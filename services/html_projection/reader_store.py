"""Fail-closed filesystem store for derived reader HTML projections."""

from __future__ import annotations

import hashlib
import html
import os
import tempfile
from datetime import UTC, datetime
from pathlib import Path


def reader_snapshots_dir() -> Path:
    raw = os.environ.get("ANTIEK_READER_SNAPSHOTS_DIR", "").strip()
    if raw:
        return Path(raw).expanduser()
    antiek_home = os.environ.get("ANTIEK_HOME", "").strip()
    if antiek_home:
        return Path(antiek_home).expanduser() / "reader-snapshots"
    return Path.home() / ".antiek" / "reader-snapshots"


def reader_snapshot_path_for(document_id: str) -> Path:
    safe = document_id.replace("/", "_")
    return reader_snapshots_dir() / f"{safe}.html"


def atomic_write_reader_snapshot(path: Path, html_doc: str) -> int:
    """Replace one complete projection without exposing partial bytes."""
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = html_doc.encode("utf-8")
    fd, raw_tmp = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    tmp = Path(raw_tmp)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)
    return len(payload)


def invalidate_reader_projection(
    document_id: str,
    *,
    reason: str,
    source_event_id: str | None,
) -> tuple[str, str]:
    """Remove readable bytes first, then publish a static revocation receipt.

    Unlink-before-write is deliberate: if the receipt write fails, revoked full
    text remains absent. Availability may fail closed; rights enforcement cannot.
    """
    path = reader_snapshot_path_for(document_id)
    path.unlink(missing_ok=True)
    rendered = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>Reader unavailable</title></head>
<body><main><h1>Document unavailable for reading</h1>
<p><strong>document_id</strong> {html.escape(document_id)}</p>
<p><strong>viewability</strong> non-viewable · <strong>reason</strong> {html.escape(reason)}</p>
<p><strong>servability</strong> taken_down · <strong>source_event_id</strong> {html.escape(source_event_id or "unknown")}</p>
<p><strong>invalidated_at</strong> {datetime.now(UTC).isoformat()}</p>
</main></body></html>"""
    atomic_write_reader_snapshot(path, rendered)
    digest = "sha256:" + hashlib.sha256(rendered.encode()).hexdigest()
    return str(path), digest
