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
    return _STYLE_RE.sub("", text)


def build_reader_snapshot(
    *,
    source_url: str,
    document_id: str,
    ip_holder_id: str | None,
    main_html: str,
    ingested_at: str,
) -> str:
    body = sanitize_html_fragment(main_html)
    ih = ip_holder_id or "null"
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>Reader snapshot</title>
<style>body{{font-family:system-ui,sans-serif;max-width:720px;margin:24px auto;padding:0 16px}}
.meta{{color:#57534e;font-size:14px;border-bottom:1px solid #e7e5e4;padding-bottom:12px}}</style>
</head><body>
<div class="meta"><p><strong>Source</strong> {html.escape(source_url)}</p>
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