"""Lock discipline + wall-clock budget + resume cursor for the arXiv sync.

Regression fixtures for the 2026-09-05 production outage: the nightly
``--bulk`` pass held the single-writer DuckDB lock for its entire multi-hour
stream (never completing inside the 6h unit timeout), starving every API
write and freezing the single uvicorn worker for ~6h a day, four days running.

Invariants pinned here:
  * the write lock is taken per BATCH and released between batches;
  * a pass that exceeds its budget pauses between batches, checkpoints a
    resume cursor, and leaves the high-water mark untouched;
  * the next run resumes from the cursor (no re-stream, no duplicates) and,
    on completion, advances the high-water mark and clears the cursor;
  * a cursor is ignored when the snapshot or window changed;
  * the CLI treats a budget pause as exit 0 (planned), not a failure.
NO live network (same conventions as ``test_arxiv_oai_sync_bulk.py``).
"""

from __future__ import annotations

import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest

_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

import duckdb  # noqa: E402

from acquisition.arxiv.oai_pmh import OaiPmhHarvester  # noqa: E402
from acquisition.arxiv.throttle import ArxivThrottle  # noqa: E402
from runtime import db_lock  # noqa: E402
from tools import arxiv_oai_sync as sync_mod  # noqa: E402
from tools.arxiv_oai_sync import (  # noqa: E402
    SyncBudgetExhausted,
    SyncCheckpoint,
    read_checkpoint,
    run_bulk_sync,
    write_checkpoint,
)

_CC_BY = "http://creativecommons.org/licenses/by/4.0/"
_AT = datetime(2026, 9, 5, tzinfo=UTC)


@pytest.fixture(autouse=True)
def _tmp_env(tmp_path, monkeypatch):
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", str(tmp_path / "graph.duckdb"))
    monkeypatch.setenv("ANTIEK_ARXIV_OAI_STATE_PATH", str(tmp_path / "harvest.json"))
    monkeypatch.setenv("ANTIEK_ARXIV_OAI_SYNC_PATH", str(tmp_path / "sync.json"))
    monkeypatch.setenv("ANTIEK_ARXIV_BULK_SNAPSHOT", str(tmp_path / "bulk-snapshot.json"))


class _FakeClock:
    def __init__(self, start: float = 1000.0) -> None:
        self.t = start

    def now(self) -> float:
        return self.t

    def sleep(self, seconds: float) -> None:
        self.t += seconds


def _harvester(tmp_path, clock, handler) -> OaiPmhHarvester:
    throttle = ArxivThrottle(
        state_path=str(tmp_path / "throttle.json"), now=clock.now, sleep=clock.sleep
    )
    return OaiPmhHarvester(
        throttle=throttle,
        base_url="https://oai.test/oai2",
        state_path=str(tmp_path / "harvest.json"),
        transport=httpx.MockTransport(handler),
    )


def _no_oai(req: httpx.Request) -> httpx.Response:
    raise AssertionError(f"OAI must not be called: {req.url}")


def _record(i: int, day: int) -> dict:
    return {
        "id": f"2409.{i:05d}",
        "title": f"Paper {i}",
        "abstract": "x",
        "authors_parsed": [["Doe", "J", ""]],
        "categories": "cs.AI",
        "license": _CC_BY,
        "update_date": f"2024-09-{day:02d}",
        "versions": [{"version": "v1", "created": "Mon, 2 Sep 2024 00:00:00 GMT"}],
    }


def _write_snapshot(path: Path, records: list[dict]) -> str:
    path.write_text("\n".join(json.dumps(r) for r in records) + "\n", encoding="utf-8")
    return str(path)


def _row_count(tmp_path) -> int:
    con = duckdb.connect(str(tmp_path / "graph.duckdb"), read_only=True)
    try:
        return con.execute("SELECT COUNT(*) FROM documents").fetchone()[0]
    finally:
        con.close()


def _count_lock_acquisitions(monkeypatch) -> list[str]:
    seen: list[str] = []
    real = sync_mod.connect_write

    def counting(db_path, **kw):
        seen.append(kw.get("purpose", ""))
        return real(db_path, **kw)

    monkeypatch.setattr(sync_mod, "connect_write", counting)
    return seen


# ---------------------------------------------------------------------------
# Lock discipline
# ---------------------------------------------------------------------------


def test_bulk_pass_takes_the_write_lock_per_batch_not_per_pass(tmp_path, monkeypatch):
    acquisitions = _count_lock_acquisitions(monkeypatch)
    snap = _write_snapshot(tmp_path / "snap.json", [_record(i, 1 + i % 5) for i in range(10)])
    result = run_bulk_sync(
        harvester=_harvester(tmp_path, _FakeClock(), _no_oai),
        mode="backfill",
        sync_state_path=str(tmp_path / "sync.json"),
        bulk_snapshot_path=snap,
        harvested_at=_AT,
        oai_tail=False,
        batch_size=4,
    )
    assert result.persist.inserted == 10
    # 10 records / batch 4 -> 3 lock acquisitions, none spanning the stream.
    assert acquisitions == ["acquisition/arxiv_oai_sync"] * 3


def test_write_lock_is_free_between_batches(tmp_path):
    """Another writer can take the lock while the sync is between batches —
    the property whose absence took the API down."""
    db = str(tmp_path / "graph.duckdb")
    snap = _write_snapshot(tmp_path / "snap.json", [_record(i, 1) for i in range(6)])
    interleaved: list[bool] = []
    real_tap = sync_mod._persist_tap

    def tap(records, db_path, tally, **kw):
        def on_batch():
            with db_lock.connect_write(db, timeout_s=1.0, purpose="test/interleave"):
                interleaved.append(True)
            hook = kw.get("on_batch")
            if hook is not None:
                hook()

        kw["on_batch"] = on_batch
        return real_tap(records, db_path, tally, **kw)

    sync_mod._persist_tap = tap
    try:
        run_bulk_sync(
            harvester=_harvester(tmp_path, _FakeClock(), _no_oai),
            mode="backfill",
            sync_state_path=str(tmp_path / "sync.json"),
            bulk_snapshot_path=snap,
            harvested_at=_AT,
            oai_tail=False,
            batch_size=2,
        )
    finally:
        sync_mod._persist_tap = real_tap
    assert interleaved == [True, True, True]


# ---------------------------------------------------------------------------
# Budget pause + resume cursor
# ---------------------------------------------------------------------------


def test_budget_pause_checkpoints_cursor_and_keeps_high_water(tmp_path):
    sync_path = str(tmp_path / "sync.json")
    write_checkpoint(sync_path, SyncCheckpoint(last_successful_datestamp="2024-08-31"))
    snap = _write_snapshot(tmp_path / "snap.json", [_record(i, 1 + i) for i in range(6)])
    clock = _FakeClock()
    ticks = iter([0.0, 0.0, 10.0, 10.0, 10.0, 10.0])  # 2nd batch crosses the deadline

    def fake_clock() -> float:
        return next(ticks, 10.0)

    with pytest.raises(SyncBudgetExhausted) as info:
        run_bulk_sync(
            harvester=_harvester(tmp_path, clock, _no_oai),
            mode="incremental",
            sync_state_path=sync_path,
            bulk_snapshot_path=snap,
            harvested_at=_AT,
            oai_tail=False,
            batch_size=2,
            max_seconds=5.0,
            clock=fake_clock,
        )
    paused = info.value
    assert paused.bulk_complete is False
    assert paused.lines_consumed == 4  # two full batches flushed
    assert paused.persist.inserted == 4
    assert _row_count(tmp_path) == 4  # flushed rows are durable

    cp = read_checkpoint(sync_path)
    assert cp.last_successful_datestamp == "2024-08-31"  # untouched
    assert cp.bulk_cursor is not None
    assert cp.bulk_cursor["lines"] == 4
    assert cp.bulk_cursor["from_date"] == "2024-08-31"
    assert cp.bulk_cursor["bulk_max_datestamp"] == "2024-09-04"
    assert cp.bulk_cursor["bulk_complete"] is False
    assert cp.bulk_cursor["snapshot"]["size"] == Path(snap).stat().st_size


def test_resume_continues_from_cursor_then_completes_and_clears_it(tmp_path):
    sync_path = str(tmp_path / "sync.json")
    snap = _write_snapshot(tmp_path / "snap.json", [_record(i, 1 + i) for i in range(6)])
    clock = _FakeClock()
    ticks = iter([0.0, 10.0])
    with pytest.raises(SyncBudgetExhausted):
        run_bulk_sync(
            harvester=_harvester(tmp_path, clock, _no_oai),
            mode="backfill",
            sync_state_path=sync_path,
            bulk_snapshot_path=snap,
            harvested_at=_AT,
            oai_tail=False,
            batch_size=2,
            max_seconds=5.0,
            clock=lambda: next(ticks, 10.0),
        )
    assert read_checkpoint(sync_path).bulk_cursor["lines"] == 2

    result = run_bulk_sync(
        harvester=_harvester(tmp_path, clock, _no_oai),
        mode="backfill",
        sync_state_path=sync_path,
        bulk_snapshot_path=snap,
        harvested_at=_AT,
        oai_tail=False,
        batch_size=2,
    )
    # Only the remaining 4 records streamed; nothing re-inserted.
    assert result.persist.inserted == 4
    assert result.persist.updated == 0
    assert result.census.total == 4
    assert _row_count(tmp_path) == 6
    # Completion: high-water carries the max across BOTH runs; cursor spent.
    assert result.new_datestamp == "2024-09-06"
    assert result.advanced is True
    cp = read_checkpoint(sync_path)
    assert cp.last_successful_datestamp == "2024-09-06"
    assert cp.bulk_cursor is None


def test_resume_after_bulk_completed_skips_snapshot_and_seeds_oai_tail(tmp_path):
    """The snapshot finished but the OAI tail was cut: the next run must not
    re-stream the snapshot, and the tail lower bound must come from the
    checkpointed bulk max, not from the corpus start."""
    sync_path = str(tmp_path / "sync.json")
    snap = _write_snapshot(tmp_path / "snap.json", [_record(i, 1 + i) for i in range(3)])
    write_checkpoint(
        sync_path,
        SyncCheckpoint(
            bulk_cursor={
                "snapshot": sync_mod._snapshot_identity(snap),
                "from_date": None,
                "until_date": None,
                "lines": 3,
                "bulk_max_datestamp": "2024-09-03",
                "bulk_complete": True,
            }
        ),
    )
    seen_from: list[str | None] = []

    def oai(req: httpx.Request) -> httpx.Response:
        seen_from.append(req.url.params.get("from"))
        body = (
            '<?xml version="1.0"?><OAI-PMH xmlns="http://www.openarchives.org/OAI/2.0/">'
            "<ListRecords></ListRecords></OAI-PMH>"
        )
        return httpx.Response(200, text=body)

    result = run_bulk_sync(
        harvester=_harvester(tmp_path, _FakeClock(), oai),
        mode="backfill",
        sync_state_path=sync_path,
        bulk_snapshot_path=snap,
        harvested_at=_AT,
        oai_tail=True,
        batch_size=2,
    )
    assert result.persist.inserted == 0  # snapshot not re-streamed
    assert seen_from == ["2024-09-03"]
    assert read_checkpoint(sync_path).bulk_cursor is None


def test_cursor_ignored_when_snapshot_or_window_changed(tmp_path):
    sync_path = str(tmp_path / "sync.json")
    snap = _write_snapshot(tmp_path / "snap.json", [_record(i, 1) for i in range(4)])
    stale = dict(sync_mod._snapshot_identity(snap))
    stale["size"] += 1  # a different (re-downloaded) snapshot
    write_checkpoint(
        sync_path,
        SyncCheckpoint(
            bulk_cursor={
                "snapshot": stale,
                "from_date": None,
                "until_date": None,
                "lines": 3,
                "bulk_max_datestamp": "2024-09-01",
                "bulk_complete": False,
            }
        ),
    )
    result = run_bulk_sync(
        harvester=_harvester(tmp_path, _FakeClock(), _no_oai),
        mode="backfill",
        sync_state_path=sync_path,
        bulk_snapshot_path=snap,
        harvested_at=_AT,
        oai_tail=False,
        batch_size=10,
    )
    assert result.persist.inserted == 4  # streamed from line 0


def test_no_bulk_resume_flag_streams_from_start(tmp_path):
    sync_path = str(tmp_path / "sync.json")
    snap = _write_snapshot(tmp_path / "snap.json", [_record(i, 1) for i in range(4)])
    write_checkpoint(
        sync_path,
        SyncCheckpoint(
            bulk_cursor={
                "snapshot": sync_mod._snapshot_identity(snap),
                "from_date": None,
                "until_date": None,
                "lines": 3,
                "bulk_max_datestamp": "2024-09-01",
                "bulk_complete": False,
            }
        ),
    )
    result = run_bulk_sync(
        harvester=_harvester(tmp_path, _FakeClock(), _no_oai),
        mode="backfill",
        sync_state_path=sync_path,
        bulk_snapshot_path=snap,
        harvested_at=_AT,
        oai_tail=False,
        bulk_resume=False,
    )
    assert result.persist.inserted == 4


def test_checkpoint_round_trips_cursor_and_tolerates_absence(tmp_path):
    path = str(tmp_path / "cp.json")
    write_checkpoint(path, SyncCheckpoint(last_successful_datestamp="2024-01-01"))
    assert "bulk_cursor" not in json.loads(Path(path).read_text())
    assert read_checkpoint(path).bulk_cursor is None
    write_checkpoint(
        path, SyncCheckpoint(last_successful_datestamp="2024-01-01", bulk_cursor={"lines": 7})
    )
    assert read_checkpoint(path).bulk_cursor == {"lines": 7}
    Path(path).write_text(json.dumps({"bulk_cursor": "garbage"}))
    assert read_checkpoint(path).bulk_cursor is None


# ---------------------------------------------------------------------------
# CLI contract
# ---------------------------------------------------------------------------


def test_cli_treats_budget_pause_as_planned_exit_zero(tmp_path, capsys, monkeypatch):
    snap = _write_snapshot(tmp_path / "snap.json", [_record(i, 1 + i) for i in range(6)])
    monkeypatch.setattr(sync_mod, "ensure_bulk_snapshot", lambda **kw: kw["snapshot_path"])
    monkeypatch.setattr(sync_mod, "default_sync_state_path", lambda: str(tmp_path / "sync.json"))
    monkeypatch.setattr(sync_mod.time, "monotonic", lambda: 0.0)
    ticks = iter([0.0, 10.0])
    monkeypatch.setattr(
        sync_mod, "run_bulk_sync",
        lambda **kw: sync_mod.__dict__["_orig_run_bulk_sync"](**{**kw, "clock": lambda: next(ticks, 10.0)}),
    ) if False else None
    # Drive the real function with a deterministic clock via --max-seconds 0.
    rc = sync_mod.main([
        "backfill", "--bulk", "--bulk-snapshot", snap, "--bulk-only",
        "--batch-size", "2", "--max-seconds", "0",
    ])
    out = capsys.readouterr().out
    assert rc == 0
    assert "paused:" in out
    assert "high-water mark unchanged" in out
    cp = read_checkpoint(str(tmp_path / "sync.json"))
    assert cp.last_successful_datestamp is None
    assert cp.bulk_cursor is not None and cp.bulk_cursor["lines"] == 2


def test_cli_exposes_budget_and_batch_flags():
    parser = sync_mod.build_parser()
    args = parser.parse_args([
        "incremental", "--bulk", "--max-seconds", "5400", "--batch-size", "2000",
        "--no-bulk-resume", "--lock-timeout", "30",
    ])
    assert args.max_seconds == 5400.0
    assert args.batch_size == 2000
    assert args.no_bulk_resume is True
    assert args.lock_timeout == 30.0
