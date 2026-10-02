"""Source controls for inline recovery with a stub replay service.

The harness replaces the recovery thread and replay service. Real module
imports and conftest effects, including database effects, need separate
runtime admission. These source declarations are not execution evidence.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from interfaces.research.api import note_taking
from runtime import db_lock
from substrate.graph import knowledge_event_projector


def run_passes(
    monkeypatch, tmp_path, streams, catch_up, *, passes, tuning,
    discover=None, observe_pass=None,
):
    clock = {"now": 0.0, "passes": 0}
    db = tmp_path / "catalog-presence-only"
    db.touch()
    calls = []

    def attempt(stream):
        calls.append((stream, clock["now"]))
        catch_up(stream)

    class Stop:
        def is_set(self):
            return clock["passes"] >= passes

        def wait(self, delay):
            if observe_pass is not None:
                observe_pass(dict(state))
            clock["now"] += delay
            clock["passes"] += 1

    class InlineThread:
        def __init__(self, *, target, **kwargs):
            self.target = target

        def start(self):
            self.target()

    monkeypatch.setattr(note_taking.threading, "Thread", InlineThread)
    monkeypatch.setattr(note_taking.time, "monotonic", lambda: clock["now"])
    monkeypatch.setattr(note_taking, "_resolve_replay_tuning", lambda: tuning)
    monkeypatch.setattr(
        note_taking,
        "_default_replay_service",
        lambda **kwargs: SimpleNamespace(db_path=str(db), events_dir="unused", catch_up=attempt),
    )
    monkeypatch.setattr(db_lock, "write_handoff_requested", lambda path: False)
    def discovered_streams(path):
        return streams if discover is None else discover(clock["passes"])

    monkeypatch.setattr(knowledge_event_projector, "discover_investigations", discovered_streams)
    monkeypatch.setenv("ANTIEK_NOTE_TAKER_REPLAY_LOCK_YIELD_S", "0")
    state = {}
    note_taking.start_replay_recovery(stop_event=Stop(), poll_interval_s=1.0, state=state)
    return calls, state


def test_empty_discovery_survives_more_than_1025_passes(monkeypatch, tmp_path):
    calls, state = run_passes(
        monkeypatch, tmp_path, [], lambda stream: None, passes=1100, tuning=(2.0, 30.0, 30.0)
    )
    assert calls == []
    assert state["status"] == "idle"
    assert state["consecutive_barren_passes"] == 0
    assert state["backoff_s"] == 0.0


def test_failed_stream_survives_more_than_1025_attempts(monkeypatch, tmp_path):
    def fail(stream):
        raise RuntimeError("controlled unavailable stream")

    calls, state = run_passes(
        monkeypatch, tmp_path, ["failing"], fail, passes=1100, tuning=(0.001, 0.002, 30.0)
    )
    assert len(calls) == 1100
    assert state["status"] == "backoff"
    assert state["pending_retries"] == 1
    assert 0.0 <= state["backoff_s"] <= 0.002


def test_healthy_stream_does_not_reset_failed_peer_retry(monkeypatch, tmp_path):
    def catch_up(stream):
        if stream == "failing":
            raise RuntimeError("controlled unavailable stream")

    calls, state = run_passes(
        monkeypatch,
        tmp_path,
        ["failing", "healthy"],
        catch_up,
        passes=30,
        tuning=(2.0, 8.0, 30.0),
    )
    healthy = [at for stream, at in calls if stream == "healthy"]
    failed = [at for stream, at in calls if stream == "failing"]
    assert len(healthy) == 30
    assert 1 < len(failed) <= 6
    assert all(later - earlier >= 2.0 for earlier, later in zip(failed, failed[1:]))
    assert state["status"] == "catching_up"
    assert state["pending_retries"] == 1


@pytest.mark.parametrize("value", ["nan", "inf", "-inf"])
def test_nonfinite_retry_tuning_uses_finite_defaults(monkeypatch, value):
    for key in (
        "ANTIEK_NOTE_TAKER_REPLAY_BACKOFF_BASE_S",
        "ANTIEK_NOTE_TAKER_REPLAY_BACKOFF_MAX_S",
        "ANTIEK_NOTE_TAKER_REPLAY_LOG_INTERVAL_S",
    ):
        monkeypatch.setenv(key, value)
    assert note_taking._resolve_replay_tuning() == (2.0, 30.0, 30.0)


def test_failed_stream_uses_exact_capped_retry_schedule(monkeypatch, tmp_path):
    def fail(stream):
        raise RuntimeError("controlled unavailable stream")

    calls, state = run_passes(
        monkeypatch, tmp_path, ["A"], fail,
        passes=31, tuning=(2.0, 8.0, 30.0),
    )
    assert calls == [("A", at) for at in (0.0, 2.0, 6.0, 14.0, 22.0, 30.0)]
    assert state["status"] == "backoff"
    assert state["pending_retries"] == 1
    assert state["backoff_s"] == 8.0


def test_success_resets_only_its_own_stream_retry(monkeypatch, tmp_path):
    current_pass = {"index": 0}

    def discover(index):
        current_pass["index"] = index
        return ["A", "B"]

    def catch_up(stream):
        if stream == "B" or current_pass["index"] in (0, 4):
            raise RuntimeError("controlled unavailable stream")

    calls, state = run_passes(
        monkeypatch, tmp_path, [], catch_up,
        passes=7, tuning=(2.0, 8.0, 30.0), discover=discover,
    )
    assert [at for stream, at in calls if stream == "A"] == [0.0, 2.0, 3.0, 4.0, 6.0]
    assert [at for stream, at in calls if stream == "B"] == [0.0, 2.0, 6.0]
    assert state["status"] == "catching_up"
    assert state["pending_retries"] == 1


def test_removal_prunes_retry_and_reappearance_is_fresh(monkeypatch, tmp_path):
    reports = []

    def fail(stream):
        raise RuntimeError("controlled unavailable stream")

    calls, state = run_passes(
        monkeypatch, tmp_path, [], fail,
        passes=3, tuning=(8.0, 8.0, 30.0),
        discover=lambda index: [] if index == 1 else ["A"],
        observe_pass=reports.append,
    )
    assert calls == [("A", 0.0), ("A", 2.0)]
    assert [report["pending_retries"] for report in reports] == [1, 0, 1]
    assert [report["status"] for report in reports] == ["backoff", "idle", "backoff"]
    assert reports[1]["failures"] == 0
    assert reports[1]["backoff_s"] == 0.0
    assert state["backoff_s"] == 8.0


def test_report_distinguishes_failure_deferred_and_current(monkeypatch, tmp_path):
    reports = []
    attempts = {"count": 0}

    def catch_up(stream):
        attempts["count"] += 1
        if attempts["count"] == 1:
            raise RuntimeError("controlled first failure")

    calls, state = run_passes(
        monkeypatch, tmp_path, ["A"], catch_up,
        passes=4, tuning=(2.0, 8.0, 30.0), observe_pass=reports.append,
    )
    assert calls == [("A", 0.0), ("A", 2.0), ("A", 3.0)]
    assert [report["status"] for report in reports] == [
        "backoff", "backoff", "current", "current",
    ]
    assert [report["pending_retries"] for report in reports] == [1, 1, 0, 0]
    assert [report["failures"] for report in reports] == [1, 0, 0, 0]
    assert state["status"] == "current"
