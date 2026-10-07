"""Read Markdown, validate front matter, and safely persist a new WordPress ID."""

import os
import re
import stat
import tempfile
from dataclasses import dataclass
from html import escape
from pathlib import Path
from typing import Any, Dict, List, Optional

import markdown
import yaml
from markdown.extensions import Extension
from markdown.preprocessors import Preprocessor


class PostError(ValueError):
    pass


WINDOWS_IMAGE_DEST = re.compile(r"(!\[[^\]\n]*\]\()([a-zA-Z]:\\[^)\n]+)(\))")


def _normalize_windows_image_paths(body: str) -> str:
    """Keep Markdown from treating a Windows separator before # as an escape."""
    return WINDOWS_IMAGE_DEST.sub(
        lambda match: match.group(1) + match.group(2).replace("\\", "/") + match.group(3),
        body,
    )


@dataclass
class Post:
    path: Path
    original: bytes
    metadata: Dict[str, Any]
    body: str
    title: str
    status: str
    categories: List[str]
    wp_media: Dict[str, Dict[str, Any]]
    wp_id: Optional[int]
    newline: str
    bom: bool
    has_front_matter: bool

    @property
    def html(self) -> str:
        html = markdown.markdown(
            _normalize_windows_image_paths(self.body),
            extensions=["fenced_code", "tables", "md_in_html", "admonition", "pymdownx.quotes", "pymdownx.arithmatex", "pymdownx.tilde", _MathBlockExtension()],
            extension_configs={
                "pymdownx.quotes": {"callouts": True},
                "pymdownx.tilde": {"subscript": False, "smart_delete": False},
                "pymdownx.arithmatex": {
                    "generic": True,
                    "preview": False,
                    "tex_inline_wrap": ["", ""],
                    "tex_block_wrap": ["", ""],
                }
            },
        )
        # The site's WP-Editor.md script renders these two KaTeX classes.
        return (html.replace('<span class="arithmatex">', '<span class="katex math inline">')
                    .replace('<div class="arithmatex">', '<div class="katex math multi-line">'))

    def write_metadata(self, wp_id: int, title: str, status: str,
                       categories: Optional[List[str]] = None,
                       wp_media: Optional[Dict[str, Dict[str, Any]]] = None) -> None:
        if not isinstance(wp_id, int) or isinstance(wp_id, bool) or wp_id <= 0:
            raise PostError("WordPress returned an invalid post ID")
        if self.wp_id is not None and wp_id != self.wp_id:
            raise PostError("WordPress returned a different post ID")
        data = dict(self.metadata)
        data.update(title=title, status=status, wp_id=wp_id)
        if categories is not None and (categories or "categories" in data):
            data["categories"] = categories
        if wp_media is not None and (wp_media or "wp_media" in data):
            data["wp_media"] = wp_media
        header = yaml.safe_dump(data, allow_unicode=True, sort_keys=False).replace("\n", self.newline)
        updated = ("\ufeff" if self.bom else "") + "---" + self.newline + header + "---" + self.newline + self.body
        encoded = updated.encode("utf-8")
        temp_name = None
        try:
            if self.path.read_bytes() != self.original:
                raise PostError("Markdown changed while publishing; WordPress post was sent, but local metadata was not saved")
            with tempfile.NamedTemporaryFile(mode="wb", dir=self.path.parent, prefix=f".{self.path.name}.", suffix=".tmp", delete=False) as temp:
                temp_name = temp.name
                temp.write(encoded)
                temp.flush()
                os.fsync(temp.fileno())
            os.chmod(temp_name, stat.S_IMODE(self.path.stat().st_mode))
            os.replace(temp_name, self.path)
        except OSError as exc:
            raise PostError(f"WordPress post was sent, but metadata could not be saved to {self.path}: {exc}") from exc
        finally:
            if temp_name and os.path.exists(temp_name):
                os.unlink(temp_name)


def read_post(path: Path) -> Post:
    try:
        original = path.read_bytes()
        text = original.decode("utf-8-sig")
    except (OSError, UnicodeError) as exc:
        raise PostError(f"Cannot read Markdown file {path}: {exc}") from exc
    bom = original.startswith(b"\xef\xbb\xbf")
    lines = text.splitlines(keepends=True)
    has_front_matter = bool(lines and lines[0].strip() == "---")
    if has_front_matter:
        closing = next((i for i in range(1, len(lines)) if lines[i].strip() == "---"), None)
        if closing is None:
            raise PostError("YAML front matter has no closing --- line")
        front_matter = "".join(lines[1:closing])
        body = "".join(lines[closing + 1:])
        try:
            data = yaml.safe_load(front_matter) or {}
        except yaml.YAMLError as exc:
            raise PostError(f"Invalid YAML front matter: {exc}") from exc
        if not isinstance(data, dict):
            raise PostError("Front matter must be a YAML mapping")
    else:
        data = {}
        body = text
    title = data.get("title") or path.stem
    if not isinstance(title, str):
        raise PostError("title must be text")
    status = data.get("status", "draft")
    if status not in ("draft", "publish"):
        raise PostError("status must be draft or publish")
    categories = data.get("categories") or []
    if not isinstance(categories, list) or any(not isinstance(item, str) or not item.strip() for item in categories):
        raise PostError("categories must be a list of non-empty names")
    categories = [item.strip() for item in categories]
    wp_media = data.get("wp_media") or {}
    if not isinstance(wp_media, dict) or any(not isinstance(key, str) or not isinstance(value, dict) for key, value in wp_media.items()):
        raise PostError("wp_media must be a mapping of local image paths to upload details")
    wp_id = data.get("wp_id")
    if wp_id is not None and (not isinstance(wp_id, int) or isinstance(wp_id, bool) or wp_id <= 0):
        raise PostError("wp_id must be empty or a positive integer")
    newline = "\r\n" if "\r\n" in text else "\n"
    return Post(path, original, data, body, title.strip() or path.stem, status, categories, wp_media, wp_id, newline, bom, has_front_matter)


class _MathBlockExtension(Extension):
    def extendMarkdown(self, md):
        # Run after fenced code is protected, before HTML and paragraph splitting.
        md.preprocessors.register(_MathBlockPreprocessor(md), "99blog-math-blocks", 24)


class _MathBlockPreprocessor(Preprocessor):
    """Protect complete display formulas, including blank lines and quote prefixes."""

    QUOTE_PREFIX = re.compile(r"^(?: {0,3}> ?)*")
    QUOTE_MARKER = re.compile(r"^ {0,3}> ?")
    DELIMITER = re.compile(r"^ {0,3}(\$\$|\\\[|\\\])[ \t]*$")
    FENCE = re.compile(r"^ {0,3}(`{3,}|~{3,})")

    def run(self, lines):
        result = []
        fence = None
        index = 0
        while index < len(lines):
            line = lines[index]
            prefix = self.QUOTE_PREFIX.match(line).group()
            depth = prefix.count(">")
            content = line[len(prefix):]
            code_fence = self.FENCE.match(content)
            if fence is not None and depth != fence[2]:
                fence = None
            if code_fence:
                marker = code_fence.group(1)
                if fence is None:
                    fence = (marker[0], len(marker), depth)
                elif marker[0] == fence[0] and len(marker) >= fence[1] and not content[code_fence.end():].strip():
                    fence = None
                result.append(line)
                index += 1
                continue
            opening = self.DELIMITER.match(content) if fence is None else None
            if opening and opening.group(1) in ("$$", r"\["):
                closing = "$$" if opening.group(1) == "$$" else r"\]"
                math_lines = []
                matched = False
                end = index + 1
                while end < len(lines):
                    math_line = lines[end]
                    quote_depth = 0
                    for _ in range(depth):
                        quote = self.QUOTE_MARKER.match(math_line)
                        if quote is None:
                            break
                        math_line = math_line[quote.end():]
                        quote_depth += 1
                    if quote_depth != depth and math_line.strip():
                        break
                    delimiter = self.DELIMITER.match(math_line)
                    if delimiter and delimiter.group(1) == closing:
                        tex = "\n" + "\n".join(math_lines) + "\n"
                        placeholder = self.md.htmlStash.store(
                            '<div class="katex math multi-line">' + escape(tex, quote=False) + '</div>'
                        )
                        result.extend([prefix.rstrip(), prefix + placeholder, prefix.rstrip()])
                        index = end + 1
                        matched = True
                        break
                    math_lines.append(math_line)
                    end += 1
                if matched:
                    continue
            result.append(line)
            index += 1
        return result
