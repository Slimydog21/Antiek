"""Export curated Antiek tables to Parquet for the analytics plane.

Uses runtime.db_lock.connect_read only — safe while antiek.service is writing.

  ./.venv/bin/python scripts/export_analytics_parquet.py \\
    --db ~/.antiek/antiek.duckdb \\
    --out ~/.antiek/exports/parquet/20260101

Writes manifest.json with ANTIEK_PARAM_VERSION, row counts, and UTC timestamp.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# Core research graph (Loop 1) — always exported when present.
TABLES_RESEARCH: tuple[str, ...] = (
    "syntheses",
    "outcomes",
    "synthesis_substrate_manifest",
    "write_log",
    "documents",
    "chunks",
    "nodes",
    "edges",
)

# Surfaces §10: Write / Speak / Loop 3 — exported when schema has them.
TABLES_WRITE_SPEAK: tuple[str, ...] = (
    "deliverables",
    "deliverable_sections",
    "section_blocks",
    "notebooks",
    "notebook_blocks",
    "loop_3_checklist",
    "interview_projects",
    "interviews",
)

# Monetization + federation analytics (read plane joins).
TABLES_MARKETPLACE: tuple[str, ...] = (
    "payout_decisions",
    "payout_transfers",
    "discovery_summary",
)

DEFAULT_TABLES: tuple[str, ...] = (
    TABLES_RESEARCH + TABLES_WRITE_SPEAK + TABLES_MARKETPLACE
)

# Manifest documents layer ownership for rebuild consumers (duckdb_plane §10).
TABLE_LAYER: dict[str, str] = {
    **{t: "research" for t in TABLES_RESEARCH},
    **{t: "write_speak" for t in TABLES_WRITE_SPEAK},
    **{t: "marketplace" for t in TABLES_MARKETPLACE},
}


def _export_agent_write_log_slice(
    con: object,
    out_dir: Path,
    manifest: dict,
    existing: set[str],
) -> None:
    """Agents layer: curated write_log rows (promotion_funnel, cascade_merge, …)."""
    from substrate.analytics.agent_write_purposes import sql_agent_purpose_predicate

    if "write_log" not in existing:
        manifest.setdefault("tables", {})["agent_write_log"] = {
            "status": "absent",
            "rows": 0,
            "layer": "agents",
        }
        return
    pred = sql_agent_purpose_predicate("purpose")
    dest = out_dir / "agent_write_log.parquet"
    n = con.execute(f"SELECT count(*) FROM write_log WHERE {pred}").fetchone()[0]  # type: ignore[union-attr]
    con.execute(  # type: ignore[union-attr]
        f"COPY (SELECT * FROM write_log WHERE {pred}) "
        f"TO '{dest.as_posix()}' (FORMAT PARQUET)"
    )
    manifest.setdefault("tables", {})["agent_write_log"] = {
        "status": "ok",
        "rows": int(n),
        "path": dest.name,
        "layer": "agents",
    }


def _plane_artifacts(con: object, existing: set[str]) -> dict:
    from substrate.analytics.agent_write_purposes import sql_agent_purpose_predicate
    from substrate.analytics.corpuscrawl_snapshot import corpuscrawl_plane_snapshot

    artifacts: dict = {"corpuscrawl": corpuscrawl_plane_snapshot()}
    if "write_log" in existing:
        pred = sql_agent_purpose_predicate("purpose")
        row = con.execute(  # type: ignore[union-attr]
            f"SELECT count(*), COALESCE(SUM(duration_s), 0.0) FROM write_log WHERE {pred}"
        ).fetchone()
        artifacts["agents_write_log"] = {
            "row_count": int(row[0]),
            "total_duration_s": float(row[1]),
        }
    return artifacts


def _resolve_db(path: str | None) -> str:
    raw = path or os.environ.get("ANTIEK_DUCKDB_PATH", "")
    if not raw:
        raise SystemExit(
            "ANTIEK_DUCKDB_PATH unset and --db not passed. "
            "Refuse to guess a production path."
        )
    expanded = os.path.expanduser(raw)
    if not os.path.isfile(expanded):
        raise SystemExit(f"DuckDB file not found: {expanded}")
    return expanded


def export_tables(db_path: str, out_dir: Path, tables: tuple[str, ...]) -> dict:
    from runtime.db_lock import connect_read
    from substrate.constants import ANTIEK_PARAM_VERSION

    out_dir.mkdir(parents=True, exist_ok=True)
    con = connect_read(db_path)

    manifest: dict = {
        "exported_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "antiek_param_version": ANTIEK_PARAM_VERSION,
        "source_db": db_path,
        "table_layers": TABLE_LAYER,
        "tables": {},
    }

    try:
        existing = {
            row[0]
            for row in con.execute(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_schema = 'main'"
            ).fetchall()
        }
        for table in tables:
            if table not in existing:
                manifest["tables"][table] = {"status": "absent", "rows": 0}
                continue
            dest = out_dir / f"{table}.parquet"
            n = con.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
            con.execute(
                f"COPY (SELECT * FROM {table}) TO '{dest.as_posix()}' (FORMAT PARQUET)"
            )
            manifest["tables"][table] = {"status": "ok", "rows": int(n), "path": dest.name}

        _export_agent_write_log_slice(con, out_dir, manifest, existing)
        manifest["plane_artifacts"] = _plane_artifacts(con, existing)
    finally:
        con.close()

    manifest_path = out_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default=None, help="DuckDB path (else ANTIEK_DUCKDB_PATH)")
    parser.add_argument(
        "--out",
        required=True,
        type=Path,
        help="Output directory for Parquet + manifest.json",
    )
    parser.add_argument(
        "--tables",
        default=",".join(DEFAULT_TABLES),
        help="Comma-separated table list",
    )
    args = parser.parse_args()

    db_path = _resolve_db(args.db)
    tables = tuple(t.strip() for t in args.tables.split(",") if t.strip())
    manifest = export_tables(db_path, args.out.resolve(), tables)
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()