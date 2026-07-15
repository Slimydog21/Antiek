from __future__ import annotations

import json
from pathlib import Path

import pytest

from substrate.paid_operations.contracts import (
    CanonicalIntent,
    IntentContractError,
    canonicalize_intent,
)

OWNER = "owner-1"
ACCOUNT = "acct-1"
OPERATION = "op-1"
HASH_A = "a" * 64
HASH_B = "b" * 64
HASH_C = "c" * 64


def collective_payload() -> dict[str, object]:
    return {
        "schema_version": 1,
        "quote_cents": 12,
        "ceiling_cents": 20,
        "pricing_snapshot_id": "price-1",
        "pricing_snapshot_hash": HASH_A,
        "created_at_ms": 1_000,
        "expires_at_ms": 2_000,
        "compose_id": "compose-1",
        "compose_fingerprint": HASH_B,
        "frozen_member_ids": ["member-1", "member-2"],
        "frozen_member_body_hashes": [HASH_A, HASH_C],
        "question": "Where do these sources disagree?",
        "context_packet_hash": HASH_C,
        "context_packet_bytes": 2048,
        "route_id": "route-1",
        "provider_id": "provider-1",
        "model_id": "model-1",
        "temperature_millionths": 250_000,
        "max_input_tokens": 4096,
        "max_output_tokens": 1024,
        "source_policy_version": "source-policy-v1",
        "answer_schema_version": "answer-schema-v1",
    }


def midnight_payload() -> dict[str, object]:
    return {
        "schema_version": 1,
        "quote_cents": 30,
        "ceiling_cents": 45,
        "pricing_snapshot_id": "price-1",
        "pricing_snapshot_hash": HASH_A,
        "created_at_ms": 1_000,
        "expires_at_ms": 2_000,
        "job_id": "job-1",
        "goals": ["read carefully", "write synthesis"],
        "duration_minutes": 90,
        "research_brief_hash": HASH_B,
        "acceptance_policy_version": "accept-v1",
        "acceptance_policy_hash": HASH_C,
        "retrieval_source_policy_version": "retrieval-v1",
        "route_id": "route-1",
        "provider_id": "provider-1",
        "model_id": "model-1",
        "temperature_millionths": 100_000,
        "max_input_tokens": 8000,
        "max_output_tokens": 2000,
        "max_steps": 12,
        "deposit_policy_version": "deposit-v1",
    }


def _canonical(kind: str, payload: dict[str, object]) -> CanonicalIntent:
    return canonicalize_intent(
        owner_user_id=OWNER,
        account_id=ACCOUNT,
        operation_id=OPERATION,
        kind=kind,
        payload=payload,
    )


def test_golden_vectors_are_reproducible() -> None:
    fixture = json.loads(
        Path("tests/fixtures/paid_operations/intent-v1.json").read_text(encoding="utf-8")
    )
    for vector in fixture["vectors"]:
        canonical = canonicalize_intent(
            owner_user_id=vector["owner_user_id"],
            account_id=vector["account_id"],
            operation_id=vector["operation_id"],
            kind=vector["kind"],
            payload=vector["payload"],
        )
        assert canonical.canonical_json == vector["canonical_json"]
        assert canonical.intent_hash == vector["intent_hash"]


@pytest.mark.parametrize("kind,payload", [
    ("collective_interrogation_v1", collective_payload()),
    ("midnight_oil_v1", midnight_payload()),
])
def test_rejects_unstable_json_profiles(kind: str, payload: dict[str, object]) -> None:
    for key, value in [
        ("unknown", "x"),
        ("quote_cents", 1.5),
        ("ceiling_cents", None),
        ("pricing_snapshot_hash", HASH_A.upper()),
        ("question" if kind == "collective_interrogation_v1" else "goals", "Cafe\u0301"),
    ]:
        changed = dict(payload)
        changed[key] = value
        with pytest.raises(IntentContractError):
            _canonical(kind, changed)


@pytest.mark.parametrize(
    "kind,payload,field",
    [
        ("collective_interrogation_v1", collective_payload(), "schema_version"),
        ("collective_interrogation_v1", collective_payload(), "quote_cents"),
        ("collective_interrogation_v1", collective_payload(), "ceiling_cents"),
        ("collective_interrogation_v1", collective_payload(), "created_at_ms"),
        ("collective_interrogation_v1", collective_payload(), "expires_at_ms"),
        ("collective_interrogation_v1", collective_payload(), "context_packet_bytes"),
        ("collective_interrogation_v1", collective_payload(), "temperature_millionths"),
        ("collective_interrogation_v1", collective_payload(), "max_input_tokens"),
        ("collective_interrogation_v1", collective_payload(), "max_output_tokens"),
        ("midnight_oil_v1", midnight_payload(), "duration_minutes"),
        ("midnight_oil_v1", midnight_payload(), "temperature_millionths"),
        ("midnight_oil_v1", midnight_payload(), "max_input_tokens"),
        ("midnight_oil_v1", midnight_payload(), "max_output_tokens"),
        ("midnight_oil_v1", midnight_payload(), "max_steps"),
    ],
)
def test_bool_as_int_rejected_for_every_integer_field(
    kind: str,
    payload: dict[str, object],
    field: str,
) -> None:
    payload[field] = True
    with pytest.raises(IntentContractError, match="integer"):
        _canonical(kind, payload)


@pytest.mark.parametrize(
    "kind,payload,field,value",
    [
        ("collective_interrogation_v1", collective_payload(), "context_packet_bytes", 104_857_601),
        ("collective_interrogation_v1", collective_payload(), "temperature_millionths", 1_000_001),
        ("collective_interrogation_v1", collective_payload(), "max_input_tokens", 1_000_001),
        ("collective_interrogation_v1", collective_payload(), "max_output_tokens", 1_000_001),
        ("midnight_oil_v1", midnight_payload(), "duration_minutes", 10_081),
        ("midnight_oil_v1", midnight_payload(), "temperature_millionths", 1_000_001),
        ("midnight_oil_v1", midnight_payload(), "max_input_tokens", 1_000_001),
        ("midnight_oil_v1", midnight_payload(), "max_output_tokens", 1_000_001),
        ("midnight_oil_v1", midnight_payload(), "max_steps", 10_001),
    ],
)
def test_operational_integer_upper_bounds(
    kind: str,
    payload: dict[str, object],
    field: str,
    value: int,
) -> None:
    payload[field] = value
    with pytest.raises(IntentContractError, match="exceeds maximum"):
        _canonical(kind, payload)


def test_rejects_duplicate_collective_member_ids_even_with_identical_hash_pair() -> None:
    payload = collective_payload()
    payload["frozen_member_ids"] = ["member-1", "member-1"]
    payload["frozen_member_body_hashes"] = [HASH_A, HASH_A]
    with pytest.raises(IntentContractError, match="unique"):
        _canonical("collective_interrogation_v1", payload)


def test_rejects_duplicate_midnight_oil_goals() -> None:
    payload = midnight_payload()
    payload["goals"] = ["read carefully", "read carefully"]
    with pytest.raises(IntentContractError, match="unique"):
        _canonical("midnight_oil_v1", payload)


def test_owner_account_operation_and_kind_are_not_body_authority() -> None:
    payload = collective_payload()
    payload["owner_user_id"] = "owner-2"
    with pytest.raises(IntentContractError, match="server-derived"):
        _canonical("collective_interrogation_v1", payload)


def test_every_collective_field_affects_hash() -> None:
    base = collective_payload()
    baseline = _canonical("collective_interrogation_v1", base).intent_hash
    changes: dict[str, object] = {
        "quote_cents": 13,
        "ceiling_cents": 21,
        "pricing_snapshot_id": "price-2",
        "pricing_snapshot_hash": HASH_B,
        "created_at_ms": 1_001,
        "expires_at_ms": 2_001,
        "compose_id": "compose-2",
        "compose_fingerprint": HASH_C,
        "frozen_member_ids": ["member-2", "member-1"],
        "frozen_member_body_hashes": [HASH_C, HASH_A],
        "question": "What changed?",
        "context_packet_hash": HASH_B,
        "context_packet_bytes": 2049,
        "route_id": "route-2",
        "provider_id": "provider-2",
        "model_id": "model-2",
        "temperature_millionths": 250_001,
        "max_input_tokens": 4097,
        "max_output_tokens": 1025,
        "source_policy_version": "source-policy-v2",
        "answer_schema_version": "answer-schema-v2",
    }
    for field, value in changes.items():
        payload = dict(base)
        payload[field] = value
        assert _canonical("collective_interrogation_v1", payload).intent_hash != baseline, field


def test_every_midnight_oil_field_affects_hash() -> None:
    base = midnight_payload()
    baseline = _canonical("midnight_oil_v1", base).intent_hash
    changes: dict[str, object] = {
        "quote_cents": 31,
        "ceiling_cents": 46,
        "pricing_snapshot_id": "price-2",
        "pricing_snapshot_hash": HASH_B,
        "created_at_ms": 1_001,
        "expires_at_ms": 2_001,
        "job_id": "job-2",
        "goals": ["write synthesis", "read carefully"],
        "duration_minutes": 91,
        "research_brief_hash": HASH_C,
        "acceptance_policy_version": "accept-v2",
        "acceptance_policy_hash": HASH_A,
        "retrieval_source_policy_version": "retrieval-v2",
        "route_id": "route-2",
        "provider_id": "provider-2",
        "model_id": "model-2",
        "temperature_millionths": 100_001,
        "max_input_tokens": 8001,
        "max_output_tokens": 2001,
        "max_steps": 13,
        "deposit_policy_version": "deposit-v2",
    }
    for field, value in changes.items():
        payload = dict(base)
        payload[field] = value
        assert _canonical("midnight_oil_v1", payload).intent_hash != baseline, field


def test_rejects_overflow_and_quote_above_ceiling() -> None:
    payload = collective_payload()
    payload["quote_cents"] = 2**63
    with pytest.raises(IntentContractError, match="out of range"):
        _canonical("collective_interrogation_v1", payload)
    payload = collective_payload()
    payload["quote_cents"] = 21
    with pytest.raises(IntentContractError, match="quote_cents"):
        _canonical("collective_interrogation_v1", payload)


def test_rejects_oversized_strings_and_arrays_before_canonicalization() -> None:
    payload = collective_payload()
    payload["question"] = "x" * 65_537
    with pytest.raises(IntentContractError, match="UTF-8 bytes"):
        _canonical("collective_interrogation_v1", payload)

    payload = midnight_payload()
    payload["goals"] = [f"goal-{index}" for index in range(1_025)]
    with pytest.raises(IntentContractError, match="1024 items"):
        _canonical("midnight_oil_v1", payload)
