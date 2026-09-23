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
    resolve_pin_sources,
    resolve_refs,
    resolve_synthesis_sources,
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


def _investigation_ids(con: Any, sql: str, investigation_ids: tuple[str, ...]) -> list[str]:
    if not investigation_ids:
        return []
    ph = ",".join("?" for _ in investigation_ids)
    rows = con.execute(sql.format(ph=ph), list(investigation_ids)).fetchall()
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
    to a servable document.

    The sources are everything the investigation, and every sub-investigation
    it handed work to, is recorded as standing on. From the trajectories:
    every chunk, document, edge and source pointer in any event (found by key
    shape, so a pointer field no code names yet is still read), the syntheses
    they name, the graph nodes they inserted and the insight and question
    nodes they distilled (including one whose row is gone). From the graph:
    the syntheses, documents and edges written under those investigation ids.
    A node grounds on every pointer its metadata records and every
    supported_by edge; an edge on its chunk, its document and the pointers of
    its metadata and endpoints; a recorded synthesis whose row or manifest is
    gone counts as one unresolved source. A pointer that cannot be followed,
    or a document that is not servable, withholds the excerpt, and so does
    having no traceable source at all."""
    inv_ids = trail.investigation_ids or (investigation_id,)
    node_ids = dict.fromkeys([
        *(n for iid in inv_ids for n in distilled_node_ids(iid, events_dir=events_dir)),
        *trail.node_ids,
    ])
    con = connect_read(db_path)
    try:
        synthesis_ids = dict.fromkeys([
            *trail.synthesis_ids,
            *_investigation_ids(
                con,
                "SELECT synthesis_id FROM syntheses WHERE investigation_id IN ({ph})",
                inv_ids,
            ),
        ])
        recorded: list[tuple[str, str]] = [
            *trail.pointers,
            *(
                ("document", d)
                for d in _investigation_ids(
                    con,
                    "SELECT document_id FROM documents WHERE investigation_id IN ({ph})",
                    inv_ids,
                )
            ),
            *(
                ("edge", e)
                for e in _investigation_ids(
                    con,
                    "SELECT edge_id FROM edges WHERE investigation_id IN ({ph})",
                    inv_ids,
                )
            ),
        ]
        sources = [
            *resolve_pin_sources(
                con,
                [*(("node", n) for n in node_ids), *dict.fromkeys(recorded)],
            ),
            *resolve_synthesis_sources(con, list(synthesis_ids)),
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