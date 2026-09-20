"""Note-taker replay must not thrash the DuckDB writer on idle catch_up.

Cite: #3164 lease yield; #3112 arxiv yield; roles/note_taker/replay.py.
"""

from __future__ import annotations

import json

from roles.note_taker import replay as replay_mod
from roles.note_taker.replay import DurableNoteTakerReplay
from runtime.db_lock import connect_read
from substrate.event_log import emit_typed
from substrate.graph.schema import init_database_at_path
from substrate.schemas.events import ClaimGroundingCheckPassedPayload


def _qualifying(events_dir, count: int, *, start: int = 0) -> None:
    for index in range(start, start + count):
        emit_typed(
            "inv-1",
            ClaimGroundingCheckPassedPayload(
                claim_id=f"claim-{index}",
                claim_text=f"Claim {index}",
                located_region_id=f"region-{index}",
                confidence=0.95,
            ),
            document_id="doc-1",
            events_dir=str(events_dir),
            role="grounder",
        )


def _response(request, idempotency_key=None):
    return json.dumps(
        {
            "notes": [
                {
                    "text": "A durable insight.",
                    "confidence": "high",
                    "source_event_ids": request["source_event_ids"],
                }
            ]
        }
    )


def test_idle_catch_up_skips_writer_when_windows_completed(tmp_path, monkeypatch):
    db = str(tmp_path / "graph.duckdb")
    events = tmp_path / "events"
    events.mkdir()
    init_database_at_path(db)
    _qualifying(events, 5)
    DurableNoteTakerReplay(_response, db_path=db, events_dir=str(events)).catch_up("inv-1")
    with connect_read(db) as con:
        assert con.execute("SELECT state FROM note_taker_windows").fetchone()[0] == "completed"

    purposes: list[str] = []
    original = replay_mod.connect_write

    def observed(db_path, *, purpose="", **kwargs):
        purposes.append(purpose)
        return original(db_path, purpose=purpose, **kwargs)

    monkeypatch.setattr(replay_mod, "connect_write", observed)
    # Also observe helper path
    original_helper = replay_mod._connect_write_replay

    def observed_helper(db_path, *, purpose):
        purposes.append(purpose)
        return original_helper(db_path, purpose=purpose)

    monkeypatch.setattr(replay_mod, "_connect_write_replay", observed_helper)

    DurableNoteTakerReplay(_response, db_path=db, events_dir=str(events)).catch_up("inv-1")
    assert purposes == [], purposes


def test_discover_window_yields_after_write(tmp_path, monkeypatch):
    db = str(tmp_path / "graph.duckdb")
    events = tmp_path / "events"
    events.mkdir()
    init_database_at_path(db)
    _qualifying(events, 10)  # 2 windows at threshold 5
    yields = {"n": 0}
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)

    def counting_yield():
        yields["n"] += 1

    # Force yield to count even under pytest by patching the function body path
    monkeypatch.setattr(replay_mod, "_yield_write_lock_for_peers", counting_yield)
    DurableNoteTakerReplay(_response, db_path=db, events_dir=str(events), threshold=5).catch_up(
        "inv-1"
    )
    # At least: discovery write yield + 2 discover inserts + 2 advance loops (+ materialize yields)
    assert yields["n"] >= 4, yields


def test_replay_write_helper_passes_timeout(monkeypatch):
    seen = {}

    def fake_connect(db_path, *, purpose="", timeout_s=300, **kwargs):
        seen["purpose"] = purpose
        seen["timeout_s"] = timeout_s

        class _CM:
            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def execute(self, *a, **k):
                raise AssertionError("should not execute")

        return _CM()

    monkeypatch.setattr(replay_mod, "connect_write", fake_connect)
    monkeypatch.setattr(replay_mod, "REPLAY_WRITE_TIMEOUT_S", 25.0)
    cm = replay_mod._connect_write_replay("/tmp/x.duckdb", purpose="note_taker/replay_advance")
    assert seen["timeout_s"] == 25.0
    assert seen["purpose"] == "note_taker/replay_advance"
    cm.__enter__()
    cm.__exit__(None, None, None)
