"""Build ResearchArtifactBody from graph + trajectory."""

from __future__ import annotations

from typing import Any

from roles.note_taker.distill_query import (
    DistilledNode,
    distillation_for,
    distilled_node_ids,
)
from runtime.db_lock import connect_read
from services.html_projection.adapters.notebook import RightsAwareResolver
from services.html_projection.context import ResolvedRef
from services.html_projection.resolvers.substrate_refs import (
    resolve_manifest_sources,
    resolve_pin_sources,
    resolve_refs,
)
from substrate.graph.insight_question import graph_db_path

from .context import SynthesisTrail, problem_question_from_events, synthesis_from_events
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


def _investigation_ids(con: Any, sql: str, investigation_id: str) -> list[str]:
    rows = con.execute(sql, [investigation_id]).fetchall()
    return [str(r[0]) for r in rows if r[0] is not None]


def _excerpt_cleared(
    investigation_id: str,
    trail: SynthesisTrail,
    *,
    db_path: str,
    events_dir: str | None,
) -> bool:
    """Whether the thesis excerpt may be exported.

    The excerpt is prose written from the investigation's sources, so it can
    repeat any of them verbatim, and the per-node gate above never sees it.
    It clears only when the investigation has sources and every one resolves
    to a servable document. The sources are everything the investigation is
    recorded as standing on: the insight and question nodes it distilled
    (including one whose row is gone), the graph nodes and edges it inserted,
    the documents it gathered or its events anchor to, and every pin of the
    syntheses it archived. A source whose rights cannot be resolved withholds
    the excerpt, and so does having no traceable source at all."""
    node_ids = dict.fromkeys(
        [*distilled_node_ids(investigation_id, events_dir=events_dir), *trail.node_ids]
    )
    con = connect_read(db_path)
    try:
        synthesis_ids = dict.fromkeys([
            *trail.synthesis_ids,
            *_investigation_ids(
                con,
                "SELECT synthesis_id FROM syntheses WHERE investigation_id = ?",
                investigation_id,
            ),
        ])
        document_ids = dict.fromkeys([
            *trail.document_ids,
            *_investigation_ids(
                con,
                "SELECT document_id FROM documents WHERE investigation_id = ?",
                investigation_id,
            ),
        ])
        edge_ids = dict.fromkeys([
            *trail.edge_ids,
            *_investigation_ids(
                con,
                "SELECT edge_id FROM edges WHERE investigation_id = ?",
                investigation_id,
            ),
        ])
        sources = [
            *resolve_pin_sources(
                con,
                [
                    *(("node", n) for n in node_ids),
                    *(("edge", e) for e in edge_ids),
                    *(("document", d) for d in document_ids),
                ],
            ),
            *resolve_manifest_sources(con, list(synthesis_ids)),
        ]
    finally:
        con.close()
    return bool(sources) and all(s.resolved and s.servable for s in sources)


def build_body(
    investigation_id: str,
    *,
    db_path: str | None = None,
    events_dir: str | None = None,
) -> ResearchArtifactBody:
    graph_path = db_path or graph_db_path()
    view = distillation_for(investigation_id, db_path=graph_path, events_dir=events_dir)
    question = problem_question_from_events(investigation_id, events_dir=events_dir)
    if not question:
        question = f"Investigation {investigation_id}"

    text = _exportable_text([*view.insights, *view.questions], db_path=graph_path)
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
    trail = synthesis_from_events(investigation_id, events_dir=events_dir)
    withheld = trail.excerpt is not None and not _excerpt_cleared(
        investigation_id, trail, db_path=graph_path, events_dir=events_dir
    )
    agent_notes = load_persisted_agent_notes(investigation_id)
    return ResearchArtifactBody(
        investigation_id=investigation_id,
        problem_question=question,
        insights=insights,
        open_questions=questions,
        synthesis_excerpt=None if withheld else trail.excerpt,
        synthesis_withheld=withheld,
        source_event_ids=trail.source_event_ids,
        agent_notes=agent_notes,
    )