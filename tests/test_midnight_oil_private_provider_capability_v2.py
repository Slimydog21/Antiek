from __future__ import annotations

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from pydantic import ValidationError

from substrate.midnight_oil.private_output_compliance import (
    OWNER_PRIVATE_OUTPUT_POLICY_V2_SHA256,
)
from substrate.midnight_oil.private_provider_capability_v2 import (
    PrivateProviderCapabilityV2ReferenceRegistry,
    PrivateProviderProcessingCapabilityV2,
    private_provider_capability_v2_sha256,
    signed_private_provider_capability_v2,
    verify_private_provider_capability_v2,
)
from substrate.midnight_oil.private_provider_composition import (
    signed_private_provider_revocation_head,
)
from substrate.midnight_oil.private_provider_policy import (
    signed_private_provider_revocation_snapshot,
)
from tests.test_midnight_oil_private_provider_policy import (
    _CAPABILITY_PUBLIC_KEY,
    _capability,
)

_V2_SIGNING_KEY = bytes(reversed(range(32)))
_REVOCATION_SIGNING_KEY = bytes(range(32, 64))
_V2_KEY_ID = "private-provider-capability-v2-2026-07"
_REVOCATION_KEY_ID = "private-provider-revocation-2026-07"


def _public_key(private_key: bytes) -> bytes:
    return Ed25519PrivateKey.from_private_bytes(private_key).public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )


_V2_PUBLIC_KEY = _public_key(_V2_SIGNING_KEY)
_REVOCATION_PUBLIC_KEY = _public_key(_REVOCATION_SIGNING_KEY)


def _capability_v2() -> PrivateProviderProcessingCapabilityV2:
    return signed_private_provider_capability_v2(
        route_evidence=_capability(),
        max_output_bytes=500_000,
        revocation_epoch=2,
        issued_at_ms=1_000,
        not_before_ms=1_000,
        expires_at_ms=100_000,
        key_id=_V2_KEY_ID,
        signing_key=_V2_SIGNING_KEY,
    )


def _registry(
    capability: PrivateProviderProcessingCapabilityV2 | None = None,
    *,
    revoked: tuple[str, ...] = (),
    issued_at_ms: int = 1_000,
) -> PrivateProviderCapabilityV2ReferenceRegistry:
    row = capability or _capability_v2()
    snapshot = signed_private_provider_revocation_snapshot(
        epoch=2,
        issued_at_ms=issued_at_ms,
        revoked_capability_sha256s=revoked,
        key_id=_REVOCATION_KEY_ID,
        signing_key=_REVOCATION_SIGNING_KEY,
    )
    head = signed_private_provider_revocation_head(
        snapshot=snapshot,
        previous_head_sha256="f" * 64,
        key_id=_REVOCATION_KEY_ID,
        signing_key=_REVOCATION_SIGNING_KEY,
    )
    return PrivateProviderCapabilityV2ReferenceRegistry(
        (row,),
        capability_v2_verification_keys={_V2_KEY_ID: _V2_PUBLIC_KEY},
        route_evidence_verification_keys={
            "private-provider-capability-2026-07": _CAPABILITY_PUBLIC_KEY
        },
        revocation_verification_keys={_REVOCATION_KEY_ID: _REVOCATION_PUBLIC_KEY},
        trusted_floor_sha256=head.head_sha256,
        current_head_chain=(head,),
    )


def test_capability_v2_is_distinct_signed_and_nonconferring() -> None:
    capability = _capability_v2()
    assert capability.capability_id == "ppcap2_" + capability.capability_sha256[:24]
    assert capability.capability_sha256 == private_provider_capability_v2_sha256(
        capability
    )
    assert capability.output_policy_sha256 == OWNER_PRIVATE_OUTPUT_POLICY_V2_SHA256
    assert capability.allowed_router_roles == (
        "gatherer",
        "planner",
        "synthesizer",
        "verifier",
    )
    assert capability.route_evidence_confers_sink_authority is False
    assert capability.confers_execution_authority is False
    assert capability.production_consumer_enabled is False
    verify_private_provider_capability_v2(
        capability,
        verification_keys={_V2_KEY_ID: _V2_PUBLIC_KEY},
        route_evidence_verification_keys={
            "private-provider-capability-2026-07": _CAPABILITY_PUBLIC_KEY
        },
    )


def test_capability_v2_has_literal_golden_vector() -> None:
    assert _capability_v2().capability_sha256 == (
        "e64aaef828c7782897b8e82ace56c608dadc211f257664e49d488e8b66bf6dd5"
    )


@pytest.mark.parametrize(
    "field",
    (
        "route_evidence_sha256",
        "allowed_router_roles",
        "output_policy_sha256",
        "checker_sha256",
        "source_extractor_sha256",
        "max_output_bytes",
        "key_id",
        "capability_sha256",
    ),
)
def test_capability_v2_identity_mutations_reject(field: str) -> None:
    raw = _capability_v2().model_dump(mode="python")
    original = raw[field]
    if field == "allowed_router_roles":
        raw[field] = ("planner", "gatherer", "synthesizer", "verifier")
    elif field == "max_output_bytes":
        raw[field] = int(original) + 1
    elif field == "key_id":
        raw[field] = "other-key"
    else:
        raw[field] = "0" * 64
    with pytest.raises((ValidationError, ValueError)):
        PrivateProviderProcessingCapabilityV2.model_validate(raw)


def test_capability_v2_signature_and_nested_route_evidence_are_reverified() -> None:
    capability = _capability_v2()
    with pytest.raises(ValueError, match="unavailable"):
        verify_private_provider_capability_v2(
            capability,
            verification_keys={
                _V2_KEY_ID: bytes(reversed(_V2_PUBLIC_KEY))
            },
            route_evidence_verification_keys={
                "private-provider-capability-2026-07": _CAPABILITY_PUBLIC_KEY
            },
        )
    forged_signature = capability.model_copy(update={"signature_ed25519": "0" * 128})
    with pytest.raises(ValueError, match="unavailable"):
        verify_private_provider_capability_v2(
            forged_signature,
            verification_keys={
                _V2_KEY_ID: _V2_PUBLIC_KEY
            },
            route_evidence_verification_keys={
                "private-provider-capability-2026-07": _CAPABILITY_PUBLIC_KEY
            },
        )
    bypassed = capability.model_copy(
        update={
            "route_evidence": capability.route_evidence.model_copy(
                update={"provider_id": "evil"}
            )
        }
    )
    with pytest.raises(ValueError, match="unavailable"):
        verify_private_provider_capability_v2(
            bypassed,
            verification_keys={
                _V2_KEY_ID: _V2_PUBLIC_KEY
            },
            route_evidence_verification_keys={
                "private-provider-capability-2026-07": _CAPABILITY_PUBLIC_KEY
            },
        )


def test_capability_v2_registry_enforces_live_horizon_and_both_revocations() -> None:
    capability = _capability_v2()
    registry = _registry(capability)
    assert registry.require_available(
        capability_sha256=capability.capability_sha256,
        now_ms=2_000,
        required_until_ms=99_999,
    ) == capability
    for now_ms, required_until_ms in ((999, 2_000), (100_000, 100_000), (2_000, 100_000)):
        with pytest.raises(ValueError, match="unavailable"):
            registry.require_available(
                capability_sha256=capability.capability_sha256,
                now_ms=now_ms,
                required_until_ms=required_until_ms,
            )
    for revoked in (
        (capability.capability_sha256,),
        (capability.route_evidence_sha256,),
    ):
        with pytest.raises(ValueError, match="unavailable"):
            _registry(capability, revoked=revoked).require_available(
                capability_sha256=capability.capability_sha256,
                now_ms=2_000,
                required_until_ms=99_999,
            )


def test_capability_v2_registry_rejects_stale_head_wrong_key_and_floor() -> None:
    capability = _capability_v2()
    stale = _registry(capability, issued_at_ms=1_000)
    with pytest.raises(ValueError, match="unavailable"):
        stale.require_available(
            capability_sha256=capability.capability_sha256,
            now_ms=302_001,
            required_until_ms=302_001,
        )
    with pytest.raises(ValueError, match="unavailable"):
        PrivateProviderCapabilityV2ReferenceRegistry(
            (capability,),
            capability_v2_verification_keys={_V2_KEY_ID: _CAPABILITY_PUBLIC_KEY},
            route_evidence_verification_keys={
                "private-provider-capability-2026-07": _CAPABILITY_PUBLIC_KEY
            },
            revocation_verification_keys={},
            trusted_floor_sha256="0" * 64,
            current_head_chain=(),
        )


def test_v1_route_evidence_never_becomes_v2_sink_authority() -> None:
    capability = _capability_v2()
    assert capability.route_evidence.output_policy_sha256 != (
        capability.output_policy_sha256
    )
    assert capability.route_evidence_confers_sink_authority is False
