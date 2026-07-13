"""Idempotent Midnight Oil projection into Antiek's durable knowledge graph.

Projection is deliberately downstream of paid-result settlement and the
engagement-spine HTML/twin deposit.  SQLite job state and DuckDB cannot commit
atomically, so every graph identifier is deterministic and replay is the
recovery protocol for a crash after DuckDB commit but before receipt checkpoint.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import NoReturn, cast

from runtime.db_lock import LockedConnection, WriteLockTimeout, connect_write
from substrate.engagement_spine import project_to_html
from substrate.engagement_spine.store import EngagementStore
from substrate.event_log import (
    Event,
    event_append_batch,
    prepare_typed_event,
)
from substrate.graph.ops import content_addressed_id
from substrate.schemas.events import (
    GraphEdgeInsertedPayload,
    GraphNodeInsertedPayload,
    NodeType,
)

from .claim_admission import (
    REFUSED_GRAPH_ADMISSION_REASONS,
    RETRYABLE_GRAPH_ADMISSION_REASONS,
    verify_claim_admission,
)
from .contracts import (
    GraphAdmissionReason,
    research_acceptance_policy_from_authority,
)
from .job import (
    JobStore,
    MidnightOilGraphEffectReceipt,
    MidnightOilJob,
    get_job,
    source_receipt_id,
)
from .job_store import OperationState, OwnerJobStore

_TERMINAL_STATUSES = {"complete", "timed_out", "budget_halted", "failed"}
_SCHEMA_VERSION = 1


class GraphProjectionNotReady(ValueError):
    """The terminal/deposit/evidence preconditions are not satisfied."""


class GraphProjectionConflict(RuntimeError):
    """Durable graph state contradicts the deterministic projection."""


class GraphProjectionRefused(GraphProjectionConflict):
    """Projection is permanently refused under the approved v1 policy."""

    def __init__(self, reason: GraphAdmissionReason, message: str | None = None) -> None:
        self.reason = reason
        super().__init__(message or reason)


class GraphProjectionPending(GraphProjectionNotReady):
    """Projection is safe to retry without redispatching research."""

    def __init__(self, reason: GraphAdmissionReason, message: str | None = None) -> None:
        self.reason = reason
        super().__init__(message or reason)


def _durable_metadata(value: object, *, label: str) -> dict[str, object]:
    try:
        decoded = json.loads(str(value))
    except (TypeError, ValueError) as exc:
        raise GraphProjectionRefused(
            "deterministic_row_conflict", f"{label} metadata is not valid JSON"
        ) from exc
    if not isinstance(decoded, dict):
        raise GraphProjectionRefused(
            "deterministic_row_conflict", f"{label} metadata is not an object"
        )
    return decoded


@dataclass(frozen=True)
class GraphProjectionResult:
    job: MidnightOilJob
    receipt: MidnightOilGraphEffectReceipt


def _checkpoint_disposition(
    job: MidnightOilJob,
    reason: GraphAdmissionReason,
    *,
    store: JobStore,
) -> MidnightOilJob:
    if job.graph_effect_receipt is not None:
        raise GraphProjectionConflict("graph admission changed after a durable effect receipt")
    if reason in REFUSED_GRAPH_ADMISSION_REASONS:
        updated = replace(
            job,
            graph_projection_state="refused",
            graph_projection_reason=reason,
            graph_effect_receipt=None,
        )
    elif reason in RETRYABLE_GRAPH_ADMISSION_REASONS:
        updated = replace(
            job,
            graph_projection_state="pending",
            graph_projection_reason=reason,
            graph_effect_receipt=None,
        )
    else:  # pragma: no cover - closed Literal defense
        raise ValueError("graph admission reason is unsupported")
    if not store.compare_and_put_graph(job, updated):
        current = get_job(job.job_id, store=store)
        if current is None:
            raise GraphProjectionConflict("graph disposition lost its durable job")
        if current.graph_projection_state == "complete":
            raise GraphProjectionConflict("graph disposition raced with a durable effect receipt")
        if current.graph_projection_state == "refused":
            current_reason = current.graph_projection_reason
            if current_reason not in REFUSED_GRAPH_ADMISSION_REASONS:
                raise GraphProjectionConflict("concurrent graph refusal lacks a reason")
            raise GraphProjectionRefused(current_reason)
        raise GraphProjectionPending(
            current.graph_projection_reason or "operational_artifact_pending"
        )
    return updated


def _raise_disposition(
    job: MidnightOilJob,
    reason: GraphAdmissionReason,
    *,
    store: JobStore,
    message: str | None = None,
) -> NoReturn:
    _checkpoint_disposition(job, reason, store=store)
    if reason in REFUSED_GRAPH_ADMISSION_REASONS:
        raise GraphProjectionRefused(reason, message)
    raise GraphProjectionPending(reason, message)


def _canonical_evidence(job: MidnightOilJob) -> bytes:
    return json.dumps(
        [
            {
                "step_key": evidence.step_key,
                "spawn_id": evidence.spawn_id,
                "output_text": evidence.output_text,
                "insights": evidence.insights,
                "questions": evidence.questions,
                "route_receipt": evidence.route_receipt,
                "source_receipts": evidence.source_receipts,
                "claim_evidence_schema_version": evidence.claim_evidence_schema_version,
                "claim_evidence": [
                    {
                        "schema_version": claim.schema_version,
                        "claim_id": claim.claim_id,
                        "claim_class": claim.claim_class,
                        "ordinal": claim.ordinal,
                        "normalized_text": claim.normalized_text,
                        "status": claim.status,
                        "source_receipt_ids": claim.source_receipt_ids,
                    }
                    for claim in evidence.claim_evidence
                ],
            }
            for evidence in job.step_evidence
        ],
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")


def _title(job: MidnightOilJob) -> str:
    # Goals are prompt material and can contain credentials or private source
    # names.  The graph title is an opaque job label; exact goals remain only
    # in the owner/detail stores that already carry the research request.
    return f"Midnight Oil research {job.job_id}"


def _html_hash(html: str) -> str:
    if "<html" not in html.lower():
        raise GraphProjectionNotReady("graph projection requires an HTML artifact")
    return hashlib.sha256(html.encode("utf-8")).hexdigest()


def _source_hash_matches(
    con: LockedConnection,
    *,
    document_id: str,
    chunk_id: str,
    content_hash: str,
) -> bool:
    row = con.execute(
        "SELECT text FROM chunks WHERE chunk_id = ? AND document_id = ? LIMIT 1",
        [chunk_id, document_id],
    ).fetchone()
    return bool(
        row is not None
        and len(content_hash) == 64
        and hashlib.sha256(str(row[0]).encode("utf-8")).hexdigest() == content_hash
    )


def _deposited_html(job: MidnightOilJob, store: EngagementStore) -> str:
    if not job.deposit_document_id:
        raise GraphProjectionNotReady("graph projection requires a deposit document id")
    document = store.get_document(job.deposit_document_id)
    if not isinstance(document, dict):
        raise GraphProjectionNotReady("deposited engagement document is unavailable")
    model = document.get("doc_model")
    if not isinstance(model, dict):
        raise GraphProjectionNotReady("deposited engagement document lacks its model")
    return project_to_html(
        model,
        document_id=job.deposit_document_id,
        creator="midnight_oil",
    )


def _authority_is_terminal(job: MidnightOilJob, state: OperationState) -> bool:
    allowed: dict[str, frozenset[OperationState]] = {
        "complete": frozenset({OperationState.COMPLETE}),
        "timed_out": frozenset({OperationState.TIMED_OUT}),
        "budget_halted": frozenset({OperationState.BUDGET_HALTED}),
        "failed": frozenset(
            {
                OperationState.FAILED,
                OperationState.STEP_CAPPED,
                OperationState.FAILED_RECONCILE,
            }
        ),
    }
    return state in allowed.get(job.status, frozenset())


def _insert_deliverable_once(
    con: LockedConnection,
    *,
    deliverable_id: str,
    title: str,
    investigation_id: str,
    owner_user_id: str,
    metadata: dict[str, object],
) -> None:
    con.execute(
        "INSERT INTO deliverables "
        "(deliverable_id, title, deliverable_kind, investigation_root_id, "
        " owner_user_id, metadata) VALUES (?, ?, 'research_memo', ?, ?, ?) "
        "ON CONFLICT (deliverable_id) DO NOTHING",
        [
            deliverable_id,
            title,
            investigation_id,
            owner_user_id,
            json.dumps(metadata, sort_keys=True, separators=(",", ":")),
        ],
    )


def _insert_section_once(
    con: LockedConnection,
    *,
    section_id: str,
    deliverable_id: str,
    section_index: int,
    title: str,
    prose_text: str,
    provenance: dict[str, object],
) -> None:
    con.execute(
        "INSERT INTO deliverable_sections "
        "(section_id, deliverable_id, section_index, title, prose_text, "
        " prose_provenance) VALUES (?, ?, ?, ?, ?, ?) "
        "ON CONFLICT (section_id) DO NOTHING",
        [
            section_id,
            deliverable_id,
            section_index,
            title,
            prose_text,
            json.dumps(provenance, sort_keys=True, separators=(",", ":")),
        ],
    )


def _insert_node_once(
    con: LockedConnection,
    *,
    node_id: str,
    label: str,
    node_type: str,
    metadata: dict[str, object],
) -> None:
    con.execute(
        "INSERT INTO nodes "
        "(node_id, canonical_label, node_type, embedding, graph_scope, metadata, created_at) "
        "VALUES (?, ?, ?, NULL, 'depth', ?, ?)",
        [
            node_id,
            label,
            node_type,
            json.dumps(metadata, sort_keys=True, separators=(",", ":")),
            datetime(1970, 1, 1),
        ],
    )


def _insert_edge_once(
    con: LockedConnection,
    *,
    edge_id: str,
    source_node_id: str,
    target_node_id: str,
    document_id: str,
    chunk_id: str,
    investigation_id: str,
    metadata: dict[str, object],
) -> None:
    con.execute(
        "INSERT INTO edges "
        "(edge_id, source_node_id, target_node_id, relation, chunk_id, "
        "source_document_id, source_tier, extraction_confidence, valid_from, "
        "graph_scope, investigation_id, metadata, extracted_at) "
        "VALUES (?, ?, ?, 'contains', ?, ?, 1, 1.0, ?, 'depth', ?, ?, ?)",
        [
            edge_id,
            source_node_id,
            target_node_id,
            chunk_id,
            document_id,
            datetime(1970, 1, 1),
            investigation_id,
            json.dumps(metadata, sort_keys=True, separators=(",", ":")),
            datetime(1970, 1, 1),
        ],
    )


@dataclass(frozen=True)
class _ProjectionPlan:
    investigation_id: str
    deliverable_id: str
    deliverable_title: str
    deliverable_metadata: dict[str, object]
    root_node_id: str
    sections: tuple[tuple[str, int, str, str, dict[str, object]], ...]
    nodes: tuple[tuple[str, str, str, dict[str, object]], ...]
    edges: tuple[tuple[str, str, str, str, str, dict[str, object]], ...]
    cited_receipts: tuple[dict[str, str], ...]


@dataclass(frozen=True)
class _MissingRows:
    deliverable: bool
    section_ids: frozenset[str]
    node_ids: frozenset[str]
    edge_ids: frozenset[str]


def _build_projection_plan(
    job: MidnightOilJob,
    *,
    owner_user_id: str,
    html_sha256: str,
    evidence_sha256: str,
    source_sha256: str,
) -> _ProjectionPlan:
    investigation_id = f"midnight-oil:{job.job_id}"
    deliverable_id = content_addressed_id("dlv", f"midnight-oil|{job.job_id}|{source_sha256}")
    root_node_id = content_addressed_id("node", f"midnight-oil-root|{job.job_id}|{source_sha256}")
    deliverable_metadata: dict[str, object] = {
        "schema_version": _SCHEMA_VERSION,
        "job_id": job.job_id,
        "deposit_document_id": job.deposit_document_id,
        "html_sha256": html_sha256,
        "evidence_sha256": evidence_sha256,
        "source_sha256": source_sha256,
    }
    root_metadata: dict[str, object] = {
        "kind": "midnight_oil_deliverable",
        "deliverable_id": deliverable_id,
        "document_id": job.deposit_document_id,
        "html_sha256": html_sha256,
        "source_sha256": source_sha256,
    }
    sections: list[tuple[str, int, str, str, dict[str, object]]] = []
    nodes: list[tuple[str, str, str, dict[str, object]]] = [
        (root_node_id, _title(job), "entity", root_metadata)
    ]
    edges: list[tuple[str, str, str, str, str, dict[str, object]]] = []
    cited_receipts: dict[str, dict[str, str]] = {}
    for step_index, evidence in enumerate(job.step_evidence):
        receipt_by_id = {
            source_receipt_id(receipt): receipt for receipt in evidence.source_receipts
        }
        supported = tuple(claim for claim in evidence.claim_evidence if claim.status == "supported")
        referenced_ids = {
            receipt_id for claim in supported for receipt_id in claim.source_receipt_ids
        }
        for receipt_id in sorted(referenced_ids):
            cited_receipts[receipt_id] = receipt_by_id[receipt_id]
        section_id = content_addressed_id("sec", f"{deliverable_id}|{evidence.step_key}")
        provenance: dict[str, object] = {
            "step_key": evidence.step_key,
            "spawn_id": evidence.spawn_id,
            "route_receipt": evidence.route_receipt,
            "source_receipts": [
                receipt
                for receipt_id, receipt in receipt_by_id.items()
                if receipt_id in referenced_ids
            ],
            "admitted_claim_ids": [claim.claim_id for claim in supported],
        }
        sections.append(
            (
                section_id,
                step_index,
                f"Research step {step_index + 1}",
                evidence.output_text,
                provenance,
            )
        )
        for claim in supported:
            node_type = "insight" if claim.claim_class == "insight" else "claim"
            node_id = content_addressed_id(
                "node", f"midnight-oil-claim|{claim.claim_id}|{source_sha256}"
            )
            node_metadata: dict[str, object] = {
                "job_id": job.job_id,
                "step_key": evidence.step_key,
                "section_id": section_id,
                "claim_id": claim.claim_id,
                "claim_class": claim.claim_class,
                "ordinal": claim.ordinal,
            }
            nodes.append((node_id, claim.normalized_text[:4096], node_type, node_metadata))
            for receipt_id in claim.source_receipt_ids:
                receipt = receipt_by_id[receipt_id]
                document_id = receipt["document_id"]
                chunk_id = receipt["source_id"]
                edge_id = content_addressed_id(
                    "edge", f"{root_node_id}|contains|{node_id}|{receipt_id}"
                )
                edge_metadata: dict[str, object] = {
                    "job_id": job.job_id,
                    "step_key": evidence.step_key,
                    "claim_id": claim.claim_id,
                    "source_receipt_id": receipt_id,
                }
                edges.append(
                    (
                        edge_id,
                        root_node_id,
                        node_id,
                        document_id,
                        chunk_id,
                        edge_metadata,
                    )
                )
    return _ProjectionPlan(
        investigation_id=investigation_id,
        deliverable_id=deliverable_id,
        deliverable_title=_title(job),
        deliverable_metadata=deliverable_metadata,
        root_node_id=root_node_id,
        sections=tuple(sections),
        nodes=tuple(nodes),
        edges=tuple(edges),
        cited_receipts=tuple(cited_receipts.values()),
    )


def _require_projection_schema(con: LockedConnection) -> None:
    required = {"documents", "chunks", "deliverables", "deliverable_sections", "nodes", "edges"}
    rows = con.execute(
        "SELECT table_name FROM information_schema.tables WHERE table_schema = 'main'"
    ).fetchall()
    if not required.issubset({str(row[0]) for row in rows}):
        raise GraphProjectionPending(
            "operational_artifact_pending",
            "graph schema must be initialized before projection",
        )


def _validate_cited_receipts(con: LockedConnection, receipts: tuple[dict[str, str], ...]) -> None:
    missing = False
    forged = False
    for receipt in receipts:
        row = con.execute(
            "SELECT chunks.text FROM chunks "
            "JOIN documents ON documents.document_id = chunks.document_id "
            "WHERE chunks.chunk_id = ? AND chunks.document_id = ? LIMIT 1",
            [receipt["source_id"], receipt["document_id"]],
        ).fetchone()
        if row is None:
            missing = True
        elif hashlib.sha256(str(row[0]).encode("utf-8")).hexdigest() != receipt["content_hash"]:
            forged = True
    if forged:
        raise GraphProjectionRefused(
            "receipt_malformed_or_forged",
            "cited local chunk no longer matches its receipt",
        )
    if missing:
        raise GraphProjectionPending(
            "internal_local_chunk_temporarily_missing",
            "cited local chunk is temporarily unavailable",
        )


def _census_projection_rows(
    con: LockedConnection,
    plan: _ProjectionPlan,
    *,
    owner_user_id: str,
    require_all: bool,
) -> _MissingRows:
    deliverable = con.execute(
        "SELECT owner_user_id, title, investigation_root_id, metadata, "
        "deliverable_kind, status FROM deliverables WHERE deliverable_id = ?",
        [plan.deliverable_id],
    ).fetchone()
    deliverable_missing = deliverable is None
    if deliverable is not None and (
        deliverable[0] != owner_user_id
        or deliverable[1] != plan.deliverable_title
        or deliverable[2] != plan.investigation_id
        or deliverable[4] != "research_memo"
        or deliverable[5] != "draft"
        or _durable_metadata(deliverable[3], label="graph deliverable") != plan.deliverable_metadata
    ):
        raise GraphProjectionRefused(
            "deterministic_row_conflict",
            "graph deliverable conflicts with expected projection",
        )
    missing_sections: set[str] = set()
    for section_id, index, title, prose, provenance in plan.sections:
        row = con.execute(
            "SELECT deliverable_id, parent_section_id, section_index, title, "
            "prose_text, prose_provenance FROM deliverable_sections "
            "WHERE section_id = ?",
            [section_id],
        ).fetchone()
        if row is None:
            missing_sections.add(section_id)
        elif (
            row[:5] != (plan.deliverable_id, None, index, title, prose)
            or _durable_metadata(row[5], label="graph section") != provenance
        ):
            raise GraphProjectionRefused(
                "deterministic_row_conflict",
                "graph section conflicts with durable evidence",
            )
    missing_nodes: set[str] = set()
    for node_id, label, node_type, metadata in plan.nodes:
        row = con.execute(
            "SELECT canonical_label, node_type, embedding, graph_scope, "
            "degree_cached, metadata "
            "FROM nodes WHERE node_id = ?",
            [node_id],
        ).fetchone()
        if row is None:
            missing_nodes.add(node_id)
        elif (
            row[:5] != (label, node_type, None, "depth", 0)
            or _durable_metadata(row[5], label="graph node") != metadata
        ):
            raise GraphProjectionRefused(
                "deterministic_row_conflict",
                "graph node conflicts with durable evidence",
            )
    missing_edges: set[str] = set()
    for edge_id, source_id, target_id, document_id, chunk_id, metadata in plan.edges:
        row = con.execute(
            "SELECT source_node_id, target_node_id, relation, chunk_id, "
            "source_document_id, source_tier, extraction_confidence, valid_from, "
            "valid_until, superseded_by, graph_scope, investigation_id, metadata "
            "FROM edges WHERE edge_id = ?",
            [edge_id],
        ).fetchone()
        expected = (
            source_id,
            target_id,
            "contains",
            chunk_id,
            document_id,
            1,
            1.0,
            datetime(1970, 1, 1),
            None,
            None,
            "depth",
            plan.investigation_id,
        )
        if row is None:
            missing_edges.add(edge_id)
        elif row[:12] != expected or _durable_metadata(row[12], label="graph edge") != metadata:
            raise GraphProjectionRefused(
                "deterministic_row_conflict",
                "graph edge conflicts with durable evidence",
            )
    missing = _MissingRows(
        deliverable=deliverable_missing,
        section_ids=frozenset(missing_sections),
        node_ids=frozenset(missing_nodes),
        edge_ids=frozenset(missing_edges),
    )
    if require_all and (
        missing.deliverable or missing.section_ids or missing.node_ids or missing.edge_ids
    ):
        raise GraphProjectionConflict("graph write did not materialize its complete plan")
    return missing


def _node_event(
    plan: _ProjectionPlan,
    node: tuple[str, str, str, dict[str, object]],
) -> Event:
    node_id, label, node_type, _metadata = node
    return prepare_typed_event(
        plan.investigation_id,
        GraphNodeInsertedPayload(
            node_id=node_id,
            canonical_label=label,
            node_type=cast(NodeType, node_type),
            graph_scope="depth",
            has_embedding=False,
        ),
        event_id=content_addressed_id("evt", f"midnight-oil-graph-node|{node_id}"),
        role="connector",
        emitted_at=datetime(1970, 1, 1, tzinfo=UTC),
    )


def _edge_event(
    plan: _ProjectionPlan,
    edge: tuple[str, str, str, str, str, dict[str, object]],
) -> Event:
    edge_id, source_node_id, target_node_id, document_id, chunk_id, _metadata = edge
    return prepare_typed_event(
        plan.investigation_id,
        GraphEdgeInsertedPayload(
            edge_id=edge_id,
            source_node_id=source_node_id,
            target_node_id=target_node_id,
            relation="contains",
            source_document_id=document_id,
            chunk_id=chunk_id,
            source_tier=1,
            extraction_confidence=1.0,
            graph_scope="depth",
        ),
        event_id=content_addressed_id("evt", f"midnight-oil-graph-edge|{edge_id}"),
        role="connector",
        emitted_at=datetime(1970, 1, 1, tzinfo=UTC),
    )


def _projection_events(plan: _ProjectionPlan) -> tuple[Event, ...]:
    return (
        *(_node_event(plan, node) for node in plan.nodes),
        *(_edge_event(plan, edge) for edge in plan.edges),
    )


def _projection_source_fingerprint(
    job: MidnightOilJob,
    *,
    owner_user_id: str,
    authority_operation_id: str,
    authority_state: OperationState,
    acceptance_policy: object,
    html_sha256: str,
    evidence_sha256: str,
) -> str:
    material = {
        "owner_user_id": owner_user_id,
        "operation_id": authority_operation_id,
        "operation_state": authority_state.value,
        "acceptance_policy": acceptance_policy,
        "job_source": {
            "status": job.status,
            "deposit_state": job.deposit_state,
            "deposit_document_id": job.deposit_document_id,
            "html_sha256": html_sha256,
            "evidence_sha256": evidence_sha256,
        },
    }
    return hashlib.sha256(
        json.dumps(material, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _projection_source_is_current(
    *,
    source_sha256: str,
    owner_user_id: str,
    job_id: str,
    owner_jobs: OwnerJobStore,
    store: JobStore,
    engagement_store: EngagementStore,
) -> bool:
    current_job = get_job(job_id, store=store)
    current_authority = owner_jobs.get_job(owner_user_id=owner_user_id, job_id=job_id)
    if (
        current_job is None
        or current_job.graph_projection_source_sha256 != source_sha256
        or current_authority is None
        or current_authority.operation_id is None
    ):
        return False
    try:
        policy = research_acceptance_policy_from_authority(current_authority.payload)
        html_sha256 = _html_hash(_deposited_html(current_job, engagement_store))
    except (GraphProjectionNotReady, TypeError, ValueError):
        return False
    evidence_sha256 = hashlib.sha256(_canonical_evidence(current_job)).hexdigest()
    return source_sha256 == _projection_source_fingerprint(
        current_job,
        owner_user_id=owner_user_id,
        authority_operation_id=current_authority.operation_id,
        authority_state=current_authority.operation_state,
        acceptance_policy=None if policy is None else policy.model_dump(mode="json"),
        html_sha256=html_sha256,
        evidence_sha256=evidence_sha256,
    )


def _project_terminal_job_to_graph_locked(
    job_id: str,
    *,
    owner_user_id: str,
    owner_jobs: OwnerJobStore,
    store: JobStore,
    engagement_store: EngagementStore,
    graph_db_path: str | Path,
    events_dir: str | None = None,
    lock_timeout_s: float = 300,
    locked_document_id: str | None = None,
) -> GraphProjectionResult:
    """Admit complete local claim evidence before the first graph write."""

    job = get_job(job_id, store=store)
    if job is None:
        raise KeyError("graph projection job not found")
    if locked_document_id is not None and job.deposit_document_id != locked_document_id:
        _raise_disposition(
            job,
            "operational_artifact_pending",
            store=store,
            message="deposit identity changed before document lock",
        )
    if job.graph_projection_state == "refused":
        reason = job.graph_projection_reason
        if reason not in REFUSED_GRAPH_ADMISSION_REASONS:
            raise GraphProjectionConflict("durable graph refusal lacks a closed reason")
        raise GraphProjectionRefused(reason)
    if not owner_user_id.strip() or len(owner_user_id) > 256:
        raise ValueError("graph projection owner must be a bounded non-empty id")
    if job.status not in _TERMINAL_STATUSES:
        _raise_disposition(
            job,
            "operational_artifact_pending",
            store=store,
            message="graph projection requires a terminal job",
        )
    authority = owner_jobs.get_job(owner_user_id=owner_user_id, job_id=job_id)
    if (
        authority is None
        or authority.operation_id is None
        or not _authority_is_terminal(job, authority.operation_state)
    ):
        _raise_disposition(
            job,
            "policy_authority_drift",
            store=store,
            message="graph projection requires matching terminal owner authority",
        )
    try:
        acceptance_policy = research_acceptance_policy_from_authority(authority.payload)
    except (TypeError, ValueError):
        acceptance_policy = None
    if job.deposit_state != "complete" or not job.deposit_document_id:
        _raise_disposition(
            job,
            "operational_artifact_pending",
            store=store,
            message="graph projection requires a completed deposit",
        )
    try:
        html = _deposited_html(job, engagement_store)
        html_sha256 = _html_hash(html)
    except GraphProjectionNotReady as exc:
        _raise_disposition(
            job,
            "operational_artifact_pending",
            store=store,
            message=str(exc),
        )
    if not job.step_evidence:
        _raise_disposition(
            job,
            "legacy_unverified",
            store=store,
            message="graph projection requires versioned step evidence",
        )
    admission = verify_claim_admission(
        job_id=job.job_id,
        step_evidence=job.step_evidence,
        acceptance_policy=acceptance_policy,
    )
    if not admission.admitted:
        _raise_disposition(
            job,
            admission.reason_codes[0],
            store=store,
        )
    step_keys = tuple(evidence.step_key for evidence in job.step_evidence)
    if len(step_keys) != len(set(step_keys)):
        _raise_disposition(
            job,
            "deterministic_row_conflict",
            store=store,
            message="graph projection requires job-wide unique step keys",
        )
    existing_receipt = job.graph_effect_receipt
    if existing_receipt is not None and (
        existing_receipt.owner_user_id != owner_user_id
        or existing_receipt.html_sha256 != html_sha256
    ):
        raise GraphProjectionConflict("graph projection request conflicts with durable receipt")
    evidence_sha256 = hashlib.sha256(_canonical_evidence(job)).hexdigest()
    policy_material = (
        None if acceptance_policy is None else acceptance_policy.model_dump(mode="json")
    )
    source_sha256 = _projection_source_fingerprint(
        job,
        owner_user_id=owner_user_id,
        authority_operation_id=str(authority.operation_id),
        authority_state=authority.operation_state,
        acceptance_policy=policy_material,
        html_sha256=html_sha256,
        evidence_sha256=evidence_sha256,
    )
    if job.graph_projection_source_sha256 is None:
        sealed = replace(job, graph_projection_source_sha256=source_sha256)
        if not store.compare_and_put_graph(job, sealed):
            current = get_job(job.job_id, store=store)
            if current is None or current.graph_projection_source_sha256 != source_sha256:
                raise GraphProjectionConflict("graph source seal lost a concurrent race")
            job = current
        else:
            job = sealed
    elif job.graph_projection_source_sha256 != source_sha256:
        raise GraphProjectionConflict("graph projection source conflicts with durable seal")
    plan = _build_projection_plan(
        job,
        owner_user_id=owner_user_id,
        html_sha256=html_sha256,
        evidence_sha256=evidence_sha256,
        source_sha256=source_sha256,
    )
    projection_events = _projection_events(plan)
    path = str(Path(graph_db_path))
    try:
        with (
            connect_write(
                path,
                purpose="midnight_oil/graph_projection",
                timeout_s=lock_timeout_s,
            ) as con,
            event_append_batch(plan.investigation_id, events_dir=events_dir) as event_batch,
        ):
            _require_projection_schema(con)
            if not _projection_source_is_current(
                source_sha256=source_sha256,
                owner_user_id=owner_user_id,
                job_id=job.job_id,
                owner_jobs=owner_jobs,
                store=store,
                engagement_store=engagement_store,
            ):
                raise GraphProjectionPending(
                    "operational_artifact_pending",
                    "graph projection source changed before admission",
                )
            _validate_cited_receipts(con, plan.cited_receipts)
            missing = _census_projection_rows(
                con,
                plan,
                owner_user_id=owner_user_id,
                require_all=False,
            )
            try:
                event_batch.validate(projection_events)
            except (TypeError, ValueError) as exc:
                raise GraphProjectionRefused(
                    "deterministic_row_conflict",
                    "graph event conflicts with projection",
                ) from exc
            con.execute("BEGIN TRANSACTION")
            if missing.deliverable:
                _insert_deliverable_once(
                    con,
                    deliverable_id=plan.deliverable_id,
                    title=plan.deliverable_title,
                    investigation_id=plan.investigation_id,
                    owner_user_id=owner_user_id,
                    metadata=plan.deliverable_metadata,
                )
            for node_id, label, node_type, metadata in plan.nodes:
                if node_id not in missing.node_ids:
                    continue
                _insert_node_once(
                    con,
                    node_id=node_id,
                    label=label,
                    node_type=node_type,
                    metadata=metadata,
                )
            for section_id, index, title, prose, provenance in plan.sections:
                if section_id not in missing.section_ids:
                    continue
                _insert_section_once(
                    con,
                    section_id=section_id,
                    deliverable_id=plan.deliverable_id,
                    section_index=index,
                    title=title,
                    prose_text=prose,
                    provenance=provenance,
                )
            for (
                edge_id,
                source_node_id,
                target_node_id,
                document_id,
                chunk_id,
                metadata,
            ) in plan.edges:
                if edge_id not in missing.edge_ids:
                    continue
                _insert_edge_once(
                    con,
                    edge_id=edge_id,
                    source_node_id=source_node_id,
                    target_node_id=target_node_id,
                    investigation_id=plan.investigation_id,
                    chunk_id=chunk_id,
                    document_id=document_id,
                    metadata=metadata,
                )
            _census_projection_rows(
                con,
                plan,
                owner_user_id=owner_user_id,
                require_all=True,
            )
            if not _projection_source_is_current(
                source_sha256=source_sha256,
                owner_user_id=owner_user_id,
                job_id=job.job_id,
                owner_jobs=owner_jobs,
                store=store,
                engagement_store=engagement_store,
            ):
                raise GraphProjectionPending(
                    "operational_artifact_pending",
                    "graph projection source changed during admission",
                )
            event_batch.append(projection_events)
            con.execute("COMMIT")
    except WriteLockTimeout:
        _raise_disposition(
            job,
            "graph_lock_unavailable",
            store=store,
        )
    except GraphProjectionPending as exc:
        _checkpoint_disposition(job, exc.reason, store=store)
        raise
    except GraphProjectionRefused as exc:
        _checkpoint_disposition(job, exc.reason, store=store)
        raise

    receipt = MidnightOilGraphEffectReceipt(
        schema_version=_SCHEMA_VERSION,
        owner_user_id=owner_user_id,
        deliverable_id=plan.deliverable_id,
        section_ids=tuple(section[0] for section in plan.sections),
        node_ids=tuple(node[0] for node in plan.nodes),
        edge_ids=tuple(edge[0] for edge in plan.edges),
        html_sha256=html_sha256,
        evidence_sha256=evidence_sha256,
        deep_links=(
            f"antiek://deliverable/{plan.deliverable_id}",
            *(f"antiek://node/{node[0]}" for node in plan.nodes),
        ),
    )
    if existing_receipt is not None and existing_receipt != receipt:
        raise GraphProjectionConflict("durable graph receipt conflicts with replayed projection")
    updated = replace(
        job,
        graph_projection_state="complete",
        graph_projection_reason=None,
        graph_effect_receipt=receipt,
    )
    if store.compare_and_put_graph(job, updated):
        current = get_job(job.job_id, store=store)
        if current is None or current.graph_effect_receipt != receipt:
            raise GraphProjectionConflict("graph receipt checkpoint was not durable")
        return GraphProjectionResult(job=current, receipt=receipt)
    current = get_job(job.job_id, store=store)
    if current is not None and current.graph_effect_receipt == receipt:
        return GraphProjectionResult(job=current, receipt=receipt)
    raise GraphProjectionConflict("graph receipt checkpoint lost a concurrent race")


def project_terminal_job_to_graph(
    job_id: str,
    *,
    owner_user_id: str,
    owner_jobs: OwnerJobStore,
    store: JobStore,
    engagement_store: EngagementStore,
    graph_db_path: str | Path,
    events_dir: str | None = None,
    lock_timeout_s: float = 300,
) -> GraphProjectionResult:
    """Lock the deposited HTML source through graph commit and receipt CAS."""

    snapshot = get_job(job_id, store=store)
    document_id = None if snapshot is None else snapshot.deposit_document_id
    if document_id is None:
        return _project_terminal_job_to_graph_locked(
            job_id,
            owner_user_id=owner_user_id,
            owner_jobs=owner_jobs,
            store=store,
            engagement_store=engagement_store,
            graph_db_path=graph_db_path,
            events_dir=events_dir,
            lock_timeout_s=lock_timeout_s,
        )
    with engagement_store.lock_document(document_id):
        return _project_terminal_job_to_graph_locked(
            job_id,
            owner_user_id=owner_user_id,
            owner_jobs=owner_jobs,
            store=store,
            engagement_store=engagement_store,
            graph_db_path=graph_db_path,
            events_dir=events_dir,
            lock_timeout_s=lock_timeout_s,
            locked_document_id=document_id,
        )


__all__ = [
    "GraphProjectionConflict",
    "GraphProjectionNotReady",
    "GraphProjectionPending",
    "GraphProjectionRefused",
    "GraphProjectionResult",
    "project_terminal_job_to_graph",
]
