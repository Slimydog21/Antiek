from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest

from runtime.provider_broker import authorization_from_mapping as package_authorization_parser
from runtime.provider_broker.protocol import (
    BROKER_AUDIENCE,
    BrokerAuthorization,
    BrokerReceipt,
    BrokerReceiptState,
    ReceiptAlgorithm,
    assert_receipt_authority,
    authorization_digest,
    authorization_from_mapping,
    canonical_json_bytes,
    receipt_signing_bytes,
    route_digest,
    signed_receipt_from_mapping,
)

FIXTURE = Path(__file__).parent / "fixtures/provider_broker_protocol_vectors.json"


def _vectors() -> dict[str, object]:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def _authorization() -> BrokerAuthorization:
    return authorization_from_mapping(_vectors()["authorization"])


def _receipt() -> BrokerReceipt:
    return signed_receipt_from_mapping(_vectors()["signed_receipt"]).receipt


def test_golden_authorization_and_receipt_vectors_recompute_independently() -> None:
    vectors = _vectors()
    authorization = _authorization()
    signed = signed_receipt_from_mapping(vectors["signed_receipt"])

    assert canonical_json_bytes(authorization).decode() == vectors[
        "authorization_canonical_json"
    ]
    assert route_digest(authorization.route) == vectors["route_digest"]
    assert authorization_digest(authorization) == vectors["authorization_digest"]
    assert receipt_signing_bytes(signed.receipt).decode() == vectors[
        "receipt_signing_json"
    ]
    assert_receipt_authority(signed.receipt, authorization)


def test_mapping_order_cannot_change_canonical_authority() -> None:
    raw = _vectors()["authorization"]
    assert isinstance(raw, dict)
    reversed_raw = dict(reversed(tuple(raw.items())))

    assert authorization_digest(authorization_from_mapping(reversed_raw)) == (
        authorization_digest(_authorization())
    )


def test_package_exports_authorization_parser() -> None:
    assert package_authorization_parser(_vectors()["authorization"]) == _authorization()


def test_direct_constructors_reject_mutable_authority_collections() -> None:
    authorization = _authorization()
    with pytest.raises(ValueError, match="immutable tuple"):
        replace(
            authorization.route,
            billing_units=list(authorization.route.billing_units),  # type: ignore[arg-type]
        )
    with pytest.raises(ValueError, match="immutable tuple"):
        replace(
            authorization,
            bounded_usage=list(authorization.bounded_usage),  # type: ignore[arg-type]
        )


@pytest.mark.parametrize(
    ("path", "value"),
    [
        (("extra",), "forbidden"),
        (("schema_version",), True),
        (("maximum_charge_cents",), True),
        (("operation_digest",), "A" * 64),
        (("currency",), "EUR"),
        (("expires_at",), "2026-07-17T00:00:00+00:00"),
        (("route", "endpoint"), "https://user@provider.example"),
        (("route", "billing_units"), ["output_token", "input_token"]),
        (("bounded_usage", 0, "maximum"), 0),
    ],
)
def test_authorization_parser_rejects_ambiguous_or_substituted_values(
    path: tuple[object, ...], value: object
) -> None:
    raw = json.loads(json.dumps(_vectors()["authorization"]))
    target = raw
    for part in path[:-1]:
        target = target[part]
    target[path[-1]] = value

    with pytest.raises((TypeError, ValueError)):
        authorization_from_mapping(raw)


@pytest.mark.parametrize(
    "endpoint",
    [
        "https://provider.example:abc",
        "https://provider.example\\attacker.example",
        "https://Provider.example",
        "https://provider.example.",
        "https://provider.example/",
        "https://provider.example:443",
        "https://provider.example:0",
        "https://-provider.example",
        "https://127.0.0.1",
        "https://169.254.169.254",
    ],
)
def test_route_rejects_noncanonical_or_malformed_https_origins(endpoint: str) -> None:
    raw = json.loads(json.dumps(_vectors()["authorization"]))
    raw["route"]["endpoint"] = endpoint
    with pytest.raises(ValueError, match="endpoint"):
        authorization_from_mapping(raw)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("audience", "another-service"),
        ("tenant_id", "tenant-2"),
        ("idempotency_key", "op-key-2"),
        ("operation_digest", "d" * 64),
        ("route_digest", "d" * 64),
        ("authorization_digest", "d" * 64),
        ("maximum_charge_cents", 124),
        ("pricing_snapshot", "different-pricing"),
        ("state", "unknown"),
        ("expires_at", "2026-07-17T00:00:01Z"),
        ("nonce", "nonce-2"),
        ("key_id", "broker-key-2"),
        ("algorithm", "hmac-sha256"),
    ],
)
def test_every_receipt_authority_substitution_changes_or_invalidates_signing_payload(
    field: str, value: object
) -> None:
    original = _receipt()
    original_bytes = receipt_signing_bytes(original)
    if field in {"state", "algorithm"}:
        raw = json.loads(json.dumps(_vectors()["signed_receipt"]))
        raw["receipt"][field] = value
        with pytest.raises((TypeError, ValueError)):
            signed_receipt_from_mapping(raw)
        return

    try:
        changed = replace(original, **{field: value})
    except (TypeError, ValueError):
        return
    assert receipt_signing_bytes(changed) != original_bytes


def test_charged_receipt_cannot_exceed_authority_or_omit_evidence_or_output() -> None:
    receipt = _receipt()
    with pytest.raises(ValueError, match="exceeds authority"):
        replace(receipt, charge_cents=receipt.maximum_charge_cents + 1)
    with pytest.raises(ValueError, match="lacks evidence"):
        replace(receipt, evidence_digest=None)
    with pytest.raises(ValueError, match="lacks evidence or output"):
        replace(receipt, output_digest=None)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("tenant_id", "tenant-2"),
        ("idempotency_key", "op-key-2"),
        ("operation_digest", "d" * 64),
        ("route_digest", "d" * 64),
        ("authorization_digest", "d" * 64),
        ("maximum_charge_cents", 124),
        ("pricing_snapshot", "different-pricing"),
        ("not_before", "2026-07-16T17:59:59Z"),
        ("expires_at", "2026-07-17T00:00:01Z"),
    ],
)
def test_receipt_must_match_exact_authorization(field: str, value: object) -> None:
    with pytest.raises(ValueError, match="exact broker authorization"):
        assert_receipt_authority(replace(_receipt(), **{field: value}), _authorization())


def test_authorization_validity_is_canonical_ordered_and_bounded() -> None:
    authorization = _authorization()
    with pytest.raises(ValueError, match="whole-second"):
        replace(authorization, issued_at="2026-07-16T18:00:00.000Z")
    with pytest.raises(ValueError, match="inconsistent"):
        replace(authorization, issued_at=authorization.expires_at)
    with pytest.raises(ValueError, match="maximum lifetime"):
        replace(authorization, expires_at="2026-07-17T18:00:01Z")


def test_nonterminal_state_evidence_contracts_are_closed() -> None:
    receipt = _receipt()
    pre_upstream = replace(
        receipt,
        state=BrokerReceiptState.AUTHORIZED,
        charge_cents=None,
        evidence_digest=None,
        output_digest=None,
    )
    with pytest.raises(ValueError, match="pre-upstream"):
        replace(pre_upstream, evidence_digest="b" * 64)

    upstream_bound = replace(
        receipt,
        state=BrokerReceiptState.UPSTREAM_BOUND,
        charge_cents=None,
        output_digest=None,
    )
    with pytest.raises(ValueError, match="identity evidence"):
        replace(upstream_bound, evidence_digest=None)
    with pytest.raises(ValueError, match="identity evidence"):
        replace(upstream_bound, output_digest="c" * 64)

    unknown = replace(
        receipt,
        state=BrokerReceiptState.UNKNOWN,
        charge_cents=None,
        output_digest=None,
    )
    with pytest.raises(ValueError, match="cannot claim output"):
        replace(unknown, output_digest="c" * 64)


def test_not_found_requires_zero_charge_evidence_and_no_output() -> None:
    receipt = _receipt()
    not_found = replace(
        receipt,
        state=BrokerReceiptState.NOT_FOUND,
        charge_cents=0,
        output_digest=None,
    )
    assert not_found.charge_cents == 0
    with pytest.raises(ValueError, match="integer cents"):
        replace(not_found, charge_cents=None)
    with pytest.raises(ValueError, match="integer cents"):
        replace(not_found, charge_cents=False)
    with pytest.raises(ValueError, match="without output"):
        replace(not_found, output_digest="c" * 64)


def test_receipt_validity_is_canonical_ordered_and_bounded() -> None:
    receipt = _receipt()
    with pytest.raises(ValueError, match="whole-second"):
        replace(receipt, issued_at="2026-07-16T18:00:01.000Z")
    with pytest.raises(ValueError, match="inconsistent"):
        replace(receipt, issued_at=receipt.expires_at)
    with pytest.raises(ValueError, match="maximum lifetime"):
        replace(receipt, expires_at="2026-07-17T18:00:01Z")


@pytest.mark.parametrize(
    "signature",
    ["", "A" * 85, "A" * 87, "+" * 86, "A" * 85 + "="],
)
def test_signed_receipt_rejects_noncanonical_signature(signature: str) -> None:
    raw = json.loads(json.dumps(_vectors()["signed_receipt"]))
    raw["signature"] = signature
    with pytest.raises(ValueError, match="signature"):
        signed_receipt_from_mapping(raw)


def test_signed_receipt_parser_rejects_extra_fields_and_closed_enums() -> None:
    raw = json.loads(json.dumps(_vectors()["signed_receipt"]))
    raw["receipt"]["extra"] = "forbidden"
    with pytest.raises(ValueError, match="field set"):
        signed_receipt_from_mapping(raw)

    raw = json.loads(json.dumps(_vectors()["signed_receipt"]))
    raw["receipt"]["state"] = "invented"
    with pytest.raises(ValueError):
        signed_receipt_from_mapping(raw)

    raw = json.loads(json.dumps(_vectors()["signed_receipt"]))
    raw["receipt"]["schema_version"] = True
    with pytest.raises(ValueError, match="schema"):
        signed_receipt_from_mapping(raw)


def test_protocol_constants_are_closed() -> None:
    receipt = _receipt()
    assert receipt.audience == BROKER_AUDIENCE
    assert receipt.algorithm is ReceiptAlgorithm.ED25519_V1
