"""Midnight Oil job schema: create → recommend ceiling → approve."""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field, replace
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, Literal, Protocol, runtime_checkable

from substrate.dispatch.research_tier import (
    DEFAULT_RESEARCH_TIER,
    normalize_research_tier,
)

from .ceiling import ModelPricing, recommend_price_ceiling

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
    return MidnightOilJob(
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
        step_evidence=tuple(
            MidnightOilStepEvidence(
                step_key=str(item["step_key"]),
                spawn_id=(
                    None if item.get("spawn_id") is None else str(item["spawn_id"])
                ),
                output_text=str(item.get("output_text") or ""),
                insights=tuple(str(value) for value in item.get("insights") or ()),
                questions=tuple(str(value) for value in item.get("questions") or ()),
                route_receipt=(
                    dict(item["route_receipt"])
                    if isinstance(item.get("route_receipt"), dict)
                    else None
                ),
                source_receipts=tuple(
                    {str(key): str(value) for key, value in receipt.items()}
                    for receipt in item.get("source_receipts") or ()
                    if isinstance(receipt, dict)
                ),
            )
            for item in row.get("step_evidence") or ()
            if isinstance(item, dict) and item.get("step_key")
        ),
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
    return _job_from_row(row) if row else None


def put_job_state(job: MidnightOilJob, *, store: JobStore) -> MidnightOilJob:
    store.put_job(_job_to_row(job))
    return job
