"""Load investigation question + synthesis excerpt from trajectory (read-only)."""

from __future__ import annotations

from dataclasses import dataclass, field

from substrate.event_log import trajectory, trajectory_read
from substrate.provenance.pointers import (
    Pointer,
    collect_child_investigations,
    collect_pointers,
    collect_syntheses,
)
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
    before any surface carries it.

    The rest names what the thesis stood on, read from every event of the
    investigation's trajectory and of every sub-investigation it handed work
    to (``investigation_ids``, the investigation first). ``pointers`` is every
    chunk, document, edge and source pointer ``collect_pointers`` finds in
    those events, envelope and payload, at any depth: the retriever's
    ``supporting_claims[].chunk_ids`` and ``edge_ids``, an edge's
    ``source_document_id``, a reading event's ``document_id`` and any pointer
    field a writer adds later, with no field list to fall behind.
    ``synthesis_ids`` are the archived syntheses (whose manifests pin their
    sources) and ``node_ids`` the graph nodes inserted. A recorded id whose
    row is gone stays here, so the gate can count it as unresolved.

    ``unreadable_investigation_ids`` are the investigations in the walk whose
    events could not all be read: none stored (a deleted log, or a child that
    never wrote one), a record that does not parse, an unreadable snapshot, or
    an id that is not an event-storage name, which is never read. What those
    stood on is unknown, so the gate withholds rather than clearing on the
    rest.
    """

    excerpt: str | None = None
    investigation_ids: tuple[str, ...] = ()
    synthesis_ids: tuple[str, ...] = ()
    node_ids: tuple[str, ...] = ()
    pointers: tuple[Pointer, ...] = ()
    source_event_ids: list[str] = field(default_factory=list)
    unreadable_investigation_ids: tuple[str, ...] = ()


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
    node_ids: list[str] = []
    pointers: dict[Pointer, None] = {}
    excerpt: str | None = None
    unreadable: list[str] = []
    # The investigation, then every sub-investigation any of their events
    # hands work to, each read once.
    pending = [investigation_id]
    walked: dict[str, None] = {}
    while pending:
        current = pending.pop(0)
        if current in walked:
            continue
        walked[current] = None
        own = current == investigation_id
        try:
            rows, complete = trajectory_read(current, events_dir=events_dir)
        except (OSError, ValueError):  # a corrupt snapshot; pyarrow's errors subclass these
            rows, complete = [], False
        if not complete:
            unreadable.append(current)
        for row in rows:
            at = row.get("action_type")
            if own and row.get("event_id"):
                source_ids.append(str(row["event_id"]))
            synthesis_ids.extend(collect_syntheses(row))
            pointers.update(dict.fromkeys(collect_pointers(row)))
            pending.extend(collect_child_investigations(row))
            payload = row.get("payload") or {}
            if not isinstance(payload, dict):
                payload = {}
            if at == ActionType.GRAPH_NODE_INSERTED.value:
                _take(node_ids, payload.get("node_id"))
            elif not own:
                continue
            elif at == ActionType.INVESTIGATION_COMPLETED.value:
                summary = (payload.get("thesis_summary") or "").strip()
                if summary:
                    excerpt = summary
            elif at == ActionType.SYNTHESIS_ARCHIVED.value and not excerpt:
                excerpt = (
                    payload.get("thesis_summary") or payload.get("summary") or ""
                ).strip() or None
    return SynthesisTrail(
        excerpt=excerpt,
        investigation_ids=tuple(walked),
        synthesis_ids=tuple(_ordered_unique(synthesis_ids)),
        node_ids=tuple(_ordered_unique(node_ids)),
        pointers=tuple(pointers),
        source_event_ids=_ordered_unique(source_ids)[-20:],
        unreadable_investigation_ids=tuple(unreadable),
    )
