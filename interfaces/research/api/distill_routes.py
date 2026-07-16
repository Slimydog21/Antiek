"""DRW SPR-03 transport — the distill (insights / open questions / living
notes) REST surface.

Two endpoints, both over the shipped note-taker + insight/question graph —
this router wires, it does not rebuild:

* ``GET  /research/{investigation_id}/distill`` (M2) — the durable product
  of a research: its insight + question nodes with current text + grounding,
  read straight off the graph (``roles.note_taker.distillation_for``). Reads
  the live node row, so a note that was challenged shows its refined text.

* ``POST /research/notes/{node_id}/challenge`` (M3 + M4) — drive the shipped
  living-note path. The route owns NONE of the determinism: it computes a
  monotonic ``seq`` (strictly greater than the node's last applied seq, so a
  fresh user challenge wins over a stale background refinement), then calls
  ``living_note.challenge_note`` with the challenger's production resolver.
  - resolver refines → the note mutates in place (``challenge_note`` →
    ``apply_refinement`` under ``runtime/db_lock``; no duplicate node);
  - resolver declines → escalation: a reserved (un-launched) child research
    id (``nothing is launched here`` — SPR-04/05 launch it);
  - no model configured → 503 + honest reason, NOT an escalation and NOT a
    fabricated refinement (the surface shows ``AIActionFailure``).

Same standalone-``APIRouter`` + one-line ``include_router`` discipline as
``cascade_routes`` / ``speak_routes`` so the hot ``create_app`` factory stays
mergeable. Single-writer honored: the only graph write here is the
challenge, and it serializes through ``runtime/db_lock`` inside the shipped
``challenge_note`` (the route opens no connection of its own for writes).
"""

from __future__ import annotations

import os
import sys
from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

# Direct import — interfaces/research/api/ depends on substrate + roles.
_PKG_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
if _PKG_ROOT not in sys.path:
    sys.path.insert(0, _PKG_ROOT)

from roles.challenger import ChallengeUnavailable, make_dispatch_resolver  # noqa: E402
from roles.note_taker import (  # noqa: E402
    LivingNoteHistoryIntegrityError,
    LivingNoteHistoryNotFound,
    distillation_for,
    living_note_history,
)
from roles.note_taker.living_note import (  # noqa: E402
    ChallengeRequestConflict,
    ChallengeRequestInProgress,
    LivingNoteScopeConflict,
    challenge_note,
)
from runtime.db_lock import connect_read  # noqa: E402
from substrate.graph import default_db_path, ensure_initialized  # noqa: E402

distill_router = APIRouter(prefix="/research", tags=["distill"])


def _db() -> str:
    path = default_db_path()
    ensure_initialized(path)
    return path


# ---------------------------------------------------------------------------
# Models — the surface's view of a distilled node. No node-id jargon leaks
# into rendered copy; the id rides as an opaque handle the challenge call
# echoes back, never a label.
# ---------------------------------------------------------------------------


class DistilledNodeOut(BaseModel):
    node_id: str
    kind: str                       # "insight" | "question"
    text: str
    confidence: str | None = None
    source_document_id: str | None = None
    refinement_count: int = 0
    escalated: bool = False
    reserved_child_investigation_id: str | None = None


class DistillationOut(BaseModel):
    investigation_id: str
    insights: list[DistilledNodeOut]
    questions: list[DistilledNodeOut]


class ChallengeRequest(BaseModel):
    investigation_id: str = Field(..., min_length=1)
    challenge_text: str = Field(default="", max_length=2000)
    idempotency_key: str = Field(..., min_length=16, max_length=128, pattern=r"^[A-Za-z0-9._:-]+$")
    origin_note_id: str | None = Field(default=None, min_length=1, max_length=256)


class ChallengeOut(BaseModel):
    node_id: str
    # exactly one of {refined, superseded, escalated} describes the outcome
    applied: bool                   # the note's text changed in place
    superseded: bool = False        # a stale refinement lost the seq race
    new_text: str | None = None
    escalated: bool = False
    reserved_child_investigation_id: str | None = None


class NoteHistoryEntryOut(BaseModel):
    event_id: str
    source_investigation_id: str
    sequence: int
    previous_sequence: int
    previous_text: str
    new_text: str
    reason: str
    outcome: Literal["applied", "superseded"]
    delivery_state: Literal["pending", "delivered"]
    emitted_at: str


class NoteHistoryOut(BaseModel):
    investigation_id: str
    node_id: str
    current_text: str
    current_sequence: int
    refinement_count: int
    authoritative_applied_count: int
    superseded_count: int
    complete: bool
    entries: list[NoteHistoryEntryOut]


# ---------------------------------------------------------------------------
# M2 — read the distilled insights + open questions
# ---------------------------------------------------------------------------


@distill_router.get("/{investigation_id}/distill", response_model=DistillationOut)
async def get_distillation(investigation_id: str) -> DistillationOut:
    """The durable product of a research: its insights + open questions, from
    the graph. Empty lists are a valid result (no notes yet / no provider) —
    the surface renders the honest no-result state, not canned content."""
    view = distillation_for(investigation_id, db_path=_db())
    return DistillationOut(
        investigation_id=investigation_id,
        insights=[DistilledNodeOut(**vars(n)) for n in view.insights],
        questions=[DistilledNodeOut(**vars(n)) for n in view.questions],
    )


# ---------------------------------------------------------------------------
# M3 + M4 — challenge a note (living note) / escalate
# ---------------------------------------------------------------------------


@distill_router.post("/notes/{node_id}/challenge", response_model=ChallengeOut)
async def challenge(node_id: str, req: ChallengeRequest) -> ChallengeOut:
    """Challenge a note. Drives the shipped living-note path; the route does
    not re-implement the seq rule — it only supplies the next monotonic seq
    so a user challenge beats a stale background refinement."""
    seq = _next_seq(node_id)
    resolver = make_dispatch_resolver(req.investigation_id)
    try:
        result = challenge_note(
            node_id,
            req.challenge_text,
            resolver=resolver,
            seq=seq,
            investigation_id=req.investigation_id,
            idempotency_key=req.idempotency_key,
            origin_note_id=req.origin_note_id,
            unavailable_errors=(ChallengeUnavailable,),
        )
    except ChallengeUnavailable:
        # No model configured — honest no-key state, never a fabricated
        # refinement nor a misleading escalation.
        raise HTTPException(
            status_code=503,
            detail="no model is configured to weigh this challenge",
        ) from None
    except (ChallengeRequestConflict, ChallengeRequestInProgress) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from None
    except LivingNoteScopeConflict:
        raise HTTPException(status_code=404, detail="no such note") from None
    except ValueError as exc:
        # ``note.refined`` / ``question.escalated_to_research`` require the
        # note's source document on the envelope (schema invariant §9.1). A
        # note distilled without document grounding (e.g. a research-step note
        # promoted with no source_document_id) cannot be challenged yet —
        # surface that honestly rather than a 500. The fix is upstream
        # provenance, not bypassing the invariant.
        raise HTTPException(
            status_code=422,
            detail=f"this note can't be challenged yet — it has no source on record: {exc}",
        ) from None
    if not result.applied and not result.escalated and not result.superseded:
        # The node id did not resolve to a note in the graph.
        raise HTTPException(status_code=404, detail="no such note")
    return ChallengeOut(
        node_id=result.note_node_id,
        applied=result.applied,
        superseded=result.superseded,
        new_text=result.new_text,
        escalated=result.escalated,
        reserved_child_investigation_id=result.reserved_child_investigation_id,
    )


@distill_router.get("/notes/{node_id}/history", response_model=NoteHistoryOut)
async def note_history(node_id: str, investigation_id: str) -> NoteHistoryOut:
    try:
        history = living_note_history(investigation_id, node_id, db_path=_db())
    except LivingNoteHistoryNotFound:
        raise HTTPException(status_code=404, detail="no such note") from None
    except LivingNoteHistoryIntegrityError:
        raise HTTPException(
            status_code=409,
            detail="living-note history failed its integrity check",
        ) from None
    return NoteHistoryOut(
        investigation_id=history.investigation_id,
        node_id=history.node_id,
        current_text=history.current_text,
        current_sequence=history.current_sequence,
        refinement_count=history.refinement_count,
        authoritative_applied_count=history.authoritative_applied_count,
        superseded_count=history.superseded_count,
        complete=history.complete,
        entries=[NoteHistoryEntryOut(**vars(entry)) for entry in history.entries],
    )


def _next_seq(node_id: str) -> int:
    """The next monotonic seq for this node: one past the last applied seq it
    recorded (``metadata.last_update_seq``). Read-only — the write happens
    inside ``challenge_note`` under the single-writer lock. A note never
    challenged yet has no recorded seq, so the first challenge gets seq=1.

    This makes a user challenge strictly newer than any refinement already
    applied to the node, which is exactly the seq rule's "last-writer-by-seq
    wins" intent for an explicit user action."""
    con = connect_read(_db())
    try:
        row = con.execute(
            "SELECT metadata FROM nodes WHERE node_id = ?", [node_id]
        ).fetchone()
    finally:
        con.close()
    if row is None or not row[0]:
        return 1
    import json
    try:
        meta = json.loads(row[0])
    except (TypeError, ValueError):
        return 1
    return int(meta.get("last_update_seq", 0) or 0) + 1
