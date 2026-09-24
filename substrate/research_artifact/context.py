"""Load investigation question + synthesis excerpt from trajectory (read-only)."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any

from substrate.event_log import (
    default_events_dir,
    is_event_storage_id,
    trajectory,
    trajectory_read,
)
from substrate.provenance.pointers import (
    Pointer,
    collect_child_investigations,
    collect_parent_investigations,
    collect_pointers,
    collect_syntheses,
    evidence_payload_intact,
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
    to (``investigation_ids``, the investigation first): a child its events
    name (an escalated question's research), and a child whose own log names
    it as parent (a cascade leaf, a chase), which the parent's events never
    name. ``pointers`` is every
    chunk, document, edge and source pointer ``collect_pointers`` finds in
    those events, envelope and payload, at any depth: the retriever's
    ``supporting_claims[].chunk_ids`` and ``edge_ids``, an edge's
    ``source_document_id``, a reading event's ``document_id`` and any pointer
    field a writer adds later, with no field list to fall behind.
    ``synthesis_ids`` are the archived syntheses (whose manifests pin their
    sources) and ``node_ids`` the graph nodes inserted. A recorded id whose
    row is gone stays here, so the gate can count it as unresolved.

    ``unreadable_investigation_ids`` are the investigations in the walk whose
    events could not all be read: a stored log holding a record that is not a
    usable event (or none at all), an unreadable snapshot, an id that is not
    an event-storage name (never read), or a child some event says ran whose
    log is gone. What those stood on is unknown, so the gate withholds rather
    than clearing on the rest. A child with no log that every reference only
    reserved (``launched`` false on its escalation) never ran and is not
    counted. A child whose log is gone and that no readable event names as
    having run cannot be seen at all: the parent's events do not record a
    cascade leaf or a chase, so its own log is the only link.
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


def _spawned_children(events_dir: str | None) -> dict[str, list[str]]:
    """Every investigation whose own log names another as its parent, keyed
    by that parent. A cascade leaf and a chase child record the link only in
    their own log, so finding them reads every stored log once."""
    root = events_dir or default_events_dir()
    try:
        names = os.listdir(root)
    except OSError:
        return {}
    stems = {
        name.rsplit(".", 1)[0] for name in names if name.endswith((".jsonl", ".parquet"))
    }
    children: dict[str, list[str]] = {}
    for iid in sorted(stems):
        if not is_event_storage_id(iid):
            continue
        try:
            rows = trajectory_read(iid, events_dir=root).rows
        except Exception:  # noqa: BLE001 - one unrelated unreadable log must not fail every export
            continue
        for row in rows:
            for parent in collect_parent_investigations(row):
                if parent != iid:
                    children.setdefault(parent, []).append(iid)
    return {parent: _ordered_unique(kids) for parent, kids in children.items()}


def _reserved_child(row: dict[str, Any]) -> str | None:
    """The child id an escalation only reserved (``launched`` false), if any."""
    if row.get("action_type") != ActionType.QUESTION_ESCALATED_TO_RESEARCH.value:
        return None
    payload = row.get("payload")
    if not isinstance(payload, dict) or payload.get("launched") is not False:
        return None
    child = payload.get("child_investigation_id")
    return child.strip() if isinstance(child, str) and child.strip() else None


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
    absent: list[str] = []
    reserved: set[str] = set()
    launched: set[str] = set()
    spawned = _spawned_children(events_dir)
    # The investigation, then every sub-investigation any of their events
    # hands work to or that names one of them as parent, each read once.
    pending = [investigation_id]
    walked: dict[str, None] = {}
    while pending:
        current = pending.pop(0)
        if current in walked:
            continue
        walked[current] = None
        own = current == investigation_id
        try:
            rows, complete, stored = trajectory_read(current, events_dir=events_dir)
        except Exception:  # noqa: BLE001 - a dependency that cannot be read is unresolved, not a crash
            rows, complete, stored = [], False, True
        if complete and not all(
            evidence_payload_intact(row.get("action_type"), row.get("payload")) for row in rows
        ):
            complete = False
        if not complete:
            (unreadable if stored else absent).append(current)
        backward = spawned.get(current, [])
        launched.update(backward)
        pending.extend(backward)
        for row in rows:
            at = row.get("action_type")
            if own and row.get("event_id"):
                source_ids.append(str(row["event_id"]))
            synthesis_ids.extend(collect_syntheses(row))
            pointers.update(dict.fromkeys(collect_pointers(row)))
            only_reserved = _reserved_child(row)
            for child in collect_child_investigations(row):
                (reserved if child == only_reserved else launched).add(child)
                pending.append(child)
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
    # Decided once every reference is known: a child with no log never ran
    # only if every event that names it reserved it.
    unreadable.extend(
        iid for iid in absent
        if iid == investigation_id or iid in launched or iid not in reserved
    )
    return SynthesisTrail(
        excerpt=excerpt,
        investigation_ids=tuple(walked),
        synthesis_ids=tuple(_ordered_unique(synthesis_ids)),
        node_ids=tuple(_ordered_unique(node_ids)),
        pointers=tuple(pointers),
        source_event_ids=_ordered_unique(source_ids)[-20:],
        unreadable_investigation_ids=tuple(unreadable),
    )
