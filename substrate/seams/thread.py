"""Cross-workflow *thread* reconstruction (antiek-unified SPR-06 M1).

A **thread** is the trajectory of ONE graph entity across the four workflows
(Research / Read / Write / Speak): a Speak interview claim → an insight → a
Write outline block → a Read published page. The load-bearing invariant — the
one the whole flywheel rests on — is that *the same node is the same node
everywhere*. A thread is the operator-navigable view of that trajectory.

This module is a **view, not a store** (rigor #2). It writes NOTHING to the
substrate and adds NO new node or edge type. It reconstructs the thread on read
by composing two sources that already exist:

* the **SPR-03 seam events** (``seam.*`` action types, payloads in
  ``substrate/schemas/events.py``) — the cross-workflow *hops*: each seam event
  records one workflow handing the entity to the next, carrying the entity id +
  kind by reference (never a copy — guarded by ``tests/test_seam_no_copy.py``).
* the existing **provenance edges** (``substrate/graph/schema.py`` ``edges``
  table, vocabulary in ``substrate/graph/insight_question.py`` —
  e.g. ``supported_by``, ``answers``) — the *within-graph* links a hop may rest
  on (an insight supported_by a claim). The thread walk *reuses* these; it does
  not invent a traversal (diligence #4).

Why a view and not a stored ``Thread`` graph object (the steelman, rigor #2):
materializing a thread as a row would make reads O(1) and the trajectory
explicit. It loses because a stored thread is a **second source of truth** that
drifts from the edges/seam events it summarizes the instant either changes —
exactly the duplication the master spec forbids ("one graph entity everywhere").
The seam events + edges are authoritative; the thread is derived from them every
read. If read latency ever demands materialization, cache it with *explicit
invalidation keyed on the seam-event/edge log* and keep the events authoritative
— never promote the cache to canonical.

Dependency injection, not a DB handle: ``reconstruct_thread`` takes the seam
events (and optional provenance edges) as inputs. A live caller passes events
read via ``substrate.event_log.trajectory`` and edges from a read-only DuckDB
query (``interfaces/research/api/thread.py``); the SPR-06 no-duplicate test
(``tests/test_thread_no_duplicate.py``) passes fixtures. This keeps the
reconstruction (a) off the DuckDB single-writer critical path — it only ever
reads — and (b) testable against a deterministic fixture exactly the way the
SPR-03 no-copy guard exercises its seams with fakes.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Literal

from .contracts import EntityKind, Workflow

# The seam ``action_type`` strings, paired with their (from_workflow,
# to_workflow). Mirrors ``substrate/schemas/events.py`` ActionType.SEAM_*.
# A seam event hands the entity from ``from_workflow`` to ``to_workflow``;
# the thread walk turns a chain of these into ordered hops. The boolean marks
# provisional contracts for honest breadcrumb rendering; every current seam is
# committed.
_SEAM_ACTION_DIRECTION: dict[str, tuple[Workflow, Workflow, bool]] = {
    "seam.research_to_read": ("research", "read", False),
    "seam.read_to_research": ("read", "research", False),
    "seam.read_to_write": ("read", "write", False),
    "seam.write_to_read": ("write", "read", False),
    "seam.speak_to_write": ("speak", "write", False),
    "seam.speak_to_read": ("speak", "read", False),
    "seam.write_to_speak": ("write", "speak", False),
}


@dataclass(frozen=True)
class ThreadHop:
    """One workflow's touch on the thread.

    A hop is *which workflow* held *which entity* (by reference — the same id
    the seam carried), and the *seam event* that handed the entity here (None
    for the origin hop, which no seam produced — it is where the entity was
    first created). ``built`` records whether the receiving workflow has a real
    surface yet; an unbuilt hop renders as the SPR-04 honest stub, never a fake
    (intellectual honesty #1).
    """

    workflow: Workflow
    # The entity AS REFERENCED on this hop — the same id the seam carried. The
    # no-duplicate guard asserts ``entity_id`` is identical across the hops that
    # carry the canonical entity (see ``assert_single_canonical_entity``).
    entity_id: str
    entity_kind: EntityKind
    # The seam event id that produced this hop (the handoff into this workflow).
    # None on the origin hop (the entity's birth — no seam created it).
    seam_event_id: str | None
    seam_action_type: str | None
    # The originating provenance reference the seam carried (an event/region/
    # source id), so the hop is auditable back to the trajectory. None at origin.
    provenance_ref: str | None
    # Whether the workflow this hop lands in has a built surface. Drives the
    # honest stub — the thread does not lie about what exists.
    built: bool = True
    # True only when a seam contract is provisional, so the breadcrumb labels
    # the unfinished hop honestly. All current contracts are committed.
    via_provisional_seam: bool = False


@dataclass(frozen=True)
class ThreadStub:
    """An honest placeholder for a workflow the thread *would* touch but that is
    not built yet (intellectual honesty #1). A stub is NEVER a fabricated
    entity — it names the workflow and says plainly it is unavailable. The
    SPR-04 ``WorkflowStub`` surface renders the same honesty in the UI.
    """

    workflow: Workflow
    reason: str


@dataclass(frozen=True)
class Thread:
    """One entity's reconstructed cross-workflow trajectory — a VIEW.

    ``hops`` is the ordered list of workflow touches (origin first). ``stubs``
    are workflows the trajectory references but that are not built; they are
    surfaced honestly, never faked into ``hops``. ``canonical_entity_id`` is the
    single node id the thread is *about* — every hop that carries the canonical
    entity references this exact id (the no-duplicate invariant).
    """

    canonical_entity_id: str
    canonical_entity_kind: EntityKind
    hops: tuple[ThreadHop, ...]
    stubs: tuple[ThreadStub, ...] = ()

    @property
    def workflows(self) -> tuple[Workflow, ...]:
        """The ordered workflows the thread touched (deduped, origin first)."""
        seen: list[Workflow] = []
        for h in self.hops:
            if h.workflow not in seen:
                seen.append(h.workflow)
        return tuple(seen)

    @property
    def is_degenerate(self) -> bool:
        """A 1-workflow thread (the entity never crossed a seam)."""
        return len(self.workflows) <= 1


# Type aliases for the injected inputs. A seam event is the dict shape
# ``substrate.event_log.trajectory`` yields (event_id + action_type + payload),
# or any mapping exposing those keys. A provenance edge is the within-graph link
# vocabulary from ``substrate/graph/insight_question.py``.
SeamEvent = Mapping[str, Any]
ProvenanceEdge = Mapping[str, Any]

ContentField = Literal["content", "text"]
# Fields whose presence on a seam event would mean the entity was COPIED inline
# rather than referenced. Seam payloads deliberately carry no such field
# (substrate/schemas/events.py); their presence is a provenance bug the thread
# reconstruction refuses to launder.
_COPY_INDICATOR_FIELDS: tuple[str, ...] = ("content", "text", "body", "full_text")


def _payload_of(event: SeamEvent) -> Mapping[str, Any]:
    payload = event.get("payload")
    if isinstance(payload, Mapping):
        return payload
    return {}


def _seam_entity(event: SeamEvent) -> tuple[str | None, str | None, str | None]:
    """Pull (entity_id, entity_kind, provenance_ref) from a seam event,
    tolerating both the envelope-level and payload-level placement."""
    payload = _payload_of(event)
    entity_id = payload.get("entity_id", event.get("entity_id"))
    entity_kind = payload.get("entity_kind", event.get("entity_kind"))
    provenance_ref = payload.get("provenance_ref", event.get("provenance_ref"))
    return (
        str(entity_id) if entity_id is not None else None,
        str(entity_kind) if entity_kind is not None else None,
        str(provenance_ref) if provenance_ref is not None else None,
    )


def _detect_inline_copy(event: SeamEvent) -> str | None:
    """Return the name of a copy-indicating field if the seam event inlined the
    entity's content (a provenance bug), else None. A seam moves a *reference*;
    a payload that carries the entity's text is a fork, and the thread walk must
    not silently weave it in."""
    payload = _payload_of(event)
    for fld in _COPY_INDICATOR_FIELDS:
        val = payload.get(fld)
        if isinstance(val, str) and val.strip():
            return fld
    return None


def reconstruct_thread(
    node_id: str,
    *,
    seam_events: Iterable[SeamEvent],
    origin_entity_kind: EntityKind | None = None,
    provenance_edges: Sequence[ProvenanceEdge] = (),
    built_workflows: Iterable[Workflow] = ("research", "read", "write", "speak"),
) -> Thread:
    """Reconstruct ``node_id``'s cross-workflow thread — a VIEW, no writes.

    Walks the SPR-03 seam events (the cross-workflow hops) that carry
    ``node_id`` by reference, in emission order, and composes them into an
    ordered list of :class:`ThreadHop`. The within-graph ``provenance_edges``
    (``supported_by`` / ``answers`` / etc. — diligence #4) let the origin hop
    name the workflow that birthed the entity even before any seam fired.

    Args:
        node_id: the canonical entity id the thread is about. EVERY hop that
            carries the canonical entity references *this exact id* — that is
            the no-duplicate invariant (assert it with
            ``assert_single_canonical_entity``).
        seam_events: the seam events (the shape ``trajectory`` yields, or any
            mapping with ``event_id`` / ``action_type`` / ``payload``). Only
            events whose ``entity_id`` equals ``node_id`` participate.
        origin_entity_kind: the entity kind at birth, if known (used for the
            origin hop when no seam names it). Defaults to the first seam's kind.
        provenance_edges: the within-graph edges touching ``node_id`` (read-only
            graph context). Reserved for richer origin/depth reconstruction;
            the seam events are the cross-workflow hop source.
        built_workflows: which workflows have a built surface today. A hop into
            an unbuilt workflow is flagged ``built=False`` (honest stub), never
            dropped or faked.

    Raises:
        ValueError: if a seam event in the thread's lineage inlines the entity's
            content (a copied/forked entity — the thread refuses to launder a
            copy).

    A note on copy detection (rigor #3): the walk does NOT simply filter to
    events whose ``entity_id == node_id`` — that would *silently exclude* a
    forked copy (a hop with a fresh, wrong id) and the thread would look clean
    while a copy existed. Instead it follows the seam **lineage**: events that
    reference this node id, plus events chained into the same trajectory by a
    shared ``provenance_ref`` (the originating event lineage). A buggy seam that
    copied the entity keeps the lineage but mints a divergent id; the walk pulls
    that hop in *with its wrong id* so :func:`assert_single_canonical_entity`
    catches it. Surfacing the fork is the whole point of the guard.
    """
    built = set(built_workflows)

    # First pass: parse every seam event into a uniform tuple, flag inline
    # copies (content in the payload — a fork by construction).
    parsed: list[tuple[SeamEvent, str, str | None, str, str | None, str | None]] = []
    for ev in seam_events:
        action_type = str(ev.get("action_type") or "")
        if action_type not in _SEAM_ACTION_DIRECTION:
            continue
        entity_id, entity_kind, provenance_ref = _seam_entity(ev)
        copied_field = _detect_inline_copy(ev)
        parsed.append(
            (ev, action_type, entity_id, entity_kind or "", provenance_ref, copied_field)
        )

    # Build the thread's lineage as a connected component. A seam event belongs
    # to the lineage if it shares any "lineage token" already in the component.
    # The tokens of a seam event are: its entity_id, its provenance_ref, and its
    # own event_id (so a downstream seam whose provenance_ref points at this
    # seam's event_id chains in — that is how a trajectory threads together).
    # Seed with the requested node id. This is what lets a forked-id copy (same
    # lineage, divergent entity_id) stay in the component and surface its wrong
    # id, rather than being silently dropped by an id-equality filter.
    def _tokens(
        entity_id: str | None, provenance_ref: str | None, event_id: str | None
    ) -> set[str]:
        return {t for t in (entity_id, provenance_ref, event_id) if t}

    lineage: set[str] = {node_id}
    changed = True
    while changed:
        changed = False
        for ev, _action, entity_id, _kind, provenance_ref, _copied in parsed:
            event_id = str(ev.get("event_id")) if ev.get("event_id") else None
            toks = _tokens(entity_id, provenance_ref, event_id)
            if toks & lineage:
                new_toks = toks - lineage
                if new_toks:
                    lineage |= toks
                    changed = True

    # Keep the lineage's seam events, ordered by emission time then event id
    # (matching trajectory()'s own ordering). Reject any inline-content copy.
    relevant: list[tuple[SeamEvent, str, str, str | None, str | None]] = []
    for ev, action_type, entity_id, entity_kind, provenance_ref, copied_field in parsed:
        event_id = str(ev.get("event_id")) if ev.get("event_id") else None
        if not (_tokens(entity_id, provenance_ref, event_id) & lineage):
            continue
        if copied_field is not None:
            raise ValueError(
                f"seam event {ev.get('event_id')!r} ({action_type}) inlined the "
                f"entity content in field {copied_field!r} — that is a copied "
                f"entity (a provenance bug), not a by-reference handoff. The "
                f"thread will not launder a fork. See tests/test_seam_no_copy.py."
            )
        relevant.append(
            (ev, action_type, entity_kind or "", provenance_ref, entity_id)
        )

    relevant.sort(
        key=lambda t: (
            str(t[0].get("emitted_at") or ""),
            str(t[0].get("event_id") or ""),
        )
    )

    resolved_kind: EntityKind = (
        origin_entity_kind
        if origin_entity_kind is not None
        else (relevant[0][2] if relevant else "insight_node")  # type: ignore[assignment]
    )

    hops: list[ThreadHop] = []
    stubs: list[ThreadStub] = []

    if not relevant:
        # Degenerate thread: the entity exists in exactly one workflow (no seam
        # has handed it anywhere yet). The origin workflow defaults to research
        # for graph nodes; provenance_edges could refine this in a richer walk.
        origin_wf: Workflow = "research"
        hops.append(
            ThreadHop(
                workflow=origin_wf,
                entity_id=node_id,
                entity_kind=resolved_kind,
                seam_event_id=None,
                seam_action_type=None,
                provenance_ref=None,
                built=origin_wf in built,
            )
        )
        return Thread(
            canonical_entity_id=node_id,
            canonical_entity_kind=resolved_kind,
            hops=tuple(hops),
            stubs=(),
        )

    # The origin hop is the FROM-workflow of the first seam (where the entity
    # lived before it was first handed across a boundary). No seam produced it.
    # Its entity id is the canonical node id (the origin is the entity itself).
    first_ev, first_action, _kind, _prov, _eid = relevant[0]
    origin_from, _to, _prov_seam = _SEAM_ACTION_DIRECTION[first_action]
    hops.append(
        ThreadHop(
            workflow=origin_from,
            entity_id=node_id,
            entity_kind=resolved_kind,
            seam_event_id=None,
            seam_action_type=None,
            provenance_ref=None,
            built=origin_from in built,
        )
    )

    # Each seam adds the TO-workflow hop (the handoff into the next workflow).
    # The hop carries the id THIS seam actually referenced (``hop_entity_id``) —
    # NOT a forced node_id. If a buggy seam copied the entity, the hop surfaces
    # the divergent id here and the no-duplicate guard fails on it (rigor #3).
    for ev, action_type, _kind, provenance_ref, hop_entity_id in relevant:
        _from, to_wf, is_provisional = _SEAM_ACTION_DIRECTION[action_type]
        hop_built = to_wf in built
        hops.append(
            ThreadHop(
                workflow=to_wf,
                entity_id=hop_entity_id if hop_entity_id is not None else node_id,
                entity_kind=resolved_kind,
                seam_event_id=str(ev.get("event_id")) if ev.get("event_id") else None,
                seam_action_type=action_type,
                provenance_ref=provenance_ref,
                built=hop_built,
                via_provisional_seam=is_provisional,
            )
        )
        if not hop_built:
            stubs.append(
                ThreadStub(
                    workflow=to_wf,
                    reason=(
                        f"{to_wf} has no built surface yet — this hop is shown "
                        f"as an honest stub, not a fabricated entity."
                    ),
                )
            )

    return Thread(
        canonical_entity_id=node_id,
        canonical_entity_kind=resolved_kind,
        hops=tuple(hops),
        stubs=tuple(stubs),
    )


def assert_single_canonical_entity(thread: Thread) -> None:
    """The load-bearing no-duplicate assertion at the THREAD level (SPR-06 M4).

    Composes the SPR-03 ``tests/test_seam_no_copy.py::_assert_no_copy``
    same-node-id guarantee across a *whole* trajectory: every hop carrying the
    canonical entity must reference the SAME node id. If any hop holds a
    different id, a workflow is holding a copy/fork rather than the one node —
    the breadcrumb would lie, and this assertion fails (rigor #3 — a copy must
    fail the guard or the guard proves nothing).

    A breadcrumb over copied entities is worse than no breadcrumb: it asserts a
    continuity that the data does not support (defensibility #5). This assertion
    is therefore the navigation's *warrant* — if it cannot pass, the thread must
    not ship.
    """
    canonical = thread.canonical_entity_id
    for hop in thread.hops:
        assert hop.entity_id == canonical, (
            f"thread holds a copy: canonical node_id={canonical!r} but the "
            f"{hop.workflow!r} hop references {hop.entity_id!r} — a different id "
            f"means that workflow holds a fork, not the one node. This is the "
            f"provenance bug the SPR-03 no-copy seam guard "
            f"(tests/test_seam_no_copy.py::_assert_no_copy) forbids, composed at "
            f"the thread level."
        )


__all__ = [
    "Thread",
    "ThreadHop",
    "ThreadStub",
    "SeamEvent",
    "ProvenanceEdge",
    "reconstruct_thread",
    "assert_single_canonical_entity",
]
