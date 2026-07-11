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
from pathlib import Path

from runtime.db_lock import LockedConnection, connect_read, connect_write
from substrate.engagement_spine import project_to_html
from substrate.engagement_spine.store import EngagementStore
from substrate.graph import ensure_initialized
from substrate.graph.ops import (
    content_addressed_id,
    insert_edge,
    insert_node,
)

from .job import (
    JobStore,
    MidnightOilGraphEffectReceipt,
    MidnightOilJob,
    get_job,
    put_job_state,
)
from .job_store import OperationState, OwnerJobStore

_TERMINAL_STATUSES = {"complete", "timed_out", "budget_halted", "failed"}
_SCHEMA_VERSION = 1


class GraphProjectionNotReady(ValueError):
    """The terminal/deposit/evidence preconditions are not satisfied."""


@dataclass(frozen=True)
class GraphProjectionResult:
    job: MidnightOilJob
    receipt: MidnightOilGraphEffectReceipt


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
        "failed": frozenset({OperationState.FAILED, OperationState.FAILED_RECONCILE}),
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


def project_terminal_job_to_graph(
    job_id: str,
    *,
    owner_user_id: str,
    owner_jobs: OwnerJobStore,
    store: JobStore,
    engagement_store: EngagementStore,
    graph_db_path: str | Path,
    events_dir: str | None = None,
) -> GraphProjectionResult:
    """Project exact terminal evidence and checkpoint a truthful effect receipt."""

    job = get_job(job_id, store=store)
    if job is None:
        raise KeyError("graph projection job not found")
    if not owner_user_id.strip() or len(owner_user_id) > 256:
        raise ValueError("graph projection owner must be a bounded non-empty id")
    authority = owner_jobs.get_job(owner_user_id=owner_user_id, job_id=job_id)
    if (
        authority is None
        or authority.operation_id is None
        or not _authority_is_terminal(job, authority.operation_state)
    ):
        raise GraphProjectionNotReady(
            "graph projection requires matching terminal owner authority"
        )
    html = _deposited_html(job, engagement_store)
    html_sha256 = _html_hash(html)
    existing_receipt = job.graph_effect_receipt
    if existing_receipt is not None and (
        existing_receipt.owner_user_id != owner_user_id
        or existing_receipt.html_sha256 != html_sha256
    ):
        raise ValueError("graph projection request conflicts with durable receipt")
    if job.status not in _TERMINAL_STATUSES:
        raise GraphProjectionNotReady("graph projection requires a terminal job")
    if job.deposit_state != "complete" or not job.deposit_document_id:
        raise GraphProjectionNotReady("graph projection requires a completed deposit")
    if not job.step_evidence:
        raise GraphProjectionNotReady("graph projection requires exact step evidence")
    evidence_sha256 = hashlib.sha256(_canonical_evidence(job)).hexdigest()
    investigation_id = f"midnight-oil:{job.job_id}"
    deliverable_id = content_addressed_id("dlv", f"midnight-oil|{job.job_id}")
    root_node_id = content_addressed_id("node", f"midnight-oil-root|{job.job_id}")
    section_ids: list[str] = []
    node_ids: list[str] = [root_node_id]
    edge_ids: list[str] = []
    section_expected: dict[str, tuple[int, str, str, str]] = {}
    root_metadata: dict[str, object] = {
        "kind": "midnight_oil_deliverable",
        "deliverable_id": deliverable_id,
        "document_id": job.deposit_document_id,
        "html_sha256": html_sha256,
    }
    node_expected: dict[str, tuple[str, str, str, str]] = {
        root_node_id: (
            _title(job),
            "entity",
            "depth",
            json.dumps(root_metadata, sort_keys=True, separators=(",", ":")),
        )
    }
    edge_expected: dict[
        str,
        tuple[str, str, str, str | None, str | None, int, float, str, str, str],
    ] = {}

    path = ensure_initialized(str(graph_db_path))
    with connect_write(path, purpose="midnight_oil/graph_projection") as con:
        _insert_deliverable_once(
            con,
            deliverable_id=deliverable_id,
            title=_title(job),
            investigation_id=investigation_id,
            owner_user_id=owner_user_id,
            metadata={
                "schema_version": _SCHEMA_VERSION,
                "job_id": job.job_id,
                "deposit_document_id": job.deposit_document_id,
                "html_sha256": html_sha256,
                "evidence_sha256": evidence_sha256,
            },
        )
        insert_node(
            con,
            node_id=root_node_id,
            canonical_label=_title(job),
            node_type="entity",
            graph_scope="depth",
            investigation_id=investigation_id,
            metadata=root_metadata,
            on_conflict="ignore",
            events_dir=events_dir,
        )
        for index, evidence in enumerate(job.step_evidence):
            section_id = content_addressed_id(
                "sec", f"{deliverable_id}|{evidence.step_key}"
            )
            section_ids.append(section_id)
            provenance: dict[str, object] = {
                "step_key": evidence.step_key,
                "spawn_id": evidence.spawn_id,
                "route_receipt": evidence.route_receipt,
                "source_receipts": evidence.source_receipts,
            }
            section_title = f"Research step {index + 1}"
            section_expected[section_id] = (
                index,
                section_title,
                evidence.output_text,
                json.dumps(provenance, sort_keys=True, separators=(",", ":")),
            )
            _insert_section_once(
                con,
                section_id=section_id,
                deliverable_id=deliverable_id,
                section_index=index,
                title=section_title,
                prose_text=evidence.output_text,
                provenance=provenance,
            )
            units = tuple(("insight", value) for value in evidence.insights) + tuple(
                ("question", value) for value in evidence.questions
            )
            for unit_index, (node_type, text) in enumerate(units):
                node_id = content_addressed_id(
                    "node", f"{job.job_id}|{evidence.step_key}|{node_type}|{text}"
                )
                node_ids.append(node_id)
                node_metadata: dict[str, object] = {
                    "job_id": job.job_id,
                    "step_key": evidence.step_key,
                    "section_id": section_id,
                    "unit_index": unit_index,
                }
                node_expected[node_id] = (
                    text[:4096],
                    node_type,
                    "depth",
                    json.dumps(
                        node_metadata, sort_keys=True, separators=(",", ":")
                    ),
                )
                insert_node(
                    con,
                    node_id=node_id,
                    canonical_label=text[:4096],
                    node_type=node_type,
                    graph_scope="depth",
                    investigation_id=investigation_id,
                    metadata=node_metadata,
                    on_conflict="ignore",
                    events_dir=events_dir,
                )
                sources = evidence.source_receipts or ({},)
                for source in sources:
                    document_id = source.get("document_id", "")
                    chunk_id = source.get("source_id", "")
                    content_hash = source.get("content_hash", "")
                    canonical_url = (
                        f"antiek://document/{document_id}#chunk={chunk_id}"
                    )
                    source_present = bool(
                        document_id
                        and chunk_id
                        and source.get("hash_scope") == "retrieval_excerpt"
                        and source.get("source_url") == canonical_url
                        and _source_hash_matches(
                            con,
                            document_id=document_id,
                            chunk_id=chunk_id,
                            content_hash=content_hash,
                        )
                    )
                    receipt_identity = hashlib.sha256(
                        json.dumps(
                            source, sort_keys=True, separators=(",", ":")
                        ).encode("utf-8")
                    ).hexdigest()
                    edge_id = content_addressed_id(
                        "edge",
                        f"{root_node_id}|contains|{node_id}|"
                        f"{chunk_id if source_present else receipt_identity}",
                    )
                    edge_ids.append(edge_id)
                    edge_metadata = {
                        "job_id": job.job_id,
                        "step_key": evidence.step_key,
                        "source_receipt": source,
                        "source_row_present": source_present,
                    }
                    edge_expected[edge_id] = (
                        root_node_id,
                        node_id,
                        "contains",
                        document_id if source_present else None,
                        chunk_id if source_present else None,
                        1,
                        1.0,
                        "depth",
                        investigation_id,
                        json.dumps(
                            edge_metadata, sort_keys=True, separators=(",", ":")
                        ),
                    )
                    insert_edge(
                        con,
                        edge_id=edge_id,
                        source_node_id=root_node_id,
                        target_node_id=node_id,
                        relation="contains",
                        source_tier=1,
                        extraction_confidence=1.0,
                        graph_scope="depth",
                        investigation_id=investigation_id,
                        chunk_id=chunk_id if source_present else None,
                        source_document_id=document_id if source_present else None,
                        metadata=edge_metadata,
                        on_conflict="ignore",
                        events_dir=events_dir,
                    )

    # Re-open read-only before checkpointing so "complete" is backed by
    # queryable rows, not merely by the absence of a write exception.
    with connect_read(path) as con:
        row = con.execute(
            "SELECT owner_user_id, title, investigation_root_id, metadata, "
            "deliverable_kind, status "
            "FROM deliverables WHERE deliverable_id = ?",
            [deliverable_id],
        ).fetchone()
        if (
            row is None
            or row[0] != owner_user_id
            or row[1] != _title(job)
            or row[2] != investigation_id
            or not isinstance(row[3], str)
            or row[4] != "research_memo"
            or row[5] != "draft"
        ):
            raise RuntimeError("graph deliverable conflicts with expected projection")
        deliverable_metadata = json.loads(row[3])
        if (
            deliverable_metadata.get("schema_version") != _SCHEMA_VERSION
            or deliverable_metadata.get("job_id") != job.job_id
            or deliverable_metadata.get("html_sha256") != html_sha256
            or deliverable_metadata.get("evidence_sha256") != evidence_sha256
            or deliverable_metadata.get("deposit_document_id")
            != job.deposit_document_id
        ):
            raise RuntimeError("graph deliverable hashes conflict with durable evidence")
        for section_id, section_expected_value in section_expected.items():
            section = con.execute(
                "SELECT section_index, title, prose_text, prose_provenance "
                "FROM deliverable_sections "
                "WHERE section_id = ? AND deliverable_id = ?",
                [section_id, deliverable_id],
            ).fetchone()
            if (
                section is None
                or section[0] != section_expected_value[0]
                or section[1] != section_expected_value[1]
                or section[2] != section_expected_value[2]
                or json.loads(str(section[3]))
                != json.loads(section_expected_value[3])
            ):
                raise RuntimeError("graph section conflicts with durable evidence")
        for node_id, node_expected_value in node_expected.items():
            node = con.execute(
                "SELECT canonical_label, node_type, graph_scope, metadata "
                "FROM nodes WHERE node_id = ?",
                [node_id],
            ).fetchone()
            if (
                node is None
                or node[:3] != node_expected_value[:3]
                or json.loads(str(node[3])) != json.loads(node_expected_value[3])
            ):
                raise RuntimeError("graph node conflicts with durable evidence")
        for edge_id, edge_expected_value in edge_expected.items():
            edge = con.execute(
                "SELECT source_node_id, target_node_id, relation, "
                "source_document_id, chunk_id, source_tier, "
                "extraction_confidence, graph_scope, investigation_id, metadata "
                "FROM edges "
                "WHERE edge_id = ?",
                [edge_id],
            ).fetchone()
            if (
                edge is None
                or edge[:9] != edge_expected_value[:9]
                or json.loads(str(edge[9])) != json.loads(edge_expected_value[9])
            ):
                raise RuntimeError("graph edge conflicts with durable evidence")

    # The graph commit and read proof precede this checkpoint.  A crash here
    # replays the deterministic inserts and then writes the same receipt.
    receipt = MidnightOilGraphEffectReceipt(
        schema_version=_SCHEMA_VERSION,
        owner_user_id=owner_user_id,
        deliverable_id=deliverable_id,
        section_ids=tuple(section_ids),
        node_ids=tuple(dict.fromkeys(node_ids)),
        edge_ids=tuple(dict.fromkeys(edge_ids)),
        html_sha256=html_sha256,
        evidence_sha256=evidence_sha256,
        deep_links=(
            f"antiek://deliverable/{deliverable_id}",
            *(f"antiek://node/{node_id}" for node_id in dict.fromkeys(node_ids)),
        ),
    )
    if existing_receipt is not None and existing_receipt != receipt:
        raise RuntimeError("durable graph receipt conflicts with replayed projection")
    updated = replace(
        job,
        graph_projection_state="complete",
        graph_effect_receipt=receipt,
    )
    put_job_state(updated, store=store)

    return GraphProjectionResult(job=updated, receipt=receipt)


__all__ = [
    "GraphProjectionNotReady",
    "GraphProjectionResult",
    "project_terminal_job_to_graph",
]
