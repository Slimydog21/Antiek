"""Build ResearchArtifactBody from graph + trajectory."""

from __future__ import annotations

from roles.note_taker.distill_query import distillation_for

from .context import problem_question_from_events, synthesis_from_events
from .import_notes import load_persisted_agent_notes
from .schema import ArtifactInsight, ArtifactQuestion, ResearchArtifactBody


def build_body(
    investigation_id: str,
    *,
    db_path: str | None = None,
    events_dir: str | None = None,
) -> ResearchArtifactBody:
    view = distillation_for(investigation_id, db_path=db_path)
    question = problem_question_from_events(investigation_id, events_dir=events_dir)
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
    excerpt, withheld, event_ids = synthesis_from_events(
        investigation_id, events_dir=events_dir
    )
    agent_notes = load_persisted_agent_notes(investigation_id)
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