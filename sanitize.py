"""Sanitize rendered Markdown before it crosses the WordPress REST boundary."""

import bleach
from bleach.css_sanitizer import CSSSanitizer


ALLOWED_TAGS = {
    "a", "abbr", "b", "blockquote", "br", "code", "del", "details", "div", "em",
    "h1", "h2", "h3", "h4", "h5", "h6", "hr", "i", "img", "kbd", "li",
    "ol", "p", "pre", "s", "span", "strong", "sub", "sup", "table",
    "summary", "tbody", "td", "th", "thead", "tr", "u", "ul",
}
ALLOWED_ATTRIBUTES = {
    "*": ["class", "id", "title"],
    "a": ["href", "target", "rel"],
    "details": ["open"],
    "div": ["style"],
    "img": ["src", "alt", "width", "height"],
    "ol": ["start"],
    "td": ["colspan", "rowspan"],
    "th": ["colspan", "rowspan", "scope"],
}
CSS_SANITIZER = CSSSanitizer(allowed_css_properties={"padding", "border"})


def sanitize_html(content: str) -> str:
    return bleach.clean(
        content,
        tags=ALLOWED_TAGS,
        attributes=ALLOWED_ATTRIBUTES,
        protocols={"http", "https", "mailto"},
        css_sanitizer=CSS_SANITIZER,
        strip=False,
        strip_comments=True,
    )
