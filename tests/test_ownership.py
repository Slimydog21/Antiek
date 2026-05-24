"""Tests for substrate.ownership — the ownership-handle reference.

The load-bearing tests are the concurrency ones: under N threads racing
to charge a budget, the cap is never exceeded (the race-free property
that justifies the handle existing).
"""

from __future__ import annotations

import threading

import pytest

from substrate.errors import BudgetExceeded, SubstrateError, WriterContended
from substrate.ownership import (
    DEFAULT_ACQUIRE_TIMEOUT_S,
    DispatchBudgetReference,
    OwnershipHandle,
)
from substrate.results import Err, Ok, Result


# ---------------------------------------------------------------------- #
# OwnershipHandle — basic read/write                                     #
# ---------------------------------------------------------------------- #


def test_read_returns_initial() -> None:
    h: OwnershipHandle[int] = OwnershipHandle(42, name="t")
    assert h.read() == 42


def test_name_property() -> None:
    h: OwnershipHandle[int] = OwnershipHandle(0, name="my_resource")
    assert h.name == "my_resource"


def test_write_ok_advances_value() -> None:
    h: OwnershipHandle[int] = OwnershipHandle(10, name="t")
    result = h.write(lambda v: Ok(value=v + 5))
    assert isinstance(result, Ok)
    assert result.value == 15
    assert h.read() == 15


def test_write_err_leaves_value_unchanged() -> None:
    h: OwnershipHandle[int] = OwnershipHandle(10, name="t")

    def reject(_v: int) -> Result[int, SubstrateError]:
        return Err(error=BudgetExceeded(cap=10, attempted=99))

    result = h.write(reject)
    assert isinstance(result, Err)
    assert h.read() == 10  # unchanged


def test_write_propagates_raising_mutation() -> None:
    """A mutation that RAISES (rather than returning Err) is a
    programmer error — the exception propagates and the lock is
    released."""
    h: OwnershipHandle[int] = OwnershipHandle(10, name="t")

    def boom(_v: int) -> Result[int, SubstrateError]:
        raise RuntimeError("programmer error")

    with pytest.raises(RuntimeError, match="programmer error"):
        h.write(boom)

    # Lock was released — a subsequent write succeeds (doesn't deadlock)
    assert h.write(lambda v: Ok(value=v + 1)).unwrap() == 11


def test_sequential_writes_accumulate() -> None:
    h: OwnershipHandle[int] = OwnershipHandle(0, name="t")
    for _ in range(100):
        h.write(lambda v: Ok(value=v + 1))
    assert h.read() == 100


# ---------------------------------------------------------------------- #
# WriterContended on lock-acquire timeout                                #
# ---------------------------------------------------------------------- #


def test_write_returns_writer_contended_on_timeout() -> None:
    """Hold the lock in one thread; a second writer with a short
    timeout must get Err(WriterContended) rather than blocking."""
    h: OwnershipHandle[int] = OwnershipHandle(0, name="contended_resource")

    holder_entered = threading.Event()
    release_holder = threading.Event()

    def holder() -> None:
        def slow_mutation(v: int) -> Result[int, SubstrateError]:
            holder_entered.set()
            release_holder.wait(timeout=5.0)  # hold the lock
            return Ok(value=v + 1)

        h.write(slow_mutation)

    t = threading.Thread(target=holder)
    t.start()
    try:
        assert holder_entered.wait(timeout=5.0), "holder never acquired lock"
        # Second writer with a tiny timeout should be contended
        result = h.write(lambda v: Ok(value=v + 100), timeout_s=0.1)
        match result:
            case Err(error=WriterContended(resource=res, timeout_s=ts)):
                assert res == "contended_resource"
                assert ts == 0.1
            case _:
                pytest.fail("expected Err(WriterContended)")
    finally:
        release_holder.set()
        t.join(timeout=5.0)


# ---------------------------------------------------------------------- #
# DispatchBudgetReference                                                #
# ---------------------------------------------------------------------- #


def test_budget_charge_under_cap() -> None:
    b = DispatchBudgetReference(cap=100)
    assert b.charge(30).unwrap() == 30
    assert b.charge(50).unwrap() == 80
    assert b.spent == 80
    assert b.remaining == 20


def test_budget_charge_over_cap_returns_err_and_does_not_advance() -> None:
    b = DispatchBudgetReference(cap=100)
    b.charge(80)
    result = b.charge(30)  # would be 110 > 100
    assert isinstance(result, Err)
    assert isinstance(result.error, BudgetExceeded)
    assert b.spent == 80  # unchanged — the rejected charge didn't land


def test_budget_units_propagate() -> None:
    b = DispatchBudgetReference(cap=100, units="usd_cents")
    result = b.charge(150)
    assert isinstance(result, Err)
    assert isinstance(result.error, BudgetExceeded)
    assert result.error.units == "usd_cents"


# ---------------------------------------------------------------------- #
# Concurrency — the load-bearing property                                #
# ---------------------------------------------------------------------- #


def test_concurrent_charges_never_exceed_cap() -> None:
    """N threads each try to charge 1 unit, K times, against a cap that's
    LESS than N*K. The committed total must land EXACTLY at the cap (not
    over), and exactly cap-many charges succeed. This is the race-free
    property that justifies the handle: without the in-lock cap check,
    concurrent charges could race past the cap."""
    cap = 500
    n_threads = 10
    charges_per_thread = 100  # 10*100 = 1000 attempts vs cap 500

    b = DispatchBudgetReference(cap=cap)
    successes = [0] * n_threads

    def worker(idx: int) -> None:
        local = 0
        for _ in range(charges_per_thread):
            result = b.charge(1, timeout_s=5.0)
            if isinstance(result, Ok):
                local += 1
        successes[idx] = local

    threads = [threading.Thread(target=worker, args=(i,))
               for i in range(n_threads)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=10.0)

    # Total committed equals the cap exactly — never over
    assert b.spent == cap
    # Exactly cap-many charges of 1 unit succeeded across all threads
    assert sum(successes) == cap


def test_concurrent_writes_serialize_correctly() -> None:
    """N threads incrementing a counter K times each must produce
    exactly N*K — no lost updates (which is what a non-serialized
    read-modify-write would suffer)."""
    h: OwnershipHandle[int] = OwnershipHandle(0, name="counter")
    n_threads = 8
    incr_per_thread = 250

    def worker() -> None:
        for _ in range(incr_per_thread):
            h.write(lambda v: Ok(value=v + 1), timeout_s=5.0)

    threads = [threading.Thread(target=worker) for _ in range(n_threads)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=10.0)

    assert h.read() == n_threads * incr_per_thread


# ---------------------------------------------------------------------- #
# Default timeout sanity                                                  #
# ---------------------------------------------------------------------- #


def test_default_acquire_timeout_is_bounded() -> None:
    """The default must be a finite, bounded wait — never block
    forever. Mirrors db_lock's bounded-wait discipline."""
    assert 0 < DEFAULT_ACQUIRE_TIMEOUT_S < 300
