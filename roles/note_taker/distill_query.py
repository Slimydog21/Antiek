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
from contextlib import nullcontext
from dataclasses import dataclass, field
from typing import Any

try:
    from runtime.db_lock import connect_read
    from substrate.event_log import trajectory
    from substrate.graph.insight_question import graph_db_path
    from substrate.schemas.events import ActionType
except ImportError:  # pragma: no cover — direct-script fallback
    _here = os.path.dirname(os.path.abspath(__file__))
    sys.path.insert(0, os.path.dirname(os.path.dirname(_here)))
    from runtime.db_lock import connect_read
    from substrate.event_log import trajectory
    from substrate.graph.insight_question import graph_db_path
    from substrate.schemas.events import ActionType


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
    unavailable_count: int = 0

    @property
    def empty(self) -> bool:
        return not self.insights and not self.questions


def _node_ids_from_trajectory(
    investigation_id: str, *, events_dir: str | None = None
) -> tuple[list[str], dict[str, dict[str, Any]]]:
    """Collect the insight/question node ids this investigation produced,
    in emission order, plus the per-question escalation (reserved child id)
    keyed by question node id. Order-preserving + de-duplicated so a note
    re-emitted (idempotent promotion) appears once."""
    ordered: list[str] = []
    seen: set[str] = set()
    escalations: dict[str, dict[str, Any]] = {}
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
        elif at == ActionType.NOTE_EMERGED.value:
            # Mini dogfood / projector-off: note.emerged is the durable signal;
            # insight node id is content-addressed from note_text.
            text = payload.get("note_text")
            if isinstance(nid, str) and nid.strip():
                cand = nid.strip()
            elif isinstance(text, str) and text.strip():
                from substrate.graph.insight_question import insight_node_id
                cand = insight_node_id(text.strip())
            else:
                cand = None
            if cand and cand not in seen:
                seen.add(cand)
                ordered.append(cand)
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
    con: Any | None = None,
) -> Distillation:
    """Read the insight + question nodes an investigation distilled, with
    their *current* text + grounding. Read-only. Nodes whose event was
    recorded but whose row no longer exists (deleted) are skipped — the
    log is history, the row is truth. This is an unscoped internal read;
    caller-facing reads must use ``readable_distillation_for``. A supplied
    connection remains open and avoids a second handle inside a write scope."""
    node_ids, escalations = _node_ids_from_trajectory(
        investigation_id, events_dir=events_dir
    )
    if not node_ids:
        return Distillation()

    insights: list[DistilledNode] = []
    questions: list[DistilledNode] = []
    unavailable_count = 0
    with nullcontext(con) if con is not None else connect_read(db_path or graph_db_path()) as con:
        for nid in node_ids:
            row = con.execute(
                "SELECT node_type, canonical_label, metadata FROM nodes WHERE node_id = ?",
                [nid],
            ).fetchone()
            if row is None:
                unavailable_count += 1
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
            else:
                unavailable_count += 1
    return Distillation(
        insights=insights, questions=questions, unavailable_count=unavailable_count
    )


def readable_distillation_for(
    investigation_id: str,
    *,
    owner_user_id: str,
    db_path: str | None = None,
    events_dir: str | None = None,
    con: Any | None = None,
) -> Distillation:
    """Return only products whose node and source the caller may inspect.

    Policy: an exact node owner may read; NULL-owned shared/legacy nodes
    may also be read, but neither grants source access. The source must pass
    the real body read gate, with owner privileges only on an exact match.
    Public bodies are inspectable through /books/{id}/full-text; the passage
    route remains exact-owner-only. /books/{id} metadata can be 404 simply
    because there is no openable book asset, not because of ownership.
    Foreign-owned nodes, unknown sources and
    withheld bodies fail closed, regardless of operator authentication.

    ``unavailable_count`` lets provenance reject an incomplete investigation
    rather than authorize a mixed-owner product from its visible subset.
    The unscoped ``distillation_for`` remains an internal graph read, not an
    authorization decision. Neither function validates source spans.
    A supplied connection is reused for both the node read and source guard;
    the caller retains its ownership and transaction scope.
    """
    from substrate.books.serve_guard import LinkBackMissingError, serve_full_text_guarded
    from substrate.rights import T3BodyServeError

    view = distillation_for(
        investigation_id, db_path=db_path, events_dir=events_dir, con=con
    )
    readable: set[str] = set()
    with nullcontext(con) if con is not None else connect_read(db_path or graph_db_path()) as con:
        for node in [*view.insights, *view.questions]:
            if not node.source_document_id:
                continue
            row = con.execute(
                "SELECT n.owner_user_id, d.owner_user_id FROM nodes n "
                "JOIN documents d ON d.document_id = ? WHERE n.node_id = ?",
                [node.source_document_id, node.node_id],
            ).fetchone()
            if (
                not owner_user_id.strip()
                or row is None
                or row[0] not in (None, owner_user_id)
            ):
                continue
            try:
                served = serve_full_text_guarded(
                    con, node.source_document_id, owner=row[1] == owner_user_id
                )
            except (T3BodyServeError, LinkBackMissingError):
                continue
            if served.full_text and served.full_text.strip():
                readable.add(node.node_id)
    return Distillation(
        insights=[n for n in view.insights if n.node_id in readable],
        questions=[n for n in view.questions if n.node_id in readable],
        unavailable_count=(
            view.unavailable_count + len(view.insights) + len(view.questions) - len(readable)
        ),
    )


def _load_meta(raw: Any) -> dict[str, Any]:
    if not raw:
        return {}
    if isinstance(raw, dict):
        return raw
    try:
        parsed = json.loads(raw)
    except (TypeError, ValueError):
        return {}
    # Metadata blobs are JSON objects by contract; anything else is corrupt.
    return parsed if isinstance(parsed, dict) else {}
