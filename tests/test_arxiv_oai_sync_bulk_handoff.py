"""The bulk phase of ``run_bulk_sync`` must honour the writer handoff.

Prod 2026-10-02 (live incident, api.antiek.ai build c7bc1a8e45): while
``tools.arxiv_oai_sync incremental --bulk --persist-batch-size 200`` ran,
``POST /api/ad/frame-telemetry`` answered 503 ``ad_frame_writer_busy``
~27k times in 24h (~85% of frame-telemetry writes). The bulk phase released
the flock between slices but then re-acquired on a BLIND
``time.sleep(yield_s)`` timer: it held the DuckDB write lock for up to
``max_lock_s`` (15s default) of every 15.5s cycle, while the frame-telemetry
route's ``connect_write(timeout_s=5.0)`` cannot survive a single 15s hold.
The runtime's writer-handoff (``write_handoff_requested`` waiter tokens,
runtime/db_lock.py) existed and was already honoured by the OAI-tail path's
``_yield_between_lock_sessions`` — the bulk phase never consulted it.

Contract pinned here: while a live waiter token is published, the bulk
phase does NOT start its next slice's acquisition.
"""

from __future__ import annotations

import json
import os
import sys
import threading
import time
from datetime import UTC, datetime
from pathlib import Path

import pytest

_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

from runtime import db_lock  # noqa: E402
from tools import arxiv_bulk_resume  # noqa: E402
from tools import arxiv_oai_sync as sync  # noqa: E402
from tools.arxiv_oai_sync import run_bulk_sync  # noqa: E402

_CC_BY = "http://creativecommons.org/licenses/by/4.0/"
_AT = datetime(2026, 5, 29, tzinfo=UTC)


@pytest.fixture(autouse=True)
def _tmp_documents_db(tmp_path, monkeypatch):
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", str(tmp_path / "graph.duckdb"))
    monkeypatch.setenv("ANTIEK_ARXIV_OAI_STATE_PATH", str(tmp_path / "harvest.json"))
    monkeypatch.setenv("ANTIEK_ARXIV_OAI_SYNC_PATH", str(tmp_path / "sync.json"))


def _bulk_record(arxiv_id: str, *, update_date: str) -> dict:
    return {
        "id": arxiv_id,
        "title": f"T {arxiv_id}",
        "abstract": f"Abstract for {arxiv_id}.",
        "categories": "cs.LG",
        "license": _CC_BY,
        "authors_parsed": [["Author", "A", ""]],
        "versions": [
            {"version": "v1", "created": "Mon, 1 Jan 2024 10:00:00 GMT"},
        ],
        "update_date": update_date,
    }


def _write_snapshot(path: Path, records: list[dict]) -> str:
    path.write_text(
        "\n".join(json.dumps(r) for r in records) + "\n", encoding="utf-8"
    )
    return str(path)


def _run_bulk(tmp_path, monkeypatch):
    """Drive the bulk phase with 3 one-record slices; collect slice acquires."""
    db = str(tmp_path / "graph.duckdb")
    snap = _write_snapshot(
        tmp_path / "snap.json",
        [_bulk_record(f"2401.000{i}", update_date=f"2024-01-0{i}") for i in (1, 2, 3)],
    )
    # oai_tail=False: no network, and the tail's chunked tap (which already
    # honours the handoff) is not the surface under test.
    import httpx

    from acquisition.arxiv.oai_pmh import OaiPmhHarvester
    from acquisition.arxiv.throttle import ArxivThrottle

    def boom(req):  # pragma: no cover - tail disabled
        raise AssertionError(f"OAI must not be called: {req.url}")

    harvester = OaiPmhHarvester(
        throttle=ArxivThrottle(state_path=str(tmp_path / "throttle.json")),
        client=httpx.Client(transport=httpx.MockTransport(boom), timeout=5.0),
        base_url="https://oai.test/oai2",
        state_path=str(tmp_path / "harvest.json"),
    )

    acquires: list[float] = []
    real_connect = arxiv_bulk_resume.connect_write

    def counting_connect(path, **kwargs):
        if kwargs.get("purpose") == "arxiv_bulk_slice":
            acquires.append(time.monotonic())
        return real_connect(path, **kwargs)

    monkeypatch.setattr(arxiv_bulk_resume, "connect_write", counting_connect)

    result = run_bulk_sync(
        harvester=harvester,
        mode="backfill",
        sync_state_path=str(tmp_path / "sync.json"),
        bulk_snapshot_path=snap,
        harvested_at=_AT,
        db_path=db,
        oai_tail=False,
        persist_batch_size=1,
        lock_yield_seconds=0.0,
    )
    assert result.persist.inserted == 3
    assert len(acquires) >= 2, f"expected multiple bulk slices, got {acquires}"
    return db, acquires


def test_bulk_phase_steps_aside_for_a_live_waiter(tmp_path, monkeypatch):
    """A queued writer published during the sync's yield must be served
    BEFORE the sync's next slice acquisition — not lose the re-acquisition
    race to a blind timer."""
    # raising=False: on the pre-fix module the bulk phase never consults the
    # waiter protocol, and the test must then fail on BEHAVIOUR (the waiter
    # is never published because nothing probes), not on a missing attribute.
    monkeypatch.setattr(sync, "HANDOFF_WAIT_MAX_S", 2.0, raising=False)
    monkeypatch.setattr(sync, "HANDOFF_POLL_S", 0.01, raising=False)

    db = str(tmp_path / "graph.duckdb")
    asked: list[str] = []
    withdrew_at: list[float] = []
    served: list[tuple[int, str]] = []
    real_requested = sync.write_handoff_requested

    def withdraw() -> None:
        db_lock._unregister_write_waiter(served.pop())
        withdrew_at.append(time.monotonic())

    def probing_requested(path):
        asked.append(path)
        if len(asked) == 1:
            # This thread plays the queued API writer: it publishes a waiter
            # token when the sync first consults the protocol and is served
            # 100ms later.
            served.append(db_lock._register_write_waiter(db))
            threading.Timer(0.1, withdraw).start()
        return real_requested(path)

    monkeypatch.setattr(sync, "write_handoff_requested", probing_requested)

    try:
        db, acquires = _run_bulk(tmp_path, monkeypatch)
    finally:
        for token in served:
            db_lock._unregister_write_waiter(token)

    assert asked, "the bulk phase never consulted the waiter protocol"
    assert withdrew_at, "the queued writer was never served"
    assert acquires[1] >= withdrew_at[0] - 0.02, (
        "the sync started its next slice while a live writer was queued "
        f"(next slice at {acquires[1]}, waiter withdrew at {withdrew_at[0]})"
    )
    assert acquires[1] - acquires[0] >= 0.08, (
        "the sync did not actually wait out the queued writer "
        f"(gap {acquires[1] - acquires[0]:.3f}s)"
    )


def test_bulk_phase_never_waits_when_no_writer_is_queued(tmp_path, monkeypatch):
    """The handoff is conditional: with nobody queued, the bulk phase must
    not add latency to its own run — but it must still ask the protocol."""
    monkeypatch.setattr(sync, "HANDOFF_WAIT_MAX_S", 2.0, raising=False)
    monkeypatch.setattr(sync, "HANDOFF_POLL_S", 0.01, raising=False)

    asked: list[str] = []
    real_requested = sync.write_handoff_requested

    def counting_requested(path):
        asked.append(path)
        return real_requested(path)

    monkeypatch.setattr(sync, "write_handoff_requested", counting_requested)

    t0 = time.monotonic()
    _run_bulk(tmp_path, monkeypatch)
    elapsed = time.monotonic() - t0

    assert asked, "the bulk phase never consulted the waiter protocol"
    assert elapsed < 5.0, f"uncontended bulk run added {elapsed:.2f}s of handoff wait"
