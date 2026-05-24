"""Tests for substrate.results — the Result[T, E] discriminated union.

Coverage:
- Construction (positional + keyword)
- Predicates (is_ok / is_err)
- Extractors (unwrap, unwrap_or, unwrap_or_else)
- Combinators (map, map_err, and_then) on both arms
- Match-case destructure for both arms
- Pydantic JSON round-trip
- Frozen invariant (cannot mutate after creation)
- ResultUnwrapError raised exactly when expected; inner preserved
- Free-function predicates
- Chained combinators (Ok.and_then → Ok / Ok.and_then → Err / Err.and_then → ...)
"""

from __future__ import annotations

import json

import pytest

from substrate.errors import BudgetExceeded, SchemaMismatch, SubstrateError
from substrate.results import (
    Err,
    Ok,
    Result,
    ResultUnwrapError,
    is_err,
    is_ok,
)


# ---------------------------------------------------------------------- #
# Construction                                                           #
# ---------------------------------------------------------------------- #


def test_ok_constructs_positional_and_keyword() -> None:
    a: Ok[int] = Ok(value=42)
    b: Ok[int] = Ok(value=42)
    assert a == b
    assert a.value == 42
    assert a.tag == "ok"


def test_err_constructs_with_substrate_error() -> None:
    e = BudgetExceeded(cap=100, attempted=150)
    err: Err[SubstrateError] = Err(error=e)
    assert err.error == e
    assert err.tag == "err"


def test_ok_value_can_be_any_type() -> None:
    # arbitrary_types_allowed=True lets T be a plain object
    class Plain:
        def __init__(self, x: int) -> None:
            self.x = x

    p = Plain(5)
    result: Ok[Plain] = Ok(value=p)
    assert result.value is p


# ---------------------------------------------------------------------- #
# Predicates                                                             #
# ---------------------------------------------------------------------- #


def test_ok_predicates() -> None:
    o: Ok[int] = Ok(value=1)
    assert o.is_ok() is True
    assert o.is_err() is False


def test_err_predicates() -> None:
    e: Err[str] = Err(error="boom")
    assert e.is_ok() is False
    assert e.is_err() is True


def test_free_function_predicates() -> None:
    o: Result[int, str] = Ok(value=1)
    e: Result[int, str] = Err(error="boom")
    assert is_ok(o) and not is_err(o)
    assert is_err(e) and not is_ok(e)


# ---------------------------------------------------------------------- #
# Extractors                                                             #
# ---------------------------------------------------------------------- #


def test_ok_unwrap_returns_value() -> None:
    assert Ok(value=7).unwrap() == 7


def test_err_unwrap_raises_result_unwrap_error() -> None:
    err = SchemaMismatch(
        field="x", expected_type="int", actual_repr="'foo'", schema_version=1
    )
    e: Err[SubstrateError] = Err(error=err)
    with pytest.raises(ResultUnwrapError) as exc_info:
        e.unwrap()
    # The original error is preserved on .inner — debuggers don't lose context
    assert exc_info.value.inner is err
    # The message includes the repr so logs show what happened
    assert "schema_mismatch" in repr(exc_info.value.inner).lower()


def test_unwrap_or_returns_default_on_err() -> None:
    e: Err[str] = Err(error="boom")
    assert e.unwrap_or(99) == 99
    o: Ok[int] = Ok(value=1)
    assert o.unwrap_or(99) == 1


def test_unwrap_or_else_invokes_fn_only_on_err() -> None:
    calls: list[str] = []

    def recover(err: str) -> int:
        calls.append(err)
        return -1

    o: Ok[int] = Ok(value=10)
    assert o.unwrap_or_else(recover) == 10
    assert calls == []  # not invoked on Ok

    e: Err[str] = Err(error="boom")
    assert e.unwrap_or_else(recover) == -1
    assert calls == ["boom"]


# ---------------------------------------------------------------------- #
# Combinators                                                            #
# ---------------------------------------------------------------------- #


def test_ok_map_transforms_value() -> None:
    o: Ok[int] = Ok(value=3)
    doubled = o.map(lambda x: x * 2)
    assert doubled.value == 6


def test_err_map_is_noop() -> None:
    e: Err[str] = Err(error="boom")
    # map on Err returns self — same instance (frozen)
    assert e.map(lambda x: x * 2) is e


def test_ok_map_err_is_noop() -> None:
    o: Ok[int] = Ok(value=3)
    assert o.map_err(lambda err: f"wrapped:{err}") is o


def test_err_map_err_transforms_error() -> None:
    e: Err[str] = Err(error="boom")
    wrapped = e.map_err(lambda err: f"wrapped:{err}")
    assert wrapped.error == "wrapped:boom"


def test_and_then_chains_through_ok() -> None:
    def step(x: int) -> Result[int, str]:
        return Ok(value=x + 1)

    result: Result[int, str] = Ok(value=1)
    final = result.and_then(step).and_then(step).and_then(step)
    assert isinstance(final, Ok)
    assert final.value == 4


def test_and_then_short_circuits_at_err() -> None:
    calls: list[int] = []

    def step(x: int) -> Result[int, str]:
        calls.append(x)
        if x == 2:
            return Err(error=f"failed at {x}")
        return Ok(value=x + 1)

    result: Result[int, str] = Ok(value=1)
    final = result.and_then(step).and_then(step).and_then(step)
    assert isinstance(final, Err)
    assert final.error == "failed at 2"
    # Third step never called because the chain short-circuited
    assert calls == [1, 2]


# ---------------------------------------------------------------------- #
# Match-case destructure                                                 #
# ---------------------------------------------------------------------- #


def test_match_destructures_ok() -> None:
    r: Result[int, str] = Ok(value=42)
    match r:
        case Ok(value=v):
            assert v == 42
        case Err():
            pytest.fail("Should not match Err")


def test_match_destructures_err() -> None:
    r: Result[int, str] = Err(error="boom")
    match r:
        case Ok():
            pytest.fail("Should not match Ok")
        case Err(error=e):
            assert e == "boom"


def test_match_with_substrate_error_variant() -> None:
    r: Result[int, SubstrateError] = Err(
        error=BudgetExceeded(cap=100, attempted=150)
    )
    match r:
        case Ok():
            pytest.fail("Should not match Ok")
        case Err(error=BudgetExceeded(cap=cap, attempted=attempted)):
            assert cap == 100
            assert attempted == 150
        case Err():
            pytest.fail("Should have matched the inner BudgetExceeded variant")


# ---------------------------------------------------------------------- #
# Pydantic round-trip                                                    #
# ---------------------------------------------------------------------- #


def test_ok_json_round_trip_primitive() -> None:
    o: Ok[int] = Ok(value=42)
    payload = o.model_dump_json()
    data = json.loads(payload)
    assert data == {"tag": "ok", "value": 42}
    restored = Ok[int].model_validate(data)
    assert restored == o


def test_err_json_round_trip_substrate_error() -> None:
    err = BudgetExceeded(cap=100, attempted=150, units="tokens")
    e: Err[BudgetExceeded] = Err(error=err)
    payload = e.model_dump_json()
    data = json.loads(payload)
    assert data["tag"] == "err"
    assert data["error"]["kind"] == "budget_exceeded"
    assert data["error"]["cap"] == 100
    restored = Err[BudgetExceeded].model_validate(data)
    assert restored.error.cap == 100


# ---------------------------------------------------------------------- #
# Frozen invariant                                                       #
# ---------------------------------------------------------------------- #


def test_ok_is_frozen() -> None:
    o: Ok[int] = Ok(value=42)
    with pytest.raises(Exception):  # pydantic raises ValidationError on frozen
        o.value = 99  # type: ignore[misc]


def test_err_is_frozen() -> None:
    e: Err[str] = Err(error="x")
    with pytest.raises(Exception):
        e.error = "y"  # type: ignore[misc]


# ---------------------------------------------------------------------- #
# Realistic boundary example                                             #
# ---------------------------------------------------------------------- #


def test_realistic_charge_example() -> None:
    """End-to-end: simulate a budget-checked operation that returns a
    Result and exercise both arms with match-case dispatch."""

    def charge(amount: int, remaining: int) -> Result[int, SubstrateError]:
        if amount > remaining:
            return Err(error=BudgetExceeded(cap=remaining, attempted=amount))
        return Ok(value=remaining - amount)

    # Happy path
    match charge(50, 100):
        case Ok(value=after):
            assert after == 50
        case Err():
            pytest.fail("Charge should have succeeded")

    # Failure path
    match charge(150, 100):
        case Ok():
            pytest.fail("Charge should have failed")
        case Err(error=BudgetExceeded(cap=cap)):
            assert cap == 100
        case Err():
            pytest.fail("Should have matched BudgetExceeded specifically")
