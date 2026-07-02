"""nygard SPR-04 — circuit-breaker state machine (deterministic, injected clock)."""

from __future__ import annotations

import pytest

from substrate.dispatch.breaker import BreakerState, CircuitBreaker


class _Clock:
    """A controllable monotonic clock for deterministic cooldown tests."""

    def __init__(self) -> None:
        self.t = 1000.0

    def __call__(self) -> float:
        return self.t

    def advance(self, dt: float) -> None:
        self.t += dt


def _breaker(threshold=3, cooldown=30.0):
    return CircuitBreaker(failure_threshold=threshold, cooldown_s=cooldown, clock=_Clock())


def test_starts_closed():
    b = _breaker()
    assert b.state("p") is BreakerState.CLOSED
    assert b.is_open("p") is False


def test_opens_after_threshold_failures():
    b = _breaker(threshold=3)
    b.record_failure("p")
    b.record_failure("p")
    assert b.is_open("p") is False  # 2 < 3
    b.record_failure("p")
    assert b.state("p") is BreakerState.OPEN
    assert b.is_open("p") is True  # now skipped


def test_success_closes_and_resets_count():
    b = _breaker(threshold=3)
    b.record_failure("p")
    b.record_failure("p")
    b.record_success("p")
    assert b.failure_count("p") == 0
    # Prior failures don't carry over toward the next open.
    b.record_failure("p")
    b.record_failure("p")
    assert b.is_open("p") is False


def test_open_within_cooldown_stays_open():
    clock = _Clock()
    b = CircuitBreaker(failure_threshold=1, cooldown_s=30.0, clock=clock)
    b.record_failure("p")
    assert b.is_open("p") is True
    clock.advance(29.0)
    assert b.is_open("p") is True  # cooldown not elapsed


def test_half_open_after_cooldown_allows_one_probe():
    clock = _Clock()
    b = CircuitBreaker(failure_threshold=1, cooldown_s=30.0, clock=clock)
    b.record_failure("p")
    clock.advance(30.0)
    assert b.is_open("p") is False  # cooldown elapsed -> probe allowed
    assert b.state("p") is BreakerState.HALF_OPEN


def test_half_open_success_closes():
    clock = _Clock()
    b = CircuitBreaker(failure_threshold=1, cooldown_s=30.0, clock=clock)
    b.record_failure("p")
    clock.advance(30.0)
    assert b.is_open("p") is False  # -> half open
    b.record_success("p")
    assert b.state("p") is BreakerState.CLOSED


def test_half_open_failure_reopens_and_restarts_cooldown():
    clock = _Clock()
    b = CircuitBreaker(failure_threshold=1, cooldown_s=30.0, clock=clock)
    b.record_failure("p")
    clock.advance(30.0)
    assert b.is_open("p") is False  # half open
    b.record_failure("p")  # probe failed
    assert b.state("p") is BreakerState.OPEN
    assert b.is_open("p") is True
    clock.advance(29.0)
    assert b.is_open("p") is True  # cooldown restarted at reopen
    clock.advance(1.0)
    assert b.is_open("p") is False


def test_per_provider_isolation():
    b = _breaker(threshold=1)
    b.record_failure("a")
    assert b.is_open("a") is True
    assert b.is_open("b") is False  # b unaffected


def test_snapshot_and_reset():
    b = _breaker(threshold=2)
    b.record_failure("p")
    snap = b.snapshot("p")
    assert snap["provider"] == "p"
    assert snap["failures"] == 1
    assert snap["threshold"] == 2
    b.reset()
    assert b.failure_count("p") == 0
    assert b.state("p") is BreakerState.CLOSED


def test_rejects_bad_config():
    with pytest.raises(ValueError):
        CircuitBreaker(failure_threshold=0)
    with pytest.raises(ValueError):
        CircuitBreaker(cooldown_s=-1)
