"""Per-call burn telemetry — Engine (jsonl) and OLTP write_log (duckdb_plane §13).

Reads only; never opens a graph writer. Event log is canonical for dispatch
cost; ``analytics.duckdb`` and ``connect_read`` on OLTP are optional fast paths.
"""

from __future__ import annotations

import os
from collections import defaultdict
from decimal import Decimal
from pathlib import Path
from typing import Any, Literal

from substrate.analytics.dispatch_rows import iter_dispatch_call_rows
from substrate.coordination.cost_view import build_cost_view

GroupBy = Literal["workflow", "provider", "model", "tool", "role"]

_GROUP_KEYS: dict[GroupBy, str] = {
    "workflow": "workflow",
    "provider": "provider",
    "model": "model",
    "tool": "target_role",
    "role": "role",
}


def _decimal_sum(values: list[object]) -> Decimal:
    total = Decimal("0")
    for v in values:
        if v is None:
            continue
        total += Decimal(str(v))
    return total


def report_dispatch_groups(
    *,
    events_dir: str | None = None,
    investigation_ids: list[str] | None = None,
    group_by: GroupBy = "workflow",
) -> list[dict[str, Any]]:
    """Aggregate ``dispatch.call`` rows from the canonical event log."""
    key = _GROUP_KEYS[group_by]
    buckets: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in iter_dispatch_call_rows(
        events_dir=events_dir,
        investigation_ids=investigation_ids,
    ):
        label = row.get(key) or "(unset)"
        buckets[str(label)].append(row)

    out: list[dict[str, Any]] = []
    for label in sorted(buckets.keys()):
        rows = buckets[label]
        costs = [r.get("cost_usd") for r in rows]
        out.append(
            {
                "group_by": group_by,
                "key": label,
                "call_count": len(rows),
                "cost_usd": float(_decimal_sum(costs)),
                "remote_exec_cost_usd": float(
                    _decimal_sum(
                        [
                            r.get("cost_usd")
                            for r in rows
                            if r.get("is_remote_exec")
                        ]
                    )
                ),
            }
        )
    return out


def report_cost_view_summary(
    *,
    events_dir: str | None = None,
    investigation_ids: list[str] | None = None,
) -> dict[str, Any]:
    """Workflow-level summary via :func:`build_cost_view` (same numbers as API)."""
    view = build_cost_view(
        events_dir=events_dir, investigation_ids=investigation_ids
    )
    return {
        "source": "events",
        "events_dir": view.events_dir,
        "aggregate": {
            "call_count": view.aggregate_call_count,
            "raw_cost_usd": float(view.aggregate_raw_cost_usd),
            "remote_exec_cost_usd": float(view.aggregate_remote_exec_cost_usd),
        },
        "per_workflow": [
            {
                "workflow": w.workflow.value,
                "call_count": w.call_count,
                "raw_cost_usd": float(w.raw_cost_usd),
                "remote_exec_cost_usd": float(w.remote_exec_cost_usd),
                "margin_status": w.margin_status.value,
            }
            for w in view.per_workflow
            if w.call_count > 0 or w.raw_cost_usd > 0
        ],
    }


def report_from_analytics_db(
    analytics_path: Path, group_by: GroupBy = "workflow"
) -> list[dict[str, Any]]:
    """Read pre-built ``dispatch_calls`` in rebuild-only analytics.duckdb."""
    from runtime.db_lock import connect_read

    if not analytics_path.is_file():
        raise FileNotFoundError(analytics_path)

    col = _GROUP_KEYS[group_by]
    con = connect_read(str(analytics_path))
    try:
        tables = {
            r[0]
            for r in con.execute(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_schema = 'main'"
            ).fetchall()
        }
        if "dispatch_calls" not in tables:
            return []
        rows = con.execute(
            f"""
            SELECT
              COALESCE(CAST({col} AS VARCHAR), '(unset)') AS key,
              COUNT(*) AS call_count,
              SUM(COALESCE(cost_usd, 0.0)) AS cost_usd,
              SUM(CASE WHEN is_remote_exec THEN COALESCE(cost_usd, 0.0) ELSE 0.0 END)
                AS remote_exec_cost_usd
            FROM dispatch_calls
            GROUP BY 1
            ORDER BY cost_usd DESC
            """
        ).fetchall()
        return [
            {
                "group_by": group_by,
                "key": r[0],
                "call_count": int(r[1]),
                "cost_usd": float(r[2]),
                "remote_exec_cost_usd": float(r[3]),
                "source": "analytics",
            }
            for r in rows
        ]
    finally:
        con.close()


def report_write_log_rollup(db_path: str | None = None) -> list[dict[str, Any]]:
    """OLTP ``write_log`` purpose rollup via ``connect_read`` (L5)."""
    from runtime.db_lock import connect_read
    from substrate.graph import default_db_path

    path = db_path or default_db_path()
    con = connect_read(path)
    try:
        exists = con.execute(
            "SELECT 1 FROM information_schema.tables "
            "WHERE table_schema = 'main' AND table_name = 'write_log'"
        ).fetchone()
        if not exists:
            return []
        rows = con.execute(
            """
            SELECT
              purpose,
              COUNT(*) AS write_count,
              SUM(COALESCE(duration_s, 0.0)) AS total_duration_s,
              SUM(CASE WHEN success THEN 1 ELSE 0 END) AS success_count
            FROM write_log
            GROUP BY purpose
            ORDER BY write_count DESC
            """
        ).fetchall()
        return [
            {
                "purpose": r[0],
                "write_count": int(r[1]),
                "total_duration_s": float(r[2]),
                "success_count": int(r[3]),
                "source": "oltp",
            }
            for r in rows
        ]
    finally:
        con.close()


def default_analytics_db_path() -> Path:
    explicit = os.environ.get("ANTIEK_ANALYTICS_DUCKDB_PATH")
    if explicit:
        return Path(explicit).expanduser()
    return Path(os.path.expanduser("~/.antiek/analytics.duckdb"))