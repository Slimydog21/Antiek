"""Sanitized HTML reader snapshot after URL/HTML ingest (SPR-AHT-04)."""

from __future__ import annotations

import hashlib
import html
import unicodedata
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlsplit

# Bump whenever allowed elements/attributes or URL normalization semantics change.
SANITIZER_VERSION = "reader-html-allowlist-v1"
_ALLOWED_ELEMENTS = frozenset(
    {
        "a",
        "article",
        "aside",
        "blockquote",
        "br",
        "caption",
        "code",
        "dd",
        "div",
        "dl",
        "dt",
        "em",
        "figcaption",
        "figure",
        "footer",
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
        "header",
        "hr",
        "img",
        "li",
        "main",
        "nav",
        "ol",
        "p",
        "pre",
        "section",
        "small",
        "span",
        "strong",
        "sub",
        "sup",
        "table",
        "tbody",
        "td",
        "tfoot",
        "th",
        "thead",
        "tr",
        "ul",
    }
)
_VOID_ELEMENTS = frozenset({"br", "hr", "img"})
_BLOCKED_ELEMENTS = frozenset(
    {
        "base",
        "button",
        "embed",
        "form",
        "iframe",
        "input",
        "link",
        "math",
        "meta",
        "object",
        "option",
        "script",
        "select",
        "style",
        "svg",
        "template",
        "textarea",
    }
)
_BLOCKED_VOID_ELEMENTS = frozenset({"base", "embed", "input", "link", "meta"})
_GLOBAL_ATTRIBUTES = frozenset({"lang", "title", "dir"})
_ELEMENT_ATTRIBUTES = {
    "a": frozenset({"href"}),
    "img": frozenset({"src", "alt", "width", "height"}),
    "td": frozenset({"colspan", "rowspan"}),
    "th": frozenset({"colspan", "rowspan", "scope"}),
}
_SAFE_SCHEMES = frozenset({"", "http", "https"})


def _safe_url(value: str, *, allow_mailto: bool) -> bool:
    decoded = html.unescape(value)
    if any(
        unicodedata.category(character).startswith("C") or ord(character) == 0xFFFD
        for character in decoded
    ):
        return False
    compact = "".join(character for character in decoded if not character.isspace())
    if compact.startswith(("#", "/")):
        return True
    scheme = urlsplit(compact).scheme.lower()
    return scheme in _SAFE_SCHEMES or (allow_mailto and scheme == "mailto")


class _SafeFragmentParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.blocked_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        name = tag.lower()
        if self.blocked_depth:
            if name in _BLOCKED_ELEMENTS and name not in _BLOCKED_VOID_ELEMENTS:
                self.blocked_depth += 1
            return
        if name in _BLOCKED_ELEMENTS:
            if name not in _BLOCKED_VOID_ELEMENTS:
                self.blocked_depth = 1
            return
        # Unknown formatting/container tags are unwrapped so their readable text
        # survives; active-content families above are removed with descendants.
        if name not in _ALLOWED_ELEMENTS:
            return
        allowed = _GLOBAL_ATTRIBUTES | _ELEMENT_ATTRIBUTES.get(name, frozenset())
        rendered: list[str] = []
        for raw_name, raw_value in attrs:
            attribute = raw_name.lower()
            value = raw_value or ""
            if attribute not in allowed or attribute.startswith("on"):
                continue
            if attribute in {"href", "src"} and not _safe_url(
                value, allow_mailto=attribute == "href"
            ):
                continue
            rendered.append(f' {attribute}="{html.escape(value, quote=True)}"')
        if name == "a" and any(part.startswith(" href=") for part in rendered):
            rendered.append(' rel="noopener noreferrer"')
        self.parts.append(f"<{name}{''.join(rendered)}>")

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)

    def handle_endtag(self, tag: str) -> None:
        name = tag.lower()
        if self.blocked_depth:
            if name in _BLOCKED_ELEMENTS and name not in _BLOCKED_VOID_ELEMENTS:
                self.blocked_depth -= 1
            return
        if name in _ALLOWED_ELEMENTS and name not in _VOID_ELEMENTS:
            self.parts.append(f"</{name}>")

    def handle_data(self, data: str) -> None:
        if not self.blocked_depth:
            self.parts.append(html.escape(data))


def sanitize_html_fragment(raw: str, *, max_chars: int = 200_000) -> str:
    parser = _SafeFragmentParser()
    parser.feed(raw[:max_chars])
    parser.close()
    return "".join(parser.parts)


def markdown_to_safe_html(markdown: str, *, max_chars: int = 500_000) -> str:
    """Minimal markdown → HTML for book/PDF reader snapshots (SPR-AHT-07)."""
    text = markdown[:max_chars]
    parts: list[str] = []
    for para in text.split("\n\n"):
        block = para.strip()
        if not block:
            continue
        if block.startswith("# "):
            parts.append(f"<h1>{html.escape(block[2:].strip())}</h1>")
        elif block.startswith("## "):
            parts.append(f"<h2>{html.escape(block[3:].strip())}</h2>")
        elif block.startswith("### "):
            parts.append(f"<h3>{html.escape(block[4:].strip())}</h3>")
        else:
            inner = "<br>\n".join(html.escape(line) for line in block.split("\n"))
            parts.append(f"<p>{inner}</p>")
    return "\n".join(parts) if parts else "<p></p>"


def build_reader_snapshot(
    *,
    source_url: str,
    document_id: str,
    ip_holder_id: str | None,
    main_html: str,
    ingested_at: str,
    title: str | None = None,
    author: str | None = None,
    source_kind: str = "url",
    canonical_content_hash: str | None = None,
    source_event_id: str | None = None,
) -> str:
    body = sanitize_html_fragment(main_html)
    projection_source_hash = "sha256:" + hashlib.sha256(main_html.encode()).hexdigest()
    snapshot_body_hash = "sha256:" + hashlib.sha256(body.encode()).hexdigest()
    # The slice preserves exactly 200,000 characters; only a larger input is truncated.
    truncated = len(main_html) > 200_000
    ih = ip_holder_id or "null"
    title_line = ""
    if title:
        title_line = f"<p><strong>Title</strong> {html.escape(title)}</p>"
    author_line = ""
    if author:
        author_line = f"<p><strong>Author</strong> {html.escape(author)}</p>"
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>Reader snapshot</title>
<style>body{{font-family:system-ui,sans-serif;max-width:720px;margin:24px auto;padding:0 16px}}
.meta{{color:#57534e;font-size:14px;border-bottom:1px solid #e7e5e4;padding-bottom:12px}}</style>
</head><body>
<div class="meta"><p><strong>Source</strong> {html.escape(source_url)} · <strong>kind</strong> {html.escape(source_kind)}</p>
{title_line}{author_line}
<p><strong>document_id</strong> {html.escape(document_id)} · <strong>ip_holder_id</strong> {html.escape(ih)}
 · <strong>ingested_at</strong> {html.escape(ingested_at)}</p>
<p><strong>canonical_content_hash</strong> {html.escape(canonical_content_hash or "unknown")}
 · <strong>projection_source_hash</strong> {projection_source_hash}
 · <strong>snapshot_body_hash</strong> {snapshot_body_hash}
 · <strong>source_event_id</strong> {html.escape(source_event_id or "unknown")}
 · <strong>sanitizer</strong> {SANITIZER_VERSION}
 · <strong>truncated</strong> {str(truncated).lower()}</p></div>
<article>{body}</article>
</body></html>"""


def write_reader_snapshot(path: Path, html_doc: str) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(html_doc, encoding="utf-8")
    return len(html_doc.encode("utf-8"))


def reader_snapshots_dir() -> Path:
    """Operator store for sanitized ingest HTML (not git; parallel to chunks)."""
    import os

    raw = os.environ.get("ANTIEK_READER_SNAPSHOTS_DIR", "").strip()
    if raw:
        return Path(raw).expanduser()
    return Path.home() / ".antiek" / "reader-snapshots"


def reader_snapshot_path_for(document_id: str) -> Path:
    safe = document_id.replace("/", "_")
    return reader_snapshots_dir() / f"{safe}.html"
