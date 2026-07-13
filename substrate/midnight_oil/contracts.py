"""Midnight-oil no-spend preflight contract.

Midnight oil is the autonomous research-swarm mode. This module only validates
and plans the envelope: operator acknowledgement, time box, price ceiling,
route policy, source policy, and HTML artifact obligations. It never launches
agents, calls model providers, reserves budget, or performs retrieval.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
import uuid
from collections.abc import Mapping
from decimal import ROUND_FLOOR, Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

ADAPTER_KEYS: tuple[str, ...] = (
    "budget_reservation_provider",
    "model_provider_route_executor",
    "retrieval_executor_source_receipts",
    "graph_mutation_writer",
    "final_html_artifact_writer",
    "operator_live_dispatch_enablement",
    "control_ledger_audit_rollback",
)

_SIDE_EFFECT_FIELDS = (
    "dispatch_performed",
    "budget_reserved",
    "provider_calls_made",
    "retrieval_performed",
    "graph_mutated",
    "final_artifact_created",
)


class _ContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class GateReceipt(_ContractModel):
    """One inert adapter gate in a provenance-ordered no-spend chain."""

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    receipt_id: str = Field(min_length=1, max_length=256)
    run_id: str = Field(min_length=1, max_length=256)
    adapter_key: str = Field(min_length=1, max_length=128)
    status: str = Field(min_length=1, max_length=256)
    prerequisite_receipt_ids: tuple[str, ...] = ()
    dispatch_performed: bool = False
    budget_reserved: bool = False
    provider_calls_made: bool = False
    retrieval_performed: bool = False
    graph_mutated: bool = False
    final_artifact_created: bool = False
    blockers: tuple[str, ...] = ()
    required_invariants: tuple[str, ...] = ()
    notes: tuple[str, ...] = ()

    @model_validator(mode="after")
    def _no_side_effect_claims(self) -> GateReceipt:
        expected_status = f"blocked_{self.adapter_key}_unimplemented"
        if self.status != expected_status:
            raise ValueError(
                f"gate receipt {self.receipt_id} status must be {expected_status!r}"
            )
        claimed = [field for field in _SIDE_EFFECT_FIELDS if getattr(self, field)]
        if claimed:
            raise ValueError(
                f"gate receipt {self.receipt_id} cannot claim side effects: {', '.join(claimed)}"
            )
        if len(set(self.prerequisite_receipt_ids)) != len(self.prerequisite_receipt_ids):
            raise ValueError(f"gate receipt {self.receipt_id} has duplicate prerequisites")
        for field_name, values in (
            ("blockers", self.blockers),
            ("required_invariants", self.required_invariants),
            ("notes", self.notes),
        ):
            if len(values) > 64 or any(
                type(value) is not str or not value.strip() or len(value) > 2_000
                for value in values
            ):
                raise ValueError(f"gate receipt {self.receipt_id} has invalid {field_name}")
        return self


def is_known_adapter_key(adapter_key: str) -> bool:
    return type(adapter_key) is str and adapter_key in ADAPTER_KEYS


def validate_receipt_chain(receipts: list[GateReceipt]) -> None:
    """Validate provenance ordering and one-owner-per-adapter invariants."""
    if not isinstance(receipts, list):
        raise TypeError("receipt chain must be a list")
    seen_receipts: set[str] = set()
    seen_adapters: dict[str, str] = {}
    run_id: str | None = None
    for receipt in receipts:
        if not isinstance(receipt, GateReceipt):
            raise TypeError("receipt chain entries must be GateReceipt instances")
        if run_id is None:
            run_id = receipt.run_id
        elif receipt.run_id != run_id:
            raise ValueError(
                f"receipt {receipt.receipt_id} has mixed run_id {receipt.run_id!r}"
            )
        if receipt.receipt_id in seen_receipts:
            raise ValueError(f"receipt {receipt.receipt_id} has a duplicate receipt_id")
        duplicate_owner = seen_adapters.get(receipt.adapter_key)
        if duplicate_owner is not None:
            raise ValueError(
                f"receipt {receipt.receipt_id} duplicates adapter_key owned by {duplicate_owner}"
            )
        dangling = [
            prerequisite
            for prerequisite in receipt.prerequisite_receipt_ids
            if prerequisite not in seen_receipts
        ]
        if dangling:
            raise ValueError(
                f"receipt {receipt.receipt_id} has dangling prerequisite {dangling[0]}"
            )
        if any(getattr(receipt, field) for field in _SIDE_EFFECT_FIELDS):
            raise ValueError(f"receipt {receipt.receipt_id} violates the no-spend invariant")
        seen_receipts.add(receipt.receipt_id)
        seen_adapters[receipt.adapter_key] = receipt.receipt_id


RouteMode = Literal["auto_quality", "auto_balanced", "auto_cost", "auto_latency", "manual"]
SourcePolicy = Literal["arxiv", "substack", "web", "operator_corpus"]
DeliverableKind = Literal["html_research_asset"]
MidnightOilRole = Literal["planner", "gatherer", "verifier", "synthesizer"]
ResearchClaimClass = Literal["insight", "output_paragraph", "exploratory_question"]


class ResearchAcceptancePolicy(_ContractModel):
    """Closed v1 epistemic floor carried by operator-bound run authority."""

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    policy_version: Literal[1] = 1
    required_coverage: Literal["insights_and_output_paragraphs"] = "insights_and_output_paragraphs"
    exploratory_questions: Literal["operational_only"] = "operational_only"
    external_receipts: Literal["local_canonical_chunk_required"] = "local_canonical_chunk_required"
    unsupported_output: Literal["retain_operational_only"] = "retain_operational_only"
    legacy_rows: Literal["legacy_unverified"] = "legacy_unverified"


def research_acceptance_policy_from_payload(
    value: object,
) -> ResearchAcceptancePolicy | None:
    if value is None:
        return None
    return ResearchAcceptancePolicy.model_validate(value)


def _identity_hash(domain: str, fields: Mapping[str, object]) -> str:
    payload = json.dumps(
        {"domain": domain, "schema_version": 1, **fields},
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def canonical_research_claim_id(
    *,
    job_id: str,
    step_key: str,
    claim_class: ResearchClaimClass,
    ordinal: int,
    normalized_text: str,
) -> str:
    if type(ordinal) is not int or ordinal < 0:
        raise ValueError("claim ordinal must be a non-negative integer")
    for name, value in (
        ("job_id", job_id),
        ("step_key", step_key),
        ("normalized_text", normalized_text),
    ):
        if type(value) is not str or not value:
            raise ValueError(f"{name} must be a non-empty string")
    if claim_class not in {"insight", "output_paragraph", "exploratory_question"}:
        raise ValueError("claim class is unsupported")
    return _identity_hash(
        "antiek.midnight_oil.claim",
        {
            "job_id": job_id,
            "step_key": step_key,
            "claim_class": claim_class,
            "ordinal": ordinal,
            "normalized_text": normalized_text,
        },
    )


def normalize_research_paragraphs(value: str) -> tuple[str, ...]:
    if type(value) is not str:
        raise TypeError("research prose must be a string")
    normalized = value.replace("\r\n", "\n").replace("\r", "\n").strip()
    if not normalized:
        return ()
    return tuple(
        paragraph.strip() for paragraph in re.split(r"\n[ \t]*\n+", normalized) if paragraph.strip()
    )


def canonical_source_receipt_id(
    *,
    document_id: str,
    chunk_id: str,
    hash_scope: str,
    content_hash: str,
    canonical_url: str,
) -> str:
    fields = {
        "document_id": document_id,
        "chunk_id": chunk_id,
        "hash_scope": hash_scope,
        "content_hash": content_hash,
        "canonical_url": canonical_url,
    }
    if any(type(value) is not str or not value for value in fields.values()):
        raise ValueError("source receipt identity fields must be non-empty strings")
    return _identity_hash("antiek.midnight_oil.source_receipt", fields)


_ROLE_ORDER: tuple[MidnightOilRole, ...] = ("planner", "gatherer", "verifier", "synthesizer")
_BUDGET_WEIGHTS: dict[MidnightOilRole, int] = {
    "planner": 15,
    "gatherer": 45,
    "verifier": 20,
    "synthesizer": 20,
}
_TIME_WEIGHTS: dict[MidnightOilRole, int] = {
    "planner": 15,
    "gatherer": 50,
    "verifier": 15,
    "synthesizer": 20,
}


class MidnightOilRequest(_ContractModel):
    goal: str = Field(min_length=1, max_length=4000)
    work_minutes: int = Field(ge=15, le=720)
    price_ceiling_usd: float = Field(gt=0.0, le=10_000.0)
    route_mode: RouteMode = "auto_balanced"
    source_policy: list[SourcePolicy] = Field(min_length=1)
    deliverable: DeliverableKind = "html_research_asset"
    acceptance_policy: ResearchAcceptancePolicy = Field(default_factory=ResearchAcceptancePolicy)
    operator_acknowledged_spend: bool = False

    @model_validator(mode="after")
    def _source_policy_unique(self) -> MidnightOilRequest:
        if len(set(self.source_policy)) != len(self.source_policy):
            raise ValueError("source_policy entries must be unique")
        return self


class MidnightOilArtifactContract(_ContractModel):
    final_format: Literal["html"] = "html"
    pdf_allowed: bool = False
    antiek_information_asset: bool = True
    twin_note_document_required: bool = True
    route_receipt_links_required: bool = True
    source_receipt_links_required: bool = True


class MidnightOilRolePlan(_ContractModel):
    role: MidnightOilRole
    budget_usd: float = Field(ge=0.0)
    max_minutes: int = Field(ge=0)
    route_mode: RouteMode
    route_receipt_required: bool = True
    source_receipts_required: bool = True
    planned_route_receipt_id: str


class MidnightOilLaunchPacket(_ContractModel):
    packet_id: str
    run_id: str
    goal: str
    work_minutes: int
    price_ceiling_usd: float = Field(ge=0.0)
    planned_budget_usd: float = Field(ge=0.0)
    unallocated_budget_usd: float = Field(ge=0.0)
    route_mode: RouteMode
    source_policy: list[SourcePolicy]
    deliverable: DeliverableKind
    acceptance_policy: ResearchAcceptancePolicy
    artifact_contract: MidnightOilArtifactContract
    role_count: int = Field(ge=0)
    role_route_receipt_ids: list[str]
    source_receipts_required: bool = True
    route_receipts_required: bool = True
    dispatch_allowed: bool = False
    budget_reserved: bool = False
    provider_calls_made: bool = False
    launch_notes: list[str] = Field(default_factory=list)


class MidnightOilApprovalReceipt(_ContractModel):
    receipt_id: str
    launch_packet_id: str
    run_id: str
    operator_acknowledged_spend: bool = True
    approved_price_ceiling_usd: float = Field(ge=0.0)
    approved_work_minutes: int = Field(ge=0)
    approved_route_mode: RouteMode
    approved_source_policy: list[SourcePolicy]
    approved_deliverable: DeliverableKind
    approved_acceptance_policy: ResearchAcceptancePolicy
    planned_budget_usd: float = Field(ge=0.0)
    unallocated_budget_usd: float = Field(ge=0.0)
    approval_scope: Literal["preflight_launch_packet_only"] = "preflight_launch_packet_only"
    runner_apply_required: bool = True
    dispatch_allowed: bool = False
    budget_reserved: bool = False
    provider_calls_made: bool = False
    receipt_notes: list[str] = Field(default_factory=list)


class MidnightOilRunnerHandoff(_ContractModel):
    handoff_id: str
    approval_receipt_id: str
    launch_packet_id: str
    run_id: str
    acceptance_policy: ResearchAcceptancePolicy
    status: Literal["ready_for_runner_apply"] = "ready_for_runner_apply"
    approved_price_ceiling_usd: float = Field(ge=0.0)
    planned_budget_usd: float = Field(ge=0.0)
    unallocated_budget_usd: float = Field(ge=0.0)
    role_route_receipt_ids: list[str]
    prerequisite_receipt_ids: list[str]
    dispatch_ready: bool = True
    dispatch_performed: bool = False
    budget_reserved: bool = False
    provider_calls_made: bool = False
    graph_mutated: bool = False
    handoff_notes: list[str] = Field(default_factory=list)


class MidnightOilAppliedRunReceipt(_ContractModel):
    receipt_id: str
    runner_handoff_id: str
    approval_receipt_id: str
    launch_packet_id: str
    run_id: str
    acceptance_policy: ResearchAcceptancePolicy
    status: Literal["planned_not_dispatched"] = "planned_not_dispatched"
    planned_role_count: int = Field(ge=0)
    planned_budget_usd: float = Field(ge=0.0)
    unallocated_budget_usd: float = Field(ge=0.0)
    planned_role_route_receipt_ids: list[str]
    dispatch_performed: bool = False
    budget_reserved: bool = False
    provider_calls_made: bool = False
    retrieval_performed: bool = False
    graph_mutated: bool = False
    final_artifact_created: bool = False
    applied_notes: list[str] = Field(default_factory=list)


class MidnightOilPreflight(_ContractModel):
    accepted: bool
    denial_reason: str | None = None
    run_id: str | None = None
    goal: str
    work_minutes: int
    price_ceiling_usd: float
    route_mode: RouteMode
    source_policy: list[SourcePolicy]
    deliverable: DeliverableKind
    acceptance_policy: ResearchAcceptancePolicy
    planned_budget_usd: float = Field(default=0.0, ge=0.0)
    unallocated_budget_usd: float = Field(default=0.0, ge=0.0)
    role_plans: list[MidnightOilRolePlan] = Field(default_factory=list)
    artifact_contract: MidnightOilArtifactContract = Field(
        default_factory=MidnightOilArtifactContract
    )
    launch_packet: MidnightOilLaunchPacket | None = None
    approval_receipt: MidnightOilApprovalReceipt | None = None
    runner_handoff: MidnightOilRunnerHandoff | None = None
    applied_run_receipt: MidnightOilAppliedRunReceipt | None = None
    notes: list[str] = Field(default_factory=list)


def preflight_midnight_oil(req: MidnightOilRequest) -> MidnightOilPreflight:
    price_ceiling_usd = round(req.price_ceiling_usd, 2)
    if not req.operator_acknowledged_spend:
        return MidnightOilPreflight(
            accepted=False,
            denial_reason="operator_acknowledged_spend_required",
            goal=req.goal,
            work_minutes=req.work_minutes,
            price_ceiling_usd=price_ceiling_usd,
            route_mode=req.route_mode,
            source_policy=req.source_policy,
            deliverable=req.deliverable,
            acceptance_policy=req.acceptance_policy,
            planned_budget_usd=0.0,
            unallocated_budget_usd=price_ceiling_usd,
            notes=[
                "denied before dispatch: autonomous research requires explicit spend acknowledgement"
            ],
        )

    run_id = f"midnight-oil-{uuid.uuid4().hex[:12]}"
    role_plans = _role_plans(
        run_id=run_id,
        price_ceiling_usd=req.price_ceiling_usd,
        work_minutes=req.work_minutes,
        route_mode=req.route_mode,
    )
    planned_budget_usd = round(sum(plan.budget_usd for plan in role_plans), 2)
    unallocated_budget_usd = round(max(0.0, price_ceiling_usd - planned_budget_usd), 2)
    launch_packet = _launch_packet(
        run_id=run_id,
        req=req,
        price_ceiling_usd=price_ceiling_usd,
        planned_budget_usd=planned_budget_usd,
        unallocated_budget_usd=unallocated_budget_usd,
        role_plans=role_plans,
    )
    approval_receipt = _approval_receipt(
        launch_packet=launch_packet,
        operator_acknowledged_spend=req.operator_acknowledged_spend,
    )
    runner_handoff = _runner_handoff(
        launch_packet=launch_packet,
        approval_receipt=approval_receipt,
    )
    return MidnightOilPreflight(
        accepted=True,
        run_id=run_id,
        goal=req.goal,
        work_minutes=req.work_minutes,
        price_ceiling_usd=price_ceiling_usd,
        route_mode=req.route_mode,
        source_policy=req.source_policy,
        deliverable=req.deliverable,
        acceptance_policy=req.acceptance_policy,
        planned_budget_usd=planned_budget_usd,
        unallocated_budget_usd=unallocated_budget_usd,
        role_plans=role_plans,
        launch_packet=launch_packet,
        approval_receipt=approval_receipt,
        runner_handoff=runner_handoff,
        applied_run_receipt=_applied_run_receipt(
            launch_packet=launch_packet,
            approval_receipt=approval_receipt,
            runner_handoff=runner_handoff,
        ),
        notes=[
            "preflight only: no agents launched, no budget reserved, no retrieval performed",
            "each future subagent must inherit the parent ceiling through this role allocation",
        ],
    )


def _applied_run_receipt(
    *,
    launch_packet: MidnightOilLaunchPacket,
    approval_receipt: MidnightOilApprovalReceipt,
    runner_handoff: MidnightOilRunnerHandoff,
) -> MidnightOilAppliedRunReceipt:
    return MidnightOilAppliedRunReceipt(
        receipt_id=f"{launch_packet.run_id}-applied-run-receipt",
        runner_handoff_id=runner_handoff.handoff_id,
        approval_receipt_id=approval_receipt.receipt_id,
        launch_packet_id=launch_packet.packet_id,
        run_id=launch_packet.run_id,
        acceptance_policy=launch_packet.acceptance_policy,
        planned_role_count=launch_packet.role_count,
        planned_budget_usd=approval_receipt.planned_budget_usd,
        unallocated_budget_usd=approval_receipt.unallocated_budget_usd,
        planned_role_route_receipt_ids=runner_handoff.role_route_receipt_ids,
        dispatch_performed=False,
        budget_reserved=False,
        provider_calls_made=False,
        retrieval_performed=False,
        graph_mutated=False,
        final_artifact_created=False,
        applied_notes=[
            "dry applied run receipt only: no autonomous agents dispatched",
            "no budget reserved, provider calls made, retrieval performed, or graph mutation",
            "future live runner must replace this with a dispatch receipt before work starts",
        ],
    )


def _runner_handoff(
    *,
    launch_packet: MidnightOilLaunchPacket,
    approval_receipt: MidnightOilApprovalReceipt,
) -> MidnightOilRunnerHandoff:
    return MidnightOilRunnerHandoff(
        handoff_id=f"{launch_packet.run_id}-runner-handoff",
        approval_receipt_id=approval_receipt.receipt_id,
        launch_packet_id=launch_packet.packet_id,
        run_id=launch_packet.run_id,
        acceptance_policy=launch_packet.acceptance_policy,
        approved_price_ceiling_usd=approval_receipt.approved_price_ceiling_usd,
        planned_budget_usd=approval_receipt.planned_budget_usd,
        unallocated_budget_usd=approval_receipt.unallocated_budget_usd,
        role_route_receipt_ids=launch_packet.role_route_receipt_ids,
        prerequisite_receipt_ids=[launch_packet.packet_id, approval_receipt.receipt_id],
        dispatch_ready=True,
        dispatch_performed=False,
        budget_reserved=False,
        provider_calls_made=False,
        graph_mutated=False,
        handoff_notes=[
            "runner apply handoff only: ready for a future dispatcher",
            "no agents dispatched, no budget reserved, no provider calls made",
            "future runner must convert this handoff into an applied run receipt",
        ],
    )


def _approval_receipt(
    *,
    launch_packet: MidnightOilLaunchPacket,
    operator_acknowledged_spend: bool,
) -> MidnightOilApprovalReceipt:
    return MidnightOilApprovalReceipt(
        receipt_id=f"{launch_packet.run_id}-approval-receipt",
        launch_packet_id=launch_packet.packet_id,
        run_id=launch_packet.run_id,
        operator_acknowledged_spend=operator_acknowledged_spend,
        approved_price_ceiling_usd=launch_packet.price_ceiling_usd,
        approved_work_minutes=launch_packet.work_minutes,
        approved_route_mode=launch_packet.route_mode,
        approved_source_policy=launch_packet.source_policy,
        approved_deliverable=launch_packet.deliverable,
        approved_acceptance_policy=launch_packet.acceptance_policy,
        planned_budget_usd=launch_packet.planned_budget_usd,
        unallocated_budget_usd=launch_packet.unallocated_budget_usd,
        dispatch_allowed=launch_packet.dispatch_allowed,
        budget_reserved=launch_packet.budget_reserved,
        provider_calls_made=launch_packet.provider_calls_made,
        receipt_notes=[
            "operator approved the ceiling for this launch packet only",
            "runner apply is still required before any dispatch or budget reservation",
            "no provider calls or graph mutations were performed by this receipt",
        ],
    )


def _role_plans(
    *,
    run_id: str,
    price_ceiling_usd: float,
    work_minutes: int,
    route_mode: RouteMode,
) -> list[MidnightOilRolePlan]:
    cents = max(
        1,
        int((Decimal(str(price_ceiling_usd)) * 100).to_integral_value(rounding=ROUND_FLOOR)),
    )
    allocated = 0
    plans: list[MidnightOilRolePlan] = []
    for index, role in enumerate(_ROLE_ORDER):
        if index == len(_ROLE_ORDER) - 1:
            role_cents = max(0, cents - allocated)
            role_minutes = max(0, work_minutes - sum(p.max_minutes for p in plans))
        else:
            role_cents = math.floor(cents * _BUDGET_WEIGHTS[role] / 100)
            allocated += role_cents
            role_minutes = max(1, math.floor(work_minutes * _TIME_WEIGHTS[role] / 100))
        plans.append(
            MidnightOilRolePlan(
                role=role,
                budget_usd=round(role_cents / 100, 2),
                max_minutes=role_minutes,
                route_mode=route_mode,
                planned_route_receipt_id=f"{run_id}-{role}-route-receipt",
            )
        )
    return plans


def _launch_packet(
    *,
    run_id: str,
    req: MidnightOilRequest,
    price_ceiling_usd: float,
    planned_budget_usd: float,
    unallocated_budget_usd: float,
    role_plans: list[MidnightOilRolePlan],
) -> MidnightOilLaunchPacket:
    artifact_contract = MidnightOilArtifactContract()
    return MidnightOilLaunchPacket(
        packet_id=f"{run_id}-launch-packet",
        run_id=run_id,
        goal=req.goal,
        work_minutes=req.work_minutes,
        price_ceiling_usd=price_ceiling_usd,
        planned_budget_usd=planned_budget_usd,
        unallocated_budget_usd=unallocated_budget_usd,
        route_mode=req.route_mode,
        source_policy=req.source_policy,
        deliverable=req.deliverable,
        acceptance_policy=req.acceptance_policy,
        artifact_contract=artifact_contract,
        role_count=len(role_plans),
        role_route_receipt_ids=[plan.planned_route_receipt_id for plan in role_plans],
        source_receipts_required=artifact_contract.source_receipt_links_required,
        route_receipts_required=artifact_contract.route_receipt_links_required,
        launch_notes=[
            "launch packet only: no agents dispatched",
            "no budget reserved and no provider calls made",
            "future runner must attach route and source receipts before final HTML asset",
        ],
    )
