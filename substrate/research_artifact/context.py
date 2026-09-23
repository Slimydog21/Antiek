"""Load investigation question + synthesis excerpt from trajectory (read-only)."""

from __future__ import annotations

from dataclasses import dataclass, field

from substrate.event_log import trajectory
from substrate.schemas.events import ActionType


def problem_question_from_events(
    investigation_id: str,
    *,
    events_dir: str | None = None,
) -> str:
    for row in trajectory(investigation_id, events_dir=events_dir):
        if row.get("action_type") != ActionType.INVESTIGATION_START_REQUESTED.value:
            continue
        payload = row.get("payload") or {}
        if isinstance(payload, dict):
            q = (payload.get("question") or "").strip()
            if q:
                return q
    return ""


@dataclass(frozen=True)
class SynthesisTrail:
    """What the trajectory records about the investigation's synthesis.

    ``excerpt`` is the raw thesis prose and is NOT cleared for export. It is
    written from the investigation's sources and can repeat a gated passage
    verbatim, so ``build_body`` puts it through the source-aware rights gate
    before any surface carries it. The id tuples name what the thesis stood
    on, as the trajectory records it: the archived syntheses (whose manifests
    pin their sources), the documents events anchor to, and the graph nodes
    and edges the investigation inserted. A recorded id whose row is gone
    stays here, so the gate can count it as unresolved.
    """

    excerpt: str | None = None
    synthesis_ids: tuple[str, ...] = ()
    document_ids: tuple[str, ...] = ()
    node_ids: tuple[str, ...] = ()
    edge_ids: tuple[str, ...] = ()
    source_event_ids: list[str] = field(default_factory=list)


def _ordered_unique(values: list[str]) -> list[str]:
    return list(dict.fromkeys(values))


def _take(bucket: list[str], value: object) -> None:
    if isinstance(value, str) and value:
        bucket.append(value)


def synthesis_from_events(
    investigation_id: str,
    *,
    events_dir: str | None = None,
) -> SynthesisTrail:
    source_ids: list[str] = []
    synthesis_ids: list[str] = []
    document_ids: list[str] = []
    node_ids: list[str] = []
    edge_ids: list[str] = []
    excerpt: str | None = None
    for row in trajectory(investigation_id, events_dir=events_dir):
        at = row.get("action_type")
        eid = row.get("event_id")
        if eid:
            source_ids.append(str(eid))
        _take(synthesis_ids, row.get("synthesis_id"))
        _take(document_ids, row.get("document_id"))
        payload = row.get("payload") or {}
        if not isinstance(payload, dict):
            payload = {}
        if at == ActionType.GRAPH_NODE_INSERTED.value:
            _take(node_ids, payload.get("node_id"))
        elif at == ActionType.GRAPH_EDGE_INSERTED.value:
            _take(edge_ids, payload.get("edge_id"))
            _take(document_ids, payload.get("source_document_id"))
        elif at == ActionType.INVESTIGATION_COMPLETED.value:
            summary = (payload.get("thesis_summary") or "").strip()
            if summary:
                excerpt = summary
        elif at == ActionType.SYNTHESIS_ARCHIVED.value and not excerpt:
            excerpt = (payload.get("thesis_summary") or payload.get("summary") or "").strip() or None
    return SynthesisTrail(
        excerpt=excerpt,
        synthesis_ids=tuple(_ordered_unique(synthesis_ids)),
        document_ids=tuple(_ordered_unique(document_ids)),
        node_ids=tuple(_ordered_unique(node_ids)),
        edge_ids=tuple(_ordered_unique(edge_ids)),
        source_event_ids=_ordered_unique(source_ids)[-20:],
    )
