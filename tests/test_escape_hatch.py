"""Tests for substrate.escape_hatch — the audited bypass marker.

Coverage:
- Context-manager form increments counter + warns on first hit
- Decorator form increments per invocation, not per decoration
- Per-reason single-warning property (10 calls = 1 warning)
- Different reasons each get their own warning
- Empty / whitespace reason raises at construction
- Exceptions inside the hatch propagate (do not get swallowed)
- counter_snapshot returns a defensive copy
- reset_counters_for_tests clears both counters and seen-set
- Thread-safety smoke test — concurrent hatch entries do not drop counts
"""

from __future__ import annotations

import logging
import threading

import pytest

from substrate.escape_hatch import (
    EscapeHatchInvalidReason,
    counter_snapshot,
    escape_hatch,
    reset_counters_for_tests,
)


@pytest.fixture(autouse=True)
def _clean_state() -> None:
    """Reset module-level state between tests so counter assertions
    don't depend on test order."""
    reset_counters_for_tests()


# ---------------------------------------------------------------------- #
# Context-manager form                                                   #
# ---------------------------------------------------------------------- #


def test_context_increments_counter_per_entry() -> None:
    with escape_hatch(reason="ctx-test"):
        pass
    with escape_hatch(reason="ctx-test"):
        pass
    with escape_hatch(reason="ctx-test"):
        pass
    snap = counter_snapshot()
    assert snap["ctx-test"] == 3


def test_context_warns_only_on_first_hit(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.WARNING, logger="substrate.escape_hatch")
    with escape_hatch(reason="ctx-warn-once"):
        pass
    with escape_hatch(reason="ctx-warn-once"):
        pass
    with escape_hatch(reason="ctx-warn-once"):
        pass

    warns = [
        r for r in caplog.records
        if r.levelno == logging.WARNING
        and "ctx-warn-once" in r.getMessage()
    ]
    assert len(warns) == 1


def test_context_different_reasons_warn_independently(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.WARNING, logger="substrate.escape_hatch")
    with escape_hatch(reason="reason-a"):
        pass
    with escape_hatch(reason="reason-b"):
        pass
    with escape_hatch(reason="reason-a"):
        pass

    msgs = [r.getMessage() for r in caplog.records if r.levelno == logging.WARNING]
    a_warns = sum(1 for m in msgs if "reason-a" in m)
    b_warns = sum(1 for m in msgs if "reason-b" in m)
    assert a_warns == 1
    assert b_warns == 1


# ---------------------------------------------------------------------- #
# Decorator form                                                         #
# ---------------------------------------------------------------------- #


def test_decorator_increments_per_call_not_per_decoration() -> None:
    @escape_hatch(reason="dec-per-call")
    def f() -> int:
        return 42

    # Decoration alone should not have hit
    assert counter_snapshot().get("dec-per-call", 0) == 0
    assert f() == 42
    assert f() == 42
    assert f() == 42
    assert counter_snapshot()["dec-per-call"] == 3


def test_decorator_preserves_return_value_and_args() -> None:
    @escape_hatch(reason="dec-preserve")
    def add(a: int, b: int, *, scale: int = 1) -> int:
        return (a + b) * scale

    assert add(2, 3) == 5
    assert add(2, 3, scale=10) == 50


def test_decorator_warn_once_per_reason_even_with_many_calls(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.WARNING, logger="substrate.escape_hatch")

    @escape_hatch(reason="dec-many-calls")
    def f() -> None:
        return None

    for _ in range(20):
        f()

    warns = [
        r for r in caplog.records
        if r.levelno == logging.WARNING
        and "dec-many-calls" in r.getMessage()
    ]
    assert len(warns) == 1
    assert counter_snapshot()["dec-many-calls"] == 20


# ---------------------------------------------------------------------- #
# Validation                                                             #
# ---------------------------------------------------------------------- #


def test_empty_reason_raises() -> None:
    with pytest.raises(EscapeHatchInvalidReason):
        escape_hatch(reason="")


def test_whitespace_only_reason_raises() -> None:
    with pytest.raises(EscapeHatchInvalidReason):
        escape_hatch(reason="   \t  ")


def test_non_string_reason_raises() -> None:
    with pytest.raises(EscapeHatchInvalidReason):
        escape_hatch(reason=None)  # type: ignore[arg-type]


# ---------------------------------------------------------------------- #
# Exception propagation                                                  #
# ---------------------------------------------------------------------- #


def test_exception_inside_context_propagates() -> None:
    """The hatch must not swallow exceptions — bypasses are operational,
    not error-eating."""
    with pytest.raises(RuntimeError, match="from inside"):
        with escape_hatch(reason="propagate-test"):
            raise RuntimeError("from inside")
    # The counter still incremented before the exception
    assert counter_snapshot()["propagate-test"] == 1


def test_exception_inside_decorated_function_propagates() -> None:
    @escape_hatch(reason="dec-propagate")
    def explode() -> None:
        raise ValueError("boom")

    with pytest.raises(ValueError, match="boom"):
        explode()
    assert counter_snapshot()["dec-propagate"] == 1


# ---------------------------------------------------------------------- #
# Snapshot defensive-copy + reset                                        #
# ---------------------------------------------------------------------- #


def test_counter_snapshot_is_defensive_copy() -> None:
    with escape_hatch(reason="snapshot-test"):
        pass
    snap1 = counter_snapshot()
    snap1["fabricated"] = 999  # mutating the snapshot must not affect state
    snap2 = counter_snapshot()
    assert "fabricated" not in snap2
    assert snap2["snapshot-test"] == 1


def test_reset_clears_both_counters_and_seen(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.WARNING, logger="substrate.escape_hatch")
    with escape_hatch(reason="reset-test"):
        pass
    assert counter_snapshot()["reset-test"] == 1

    reset_counters_for_tests()
    assert counter_snapshot() == {}

    # After reset, a new entry with the same reason should warn again
    caplog.clear()
    with escape_hatch(reason="reset-test"):
        pass
    warns = [
        r for r in caplog.records
        if r.levelno == logging.WARNING and "reset-test" in r.getMessage()
    ]
    assert len(warns) == 1


# ---------------------------------------------------------------------- #
# Thread-safety smoke test                                               #
# ---------------------------------------------------------------------- #


def test_concurrent_entries_do_not_drop_counts() -> None:
    """Spin N threads, each hits the hatch K times. Counter must equal
    N*K. Tests the lock around _counts."""
    n_threads = 8
    k_per_thread = 50

    def worker() -> None:
        for _ in range(k_per_thread):
            with escape_hatch(reason="concurrent-test"):
                pass

    threads = [threading.Thread(target=worker) for _ in range(n_threads)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert counter_snapshot()["concurrent-test"] == n_threads * k_per_thread


def test_concurrent_distinct_reasons_warn_once_each(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Two threads racing on distinct reasons; each reason should produce
    exactly one warning record."""
    caplog.set_level(logging.WARNING, logger="substrate.escape_hatch")

    def worker(reason: str) -> None:
        for _ in range(10):
            with escape_hatch(reason=reason):
                pass

    t1 = threading.Thread(target=worker, args=("race-a",))
    t2 = threading.Thread(target=worker, args=("race-b",))
    t1.start()
    t2.start()
    t1.join()
    t2.join()

    msgs = [r.getMessage() for r in caplog.records if r.levelno == logging.WARNING]
    assert sum(1 for m in msgs if "race-a" in m) == 1
    assert sum(1 for m in msgs if "race-b" in m) == 1
