"""Sanitized HTML reader snapshot after URL/HTML ingest (SPR-AHT-04)."""

from __future__ import annotations

import html
import re
from pathlib import Path

_SCRIPT_RE = re.compile(r"<script[\s\S]*?</script>", re.IGNORECASE)
_STYLE_RE = re.compile(r"<style[\s\S]*?</style>", re.IGNORECASE)


def sanitize_html_fragment(raw: str, *, max_chars: int = 200_000) -> str:
    text = raw[:max_chars]
    text = _SCRIPT_RE.sub("", text)
    text = _STYLE_RE.sub("", text)
    return text


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
) -> str:
    body = sanitize_html_fragment(main_html)
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
 · <strong>ingested_at</strong> {html.escape(ingested_at)}</p></div>
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