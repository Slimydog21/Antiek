"""
Tests for acquisition.arxiv.throttle — the cross-process rate limiter.

Closes the throttle half of
``tests/regression/agent_failures/arxiv-429-export-ban.yaml`` (the
in-process-only throttle was the documented root cause).

The load-bearing property is *cross-process* spacing. We can't easily
fork real processes in a unit test, but the correctness hinges on the
flock-serialized read-modify-write of a shared state file — so we test:

1. Single-caller spacing with injected clock/sleep (deterministic).
2. The shared state file is what carries the last-request time (a
   "second process" is simulated by a second ``acquire()`` call that
   reads the same on-disk state — which is exactly what a separate
   process would do).
3. Real cross-thread spacing under contention (threads share the
   process but contend on the same flock + state file, exercising the
   serialization path with the real clock).

Spec: ~/specs/antiek-hashimoto-engineering/sprint-e2-harness.html (E2 GAP closure)
"""

from __future__ import annotations

import threading
import time
from pathlib import Path

import pytest

from acquisition.arxiv import throttle


@pytest.fixture(autouse=True)
def _isolate_throttle(tmp_path: Path, monkeypatch):
    """Point throttle state at a tmp dir + a short interval so tests
    are fast and don't touch the operator's real ~/.antiek state."""
    monkeypatch.setenv("ANTIEK_ARXIV_THROTTLE_DIR", str(tmp_path))
    monkeypatch.delenv("ANTIEK_ARXIV_MIN_INTERVAL_S", raising=False)
    yield


# ---------------------------------------------------------------------------
# Deterministic spacing with injected clock + sleep
# ---------------------------------------------------------------------------


def test_first_request_does_not_wait() -> None:
    res = throttle.acquire(min_interval_s=3.0, now_fn=lambda: 1000.0, sleep_fn=lambda s: None)
    assert res.waited_s == 0.0
    assert res.last_request_at == 1000.0


def test_second_request_waits_the_remaining_interval() -> None:
    slept: list[float] = []

    # First call stamps t=1000.
    throttle.acquire(min_interval_s=3.0, now_fn=lambda: 1000.0, sleep_fn=lambda s: None)

    # Second call at t=1001 (only 1s elapsed) must wait 2s.
    clock = {"t": 1001.0}

    def now():
        return clock["t"]

    def sleep(s):
        slept.append(s)
        clock["t"] += s  # advance the clock as if we really slept

    res = throttle.acquire(min_interval_s=3.0, now_fn=now, sleep_fn=sleep)
    assert slept == [pytest.approx(2.0)]
    assert res.waited_s == pytest.approx(2.0)
    # Stamp written is the post-sleep time.
    assert res.last_request_at == pytest.approx(1003.0)


def test_request_after_interval_does_not_wait() -> None:
    throttle.acquire(min_interval_s=3.0, now_fn=lambda: 1000.0, sleep_fn=lambda s: None)
    # 5s later — well past the interval — no wait.
    res = throttle.acquire(min_interval_s=3.0, now_fn=lambda: 1005.0, sleep_fn=lambda s: None)
    assert res.waited_s == 0.0


def test_zero_interval_never_waits() -> None:
    throttle.acquire(min_interval_s=0.0, now_fn=lambda: 1000.0, sleep_fn=lambda s: None)
    res = throttle.acquire(min_interval_s=0.0, now_fn=lambda: 1000.0, sleep_fn=lambda s: None)
    assert res.waited_s == 0.0


# ---------------------------------------------------------------------------
# State file is the cross-process carrier
# ---------------------------------------------------------------------------


def test_state_file_persists_last_request(tmp_path: Path) -> None:
    throttle.acquire(min_interval_s=3.0, now_fn=lambda: 4242.0, sleep_fn=lambda s: None)
    state = tmp_path / "arxiv_throttle.state"
    assert state.exists()
    assert float(state.read_text(encoding="utf-8").strip()) == pytest.approx(4242.0)


def test_second_acquire_reads_prior_state_from_disk(tmp_path: Path) -> None:
    """A 'second process' is simulated by a fresh acquire() that reads
    the same on-disk state — which is precisely what a separate process
    does. It must honor the first's timestamp, not start fresh."""
    # "Process A" stamps t=2000.
    throttle.acquire(min_interval_s=3.0, now_fn=lambda: 2000.0, sleep_fn=lambda s: None)

    # "Process B" arrives at t=2001 — must wait 2s because it reads A's
    # timestamp from the shared state file (the in-process-only bug was
    # that B started fresh and didn't wait).
    slept: list[float] = []
    clock = {"t": 2001.0}
    res = throttle.acquire(
        min_interval_s=3.0,
        now_fn=lambda: clock["t"],
        sleep_fn=lambda s: (slept.append(s), clock.__setitem__("t", clock["t"] + s)),
    )
    assert slept == [pytest.approx(2.0)], "second 'process' did not honor the shared timestamp"


def test_corrupt_state_treated_as_no_prior_request(tmp_path: Path) -> None:
    state = tmp_path / "arxiv_throttle.state"
    state.parent.mkdir(parents=True, exist_ok=True)
    state.write_text("not a float", encoding="utf-8")
    # Corrupt state must not wedge — treated as 0.0 (no prior request).
    res = throttle.acquire(min_interval_s=3.0, now_fn=lambda: 5000.0, sleep_fn=lambda s: None)
    assert res.waited_s == 0.0


def test_reset_clears_state(tmp_path: Path) -> None:
    throttle.acquire(min_interval_s=3.0, now_fn=lambda: 1000.0, sleep_fn=lambda s: None)
    assert (tmp_path / "arxiv_throttle.state").exists()
    throttle.reset()
    assert not (tmp_path / "arxiv_throttle.state").exists()


# ---------------------------------------------------------------------------
# Env-var overrides
# ---------------------------------------------------------------------------


def test_min_interval_env_override(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("ANTIEK_ARXIV_MIN_INTERVAL_S", "10.0")
    throttle.acquire(now_fn=lambda: 1000.0, sleep_fn=lambda s: None)
    slept: list[float] = []
    throttle.acquire(
        now_fn=lambda: 1002.0,  # 2s elapsed, interval is 10
        sleep_fn=lambda s: slept.append(s),
    )
    assert slept == [pytest.approx(8.0)]


def test_invalid_env_interval_falls_back_to_default(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("ANTIEK_ARXIV_MIN_INTERVAL_S", "not-a-number")
    # Should not raise; falls back to DEFAULT_MIN_INTERVAL_S.
    res = throttle.acquire(now_fn=lambda: 1000.0, sleep_fn=lambda s: None)
    assert res.waited_s == 0.0


# ---------------------------------------------------------------------------
# Real cross-thread contention (real clock, real flock)
# ---------------------------------------------------------------------------


def test_concurrent_threads_are_serialized_and_spaced(tmp_path: Path, monkeypatch) -> None:
    """Four threads contend on the same flock + state file with a small
    real interval. The flock must serialize them; the recorded stamps
    must be spaced by at least the interval. This exercises the real
    read-modify-write-under-lock path that an in-process lock alone
    couldn't provide cross-process.
    """
    interval = 0.1
    stamps: list[float] = []
    lock = threading.Lock()
    barrier = threading.Barrier(4)

    def worker():
        barrier.wait()
        res = throttle.acquire(min_interval_s=interval)
        with lock:
            stamps.append(res.last_request_at)

    threads = [threading.Thread(target=worker) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    stamps.sort()
    assert len(stamps) == 4
    # Consecutive stamps must be at least `interval` apart (minus a
    # small scheduling tolerance) — proof the throttle spaced them.
    for earlier, later in zip(stamps, stamps[1:]):
        gap = later - earlier
        assert gap >= interval - 0.02, f"requests spaced only {gap:.3f}s, expected ≥ {interval}s"
