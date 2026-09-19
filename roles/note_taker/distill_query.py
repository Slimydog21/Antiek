"""DRW SPR-03 M2 — read an investigation's distilled insights + questions.

The surface (DistillView) needs the durable product of a research: the
insight and question *graph nodes*, with their current text and their
grounding. This module is the read seam.

Why a trajectory walk, not a ``WHERE investigation_id`` on the nodes
table: a node is content-addressed and shared across investigations, so it
carries no owning ``investigation_id`` column — the investigation it came
from rides on the ``GRAPH_NODE_INSERTED`` / ``note.emerged`` /
``question.identified`` event envelopes (see ``substrate/graph/ops.insert_node``).
So we read the per-investigation event log for the node ids this research
produced, then read the *live* node rows for their current text and
metadata. Reading the live row (not the event payload) is the point: after
a challenge mutates a note in place, the distill view shows the refined
text, because ``canonical_label`` is the single source of truth and the
event log is the history. We never re-derive a note from raw events.

No second writer: this is read-only (``connect_read``); it promotes
nothing and emits nothing.
"""

from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass, field
from typing import Any

try:
    from ...event_log import trajectory
    from ...graph.insight_question import graph_db_path
    from ...runtime.db_lock import connect_read
    from ...schemas.events import ActionType
except ImportError:  # pragma: no cover — direct-script fallback
    _here = os.path.dirname(os.path.abspath(__file__))
    sys.path.insert(0, os.path.dirname(os.path.dirname(_here)))
    from runtime.db_lock import connect_read  # type: ignore[no-redef]
    from substrate.event_log import trajectory  # type: ignore[no-redef]
    from substrate.graph.insight_question import graph_db_path  # type: ignore[no-redef]
    from substrate.schemas.events import ActionType  # type: ignore[no-redef]


@dataclass(frozen=True)
class DistilledNode:
    """One distilled insight or question as the surface renders it."""

    node_id: str
    kind: str                       # "insight" | "question"
    text: str                       # current canonical text (post-challenge)
    confidence: str | None = None
    source_document_id: str | None = None
    refinement_count: int = 0       # how many times this note has changed
    escalated: bool = False         # a question with a reserved child research
    reserved_child_investigation_id: str | None = None


@dataclass(frozen=True)
class Distillation:
    insights: list[DistilledNode] = field(default_factory=list)
    questions: list[DistilledNode] = field(default_factory=list)

    @property
    def empty(self) -> bool:
        return not self.insights and not self.questions


def _node_ids_from_trajectory(
    investigation_id: str, *, events_dir: str | None = None
) -> tuple[list[str], dict[str, dict]]:
    """Collect the insight/question node ids this investigation produced,
    in emission order, plus the per-question escalation (reserved child id)
    keyed by question node id. Order-preserving + de-duplicated so a note
    re-emitted (idempotent promotion) appears once."""
    ordered: list[str] = []
    seen: set[str] = set()
    escalations: dict[str, dict] = {}
    # promote_question used in the escalation seam stores the challenged
    # note's id; map question_id (payload) → node — handled at read time.
    for row in trajectory(investigation_id, events_dir=events_dir):
        at = row.get("action_type")
        payload = row.get("payload") or {}
        nid = payload.get("node_id")
        if at == ActionType.GRAPH_NODE_INSERTED.value and isinstance(nid, str):
            ntype = payload.get("node_type")
            if ntype in ("insight", "question") and nid not in seen:
                seen.add(nid)
                ordered.append(nid)
        elif at == ActionType.QUESTION_ESCALATED_TO_RESEARCH.value:
            qid = payload.get("question_id")
            child = payload.get("child_investigation_id")
            if isinstance(qid, str) and isinstance(child, str):
                escalations[qid] = {"reserved_child_investigation_id": child}
    return ordered, escalations


def distillation_for(
    investigation_id: str,
    *,
    db_path: str | None = None,
    events_dir: str | None = None,
) -> Distillation:
    """Read the insight + question nodes an investigation distilled, with
    their *current* text + grounding. Read-only. Nodes whose event was
    recorded but whose row no longer exists (deleted) are skipped — the
    log is history, the row is truth."""
    node_ids, escalations = _node_ids_from_trajectory(
        investigation_id, events_dir=events_dir
    )
    if not node_ids:
        return Distillation()

    insights: list[DistilledNode] = []
    questions: list[DistilledNode] = []
    con = connect_read(db_path or graph_db_path())
    try:
        for nid in node_ids:
            row = con.execute(
                "SELECT node_type, canonical_label, metadata FROM nodes WHERE node_id = ?",
                [nid],
            ).fetchone()
            if row is None:
                continue  # tombstoned row — skip, don't fabricate
            ntype, label, meta_raw = row
            meta = _load_meta(meta_raw)
            if ntype == "insight":
                insights.append(DistilledNode(
                    node_id=nid, kind="insight", text=label,
                    confidence=meta.get("confidence"),
                    source_document_id=meta.get("source_document_id"),
                    refinement_count=int(meta.get("refinement_count", 0) or 0),
                ))
            elif ntype == "question":
                # The escalation seam emits QuestionEscalatedToResearch with
                # ``question_id`` = the question *node* id (living_note passes
                # the promoted node id as qid), so escalations are keyed by the
                # node id directly.
                esc = escalations.get(nid)
                questions.append(DistilledNode(
                    node_id=nid, kind="question", text=label,
                    source_document_id=meta.get("source_document_id"),
                    escalated=esc is not None,
                    reserved_child_investigation_id=(
                        esc.get("reserved_child_investigation_id") if esc else None
                    ),
                ))
    finally:
        con.close()
    return Distillation(insights=insights, questions=questions)


def distillation_for_authorized(
    authority,
    *,
    db_path: str | None = None,
) -> Distillation:
    """Read only live nodes visible through the exact graph membership."""
    from substrate.event_log import trajectory_authorized
    from substrate.graph.tenancy import (
        assert_graph_authority_read,
        has_node_membership_read,
    )

    escalations: dict[str, dict] = {}
    for row in trajectory_authorized(authority):
        action_type = row.get("action_type")
        payload = row.get("payload") or {}
        if action_type == ActionType.QUESTION_ESCALATED_TO_RESEARCH.value:
            question_id = payload.get("question_id")
            child = payload.get("child_investigation_id")
            if isinstance(question_id, str) and isinstance(child, str):
                escalations[question_id] = {"reserved_child_investigation_id": child}

    insights: list[DistilledNode] = []
    questions: list[DistilledNode] = []
    con = connect_read(db_path or graph_db_path())
    try:
        assert_graph_authority_read(con, authority)
        memberships = con.execute(
            "SELECT node_id, membership_metadata "
            "FROM investigation_node_memberships "
            "WHERE account_digest = ? AND investigation_digest = ? "
            "AND role IN ('insight', 'question') ORDER BY created_at, node_id",
            [authority.account_digest, authority.investigation_digest],
        ).fetchall()
        for node_id, membership_metadata_raw in memberships:
            if not has_node_membership_read(con, authority, node_id=node_id):
                raise RuntimeError("graph membership changed during distillation read")
            row = con.execute(
                "SELECT node_type, canonical_label, metadata FROM nodes WHERE node_id = ?",
                [node_id],
            ).fetchone()
            if row is None:
                continue
            node_type, _shared_label, _shared_metadata_raw = row
            metadata = _load_meta(membership_metadata_raw)
            label = metadata.get("canonical_text")
            if not isinstance(label, str) or not label:
                raise RuntimeError("authorized graph membership lacks canonical text")
            if node_type == "insight":
                insights.append(
                    DistilledNode(
                        node_id=node_id,
                        kind="insight",
                        text=label,
                        confidence=metadata.get("confidence"),
                        source_document_id=metadata.get("source_document_id"),
                        refinement_count=int(metadata.get("refinement_count", 0) or 0),
                    )
                )
            elif node_type == "question":
                escalation = escalations.get(node_id)
                questions.append(
                    DistilledNode(
                        node_id=node_id,
                        kind="question",
                        text=label,
                        source_document_id=metadata.get("source_document_id"),
                        escalated=escalation is not None,
                        reserved_child_investigation_id=(
                            escalation.get("reserved_child_investigation_id")
                            if escalation
                            else None
                        ),
                    )
                )
    finally:
        con.close()
    return Distillation(insights=insights, questions=questions)


def _load_meta(raw: Any) -> dict:
    if not raw:
        return {}
    if isinstance(raw, dict):
        return raw
    try:
        return json.loads(raw)
    except (TypeError, ValueError):
        return {}
