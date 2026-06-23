"""``antiek burn`` / burn_report (Engine + OLTP read paths)."""

from __future__ import annotations

import json
from pathlib import Path

from substrate.observability.burn_report import (
    report_cost_view_summary,
    report_dispatch_groups,
    report_from_analytics_db,
)
from substrate.schemas.events import ActionType


def test_report_dispatch_groups_by_provider(tmp_path: Path) -> None:
    iid = "inv-burn-1"
    event = {
        "event_id": "e1",
        "investigation_id": iid,
        "action_type": ActionType.DISPATCH_CALL.value,
        "role": "synthesizer",
        "payload": {
            "provider": "openrouter",
            "target_role": "synthesizer",
            "cost_usd": 0.02,
        },
    }
    (tmp_path / f"{iid}.jsonl").write_text(
        json.dumps(event) + "\n", encoding="utf-8"
    )
    groups = report_dispatch_groups(
        events_dir=str(tmp_path), group_by="provider"
    )
    assert len(groups) == 1
    assert groups[0]["key"] == "openrouter"
    assert groups[0]["call_count"] == 1


def test_report_cost_view_idle(tmp_path: Path) -> None:
    summary = report_cost_view_summary(events_dir=str(tmp_path))
    assert summary["aggregate"]["call_count"] == 0
    assert summary["aggregate"]["raw_cost_usd"] == 0.0


def test_report_from_analytics_db(tmp_path: Path) -> None:
    import duckdb

    from scripts.export_dispatch_events_parquet import export_dispatch_parquet

    events = tmp_path / "events"
    events.mkdir()
    iid = "inv-a"
    event = {
        "event_id": "e1",
        "investigation_id": iid,
        "action_type": ActionType.DISPATCH_CALL.value,
        "role": "reader",
        "payload": {
            "provider": "daytona",
            "target_role": "wrestler",
            "cost_usd": 0.5,
        },
    }
    (events / f"{iid}.jsonl").write_text(
        json.dumps(event) + "\n", encoding="utf-8"
    )
    pq = tmp_path / "dispatch_calls.parquet"
    export_dispatch_parquet(str(events), pq)

    adb = tmp_path / "analytics.duckdb"
    con = duckdb.connect(str(adb))
    con.execute(
        f"CREATE TABLE dispatch_calls AS SELECT * FROM read_parquet('{pq.as_posix()}')"
    )
    con.close()

    rows = report_from_analytics_db(adb, group_by="workflow")
    assert rows and rows[0]["call_count"] == 1
    assert rows[0]["cost_usd"] == 0.5