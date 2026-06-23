"""Rebuild ~/.antiek/analytics.duckdb from export_analytics_parquet output.

Replaceable analytics file — never wire the live substrate to this path.
Optional: place posthog_events.parquet in the parquet-dir before rebuild.

  ./.venv/bin/python scripts/rebuild_analytics_duckdb.py \\
    --parquet-dir ~/.antiek/exports/parquet/20260101 \\
    --out ~/.antiek/analytics.duckdb
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import duckdb  # noqa: E402

# Hard-to-vary analytics views (duckdb_plane §6). Created only when base tables exist.
_ANALYTICS_VIEWS: tuple[str, ...] = (
    """
    CREATE OR REPLACE VIEW v_research_synthesis_outcomes AS
    SELECT
      s.synthesis_id,
      s.investigation_id,
      s.status AS synthesis_status,
      s.synthesis_timestamp,
      o.outcome_id,
      o.observer AS outcome_observer,
      o.observed_at AS outcome_observed_at
    FROM syntheses s
    LEFT JOIN outcomes o ON o.synthesis_id = s.synthesis_id
    """,
    """
    CREATE OR REPLACE VIEW v_write_deliverable_depth AS
    SELECT
      d.deliverable_id,
      d.title,
      d.deliverable_kind,
      d.status,
      COUNT(DISTINCT s.section_id) AS section_count,
      SUM(COALESCE(LENGTH(s.prose_text), 0)) AS prose_chars
    FROM deliverables d
    LEFT JOIN deliverable_sections s ON s.deliverable_id = d.deliverable_id
    GROUP BY d.deliverable_id, d.title, d.deliverable_kind, d.status
    """,
    """
    CREATE OR REPLACE VIEW v_speak_interview_funnel AS
    SELECT
      p.project_id,
      p.title AS project_title,
      i.interview_id,
      i.status AS interview_status,
      i.invited_at,
      i.completed_at,
      i.transcript_document_id
    FROM interview_projects p
    LEFT JOIN interviews i ON i.project_id = p.project_id
    """,
    """
    CREATE OR REPLACE VIEW v_write_log_purpose_rollup AS
    SELECT
      purpose,
      COUNT(*) AS write_count,
      SUM(COALESCE(duration_s, 0.0)) AS total_duration_s,
      SUM(CASE WHEN success THEN 1 ELSE 0 END) AS success_count
    FROM write_log
    GROUP BY purpose
    ORDER BY write_count DESC
    """,
)


def _table_exists(con: duckdb.DuckDBPyConnection, name: str) -> bool:
    row = con.execute(
        "SELECT 1 FROM information_schema.tables "
        "WHERE table_schema = 'main' AND table_name = ?",
        [name],
    ).fetchone()
    return row is not None


def _create_analytics_views(
    con: duckdb.DuckDBPyConnection, parquet_dir: Path
) -> None:
    """Install cross-layer views when prerequisite tables were loaded."""
    need = {
        0: ("syntheses",),
        1: ("deliverables", "deliverable_sections"),
        2: ("interview_projects", "interviews"),
        3: ("write_log",),
    }
    view_names = (
        "v_research_synthesis_outcomes",
        "v_write_deliverable_depth",
        "v_speak_interview_funnel",
        "v_write_log_purpose_rollup",
    )
    for idx, tables in need.items():
        if all(_table_exists(con, t) for t in tables):
            con.execute(_ANALYTICS_VIEWS[idx])
            print(f"view: {view_names[idx]}")

    if _table_exists(con, "dispatch_calls"):
        con.execute(
            """
            CREATE OR REPLACE VIEW v_engine_dispatch_by_workflow AS
            SELECT
              workflow,
              COUNT(*) AS call_count,
              SUM(COALESCE(cost_usd, 0.0)) AS total_cost_usd,
              SUM(CASE WHEN is_remote_exec THEN COALESCE(cost_usd, 0.0) ELSE 0.0 END)
                AS remote_exec_cost_usd
            FROM dispatch_calls
            GROUP BY workflow
            """
        )
        print("view: v_engine_dispatch_by_workflow")
        if _table_exists(con, "syntheses"):
            con.execute(
                """
                CREATE OR REPLACE VIEW v_research_investigation_dispatch_cost AS
                SELECT
                  s.investigation_id,
                  s.synthesis_id,
                  COALESCE(SUM(d.cost_usd), 0.0) AS dispatch_cost_usd,
                  COUNT(d.event_id) AS dispatch_call_count
                FROM syntheses s
                LEFT JOIN dispatch_calls d
                  ON d.investigation_id = s.investigation_id
                GROUP BY s.investigation_id, s.synthesis_id
                """
            )
            print("view: v_research_investigation_dispatch_cost")

    if _table_exists(con, "write_log"):
        from substrate.analytics.agent_write_purposes import sql_agent_purpose_predicate

        pred = sql_agent_purpose_predicate("purpose")
        con.execute(
            f"CREATE OR REPLACE VIEW v_agents_write_log AS "
            f"SELECT * FROM write_log WHERE {pred}"
        )
        con.execute(
            f"""
            CREATE OR REPLACE VIEW v_agents_write_rollup AS
            SELECT
              purpose,
              COUNT(*) AS write_count,
              SUM(COALESCE(duration_s, 0.0)) AS total_duration_s,
              SUM(CASE WHEN success THEN 1 ELSE 0 END) AS success_count
            FROM write_log
            WHERE {pred}
            GROUP BY purpose
            ORDER BY write_count DESC
            """
        )
        print("view: v_agents_write_log")
        print("view: v_agents_write_rollup")

    agent_pq = parquet_dir / "agent_write_log.parquet"
    if agent_pq.is_file() and not _table_exists(con, "agent_write_log"):
        con.execute(
            "CREATE OR REPLACE TABLE agent_write_log AS "
            f"SELECT * FROM read_parquet('{agent_pq.as_posix()}')"
        )
        print("loaded agent_write_log (agents slice)")


def rebuild(parquet_dir: Path, out_db: Path) -> None:
    manifest_path = parquet_dir / "manifest.json"
    if not manifest_path.is_file():
        raise SystemExit(
            f"manifest.json missing in {parquet_dir} — run export_analytics_parquet.py first"
        )

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if out_db.is_file():
        out_db.unlink()

    con = duckdb.connect(str(out_db))
    try:
        con.execute("CREATE TABLE IF NOT EXISTS _export_manifest (manifest JSON);")
        con.execute(
            "INSERT INTO _export_manifest VALUES (?::JSON);",
            [json.dumps(manifest)],
        )

        for table, info in manifest.get("tables", {}).items():
            if info.get("status") != "ok":
                continue
            pq = parquet_dir / info.get("path", f"{table}.parquet")
            if not pq.is_file():
                print(f"skip {table}: {pq} missing", file=sys.stderr)
                continue
            con.execute(
                f"CREATE OR REPLACE TABLE {table} AS "
                f"SELECT * FROM read_parquet('{pq.as_posix()}')"
            )
            print(f"loaded {table} ({info.get('rows', '?')} rows)")

        optional_ph = parquet_dir / "posthog_events.parquet"
        if optional_ph.is_file():
            con.execute(
                "CREATE OR REPLACE TABLE posthog_events AS "
                f"SELECT * FROM read_parquet('{optional_ph.as_posix()}')"
            )
            print("loaded posthog_events (optional)")

        dispatch_pq = parquet_dir / "dispatch_calls.parquet"
        if dispatch_pq.is_file():
            con.execute(
                "CREATE OR REPLACE TABLE dispatch_calls AS "
                f"SELECT * FROM read_parquet('{dispatch_pq.as_posix()}')"
            )
            print("loaded dispatch_calls (engine / jsonl export)")

        _create_analytics_views(con, parquet_dir)
    finally:
        con.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--parquet-dir", required=True, type=Path)
    parser.add_argument(
        "--out",
        type=Path,
        default=Path(os.path.expanduser("~/.antiek/analytics.duckdb")),
        help="Analytics DuckDB path (default: ~/.antiek/analytics.duckdb)",
    )
    args = parser.parse_args()
    rebuild(args.parquet_dir.resolve(), args.out.expanduser().resolve())
    print(f"analytics plane: {args.out}")


if __name__ == "__main__":
    main()