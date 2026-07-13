"""Closed owner-private dispatch preparation with no production transport seam."""

from __future__ import annotations

import hashlib
import json
import struct
import unicodedata
from collections.abc import Mapping, Sequence
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from acquisition.substack.midnight_oil import (
    StoredAuthorizedSubstackExcerpt,
    StoredAuthorizedSubstackExcerptReader,
)

from .private_provider_authority import OwnerPrivatePublicationAuthorityV1
from .private_provider_composition import PrivateProviderComposition
from .private_provider_policy import PrivateProviderProcessingCapabilityV1
from .publication_authority_v2 import (
    ProviderProcessingCapabilityReferenceV2,
    ReviewedPublicationManifestV2,
    SubstackOwnerPrivateExcerptAuthorityV2,
)
from .stages import StageOutputSchema, StagePlan, StagePlanItem
from .swarm_plan import SwarmLivePlan, build_stage_plan

_PRIVATE_INPUT_DOMAIN = b"antiek.midnight-oil.private-input.v1\x00"
_PROVIDER_REQUEST_DOMAIN = b"antiek.midnight-oil.provider-request.v1\x00"
_SOURCE_RECEIPT_V4_DOMAIN = b"antiek.midnight-oil.owner-private-source-receipt.v4\x00"

PrivateRouterRole = Literal["gatherer", "verifier", "synthesizer"]
_OUTPUT_SCHEMA_BY_ROLE: Mapping[PrivateRouterRole, StageOutputSchema] = {
    "gatherer": "midnight-oil.gather-output/v1",
    "verifier": "midnight-oil.verifier-output/v1",
    "synthesizer": "midnight-oil.synthesizer-output/v1",
}


class _Closed(BaseModel):
    model_config = ConfigDict(
        extra="forbid", strict=True, frozen=True, hide_input_in_errors=True
    )


class PrivateProviderRequestSourceV1(_Closed):
    alias: str = Field(pattern=r"^private-source-[0-9]{4}$")
    text: str = Field(min_length=1, max_length=32_000)


class PreparedOwnerPrivateProviderRequestV1(_Closed):
    schema_version: Literal[1] = 1
    role: PrivateRouterRole
    output_schema: StageOutputSchema
    tools_enabled: Literal[False] = False
    instruction: str = Field(min_length=1, max_length=32_000)
    question: str = Field(min_length=1, max_length=32_000)
    private_sources: tuple[PrivateProviderRequestSourceV1, ...] = Field(
        min_length=1, max_length=8
    )

    @model_validator(mode="after")
    def _canonical(self) -> PreparedOwnerPrivateProviderRequestV1:
        aliases = tuple(source.alias for source in self.private_sources)
        expected = tuple(
            f"private-source-{ordinal:04d}"
            for ordinal in range(1, len(self.private_sources) + 1)
        )
        if aliases != expected or self.output_schema != _OUTPUT_SCHEMA_BY_ROLE[self.role]:
            raise ValueError("owner-private provider request identity conflicts")
        _validate_text(self.instruction, field="instruction")
        _validate_text(self.question, field="question")
        for source in self.private_sources:
            _validate_text(source.text, field="private source")
        return self


class OwnerPrivateExactTransportDescriptorV1(_Closed):
    schema_version: Literal[1] = 1
    provider_id: str = Field(min_length=1, max_length=128)
    model_id: str = Field(min_length=1, max_length=256)
    route_key: str = Field(min_length=3, max_length=385)
    api_mode: Literal["responses_no_store", "messages_no_store"]
    processing_region: str = Field(min_length=1, max_length=64)
    endpoint_origin_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    account_project_scope_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    adapter_contract_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    dispatch_config_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    tools_enabled: Literal[False] = False
    fallback_enabled: Literal[False] = False
    request_storage_enabled: Literal[False] = False
    response_storage_enabled: Literal[False] = False
    provider_cache_enabled: Literal[False] = False
    provider_logging_enabled: Literal[False] = False


class OwnerPrivateDispatchHarnessAuthorityV1(_Closed):
    """Hash-bound synthetic harness material; never consent or execution authority."""

    schema_version: Literal[1] = 1
    purpose: Literal["owner_private_dispatch_validation_only"] = (
        "owner_private_dispatch_validation_only"
    )
    owner_scope_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    operation_id: str = Field(min_length=1, max_length=256)
    job_id: str = Field(min_length=1, max_length=256)
    execution_id: str = Field(min_length=1, max_length=256)
    required_until_ms: int = Field(gt=0)
    manifest: ReviewedPublicationManifestV2
    carrier: OwnerPrivatePublicationAuthorityV1
    swarm_plan: SwarmLivePlan
    stage_plan: StagePlan
    selected_stage_key: str = Field(pattern=r"^[0-9a-f]{64}$")
    confers_execution_authority: Literal[False] = False

    @model_validator(mode="after")
    def _joins(self) -> OwnerPrivateDispatchHarnessAuthorityV1:
        expected_stage_plan = build_stage_plan(
            self.swarm_plan,
            operation_id=self.operation_id,
            job_id=self.job_id,
            approved_ceiling_cents=self.stage_plan.approved_ceiling_cents,
        )
        if (
            self.manifest.manifest_sha256 != self.carrier.publication_manifest_sha256
            or self.stage_plan.operation_id != self.operation_id
            or self.stage_plan.job_id != self.job_id
            or self.stage_plan.approved_ceiling_cents
            != self.swarm_plan.projected_total_cents
            or self.stage_plan != expected_stage_plan
        ):
            raise ValueError("owner-private dispatch harness binding conflicts")
        for stage in self.stage_plan.stages:
            role_plan = self.swarm_plan.role(stage.router_role)  # type: ignore[arg-type]
            if (
                stage.route_plan_sha256 != role_plan.plan_hash
                or stage.projected_max_cents != role_plan.projected_max_cents
            ):
                raise ValueError("owner-private dispatch topology conflicts")
        item = _selected_stage(self.stage_plan, self.selected_stage_key)
        role = _private_role(item)
        if item.route_plan_sha256 != self.swarm_plan.role(role).plan_hash:
            raise ValueError("owner-private dispatch stage route plan conflicts")
        return self


class OwnerPrivatePublicationSourceReceiptV4(_Closed):
    schema_version: Literal[4] = 4
    authority_kind: Literal["substack_owner_private_excerpt_v2"] = (
        "substack_owner_private_excerpt_v2"
    )
    receipt_id: str = Field(pattern=r"^opsr4_[0-9a-f]{24}$")
    receipt_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    owner_scope_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    operation_id: str = Field(min_length=1, max_length=256)
    job_id: str = Field(min_length=1, max_length=256)
    execution_id: str = Field(min_length=1, max_length=256)
    stage_key: str = Field(pattern=r"^[0-9a-f]{64}$")
    router_role: PrivateRouterRole
    swarm_plan_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    stage_plan_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    route_plan_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    publication_manifest_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    owner_private_authority_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    provider_request_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    private_input_commitment_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    private_input_bytes: int = Field(ge=1, le=32_000)
    required_until_ms: int = Field(gt=0)
    private_source_ordinal: int = Field(ge=1, le=8)
    collective_unit_id: str = Field(pattern=r"^cunit_[0-9a-f]{24}$")
    collective_preview_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    ref_id: str = Field(pattern=r"^sref_[0-9a-f]{16}$")
    overlay_id: str = Field(pattern=r"^csubrev_[0-9a-f]{24}$")
    overlay_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    authorization_id: str = Field(pattern=r"^sua_[0-9a-f]{24}$")
    authorization_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_receipt_id: str = Field(pattern=r"^suer_[0-9a-f]{24}$")
    source_receipt_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_representation_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_representation_bytes: int = Field(ge=1, le=100_000_000)
    source_byte_start: int = Field(ge=0)
    source_byte_end: int = Field(gt=0)
    excerpt_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    excerpt_bytes: int = Field(ge=1, le=32_000)
    provider_capability_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    provider_id: str = Field(min_length=1, max_length=128)
    model_id: str = Field(min_length=1, max_length=256)
    route_key: str = Field(min_length=3, max_length=385)
    api_mode: Literal["responses_no_store", "messages_no_store"]
    processing_region: str = Field(min_length=1, max_length=64)
    endpoint_origin_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    account_project_scope_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    adapter_contract_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    dispatch_config_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    provider_constraints_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    output_policy_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    max_output_bytes: int = Field(ge=1, le=10_000_000)
    content_class: Literal["personal_reading"] = "personal_reading"
    rights_tier: Literal["not_applicable"] = "not_applicable"
    rights_use: Literal["operator_authorized_excerpt"] = "operator_authorized_excerpt"
    source_acquisition_network_egress: Literal[False] = False
    confers_execution_authority: Literal[False] = False

    @model_validator(mode="after")
    def _identity(self) -> OwnerPrivatePublicationSourceReceiptV4:
        digest = owner_private_source_receipt_v4_sha256(self)
        if self.receipt_sha256 != digest or self.receipt_id != "opsr4_" + digest[:24]:
            raise ValueError("owner-private source receipt v4 identity conflicts")
        return self


class PreparedOwnerPrivateDispatchV1(_Closed):
    schema_version: Literal[1] = 1
    descriptor: OwnerPrivateExactTransportDescriptorV1
    provider_request_bytes: bytes = Field(
        min_length=1, max_length=10_000_000, repr=False
    )
    provider_request_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    private_input_commitment_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    private_input_bytes: int = Field(ge=1, le=32_000)
    required_until_ms: int = Field(gt=0)
    max_output_bytes: int = Field(ge=1, le=10_000_000)
    source_receipts: tuple[OwnerPrivatePublicationSourceReceiptV4, ...] = Field(
        min_length=1, max_length=8
    )
    confers_execution_authority: Literal[False] = False

    @model_validator(mode="after")
    def _request_identity(self) -> PreparedOwnerPrivateDispatchV1:
        expected = hashlib.sha256(
            _PROVIDER_REQUEST_DOMAIN + self.provider_request_bytes
        ).hexdigest()
        try:
            raw = json.loads(
                self.provider_request_bytes.decode("utf-8"),
                object_pairs_hook=_reject_duplicate_keys,
            )
            if not isinstance(raw, dict) or not isinstance(raw.get("private_sources"), list):
                raise ValueError("owner-private prepared request shape is invalid")
            raw = {**raw, "private_sources": tuple(raw["private_sources"])}
            request = PreparedOwnerPrivateProviderRequestV1.model_validate(raw)
        except (UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError):
            raise ValueError("owner-private prepared request is invalid") from None
        receipts = self.source_receipts
        ids = tuple(row.receipt_id for row in receipts)
        refs = tuple(row.ref_id for row in receipts)
        ordinals = tuple(row.private_source_ordinal for row in receipts)
        common_capabilities = {row.provider_capability_sha256 for row in receipts}
        common_policies = {row.output_policy_sha256 for row in receipts}
        common_lineage = {
            (
                row.owner_scope_sha256,
                row.operation_id,
                row.job_id,
                row.execution_id,
                row.stage_key,
                row.router_role,
                row.swarm_plan_sha256,
                row.stage_plan_sha256,
                row.route_plan_sha256,
                row.publication_manifest_sha256,
                row.owner_private_authority_sha256,
                row.required_until_ms,
            )
            for row in receipts
        }
        request_members = tuple(
            (row.ref_id, row.source_receipt_id, source.text.encode("utf-8"))
            for source, row in zip(request.private_sources, receipts, strict=True)
        )
        recomputed_private_hash, recomputed_private_bytes = (
            _private_input_commitment_from_members(request_members)
        )
        if (
            self.provider_request_sha256 != expected
            or _canonical_json(request.model_dump(mode="json"))
            != self.provider_request_bytes
            or len(request.private_sources) != len(receipts)
            or len(set(ids)) != len(ids)
            or len(set(refs)) != len(refs)
            or ordinals != tuple(range(1, len(receipts) + 1))
            or len(common_capabilities) != 1
            or len(common_policies) != 1
            or len(common_lineage) != 1
            or request.role != receipts[0].router_role
            or recomputed_private_hash != self.private_input_commitment_sha256
            or recomputed_private_bytes != self.private_input_bytes
            or any(
                row.provider_request_sha256 != self.provider_request_sha256
                or row.private_input_commitment_sha256
                != self.private_input_commitment_sha256
                or row.private_input_bytes != self.private_input_bytes
                or row.required_until_ms != self.required_until_ms
                or row.provider_id != self.descriptor.provider_id
                or row.model_id != self.descriptor.model_id
                or row.route_key != self.descriptor.route_key
                or row.api_mode != self.descriptor.api_mode
                or row.processing_region != self.descriptor.processing_region
                or row.endpoint_origin_sha256
                != self.descriptor.endpoint_origin_sha256
                or row.account_project_scope_sha256
                != self.descriptor.account_project_scope_sha256
                or row.adapter_contract_sha256
                != self.descriptor.adapter_contract_sha256
                or row.dispatch_config_sha256
                != self.descriptor.dispatch_config_sha256
                or row.max_output_bytes != self.max_output_bytes
                or hashlib.sha256(source.text.encode("utf-8")).hexdigest()
                != row.excerpt_sha256
                or len(source.text.encode("utf-8")) != row.excerpt_bytes
                for source, row in zip(request.private_sources, receipts, strict=True)
            )
        ):
            raise ValueError("owner-private prepared request identity conflicts")
        return self


def owner_private_source_receipt_v4_sha256(
    receipt: OwnerPrivatePublicationSourceReceiptV4 | Mapping[str, object],
) -> str:
    raw = receipt.model_dump(mode="json") if isinstance(receipt, BaseModel) else dict(receipt)
    material = {
        key: value for key, value in raw.items() if key not in {"receipt_id", "receipt_sha256"}
    }
    return hashlib.sha256(_SOURCE_RECEIPT_V4_DOMAIN + _canonical_json(material)).hexdigest()


def private_input_commitment(
    excerpts: Sequence[StoredAuthorizedSubstackExcerpt],
) -> tuple[str, int]:
    return _private_input_commitment_from_members(
        tuple(
            (excerpt.authority.ref_id, excerpt.authority.receipt_id, excerpt.exact_bytes)
            for excerpt in excerpts
        )
    )


def _private_input_commitment_from_members(
    members: Sequence[tuple[str, str, bytes]],
) -> tuple[str, int]:
    if not members or len(members) > 8:
        raise ValueError("owner-private input roster is invalid")
    seen_refs: set[str] = set()
    seen_receipts: set[str] = set()
    frames: list[bytes] = []
    total = 0
    for ref_id, receipt_id, exact in members:
        ref = ref_id.encode("utf-8")
        receipt = receipt_id.encode("utf-8")
        if (
            not exact
            or len(ref) > 0xFFFF
            or len(receipt) > 0xFFFF
            or ref_id in seen_refs
            or receipt_id in seen_receipts
        ):
            raise ValueError("owner-private input member is invalid")
        seen_refs.add(ref_id)
        seen_receipts.add(receipt_id)
        frames.append(
            struct.pack(">H", len(ref))
            + ref
            + struct.pack(">H", len(receipt))
            + receipt
            + struct.pack(">Q", len(exact))
            + exact
        )
        total += len(exact)
    material = _PRIVATE_INPUT_DOMAIN + struct.pack(">I", len(frames)) + b"".join(frames)
    return hashlib.sha256(material).hexdigest(), total


def validate_exact_private_dispatch(
    *,
    harness: OwnerPrivateDispatchHarnessAuthorityV1,
    owner_id: str,
    reader: StoredAuthorizedSubstackExcerptReader,
    composition: PrivateProviderComposition,
    descriptor: OwnerPrivateExactTransportDescriptorV1,
    instruction: str,
    question: str,
    now_ms: int,
) -> PreparedOwnerPrivateDispatchV1:
    """Return an inert exact dispatch envelope after fresh local/live validation."""
    try:
        return _validate_exact_private_dispatch(
            harness=harness,
            owner_id=owner_id,
            reader=reader,
            composition=composition,
            descriptor=descriptor,
            instruction=instruction,
            question=question,
            now_ms=now_ms,
        )
    except (TypeError, ValueError):
        raise ValueError("owner-private dispatch validation failed") from None


def _validate_exact_private_dispatch(
    *,
    harness: OwnerPrivateDispatchHarnessAuthorityV1,
    owner_id: str,
    reader: StoredAuthorizedSubstackExcerptReader,
    composition: PrivateProviderComposition,
    descriptor: OwnerPrivateExactTransportDescriptorV1,
    instruction: str,
    question: str,
    now_ms: int,
) -> PreparedOwnerPrivateDispatchV1:
    _validate_text(instruction, field="instruction")
    _validate_text(question, field="question")
    if len(instruction) > 32_000 or len(question) > 32_000:
        raise ValueError("owner-private request text exceeds its bound")
    # Reparse frozen inputs so model_construct or subclass shortcuts cannot authorize.
    harness = OwnerPrivateDispatchHarnessAuthorityV1.model_validate(
        harness.model_dump(mode="python")
    )
    descriptor = OwnerPrivateExactTransportDescriptorV1.model_validate(
        descriptor.model_dump(mode="python")
    )
    item = _selected_stage(harness.stage_plan, harness.selected_stage_key)
    role = _private_role(item)
    role_plan = harness.swarm_plan.role(role)
    private_authorities = tuple(
        row.authority
        for row in harness.manifest.sources
        if isinstance(row.authority, SubstackOwnerPrivateExcerptAuthorityV2)
    )
    if not private_authorities:
        raise ValueError("owner-private manifest has no private sources")
    if any(
        authority.owner_scope_sha256 != harness.owner_scope_sha256
        for authority in private_authorities
    ):
        raise ValueError("owner-private manifest owner scope conflicts")
    capability_hashes = {
        authority.provider_processing_authority.capability_sha256
        for authority in private_authorities
        if isinstance(
            authority.provider_processing_authority,
            ProviderProcessingCapabilityReferenceV2,
        )
    }
    if len(capability_hashes) != 1 or len(capability_hashes) != len(
        {
            selection.capability_sha256
            for selection in harness.carrier.selections
        }
    ):
        raise ValueError("owner-private capability composition is unsupported")
    capability_sha256 = next(iter(capability_hashes))
    selections = tuple(
        selection
        for selection in harness.carrier.selections
        if selection.capability_sha256 == capability_sha256
    )
    if len(selections) != 1:
        raise ValueError("owner-private provider selection is unavailable")
    selection = selections[0]
    if (
        descriptor.route_key not in role_plan.allowed_routes
        or descriptor.dispatch_config_sha256 != role_plan.dispatch_config_sha256
        or descriptor.provider_id != selection.provider_id
        or descriptor.model_id != selection.model_id
        or descriptor.route_key != selection.route_key
        or role not in selection.allowed_router_roles
    ):
        raise ValueError("owner-private exact route conflicts")

    excerpts = tuple(
        reader.read(
            owner_id=owner_id,
            authority=authority,
            now_ms=now_ms,
            required_until_ms=harness.required_until_ms,
        )
        for authority in private_authorities
    )
    private_hash, private_bytes = private_input_commitment(excerpts)
    registry = composition.live_reference_registry(now_ms=now_ms)
    capability = registry.require_reference_match(
        capability_sha256=capability_sha256,
        provider_id=descriptor.provider_id,
        model_id=descriptor.model_id,
        route_key=descriptor.route_key,
        router_role=role,
        private_input_bytes=private_bytes,
        now_ms=now_ms,
        required_until_ms=harness.required_until_ms,
    )
    _match_descriptor(descriptor, capability)
    request = PreparedOwnerPrivateProviderRequestV1(
        role=role,
        output_schema=_OUTPUT_SCHEMA_BY_ROLE[role],
        instruction=instruction,
        question=question,
        private_sources=tuple(
            PrivateProviderRequestSourceV1(
                alias=f"private-source-{ordinal:04d}",
                text=excerpt.receipt.text,
            )
            for ordinal, excerpt in enumerate(excerpts, start=1)
        ),
    )
    request_bytes = _canonical_json(request.model_dump(mode="json"))
    if len(request_bytes) > role_plan.max_prompt_bytes:
        raise ValueError("owner-private provider request exceeds the role plan")
    request_sha256 = hashlib.sha256(_PROVIDER_REQUEST_DOMAIN + request_bytes).hexdigest()
    receipts = tuple(
        _build_source_receipt(
            harness=harness,
            item=item,
            role=role,
            excerpt=excerpt,
            capability=capability,
            provider_request_sha256=request_sha256,
            private_input_commitment_sha256=private_hash,
            private_input_bytes=private_bytes,
            private_source_ordinal=ordinal,
        )
        for ordinal, excerpt in enumerate(excerpts, start=1)
    )
    return PreparedOwnerPrivateDispatchV1(
        descriptor=descriptor,
        provider_request_bytes=request_bytes,
        provider_request_sha256=request_sha256,
        private_input_commitment_sha256=private_hash,
        private_input_bytes=private_bytes,
        required_until_ms=harness.required_until_ms,
        max_output_bytes=capability.max_output_bytes,
        source_receipts=receipts,
    )


def _build_source_receipt(
    *,
    harness: OwnerPrivateDispatchHarnessAuthorityV1,
    item: StagePlanItem,
    role: PrivateRouterRole,
    excerpt: StoredAuthorizedSubstackExcerpt,
    capability: PrivateProviderProcessingCapabilityV1,
    provider_request_sha256: str,
    private_input_commitment_sha256: str,
    private_input_bytes: int,
    private_source_ordinal: int,
) -> OwnerPrivatePublicationSourceReceiptV4:
    authority = excerpt.authority
    material: dict[str, object] = {
        "schema_version": 4,
        "authority_kind": "substack_owner_private_excerpt_v2",
        "owner_scope_sha256": harness.owner_scope_sha256,
        "operation_id": harness.operation_id,
        "job_id": harness.job_id,
        "execution_id": harness.execution_id,
        "stage_key": item.stage_key,
        "router_role": role,
        "swarm_plan_sha256": harness.swarm_plan.plan_hash,
        "stage_plan_sha256": harness.stage_plan.plan_hash,
        "route_plan_sha256": item.route_plan_sha256,
        "publication_manifest_sha256": harness.manifest.manifest_sha256,
        "owner_private_authority_sha256": harness.carrier.authority_sha256,
        "provider_request_sha256": provider_request_sha256,
        "private_input_commitment_sha256": private_input_commitment_sha256,
        "private_input_bytes": private_input_bytes,
        "required_until_ms": harness.required_until_ms,
        "private_source_ordinal": private_source_ordinal,
        "collective_unit_id": authority.collective_unit_id,
        "collective_preview_sha256": authority.collective_preview_sha256,
        "ref_id": authority.ref_id,
        "overlay_id": authority.overlay_id,
        "overlay_sha256": authority.overlay_sha256,
        "authorization_id": authority.authorization_id,
        "authorization_sha256": authority.authorization_sha256,
        "source_receipt_id": authority.receipt_id,
        "source_receipt_sha256": authority.receipt_sha256,
        "source_representation_sha256": authority.source_representation_sha256,
        "source_representation_bytes": authority.source_representation_bytes,
        "source_byte_start": authority.source_byte_start,
        "source_byte_end": authority.source_byte_end,
        "excerpt_sha256": authority.excerpt_sha256,
        "excerpt_bytes": authority.excerpt_bytes,
        "provider_capability_sha256": capability.capability_sha256,
        "provider_id": capability.provider_id,
        "model_id": capability.model_id,
        "route_key": capability.route_key,
        "api_mode": capability.api_mode,
        "processing_region": capability.processing_region,
        "endpoint_origin_sha256": capability.endpoint_origin_sha256,
        "account_project_scope_sha256": capability.account_project_scope_sha256,
        "adapter_contract_sha256": capability.adapter_contract_sha256,
        "dispatch_config_sha256": capability.dispatch_config_sha256,
        "provider_constraints_sha256": capability.provider_constraints_sha256,
        "output_policy_sha256": capability.output_policy_sha256,
        "max_output_bytes": capability.max_output_bytes,
        "content_class": authority.content_class,
        "rights_tier": authority.rights_tier,
        "rights_use": authority.rights_use,
        "source_acquisition_network_egress": False,
        "confers_execution_authority": False,
    }
    digest = owner_private_source_receipt_v4_sha256(material)
    return OwnerPrivatePublicationSourceReceiptV4.model_validate(
        {**material, "receipt_id": "opsr4_" + digest[:24], "receipt_sha256": digest}
    )


def _match_descriptor(
    descriptor: OwnerPrivateExactTransportDescriptorV1,
    capability: PrivateProviderProcessingCapabilityV1,
) -> None:
    expected = (
        capability.provider_id,
        capability.model_id,
        capability.route_key,
        capability.api_mode,
        capability.processing_region,
        capability.endpoint_origin_sha256,
        capability.account_project_scope_sha256,
        capability.adapter_contract_sha256,
        capability.dispatch_config_sha256,
    )
    actual = (
        descriptor.provider_id,
        descriptor.model_id,
        descriptor.route_key,
        descriptor.api_mode,
        descriptor.processing_region,
        descriptor.endpoint_origin_sha256,
        descriptor.account_project_scope_sha256,
        descriptor.adapter_contract_sha256,
        descriptor.dispatch_config_sha256,
    )
    if actual != expected:
        raise ValueError("owner-private transport descriptor conflicts")


def _selected_stage(stage_plan: StagePlan, selected_stage_key: str) -> StagePlanItem:
    selected = tuple(stage for stage in stage_plan.stages if stage.stage_key == selected_stage_key)
    if len(selected) != 1:
        raise ValueError("owner-private selected stage is unavailable")
    return selected[0]


def _private_role(item: StagePlanItem) -> PrivateRouterRole:
    if item.router_role not in _OUTPUT_SCHEMA_BY_ROLE:
        raise ValueError("owner-private stage role is unavailable")
    return item.router_role  # type: ignore[return-value]


def _canonical_json(value: object) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")


def _reject_duplicate_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("owner-private request contains duplicate fields")
        result[key] = value
    return result


def _validate_text(value: str, *, field: str) -> None:
    if "\r" in value or any(
        unicodedata.category(char).startswith("C") and char not in "\n\t" for char in value
    ):
        raise ValueError(f"owner-private {field} contains forbidden control text")
    value.encode("utf-8")


__all__ = [
    "OwnerPrivateDispatchHarnessAuthorityV1",
    "OwnerPrivateExactTransportDescriptorV1",
    "OwnerPrivatePublicationSourceReceiptV4",
    "PreparedOwnerPrivateDispatchV1",
    "PreparedOwnerPrivateProviderRequestV1",
    "PrivateProviderRequestSourceV1",
    "owner_private_source_receipt_v4_sha256",
    "private_input_commitment",
    "validate_exact_private_dispatch",
]
