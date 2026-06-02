"""Hypothesis property tests for the ARE paved-road modules.

substrate/result_helpers.py, substrate/ownership.py, substrate/exhaustive.py.

Where test_substrate_properties.py covers the Wave 1 encoding, this file
covers the invariants of the paved roads — the properties that, if they
held only for the hand-picked examples but not for all inputs, would let
a subtle bug ship. These are the antithesis/Hegel-style runtime
verifications the Rust interview argued complement the type checker.

Skips cleanly if hypothesis is not installed (opt-in dep).
"""

from __future__ import annotations

import json
import threading

import pytest

hypothesis = pytest.importorskip("hypothesis", reason="hypothesis not installed")
from hypothesis import given, settings  # noqa: E402
from hypothesis import strategies as st  # noqa: E402

from substrate.errors import BudgetExceeded  # noqa: E402
from substrate.exhaustive import (  # noqa: E402
    ReferenceOutcome,
    classify_reference_outcome,
)
from substrate.ownership import DispatchBudgetReference, OwnershipHandle  # noqa: E402
from substrate.result_helpers import (  # noqa: E402
    checked_budget_charge,
    try_decode_json,
    try_parse_model,
)
from substrate.results import Err, Ok  # noqa: E402

PROPERTY_SETTINGS = settings(max_examples=200, deadline=None)
# Concurrency properties run fewer examples — each spins real threads.
CONCURRENCY_SETTINGS = settings(max_examples=25, deadline=None)


# ====================================================================== #
# checked_budget_charge — the never-overspend invariant                  #
# ====================================================================== #


@PROPERTY_SETTINGS
@given(
    current=st.integers(min_value=0, max_value=10**9),
    amount=st.integers(min_value=-(10**9), max_value=10**9),
    cap=st.integers(min_value=0, max_value=10**9),
)
def test_budget_charge_never_commits_over_cap(
    current: int, amount: int, cap: int
) -> None:
    """THE invariant: for ANY inputs, an Ok result's value is <= cap.
    The whole point of the function — proven over the input space, not
    3 examples."""
    result = checked_budget_charge(current, amount, cap)
    match result:
        case Ok(value=new_spend):
            assert new_spend <= cap, (
                f"committed {new_spend} > cap {cap} "
                f"(current={current}, amount={amount})"
            )
        case Err(error=BudgetExceeded()):
            # Rejected — fine. The complementary property below checks
            # rejection happens exactly when it should.
            pass
        case Err():
            pytest.fail("only BudgetExceeded should be returned")


@PROPERTY_SETTINGS
@given(
    current=st.integers(min_value=0, max_value=10**9),
    amount=st.integers(min_value=0, max_value=10**9),
    cap=st.integers(min_value=0, max_value=10**9),
)
def test_budget_charge_rejects_exactly_when_over_cap(
    current: int, amount: int, cap: int
) -> None:
    """Complement: a non-negative charge is Err IFF current+amount > cap.
    No false accepts, no false rejects. (Restricted to amount>=0 because
    negative amounts are refunds and never trip the cap.)"""
    result = checked_budget_charge(current, amount, cap)
    would_exceed = (current + amount) > cap
    assert isinstance(result, Err) == would_exceed


@PROPERTY_SETTINGS
@given(
    current=st.integers(min_value=0, max_value=10**6),
    amount=st.integers(min_value=-(10**6), max_value=10**6),
    cap=st.integers(min_value=0, max_value=10**6),
)
def test_budget_charge_ok_value_is_current_plus_amount(
    current: int, amount: int, cap: int
) -> None:
    """When accepted, the new spend is exactly current+amount — no
    rounding, no drift."""
    result = checked_budget_charge(current, amount, cap)
    if isinstance(result, Ok):
        assert result.value == current + amount


# ====================================================================== #
# try_decode_json — round-trip + total                                   #
# ====================================================================== #

# JSON-serializable values (no NaN/inf — json rejects those by default).
_json_values = st.recursive(
    st.none()
    | st.booleans()
    | st.integers(min_value=-(10**12), max_value=10**12)
    | st.text(max_size=50),
    lambda children: st.lists(children, max_size=5)
    | st.dictionaries(st.text(max_size=20), children, max_size=5),
    max_leaves=15,
)


@PROPERTY_SETTINGS
@given(value=_json_values)
def test_decode_json_round_trips_any_serializable(value: object) -> None:
    """For any JSON-serializable value, decoding its dumps yields Ok
    with the equal value. The encoding is lossless through the helper."""
    raw = json.dumps(value)
    result = try_decode_json(raw)
    match result:
        case Ok(value=decoded):
            assert decoded == value
        case Err():
            pytest.fail(f"valid JSON failed to decode: {raw!r}")


@PROPERTY_SETTINGS
@given(raw=st.text(max_size=200))
def test_decode_json_is_total_never_raises(raw: str) -> None:
    """For ANY string (valid JSON or garbage), try_decode_json returns
    a Result — never raises. Totality is the contract: that's what makes
    it safe to call at a boundary."""
    result = try_decode_json(raw)
    assert isinstance(result, (Ok, Err))


# ====================================================================== #
# try_parse_model — total over arbitrary input                           #
# ====================================================================== #


from pydantic import BaseModel  # noqa: E402


class _PropModel(BaseModel):
    name: str
    count: int


@PROPERTY_SETTINGS
@given(
    data=st.dictionaries(
        st.text(max_size=10),
        st.none() | st.integers() | st.text(max_size=10),
        max_size=5,
    )
)
def test_parse_model_is_total(data: dict[str, object]) -> None:
    """For any dict, try_parse_model returns a Result — never raises a
    ValidationError out of the helper."""
    result = try_parse_model(_PropModel, data)
    assert isinstance(result, (Ok, Err))


@PROPERTY_SETTINGS
@given(name=st.text(min_size=1, max_size=30), count=st.integers())
def test_parse_model_accepts_valid_shape(name: str, count: int) -> None:
    """A dict with the right shape always parses to Ok with matching
    fields."""
    result = try_parse_model(_PropModel, {"name": name, "count": count})
    match result:
        case Ok(value=m):
            assert m.name == name and m.count == count
        case Err():
            pytest.fail(f"valid shape rejected: name={name!r} count={count}")


# ====================================================================== #
# OwnershipHandle — serialization equivalence                            #
# ====================================================================== #


@PROPERTY_SETTINGS
@given(deltas=st.lists(st.integers(min_value=-1000, max_value=1000), max_size=50))
def test_handle_sequential_writes_equal_sum(deltas: list[int]) -> None:
    """Applying a sequence of +delta mutations through write() leaves
    the value equal to initial + sum(deltas). Sequential correctness
    as a property over arbitrary delta sequences."""
    h: OwnershipHandle[int] = OwnershipHandle(0, name="prop")
    for d in deltas:
        h.write(lambda v, d=d: Ok(value=v + d))
    assert h.read() == sum(deltas)


@CONCURRENCY_SETTINGS
@given(
    n_threads=st.integers(min_value=2, max_value=8),
    incr_per_thread=st.integers(min_value=1, max_value=50),
)
def test_handle_concurrent_writes_no_lost_updates(
    n_threads: int, incr_per_thread: int
) -> None:
    """For any thread-count + increment-count, concurrent +1 writes
    through the handle produce exactly n_threads*incr_per_thread — no
    lost updates. The serialization guarantee, proven over a range of
    concurrency shapes rather than one hand-picked (8, 250)."""
    h: OwnershipHandle[int] = OwnershipHandle(0, name="prop_concurrent")

    def worker() -> None:
        for _ in range(incr_per_thread):
            h.write(lambda v: Ok(value=v + 1), timeout_s=5.0)

    threads = [threading.Thread(target=worker) for _ in range(n_threads)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=10.0)

    assert h.read() == n_threads * incr_per_thread


@CONCURRENCY_SETTINGS
@given(
    cap=st.integers(min_value=1, max_value=200),
    n_threads=st.integers(min_value=2, max_value=6),
)
def test_budget_reference_never_exceeds_cap_under_concurrency(
    cap: int, n_threads: int
) -> None:
    """For any cap + thread-count, N threads each charging 1 unit far
    more times than the cap allows leaves the committed total EXACTLY
    at cap (never over) and exactly cap successful charges. The
    race-free cap invariant, proven over a range of caps + concurrency."""
    b = DispatchBudgetReference(cap=cap)
    attempts_per_thread = cap  # total attempts (n_threads*cap) >> cap
    successes = [0] * n_threads

    def worker(idx: int) -> None:
        local = 0
        for _ in range(attempts_per_thread):
            if isinstance(b.charge(1, timeout_s=5.0), Ok):
                local += 1
        successes[idx] = local

    threads = [
        threading.Thread(target=worker, args=(i,)) for i in range(n_threads)
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=15.0)

    assert b.spent == cap
    assert sum(successes) == cap


# ====================================================================== #
# exhaustive — classify is total over the closed set                     #
# ====================================================================== #


@PROPERTY_SETTINGS
@given(outcome=st.sampled_from(["allowed", "blocked", "held"]))
def test_classify_reference_outcome_total_over_closed_set(
    outcome: ReferenceOutcome,
) -> None:
    """For every declared variant, classify returns a non-empty string
    (none fall through to assert_exhaustive). Totality over the closed
    set — the property the type guarantees and this confirms at runtime."""
    result = classify_reference_outcome(outcome)
    assert isinstance(result, str) and result
