"""Acyclic, content-addressed, non-conferring Cycle-35 request CoreV4."""

from __future__ import annotations

import hashlib
import hmac
import json
from collections.abc import Mapping, Sequence
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .private_output_policy_v4 import (
    _CONTRACT_DOMAINS,
    OWNER_PRIVATE_OUTPUT_POLICY_V4_SHA256,
    PRIVATE_CYCLE_35_CONTRACT_SHA256,
)
from .private_provider_capability_v4 import (
    PrivateProviderProcessingCapabilityV4,
    verify_private_provider_capability_v4,
)

_REQUEST_CORE_V4_DOMAIN = _CONTRACT_DOMAINS["request_core_v4"].encode("utf-8")
_PRIVATE_INPUT_COMMITMENT_V4_DOMAIN = (
    b"antiek.midnight-oil.owner-private-input-commitment.v4\x00"
)
_IDEMPOTENCY_V4_DOMAIN = b"antiek.midnight-oil.provider-scoped-idempotency.v4\x00"
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
    if isinstance(value, BaseModel):
        return _canonical_value(value.model_dump(mode="python"))
    if isinstance(value, dict):
        return {key: _canonical_value(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
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


class Cycle32SourceReceiptPairV1(_Closed):
    ordinal: int = Field(ge=1, le=8)
    receipt_id: str = Field(pattern=r"^opsr5_[0-9a-f]{24}$")
    receipt_sha256: str = Field(pattern=_HEX64)
    private_input_member_sha256: str = Field(pattern=_HEX64)
    private_input_member_bytes: int = Field(ge=1, le=32_000)

    @model_validator(mode="after")
    def _content_addressed(self) -> Cycle32SourceReceiptPairV1:
        if self.receipt_id != "opsr5_" + self.receipt_sha256[:24]:
            raise ValueError("Cycle 32 source receipt pair conflicts")
        return self


class PreparedOwnerPrivateRequestCoreV4(_Closed):
    schema_version: Literal[4] = 4
    request_core_id: str = Field(pattern=r"^oprc4_[0-9a-f]{24}$")
    request_core_sha256: str = Field(pattern=_HEX64)
    owner_path_discriminator: str = Field(pattern=r"^opspd1_[0-9a-f]{64}$")
    operation_id: str = Field(min_length=1, max_length=256)
    job_id: str = Field(min_length=1, max_length=256)
    execution_id: str = Field(min_length=1, max_length=256)
    stage_key: str = Field(pattern=_HEX64)
    router_role: Literal["gatherer", "planner", "synthesizer", "verifier"]
    output_schema: Literal[
        "midnight-oil.gather-output/v1",
        "midnight-oil.planner-output/v1",
        "midnight-oil.synthesizer-output/v1",
        "midnight-oil.verifier-output/v1",
    ]
    capability_id: str = Field(pattern=r"^ppcap4_[0-9a-f]{24}$")
    capability_v4_sha256: str = Field(pattern=_HEX64)
    output_policy_v4_sha256: str = Field(pattern=_HEX64)
    cycle_35_contract_sha256: str = Field(pattern=_HEX64)
    provider_id: str = Field(pattern=r"^[A-Za-z0-9._-]{1,128}$")
    model_id: str = Field(pattern=r"^[A-Za-z0-9._:/-]{1,256}$")
    route_key: str = Field(min_length=3, max_length=385)
    api_mode: Literal["responses_no_store", "messages_no_store"]
    processing_region: str = Field(pattern=r"^[A-Za-z0-9._-]{1,64}$")
    account_scope_blind_id: bytes = Field(min_length=32, max_length=32, repr=False)
    project_scope_blind_id: bytes = Field(min_length=32, max_length=32, repr=False)
    provider_request_bytes: bytes = Field(
        min_length=1, max_length=10_000_000, repr=False
    )
    provider_request_sha256: str = Field(pattern=_HEX64)
    provider_request_bytes_count: int = Field(ge=1, le=10_000_000)
    private_input_commitment_sha256: str = Field(pattern=_HEX64)
    private_input_bytes: int = Field(ge=0, le=32_000)
    source_registry_id: str = Field(min_length=1, max_length=128)
    source_head_sha256: str = Field(pattern=_HEX64)
    source_epoch: int = Field(ge=0, le=_MAX_I63)
    opaque_source_bundle_id: str = Field(min_length=1, max_length=128)
    source_row_version: Literal[1] = 1
    source_selector: str = Field(min_length=1, max_length=256)
    source_receipt_pairs: tuple[Cycle32SourceReceiptPairV1, ...] = Field(
        max_length=8, repr=False
    )
    required_until_ms: int = Field(ge=1, le=_MAX_I63)
    projected_max_cents: int = Field(ge=1, le=1_000_000_000)
    max_output_bytes: int = Field(ge=1, le=1_000_000)
    provider_scoped_idempotency_sha256: str = Field(pattern=_HEX64)
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
    def _canonical(self) -> PreparedOwnerPrivateRequestCoreV4:
        pairs = self.source_receipt_pairs
        expected = tuple(range(1, len(pairs) + 1))
        planner = self.router_role == "planner"
        digest = owner_private_request_core_v4_sha256(self)
        if (
            self.output_schema != _OUTPUT_SCHEMA_BY_ROLE[self.router_role]
            or self.route_key != f"{self.provider_id}/{self.model_id}"
            or self.output_policy_v4_sha256 != OWNER_PRIVATE_OUTPUT_POLICY_V4_SHA256
            or self.cycle_35_contract_sha256 != PRIVATE_CYCLE_35_CONTRACT_SHA256
            or self.provider_request_sha256
            != hashlib.sha256(self.provider_request_bytes).hexdigest()
            or self.provider_request_bytes_count != len(self.provider_request_bytes)
            or tuple(pair.ordinal for pair in pairs) != expected
            or len({pair.receipt_id for pair in pairs}) != len(pairs)
            or len({pair.receipt_sha256 for pair in pairs}) != len(pairs)
            or planner != (len(pairs) == 0)
            or (not planner and not pairs)
            or self.private_input_bytes
            != sum(pair.private_input_member_bytes for pair in pairs)
            or self.private_input_commitment_sha256
            != private_input_commitment_v4_sha256(pairs)
            or self.provider_scoped_idempotency_sha256
            != provider_scoped_idempotency_v4_sha256(self)
            or not hmac.compare_digest(self.request_core_sha256, digest)
            or self.request_core_id != "oprc4_" + digest[:24]
        ):
            raise ValueError("owner-private request core v4 contract conflicts")
        return self


def private_input_commitment_v4_sha256(
    pairs: tuple[Cycle32SourceReceiptPairV1, ...],
) -> str:
    if type(pairs) is not tuple or len(pairs) > 8:
        raise ValueError("owner-private input commitment v4 is unavailable")
    material = tuple(
        {
            "ordinal": pair.ordinal,
            "private_input_member_bytes": pair.private_input_member_bytes,
            "private_input_member_sha256": pair.private_input_member_sha256,
            "receipt_id": pair.receipt_id,
            "receipt_sha256": pair.receipt_sha256,
        }
        for pair in pairs
    )
    return hashlib.sha256(
        _PRIVATE_INPUT_COMMITMENT_V4_DOMAIN + _canonical_json(material)
    ).hexdigest()


def _core_material(
    core: PreparedOwnerPrivateRequestCoreV4 | Mapping[str, object],
    *,
    exclude_idempotency: bool = False,
) -> dict[str, object]:
    raw = core.model_dump(mode="python") if isinstance(core, BaseModel) else dict(core)
    excluded = {"request_core_id", "request_core_sha256"}
    if exclude_idempotency:
        excluded.add("provider_scoped_idempotency_sha256")
    return {key: value for key, value in raw.items() if key not in excluded}


def provider_scoped_idempotency_v4_sha256(
    core: PreparedOwnerPrivateRequestCoreV4 | Mapping[str, object],
) -> str:
    material = _core_material(core, exclude_idempotency=True)
    material["attempt_ordinal"] = 1
    return hashlib.sha256(
        _IDEMPOTENCY_V4_DOMAIN + _canonical_json(material)
    ).hexdigest()


def owner_private_request_core_v4_sha256(
    core: PreparedOwnerPrivateRequestCoreV4 | Mapping[str, object],
) -> str:
    return hashlib.sha256(
        _REQUEST_CORE_V4_DOMAIN + _canonical_json(_core_material(core))
    ).hexdigest()


def verify_owner_private_request_core_v4(
    core: PreparedOwnerPrivateRequestCoreV4,
    *,
    capability: PrivateProviderProcessingCapabilityV4,
    capability_verification_keys: Mapping[str, bytes],
) -> None:
    """Join an internally canonical non-conferring core to signed capability authority."""
    try:
        if (
            type(core) is not PreparedOwnerPrivateRequestCoreV4
            or type(capability) is not PrivateProviderProcessingCapabilityV4
        ):
            raise ValueError
        validated = PreparedOwnerPrivateRequestCoreV4.model_validate(
            core.model_dump(mode="python")
        )
        verify_private_provider_capability_v4(
            capability, verification_keys=capability_verification_keys
        )
        direct = (
            validated.owner_path_discriminator,
            validated.capability_id,
            validated.capability_v4_sha256,
            validated.output_policy_v4_sha256,
            validated.cycle_35_contract_sha256,
            validated.provider_id,
            validated.model_id,
            validated.route_key,
            validated.api_mode,
            validated.processing_region,
            validated.output_schema,
            validated.router_role,
            validated.account_scope_blind_id,
            validated.project_scope_blind_id,
        )
        signed = (
            capability.owner_path_discriminator,
            capability.capability_id,
            capability.capability_sha256,
            capability.output_policy_v4_sha256,
            capability.cycle_35_contract_sha256,
            capability.provider_id,
            capability.model_id,
            capability.route_key,
            capability.api_mode,
            capability.processing_region,
            capability.output_schema,
            capability.router_role,
            capability.account_scope_blind_id,
            capability.project_scope_blind_id,
        )
        if (
            direct != signed
            or not (
                capability.not_before_ms
                < validated.required_until_ms
                <= capability.expires_at_ms
            )
            or validated.projected_max_cents > capability.approved_max_cents
            or validated.max_output_bytes > capability.max_output_bytes
            or validated.private_input_bytes > capability.max_private_input_bytes
        ):
            raise ValueError
    except Exception:
        raise ValueError("owner-private request core v4 is unavailable") from None


def build_owner_private_request_core_v4(
    *,
    capability: PrivateProviderProcessingCapabilityV4,
    capability_verification_keys: Mapping[str, bytes],
    operation_id: str,
    job_id: str,
    execution_id: str,
    stage_key: str,
    provider_request_bytes: bytes,
    source_registry_id: str,
    source_head_sha256: str,
    source_epoch: int,
    opaque_source_bundle_id: str,
    source_selector: str,
    source_receipt_pairs: Sequence[Cycle32SourceReceiptPairV1],
    required_until_ms: int,
    projected_max_cents: int,
    max_output_bytes: int,
) -> PreparedOwnerPrivateRequestCoreV4:
    try:
        if type(capability) is not PrivateProviderProcessingCapabilityV4:
            raise ValueError
        verify_private_provider_capability_v4(
            capability, verification_keys=capability_verification_keys
        )
        if type(source_receipt_pairs) not in (tuple, list) or len(source_receipt_pairs) > 8:
            raise ValueError
        pairs = tuple(
            Cycle32SourceReceiptPairV1.model_validate(pair.model_dump(mode="python"))
            for pair in source_receipt_pairs
        )
        if (
            not capability.not_before_ms < required_until_ms <= capability.expires_at_ms
            or projected_max_cents > capability.approved_max_cents
            or max_output_bytes > capability.max_output_bytes
            or sum(pair.private_input_member_bytes for pair in pairs)
            > capability.max_private_input_bytes
        ):
            raise ValueError
        material: dict[str, object] = {
            "schema_version": 4,
            "owner_path_discriminator": capability.owner_path_discriminator,
            "operation_id": operation_id,
            "job_id": job_id,
            "execution_id": execution_id,
            "stage_key": stage_key,
            "router_role": capability.router_role,
            "output_schema": capability.output_schema,
            "capability_id": capability.capability_id,
            "capability_v4_sha256": capability.capability_sha256,
            "output_policy_v4_sha256": capability.output_policy_v4_sha256,
            "cycle_35_contract_sha256": capability.cycle_35_contract_sha256,
            "provider_id": capability.provider_id,
            "model_id": capability.model_id,
            "route_key": capability.route_key,
            "api_mode": capability.api_mode,
            "processing_region": capability.processing_region,
            "account_scope_blind_id": capability.account_scope_blind_id,
            "project_scope_blind_id": capability.project_scope_blind_id,
            "provider_request_bytes": provider_request_bytes,
            "provider_request_sha256": hashlib.sha256(provider_request_bytes).hexdigest(),
            "provider_request_bytes_count": len(provider_request_bytes),
            "private_input_commitment_sha256": private_input_commitment_v4_sha256(pairs),
            "private_input_bytes": sum(pair.private_input_member_bytes for pair in pairs),
            "source_registry_id": source_registry_id,
            "source_head_sha256": source_head_sha256,
            "source_epoch": source_epoch,
            "opaque_source_bundle_id": opaque_source_bundle_id,
            "source_row_version": 1,
            "source_selector": source_selector,
            "source_receipt_pairs": pairs,
            "required_until_ms": required_until_ms,
            "projected_max_cents": projected_max_cents,
            "max_output_bytes": max_output_bytes,
            "synthetic_fixture_eligibility_only": True,
            "live_migration_verified": False,
            "user_accounting_effect": False,
            "transport_reachable": False,
            "confers_execution_authority": False,
            "confers_checkpoint_authority": False,
            "confers_sink_authority": False,
            "confers_transition_authority": False,
            "production_consumer_enabled": False,
        }
        idempotency = provider_scoped_idempotency_v4_sha256(material)
        material["provider_scoped_idempotency_sha256"] = idempotency
        digest = owner_private_request_core_v4_sha256(material)
        core = PreparedOwnerPrivateRequestCoreV4.model_validate(
            {
                **material,
                "request_core_id": "oprc4_" + digest[:24],
                "request_core_sha256": digest,
            }
        )
        verify_owner_private_request_core_v4(
            core,
            capability=capability,
            capability_verification_keys=capability_verification_keys,
        )
        return core
    except Exception:
        raise ValueError("owner-private request core v4 is unavailable") from None


__all__ = [
    "Cycle32SourceReceiptPairV1",
    "PreparedOwnerPrivateRequestCoreV4",
    "build_owner_private_request_core_v4",
    "owner_private_request_core_v4_sha256",
    "private_input_commitment_v4_sha256",
    "provider_scoped_idempotency_v4_sha256",
    "verify_owner_private_request_core_v4",
]
