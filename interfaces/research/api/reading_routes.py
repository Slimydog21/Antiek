"""DRW SPR-10 transport — the reading-surface REST API.

Wires the reading surface's backend: a document's editable ``raw_text`` +
versions (SPR-08), the insight/question notes anchored to it (SPR-03, via
``document_notes``), living-note challenge (SPR-03 ``note.refined`` / escalate),
and the structural gaps relevant to the document (SPR-07, scoped). Same
standalone-``APIRouter`` + one-line ``include_router`` discipline as
``cascade_routes`` / ``speak_routes``.

Spin-research-from-a-span needs NO endpoint here — the surface seeds a plan
through the existing ``/research/plans`` (SPR-06 transport) with the span/note
text as the problem, so the cascade lifecycle is reused, not forked.

Reading a document's ``raw_text`` is the operator reading their OWN ingested
material (``ip_holder_id == __operator__``, ``content_class == user_owned``);
the Read servability gate governs PUBLIC serving, a different surface, and is
untouched here.
"""

from __future__ import annotations

import time
from contextlib import contextmanager
from typing import Any, Iterator, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from runtime.db_lock import connect_read, connect_write
from substrate.graph import default_db_path, ensure_initialized
from substrate.graph.document_notes import document_chunk_node_ids, notes_for_document
from substrate.research_bridge.versioning import create_document_version, document_versions
from roles.note_taker.living_note import challenge_note

reading_router = APIRouter(prefix="/reading", tags=["deep-research", "reading"])


# ---------------------------------------------------------------------------
# Plumbing
# ---------------------------------------------------------------------------


def _db() -> str:
    path = default_db_path()
    ensure_initialized(path)
    return path


@contextmanager
def _read() -> Iterator[Any]:
    con = connect_read(_db())
    try:
        yield con
    finally:
        con.close()


@contextmanager
def _write(purpose: str) -> Iterator[Any]:
    con = connect_write(_db(), purpose=purpose)
    try:
        yield con
    finally:
        con.close()


def _embedding_provider():
    from processing.embedding import default_embedding_provider
    return default_embedding_provider()


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class CreateVersionRequest(BaseModel):
    new_text: str = Field(..., min_length=1)
    edited_by: str = "__operator__"


class ChallengeRequest(BaseModel):
    challenge_text: str = Field(..., min_length=1)
    document_id: str
    # When provided, the note is refined to this text (operator/UI-resolved).
    # When omitted, an unresolvable challenge escalates to a spin-research
    # seam (a reserved, un-launched child investigation id).
    resolution: Optional[str] = None


# ---------------------------------------------------------------------------
# Document + versions (SPR-08)
# ---------------------------------------------------------------------------


@reading_router.get("/documents/{document_id}")
async def get_document(document_id: str) -> dict:
    with _read() as con:
        row = con.execute(
            "SELECT document_id, title, raw_text, document_type, content_class "
            "FROM documents WHERE document_id = ?", [document_id],
        ).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail=f"no document {document_id!r}")
        versions = document_versions(con, document_id)
    return {
        "document_id": row[0], "title": row[1], "raw_text": row[2],
        "document_type": row[3], "content_class": row[4],
        "versions": [{"document_id": v.document_id, "version": v.version,
                      "parent_document_id": v.parent_document_id} for v in versions],
    }


@reading_router.post("/documents/{document_id}/versions")
async def create_version(document_id: str, req: CreateVersionRequest) -> dict:
    """Persist an edit as a new version; the original is preserved (SPR-08)."""
    with _write("reading_create_version") as con:
        try:
            new_id = create_document_version(
                con, original_document_id=document_id, new_text=req.new_text,
                edited_by=req.edited_by,
            )
        except ValueError as e:
            raise HTTPException(status_code=404, detail=str(e))
    return {"document_id": document_id, "new_document_id": new_id,
            "unchanged": new_id == document_id}


# ---------------------------------------------------------------------------
# Notes anchored to the document (SPR-03) — content-anchored, edit-robust
# ---------------------------------------------------------------------------


@reading_router.get("/documents/{document_id}/notes")
async def get_document_notes(document_id: str) -> dict:
    with _read() as con:
        notes = notes_for_document(con, document_id)
    return {"document_id": document_id, "notes": [n.to_dict() for n in notes]}


# ---------------------------------------------------------------------------
# Living-note challenge (SPR-03) — refine in place, or escalate to spin
# ---------------------------------------------------------------------------


@reading_router.post("/notes/{node_id}/challenge")
async def challenge(node_id: str, req: ChallengeRequest) -> dict:
    """Challenge a note. With a resolution → refine the note in place
    (note.refined; last-writer-by-event-seq). Without → escalate to a
    reserved (un-launched) child investigation the surface can spin a
    research into."""
    seq = int(time.time() * 1_000_000)  # monotonic-enough for last-writer-by-seq
    resolution = req.resolution

    def _resolver(_current: str, _challenge: str) -> Optional[str]:
        return resolution  # operator/UI-provided; None → escalate

    with _write("reading_challenge_note") as con:
        result = challenge_note(
            node_id, req.challenge_text, resolver=_resolver, seq=seq,
            investigation_id="__operator__", document_id=req.document_id,
            embedding_provider=_embedding_provider(), con=con,
        )
    return {
        "node_id": result.note_node_id,
        "applied": result.applied,
        "new_text": result.new_text,
        "escalated": result.escalated,
        "escalated_question_id": result.escalated_question_id,
        "reserved_child_investigation_id": result.reserved_child_investigation_id,
    }


# ---------------------------------------------------------------------------
# Document-scoped structural gaps (SPR-07)
# ---------------------------------------------------------------------------


@reading_router.get("/documents/{document_id}/gaps")
async def get_document_gaps(document_id: str) -> dict:
    """Structural gaps (SPR-07) whose backing nodes are anchored to this
    document — graph-grounded only (no LLM free-association, per SPR-07's
    guarantee). Clicking a gap spins a research via /research/plans."""
    from substrate.gap_detection import detect_gaps
    with _read() as con:
        doc_nodes = document_chunk_node_ids(con, document_id)
        candidates = detect_gaps(con)
    gaps = [
        {"gap_id": c.gap_id, "kind": c.kind, "question": c.question,
         "impact_score": c.impact_score, "backing_node_ids": list(c.backing_node_ids)}
        for c in candidates
        if doc_nodes & set(c.backing_node_ids)
    ]
    return {"document_id": document_id, "gaps": gaps}
