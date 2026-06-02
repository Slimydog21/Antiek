"""Cross-workflow thread navigation API (antiek-unified SPR-06 M1).

A read-only HTTP surface over :func:`substrate.seams.thread.reconstruct_thread`.
Given any node id, it reconstructs that entity's cross-workflow *thread* — the
ordered list of workflow touches the SPR-03 seam events recorded — and returns
it for the frontend breadcrumb (``apps/reading/src/shell/ThreadBreadcrumb.tsx``)
and cross-workflow jump (``ThreadJump.tsx``).

This is **read-only traversal** (the SPR-06 invariant): it opens the substrate
read-only, reads seam events from the per-investigation event log, and writes
NOTHING. It is off the DuckDB single-writer critical path entirely — concurrent
with the host writer (``runtime/db_lock.connect_read``). It adds no node/edge
type; the thread is a view derived on read.

Seam events live per-investigation in the event log (``substrate/event_log`` →
JSONL/Parquet under ``default_events_dir()``). To reconstruct a thread we scan
those files for ``seam.*`` events referencing the requested node id. This is a
linear scan today (single operator, G7); when the operator volume warrants it,
the right move is a seam-event index, NOT materializing the thread as a stored
entity (that would be the second-source-of-truth drift the master spec forbids —
see ``substrate/seams/thread.py`` rigor #2).
"""

from __future__ import annotations

import os

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from substrate.event_log import default_events_dir, trajectory
from substrate.seams.contracts import EntityKind, Workflow
from substrate.seams.thread import (
    Thread,
    ThreadHop,
    ThreadStub,
    assert_single_canonical_entity,
    reconstruct_thread,
)

# The set of action types the thread walk cares about — the seam handoffs.
_SEAM_ACTION_TYPES = frozenset(
    {
        "seam.research_to_read",
        "seam.read_to_research",
        "seam.read_to_write",
        "seam.write_to_read",
        "seam.speak_to_write",
        "seam.speak_to_read",
        "seam.write_to_speak",
    }
)


class ThreadHopResponse(BaseModel):
    """One workflow touch on the thread, for the frontend breadcrumb."""

    workflow: Workflow
    entity_id: str
    entity_kind: EntityKind
    seam_event_id: str | None = None
    seam_action_type: str | None = None
    provenance_ref: str | None = None
    built: bool = True
    via_provisional_seam: bool = False

    @classmethod
    def of(cls, hop: ThreadHop) -> ThreadHopResponse:
        return cls(
            workflow=hop.workflow,
            entity_id=hop.entity_id,
            entity_kind=hop.entity_kind,
            seam_event_id=hop.seam_event_id,
            seam_action_type=hop.seam_action_type,
            provenance_ref=hop.provenance_ref,
            built=hop.built,
            via_provisional_seam=hop.via_provisional_seam,
        )


class ThreadStubResponse(BaseModel):
    """An honest unbuilt-workflow placeholder (never a fabricated entity)."""

    workflow: Workflow
    reason: str

    @classmethod
    def of(cls, stub: ThreadStub) -> ThreadStubResponse:
        return cls(workflow=stub.workflow, reason=stub.reason)


class ThreadResponse(BaseModel):
    """One entity's reconstructed cross-workflow trajectory (a VIEW)."""

    canonical_entity_id: str
    canonical_entity_kind: EntityKind
    hops: list[ThreadHopResponse]
    stubs: list[ThreadStubResponse]
    is_degenerate: bool

    @classmethod
    def of(cls, thread: Thread) -> ThreadResponse:
        return cls(
            canonical_entity_id=thread.canonical_entity_id,
            canonical_entity_kind=thread.canonical_entity_kind,
            hops=[ThreadHopResponse.of(h) for h in thread.hops],
            stubs=[ThreadStubResponse.of(s) for s in thread.stubs],
            is_degenerate=thread.is_degenerate,
        )


def _collect_seam_events(events_dir: str | None = None) -> list[dict[str, object]]:
    """Scan every investigation's event log for ``seam.*`` events. Read-only.

    Linear scan across the per-investigation files; fine for a single operator
    (G7). Returns the raw event dicts (the shape ``trajectory`` yields), which
    ``reconstruct_thread`` filters by node id.
    """
    d = events_dir or default_events_dir()
    if not os.path.isdir(d):
        return []
    seam_events: list[dict[str, object]] = []
    seen_investigations: set[str] = set()
    for fn in sorted(os.listdir(d)):
        if fn.endswith(".parquet"):
            iid = fn[: -len(".parquet")]
        elif fn.endswith(".jsonl"):
            iid = fn[: -len(".jsonl")]
        else:
            continue
        if iid in seen_investigations:
            continue  # prefer parquet (sealed); trajectory() handles precedence
        seen_investigations.add(iid)
        for row in trajectory(iid, events_dir=events_dir):
            if str(row.get("action_type") or "") in _SEAM_ACTION_TYPES:
                seam_events.append(row)
    return seam_events


def build_thread(
    node_id: str,
    *,
    events_dir: str | None = None,
    origin_entity_kind: EntityKind | None = None,
) -> Thread:
    """Reconstruct ``node_id``'s thread from the event log. Read-only.

    Composes the SPR-03 seam events into the cross-workflow view, then runs the
    load-bearing no-duplicate assertion (``assert_single_canonical_entity``)
    before returning — a thread over copied entities must never be served (the
    breadcrumb's warrant, defensibility #5).
    """
    seam_events = _collect_seam_events(events_dir=events_dir)
    thread = reconstruct_thread(
        node_id,
        seam_events=seam_events,
        origin_entity_kind=origin_entity_kind,
    )
    # The navigation's warrant: refuse to serve a thread that holds a fork.
    assert_single_canonical_entity(thread)
    return thread


def make_router(*, events_dir: str | None = None) -> APIRouter:
    """Build the read-only thread-navigation router.

    GET /thread/{node_id} — reconstruct the entity's cross-workflow thread.
    """
    router = APIRouter(tags=["thread"])

    @router.get("/thread/{node_id}", response_model=ThreadResponse)
    async def get_thread(node_id: str) -> ThreadResponse:
        if not node_id.strip():
            raise HTTPException(status_code=400, detail="node_id is required")
        try:
            thread = build_thread(node_id, events_dir=events_dir)
        except AssertionError as exc:
            # The no-duplicate guard failed — the thread holds a copy. Refusing
            # to serve is correct: a breadcrumb over forked entities lies.
            raise HTTPException(
                status_code=409,
                detail=f"thread integrity violation (copied entity): {exc}",
            ) from exc
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return ThreadResponse.of(thread)

    return router


__all__ = [
    "ThreadResponse",
    "ThreadHopResponse",
    "ThreadStubResponse",
    "build_thread",
    "make_router",
]
