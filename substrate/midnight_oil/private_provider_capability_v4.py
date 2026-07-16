"""Signed, owner-bound, non-conferring Cycle-35 CapabilityV4."""

from __future__ import annotations

import hashlib
import hmac
import json
from collections.abc import Mapping
from typing import Literal

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from pydantic import BaseModel, ConfigDict, Field, model_validator

from .private_output_policy_v4 import (
    _CONTRACT_DOMAINS,
    OWNER_PRIVATE_OUTPUT_POLICY_V4_SHA256,
    PRIVATE_CYCLE_35_CONTRACT_SHA256,
    parse_cycle_35_canonical_document,
)

_CAPABILITY_V4_DOMAIN = _CONTRACT_DOMAINS["capability_v4"].encode("utf-8")
_SIGNATURE_V4_DOMAIN = _CONTRACT_DOMAINS["capability_signature_v4"].encode("utf-8")
_HEX64 = r"^[0-9a-f]{64}$"
_MAX_I63 = 2**63 - 1
_OUTPUT_SCHEMA_BY_ROLE = {
    "gatherer": "midnight-oil.gather-output/v1",
    "planner": "midnight-oil.planner-output/v1",
    "synthesizer": "midnight-oil.synthesizer-output/v1",
    "verifier": "midnight-oil.verifier-output/v1",
}


def _canonical_value(value: object) -> object:
    if isinstance(value, bytes):
        return value.hex()
    if isinstance(value, dict):
        return {key: _canonical_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_canonical_value(item) for item in value]
    return value


def _canonical_json(value: object) -> bytes:
    return json.dumps(
        _canonical_value(value),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


class _Closed(BaseModel):
    model_config = ConfigDict(
        extra="forbid", strict=True, frozen=True, hide_input_in_errors=True
    )

    def __repr_args__(self) -> list[tuple[str | None, object]]:
        return [("redacted", True)]


class PrivateProviderProcessingCapabilityV4(_Closed):
    schema_version: Literal[4] = 4
    capability_id: str = Field(pattern=r"^ppcap4_[0-9a-f]{24}$")
    purpose: Literal["midnight_oil_owner_private_paid_research_v4"] = (
        "midnight_oil_owner_private_paid_research_v4"
    )
    owner_path_discriminator: str = Field(pattern=r"^opspd1_[0-9a-f]{64}$")
    provider_id: str = Field(pattern=r"^[A-Za-z0-9._-]{1,128}$")
    model_id: str = Field(pattern=r"^[A-Za-z0-9._:/-]{1,256}$")
    route_key: str = Field(min_length=3, max_length=385)
    api_mode: Literal["responses_no_store", "messages_no_store"]
    processing_region: str = Field(pattern=r"^[A-Za-z0-9._-]{1,64}$")
    output_schema: Literal[
        "midnight-oil.gather-output/v1",
        "midnight-oil.planner-output/v1",
        "midnight-oil.synthesizer-output/v1",
        "midnight-oil.verifier-output/v1",
    ]
    router_role: Literal["gatherer", "planner", "synthesizer", "verifier"]
    account_scope_blind_id: bytes = Field(min_length=32, max_length=32, repr=False)
    project_scope_blind_id: bytes = Field(min_length=32, max_length=32, repr=False)
    output_policy_v4_sha256: str = Field(pattern=_HEX64)
    cycle_35_contract_sha256: str = Field(pattern=_HEX64)
    revocation_registry_id: str = Field(min_length=1, max_length=128)
    revocation_trusted_floor_sha256: str = Field(pattern=_HEX64)
    approved_max_cents: int = Field(ge=1, le=1_000_000_000)
    max_private_input_bytes: int = Field(ge=1, le=32_000)
    max_output_bytes: int = Field(ge=1, le=1_000_000)
    issued_at_ms: int = Field(ge=0, le=_MAX_I63)
    not_before_ms: int = Field(ge=0, le=_MAX_I63)
    expires_at_ms: int = Field(ge=1, le=_MAX_I63)
    key_id: str = Field(pattern=r"^[A-Za-z0-9._-]{1,128}$")
    issuer_role: Literal["private_provider_capability_issuer"] = (
        "private_provider_capability_issuer"
    )
    key_purpose: Literal["owner_private_provider_capability_v4"] = (
        "owner_private_provider_capability_v4"
    )
    signature_scheme: Literal["ed25519"] = "ed25519"
    capability_sha256: str = Field(pattern=_HEX64)
    signature_ed25519: str = Field(pattern=r"^[0-9a-f]{128}$", repr=False)
    synthetic_fixture_eligibility_only: Literal[True] = True
    live_migration_verified: Literal[False] = False
    user_accounting_effect: Literal[False] = False
    transport_reachable: Literal[False] = False
    confers_execution_authority: Literal[False] = False
    confers_checkpoint_authority: Literal[False] = False
    confers_sink_authority: Literal[False] = False
    confers_transition_authority: Literal[False] = False
    production_consumer_enabled: Literal[False] = False

    @model_validator(mode="after")
    def _canonical(self) -> PrivateProviderProcessingCapabilityV4:
        digest = private_provider_capability_v4_sha256(self)
        if (
            self.route_key != f"{self.provider_id}/{self.model_id}"
            or self.output_schema != _OUTPUT_SCHEMA_BY_ROLE[self.router_role]
            or self.output_policy_v4_sha256 != OWNER_PRIVATE_OUTPUT_POLICY_V4_SHA256
            or self.cycle_35_contract_sha256 != PRIVATE_CYCLE_35_CONTRACT_SHA256
            or not (self.issued_at_ms <= self.not_before_ms < self.expires_at_ms)
            or not hmac.compare_digest(self.capability_sha256, digest)
            or self.capability_id != "ppcap4_" + digest[:24]
        ):
            raise ValueError("private provider capability v4 contract conflicts")
        return self


def _capability_material(
    capability: PrivateProviderProcessingCapabilityV4 | Mapping[str, object],
) -> dict[str, object]:
    raw = (
        capability.model_dump(mode="python")
        if isinstance(capability, BaseModel)
        else dict(capability)
    )
    return {
        key: value
        for key, value in raw.items()
        if key not in {"capability_id", "capability_sha256", "signature_ed25519"}
    }


def private_provider_capability_v4_sha256(
    capability: PrivateProviderProcessingCapabilityV4 | Mapping[str, object],
) -> str:
    return hashlib.sha256(
        _CAPABILITY_V4_DOMAIN + _canonical_json(_capability_material(capability))
    ).hexdigest()


def verify_private_provider_capability_v4(
    capability: PrivateProviderProcessingCapabilityV4,
    *,
    verification_keys: Mapping[str, bytes],
) -> None:
    try:
        if type(capability) is not PrivateProviderProcessingCapabilityV4:
            raise ValueError
        validated = PrivateProviderProcessingCapabilityV4.model_validate(
            capability.model_dump(mode="python")
        )
        digest = private_provider_capability_v4_sha256(validated)
        key = verification_keys.get(validated.key_id)
        if (
            not hmac.compare_digest(digest, validated.capability_sha256)
            or type(key) is not bytes
            or len(key) != 32
        ):
            raise ValueError
        Ed25519PublicKey.from_public_bytes(key).verify(
            bytes.fromhex(validated.signature_ed25519),
            _SIGNATURE_V4_DOMAIN + bytes.fromhex(digest),
        )
    except Exception:
        raise ValueError("private provider capability v4 is unavailable") from None


def parse_private_provider_capability_v4_document(
    document: bytes,
    *,
    verification_keys: Mapping[str, bytes],
) -> PrivateProviderProcessingCapabilityV4:
    """Parse one exact canonical wire document with explicit blind-byte decoding."""
    try:
        raw = parse_cycle_35_canonical_document(document)
        if type(raw) is not dict:
            raise ValueError
        material = dict(raw)
        for field in ("account_scope_blind_id", "project_scope_blind_id"):
            value = material.get(field)
            if type(value) is not str or len(value) != 64:
                raise ValueError
            decoded = bytes.fromhex(value)
            if value != decoded.hex():
                raise ValueError
            material[field] = decoded
        capability = PrivateProviderProcessingCapabilityV4.model_validate(material)
        verify_private_provider_capability_v4(
            capability, verification_keys=verification_keys
        )
        return capability
    except (TypeError, ValueError):
        raise ValueError("private provider capability v4 is unavailable") from None


__all__ = [
    "PrivateProviderProcessingCapabilityV4",
    "private_provider_capability_v4_sha256",
    "parse_private_provider_capability_v4_document",
    "verify_private_provider_capability_v4",
]
