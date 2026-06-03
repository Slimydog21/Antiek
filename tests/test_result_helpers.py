"""Tests for substrate.result_helpers — the paved-path Result adapters."""

from __future__ import annotations

import pytest
from pydantic import BaseModel

from substrate.errors import BudgetExceeded, SchemaMismatch
from substrate.result_helpers import (
    checked_budget_charge,
    try_call,
    try_decode_json,
    try_parse_model,
)
from substrate.results import Err, Ok

# ---------------------------------------------------------------------- #
# try_decode_json                                                        #
# ---------------------------------------------------------------------- #


def test_decode_json_ok_on_valid() -> None:
    result = try_decode_json('{"a": 1, "b": [2, 3]}')
    match result:
        case Ok(value=v):
            assert v == {"a": 1, "b": [2, 3]}
        case Err():
            pytest.fail("valid JSON should decode")


def test_decode_json_err_on_invalid() -> None:
    result = try_decode_json("not json {{{")
    match result:
        case Ok():
            pytest.fail("invalid JSON should not decode")
        case Err(error=SchemaMismatch(field=field, expected_type=et)):
            assert field == "<json-root>"
            assert et == "valid-json"
        case Err():
            pytest.fail("should be a SchemaMismatch")


def test_decode_json_truncates_actual_repr() -> None:
    big = '{"x": "' + ("z" * 5000) + '"'  # invalid (unterminated)
    result = try_decode_json(big)
    assert isinstance(result, Err)
    assert isinstance(result.error, SchemaMismatch)
    assert len(result.error.actual_repr) <= 200


def test_decode_json_propagates_schema_version() -> None:
    result = try_decode_json("bad", schema_version=7)
    assert isinstance(result, Err)
    assert isinstance(result.error, SchemaMismatch)
    assert result.error.schema_version == 7


# ---------------------------------------------------------------------- #
# try_parse_model                                                        #
# ---------------------------------------------------------------------- #


class _Sample(BaseModel):
    name: str
    count: int


def test_parse_model_ok_on_valid() -> None:
    result = try_parse_model(_Sample, {"name": "x", "count": 5})
    match result:
        case Ok(value=m):
            assert m.name == "x"
            assert m.count == 5
        case Err():
            pytest.fail("valid data should parse")


def test_parse_model_err_on_missing_field() -> None:
    result = try_parse_model(_Sample, {"name": "x"})  # count missing
    assert isinstance(result, Err)
    assert isinstance(result.error, SchemaMismatch)
    assert "count" in result.error.field


def test_parse_model_err_on_wrong_type() -> None:
    result = try_parse_model(_Sample, {"name": "x", "count": "not-an-int"})
    assert isinstance(result, Err)
    assert isinstance(result.error, SchemaMismatch)
    assert "count" in result.error.field


def test_parse_model_propagates_schema_version() -> None:
    result = try_parse_model(_Sample, {}, schema_version=3)
    assert isinstance(result, Err)
    assert isinstance(result.error, SchemaMismatch)
    assert result.error.schema_version == 3


# ---------------------------------------------------------------------- #
# checked_budget_charge                                                  #
# ---------------------------------------------------------------------- #


def test_budget_charge_ok_under_cap() -> None:
    result = checked_budget_charge(current_spend=50, amount=30, cap=100)
    assert result.unwrap() == 80


def test_budget_charge_ok_exactly_at_cap() -> None:
    """Exactly hitting the cap is allowed — cap is inclusive."""
    result = checked_budget_charge(current_spend=70, amount=30, cap=100)
    assert result.unwrap() == 100


def test_budget_charge_err_over_cap() -> None:
    result = checked_budget_charge(current_spend=80, amount=30, cap=100)
    match result:
        case Ok():
            pytest.fail("over-cap charge should fail")
        case Err(error=BudgetExceeded(cap=cap, attempted=att)):
            assert cap == 100
            assert att == 110
        case Err():
            pytest.fail("should be BudgetExceeded")


def test_budget_charge_allows_negative_amount_refund() -> None:
    """Refunds/credits (negative amount) are permitted; only the cap is
    enforced."""
    result = checked_budget_charge(current_spend=50, amount=-20, cap=100)
    assert result.unwrap() == 30


def test_budget_charge_custom_units() -> None:
    result = checked_budget_charge(
        current_spend=80, amount=30, cap=100, units="usd_cents"
    )
    assert isinstance(result, Err)
    assert isinstance(result.error, BudgetExceeded)
    assert result.error.units == "usd_cents"


# ---------------------------------------------------------------------- #
# try_call                                                               #
# ---------------------------------------------------------------------- #


def test_try_call_ok_on_success() -> None:
    result = try_call(
        lambda: 6 * 7,
        on_error=lambda exc: SchemaMismatch(
            field="x", expected_type="int", actual_repr=repr(exc),
            schema_version=0,
        ),
    )
    assert result.unwrap() == 42


def test_try_call_err_on_exception() -> None:
    def boom() -> int:
        raise ValueError("kaboom")

    result = try_call(
        boom,
        on_error=lambda exc: SchemaMismatch(
            field="boom", expected_type="int", actual_repr=str(exc),
            schema_version=0,
        ),
    )
    match result:
        case Ok():
            pytest.fail("exception should produce Err")
        case Err(error=SchemaMismatch(actual_repr=rep)):
            assert "kaboom" in rep
        case Err():
            pytest.fail("should be SchemaMismatch")


def test_try_call_does_not_catch_keyboardinterrupt() -> None:
    """try_call catches Exception, NOT BaseException — so shutdown
    signals propagate as they should."""

    def interrupt() -> int:
        raise KeyboardInterrupt()

    with pytest.raises(KeyboardInterrupt):
        try_call(
            interrupt,
            on_error=lambda exc: SchemaMismatch(
                field="x", expected_type="int", actual_repr="",
                schema_version=0,
            ),
        )


def test_try_call_on_error_receives_the_exception() -> None:
    captured: list[Exception] = []

    def boom() -> int:
        raise RuntimeError("specific message")

    def on_error(exc: Exception) -> SchemaMismatch:
        captured.append(exc)
        return SchemaMismatch(
            field="x", expected_type="int", actual_repr=str(exc),
            schema_version=0,
        )

    try_call(boom, on_error=on_error)
    assert len(captured) == 1
    assert isinstance(captured[0], RuntimeError)
    assert str(captured[0]) == "specific message"


# ---------------------------------------------------------------------- #
# Realistic composition — chain helpers via and_then                     #
# ---------------------------------------------------------------------- #


def test_decode_then_parse_chains_via_and_then() -> None:
    """The paved path composes: decode JSON, then parse into a model,
    short-circuiting at the first Err."""
    raw = '{"name": "widget", "count": 3}'
    result = try_decode_json(raw).and_then(
        lambda data: try_parse_model(_Sample, data)
    )
    match result:
        case Ok(value=m):
            assert m.name == "widget"
            assert m.count == 3
        case Err():
            pytest.fail("valid pipeline should succeed")


def test_decode_then_parse_short_circuits_on_bad_json() -> None:
    result = try_decode_json("not json").and_then(
        lambda data: try_parse_model(_Sample, data)
    )
    assert isinstance(result, Err)
    # The error is the JSON decode failure, not a parse failure
    assert isinstance(result.error, SchemaMismatch)
    assert result.error.field == "<json-root>"
