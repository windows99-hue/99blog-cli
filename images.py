"""Find local HTML images, upload them, and replace only published HTML URLs."""

import hashlib
import mimetypes
import os
import re
from dataclasses import dataclass
from html import escape, unescape
from pathlib import Path
from typing import Any, Dict, Tuple
from urllib.parse import unquote, urlsplit
from urllib.request import url2pathname

from config import Config
from post import Post, PostError
from wordpress import upload_media


IMG_TAG = re.compile(r"<img\b[^>]*>", re.I)
SRC_ATTR = re.compile(r"(\bsrc\s*=\s*)([\"'])(.*?)\2", re.I | re.S)


@dataclass
class LocalImage:
    key: str
    path: Path
    data: bytes
    sha256: str
    mime_type: str


def find_local_images(post: Post, html: str) -> Dict[str, LocalImage]:
    images = {}
    for tag in IMG_TAG.findall(html):
        match = SRC_ATTR.search(tag)
        if not match:
            continue
        source = unescape(match.group(3))
        try:
            parsed = urlsplit(source)
        except ValueError as exc:
            raise PostError(f"Invalid image path: {source}") from exc
        if parsed.scheme in ("http", "https", "data", "blob") or source.startswith(("//", "#")):
            continue
        if parsed.scheme == "file":
            local_path = Path(url2pathname(parsed.path))
        elif re.match(r"^[a-zA-Z]:[\\/]", source):
            local_path = Path(source)
        elif parsed.scheme or parsed.netloc or source.startswith(("/", "\\")):
            continue
        else:
            local_path = post.path.parent / unquote(parsed.path)
        local_path = local_path.resolve()
        if not local_path.is_file():
            raise PostError(f"Local image not found: {source} (looked at {local_path})")
        mime_type = mimetypes.guess_type(local_path.name)[0]
        if not mime_type or not mime_type.startswith("image/"):
            raise PostError(f"Not a supported image file: {local_path}")
        try:
            data = local_path.read_bytes()
        except OSError as exc:
            raise PostError(f"Cannot read local image {local_path}: {exc}") from exc
        key = os.path.relpath(local_path, post.path.parent.resolve()).replace("\\", "/")
        images[source] = LocalImage(key, local_path, data, hashlib.sha256(data).hexdigest(), mime_type)
    return images


def replace_with_wordpress_urls(config: Config, html: str, images: Dict[str, LocalImage],
                                previous: Dict[str, Dict[str, Any]]) -> Tuple[str, Dict[str, Dict[str, Any]], int]:
    cache = {key: dict(value) for key, value in previous.items()}
    urls = {}
    uploaded = 0
    for image in images.values():
        if image.key in urls:
            continue
        saved = cache.get(image.key)
        if not saved or saved.get("sha256") != image.sha256 or not _usable_url(saved.get("url")):
            saved = next((item for item in cache.values()
                          if item.get("sha256") == image.sha256 and _usable_url(item.get("url"))), None)
        if saved:
            cache[image.key] = saved
            urls[image.key] = saved["url"]
            continue
        extension = image.path.suffix.lower()
        if not re.fullmatch(r"\.[a-z0-9]{1,8}", extension):
            raise PostError(f"Unsupported image filename extension: {image.path.name}")
        filename = f"99blog-{image.sha256[:20]}{extension}"
        media_id, url = upload_media(config, image.data, image.mime_type, filename)
        cache[image.key] = {"sha256": image.sha256, "id": media_id, "url": url}
        urls[image.key] = url
        uploaded += 1

    def replace_tag(match: re.Match) -> str:
        tag = match.group(0)
        src = SRC_ATTR.search(tag)
        if not src:
            return tag
        source = unescape(src.group(3))
        image = images.get(source)
        if image is None:
            return tag
        return tag[:src.start(3)] + escape(urls[image.key], quote=True) + tag[src.end(3):]

    return IMG_TAG.sub(replace_tag, html), cache, uploaded


def _usable_url(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    try:
        parsed = urlsplit(value)
    except ValueError:
        return False
    return parsed.scheme in ("http", "https") and bool(parsed.netloc)
