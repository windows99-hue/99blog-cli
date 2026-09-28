"""Minimal WordPress REST API client for posts and categories."""

from html import unescape
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlsplit

import requests

from config import Config
from sanitize import sanitize_html


class WordPressError(RuntimeError):
    def __init__(self, message: str, status_code: Optional[int] = None) -> None:
        super().__init__(message)
        self.status_code = status_code


def _request(config: Config, method: str, route: str, **kwargs: Any) -> requests.Response:
    options = {"auth": (config.username, config.app_password), "timeout": (10, 30), **kwargs}
    call = requests.get if method == "GET" else requests.post
    try:
        response = call(f"{config.url}/wp-json{route}", **options)
        # /wp-json/ needs a server rewrite rule. The query form works without it.
        if response.status_code == 404 and "application/json" not in response.headers.get("Content-Type", ""):
            fallback = dict(options)
            fallback["params"] = {**options.get("params", {}), "rest_route": route}
            response = call(f"{config.url}/index.php", **fallback)
        return response
    except requests.exceptions.Timeout as exc:
        raise WordPressError("WordPress connection timed out") from exc
    except requests.exceptions.ConnectionError as exc:
        raise WordPressError(f"Cannot connect to WordPress: {exc}") from exc
    except requests.exceptions.RequestException as exc:
        raise WordPressError(f"WordPress request failed: {exc}") from exc


def _response_json(response: requests.Response, missing_post_id: Optional[int] = None) -> Any:
    if not response.ok:
        detail = ""
        try:
            error = response.json()
            if isinstance(error, dict) and isinstance(error.get("message"), str):
                detail = f": {error['message']}"
        except ValueError:
            pass
        if response.status_code in (401, 403):
            raise WordPressError(f"WordPress returned HTTP {response.status_code} (check Application Password and permissions){detail}", response.status_code)
        if response.status_code == 404 and missing_post_id is not None:
            raise WordPressError(f"WordPress post #{missing_post_id} was not found (HTTP 404); wp_id was kept unchanged{detail}", response.status_code)
        raise WordPressError(f"WordPress returned HTTP {response.status_code}{detail}", response.status_code)
    try:
        return response.json()
    except ValueError as exc:
        raise WordPressError("WordPress returned invalid JSON") from exc


def _valid_id(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def resolve_categories(config: Config, names: List[str]) -> List[int]:
    ids = []
    for name in names:
        found_id = None
        page = 1
        while True:
            response = _request(config, "GET", "/wp/v2/categories", params={"search": name, "per_page": 100, "page": page})
            results = _response_json(response)
            if not isinstance(results, list):
                raise WordPressError("WordPress returned an unexpected categories response")
            for category in results:
                if isinstance(category, dict) and unescape(str(category.get("name", ""))).strip().casefold() == name.casefold():
                    found_id = category.get("id")
                    break
            total_pages = response.headers.get("X-WP-TotalPages")
            last_page = isinstance(total_pages, str) and total_pages.isdigit() and page >= int(total_pages)
            if found_id is not None or len(results) < 100 or last_page:
                break
            page += 1
        if found_id is None:
            response = _request(config, "POST", "/wp/v2/categories", json={"name": name})
            category = _response_json(response)
            if not isinstance(category, dict):
                raise WordPressError("WordPress returned an unexpected category response")
            found_id = category.get("id")
        if not _valid_id(found_id):
            raise WordPressError(f"WordPress returned an invalid ID for category '{name}'")
        ids.append(found_id)
    return ids


def publish_post(config: Config, title: str, content: str, status: str,
                 wp_id: Optional[int] = None, categories: Optional[List[int]] = None) -> Tuple[int, str]:
    route = "/wp/v2/posts" + (f"/{wp_id}" if wp_id is not None else "")
    # WP-Editor.md treats ordinary REST HTML as Markdown and decodes escaped
    # code examples. A core HTML block makes it preserve the sanitized HTML.
    safe_content = sanitize_html(content)
    payload: Dict[str, Any] = {
        "title": title,
        "content": f"<!-- wp:html -->\n{safe_content}\n<!-- /wp:html -->",
        "status": status,
    }
    if categories is not None:
        payload["categories"] = categories
    result = _response_json(_request(config, "POST", route, json=payload), wp_id)
    if not isinstance(result, dict):
        raise WordPressError("WordPress returned an unexpected response")
    returned_id = result.get("id")
    if not _valid_id(returned_id):
        raise WordPressError("WordPress response has no valid post ID")
    if wp_id is not None and returned_id != wp_id:
        raise WordPressError(f"WordPress returned post #{returned_id} while updating #{wp_id}")
    link = result.get("link", "")
    return returned_id, link if isinstance(link, str) else ""


def upload_media(config: Config, data: bytes, mime_type: str, filename: str) -> Tuple[int, str]:
    response = _request(
        config, "POST", "/wp/v2/media", data=data,
        headers={"Content-Type": mime_type, "Content-Disposition": f'attachment; filename="{filename}"'},
    )
    result = _response_json(response)
    if not isinstance(result, dict) or not _valid_id(result.get("id")):
        raise WordPressError("WordPress media response has no valid ID")
    source_url = result.get("source_url")
    if not isinstance(source_url, str):
        raise WordPressError("WordPress media response has no usable source_url")
    parsed = urlsplit(source_url)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise WordPressError("WordPress media response has no usable source_url")
    return result["id"], source_url
