"""Read-only snapshot of corpuscrawl FTS store for analytics manifest (not graph truth).

Uses ``connect_read`` on ``~/.corpuscrawl/corpus.duckdb`` per duckdb_plane store topology.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any


def default_corpus_db() -> Path:
    override = os.environ.get("CORPUSCRAWL_DUCKDB_PATH", "").strip()
    if override:
        return Path(os.path.expanduser(override))
    return Path.home() / ".corpuscrawl" / "corpus.duckdb"


def corpuscrawl_plane_snapshot(db_path: Path | None = None) -> dict[str, Any]:
    """JSON-serializable health block for ``manifest.json`` plane_artifacts."""
    path = (db_path or default_corpus_db()).expanduser()
    if not path.is_file():
        return {
            "layer": "discovery_fts",
            "status": "absent",
            "path": str(path),
            "note": "Run corpuscrawl build; separate from antiek.duckdb",
        }
    from runtime.db_lock import connect_read

    try:
        con = connect_read(str(path))
    except Exception as exc:
        return {
            "layer": "discovery_fts",
            "status": "unreadable",
            "path": str(path),
            "error": str(exc)[:200],
        }
    try:
        row = con.execute("SELECT count(*) FROM docs").fetchone()
        doc_count = int(row[0]) if row else 0
        projects = con.execute(
            "SELECT project, count(*) AS n FROM docs GROUP BY 1 ORDER BY n DESC LIMIT 10"
        ).fetchall()
    except Exception as exc:
        return {
            "layer": "discovery_fts",
            "status": "schema_error",
            "path": str(path),
            "error": str(exc)[:200],
        }
    finally:
        con.close()
    return {
        "layer": "discovery_fts",
        "status": "ok",
        "path": str(path),
        "doc_count": doc_count,
        "top_projects": [{"project": p[0], "count": int(p[1])} for p in projects],
    }