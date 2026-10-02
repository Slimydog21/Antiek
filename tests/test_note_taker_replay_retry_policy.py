"""Deterministic recovery schedules, with no provider, database or real thread."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from interfaces.research.api import note_taking
from runtime import db_lock
from substrate.graph import knowledge_event_projector


def run_passes(monkeypatch, tmp_path, streams, catch_up, *, passes, tuning):
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
    monkeypatch.setattr(knowledge_event_projector, "discover_investigations", lambda path: streams)
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
