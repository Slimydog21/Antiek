"""Fixture-only owner-private request core for the 11B-E authority DAG."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from typing import Literal, Protocol

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
from .private_provider_capability_v2 import (
    PrivateProviderCapabilityV2ReferenceRegistry,
)
from .private_provider_dispatch import (
    OwnerPrivateExactTransportDescriptorV1,
    OwnerPrivatePublicationSourceReceiptV4,
)
from .stages import StagePlan, provider_effect_key
from .swarm_plan import SwarmLivePlan, build_stage_plan

_REQUEST_CORE_DOMAIN = b"antiek.midnight-oil.owner-private-request-core.v2\x00"
_V1_REQUEST_EVIDENCE_DOMAIN = b"antiek.midnight-oil.provider-request.v1\x00"
_PLANNER_PROMPT_DOMAIN = b"antiek.midnight-oil.owner-private-planner-prompt.v2\x00"
_PLANNER_PROMPT_SIGNATURE_DOMAIN = (
    b"antiek.midnight-oil.owner-private-planner-prompt-signature.v2\x00"
)
_PLANNER_CONTEXT_DOMAIN = b"antiek.midnight-oil.owner-private-planner-context.v2\x00"
_HEX64 = r"^[0-9a-f]{64}$"
_OUTPUT_SCHEMA_BY_ROLE = {
    "gatherer": "midnight-oil.gather-output/v1",
    "planner": "midnight-oil.planner-output/v1",
    "synthesizer": "midnight-oil.synthesizer-output/v1",
    "verifier": "midnight-oil.verifier-output/v1",
}


class OwnerPrivatePreparedRequestEvidence(Protocol):
    """Structural fixture evidence; deliberately not a legacy-class consumer."""

    @property
    def descriptor(self) -> OwnerPrivateExactTransportDescriptorV1: ...

    @property
    def provider_request_bytes(self) -> bytes: ...

    @property
    def provider_request_sha256(self) -> str: ...

    @property
    def required_until_ms(self) -> int: ...

    @property
    def max_output_bytes(self) -> int: ...

    @property
    def source_receipts(self) -> tuple[OwnerPrivatePublicationSourceReceiptV4, ...]: ...


class _Closed(BaseModel):
    model_config = ConfigDict(
        extra="forbid", strict=True, frozen=True, hide_input_in_errors=True
    )

    def __repr_args__(self) -> list[tuple[str | None, object]]:
        return [("redacted", True)]

    def safe_diagnostic(self) -> dict[str, object]:
        return {"authority_type": type(self).__name__, "redacted": True}


class OwnerPrivateRequestSourceV2(_Closed):
    ordinal: int = Field(ge=1, le=8)
    alias: str = Field(pattern=r"^private-source-[0-9]{4}$")
    text: str = Field(min_length=1, max_length=32_000, repr=False)


class OwnerPrivatePlannerPromptAuthorityV2(_Closed):
    """Signed fixture authority for exact zero-source planner prompt material."""

    schema_version: Literal[2] = 2
    authority_id: str = Field(pattern=r"^oppa2_[0-9a-f]{24}$")
    authority_sha256: str = Field(pattern=_HEX64)
    owner_scope_sha256: str = Field(pattern=_HEX64)
    operation_id: str = Field(min_length=1, max_length=256)
    job_id: str = Field(min_length=1, max_length=256)
    execution_id: str = Field(min_length=1, max_length=256)
    swarm_plan_sha256: str = Field(pattern=_HEX64)
    stage_plan_sha256: str = Field(pattern=_HEX64)
    selected_stage_key: str = Field(pattern=_HEX64)
    provider_effect_key: str = Field(pattern=_HEX64)
    goal_index: int = Field(ge=0, le=100_000)
    goal: str = Field(min_length=1, max_length=32_000, repr=False)
    instruction: str = Field(min_length=1, max_length=32_000, repr=False)
    question: str = Field(min_length=1, max_length=32_000, repr=False)
    context: str = Field(max_length=128_000, repr=False)
    planner_context_sha256: str = Field(pattern=_HEX64)
    key_id: str = Field(pattern=r"^[A-Za-z0-9._-]{1,128}$")
    key_purpose: Literal["owner_private_planner_prompt_fixture_v2"] = (
        "owner_private_planner_prompt_fixture_v2"
    )
    signature_scheme: Literal["ed25519"] = "ed25519"
    signature_ed25519: str = Field(pattern=r"^[0-9a-f]{128}$")
    confers_execution_authority: Literal[False] = False
    production_consumer_enabled: Literal[False] = False

    @model_validator(mode="after")
    def _canonical(self) -> OwnerPrivatePlannerPromptAuthorityV2:
        if (
            self.provider_effect_key != provider_effect_key(self.selected_stage_key)
            or self.planner_context_sha256 != _planner_context_sha256(self)
        ):
            raise ValueError("owner-private planner prompt authority conflicts")
        digest = owner_private_planner_prompt_authority_v2_sha256(self)
        if self.authority_sha256 != digest or self.authority_id != "oppa2_" + digest[:24]:
            raise ValueError("owner-private planner prompt authority identity conflicts")
        return self


def _planner_context_sha256(
    authority: OwnerPrivatePlannerPromptAuthorityV2 | Mapping[str, object],
) -> str:
    raw = authority.model_dump(mode="json") if isinstance(authority, BaseModel) else dict(authority)
    material = {
        key: raw[key]
        for key in (
            "owner_scope_sha256",
            "operation_id",
            "job_id",
            "execution_id",
            "swarm_plan_sha256",
            "stage_plan_sha256",
            "selected_stage_key",
            "provider_effect_key",
            "goal_index",
            "goal",
            "instruction",
            "question",
            "context",
        )
    }
    return hashlib.sha256(
        _PLANNER_CONTEXT_DOMAIN
        + json.dumps(
            material, sort_keys=True, separators=(",", ":"), ensure_ascii=False
        ).encode("utf-8")
    ).hexdigest()


def owner_private_planner_prompt_authority_v2_sha256(
    authority: OwnerPrivatePlannerPromptAuthorityV2 | Mapping[str, object],
) -> str:
    raw = authority.model_dump(mode="json") if isinstance(authority, BaseModel) else dict(authority)
    material = {
        key: value
        for key, value in raw.items()
        if key not in {"authority_id", "authority_sha256", "signature_ed25519"}
    }
    return hashlib.sha256(
        _PLANNER_PROMPT_DOMAIN
        + json.dumps(
            material, sort_keys=True, separators=(",", ":"), ensure_ascii=False
        ).encode("utf-8")
    ).hexdigest()


def signed_owner_private_planner_prompt_authority_v2(
    *,
    owner_scope_sha256: str,
    operation_id: str,
    job_id: str,
    execution_id: str,
    swarm_plan_sha256: str,
    stage_plan_sha256: str,
    selected_stage_key: str,
    goal_index: int,
    goal: str,
    instruction: str,
    question: str,
    context: str,
    key_id: str,
    signing_key: bytes,
) -> OwnerPrivatePlannerPromptAuthorityV2:
    if len(signing_key) != 32:
        raise ValueError("owner-private planner prompt signing key must be 32 bytes")
    material: dict[str, object] = {
        "schema_version": 2,
        "owner_scope_sha256": owner_scope_sha256,
        "operation_id": operation_id,
        "job_id": job_id,
        "execution_id": execution_id,
        "swarm_plan_sha256": swarm_plan_sha256,
        "stage_plan_sha256": stage_plan_sha256,
        "selected_stage_key": selected_stage_key,
        "provider_effect_key": provider_effect_key(selected_stage_key),
        "goal_index": goal_index,
        "goal": goal,
        "instruction": instruction,
        "question": question,
        "context": context,
        "key_id": key_id,
        "key_purpose": "owner_private_planner_prompt_fixture_v2",
        "signature_scheme": "ed25519",
        "confers_execution_authority": False,
        "production_consumer_enabled": False,
    }
    material["planner_context_sha256"] = _planner_context_sha256(material)
    digest = owner_private_planner_prompt_authority_v2_sha256(material)
    signature = Ed25519PrivateKey.from_private_bytes(signing_key).sign(
        _PLANNER_PROMPT_SIGNATURE_DOMAIN + digest.encode("ascii")
    )
    return OwnerPrivatePlannerPromptAuthorityV2.model_validate(
        {
            **material,
            "authority_id": "oppa2_" + digest[:24],
            "authority_sha256": digest,
            "signature_ed25519": signature.hex(),
        }
    )


def verify_owner_private_planner_prompt_authority_v2(
    authority: OwnerPrivatePlannerPromptAuthorityV2,
    *,
    verification_keys: Mapping[str, bytes],
) -> None:
    try:
        authority = OwnerPrivatePlannerPromptAuthorityV2.model_validate(
            authority.model_dump(mode="python")
        )
        key = verification_keys.get(authority.key_id)
        if key is None or len(key) != 32:
            raise ValueError
        Ed25519PublicKey.from_public_bytes(key).verify(
            bytes.fromhex(authority.signature_ed25519),
            _PLANNER_PROMPT_SIGNATURE_DOMAIN + authority.authority_sha256.encode("ascii"),
        )
    except (InvalidSignature, TypeError, ValueError):
        raise ValueError("owner-private planner prompt authority is unavailable") from None


class PreparedOwnerPrivateRequestCoreV2(_Closed):
    """Content-addressed request material; it confers no transport authority."""

    schema_version: Literal[2] = 2
    request_core_id: str = Field(pattern=r"^oprc2_[0-9a-f]{24}$")
    request_core_sha256: str = Field(pattern=_HEX64)
    owner_scope_sha256: str = Field(pattern=_HEX64)
    operation_id: str = Field(min_length=1, max_length=256)
    job_id: str = Field(min_length=1, max_length=256)
    execution_id: str = Field(min_length=1, max_length=256)
    stage_key: str = Field(pattern=_HEX64)
    provider_effect_key: str = Field(pattern=_HEX64)
    router_role: Literal["gatherer", "planner", "synthesizer", "verifier"]
    output_schema: Literal[
        "midnight-oil.gather-output/v1",
        "midnight-oil.planner-output/v1",
        "midnight-oil.synthesizer-output/v1",
        "midnight-oil.verifier-output/v1",
    ]
    swarm_plan_sha256: str = Field(pattern=_HEX64)
    stage_plan_sha256: str = Field(pattern=_HEX64)
    route_plan_sha256: str = Field(pattern=_HEX64)
    publication_manifest_sha256: str | None = Field(default=None, pattern=_HEX64)
    provider_capability_v2_sha256: str = Field(pattern=_HEX64)
    output_policy_v2_sha256: str = Field(pattern=_HEX64)
    checker_sha256: str = Field(pattern=_HEX64)
    source_extractor_sha256: str = Field(pattern=_HEX64)
    required_until_ms: int = Field(gt=0)
    max_output_bytes: int = Field(ge=1, le=1_000_000)
    provider_id: str = Field(min_length=1, max_length=128)
    model_id: str = Field(min_length=1, max_length=256)
    route_key: str = Field(min_length=3, max_length=385)
    api_mode: Literal["responses_no_store", "messages_no_store"]
    processing_region: str = Field(min_length=1, max_length=64)
    endpoint_origin_sha256: str = Field(pattern=_HEX64)
    account_project_scope_sha256: str = Field(pattern=_HEX64)
    adapter_contract_sha256: str = Field(pattern=_HEX64)
    dispatch_config_sha256: str = Field(pattern=_HEX64)
    tools_enabled: Literal[False] = False
    instruction: str = Field(min_length=1, max_length=32_000, repr=False)
    question: str = Field(min_length=1, max_length=32_000, repr=False)
    private_sources: tuple[OwnerPrivateRequestSourceV2, ...] = Field(max_length=8, repr=False)
    provider_request_bytes: bytes = Field(min_length=1, max_length=10_000_000, repr=False)
    prompt_authority_kind: Literal[
        "audit_v1_exact_request_evidence",
        "canonical_planner_fixture_commitment_v2",
    ]
    goal_index: int | None = Field(default=None, ge=0, le=100_000)
    planner_context_sha256: str | None = Field(default=None, pattern=_HEX64)
    planner_prompt_authority_sha256: str | None = Field(default=None, pattern=_HEX64)
    planner_prompt_authority_key_id: str | None = Field(
        default=None, pattern=r"^[A-Za-z0-9._-]{1,128}$"
    )
    route_source_evidence_v1_request_sha256: str = Field(pattern=_HEX64)
    route_source_evidence_confers_request_authority: Literal[False] = False
    confers_execution_authority: Literal[False] = False
    production_consumer_enabled: Literal[False] = False

    @model_validator(mode="after")
    def _canonical(self) -> PreparedOwnerPrivateRequestCoreV2:
        sources = self.private_sources
        expected = tuple(range(1, len(sources) + 1))
        request_material = {
            "instruction": self.instruction,
            "output_schema": self.output_schema,
            "private_sources": tuple(
                {"alias": source.alias, "text": source.text} for source in sources
            ),
            "question": self.question,
            "role": self.router_role,
            "schema_version": 1,
            "tools_enabled": False,
        }
        canonical_request = json.dumps(
            request_material,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")
        if (
            tuple(source.ordinal for source in sources) != expected
            or tuple(source.alias for source in sources)
            != tuple(f"private-source-{ordinal:04d}" for ordinal in expected)
            or (self.router_role == "planner" and sources)
            or (self.router_role != "planner" and not sources)
            or (
                self.router_role == "planner"
                and (
                    self.publication_manifest_sha256 is not None
                    or self.prompt_authority_kind
                    != "canonical_planner_fixture_commitment_v2"
                    or self.goal_index is None
                    or self.planner_context_sha256 is None
                    or self.planner_prompt_authority_sha256 is None
                    or self.planner_prompt_authority_key_id is None
                    or self.route_source_evidence_v1_request_sha256 != "0" * 64
                )
            )
            or (
                self.router_role != "planner"
                and (
                    self.publication_manifest_sha256 is None
                    or self.prompt_authority_kind
                    != "audit_v1_exact_request_evidence"
                    or self.goal_index is not None
                    or self.planner_context_sha256 is not None
                    or self.planner_prompt_authority_sha256 is not None
                    or self.planner_prompt_authority_key_id is not None
                )
            )
            or self.provider_effect_key != provider_effect_key(self.stage_key)
            or self.output_schema != _OUTPUT_SCHEMA_BY_ROLE[self.router_role]
            or self.route_key != f"{self.provider_id}/{self.model_id}"
            or self.provider_request_bytes != canonical_request
            or self.output_policy_v2_sha256 != OWNER_PRIVATE_OUTPUT_POLICY_V2_SHA256
            or self.checker_sha256 != PRIVATE_OUTPUT_CHECKER_SHA256
            or self.source_extractor_sha256 != PRIVATE_OUTPUT_SOURCE_EXTRACTOR_SHA256
        ):
            raise ValueError("owner-private request core v2 contract conflicts")
        digest = owner_private_request_core_v2_sha256(self)
        if self.request_core_sha256 != digest or self.request_core_id != "oprc2_" + digest[:24]:
            raise ValueError("owner-private request core v2 identity conflicts")
        return self


def owner_private_request_core_v2_sha256(
    core: PreparedOwnerPrivateRequestCoreV2 | Mapping[str, object],
) -> str:
    raw = core.model_dump(mode="json") if isinstance(core, BaseModel) else dict(core)
    provider_request_bytes = raw.get("provider_request_bytes")
    if isinstance(provider_request_bytes, bytes):
        raw["provider_request_bytes"] = provider_request_bytes.decode("utf-8")
    material = {
        key: value
        for key, value in raw.items()
        if key not in {"request_core_id", "request_core_sha256"}
    }
    encoded = json.dumps(
        material, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")
    return hashlib.sha256(_REQUEST_CORE_DOMAIN + encoded).hexdigest()


def build_owner_private_request_core_v2(
    *,
    prepared_v1: OwnerPrivatePreparedRequestEvidence,
    capability_sha256: str,
    registry: PrivateProviderCapabilityV2ReferenceRegistry,
    now_ms: int,
) -> PreparedOwnerPrivateRequestCoreV2:
    capability = registry.require_available(
        capability_sha256=capability_sha256,
        now_ms=now_ms,
        required_until_ms=prepared_v1.required_until_ms,
    )
    try:
        source_receipts = tuple(
            OwnerPrivatePublicationSourceReceiptV4.model_validate(
                receipt.model_dump(mode="python")
            )
            for receipt in prepared_v1.source_receipts
        )
    except (ValueError, TypeError):
        raise ValueError("owner-private request core v2 source evidence is unavailable") from None
    if not source_receipts:
        raise ValueError("owner-private request core v2 source evidence is unavailable")
    try:
        request = json.loads(prepared_v1.provider_request_bytes.decode("utf-8"))
        raw_sources = request["private_sources"]
        if type(request) is not dict or type(raw_sources) is not list:
            raise ValueError
        sources = tuple(
            OwnerPrivateRequestSourceV2(
                ordinal=ordinal,
                alias=raw["alias"],
                text=raw["text"],
            )
            for ordinal, raw in enumerate(raw_sources, start=1)
            if type(raw) is dict
        )
        if len(sources) != len(raw_sources):
            raise ValueError
    except (KeyError, TypeError, UnicodeError, ValueError, json.JSONDecodeError):
        raise ValueError("owner-private request core v2 source material is unavailable") from None
    first = source_receipts[0]
    evidence = capability.route_evidence
    descriptor = prepared_v1.descriptor
    descriptor_values = (
        descriptor.provider_id,
        descriptor.model_id,
        descriptor.route_key,
        descriptor.api_mode,
        descriptor.processing_region,
        descriptor.endpoint_origin_sha256,
        descriptor.account_project_scope_sha256,
        descriptor.adapter_contract_sha256,
        descriptor.dispatch_config_sha256,
        descriptor.tools_enabled,
        descriptor.fallback_enabled,
        descriptor.request_storage_enabled,
        descriptor.response_storage_enabled,
        descriptor.provider_cache_enabled,
        descriptor.provider_logging_enabled,
    )
    capability_values = (
        evidence.provider_id,
        evidence.model_id,
        evidence.route_key,
        evidence.api_mode,
        evidence.processing_region,
        evidence.endpoint_origin_sha256,
        evidence.account_project_scope_sha256,
        evidence.adapter_contract_sha256,
        evidence.dispatch_config_sha256,
        False,
        evidence.router_fallback_allowed,
        evidence.request_storage_allowed,
        evidence.response_storage_allowed,
        evidence.provider_cache_allowed,
        evidence.provider_logging_allowed,
    )
    request_evidence_sha256 = hashlib.sha256(
        _V1_REQUEST_EVIDENCE_DOMAIN + prepared_v1.provider_request_bytes
    ).hexdigest()
    if (
        any(row.provider_capability_sha256 != capability.route_evidence_sha256 for row in source_receipts)
        or prepared_v1.max_output_bytes < capability.max_output_bytes
        or request.get("role") != first.router_role
        or descriptor_values != capability_values
        or request_evidence_sha256 != prepared_v1.provider_request_sha256
        or any(
            row.provider_request_sha256 != request_evidence_sha256
            for row in source_receipts
        )
        or any(
            (
                row.provider_id,
                row.model_id,
                row.route_key,
                row.api_mode,
                row.processing_region,
                row.endpoint_origin_sha256,
                row.account_project_scope_sha256,
                row.adapter_contract_sha256,
                row.dispatch_config_sha256,
            )
            != descriptor_values[:9]
            for row in source_receipts
        )
        or len(source_receipts) != len(sources)
        or tuple(row.private_source_ordinal for row in source_receipts)
        != tuple(range(1, len(source_receipts) + 1))
        or any(
            hashlib.sha256(source.text.encode("utf-8")).hexdigest()
            != receipt.excerpt_sha256
            or len(source.text.encode("utf-8")) != receipt.excerpt_bytes
            for source, receipt in zip(sources, source_receipts, strict=True)
        )
    ):
        raise ValueError("owner-private request core v2 authority conflicts")
    material: dict[str, object] = {
        "schema_version": 2,
        "owner_scope_sha256": first.owner_scope_sha256,
        "operation_id": first.operation_id,
        "job_id": first.job_id,
        "execution_id": first.execution_id,
        "stage_key": first.stage_key,
        "provider_effect_key": provider_effect_key(first.stage_key),
        "router_role": first.router_role,
        "output_schema": request["output_schema"],
        "swarm_plan_sha256": first.swarm_plan_sha256,
        "stage_plan_sha256": first.stage_plan_sha256,
        "route_plan_sha256": first.route_plan_sha256,
        "publication_manifest_sha256": first.publication_manifest_sha256,
        "provider_capability_v2_sha256": capability.capability_sha256,
        "output_policy_v2_sha256": OWNER_PRIVATE_OUTPUT_POLICY_V2_SHA256,
        "checker_sha256": PRIVATE_OUTPUT_CHECKER_SHA256,
        "source_extractor_sha256": PRIVATE_OUTPUT_SOURCE_EXTRACTOR_SHA256,
        "required_until_ms": prepared_v1.required_until_ms,
        "max_output_bytes": capability.max_output_bytes,
        "provider_id": descriptor.provider_id,
        "model_id": descriptor.model_id,
        "route_key": descriptor.route_key,
        "api_mode": descriptor.api_mode,
        "processing_region": descriptor.processing_region,
        "endpoint_origin_sha256": descriptor.endpoint_origin_sha256,
        "account_project_scope_sha256": descriptor.account_project_scope_sha256,
        "adapter_contract_sha256": descriptor.adapter_contract_sha256,
        "dispatch_config_sha256": descriptor.dispatch_config_sha256,
        "tools_enabled": False,
        "instruction": request["instruction"],
        "question": request["question"],
        "private_sources": tuple(source.model_dump(mode="python") for source in sources),
        "provider_request_bytes": prepared_v1.provider_request_bytes,
        "prompt_authority_kind": "audit_v1_exact_request_evidence",
        "goal_index": None,
        "planner_context_sha256": None,
        "planner_prompt_authority_sha256": None,
        "planner_prompt_authority_key_id": None,
        "route_source_evidence_v1_request_sha256": prepared_v1.provider_request_sha256,
        "route_source_evidence_confers_request_authority": False,
        "confers_execution_authority": False,
        "production_consumer_enabled": False,
    }
    digest = owner_private_request_core_v2_sha256(material)
    return PreparedOwnerPrivateRequestCoreV2.model_validate(
        {**material, "request_core_id": "oprc2_" + digest[:24], "request_core_sha256": digest}
    )


def build_owner_private_planner_request_core_v2(
    *,
    prompt_authority: OwnerPrivatePlannerPromptAuthorityV2,
    prompt_authority_verification_keys: Mapping[str, bytes],
    swarm_plan: SwarmLivePlan,
    stage_plan: StagePlan,
    descriptor: OwnerPrivateExactTransportDescriptorV1,
    capability_sha256: str,
    registry: PrivateProviderCapabilityV2ReferenceRegistry,
    required_until_ms: int,
    now_ms: int,
) -> PreparedOwnerPrivateRequestCoreV2:
    """Build the canonical zero-source planner fixture from plan authority."""

    capability = registry.require_available(
        capability_sha256=capability_sha256,
        now_ms=now_ms,
        required_until_ms=required_until_ms,
    )
    rebuilt = build_stage_plan(
        swarm_plan,
        operation_id=stage_plan.operation_id,
        job_id=stage_plan.job_id,
        approved_ceiling_cents=stage_plan.approved_ceiling_cents,
    )
    verify_owner_private_planner_prompt_authority_v2(
        prompt_authority, verification_keys=prompt_authority_verification_keys
    )
    selected = next(
        (
            item
            for item in stage_plan.stages
            if item.stage_key == prompt_authority.selected_stage_key
        ),
        None,
    )
    evidence = capability.route_evidence
    if (
        rebuilt != stage_plan
        or selected is None
        or selected.kind != "planner"
        or selected.router_role != "planner"
        or selected.route_plan_sha256 != swarm_plan.role("planner").plan_hash
        or prompt_authority.operation_id != stage_plan.operation_id
        or prompt_authority.job_id != stage_plan.job_id
        or prompt_authority.swarm_plan_sha256 != swarm_plan.plan_hash
        or prompt_authority.stage_plan_sha256 != stage_plan.plan_hash
        or prompt_authority.provider_effect_key != selected.provider_effect_key
        or prompt_authority.goal_index != selected.goal_index
        or descriptor.route_key not in swarm_plan.role("planner").allowed_routes
        or (
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
        != (
            evidence.provider_id,
            evidence.model_id,
            evidence.route_key,
            evidence.api_mode,
            evidence.processing_region,
            evidence.endpoint_origin_sha256,
            evidence.account_project_scope_sha256,
            evidence.adapter_contract_sha256,
            evidence.dispatch_config_sha256,
        )
        or descriptor.tools_enabled
        or descriptor.fallback_enabled
        or descriptor.request_storage_enabled
        or descriptor.response_storage_enabled
        or descriptor.provider_cache_enabled
        or descriptor.provider_logging_enabled
    ):
        raise ValueError("owner-private planner request core v2 authority conflicts")
    request_material = {
        "instruction": prompt_authority.instruction,
        "output_schema": "midnight-oil.planner-output/v1",
        "private_sources": (),
        "question": prompt_authority.question,
        "role": "planner",
        "schema_version": 1,
        "tools_enabled": False,
    }
    request_bytes = json.dumps(
        request_material,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    material: dict[str, object] = {
        "schema_version": 2,
        "owner_scope_sha256": prompt_authority.owner_scope_sha256,
        "operation_id": stage_plan.operation_id,
        "job_id": stage_plan.job_id,
        "execution_id": prompt_authority.execution_id,
        "stage_key": selected.stage_key,
        "provider_effect_key": selected.provider_effect_key,
        "router_role": "planner",
        "output_schema": "midnight-oil.planner-output/v1",
        "swarm_plan_sha256": swarm_plan.plan_hash,
        "stage_plan_sha256": stage_plan.plan_hash,
        "route_plan_sha256": selected.route_plan_sha256,
        "publication_manifest_sha256": None,
        "provider_capability_v2_sha256": capability.capability_sha256,
        "output_policy_v2_sha256": OWNER_PRIVATE_OUTPUT_POLICY_V2_SHA256,
        "checker_sha256": PRIVATE_OUTPUT_CHECKER_SHA256,
        "source_extractor_sha256": PRIVATE_OUTPUT_SOURCE_EXTRACTOR_SHA256,
        "required_until_ms": required_until_ms,
        "max_output_bytes": capability.max_output_bytes,
        "provider_id": descriptor.provider_id,
        "model_id": descriptor.model_id,
        "route_key": descriptor.route_key,
        "api_mode": descriptor.api_mode,
        "processing_region": descriptor.processing_region,
        "endpoint_origin_sha256": descriptor.endpoint_origin_sha256,
        "account_project_scope_sha256": descriptor.account_project_scope_sha256,
        "adapter_contract_sha256": descriptor.adapter_contract_sha256,
        "dispatch_config_sha256": descriptor.dispatch_config_sha256,
        "tools_enabled": False,
        "instruction": prompt_authority.instruction,
        "question": prompt_authority.question,
        "private_sources": (),
        "provider_request_bytes": request_bytes,
        "prompt_authority_kind": "canonical_planner_fixture_commitment_v2",
        "goal_index": selected.goal_index,
        "planner_context_sha256": prompt_authority.planner_context_sha256,
        "planner_prompt_authority_sha256": prompt_authority.authority_sha256,
        "planner_prompt_authority_key_id": prompt_authority.key_id,
        "route_source_evidence_v1_request_sha256": "0" * 64,
        "route_source_evidence_confers_request_authority": False,
        "confers_execution_authority": False,
        "production_consumer_enabled": False,
    }
    digest = owner_private_request_core_v2_sha256(material)
    return PreparedOwnerPrivateRequestCoreV2.model_validate(
        {**material, "request_core_id": "oprc2_" + digest[:24], "request_core_sha256": digest}
    )


__all__ = [
    "OwnerPrivateRequestSourceV2",
    "OwnerPrivatePreparedRequestEvidence",
    "OwnerPrivatePlannerPromptAuthorityV2",
    "PreparedOwnerPrivateRequestCoreV2",
    "build_owner_private_request_core_v2",
    "build_owner_private_planner_request_core_v2",
    "owner_private_request_core_v2_sha256",
    "owner_private_planner_prompt_authority_v2_sha256",
    "signed_owner_private_planner_prompt_authority_v2",
    "verify_owner_private_planner_prompt_authority_v2",
]
