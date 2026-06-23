"""Engine plane: dispatch.call → Parquet projection."""

from __future__ import annotations

import json
from pathlib import Path

from substrate.analytics.dispatch_rows import iter_dispatch_call_rows
from substrate.schemas.events import ActionType


def test_iter_dispatch_empty_dir(tmp_path: Path) -> None:
    assert list(iter_dispatch_call_rows(events_dir=str(tmp_path))) == []


def test_export_dispatch_parquet_empty(tmp_path: Path) -> None:
    from scripts.export_dispatch_events_parquet import export_dispatch_parquet

    events = tmp_path / "events"
    events.mkdir()
    out = tmp_path / "dispatch_calls.parquet"
    manifest = export_dispatch_parquet(str(events), out)
    assert manifest["row_count"] == 0
    assert out.is_file()


def test_iter_dispatch_reads_jsonl(tmp_path: Path) -> None:
    iid = "inv-test-1"
    event = {
        "event_id": "evt-1",
        "investigation_id": iid,
        "action_type": ActionType.DISPATCH_CALL.value,
        "role": "synthesizer",
        "emitted_at": "2026-01-01T00:00:00Z",
        "payload": {
            "provider": "openrouter",
            "model": "test",
            "tier": "pro",
            "target_role": "synthesizer",
            "input_tokens": 10,
            "output_tokens": 5,
            "cost_usd": 0.01,
            "latency_ms": 100,
            "prompt_hash": "abc",
        },
    }
    (tmp_path / f"{iid}.jsonl").write_text(json.dumps(event) + "\n", encoding="utf-8")
    rows = list(iter_dispatch_call_rows(events_dir=str(tmp_path)))
    assert len(rows) == 1
    assert rows[0]["workflow"] == "research"
    assert rows[0]["cost_usd"] == 0.01