"""One-source, non-conferring Cycle-35 ReceiptV7 provenance evidence."""

from __future__ import annotations

import hashlib
import hmac
import json
from collections.abc import Mapping
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .private_output_policy_v4 import _CONTRACT_DOMAINS
from .private_provider_capability_v4 import PrivateProviderProcessingCapabilityV4
from .private_provider_request_core_v4 import (
    PreparedOwnerPrivateRequestCoreV4,
    verify_owner_private_request_core_v4,
)

_RECEIPT_V7_DOMAIN = _CONTRACT_DOMAINS["receipt_v7"].encode("utf-8")
_HEX64 = r"^[0-9a-f]{64}$"
_MAX_I63 = 2**63 - 1


def _canonical_json(value: object) -> bytes:
    return json.dumps(
        value,
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


class OwnerPrivatePublicationSourceReceiptV7(_Closed):
    schema_version: Literal[7] = 7
    authority_kind: Literal["owner_private_sealed_source_claim_v7"] = (
        "owner_private_sealed_source_claim_v7"
    )
    receipt_id: str = Field(pattern=r"^opsr7_[0-9a-f]{24}$")
    receipt_sha256: str = Field(pattern=_HEX64)
    owner_path_discriminator: str = Field(pattern=r"^opspd1_[0-9a-f]{64}$")
    operation_id: str = Field(min_length=1, max_length=256)
    job_id: str = Field(min_length=1, max_length=256)
    execution_id: str = Field(min_length=1, max_length=256)
    stage_key: str = Field(pattern=_HEX64)
    router_role: Literal["gatherer", "synthesizer", "verifier"]
    request_core_v4_sha256: str = Field(pattern=_HEX64)
    output_policy_v4_sha256: str = Field(pattern=_HEX64)
    capability_id: str = Field(pattern=r"^ppcap4_[0-9a-f]{24}$")
    capability_v4_sha256: str = Field(pattern=_HEX64)
    required_until_ms: int = Field(ge=1, le=_MAX_I63)
    private_input_commitment_sha256: str = Field(pattern=_HEX64)
    private_input_bytes: int = Field(ge=1, le=32_000)
    private_source_ordinal: int = Field(ge=1, le=8)
    source_receipt_id: str = Field(pattern=r"^opsr5_[0-9a-f]{24}$")
    source_receipt_sha256: str = Field(pattern=_HEX64)
    source_registry_id: str = Field(min_length=1, max_length=128)
    source_head_sha256: str = Field(pattern=_HEX64)
    source_epoch: int = Field(ge=0, le=_MAX_I63)
    opaque_source_bundle_id: str = Field(min_length=1, max_length=128)
    source_row_version: Literal[1] = 1
    source_selector: str = Field(min_length=1, max_length=256)
    source_authority_kind: Literal[
        "cycle32_receipt_pair_nonconferring_evidence"
    ] = "cycle32_receipt_pair_nonconferring_evidence"
    source_authority_confers_sink_authority: Literal[False] = False
    source_current_verified: Literal[False] = False
    admission_live_resolution_required: Literal[True] = True
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
    def _canonical(self) -> OwnerPrivatePublicationSourceReceiptV7:
        digest = owner_private_source_receipt_v7_sha256(self)
        if (
            self.source_receipt_id != "opsr5_" + self.source_receipt_sha256[:24]
            or not hmac.compare_digest(self.receipt_sha256, digest)
            or self.receipt_id != "opsr7_" + digest[:24]
        ):
            raise ValueError("owner-private source receipt v7 conflicts")
        return self


def _receipt_material(
    receipt: OwnerPrivatePublicationSourceReceiptV7 | Mapping[str, object],
) -> dict[str, object]:
    raw = receipt.model_dump(mode="python") if isinstance(receipt, BaseModel) else dict(receipt)
    return {
        key: value
        for key, value in raw.items()
        if key not in {"receipt_id", "receipt_sha256"}
    }


def owner_private_source_receipt_v7_sha256(
    receipt: OwnerPrivatePublicationSourceReceiptV7 | Mapping[str, object],
) -> str:
    return hashlib.sha256(
        _RECEIPT_V7_DOMAIN + _canonical_json(_receipt_material(receipt))
    ).hexdigest()


def verify_owner_private_source_receipt_v7(
    receipt: OwnerPrivatePublicationSourceReceiptV7,
    *,
    core: PreparedOwnerPrivateRequestCoreV4,
    capability: PrivateProviderProcessingCapabilityV4,
    capability_verification_keys: Mapping[str, bytes],
) -> None:
    try:
        if (
            type(receipt) is not OwnerPrivatePublicationSourceReceiptV7
            or type(core) is not PreparedOwnerPrivateRequestCoreV4
            or type(capability) is not PrivateProviderProcessingCapabilityV4
        ):
            raise ValueError
        validated = OwnerPrivatePublicationSourceReceiptV7.model_validate(
            receipt.model_dump(mode="python")
        )
        verify_owner_private_request_core_v4(
            core,
            capability=capability,
            capability_verification_keys=capability_verification_keys,
        )
        if core.router_role == "planner" or not (
            1 <= validated.private_source_ordinal <= len(core.source_receipt_pairs)
        ):
            raise ValueError
        pair = core.source_receipt_pairs[validated.private_source_ordinal - 1]
        direct = (
            validated.owner_path_discriminator,
            validated.operation_id,
            validated.job_id,
            validated.execution_id,
            validated.stage_key,
            validated.router_role,
            validated.request_core_v4_sha256,
            validated.output_policy_v4_sha256,
            validated.capability_id,
            validated.capability_v4_sha256,
            validated.required_until_ms,
            validated.private_input_commitment_sha256,
            validated.private_input_bytes,
            validated.private_source_ordinal,
            validated.source_receipt_id,
            validated.source_receipt_sha256,
            validated.source_registry_id,
            validated.source_head_sha256,
            validated.source_epoch,
            validated.opaque_source_bundle_id,
            validated.source_row_version,
            validated.source_selector,
        )
        expected = (
            core.owner_path_discriminator,
            core.operation_id,
            core.job_id,
            core.execution_id,
            core.stage_key,
            core.router_role,
            core.request_core_sha256,
            core.output_policy_v4_sha256,
            core.capability_id,
            core.capability_v4_sha256,
            core.required_until_ms,
            core.private_input_commitment_sha256,
            core.private_input_bytes,
            pair.ordinal,
            pair.receipt_id,
            pair.receipt_sha256,
            core.source_registry_id,
            core.source_head_sha256,
            core.source_epoch,
            core.opaque_source_bundle_id,
            core.source_row_version,
            core.source_selector,
        )
        if direct != expected:
            raise ValueError
    except Exception:
        raise ValueError("owner-private source receipt v7 is unavailable") from None


def build_owner_private_source_receipt_v7(
    *,
    core: PreparedOwnerPrivateRequestCoreV4,
    capability: PrivateProviderProcessingCapabilityV4,
    capability_verification_keys: Mapping[str, bytes],
    private_source_ordinal: int,
) -> OwnerPrivatePublicationSourceReceiptV7:
    try:
        verify_owner_private_request_core_v4(
            core,
            capability=capability,
            capability_verification_keys=capability_verification_keys,
        )
        if type(private_source_ordinal) is not int or not (
            1 <= private_source_ordinal <= len(core.source_receipt_pairs)
        ):
            raise ValueError
        pair = core.source_receipt_pairs[private_source_ordinal - 1]
        material: dict[str, object] = {
            "schema_version": 7,
            "authority_kind": "owner_private_sealed_source_claim_v7",
            "owner_path_discriminator": core.owner_path_discriminator,
            "operation_id": core.operation_id,
            "job_id": core.job_id,
            "execution_id": core.execution_id,
            "stage_key": core.stage_key,
            "router_role": core.router_role,
            "request_core_v4_sha256": core.request_core_sha256,
            "output_policy_v4_sha256": core.output_policy_v4_sha256,
            "capability_id": core.capability_id,
            "capability_v4_sha256": core.capability_v4_sha256,
            "required_until_ms": core.required_until_ms,
            "private_input_commitment_sha256": core.private_input_commitment_sha256,
            "private_input_bytes": core.private_input_bytes,
            "private_source_ordinal": pair.ordinal,
            "source_receipt_id": pair.receipt_id,
            "source_receipt_sha256": pair.receipt_sha256,
            "source_registry_id": core.source_registry_id,
            "source_head_sha256": core.source_head_sha256,
            "source_epoch": core.source_epoch,
            "opaque_source_bundle_id": core.opaque_source_bundle_id,
            "source_row_version": core.source_row_version,
            "source_selector": core.source_selector,
            "source_authority_kind": "cycle32_receipt_pair_nonconferring_evidence",
            "source_authority_confers_sink_authority": False,
            "source_current_verified": False,
            "admission_live_resolution_required": True,
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
        digest = owner_private_source_receipt_v7_sha256(material)
        receipt = OwnerPrivatePublicationSourceReceiptV7.model_validate(
            {
                **material,
                "receipt_id": "opsr7_" + digest[:24],
                "receipt_sha256": digest,
            }
        )
        verify_owner_private_source_receipt_v7(
            receipt,
            core=core,
            capability=capability,
            capability_verification_keys=capability_verification_keys,
        )
        return receipt
    except Exception:
        raise ValueError("owner-private source receipt v7 is unavailable") from None


__all__ = [
    "OwnerPrivatePublicationSourceReceiptV7",
    "build_owner_private_source_receipt_v7",
    "owner_private_source_receipt_v7_sha256",
    "verify_owner_private_source_receipt_v7",
]
