"""P1 §6 — full-graph export bundle (read half). ``GET /export/my-graph``.

Streams a downloadable zip of the operator's full knowledge graph:

- ``graph/`` — DuckDB ``EXPORT DATABASE`` snapshot of the graph DB
  (``schema.sql`` + ``load.sql`` + per-table Parquet shards), taken on a
  READ-ONLY connection under the same exclusive writer flock that
  ``runtime/db_lock.connect_write`` uses — mirroring the proven pattern in
  ``infrastructure/ansible/templates/backup.sh.j2``. The malformed
  ``schema.sql`` DuckDB emits for self-referential FKs is normalized with
  ``tools/backup_normalize_schema.py`` so the bundle restores via
  ``IMPORT DATABASE``.
- ``events/`` — sealed event-log Parquet files plus live JSONL tails, copied
  byte-for-byte. No locks: the event log is append-only by construction
  (substrate/event_log/events.py), so reads never race a writer.
- ``manifest.json`` — generated_at, source db basename, schema versions,
  counts, and an explicit ``graph_not_mutated`` statement.

READ-ONLY CONTRACT
------------------
The source graph is never opened for write and no table is written. The only
on-disk side effects besides the /tmp bundle are the writer-coordination
sidecar conventions every writer already uses: the ``<db>.write.lock`` file
is created if absent and stamped (never unlinked) — the identical protocol
``connect_write`` follows — so a concurrent writer is excluded for the
minimal snapshot window and the DB file itself is untouched.

Why not ``connect_write``? It opens DuckDB for WRITE (the backup template
documents this exact reason) and appends a ``write_log`` row — a mutation of
the source DB. Why not ``authority_handoff_guard``? It too appends a
``write_log`` row on exit. The backup script's manual flock is the
read-only-correct pattern and is reused here verbatim.

MASTER.md
---------
Rendered MASTER.md files are NOT stored in the graph store. Orchestrator
phase 7 (``orchestration/loop_one/orchestrator.py``) calls
``skills/domain/master_md.py::generate_master_md``, which writes
``<ANTIEK_RESEARCH_DIR|~/research>/<topic_slug>/MASTER.md`` — an
operator-machine path outside ``~/.antiek``; neither ``services/`` nor
``middleware/archive/`` stores rendered markdown (the syntheses table, which
IS the render input, is carried by the DuckDB export). The bundle therefore
omits renderings and the manifest documents ``n/a — generated on demand``
honestly instead of scraping a non-canonical directory.
"""

from __future__ import annotations

import errno
import fcntl
import json
import os
import shutil
import stat
import sys
import tempfile
import time
import zipfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fastapi import APIRouter, FastAPI, HTTPException, Request
from fastapi.responses import StreamingResponse

# Ensure package root on path for direct uvicorn invocation.
_PKG_ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)
if _PKG_ROOT not in sys.path:
    sys.path.insert(0, _PKG_ROOT)

from substrate.event_log import EVENT_SCHEMA_VERSION, default_events_dir  # noqa: E402
from substrate.graph import default_db_path  # noqa: E402

export_router = APIRouter(prefix="/export", tags=["export"])

# Lock-window ceiling for the consistent snapshot. Shorter than the writer
# default (300s): an HTTP request must fail loudly rather than pin a request
# thread for minutes behind a stuck writer.
EXPORT_LOCK_TIMEOUT_S = 15.0

# Value-free 503 details: never echo paths, exceptions, or stack traces.
_DB_UNAVAILABLE = "graph database unavailable"
_EXPORT_FAILED = "graph export failed"
_LOCK_BUSY = "graph write lock held by another process"


class _ExportUnavailable(RuntimeError):
    """Internal marker mapped to a value-free 503 at the route boundary.

    ``detail`` is one of the module-level value-free 503 strings — never a
    path, exception text, or stack trace."""

    def __init__(self, detail: str) -> None:
        super().__init__(detail)
        self.detail = detail


def register_export_routes(app: FastAPI) -> None:
    """Mount the full-graph export route. Called from ``create_app`` — one
    line, same inclusion discipline as the artifact/speak routers. The route
    carries no per-handler auth: the global operator-auth middleware covers
    it."""
    app.include_router(export_router)


@export_router.get("/my-graph")
async def export_my_graph(request: Request) -> StreamingResponse:
    """Stream the full-graph export bundle as ``antiek-graph-export-YYYYMMDD.zip``.

    Errors are value-free 503s: a missing/unopenable/locked DB or a failed
    export is reported as an opaque failure, never with paths or exception
    text (the operator DB path is a deployment secret).
    """
    db_path = default_db_path()
    if not db_path or not os.path.isfile(db_path):
        raise HTTPException(status_code=503, detail=_DB_UNAVAILABLE)

    bundle_root: Path | None = None
    try:
        bundle_root = Path(tempfile.mkdtemp(prefix="antiek-graph-export-"))
        graph_dir = bundle_root / "graph"
        events_dir = bundle_root / "events"
        graph_dir.mkdir()
        events_dir.mkdir()

        tables, table_rows, duckdb_version = _export_graph(db_path, graph_dir)
        event_counts = _copy_event_files(default_events_dir(), events_dir)

        manifest = {
            "generated_at": datetime.now(UTC).isoformat(),
            "source_db_path": os.path.basename(os.path.abspath(db_path)),
            "duckdb_version": duckdb_version,
            "schema_version": "v1 (ANTIEK_GRAPH_SCHEMA_V1_SQL — cumulative DDL "
            "script; the DB carries no per-database marker)",
            "event_schema_version": EVENT_SCHEMA_VERSION,
            "counts": {
                "tables": len(tables),
                "table_rows": table_rows,
                "event_files": event_counts["parquet"] + event_counts["jsonl"],
                "event_parquet_files": event_counts["parquet"],
                "event_jsonl_files": event_counts["jsonl"],
                "master_files": 0,
            },
            "master_md": _master_md_status(),
            "graph_not_mutated": True,
        }
        (bundle_root / "manifest.json").write_text(
            json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8"
        )

        zip_name = f"antiek-graph-export-{datetime.now(UTC):%Y%m%d}.zip"
        zip_path = bundle_root / zip_name
        _zip_bundle(bundle_root, zip_path)
        size = zip_path.stat().st_size
        return StreamingResponse(
            _stream_zip_then_cleanup(zip_path, bundle_root),
            media_type="application/zip",
            headers={
                "Content-Disposition": f'attachment; filename="{zip_name}"',
                "Content-Length": str(size),
                "X-Content-Type-Options": "nosniff",
            },
        )
    except HTTPException:
        _cleanup(bundle_root)
        raise
    except _ExportUnavailable as exc:
        _cleanup(bundle_root)
        raise HTTPException(status_code=503, detail=exc.detail) from None
    except Exception:
        _cleanup(bundle_root)
        raise HTTPException(status_code=503, detail=_EXPORT_FAILED) from None


def _export_graph(
    db_path: str, out_dir: Path
) -> tuple[list[str], dict[str, int], str]:
    """Consistent read-only snapshot via DuckDB EXPORT under the writer flock.

    Mirrors ``infrastructure/ansible/templates/backup.sh.j2``: acquire the
    exclusive sidecar flock (``<db>.write.lock``, same inode discipline as
    ``connect_write``), open the DB READ-ONLY (EXPORT works on a read-only
    connection — the backup template proves it and this route tests it),
    export, release. The ``write_log`` row that ``connect_write`` /
    ``authority_handoff_guard`` would append is deliberately NOT written —
    that would mutate the source DB.

    Returns (table names, per-table row counts, duckdb version string).
    """
    lock_path = db_path + ".write.lock"
    parent = os.path.dirname(lock_path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    # Never unlink the sidecar: flock authority belongs to its inode
    # (runtime/db_lock.py connect_write comment — replacing the pathname
    # while another process holds the old inode would split the lock).
    fd = os.open(lock_path, os.O_CREAT | os.O_WRONLY, 0o600)
    acquired = False
    try:
        deadline = time.monotonic() + EXPORT_LOCK_TIMEOUT_S
        while True:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                acquired = True
                break
            except OSError as exc:
                if exc.errno not in (errno.EWOULDBLOCK, errno.EAGAIN):
                    raise
                if time.monotonic() >= deadline:
                    raise _ExportUnavailable(_LOCK_BUSY) from None
                time.sleep(0.1)
        # Stamp pid + purpose + timestamp for ops debugging — best-effort,
        # exactly like connect_write.
        try:
            os.ftruncate(fd, 0)
            os.write(
                fd,
                (
                    f"{os.getpid()} api:export "
                    f"{time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}\n"
                ).encode(),
            )
        except OSError:
            pass

        import duckdb

        try:
            con = duckdb.connect(db_path, read_only=True)
        except Exception:
            raise _ExportUnavailable(_DB_UNAVAILABLE) from None
        try:
            # Counts capture happens on the SAME connection inside the SAME
            # lock window as the EXPORT, so the counts are exactly the
            # snapshot's (backup.sh.j2 discipline).
            con.execute("BEGIN TRANSACTION")
            tables = [
                row[0]
                for row in con.execute(
                    "SELECT table_name FROM information_schema.tables "
                    "WHERE table_schema = 'main' AND table_type = 'BASE TABLE' "
                    "ORDER BY table_name"
                ).fetchall()
            ]
            table_rows: dict[str, int] = {}
            for t in tables:
                quoted = '"' + t.replace('"', '""') + '"'
                table_rows[t] = con.execute(
                    f"SELECT COUNT(*) FROM {quoted}"
                ).fetchone()[0]
            # EXPORT DATABASE takes a literal path (no bound parameter —
            # DuckDB rejects '?'), so escape single quotes for the SQL
            # string literal.
            escaped = str(out_dir).replace("'", "''")
            con.execute(f"EXPORT DATABASE '{escaped}' (FORMAT PARQUET);")
            duckdb_version = con.execute("SELECT version()").fetchone()[0]
            con.execute("COMMIT")
        finally:
            con.close()
    finally:
        if acquired:
            fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)

    # Normalize the malformed schema.sql DuckDB EXPORT emits for
    # self-referential FKs (edges.superseded_by, deliverable_sections.
    # parent_section_id) so the bundle restores via IMPORT DATABASE. Done
    # after lock release — same as backup.sh.j2 step 1b.
    schema_path = out_dir / "schema.sql"
    if schema_path.exists():
        from tools.backup_normalize_schema import normalize_exported_schema_sql

        raw = schema_path.read_text(encoding="utf-8")
        fixed = normalize_exported_schema_sql(raw)
        if fixed != raw:
            schema_path.write_text(fixed, encoding="utf-8")
    return tables, table_rows, duckdb_version


def _copy_event_files(events_root: str, out_dir: Path) -> dict[str, int]:
    """Copy sealed ``*.parquet`` + live ``*.jsonl`` event files byte-for-byte.

    No locks on the event log (append-only by construction); a torn tail
    line in a live JSONL is copied as-is, exactly like the nightly backup.
    Symlinks are skipped (the hardened reader in substrate/event_log/events.py
    treats non-regular event files as a physical-trajectory error).
    """
    counts = {"parquet": 0, "jsonl": 0}
    if not events_root or not os.path.isdir(events_root):
        return counts
    for name in sorted(os.listdir(events_root)):
        src = os.path.join(events_root, name)
        try:
            info = os.lstat(src)
        except OSError:
            continue
        if not stat.S_ISREG(info.st_mode):
            continue
        if name.endswith(".parquet"):
            shutil.copyfile(src, out_dir / name)
            counts["parquet"] += 1
        elif name.endswith(".jsonl"):
            shutil.copyfile(src, out_dir / name)
            counts["jsonl"] += 1
    return counts


def _master_md_status() -> dict[str, Any]:
    """Honest MASTER.md section: renderings are not stored in the graph store.

    Verified against the codebase (P1 §6): orchestrator phase 7 renders via
    ``skills/domain/master_md.py`` to ``<ANTIEK_RESEARCH_DIR|~/research>/
    <topic_slug>/MASTER.md`` — an operator-machine path outside the Antiek
    store; neither ``services/`` nor ``middleware/archive/`` stores rendered
    markdown. The render input (``syntheses`` + ``synthesis_substrate_manifest``
    rows) IS included in ``graph/`` via the DuckDB export, so the renderings
    can be regenerated on demand.
    """
    return {
        "status": "n/a — generated on demand",
        "note": (
            "Rendered MASTER.md files are not stored in the graph store; "
            "orchestrator phase 7 writes them to ANTIEK_RESEARCH_DIR/<slug>/"
            "MASTER.md on the operator machine (skills/domain/master_md.py). "
            "The render input (syntheses + synthesis_substrate_manifest rows) "
            "is included in graph/ via the DuckDB export."
        ),
    }


def _zip_bundle(bundle_root: Path, zip_path: Path) -> None:
    """Zip ``graph/`` + ``events/`` + ``manifest.json`` with stable arcnames
    (sorted walk → reproducible archives). The zip file itself is skipped."""
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for child in sorted(bundle_root.iterdir()):
            if child.name == zip_path.name:
                continue
            if child.is_dir():
                for path in sorted(child.rglob("*")):
                    if path.is_file():
                        zf.write(path, path.relative_to(bundle_root).as_posix())
            elif child.is_file():
                zf.write(child, child.name)


def _stream_zip_then_cleanup(zip_path: Path, bundle_root: Path) -> Any:
    """Yield the zip in 1 MiB chunks; remove the temp bundle when streaming
    finishes (including client disconnect)."""
    try:
        with open(zip_path, "rb") as f:
            while chunk := f.read(1024 * 1024):
                yield chunk
    finally:
        _cleanup(bundle_root)


def _cleanup(bundle_root: Path | None) -> None:
    if bundle_root is not None:
        shutil.rmtree(bundle_root, ignore_errors=True)


__all__ = [
    "EXPORT_LOCK_TIMEOUT_S",
    "export_router",
    "register_export_routes",
]
