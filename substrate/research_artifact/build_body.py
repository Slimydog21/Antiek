"""Build ResearchArtifactBody from graph + trajectory."""

from __future__ import annotations

from roles.note_taker.distill_query import Distillation, distillation_for, readable_distillation_for
from substrate.event_log import trajectory
from substrate.graph import default_db_path
from substrate.schemas.events import ActionType

from .context import problem_question_from_events, synthesis_from_events
from .import_notes import load_persisted_agent_notes
from .schema import ArtifactInsight, ArtifactQuestion, ResearchArtifactBody
from .store import ResearchArtifactStore


def build_body(
    investigation_id: str,
    *,
    db_path: str | None = None,
    events_dir: str | None = None,
) -> ResearchArtifactBody:
    view = distillation_for(investigation_id, db_path=db_path, events_dir=events_dir)
    return _assemble_body(investigation_id, view, events_dir=events_dir, include_context=True)


def build_body_for_reader(
    investigation_id: str,
    *,
    owner_user_id: str,
    db_path: str | None = None,
    events_dir: str | None = None,
) -> ResearchArtifactBody:
    """Scope every field, not just graph text, before rendering an HTTP body.

    Graph products use the node/source read gate. Opaque event/file fields
    need both a caller-owned artifact record and matching start-event owners.
    A stored artifact alone is not authority: the export endpoint can mint
    one for a foreign investigation. Missing, legacy or conflicting start
    ownership withholds context. An incomplete product withholds it too.
    """
    db = db_path or default_db_path()
    view = readable_distillation_for(
        investigation_id, owner_user_id=owner_user_id, db_path=db, events_dir=events_dir,
    )
    starts = [
        row.get("payload") or {} for row in trajectory(investigation_id, events_dir=events_dir)
        if row.get("action_type") == ActionType.INVESTIGATION_START_REQUESTED.value
    ]
    context_owned = (
        bool(starts)
        and all(start.get("owner_user_id") == owner_user_id for start in starts)
        and view.unavailable_count == 0
        and ResearchArtifactStore(db).get_for_investigation(investigation_id, owner_user_id) is not None
    )
    return _assemble_body(
        investigation_id, view, events_dir=events_dir, include_context=context_owned,
    )


def _assemble_body(
    investigation_id: str,
    view: Distillation,
    *,
    events_dir: str | None,
    include_context: bool,
) -> ResearchArtifactBody:
    question = (
        problem_question_from_events(investigation_id, events_dir=events_dir)
        if include_context else ""
    )
    if not question:
        question = f"Investigation {investigation_id}"

    insights = [
        ArtifactInsight(
            node_id=n.node_id,
            text=n.text,
            source_document_id=n.source_document_id,
            confidence=n.confidence,
        )
        for n in view.insights
    ]
    questions = [
        ArtifactQuestion(
            node_id=n.node_id,
            text=n.text,
            escalated=n.escalated,
            reserved_child_investigation_id=n.reserved_child_investigation_id,
        )
        for n in view.questions
    ]
    excerpt, withheld, event_ids = (
        synthesis_from_events(investigation_id, events_dir=events_dir)
        if include_context else (None, True, [])
    )
    agent_notes = load_persisted_agent_notes(investigation_id) if include_context else []
    return ResearchArtifactBody(
        investigation_id=investigation_id,
        problem_question=question,
        insights=insights,
        open_questions=questions,
        synthesis_excerpt=excerpt if not withheld else None,
        synthesis_withheld=withheld,
        source_event_ids=event_ids,
        agent_notes=agent_notes,
    )