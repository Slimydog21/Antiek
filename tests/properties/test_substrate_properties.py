"""Hypothesis property tests for substrate.results / errors / escape_hatch.

Skips if hypothesis is not installed. ARE-07 scoped to Wave-1 modules.
"""

from __future__ import annotations

import json

import pytest

hypothesis = pytest.importorskip("hypothesis", reason="hypothesis not installed")
from hypothesis import given, settings  # noqa: E402
from hypothesis import strategies as st  # noqa: E402
from pydantic import TypeAdapter  # noqa: E402

from substrate.errors import SubstrateError  # noqa: E402
from substrate.escape_hatch import (  # noqa: E402
    counter_snapshot,
    escape_hatch,
    reset_counters_for_tests,
)
from substrate.results import Err, Ok  # noqa: E402
from tests.properties.strategies import (  # noqa: E402
    err_substrate,
    ok_int,
    result_int,
    substrate_error,
)

PROPERTY_SETTINGS = settings(max_examples=100, deadline=None)


@PROPERTY_SETTINGS
@given(value=ok_int())
def test_ok_int_json_round_trip(value: Ok[int]) -> None:
    restored = Ok[int].model_validate_json(value.model_dump_json())
    assert restored == value


@PROPERTY_SETTINGS
@given(value=err_substrate())
def test_err_substrate_round_trip(value: Err[SubstrateError]) -> None:
    data = json.loads(value.model_dump_json())
    adapter: TypeAdapter[SubstrateError] = TypeAdapter(SubstrateError)
    restored = adapter.validate_python(data["error"])
    assert restored == value.error
    assert type(restored) is type(value.error)


@PROPERTY_SETTINGS
@given(err=substrate_error())
def test_substrate_error_union_preserves_variant(err: SubstrateError) -> None:
    adapter: TypeAdapter[SubstrateError] = TypeAdapter(SubstrateError)
    restored = adapter.validate_json(adapter.dump_json(err))
    assert type(restored) is type(err)
    assert restored == err


@PROPERTY_SETTINGS
@given(o=ok_int())
def test_ok_and_then_left_identity(o: Ok[int]) -> None:
    chained = o.and_then(lambda v: Ok(value=v))
    assert chained == o


@PROPERTY_SETTINGS
@given(e=err_substrate(), seed=st.integers())
def test_err_and_then_short_circuits(e: Err[SubstrateError], seed: int) -> None:
    invocations: list[object] = []

    def fn(v: object) -> Ok[int]:
        invocations.append(v)
        return Ok(value=seed)

    result = e.and_then(fn)
    assert invocations == []
    assert result == e


@PROPERTY_SETTINGS
@given(o=ok_int(),
       a=st.integers(min_value=-1000, max_value=1000),
       b=st.integers(min_value=-1000, max_value=1000))
def test_ok_map_composes(o: Ok[int], a: int, b: int) -> None:
    def f(x: int) -> int:
        return x + a

    def g(x: int) -> int:
        return x * b

    assert o.map(f).map(g) == o.map(lambda x: g(f(x)))


@PROPERTY_SETTINGS
@given(v=st.integers())
def test_two_ok_with_same_value_equal(v: int) -> None:
    assert Ok(value=v) == Ok(value=v)


@PROPERTY_SETTINGS
@given(e=substrate_error())
def test_two_err_with_same_inner_equal(e: SubstrateError) -> None:
    assert Err(error=e) == Err(error=e)


@PROPERTY_SETTINGS
@given(reason=st.text(min_size=1, max_size=48).filter(lambda s: s.strip()),
       n=st.integers(min_value=1, max_value=50))
def test_escape_hatch_counter_linearity(reason: str, n: int) -> None:
    reset_counters_for_tests()
    for _ in range(n):
        with escape_hatch(reason=reason):
            pass
    assert counter_snapshot().get(reason, 0) == n


@PROPERTY_SETTINGS
@given(o=ok_int(), default=st.integers())
def test_ok_unwrap_or_returns_value(o: Ok[int], default: int) -> None:
    assert o.unwrap_or(default) == o.value


@PROPERTY_SETTINGS
@given(e=err_substrate(), default=st.integers())
def test_err_unwrap_or_returns_default(e: Err[SubstrateError], default: int) -> None:
    assert e.unwrap_or(default) == default


@PROPERTY_SETTINGS
@given(r=result_int())
def test_any_result_destructures_via_match(r: object) -> None:
    matched: list[str] = []
    match r:
        case Ok():
            matched.append("ok")
        case Err():
            matched.append("err")
    assert len(matched) == 1
