from __future__ import annotations

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from pydantic import ValidationError

from substrate.midnight_oil.private_provider_capability_v2 import (
    PrivateProviderCapabilityV2ReferenceRegistry,
    PrivateProviderProcessingCapabilityV2,
    signed_private_provider_capability_v2,
)
from substrate.midnight_oil.private_provider_composition import (
    signed_private_provider_revocation_head,
)
from substrate.midnight_oil.private_provider_policy import (
    signed_private_provider_revocation_snapshot,
)
from substrate.midnight_oil.private_provider_receipt_v5 import (
    OwnerPrivatePublicationSourceReceiptV5,
    build_owner_private_source_receipt_v5,
    owner_private_source_receipt_v5_sha256,
)
from substrate.midnight_oil.private_provider_request_core_v2 import (
    build_owner_private_request_core_v2,
)
from tests.test_midnight_oil_private_dispatch_boundary import (
    _prepare,
    _private_capability,
)
from tests.test_midnight_oil_private_provider_authority import (
    _CAP_KEY_ID,
    _CAP_PRIVATE,
    _REV_KEY_ID,
    _REV_PRIVATE,
)

_V2_PRIVATE = bytes(value ^ 0x55 for value in range(32))
_V2_KEY_ID = "private-capability-v2-issuer"


def _public(private: bytes) -> bytes:
    return Ed25519PrivateKey.from_private_bytes(private).public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )


def _matching_capability_v2() -> PrivateProviderProcessingCapabilityV2:
    return signed_private_provider_capability_v2(
        route_evidence=_private_capability(),
        max_output_bytes=500_000,
        revocation_epoch=2,
        issued_at_ms=1_000,
        not_before_ms=1_000,
        expires_at_ms=100_000,
        key_id=_V2_KEY_ID,
        signing_key=_V2_PRIVATE,
    )


def _registry(
    capability: PrivateProviderProcessingCapabilityV2 | None = None,
    *,
    revoked: tuple[str, ...] = (),
) -> PrivateProviderCapabilityV2ReferenceRegistry:
    row = capability or _matching_capability_v2()
    snapshot = signed_private_provider_revocation_snapshot(
        epoch=2,
        issued_at_ms=2_000,
        revoked_capability_sha256s=revoked,
        key_id=_REV_KEY_ID,
        signing_key=_REV_PRIVATE,
    )
    head = signed_private_provider_revocation_head(
        snapshot=snapshot,
        previous_head_sha256="f" * 64,
        key_id=_REV_KEY_ID,
        signing_key=_REV_PRIVATE,
    )
    return PrivateProviderCapabilityV2ReferenceRegistry(
        (row,),
        capability_v2_verification_keys={_V2_KEY_ID: _public(_V2_PRIVATE)},
        route_evidence_verification_keys={_CAP_KEY_ID: _public(_CAP_PRIVATE)},
        revocation_verification_keys={_REV_KEY_ID: _public(_REV_PRIVATE)},
        trusted_floor_sha256=head.head_sha256,
        current_head_chain=(head,),
    )


def _receipt_v5() -> OwnerPrivatePublicationSourceReceiptV5:
    prepared, _composition = _prepare()
    capability = _matching_capability_v2()
    registry = _registry(capability)
    core = build_owner_private_request_core_v2(
        prepared_v1=prepared,
        capability_sha256=capability.capability_sha256,
        registry=registry,
        now_ms=2_002,
    )
    return build_owner_private_source_receipt_v5(
        source=prepared.source_receipts[0],
        request_core=core,
        capability_sha256=capability.capability_sha256,
        registry=registry,
        now_ms=2_002,
    )


def test_receipt_v5_is_distinct_content_addressed_and_nonconferring() -> None:
    receipt = _receipt_v5()
    assert receipt.receipt_id == "opsr5_" + receipt.receipt_sha256[:24]
    assert receipt.receipt_sha256 == owner_private_source_receipt_v5_sha256(receipt)
    assert receipt.source_authority_v4.receipt_id.startswith("opsr4_")
    assert receipt.source_authority_confers_sink_authority is False
    assert receipt.confers_execution_authority is False


def test_receipt_v5_has_literal_golden_vector() -> None:
    assert _receipt_v5().receipt_sha256 == (
        "0b342003db2d624c1beb3c839a6dd83e669246fe78d1c8e37ebf7811a34e59b4"
    )


@pytest.mark.parametrize(
    "field",
    (
        "owner_scope_sha256",
        "operation_id",
        "stage_key",
        "router_role",
        "source_evidence_v1_request_sha256",
        "request_core_v2_sha256",
        "private_source_ordinal",
        "collective_unit_id",
        "source_authority_v4_sha256",
        "provider_capability_v2_sha256",
        "output_policy_v2_sha256",
        "checker_sha256",
        "source_extractor_sha256",
        "receipt_sha256",
    ),
)
def test_receipt_v5_identity_mutations_reject(field: str) -> None:
    raw = _receipt_v5().model_dump(mode="python")
    original = raw[field]
    if field == "private_source_ordinal":
        raw[field] = 2
    elif isinstance(original, str) and len(original) == 64:
        raw[field] = "0" * 64
    else:
        raw[field] = "changed"
    with pytest.raises((ValidationError, ValueError)):
        OwnerPrivatePublicationSourceReceiptV5.model_validate(raw)


def test_altered_route_evidence_cannot_enter_receipt_builder() -> None:
    capability = _matching_capability_v2().model_copy(
        update={"route_evidence_sha256": "0" * 64}
    )
    with pytest.raises(ValueError, match="unavailable"):
        _registry(capability)


def test_receipt_v5_builder_rejects_forged_or_revoked_capability() -> None:
    prepared, _composition = _prepare()
    capability = _matching_capability_v2()
    forged = capability.model_copy(update={"signature_ed25519": "0" * 128})
    with pytest.raises(ValueError, match="unavailable"):
        _registry(forged)
    valid_registry = _registry(capability)
    core = build_owner_private_request_core_v2(
        prepared_v1=prepared,
        capability_sha256=capability.capability_sha256,
        registry=valid_registry,
        now_ms=2_002,
    )
    with pytest.raises(ValueError, match="unavailable"):
        build_owner_private_source_receipt_v5(
            source=prepared.source_receipts[0],
            request_core=core,
            capability_sha256=capability.capability_sha256,
            registry=_registry(capability, revoked=(capability.capability_sha256,)),
            now_ms=2_002,
        )


def test_v2_v5_routine_representations_are_redacted() -> None:
    capability = _matching_capability_v2()
    receipt = _receipt_v5()
    for value in (capability, receipt):
        rendered = repr(value)
        assert "redacted=True" in rendered
        assert value.safe_diagnostic()["redacted"] is True
        assert "operation_id" not in rendered
