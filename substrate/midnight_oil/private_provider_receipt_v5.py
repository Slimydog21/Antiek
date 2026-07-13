"""Receipt-v5 source authority for the additive capability-v2 lane."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .private_output_compliance import (
    OWNER_PRIVATE_OUTPUT_POLICY_V2_SHA256,
    PRIVATE_OUTPUT_CHECKER_SHA256,
    PRIVATE_OUTPUT_SOURCE_EXTRACTOR_SHA256,
)
from .private_provider_capability_v2 import (
    PrivateProviderCapabilityV2ReferenceRegistry,
)
from .private_provider_dispatch import (
    OwnerPrivatePublicationSourceReceiptV4,
    owner_private_source_receipt_v4_sha256,
)
from .private_provider_request_core_v2 import (
    PreparedOwnerPrivateRequestCoreV2,
    owner_private_request_core_v2_sha256,
)

_RECEIPT_V5_DOMAIN = b"antiek.midnight-oil.private-publication-receipt.v5\x00"
_HEX64 = r"^[0-9a-f]{64}$"


class _Closed(BaseModel):
    model_config = ConfigDict(
        extra="forbid", strict=True, frozen=True, hide_input_in_errors=True
    )

    def __repr_args__(self) -> list[tuple[str | None, object]]:
        return [("redacted", True)]

    def safe_diagnostic(self) -> dict[str, object]:
        return {"authority_type": type(self).__name__, "redacted": True}


class OwnerPrivatePublicationSourceReceiptV5(_Closed):
    """New source receipt; v4 is nested non-conferring source/route evidence."""

    schema_version: Literal[5] = 5
    authority_kind: Literal["owner_private_excerpt_capability_v2"] = (
        "owner_private_excerpt_capability_v2"
    )
    receipt_id: str = Field(pattern=r"^opsr5_[0-9a-f]{24}$")
    receipt_sha256: str = Field(pattern=_HEX64)
    owner_scope_sha256: str = Field(pattern=_HEX64)
    operation_id: str = Field(min_length=1, max_length=256)
    job_id: str = Field(min_length=1, max_length=256)
    execution_id: str = Field(min_length=1, max_length=256)
    stage_key: str = Field(pattern=_HEX64)
    router_role: Literal["gatherer", "verifier", "synthesizer"]
    swarm_plan_sha256: str = Field(pattern=_HEX64)
    stage_plan_sha256: str = Field(pattern=_HEX64)
    route_plan_sha256: str = Field(pattern=_HEX64)
    publication_manifest_sha256: str = Field(pattern=_HEX64)
    source_evidence_v1_request_sha256: str = Field(pattern=_HEX64)
    request_core_v2_sha256: str = Field(pattern=_HEX64)
    private_input_commitment_sha256: str = Field(pattern=_HEX64)
    private_input_bytes: int = Field(ge=1, le=32_000)
    required_until_ms: int = Field(gt=0)
    private_source_ordinal: int = Field(ge=1, le=8)
    collective_unit_id: str = Field(pattern=r"^cunit_[0-9a-f]{24}$")
    collective_preview_sha256: str = Field(pattern=_HEX64)
    source_authority_kind: Literal["receipt_v4_nonconferring_evidence"] = (
        "receipt_v4_nonconferring_evidence"
    )
    source_authority_v4: OwnerPrivatePublicationSourceReceiptV4
    source_authority_v4_sha256: str = Field(pattern=_HEX64)
    provider_capability_v2_sha256: str = Field(pattern=_HEX64)
    output_policy_v2_sha256: str = Field(pattern=_HEX64)
    checker_sha256: str = Field(pattern=_HEX64)
    source_extraction_mode: Literal["owner_supplied_local_excerpt_utf8_v1"] = (
        "owner_supplied_local_excerpt_utf8_v1"
    )
    source_extractor_sha256: str = Field(pattern=_HEX64)
    content_class: Literal["personal_reading"] = "personal_reading"
    rights_tier: Literal["not_applicable"] = "not_applicable"
    source_authority_confers_sink_authority: Literal[False] = False
    confers_execution_authority: Literal[False] = False

    @model_validator(mode="after")
    def _canonical(self) -> OwnerPrivatePublicationSourceReceiptV5:
        source = self.source_authority_v4
        direct = (
            self.owner_scope_sha256,
            self.operation_id,
            self.job_id,
            self.execution_id,
            self.stage_key,
            self.router_role,
            self.swarm_plan_sha256,
            self.stage_plan_sha256,
            self.route_plan_sha256,
            self.publication_manifest_sha256,
            self.source_evidence_v1_request_sha256,
            self.private_input_commitment_sha256,
            self.private_input_bytes,
            self.required_until_ms,
            self.private_source_ordinal,
            self.collective_unit_id,
            self.collective_preview_sha256,
        )
        nested = (
            source.owner_scope_sha256,
            source.operation_id,
            source.job_id,
            source.execution_id,
            source.stage_key,
            source.router_role,
            source.swarm_plan_sha256,
            source.stage_plan_sha256,
            source.route_plan_sha256,
            source.publication_manifest_sha256,
            source.provider_request_sha256,
            source.private_input_commitment_sha256,
            source.private_input_bytes,
            source.required_until_ms,
            source.private_source_ordinal,
            source.collective_unit_id,
            source.collective_preview_sha256,
        )
        digest = owner_private_source_receipt_v5_sha256(self)
        if (
            direct != nested
            or self.source_authority_v4_sha256
            != owner_private_source_receipt_v4_sha256(source)
            or self.source_authority_v4_sha256 != source.receipt_sha256
            or self.output_policy_v2_sha256
            != OWNER_PRIVATE_OUTPUT_POLICY_V2_SHA256
            or self.checker_sha256 != PRIVATE_OUTPUT_CHECKER_SHA256
            or self.source_extractor_sha256
            != PRIVATE_OUTPUT_SOURCE_EXTRACTOR_SHA256
            or self.receipt_sha256 != digest
            or self.receipt_id != "opsr5_" + digest[:24]
        ):
            raise ValueError("owner-private source receipt v5 conflicts")
        return self


def owner_private_source_receipt_v5_sha256(
    receipt: OwnerPrivatePublicationSourceReceiptV5 | Mapping[str, object],
) -> str:
    raw = receipt.model_dump(mode="json") if isinstance(receipt, BaseModel) else dict(receipt)
    material = {
        key: value
        for key, value in raw.items()
        if key not in {"receipt_id", "receipt_sha256"}
    }
    encoded = json.dumps(
        material, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")
    return hashlib.sha256(_RECEIPT_V5_DOMAIN + encoded).hexdigest()


def build_owner_private_source_receipt_v5(
    *,
    source: OwnerPrivatePublicationSourceReceiptV4,
    request_core: PreparedOwnerPrivateRequestCoreV2,
    capability_sha256: str,
    registry: PrivateProviderCapabilityV2ReferenceRegistry,
    now_ms: int,
) -> OwnerPrivatePublicationSourceReceiptV5:
    try:
        request_core = PreparedOwnerPrivateRequestCoreV2.model_validate(
            request_core.model_dump(mode="python")
        )
        source = OwnerPrivatePublicationSourceReceiptV4.model_validate(
            source.model_dump(mode="python")
        )
    except (ValueError, TypeError):
        raise ValueError("owner-private source receipt v5 authority is unavailable") from None
    if (
        owner_private_request_core_v2_sha256(request_core)
        != request_core.request_core_sha256
        or request_core.request_core_id
        != "oprc2_" + request_core.request_core_sha256[:24]
        or owner_private_source_receipt_v4_sha256(source) != source.receipt_sha256
    ):
        raise ValueError("owner-private source receipt v5 authority is unavailable")
    capability = registry.require_available(
        capability_sha256=capability_sha256,
        now_ms=now_ms,
        required_until_ms=source.required_until_ms,
    )
    if source.private_source_ordinal > len(request_core.private_sources):
        raise ValueError("owner-private source receipt v5 capability conflicts")
    core_source = request_core.private_sources[source.private_source_ordinal - 1]
    core_lineage = (
        request_core.owner_scope_sha256,
        request_core.operation_id,
        request_core.job_id,
        request_core.execution_id,
        request_core.stage_key,
        request_core.router_role,
        request_core.swarm_plan_sha256,
        request_core.stage_plan_sha256,
        request_core.route_plan_sha256,
        request_core.publication_manifest_sha256,
        request_core.required_until_ms,
    )
    source_lineage = (
        source.owner_scope_sha256,
        source.operation_id,
        source.job_id,
        source.execution_id,
        source.stage_key,
        source.router_role,
        source.swarm_plan_sha256,
        source.stage_plan_sha256,
        source.route_plan_sha256,
        source.publication_manifest_sha256,
        source.required_until_ms,
    )
    if (
        source.provider_capability_sha256
        != capability.route_evidence.capability_sha256
        or source.provider_id != capability.route_evidence.provider_id
        or source.model_id != capability.route_evidence.model_id
        or source.route_key != capability.route_evidence.route_key
        or source.max_output_bytes < capability.max_output_bytes
        or source.required_until_ms >= capability.expires_at_ms
        or request_core.provider_capability_v2_sha256 != capability.capability_sha256
        or core_lineage != source_lineage
        or core_source.ordinal != source.private_source_ordinal
        or hashlib.sha256(core_source.text.encode("utf-8")).hexdigest()
        != source.excerpt_sha256
        or len(core_source.text.encode("utf-8")) != source.excerpt_bytes
    ):
        raise ValueError("owner-private source receipt v5 capability conflicts")
    material: dict[str, object] = {
        "schema_version": 5,
        "authority_kind": "owner_private_excerpt_capability_v2",
        "owner_scope_sha256": source.owner_scope_sha256,
        "operation_id": source.operation_id,
        "job_id": source.job_id,
        "execution_id": source.execution_id,
        "stage_key": source.stage_key,
        "router_role": source.router_role,
        "swarm_plan_sha256": source.swarm_plan_sha256,
        "stage_plan_sha256": source.stage_plan_sha256,
        "route_plan_sha256": source.route_plan_sha256,
        "publication_manifest_sha256": source.publication_manifest_sha256,
        "source_evidence_v1_request_sha256": source.provider_request_sha256,
        "request_core_v2_sha256": request_core.request_core_sha256,
        "private_input_commitment_sha256": source.private_input_commitment_sha256,
        "private_input_bytes": source.private_input_bytes,
        "required_until_ms": source.required_until_ms,
        "private_source_ordinal": source.private_source_ordinal,
        "collective_unit_id": source.collective_unit_id,
        "collective_preview_sha256": source.collective_preview_sha256,
        "source_authority_kind": "receipt_v4_nonconferring_evidence",
        "source_authority_v4": source.model_dump(mode="json"),
        "source_authority_v4_sha256": source.receipt_sha256,
        "provider_capability_v2_sha256": capability.capability_sha256,
        "output_policy_v2_sha256": OWNER_PRIVATE_OUTPUT_POLICY_V2_SHA256,
        "checker_sha256": PRIVATE_OUTPUT_CHECKER_SHA256,
        "source_extraction_mode": "owner_supplied_local_excerpt_utf8_v1",
        "source_extractor_sha256": PRIVATE_OUTPUT_SOURCE_EXTRACTOR_SHA256,
        "content_class": "personal_reading",
        "rights_tier": "not_applicable",
        "source_authority_confers_sink_authority": False,
        "confers_execution_authority": False,
    }
    material["source_authority_v4"] = source.model_dump(mode="python")
    digest = owner_private_source_receipt_v5_sha256(material)
    return OwnerPrivatePublicationSourceReceiptV5.model_validate(
        {
            **material,
            "receipt_id": "opsr5_" + digest[:24],
            "receipt_sha256": digest,
        }
    )


__all__ = [
    "OwnerPrivatePublicationSourceReceiptV5",
    "build_owner_private_source_receipt_v5",
    "owner_private_source_receipt_v5_sha256",
]
