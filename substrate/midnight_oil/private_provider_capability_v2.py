"""Additive signed capability-v2 authority for 11B-E fixture-only work.

The nested v1 capability is route/handling evidence only.  Its deny-all output
policy is never amended or consumed as sink authority.  The outer v2 signature
uses a distinct domain and directly binds the immutable output policy v2.
"""

from __future__ import annotations

import hashlib
import hmac
import json
from collections.abc import Iterable, Mapping, Sequence
from typing import Literal

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)
from pydantic import BaseModel, ConfigDict, Field, model_validator

from .private_output_compliance import (
    OWNER_PRIVATE_OUTPUT_POLICY_V2_SHA256,
    PRIVATE_OUTPUT_CHECKER_SHA256,
    PRIVATE_OUTPUT_SOURCE_EXTRACTOR_SHA256,
)
from .private_provider_policy import (
    MAX_PRIVATE_PROVIDER_CAPABILITIES,
    MAX_PRIVATE_PROVIDER_REVOCATION_REFERENCE_AGE_MS,
    OWNER_PRIVATE_OUTPUT_SINK_POLICY_SHA256,
    PrivateProviderProcessingCapabilityV1,
    private_provider_capability_sha256,
    verify_private_provider_capability,
)

_CAPABILITY_V2_DOMAIN = b"antiek.midnight-oil.private-provider-capability.v2\x00"
_SIGNATURE_V2_DOMAIN = (
    b"antiek.midnight-oil.private-provider-capability-signature.v2\x00"
)
_HEX64 = r"^[0-9a-f]{64}$"
_ROLES = ("gatherer", "planner", "synthesizer", "verifier")


class _Closed(BaseModel):
    model_config = ConfigDict(
        extra="forbid", strict=True, frozen=True, hide_input_in_errors=True
    )

    def __repr_args__(self) -> list[tuple[str | None, object]]:
        """Keep private authority material out of routine diagnostics."""

        return [("redacted", True)]

    def safe_diagnostic(self) -> dict[str, object]:
        return {"authority_type": type(self).__name__, "redacted": True}


class PrivateProviderProcessingCapabilityV2(_Closed):
    """New signed authority; fixture-only and non-conferring in 11B-E."""

    schema_version: Literal[2] = 2
    capability_id: str = Field(pattern=r"^ppcap2_[0-9a-f]{24}$")
    purpose: Literal["midnight_oil_owner_private_research_v2"] = (
        "midnight_oil_owner_private_research_v2"
    )
    route_evidence_kind: Literal["signed_capability_v1_nonconferring"] = (
        "signed_capability_v1_nonconferring"
    )
    route_evidence: PrivateProviderProcessingCapabilityV1
    route_evidence_sha256: str = Field(pattern=_HEX64)
    allowed_router_roles: tuple[
        Literal["gatherer", "planner", "synthesizer", "verifier"], ...
    ] = Field(min_length=4, max_length=4)
    planner_source_rule: Literal["exactly_zero_publication_sources"] = (
        "exactly_zero_publication_sources"
    )
    non_planner_source_rule: Literal["one_to_eight_receipt_v5_sources"] = (
        "one_to_eight_receipt_v5_sources"
    )
    output_policy_sha256: str = Field(pattern=_HEX64)
    checker_sha256: str = Field(pattern=_HEX64)
    source_extractor_sha256: str = Field(pattern=_HEX64)
    max_output_bytes: int = Field(ge=1, le=1_000_000)
    revocation_registry_id: Literal["antiek-private-provider-revocations-v1"] = (
        "antiek-private-provider-revocations-v1"
    )
    revocation_epoch: int = Field(ge=0)
    issued_at_ms: int = Field(ge=0)
    not_before_ms: int = Field(ge=0)
    expires_at_ms: int = Field(gt=0)
    key_id: str = Field(pattern=r"^[A-Za-z0-9._-]{1,128}$")
    issuer_role: Literal["private_provider_capability_issuer"] = (
        "private_provider_capability_issuer"
    )
    key_purpose: Literal["owner_private_provider_capability_v2"] = (
        "owner_private_provider_capability_v2"
    )
    signature_scheme: Literal["ed25519"] = "ed25519"
    capability_sha256: str = Field(pattern=_HEX64)
    signature_ed25519: str = Field(pattern=r"^[0-9a-f]{128}$")
    route_evidence_confers_sink_authority: Literal[False] = False
    confers_execution_authority: Literal[False] = False
    live_reverification_required: Literal[True] = True
    production_consumer_enabled: Literal[False] = False

    @model_validator(mode="after")
    def _canonical(self) -> PrivateProviderProcessingCapabilityV2:
        evidence = self.route_evidence
        if (
            self.route_evidence_sha256
            != private_provider_capability_sha256(evidence)
            or self.route_evidence_sha256 != evidence.capability_sha256
            or evidence.output_policy_sha256
            != OWNER_PRIVATE_OUTPUT_SINK_POLICY_SHA256
            or self.allowed_router_roles != _ROLES
            or self.output_policy_sha256 != OWNER_PRIVATE_OUTPUT_POLICY_V2_SHA256
            or self.checker_sha256 != PRIVATE_OUTPUT_CHECKER_SHA256
            or self.source_extractor_sha256
            != PRIVATE_OUTPUT_SOURCE_EXTRACTOR_SHA256
            or self.max_output_bytes > min(evidence.max_output_bytes, 1_000_000)
            or self.revocation_epoch < evidence.revocation_epoch
            or not (
                evidence.not_before_ms
                <= self.issued_at_ms
                <= self.not_before_ms
                < self.expires_at_ms
                <= evidence.expires_at_ms
            )
        ):
            raise ValueError("private provider capability v2 contract conflicts")
        digest = private_provider_capability_v2_sha256(self)
        if self.capability_sha256 != digest or self.capability_id != "ppcap2_" + digest[:24]:
            raise ValueError("private provider capability v2 identity conflicts")
        return self


def _canonical_material(
    capability: PrivateProviderProcessingCapabilityV2 | Mapping[str, object],
) -> bytes:
    raw = (
        capability.model_dump(mode="json")
        if isinstance(capability, BaseModel)
        else dict(capability)
    )
    material = {
        key: value
        for key, value in raw.items()
        if key not in {"capability_id", "capability_sha256", "signature_ed25519"}
    }
    return json.dumps(
        material, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")


def private_provider_capability_v2_sha256(
    capability: PrivateProviderProcessingCapabilityV2 | Mapping[str, object],
) -> str:
    return hashlib.sha256(_CAPABILITY_V2_DOMAIN + _canonical_material(capability)).hexdigest()


def private_provider_capability_v2_signature(
    capability_sha256: str, *, signing_key: bytes
) -> str:
    if len(signing_key) != 32:
        raise ValueError("private provider v2 Ed25519 signing key must be 32 bytes")
    return Ed25519PrivateKey.from_private_bytes(signing_key).sign(
        _SIGNATURE_V2_DOMAIN + capability_sha256.encode("ascii")
    ).hex()


def signed_private_provider_capability_v2(
    *,
    route_evidence: PrivateProviderProcessingCapabilityV1,
    max_output_bytes: int,
    revocation_epoch: int,
    issued_at_ms: int,
    not_before_ms: int,
    expires_at_ms: int,
    key_id: str,
    signing_key: bytes,
) -> PrivateProviderProcessingCapabilityV2:
    route_material = route_evidence.model_dump(mode="json")
    route_material["allowed_router_roles"] = tuple(
        route_material["allowed_router_roles"]
    )
    material: dict[str, object] = {
        "schema_version": 2,
        "purpose": "midnight_oil_owner_private_research_v2",
        "route_evidence_kind": "signed_capability_v1_nonconferring",
        "route_evidence": route_material,
        "route_evidence_sha256": route_evidence.capability_sha256,
        "allowed_router_roles": _ROLES,
        "planner_source_rule": "exactly_zero_publication_sources",
        "non_planner_source_rule": "one_to_eight_receipt_v5_sources",
        "output_policy_sha256": OWNER_PRIVATE_OUTPUT_POLICY_V2_SHA256,
        "checker_sha256": PRIVATE_OUTPUT_CHECKER_SHA256,
        "source_extractor_sha256": PRIVATE_OUTPUT_SOURCE_EXTRACTOR_SHA256,
        "max_output_bytes": max_output_bytes,
        "revocation_registry_id": "antiek-private-provider-revocations-v1",
        "revocation_epoch": revocation_epoch,
        "issued_at_ms": issued_at_ms,
        "not_before_ms": not_before_ms,
        "expires_at_ms": expires_at_ms,
        "key_id": key_id,
        "issuer_role": "private_provider_capability_issuer",
        "key_purpose": "owner_private_provider_capability_v2",
        "signature_scheme": "ed25519",
        "route_evidence_confers_sink_authority": False,
        "confers_execution_authority": False,
        "live_reverification_required": True,
        "production_consumer_enabled": False,
    }
    digest = private_provider_capability_v2_sha256(material)
    return PrivateProviderProcessingCapabilityV2.model_validate(
        {
            **material,
            "capability_id": "ppcap2_" + digest[:24],
            "capability_sha256": digest,
            "signature_ed25519": private_provider_capability_v2_signature(
                digest, signing_key=signing_key
            ),
        }
    )


def verify_private_provider_capability_v2(
    capability: PrivateProviderProcessingCapabilityV2,
    *,
    verification_keys: Mapping[str, bytes],
    route_evidence_verification_keys: Mapping[str, bytes],
) -> None:
    key = verification_keys.get(capability.key_id)
    if key is None or len(key) != 32:
        raise ValueError("private provider capability v2 is unavailable")
    try:
        verify_private_provider_capability(
            capability.route_evidence,
            verification_keys=route_evidence_verification_keys,
        )
        if (
            private_provider_capability_v2_sha256(capability)
            != capability.capability_sha256
        ):
            raise ValueError("private provider capability v2 is unavailable")
        Ed25519PublicKey.from_public_bytes(key).verify(
            bytes.fromhex(capability.signature_ed25519),
            _SIGNATURE_V2_DOMAIN + capability.capability_sha256.encode("ascii"),
        )
    except (InvalidSignature, ValueError):
        raise ValueError("private provider capability v2 is unavailable") from None


class PrivateProviderCapabilityV2ReferenceRegistry:
    """Pure verified matcher over one rollback-floored signed head chain.

    This object does not load durable state and confers no execution authority.
    A caller must reconstruct it from the durable store's current chain for each
    transition; receipts can only consume rows returned by this matcher.
    """

    def __init__(
        self,
        capabilities: Iterable[PrivateProviderProcessingCapabilityV2],
        *,
        capability_v2_verification_keys: Mapping[str, bytes],
        route_evidence_verification_keys: Mapping[str, bytes],
        revocation_verification_keys: Mapping[str, bytes],
        trusted_floor_sha256: str,
        current_head_chain: Sequence[object],
    ) -> None:
        # Imported locally to keep the foundational composition module free of a
        # reverse dependency on this additive, fixture-only authority lane.
        from .private_provider_composition import (
            PrivateProviderRevocationHeadV1,
            verify_private_provider_revocation_head,
        )

        rows = tuple(capabilities)
        heads = tuple(current_head_chain)
        if len(rows) > MAX_PRIVATE_PROVIDER_CAPABILITIES or not heads:
            raise ValueError("private provider capability v2 registry is unavailable")
        if any(not isinstance(head, PrivateProviderRevocationHeadV1) for head in heads):
            raise ValueError("private provider capability v2 registry is unavailable")
        typed_heads = tuple(head for head in heads if isinstance(head, PrivateProviderRevocationHeadV1))
        if not hmac.compare_digest(typed_heads[0].head_sha256, trusted_floor_sha256):
            raise ValueError("private provider capability v2 trusted floor conflicts")
        for head in typed_heads:
            verify_private_provider_revocation_head(
                head, verification_keys=revocation_verification_keys
            )
        for previous, current in zip(typed_heads, typed_heads[1:], strict=False):
            if (
                current.registry_id != previous.registry_id
                or current.previous_head_sha256 != previous.head_sha256
                or current.epoch != previous.epoch + 1
                or current.issued_at_ms <= previous.issued_at_ms
                or not set(previous.snapshot.revoked_capability_sha256s).issubset(
                    current.snapshot.revoked_capability_sha256s
                )
            ):
                raise ValueError("private provider capability v2 head chain conflicts")
        current = typed_heads[-1]
        by_hash: dict[str, PrivateProviderProcessingCapabilityV2] = {}
        for row in rows:
            verify_private_provider_capability_v2(
                row,
                verification_keys=capability_v2_verification_keys,
                route_evidence_verification_keys=route_evidence_verification_keys,
            )
            if (
                row.revocation_registry_id != current.registry_id
                or row.revocation_epoch > current.epoch
                or row.capability_sha256 in by_hash
            ):
                raise ValueError("private provider capability v2 registry conflicts")
            by_hash[row.capability_sha256] = row
        self._by_hash = by_hash
        self._revoked = frozenset(current.snapshot.revoked_capability_sha256s)
        self._head_issued_at_ms = current.issued_at_ms
        self.current_head_sha256 = current.head_sha256
        self.trusted_floor_sha256 = trusted_floor_sha256

    def require_available(
        self,
        *,
        capability_sha256: str,
        now_ms: int,
        required_until_ms: int,
    ) -> PrivateProviderProcessingCapabilityV2:
        row = self._by_hash.get(capability_sha256)
        if (
            row is None
            or capability_sha256 in self._revoked
            or row.route_evidence_sha256 in self._revoked
            or type(now_ms) is not int
            or isinstance(now_ms, bool)
            or self._head_issued_at_ms > now_ms
            or now_ms - self._head_issued_at_ms
            > MAX_PRIVATE_PROVIDER_REVOCATION_REFERENCE_AGE_MS
            or type(required_until_ms) is not int
            or isinstance(required_until_ms, bool)
            or now_ms < row.not_before_ms
            or now_ms >= row.expires_at_ms
            or required_until_ms < now_ms
            or required_until_ms >= row.expires_at_ms
        ):
            raise ValueError("private provider capability v2 is unavailable")
        return row


__all__ = [
    "PrivateProviderCapabilityV2ReferenceRegistry",
    "PrivateProviderProcessingCapabilityV2",
    "private_provider_capability_v2_sha256",
    "private_provider_capability_v2_signature",
    "signed_private_provider_capability_v2",
    "verify_private_provider_capability_v2",
]
