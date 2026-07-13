"""Midnight Oil job schema: create → recommend ceiling → approve."""

from __future__ import annotations

import math
import re
import uuid
from dataclasses import dataclass, field, replace
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, Literal, Protocol, cast, runtime_checkable

from substrate.dispatch.research_tier import (
    DEFAULT_RESEARCH_TIER,
    normalize_research_tier,
)

from .ceiling import ModelPricing, recommend_price_ceiling
from .contracts import (
    ResearchClaimClass,
    canonical_research_claim_id,
    canonical_source_receipt_id,
    normalize_research_paragraphs,
)

JobStatus = Literal[
    "draft",
    "awaiting_approval",
    "approved",
    "running",
    "complete",
    "timed_out",
    "budget_halted",
    "failed",
]
ClaimEvidenceStatus = Literal["supported", "unverified", "exploratory"]
_VERSIONED_SOURCE_RECEIPT_REQUIRED_KEYS = {
    "source_id",
    "document_id",
    "source_url",
    "content_hash",
    "hash_scope",
}
_VERSIONED_SOURCE_RECEIPT_KEYS = _VERSIONED_SOURCE_RECEIPT_REQUIRED_KEYS | {
    "receipt_id",
    "title",
}
_VERSIONED_ROUTE_RECEIPT_KEYS = {
    "provider",
    "model",
    "tier",
    "event_id",
    "fallback_chain_index",
    "actual_cost_usd",
}
_VERSIONED_ROUTE_RECEIPT_REQUIRED_KEYS = {"provider", "model"}


@dataclass(frozen=True)
class MidnightOilClaimEvidence:
    schema_version: Literal[1]
    claim_id: str
    claim_class: ResearchClaimClass
    ordinal: int
    normalized_text: str
    status: ClaimEvidenceStatus
    source_receipt_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class MidnightOilStepEvidence:
    """Secret-free durable result of one returned provider step."""

    step_key: str
    spawn_id: str | None
    output_text: str
    insights: tuple[str, ...]
    questions: tuple[str, ...]
    route_receipt: dict[str, object] | None = None
    source_receipts: tuple[dict[str, str], ...] = ()
    claim_evidence_schema_version: Literal[1] | None = None
    claim_evidence: tuple[MidnightOilClaimEvidence, ...] = ()


def source_receipt_id(receipt: dict[str, str]) -> str:
    identity = canonical_source_receipt_id(
        document_id=receipt.get("document_id", ""),
        chunk_id=receipt.get("source_id", ""),
        hash_scope=receipt.get("hash_scope", ""),
        content_hash=receipt.get("content_hash", ""),
        canonical_url=receipt.get("source_url", ""),
    )
    stored_identity = receipt.get("receipt_id")
    if stored_identity is not None and stored_identity != identity:
        raise ValueError("source receipt id conflicts with canonical fields")
    return identity


def _validate_versioned_source_receipt(value: object) -> None:
    if (
        not isinstance(value, dict)
        or not _VERSIONED_SOURCE_RECEIPT_REQUIRED_KEYS.issubset(value)
        or not set(value).issubset(_VERSIONED_SOURCE_RECEIPT_KEYS)
        or any(type(key) is not str or len(key) > 128 for key in value)
        or any(type(item) is not str or len(item) > 2_048 for item in value.values())
    ):
        raise ValueError("stored source receipt evidence is malformed")
    source_receipt_id(value)


def _validate_versioned_route_receipt(value: object) -> None:
    if value is None:
        return
    if (
        not isinstance(value, dict)
        or len(value) > len(_VERSIONED_ROUTE_RECEIPT_KEYS)
        or not _VERSIONED_ROUTE_RECEIPT_REQUIRED_KEYS.issubset(value)
        or not set(value).issubset(_VERSIONED_ROUTE_RECEIPT_KEYS)
        or any(
            type(item) not in {str, int, float, bool, type(None)}
            or (type(item) is str and len(item) > 2_048)
            for item in value.values()
        )
    ):
        raise ValueError("stored versioned route receipt is malformed")
    provider = value["provider"]
    model = value["model"]
    tier = value.get("tier")
    event_id = value.get("event_id")
    fallback_index = value.get("fallback_chain_index")
    actual_cost = value.get("actual_cost_usd")
    if (
        type(provider) is not str
        or not provider
        or type(model) is not str
        or not model
        or (tier is not None and (type(tier) is not str or not tier))
        or (event_id is not None and (type(event_id) is not str or not event_id))
        or (
            fallback_index is not None
            and (
                type(fallback_index) is not int
                or fallback_index < 0
                or fallback_index > 2_048
            )
        )
        or (
            actual_cost is not None
            and (
                type(actual_cost) not in {int, float}
                or actual_cost < 0
                or actual_cost > 1_000_000
                or (type(actual_cost) is float and not math.isfinite(actual_cost))
            )
        )
    ):
        raise ValueError("stored versioned route receipt is malformed")


def _claim_census(
    *,
    job_id: str,
    step_key: str,
    output_text: str,
    insights: tuple[str, ...],
    questions: tuple[str, ...],
) -> tuple[MidnightOilClaimEvidence, ...]:
    units: list[tuple[ResearchClaimClass, int, str]] = []
    units.extend(
        ("output_paragraph", ordinal, paragraph)
        for ordinal, paragraph in enumerate(normalize_research_paragraphs(output_text))
    )
    normalized_insights = tuple(text.strip() for text in insights if text.strip())
    units.extend(("insight", ordinal, text) for ordinal, text in enumerate(normalized_insights))
    normalized_questions = tuple(text.strip() for text in questions if text.strip())
    units.extend(
        ("exploratory_question", ordinal, text) for ordinal, text in enumerate(normalized_questions)
    )
    if len(units) > 2_048:
        raise ValueError("step claim census exceeds the durable bound")
    return tuple(
        MidnightOilClaimEvidence(
            schema_version=1,
            claim_id=canonical_research_claim_id(
                job_id=job_id,
                step_key=step_key,
                claim_class=claim_class,
                ordinal=ordinal,
                normalized_text=text,
            ),
            claim_class=claim_class,
            ordinal=ordinal,
            normalized_text=text,
            status=("exploratory" if claim_class == "exploratory_question" else "unverified"),
        )
        for claim_class, ordinal, text in units
    )


def build_step_claim_evidence(
    *,
    job_id: str,
    step_key: str,
    output_text: str,
    insights: tuple[str, ...],
    questions: tuple[str, ...],
    source_receipts: tuple[dict[str, str], ...],
    supported_claims: tuple[tuple[ResearchClaimClass, int, tuple[str, ...]], ...],
) -> tuple[MidnightOilClaimEvidence, ...]:
    census = _claim_census(
        job_id=job_id,
        step_key=step_key,
        output_text=output_text,
        insights=insights,
        questions=questions,
    )
    canonical_receipt_ids = [source_receipt_id(receipt) for receipt in source_receipts]
    if len(canonical_receipt_ids) != len(set(canonical_receipt_ids)):
        raise ValueError("duplicate source receipt id")
    known_receipts = set(canonical_receipt_ids)
    support_by_unit: dict[tuple[ResearchClaimClass, int], tuple[str, ...]] = {}
    for claim_class, ordinal, receipt_ids in supported_claims:
        unit = (claim_class, ordinal)
        if unit in support_by_unit:
            raise ValueError("duplicate claim support mapping")
        if claim_class == "exploratory_question":
            raise ValueError("exploratory questions cannot carry support in v1")
        if not receipt_ids or len(receipt_ids) > 100 or len(set(receipt_ids)) != len(receipt_ids):
            raise ValueError("supported claim receipts must be bounded and unique")
        if any(receipt_id not in known_receipts for receipt_id in receipt_ids):
            raise ValueError("claim support references an unknown source receipt")
        support_by_unit[unit] = receipt_ids
    census_units = {(claim.claim_class, claim.ordinal) for claim in census}
    if set(support_by_unit) - census_units:
        raise ValueError("claim support references an unknown claim")
    return tuple(
        replace(
            claim,
            status="supported",
            source_receipt_ids=support_by_unit[(claim.claim_class, claim.ordinal)],
        )
        if (claim.claim_class, claim.ordinal) in support_by_unit
        else claim
        for claim in census
    )


def validate_step_claim_evidence(job_id: str, evidence: MidnightOilStepEvidence) -> None:
    if evidence.claim_evidence_schema_version is None:
        if evidence.claim_evidence:
            raise ValueError("legacy step evidence cannot carry versioned claim records")
        return
    if evidence.claim_evidence_schema_version != 1:
        raise ValueError("claim evidence schema version is unsupported")
    if len(evidence.source_receipts) > 100:
        raise ValueError("source receipt census exceeds the durable bound")
    expected = _claim_census(
        job_id=job_id,
        step_key=evidence.step_key,
        output_text=evidence.output_text,
        insights=evidence.insights,
        questions=evidence.questions,
    )
    if len(evidence.claim_evidence) != len(expected):
        raise ValueError("claim evidence does not cover the exact step census")
    receipt_ids = [source_receipt_id(receipt) for receipt in evidence.source_receipts]
    if len(receipt_ids) != len(set(receipt_ids)):
        raise ValueError("duplicate source receipt id")
    known_receipts = set(receipt_ids)
    seen: set[str] = set()
    for actual, baseline in zip(evidence.claim_evidence, expected, strict=True):
        if actual.claim_id in seen:
            raise ValueError("duplicate claim id")
        seen.add(actual.claim_id)
        if (
            actual.schema_version != 1
            or actual.claim_id != baseline.claim_id
            or actual.claim_class != baseline.claim_class
            or actual.ordinal != baseline.ordinal
            or actual.normalized_text != baseline.normalized_text
        ):
            raise ValueError("claim evidence identity conflicts with step output")
        if actual.claim_class == "exploratory_question":
            if actual.status != "exploratory" or actual.source_receipt_ids:
                raise ValueError("exploratory claim evidence is invalid")
        elif actual.status == "supported":
            if (
                not actual.source_receipt_ids
                or len(actual.source_receipt_ids) > 100
                or len(set(actual.source_receipt_ids)) != len(actual.source_receipt_ids)
                or any(receipt_id not in known_receipts for receipt_id in actual.source_receipt_ids)
            ):
                raise ValueError("supported claim evidence is invalid")
        elif actual.status != "unverified" or actual.source_receipt_ids:
            raise ValueError("unverified claim evidence is invalid")


@dataclass(frozen=True)
class MidnightOilGraphEffectReceipt:
    """Secret-free proof that a terminal job was projected into DuckDB."""

    schema_version: int
    owner_user_id: str
    deliverable_id: str
    section_ids: tuple[str, ...]
    node_ids: tuple[str, ...]
    edge_ids: tuple[str, ...]
    html_sha256: str
    evidence_sha256: str
    deep_links: tuple[str, ...]


@dataclass(frozen=True)
class MidnightOilJob:
    job_id: str
    goals: tuple[str, ...]
    duration_minutes: int
    model_id: str | None
    recommended_price_ceiling_usd: float
    status: JobStatus
    approved_ceiling_usd: float | None = None
    spent_usd: float = 0.0
    asset_id: str | None = None
    spawn_ids: tuple[str, ...] = ()
    started_at_ms: int | None = None
    elapsed_ms: int = 0
    force_below_recommended: bool = False
    notes: str = ""
    # Residual (gs): curated research tier for autonomous runs (fast|deep|wrestle).
    research_tier: str = DEFAULT_RESEARCH_TIER
    # Residual (adb): fan-out depth used for recommended ceiling (parity formula).
    fanout_depth: int = 3
    completed_step_keys: tuple[str, ...] = ()
    returned_step_keys: tuple[str, ...] = ()
    step_evidence: tuple[MidnightOilStepEvidence, ...] = ()
    deposit_state: Literal["pending", "complete"] = "pending"
    deposit_document_id: str | None = None
    graph_projection_state: Literal["pending", "complete"] = "pending"
    graph_effect_receipt: MidnightOilGraphEffectReceipt | None = None


@runtime_checkable
class JobStore(Protocol):
    def put_job(self, job: dict[str, Any]) -> None: ...
    def get_job(self, job_id: str) -> dict[str, Any] | None: ...
    def budget_db_path(self) -> str: ...


class InvalidStoredJobDetails(ValueError):
    """A retrieved detail row cannot be decoded as a Midnight Oil job."""


@dataclass
class InMemoryJobStore:
    _jobs: dict[str, dict[str, Any]] = field(default_factory=dict)
    _budget_dir: TemporaryDirectory[str] = field(
        default_factory=TemporaryDirectory, repr=False
    )

    def put_job(self, job: dict[str, Any]) -> None:
        self._jobs[job["job_id"]] = dict(job)

    def get_job(self, job_id: str) -> dict[str, Any] | None:
        row = self._jobs.get(job_id)
        return dict(row) if row is not None else None

    def budget_db_path(self) -> str:
        """Return the store-scoped durable ledger used by its worker jobs."""
        return str(Path(self._budget_dir.name) / "midnight-oil-budget.duckdb")


def _job_to_row(job: MidnightOilJob) -> dict[str, Any]:
    for evidence in job.step_evidence:
        validate_step_claim_evidence(job.job_id, evidence)
    return {
        "job_id": job.job_id,
        "goals": list(job.goals),
        "duration_minutes": job.duration_minutes,
        "model_id": job.model_id,
        "recommended_price_ceiling_usd": job.recommended_price_ceiling_usd,
        "status": job.status,
        "approved_ceiling_usd": job.approved_ceiling_usd,
        "spent_usd": job.spent_usd,
        "asset_id": job.asset_id,
        "spawn_ids": list(job.spawn_ids),
        "started_at_ms": job.started_at_ms,
        "elapsed_ms": job.elapsed_ms,
        "force_below_recommended": job.force_below_recommended,
        "notes": job.notes,
        "research_tier": job.research_tier,
        "fanout_depth": int(job.fanout_depth),
        "completed_step_keys": list(job.completed_step_keys),
        "returned_step_keys": list(job.returned_step_keys),
        "step_evidence": [
            {
                "step_key": evidence.step_key,
                "spawn_id": evidence.spawn_id,
                "output_text": evidence.output_text,
                "insights": list(evidence.insights),
                "questions": list(evidence.questions),
                "route_receipt": evidence.route_receipt,
                "source_receipts": [dict(item) for item in evidence.source_receipts],
                "claim_evidence_schema_version": evidence.claim_evidence_schema_version,
                "claim_evidence": [
                    {
                        "schema_version": claim.schema_version,
                        "claim_id": claim.claim_id,
                        "claim_class": claim.claim_class,
                        "ordinal": claim.ordinal,
                        "normalized_text": claim.normalized_text,
                        "status": claim.status,
                        "source_receipt_ids": list(claim.source_receipt_ids),
                    }
                    for claim in evidence.claim_evidence
                ],
            }
            for evidence in job.step_evidence
        ],
        "deposit_state": job.deposit_state,
        "deposit_document_id": job.deposit_document_id,
        "graph_projection_state": job.graph_projection_state,
        "graph_effect_receipt": (
            None
            if job.graph_effect_receipt is None
            else {
                "schema_version": job.graph_effect_receipt.schema_version,
                "owner_user_id": job.graph_effect_receipt.owner_user_id,
                "deliverable_id": job.graph_effect_receipt.deliverable_id,
                "section_ids": list(job.graph_effect_receipt.section_ids),
                "node_ids": list(job.graph_effect_receipt.node_ids),
                "edge_ids": list(job.graph_effect_receipt.edge_ids),
                "html_sha256": job.graph_effect_receipt.html_sha256,
                "evidence_sha256": job.graph_effect_receipt.evidence_sha256,
                "deep_links": list(job.graph_effect_receipt.deep_links),
            }
        ),
    }


def _decode_claim_evidence(value: object) -> MidnightOilClaimEvidence:
    if not isinstance(value, dict) or set(value) != {
        "schema_version",
        "claim_id",
        "claim_class",
        "ordinal",
        "normalized_text",
        "status",
        "source_receipt_ids",
    }:
        raise ValueError("stored claim evidence is malformed")
    claim_id = value.get("claim_id")
    claim_class = value.get("claim_class")
    ordinal = value.get("ordinal")
    normalized_text = value.get("normalized_text")
    status = value.get("status")
    receipt_ids = value.get("source_receipt_ids")
    if (
        value.get("schema_version") != 1
        or type(claim_id) is not str
        or re.fullmatch(r"[0-9a-f]{64}", claim_id) is None
        or claim_class not in {"insight", "output_paragraph", "exploratory_question"}
        or type(ordinal) is not int
        or ordinal < 0
        or type(normalized_text) is not str
        or not normalized_text
        or len(normalized_text) > 200_000
        or status not in {"supported", "unverified", "exploratory"}
        or not isinstance(receipt_ids, list)
        or len(receipt_ids) > 100
        or any(
            type(receipt_id) is not str or re.fullmatch(r"[0-9a-f]{64}", receipt_id) is None
            for receipt_id in receipt_ids
        )
    ):
        raise ValueError("stored claim evidence is malformed")
    return MidnightOilClaimEvidence(
        schema_version=1,
        claim_id=claim_id,
        claim_class=cast(ResearchClaimClass, claim_class),
        ordinal=ordinal,
        normalized_text=normalized_text,
        status=cast(ClaimEvidenceStatus, status),
        source_receipt_ids=tuple(receipt_ids),
    )


def _decode_claim_schema_version(value: object) -> Literal[1] | None:
    if value is None:
        return None
    if type(value) is int and value == 1:
        return 1
    raise ValueError("claim evidence schema version is unsupported")


def _decode_claim_records(value: object) -> tuple[MidnightOilClaimEvidence, ...]:
    if not isinstance(value, list) or len(value) > 2_048:
        raise ValueError("stored claim evidence is malformed")
    return tuple(_decode_claim_evidence(claim) for claim in value)


def _decode_source_receipts(
    value: object, *, claim_schema_version: Literal[1] | None
) -> tuple[dict[str, str], ...]:
    if claim_schema_version is None:
        legacy_receipts = value if isinstance(value, (list, tuple)) else ()
        return tuple(
            {str(key): str(item) for key, item in receipt.items()}
            for receipt in legacy_receipts
            if isinstance(receipt, dict)
        )
    if not isinstance(value, list) or len(value) > 100:
        raise ValueError("stored source receipt evidence is malformed")
    receipts: list[dict[str, str]] = []
    for receipt in value:
        _validate_versioned_source_receipt(receipt)
        receipts.append(dict(receipt))
    return tuple(receipts)


_VERSIONED_STEP_EVIDENCE_KEYS = {
    "step_key",
    "spawn_id",
    "output_text",
    "insights",
    "questions",
    "route_receipt",
    "source_receipts",
    "claim_evidence_schema_version",
    "claim_evidence",
}


def _decode_step_evidence(value: object) -> MidnightOilStepEvidence | None:
    if not isinstance(value, dict):
        raise ValueError("stored step evidence is malformed")
    claim_schema_version = _decode_claim_schema_version(value.get("claim_evidence_schema_version"))
    if claim_schema_version is None:
        if not value.get("step_key"):
            return None
        return MidnightOilStepEvidence(
            step_key=str(value["step_key"]),
            spawn_id=(None if value.get("spawn_id") is None else str(value["spawn_id"])),
            output_text=str(value.get("output_text") or ""),
            insights=tuple(str(item) for item in value.get("insights") or ()),
            questions=tuple(str(item) for item in value.get("questions") or ()),
            route_receipt=(
                dict(value["route_receipt"])
                if isinstance(value.get("route_receipt"), dict)
                else None
            ),
            source_receipts=_decode_source_receipts(
                value.get("source_receipts", []), claim_schema_version=None
            ),
            claim_evidence_schema_version=None,
            claim_evidence=_decode_claim_records(value.get("claim_evidence", [])),
        )
    step_key = value.get("step_key")
    spawn_id = value.get("spawn_id")
    output_text = value.get("output_text")
    insights = value.get("insights")
    questions = value.get("questions")
    route_receipt = value.get("route_receipt")
    _validate_versioned_route_receipt(route_receipt)
    if (
        set(value) != _VERSIONED_STEP_EVIDENCE_KEYS
        or type(step_key) is not str
        or not step_key
        or len(step_key) > 512
        or (spawn_id is not None and (type(spawn_id) is not str or len(spawn_id) > 512))
        or type(output_text) is not str
        or len(output_text) > 200_000
        or not isinstance(insights, list)
        or len(insights) > 100
        or any(type(item) is not str or len(item) > 20_000 for item in insights)
        or not isinstance(questions, list)
        or len(questions) > 100
        or any(type(item) is not str or len(item) > 20_000 for item in questions)
    ):
        raise ValueError("stored versioned step evidence is malformed")
    return MidnightOilStepEvidence(
        step_key=step_key,
        spawn_id=spawn_id,
        output_text=output_text,
        insights=tuple(insights),
        questions=tuple(questions),
        route_receipt=None if route_receipt is None else dict(route_receipt),
        source_receipts=_decode_source_receipts(
            value.get("source_receipts"), claim_schema_version=claim_schema_version
        ),
        claim_evidence_schema_version=claim_schema_version,
        claim_evidence=_decode_claim_records(value.get("claim_evidence")),
    )


def _decode_step_evidence_census(value: object) -> tuple[MidnightOilStepEvidence, ...]:
    if not isinstance(value, (list, tuple)) or len(value) > 2_048:
        raise ValueError("stored step evidence census is malformed")
    decoded = tuple(_decode_step_evidence(item) for item in value)
    return tuple(item for item in decoded if item is not None)


def _job_from_row(row: dict[str, Any]) -> MidnightOilJob:
    fanout = int(row.get("fanout_depth") or 3)
    if fanout <= 0:
        fanout = 3
    raw_graph_receipt = row.get("graph_effect_receipt")
    graph_receipt: MidnightOilGraphEffectReceipt | None = None
    if isinstance(raw_graph_receipt, dict):
        html_hash = raw_graph_receipt.get("html_sha256")
        evidence_hash = raw_graph_receipt.get("evidence_sha256")
        owner = raw_graph_receipt.get("owner_user_id")
        deliverable = raw_graph_receipt.get("deliverable_id")
        section_values = raw_graph_receipt.get("section_ids")
        node_values = raw_graph_receipt.get("node_ids")
        edge_values = raw_graph_receipt.get("edge_ids")
        link_values = raw_graph_receipt.get("deep_links")

        def checked_ids(value: object, prefix: str, limit: int) -> tuple[str, ...] | None:
            if not isinstance(value, list) or len(value) > limit:
                return None
            if any(
                not isinstance(item, str)
                or re.fullmatch(rf"{prefix}-[0-9a-f]{{16}}", item) is None
                for item in value
            ):
                return None
            result = tuple(value)
            return result if len(result) == len(set(result)) else None

        sections = checked_ids(section_values, "sec", 1024)
        nodes = checked_ids(node_values, "node", 4096)
        edges = checked_ids(edge_values, "edge", 8192)
        if (
            raw_graph_receipt.get("schema_version") == 1
            and isinstance(owner, str)
            and owner == owner.strip()
            and 0 < len(owner) <= 256
            and isinstance(deliverable, str)
            and re.fullmatch(r"dlv-[0-9a-f]{16}", deliverable) is not None
            and sections is not None
            and bool(sections)
            and nodes is not None
            and bool(nodes)
            and edges is not None
            and isinstance(html_hash, str)
            and re.fullmatch(r"[0-9a-f]{64}", html_hash) is not None
            and isinstance(evidence_hash, str)
            and re.fullmatch(r"[0-9a-f]{64}", evidence_hash) is not None
            and isinstance(link_values, list)
        ):
            expected_links = (
                f"antiek://deliverable/{deliverable}",
                *(f"antiek://node/{node_id}" for node_id in nodes),
            )
            if tuple(link_values) == expected_links:
                graph_receipt = MidnightOilGraphEffectReceipt(
                    schema_version=1,
                    owner_user_id=owner,
                    deliverable_id=deliverable,
                    section_ids=sections,
                    node_ids=nodes,
                    edge_ids=edges,
                    html_sha256=html_hash,
                    evidence_sha256=evidence_hash,
                    deep_links=expected_links,
                )
    graph_complete = (
        row.get("graph_projection_state") == "complete"
        and graph_receipt is not None
        and bool(graph_receipt.owner_user_id)
        and bool(graph_receipt.deliverable_id)
    )
    job = MidnightOilJob(
        job_id=row["job_id"],
        goals=tuple(row.get("goals") or ()),
        duration_minutes=int(row["duration_minutes"]),
        model_id=row.get("model_id"),
        recommended_price_ceiling_usd=float(row["recommended_price_ceiling_usd"]),
        status=row["status"],
        approved_ceiling_usd=(
            None
            if row.get("approved_ceiling_usd") is None
            else float(row["approved_ceiling_usd"])
        ),
        spent_usd=float(row.get("spent_usd") or 0.0),
        asset_id=row.get("asset_id"),
        spawn_ids=tuple(row.get("spawn_ids") or ()),
        started_at_ms=row.get("started_at_ms"),
        elapsed_ms=int(row.get("elapsed_ms") or 0),
        force_below_recommended=bool(row.get("force_below_recommended") or False),
        notes=str(row.get("notes") or ""),
        research_tier=normalize_research_tier(row.get("research_tier")),
        fanout_depth=fanout,
        completed_step_keys=tuple(row.get("completed_step_keys") or ()),
        returned_step_keys=tuple(row.get("returned_step_keys") or ()),
        step_evidence=_decode_step_evidence_census(row.get("step_evidence") or ()),
        deposit_state=(
            "complete" if row.get("deposit_state") == "complete" else "pending"
        ),
        deposit_document_id=(
            None
            if row.get("deposit_document_id") is None
            else str(row["deposit_document_id"])
        ),
        graph_projection_state="complete" if graph_complete else "pending",
        graph_effect_receipt=graph_receipt if graph_complete else None,
    )
    for evidence in job.step_evidence:
        validate_step_claim_evidence(job.job_id, evidence)
    return job


def create_job(
    goals: list[str] | tuple[str, ...],
    duration_minutes: int,
    *,
    store: JobStore,
    model_id: str | None = None,
    fanout_depth: int = 3,
    pricing: ModelPricing | None = None,
    job_id: str | None = None,
    asset_id: str | None = None,
    research_tier: str | None = None,
) -> MidnightOilJob:
    """Create a draft Midnight Oil job with a recommended price ceiling.

    Does **not** start work — operator must ``approve_job`` first.
    """
    cleaned = tuple(g.strip() for g in goals if g and str(g).strip())
    if not cleaned:
        raise ValueError("at least one non-empty goal is required")
    if duration_minutes <= 0:
        raise ValueError("duration_minutes must be positive")

    jid = job_id or f"moil_{uuid.uuid4().hex[:16]}"
    tier = normalize_research_tier(research_tier)
    # Residual (jl): ceiling recommendation scales with research_tier.
    ceiling = recommend_price_ceiling(
        duration_minutes,
        model_id=model_id,
        fanout_depth=fanout_depth,
        pricing=pricing,
        research_tier=tier,
    )
    job = MidnightOilJob(
        job_id=jid,
        goals=cleaned,
        duration_minutes=duration_minutes,
        model_id=model_id,
        recommended_price_ceiling_usd=ceiling,
        status="awaiting_approval",
        asset_id=asset_id or f"moil_asset_{jid.removeprefix('moil_')}",
        research_tier=tier,
        # Residual (adb): persist fanout used for ceiling so API/UI formula match.
        fanout_depth=int(fanout_depth) if int(fanout_depth) > 0 else 3,
    )
    store.put_job(_job_to_row(job))
    return job


def approve_job(
    job_id: str,
    ceiling_usd: float,
    *,
    store: JobStore,
    force_below: bool = False,
) -> MidnightOilJob:
    """Explicitly approve a price ceiling before the worker may run.

    Requires ``ceiling_usd >= recommended`` unless ``force_below`` is True
    (operator override with a recorded warning note).
    """
    row = store.get_job(job_id)
    if row is None:
        raise KeyError(f"unknown job_id: {job_id}")
    job = _job_from_row(row)
    if job.status not in ("awaiting_approval", "draft"):
        raise ValueError(f"job {job_id} status is {job.status!r}; cannot approve")
    if ceiling_usd <= 0:
        raise ValueError("ceiling_usd must be positive")
    if ceiling_usd < job.recommended_price_ceiling_usd and not force_below:
        raise ValueError(
            f"ceiling_usd {ceiling_usd} is below recommended "
            f"{job.recommended_price_ceiling_usd}; pass force_below=True to override"
        )
    notes = job.notes
    if ceiling_usd < job.recommended_price_ceiling_usd and force_below:
        notes = (
            notes + " | "
            if notes
            else ""
        ) + (
            f"force_below: approved {ceiling_usd} < recommended "
            f"{job.recommended_price_ceiling_usd}"
        )
    updated = replace(
        job,
        status="approved",
        approved_ceiling_usd=float(ceiling_usd),
        force_below_recommended=bool(
            force_below and ceiling_usd < job.recommended_price_ceiling_usd
        ),
        notes=notes,
    )
    store.put_job(_job_to_row(updated))
    return updated


def get_job(job_id: str, *, store: JobStore) -> MidnightOilJob | None:
    row = store.get_job(job_id)
    if not row:
        return None
    try:
        return _job_from_row(row)
    except (KeyError, TypeError, ValueError) as exc:
        raise InvalidStoredJobDetails("stored Midnight Oil job is invalid") from exc


def put_job_state(job: MidnightOilJob, *, store: JobStore) -> MidnightOilJob:
    store.put_job(_job_to_row(job))
    return job
