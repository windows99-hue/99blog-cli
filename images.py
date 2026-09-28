"""Find local HTML images, upload them, and replace only published HTML URLs."""

import hashlib
import mimetypes
import os
import re
from dataclasses import dataclass
from html import escape, unescape
from io import BytesIO
from pathlib import Path
from typing import Any, Dict, Optional, Tuple
from urllib.parse import unquote, urlsplit
from urllib.request import url2pathname

from config import Config
import output
from post import Post, PostError
from wordpress import WordPressError, upload_media


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
        try:
            key = os.path.relpath(local_path, post.path.parent.resolve()).replace("\\", "/")
        except ValueError:
            # Windows cannot form a relative path between different drives.
            key = local_path.as_posix()
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
        try:
            media_id, url = upload_media(config, image.data, image.mime_type, filename)
        except WordPressError as exc:
            if exc.status_code != 413:
                raise
            variant = _smaller_upload_copy(image)
            if variant is None:
                raise WordPressError(
                    f"Image {image.path.name} ({len(image.data) / 1048576:.2f} MiB) exceeds the server upload limit (HTTP 413). "
                    "Use a smaller image or raise the server request-body limit.", 413
                ) from exc
            smaller_data, smaller_mime, smaller_extension = variant
            output.warning(
                f"Image {image.path.name} exceeded the server upload limit; "
                f"retrying with a {len(smaller_data) / 1024:.0f} KiB {smaller_extension[1:].upper()} copy"
            )
            try:
                media_id, url = upload_media(
                    config, smaller_data, smaller_mime,
                    f"99blog-{image.sha256[:20]}{smaller_extension}",
                )
            except WordPressError as retry_exc:
                if retry_exc.status_code == 413:
                    raise WordPressError(
                        f"Image {image.path.name} still exceeds the server upload limit after compression (HTTP 413). "
                        "Raise the server request-body limit or resize the image.", 413
                    ) from retry_exc
                raise
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


def _smaller_upload_copy(image: LocalImage) -> Optional[Tuple[bytes, str, str]]:
    """Keep the local original and prepare a smaller upload after HTTP 413."""
    if image.mime_type not in ("image/png", "image/jpeg"):
        return None
    from PIL import Image, ImageOps, UnidentifiedImageError

    target_bytes = min(900 * 1024, max(64 * 1024, int(len(image.data) * 0.7)))
    try:
        with Image.open(BytesIO(image.data)) as original:
            if getattr(original, "is_animated", False):
                return None
            picture = ImageOps.exif_transpose(original)
            has_alpha = "A" in picture.getbands() or "transparency" in picture.info
            if has_alpha:
                if image.mime_type != "image/png":
                    return None
                picture = picture.convert("RGBA")
                format_name, mime, extension = "PNG", "image/png", ".png"
            else:
                picture = picture.convert("RGB")
                format_name, mime, extension = "JPEG", "image/jpeg", ".jpg"
            width, height = picture.size
            for scale in (1, 0.85, 0.7, 0.55, 0.4):
                candidate = picture.copy()
                if scale < 1:
                    candidate.thumbnail((max(1, int(width * scale)), max(1, int(height * scale))), Image.Resampling.LANCZOS)
                for quality in ((92, 85, 75) if format_name == "JPEG" else (None,)):
                    buffer = BytesIO()
                    settings = {"optimize": True}
                    if quality is not None:
                        settings["quality"] = quality
                    candidate.save(buffer, format=format_name, **settings)
                    data = buffer.getvalue()
                    if len(data) < target_bytes and len(data) < len(image.data):
                        return data, mime, extension
    except (OSError, ValueError, UnidentifiedImageError, Image.DecompressionBombError):
        return None
    return None


def _usable_url(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    try:
        parsed = urlsplit(value)
    except ValueError:
        return False
    return parsed.scheme in ("http", "https") and bool(parsed.netloc)
