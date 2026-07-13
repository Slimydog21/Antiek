"""Isolated, non-conferring receipt-to-checker adapter for owner-private output.

The adapter performs no I/O and has no application consumer. It resolves the exact
receipt-v5 roster through a caller-supplied trusted resolver, derives checker inputs
only from request-core text, invokes checker-v2 internally, and returns content-free
decision metadata.
"""

from __future__ import annotations

import ast
import hashlib
import hmac
import json
from pathlib import Path
from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .live_roles import parse_role_output as _parse_role_output
from .private_output_checker_v2 import (
    PRIVATE_OUTPUT_ATTRIBUTED_NORMALIZER_V2_SHA256,
    PRIVATE_OUTPUT_CHECKER_CONTRACT_V2_SHA256,
    PRIVATE_OUTPUT_CHECKER_V2_SHA256,
    PRIVATE_OUTPUT_EXECUTABLE_CORPUS_V2_SHA256,
    PRIVATE_OUTPUT_LEDGER_V2_SHA256,
)
from .private_output_checker_v2 import (
    OwnerPrivateOverlapNotApplicableV2 as _CheckerNotApplicableV2,
)
from .private_output_checker_v2 import OwnerPrivateOverlapPassV2 as _CheckerPassV2
from .private_output_checker_v2 import OwnerPrivateOverlapSourceV2 as _CheckerSourceV2
from .private_output_checker_v2 import (
    check_owner_private_overlap_v2 as _check_owner_private_overlap_v2,
)
from .private_output_compliance import (
    OWNER_PRIVATE_OUTPUT_POLICY_V2_SHA256,
    PRIVATE_OUTPUT_CHECKER_SHA256,
    PRIVATE_OUTPUT_SOURCE_EXTRACTOR_SHA256,
)
from .private_provider_capability_v2 import (
    PrivateProviderCapabilityV2ReferenceRegistry,
    PrivateProviderProcessingCapabilityV2,
)
from .private_provider_dispatch import (
    _private_input_commitment_from_members,
    owner_private_source_receipt_v4_sha256,
)
from .private_provider_envelope_v2 import (
    PreparedOwnerPrivateEnvelopeV2,
    prepared_owner_private_envelope_v2_sha256,
)
from .private_provider_receipt_v5 import (
    OwnerPrivatePublicationSourceReceiptV5,
    owner_private_source_receipt_v5_sha256,
)
from .private_provider_request_core_v2 import owner_private_request_core_v2_sha256
from .stages import provider_effect_key

_HEX64 = r"^[0-9a-f]{64}$"
_ADAPTER_DOMAIN = b"antiek.midnight-oil.owner-private-checker-source-adapter.v1\x00"
_CONTRACT_DOMAIN = (
    b"antiek.midnight-oil.owner-private-checker-source-adapter-contract.v1\x00"
)
_SOURCE_SET_DOMAIN = (
    b"antiek.midnight-oil.owner-private-resolved-checker-source-set.v1\x00"
)


def _canonical_json(value: object) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")


def _digest(domain: bytes, value: object) -> str:
    return hashlib.sha256(domain + _canonical_json(value)).hexdigest()


def _same(first: str, second: str) -> bool:
    return hmac.compare_digest(first, second)


class OwnerPrivateOutputSourceAdapterRejected(ValueError):
    """The sole content-free adapter failure."""

    def __init__(self) -> None:
        super().__init__("owner-private output source adapter rejected")

    def __repr__(self) -> str:
        return "OwnerPrivateOutputSourceAdapterRejected()"


class OwnerPrivateReceiptV5Resolver(Protocol):
    """Trusted resolver for one exact receipt identity; no implementation is provided."""

    def resolve_exact(
        self, *, receipt_id: str, receipt_sha256: str
    ) -> OwnerPrivatePublicationSourceReceiptV5 | None: ...


class _Closed(BaseModel):
    model_config = ConfigDict(
        extra="forbid", strict=True, frozen=True, hide_input_in_errors=True
    )

    def __repr_args__(self) -> list[tuple[str | None, object]]:
        return [("redacted", True)]


_SOURCE_SET_MATERIAL_V1 = {
    "schema_version": 1,
    "evidence_algorithms": (
        "owner-private-request-core-v2",
        "owner-private-publication-source-receipt-v5",
        "owner-private-publication-source-receipt-v4",
        "owner-private-prepared-envelope-v2",
        "owner-private-input-commitment-v1",
    ),
    "old_evidence_policy_sha256": OWNER_PRIVATE_OUTPUT_POLICY_V2_SHA256,
    "old_evidence_checker_sha256": PRIVATE_OUTPUT_CHECKER_SHA256,
    "old_evidence_source_extractor_sha256": PRIVATE_OUTPUT_SOURCE_EXTRACTOR_SHA256,
    "checker_v2_sha256": PRIVATE_OUTPUT_CHECKER_V2_SHA256,
    "checker_v2_contract_sha256": PRIVATE_OUTPUT_CHECKER_CONTRACT_V2_SHA256,
    "checker_v2_corpus_sha256": PRIVATE_OUTPUT_EXECUTABLE_CORPUS_V2_SHA256,
    "checker_v2_normalizer_sha256": PRIVATE_OUTPUT_ATTRIBUTED_NORMALIZER_V2_SHA256,
    "checker_v2_ledger_sha256": PRIVATE_OUTPUT_LEDGER_V2_SHA256,
}
PRIVATE_OUTPUT_SOURCE_ADAPTER_V1_SOURCE_SET_SHA256 = _digest(
    _SOURCE_SET_DOMAIN, _SOURCE_SET_MATERIAL_V1
)


def private_output_source_adapter_v1_implementation_sha256() -> str:
    """Attest the semantic module AST while excluding only this self literal."""
    tree = ast.parse(Path(__file__).read_bytes(), filename=__file__)
    name = "PRIVATE_OUTPUT_SOURCE_ADAPTER_V1_IMPLEMENTATION_SHA256"
    assignments = 0
    for statement in tree.body:
        if (
            not isinstance(statement, ast.Assign)
            or len(statement.targets) != 1
            or not isinstance(statement.targets[0], ast.Name)
            or statement.targets[0].id != name
        ):
            continue
        value = statement.value
        if (
            not isinstance(value, ast.Constant)
            or type(value.value) is not str
            or len(value.value) != 64
            or any(character not in "0123456789abcdef" for character in value.value)
        ):
            raise RuntimeError("owner-private source adapter identity literal conflicts")
        assignments += 1
        statement.value = ast.Constant(value="<self-semantic-module-source-sha256>")
    stores = sum(
        isinstance(node, ast.Name)
        and isinstance(node.ctx, ast.Store)
        and node.id == name
        for node in ast.walk(tree)
    )
    if assignments != 1 or stores != 1:
        raise RuntimeError("owner-private source adapter identity assignment conflicts")
    material = ast.dump(tree, annotate_fields=True, include_attributes=False).encode(
        "utf-8"
    )
    return hashlib.sha256(_ADAPTER_DOMAIN + material).hexdigest()


PRIVATE_OUTPUT_SOURCE_ADAPTER_V1_IMPLEMENTATION_SHA256 = (
    "f2664f132befe286db889eed71ee32780b203d0d8749ef7aa514a345a43fd1ad"
)


def require_private_output_source_adapter_v1_implementation() -> None:
    """Explicit build/CI source attestation; never called by evaluation."""
    if not _same(
        private_output_source_adapter_v1_implementation_sha256(),
        PRIVATE_OUTPUT_SOURCE_ADAPTER_V1_IMPLEMENTATION_SHA256,
    ):
        raise RuntimeError("owner-private source adapter implementation conflicts")

_CONTRACT_MATERIAL_V1 = {
    "schema_version": 1,
    "adapter_id": "antiek-owner-private-output-source-adapter-v1",
    "source_set_sha256": PRIVATE_OUTPUT_SOURCE_ADAPTER_V1_SOURCE_SET_SHA256,
    "implementation_sha256": PRIVATE_OUTPUT_SOURCE_ADAPTER_V1_IMPLEMENTATION_SHA256,
    "old_evidence_policy_sha256": OWNER_PRIVATE_OUTPUT_POLICY_V2_SHA256,
    "old_evidence_checker_sha256": PRIVATE_OUTPUT_CHECKER_SHA256,
    "old_evidence_source_extractor_sha256": PRIVATE_OUTPUT_SOURCE_EXTRACTOR_SHA256,
    "checker_v2_sha256": PRIVATE_OUTPUT_CHECKER_V2_SHA256,
    "checker_v2_contract_sha256": PRIVATE_OUTPUT_CHECKER_CONTRACT_V2_SHA256,
    "checker_v2_corpus_sha256": PRIVATE_OUTPUT_EXECUTABLE_CORPUS_V2_SHA256,
    "confers_execution_authority": False,
    "confers_sink_authority": False,
    "production_consumer_enabled": False,
}
PRIVATE_OUTPUT_SOURCE_ADAPTER_V1_CONTRACT_SHA256 = _digest(
    _CONTRACT_DOMAIN, _CONTRACT_MATERIAL_V1
)


class OwnerPrivateOutputSourceAdapterContractV1(_Closed):
    schema_version: Literal[1] = 1
    adapter_id: Literal["antiek-owner-private-output-source-adapter-v1"] = (
        "antiek-owner-private-output-source-adapter-v1"
    )
    source_set_sha256: str = Field(pattern=_HEX64)
    implementation_sha256: str = Field(pattern=_HEX64)
    old_evidence_policy_sha256: str = Field(pattern=_HEX64)
    old_evidence_checker_sha256: str = Field(pattern=_HEX64)
    old_evidence_source_extractor_sha256: str = Field(pattern=_HEX64)
    checker_v2_sha256: str = Field(pattern=_HEX64)
    checker_v2_contract_sha256: str = Field(pattern=_HEX64)
    checker_v2_corpus_sha256: str = Field(pattern=_HEX64)
    confers_execution_authority: Literal[False] = False
    confers_sink_authority: Literal[False] = False
    production_consumer_enabled: Literal[False] = False
    contract_sha256: str = Field(pattern=_HEX64)

    @model_validator(mode="after")
    def _canonical(self) -> OwnerPrivateOutputSourceAdapterContractV1:
        if self.model_dump(mode="json", exclude={"contract_sha256"}) != _CONTRACT_MATERIAL_V1:
            raise ValueError("owner-private output source adapter contract conflicts")
        if not _same(self.contract_sha256, PRIVATE_OUTPUT_SOURCE_ADAPTER_V1_CONTRACT_SHA256):
            raise ValueError("owner-private output source adapter identity conflicts")
        return self


def build_owner_private_output_source_adapter_contract_v1(
) -> OwnerPrivateOutputSourceAdapterContractV1:
    return OwnerPrivateOutputSourceAdapterContractV1.model_validate(
        {
            **_CONTRACT_MATERIAL_V1,
            "contract_sha256": PRIVATE_OUTPUT_SOURCE_ADAPTER_V1_CONTRACT_SHA256,
        }
    )


class OwnerPrivateOutputSourceAdapterResultV1(_Closed):
    schema_version: Literal[1] = 1
    decision: Literal["pass", "not_applicable"]
    adapter_contract_sha256: str = Field(pattern=_HEX64)
    checker_v2_sha256: str = Field(pattern=_HEX64)
    checker_v2_contract_sha256: str = Field(pattern=_HEX64)
    checker_v2_corpus_sha256: str = Field(pattern=_HEX64)
    source_count: int = Field(ge=0, le=8)
    confers_execution_authority: Literal[False] = False
    confers_sink_authority: Literal[False] = False
    production_consumer_enabled: Literal[False] = False

    @model_validator(mode="after")
    def _canonical(self) -> OwnerPrivateOutputSourceAdapterResultV1:
        planner = self.decision == "not_applicable"
        if (
            self.adapter_contract_sha256
            != PRIVATE_OUTPUT_SOURCE_ADAPTER_V1_CONTRACT_SHA256
            or self.checker_v2_sha256 != PRIVATE_OUTPUT_CHECKER_V2_SHA256
            or self.checker_v2_contract_sha256
            != PRIVATE_OUTPUT_CHECKER_CONTRACT_V2_SHA256
            or self.checker_v2_corpus_sha256
            != PRIVATE_OUTPUT_EXECUTABLE_CORPUS_V2_SHA256
            or planner != (self.source_count == 0)
        ):
            raise ValueError("owner-private output source adapter result conflicts")
        return self


def _validated_envelope(
    envelope: PreparedOwnerPrivateEnvelopeV2,
) -> PreparedOwnerPrivateEnvelopeV2:
    if type(envelope) is not PreparedOwnerPrivateEnvelopeV2:
        raise ValueError("owner-private source adapter envelope conflicts")
    validated = PreparedOwnerPrivateEnvelopeV2.model_validate(
        envelope.model_dump(mode="python")
    )
    core = validated.request_core
    if (
        not _same(
            prepared_owner_private_envelope_v2_sha256(validated),
            validated.envelope_sha256,
        )
        or validated.envelope_id != "openv2_" + validated.envelope_sha256[:24]
        or not _same(owner_private_request_core_v2_sha256(core), core.request_core_sha256)
        or core.request_core_id != "oprc2_" + core.request_core_sha256[:24]
        or not _same(validated.request_core_v2_sha256, core.request_core_sha256)
    ):
        raise ValueError("owner-private source adapter envelope identity conflicts")
    return validated


def _resolve_receipts(
    *,
    envelope: PreparedOwnerPrivateEnvelopeV2,
    resolver: OwnerPrivateReceiptV5Resolver,
) -> tuple[OwnerPrivatePublicationSourceReceiptV5, ...]:
    rows: list[OwnerPrivatePublicationSourceReceiptV5] = []
    for expected_ordinal, member in enumerate(envelope.receipt_v5_roster, start=1):
        if member.ordinal != expected_ordinal:
            raise ValueError("owner-private source adapter roster conflicts")
        resolved = resolver.resolve_exact(
            receipt_id=member.receipt_id, receipt_sha256=member.receipt_sha256
        )
        if type(resolved) is not OwnerPrivatePublicationSourceReceiptV5:
            raise ValueError("owner-private source adapter receipt is unavailable")
        receipt = OwnerPrivatePublicationSourceReceiptV5.model_validate(
            resolved.model_dump(mode="python")
        )
        source_v4 = receipt.source_authority_v4
        if (
            receipt.private_source_ordinal != expected_ordinal
            or receipt.receipt_id != member.receipt_id
            or not _same(receipt.receipt_sha256, member.receipt_sha256)
            or not _same(
                owner_private_source_receipt_v5_sha256(receipt),
                receipt.receipt_sha256,
            )
            or receipt.receipt_id != "opsr5_" + receipt.receipt_sha256[:24]
            or not _same(
                owner_private_source_receipt_v4_sha256(source_v4),
                source_v4.receipt_sha256,
            )
            or not _same(receipt.source_authority_v4_sha256, source_v4.receipt_sha256)
        ):
            raise ValueError("owner-private source adapter receipt identity conflicts")
        rows.append(receipt)
    if len({row.receipt_id for row in rows}) != len(rows) or len(
        {row.receipt_sha256 for row in rows}
    ) != len(rows):
        raise ValueError("owner-private source adapter duplicate receipt conflicts")
    return tuple(rows)


def _joined_sources(
    *,
    envelope: PreparedOwnerPrivateEnvelopeV2,
    receipts: tuple[OwnerPrivatePublicationSourceReceiptV5, ...],
    capability: PrivateProviderProcessingCapabilityV2,
) -> tuple[
    tuple[_CheckerSourceV2, ...],
    str | None,
    int,
]:
    core = envelope.request_core
    if core.router_role == "planner":
        if core.private_sources or receipts or envelope.receipt_v5_roster:
            raise ValueError("owner-private planner source roster conflicts")
        return (), None, 0
    if not receipts or len(receipts) != len(core.private_sources):
        raise ValueError("owner-private non-planner source roster conflicts")
    checker_sources: list[_CheckerSourceV2] = []
    commitment_members: list[tuple[str, str, bytes]] = []
    expected_common = (
        core.owner_scope_sha256,
        core.operation_id,
        core.job_id,
        core.execution_id,
        core.stage_key,
        core.router_role,
        core.swarm_plan_sha256,
        core.stage_plan_sha256,
        core.route_plan_sha256,
        core.publication_manifest_sha256,
        core.required_until_ms,
    )
    for ordinal, (source, receipt) in enumerate(
        zip(core.private_sources, receipts, strict=True), start=1
    ):
        source_v4 = receipt.source_authority_v4
        exact = source.text.encode("utf-8")
        receipt_common = (
            receipt.owner_scope_sha256,
            receipt.operation_id,
            receipt.job_id,
            receipt.execution_id,
            receipt.stage_key,
            receipt.router_role,
            receipt.swarm_plan_sha256,
            receipt.stage_plan_sha256,
            receipt.route_plan_sha256,
            receipt.publication_manifest_sha256,
            receipt.required_until_ms,
        )
        if (
            source.ordinal != ordinal
            or source.alias != f"private-source-{ordinal:04d}"
            or receipt.private_source_ordinal != ordinal
            or source_v4.private_source_ordinal != ordinal
            or receipt_common != expected_common
            or not _same(receipt.request_core_v2_sha256, core.request_core_sha256)
            or not _same(
                receipt.provider_capability_v2_sha256,
                core.provider_capability_v2_sha256,
            )
            or not _same(receipt.output_policy_v2_sha256, core.output_policy_v2_sha256)
            or not _same(receipt.checker_sha256, core.checker_sha256)
            or not _same(receipt.source_extractor_sha256, core.source_extractor_sha256)
            or core.provider_effect_key != provider_effect_key(receipt.stage_key)
            or not _same(
                source_v4.provider_capability_sha256,
                capability.route_evidence_sha256,
            )
            or (
                source_v4.provider_id,
                source_v4.model_id,
                source_v4.route_key,
                source_v4.api_mode,
                source_v4.processing_region,
                source_v4.endpoint_origin_sha256,
                source_v4.account_project_scope_sha256,
                source_v4.adapter_contract_sha256,
                source_v4.dispatch_config_sha256,
            )
            != (
                core.provider_id,
                core.model_id,
                core.route_key,
                core.api_mode,
                core.processing_region,
                core.endpoint_origin_sha256,
                core.account_project_scope_sha256,
                core.adapter_contract_sha256,
                core.dispatch_config_sha256,
            )
            or not _same(
                source_v4.provider_request_sha256,
                core.route_source_evidence_v1_request_sha256,
            )
            or not _same(
                source_v4.provider_constraints_sha256,
                capability.route_evidence.provider_constraints_sha256,
            )
            or not _same(
                source_v4.output_policy_sha256,
                capability.route_evidence.output_policy_sha256,
            )
            or source_v4.max_output_bytes < core.max_output_bytes
            or not _same(hashlib.sha256(exact).hexdigest(), source_v4.excerpt_sha256)
            or len(exact) != source_v4.excerpt_bytes
            or source_v4.source_byte_end - source_v4.source_byte_start
            != source_v4.excerpt_bytes
            or len(exact) == 0
            or receipt.private_input_bytes != source_v4.private_input_bytes
            or not _same(
                receipt.private_input_commitment_sha256,
                source_v4.private_input_commitment_sha256,
            )
        ):
            raise ValueError("owner-private source adapter source join conflicts")
        checker_sources.append(_CheckerSourceV2(ordinal, exact))
        commitment_members.append((source_v4.ref_id, source_v4.source_receipt_id, exact))
    commitment, total = _private_input_commitment_from_members(tuple(commitment_members))
    if any(
        row.private_input_bytes != total
        or not _same(row.private_input_commitment_sha256, commitment)
        for row in receipts
    ):
        raise ValueError("owner-private source adapter aggregate commitment conflicts")
    return (
        tuple(checker_sources),
        commitment,
        total,
    )


def _evaluate_owner_private_output_source_adapter_v1(
    *,
    envelope: PreparedOwnerPrivateEnvelopeV2,
    receipt_resolver: OwnerPrivateReceiptV5Resolver,
    capability_registry: PrivateProviderCapabilityV2ReferenceRegistry,
    output_bytes: bytes,
    now_ms: int,
) -> OwnerPrivateOutputSourceAdapterResultV1:
    if type(output_bytes) is not bytes or not output_bytes:
        raise ValueError("owner-private source adapter output conflicts")
    checked_envelope = _validated_envelope(envelope)
    core = checked_envelope.request_core
    if (
        type(now_ms) is not int
        or isinstance(now_ms, bool)
        or type(capability_registry) is not PrivateProviderCapabilityV2ReferenceRegistry
    ):
        raise ValueError("owner-private source adapter time conflicts")
    capability = capability_registry.require_available(
        capability_sha256=core.provider_capability_v2_sha256,
        now_ms=now_ms,
        required_until_ms=core.required_until_ms,
    )
    if (
        core.router_role not in capability.allowed_router_roles
        or len(output_bytes) > core.max_output_bytes
        or core.max_output_bytes != capability.max_output_bytes
        or (
            core.provider_id,
            core.model_id,
            core.route_key,
            core.api_mode,
            core.processing_region,
            core.endpoint_origin_sha256,
            core.account_project_scope_sha256,
            core.adapter_contract_sha256,
            core.dispatch_config_sha256,
        )
        != (
            capability.route_evidence.provider_id,
            capability.route_evidence.model_id,
            capability.route_evidence.route_key,
            capability.route_evidence.api_mode,
            capability.route_evidence.processing_region,
            capability.route_evidence.endpoint_origin_sha256,
            capability.route_evidence.account_project_scope_sha256,
            capability.route_evidence.adapter_contract_sha256,
            capability.route_evidence.dispatch_config_sha256,
        )
        or not _same(core.output_policy_v2_sha256, capability.output_policy_sha256)
        or not _same(core.checker_sha256, capability.checker_sha256)
        or not _same(core.source_extractor_sha256, capability.source_extractor_sha256)
        or not _same(core.output_policy_v2_sha256, OWNER_PRIVATE_OUTPUT_POLICY_V2_SHA256)
        or not _same(core.checker_sha256, PRIVATE_OUTPUT_CHECKER_SHA256)
        or not _same(
            core.source_extractor_sha256, PRIVATE_OUTPUT_SOURCE_EXTRACTOR_SHA256
        )
    ):
        raise ValueError("owner-private source adapter capability conflicts")
    receipts = _resolve_receipts(
        envelope=checked_envelope, resolver=receipt_resolver
    )
    sources, commitment, source_bytes = _joined_sources(
        envelope=checked_envelope, receipts=receipts, capability=capability
    )
    if source_bytes > capability.route_evidence.max_private_input_bytes:
        raise ValueError("owner-private source adapter private input bound conflicts")
    parsed_output = _parse_role_output(output_bytes)
    if parsed_output.role != core.router_role:
        raise ValueError("owner-private source adapter output role conflicts")
    outcome = _check_owner_private_overlap_v2(output_bytes=output_bytes, sources=sources)
    if type(outcome) is _CheckerNotApplicableV2:
        if core.router_role != "planner" or sources:
            raise ValueError("owner-private source adapter planner decision conflicts")
        decision = "not_applicable"
    elif type(outcome) is _CheckerPassV2:
        if core.router_role == "planner" or not sources:
            raise ValueError("owner-private source adapter pass decision conflicts")
        decision = "pass"
    else:
        raise ValueError("owner-private source adapter checker decision conflicts")
    if (commitment is None) != (not sources) or source_bytes != sum(
        len(source.exact_bytes) for source in sources
    ):
        raise ValueError("owner-private source adapter internal count conflicts")
    material: dict[str, object] = {
        "schema_version": 1,
        "decision": decision,
        "adapter_contract_sha256": PRIVATE_OUTPUT_SOURCE_ADAPTER_V1_CONTRACT_SHA256,
        "checker_v2_sha256": PRIVATE_OUTPUT_CHECKER_V2_SHA256,
        "checker_v2_contract_sha256": PRIVATE_OUTPUT_CHECKER_CONTRACT_V2_SHA256,
        "checker_v2_corpus_sha256": PRIVATE_OUTPUT_EXECUTABLE_CORPUS_V2_SHA256,
        "source_count": len(sources),
        "confers_execution_authority": False,
        "confers_sink_authority": False,
        "production_consumer_enabled": False,
    }
    return OwnerPrivateOutputSourceAdapterResultV1.model_validate(material)


def evaluate_owner_private_output_source_adapter_v1(
    *,
    envelope: PreparedOwnerPrivateEnvelopeV2,
    receipt_resolver: OwnerPrivateReceiptV5Resolver,
    capability_registry: PrivateProviderCapabilityV2ReferenceRegistry,
    output_bytes: bytes,
    now_ms: int,
) -> OwnerPrivateOutputSourceAdapterResultV1:
    """Evaluate exact in-memory evidence and expose only content-free metadata."""
    try:
        return _evaluate_owner_private_output_source_adapter_v1(
            envelope=envelope,
            receipt_resolver=receipt_resolver,
            capability_registry=capability_registry,
            output_bytes=output_bytes,
            now_ms=now_ms,
        )
    except Exception:
        pass
    raise OwnerPrivateOutputSourceAdapterRejected() from None


__all__ = [
    "PRIVATE_OUTPUT_SOURCE_ADAPTER_V1_CONTRACT_SHA256",
    "PRIVATE_OUTPUT_SOURCE_ADAPTER_V1_IMPLEMENTATION_SHA256",
    "PRIVATE_OUTPUT_SOURCE_ADAPTER_V1_SOURCE_SET_SHA256",
    "OwnerPrivateOutputSourceAdapterContractV1",
    "OwnerPrivateOutputSourceAdapterRejected",
    "OwnerPrivateOutputSourceAdapterResultV1",
    "OwnerPrivateReceiptV5Resolver",
    "build_owner_private_output_source_adapter_contract_v1",
    "evaluate_owner_private_output_source_adapter_v1",
    "private_output_source_adapter_v1_implementation_sha256",
    "require_private_output_source_adapter_v1_implementation",
]
