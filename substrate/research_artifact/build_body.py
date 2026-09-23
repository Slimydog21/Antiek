"""Build ResearchArtifactBody from graph + trajectory."""

from __future__ import annotations

from roles.note_taker.distill_query import DistilledNode, distillation_for
from services.html_projection.adapters.notebook import RightsAwareResolver
from services.html_projection.context import ResolvedRef
from services.html_projection.resolvers.substrate_refs import resolve_refs
from substrate.graph.insight_question import graph_db_path

from .context import problem_question_from_events, synthesis_from_events
from .import_notes import load_persisted_agent_notes
from .schema import ArtifactInsight, ArtifactQuestion, ResearchArtifactBody

# A node that vanished between the distillation read and the rights read has
# no resolvable rights, so it is withheld rather than shown on the first read.
_UNRESOLVED_NOTICE = (
    "[cite-only — source; full text withheld: its rights could not be resolved]"
)


def _exportable_text(nodes: list[DistilledNode], *, db_path: str) -> dict[str, str]:
    """The text each node may carry into the artifact.

    The artifact is an export, and an export is serving
    (spr-05-export-eligibility-contract.md), so each node passes the same
    chokepoint the notebook and deliverable exporters use: ``resolve_refs``
    reads the source document's rights and ``RightsAwareResolver`` reduces a
    non-servable node to a cite-only notice. A node whose rights are unknown
    (a missing document row, a sourced kind with no source) resolves to the
    gated default and is withheld too."""
    refs = resolve_refs([n.node_id for n in nodes], db_path=db_path)
    resolver = RightsAwareResolver(refs)
    out: dict[str, str] = {}
    for n in nodes:
        data = refs.get(n.node_id)
        if data is not None and data.content_class is None and data.source_document_id is None:
            # resolve_refs leaves rights None only for a node that is not
            # derived from sources and names none: the operator's own words.
            out[n.node_id] = n.text
            continue
        resolved = resolver(n.node_id, n.kind)
        if not isinstance(resolved, ResolvedRef):
            out[n.node_id] = _UNRESOLVED_NOTICE
        elif resolved.payload.get("cite_only"):
            out[n.node_id] = str(resolved.payload["text"])
        else:
            out[n.node_id] = n.text
    return out


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

    text = _exportable_text(
        [*view.insights, *view.questions], db_path=db_path or graph_db_path()
    )
    insights = [
        ArtifactInsight(
            node_id=n.node_id,
            text=text[n.node_id],
            source_document_id=n.source_document_id,
            confidence=n.confidence,
        )
        for n in view.insights
    ]
    questions = [
        ArtifactQuestion(
            node_id=n.node_id,
            text=text[n.node_id],
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