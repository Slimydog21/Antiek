"""Tests for substrate.errors — the SubstrateError discriminated union.

Coverage:
- Each variant constructs cleanly with required + optional fields
- The ``kind`` discriminator is the variant's literal
- Pydantic JSON round-trip preserves the kind discriminator and all fields
- Frozen — variants cannot be mutated after construction
- The SubstrateError union resolves on the ``kind`` discriminator
- ``Optional`` fields default to None and are omitted-or-null on serialization
"""

from __future__ import annotations

import json

import pytest
from pydantic import TypeAdapter, ValidationError

from substrate.errors import (
    BudgetExceeded,
    SchemaMismatch,
    SubstrateError,
    UpstreamUnavailable,
    VerifierTimeout,
    WriterContended,
)

# ---------------------------------------------------------------------- #
# Construction + discriminator                                           #
# ---------------------------------------------------------------------- #


def test_budget_exceeded_construction_and_default_units() -> None:
    err = BudgetExceeded(cap=100, attempted=150)
    assert err.kind == "budget_exceeded"
    assert err.cap == 100
    assert err.attempted == 150
    assert err.units == "tokens"  # default


def test_budget_exceeded_override_units() -> None:
    err = BudgetExceeded(cap=100, attempted=150, units="usd_cents")
    assert err.units == "usd_cents"


def test_schema_mismatch_required_fields() -> None:
    err = SchemaMismatch(
        field="user_id",
        expected_type="int",
        actual_repr="'abc'",
        schema_version=3,
    )
    assert err.kind == "schema_mismatch"
    assert err.field == "user_id"
    assert err.schema_version == 3


def test_upstream_unavailable_optional_fields() -> None:
    err = UpstreamUnavailable(upstream="openai")
    assert err.kind == "upstream_unavailable"
    assert err.upstream == "openai"
    assert err.status_code is None
    assert err.reason is None


def test_upstream_unavailable_with_status_and_reason() -> None:
    err = UpstreamUnavailable(
        upstream="anthropic", status_code=503, reason="overloaded"
    )
    assert err.status_code == 503
    assert err.reason == "overloaded"


def test_verifier_timeout_fields() -> None:
    err = VerifierTimeout(
        verifier="legal_gate.v2", elapsed_s=12.5, timeout_s=10.0
    )
    assert err.kind == "verifier_timeout"
    assert err.elapsed_s == 12.5


def test_writer_contended_optional_holder_pid() -> None:
    err = WriterContended(resource="syntheses", timeout_s=300.0)
    assert err.kind == "writer_contended"
    assert err.holder_pid is None

    err2 = WriterContended(
        resource="syntheses", holder_pid=4242, timeout_s=300.0
    )
    assert err2.holder_pid == 4242


# ---------------------------------------------------------------------- #
# Frozen invariant                                                       #
# ---------------------------------------------------------------------- #


def test_budget_exceeded_is_frozen() -> None:
    err = BudgetExceeded(cap=100, attempted=150)
    with pytest.raises(ValidationError):
        err.cap = 999  # type: ignore[misc]


def test_schema_mismatch_is_frozen() -> None:
    err = SchemaMismatch(
        field="x", expected_type="int", actual_repr="'y'", schema_version=1
    )
    with pytest.raises(ValidationError):
        err.field = "renamed"  # type: ignore[misc]


# ---------------------------------------------------------------------- #
# Pydantic round-trip                                                    #
# ---------------------------------------------------------------------- #


def test_budget_exceeded_round_trip() -> None:
    err = BudgetExceeded(cap=100, attempted=150)
    payload = err.model_dump_json()
    restored = BudgetExceeded.model_validate(json.loads(payload))
    assert restored == err


def test_upstream_unavailable_round_trip_with_optionals() -> None:
    err = UpstreamUnavailable(upstream="openai", status_code=429, reason="rate-limit")
    data = json.loads(err.model_dump_json())
    assert data["upstream"] == "openai"
    assert data["status_code"] == 429
    restored = UpstreamUnavailable.model_validate(data)
    assert restored == err


# ---------------------------------------------------------------------- #
# Discriminated-union dispatch via TypeAdapter                           #
# ---------------------------------------------------------------------- #


def test_substrate_error_union_resolves_each_variant() -> None:
    """The SubstrateError union should resolve to the right concrete
    variant when deserializing from JSON. Pydantic resolves by trying
    each member; with the ``kind`` literal it picks the right one.
    """
    adapter: TypeAdapter[SubstrateError] = TypeAdapter(SubstrateError)

    samples: list[SubstrateError] = [
        BudgetExceeded(cap=10, attempted=20),
        SchemaMismatch(
            field="x", expected_type="int", actual_repr="None", schema_version=1
        ),
        UpstreamUnavailable(upstream="exa", status_code=500),
        VerifierTimeout(verifier="v1", elapsed_s=5.0, timeout_s=4.0),
        WriterContended(resource="syntheses", timeout_s=300.0),
    ]

    for original in samples:
        payload = original.model_dump_json()
        restored = adapter.validate_json(payload)
        # Variant preserved; equality holds
        assert type(restored) is type(original)
        assert restored == original


def test_substrate_error_can_match_on_kind() -> None:
    """The whole point of the discriminator: ``match`` on the ``kind``
    field cleanly routes to the right variant."""
    err: SubstrateError = BudgetExceeded(cap=100, attempted=150)

    match err:
        case BudgetExceeded(cap=cap, attempted=att):
            assert cap == 100 and att == 150
        case SchemaMismatch():
            pytest.fail()
        case UpstreamUnavailable():
            pytest.fail()
        case VerifierTimeout():
            pytest.fail()
        case WriterContended():
            pytest.fail()
