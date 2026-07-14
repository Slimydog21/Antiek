"""Write workflow — the REST surface (specs/write/).

A standalone ``APIRouter`` wiring the ``substrate/write`` + ``substrate/edit``
substrate into the FastAPI app, mirroring ``speak_routes.py``. Kept in its
own module (not inlined into the 5k-line ``app.py`` factory) per CLAUDE.md:
``app.py`` is a hot, concurrently-edited file. This router is included with
ONE line — ``app.include_router(write_router)`` — and is fully testable on
its own.

It exposes the substrate the Write spec's milestones reference as
"interfaces/research/api/ (… endpoint)":

  • outline composition (SPR-01): place / move / remove blocks, the outline
    tree, provenance resolution;
  • block repository (SPR-03): folders (views over nodes), block search;
  • brainstorm → blocks (SPR-05): drivers → user-originated OutlineBlocks;
  • draft generation (SPR-06): generate a section from its blocks (the
    no-blocks→gap + citation + gate contract; the live model call needs
    creative_writer in the dispatch config);
  • trace-to-source (SPR-07): gated target resolution plus the durable
    Write→Read command/event used by the shared HTML reader;
  • pre-outline context window (SPR-08): promote a loose context to a
    structured outline.

Conventions matched from ``app.py`` / ``speak_routes.py``:
  • db path via ``substrate.graph.default_db_path`` + ``ensure_initialized``;
  • writes through ``runtime.db_lock.connect_write`` (single-writer);
  • reads through a read-only DuckDB connection;
  • auth is the app's global middleware — these handlers carry none.

Provenance is the moat, enforced end to end: every place-block call goes
through ``substrate.write.outline_block.place_block`` (graph_node ⟺ node_id;
no fabricated citations), so no REST path can mint orphan prose.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from typing import Any, Literal

import duckdb
from fastapi import APIRouter, Header, HTTPException, Query
from pydantic import BaseModel, Field

from roles.creative_writer.prompt import AdjacentSection
from roles.interviewer.drivers import DriverSet
from runtime.db_lock import connect_write
from substrate.event_log import (
    append_event_once,
    prepare_typed_event,
    require_event_persistence,
    trajectory,
)
from substrate.graph import default_db_path, ensure_initialized
from substrate.graph.insight_question import insight_node_id
from substrate.graph.ops import content_addressed_id
from substrate.schemas.events import (
    SeamReadToWritePayload,
    SeamWriteToReadPayload,
    SeamWriteToSpeakPayload,
)
from substrate.speak import project as speak_project_mod
from substrate.write import block_search
from substrate.write import folders as folders_mod
from substrate.write.brainstorm_blocks import drivers_to_blocks
from substrate.write.draft_generation import build_creative_writer_context, generate_section
from substrate.write.outline import OutlineError, OutlineNode, build_outline_tree
from substrate.write.outline_block import (
    OutlineBlock,
    OutlineBlockCommandConflict,
    OutlineBlockError,
    get_block,
    list_section_blocks,
    move_block,
    place_block,
    remove_block,
)
from substrate.write.promote_context import ContextBlockSpec, promote_to_outline
from substrate.write.provenance import resolve_provenance
from substrate.write.trace import resolve_trace_target

write_router = APIRouter(prefix="/write", tags=["write"])


# ---------------------------------------------------------------------------
# Plumbing
# ---------------------------------------------------------------------------


def _db() -> str:
    path = default_db_path()
    ensure_initialized(path)
    return path


def _validated_idempotency_key(value: str) -> str:
    if not value.strip() or len(value) > 512 or "\n" in value or "\r" in value:
        raise HTTPException(
            status_code=422,
            detail="Idempotency-Key must be a bounded canonical string",
        )
    return value


@contextmanager
def _write(purpose: str) -> Iterator[Any]:
    con = connect_write(_db(), purpose=purpose)
    try:
        folders_mod.ensure_folders_schema(con)
        yield con
    finally:
        con.close()


@contextmanager
def _transaction(con: Any) -> Iterator[None]:
    con.execute("BEGIN TRANSACTION")
    try:
        yield
    except BaseException:
        con.execute("ROLLBACK")
        raise
    else:
        con.execute("COMMIT")


@contextmanager
def _read() -> Iterator[duckdb.DuckDBPyConnection]:
    con = duckdb.connect(_db(), read_only=True)
    try:
        yield con
    finally:
        con.close()


@contextmanager
def _translate() -> Iterator[None]:
    """Map Write domain exceptions onto HTTP status. Composition-invariant
    violations (no-orphan-prose, incoherent kind pairs, cycles) are
    bad-input → 400; missing entities → 404 (raised explicitly)."""
    try:
        yield
    except OutlineBlockCommandConflict as e:
        raise HTTPException(status_code=409, detail=str(e)) from e
    except (OutlineBlockError, OutlineError) as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


# ---------------------------------------------------------------------------
# Serialization
# ---------------------------------------------------------------------------


def _block_dict(b: OutlineBlock) -> dict[str, Any]:
    return {
        "outline_block_id": b.outline_block_id, "section_id": b.section_id,
        "block_kind": b.block_kind, "provenance_kind": b.provenance_kind,
        "node_id": b.node_id, "content": b.content, "block_index": b.block_index,
        "cluster_id": b.cluster_id, "is_user_originated": b.is_user_originated,
    }


def _node_dict(n: OutlineNode) -> dict[str, Any]:
    return {
        "section_id": n.section_id, "title": n.title, "depth": n.depth,
        "section_index": n.section_index,
        "blocks": [_block_dict(b) for b in n.blocks],
        "children": [_node_dict(c) for c in n.children],
    }


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class PlaceBlockRequest(BaseModel):
    section_id: str
    block_kind: Literal[
        "insight", "open_question", "operator_note", "claim",
        "user_authored", "synthesized",
    ]
    provenance_kind: Literal["graph_node", "user_authored", "synthesized", "brainstorm"]
    block_index: int = Field(..., ge=0)
    node_id: str | None = None
    content: str | None = None
    deliverable_id: str | None = None


class MoveBlockRequest(BaseModel):
    to_section_id: str
    to_index: int = Field(..., ge=0)


class CreateFolderRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)


class FolderMemberRequest(BaseModel):
    node_id: str = Field(..., min_length=1)


class ReadToWriteRequest(BaseModel):
    note_id: str = Field(..., min_length=1, max_length=200)
    target_section_id: str = Field(..., min_length=1)
    investigation_id: str = Field(..., min_length=1)


class WriteToReadRequest(BaseModel):
    deliverable_id: str = Field(..., min_length=1)


class WriteToSpeakRequest(BaseModel):
    deliverable_id: str = Field(..., min_length=1)


class BrainstormBlocksRequest(BaseModel):
    section_id: str
    deliverable_id: str | None = None
    insights: list[str] = Field(default_factory=list)
    questions: list[str] = Field(default_factory=list)
    data_points: list[str] = Field(default_factory=list)


class PromoteContextRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=300)
    deliverable_kind: Literal[
        "research_memo", "book_chapter", "biography_section",
        "investor_brief", "general_essay",
    ] = "general_essay"
    objective: str = ""
    blocks: list[PlaceBlockRequest] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Outline composition (SPR-01)
# ---------------------------------------------------------------------------


@write_router.post("/blocks", status_code=201)
def place_outline_block(req: PlaceBlockRequest) -> dict[str, Any]:
    with _translate(), _write("write/place_block") as con:
        if con.execute(
            "SELECT 1 FROM deliverable_sections WHERE section_id = ?", [req.section_id]
        ).fetchone() is None:
            raise HTTPException(status_code=404, detail="section not found")
        obid = place_block(
            con, section_id=req.section_id, block_kind=req.block_kind,
            provenance_kind=req.provenance_kind, block_index=req.block_index,
            node_id=req.node_id, content=req.content, deliverable_id=req.deliverable_id,
        )
    return {"outline_block_id": obid}


@write_router.post("/read-handoffs", status_code=201)
def handoff_read_note(req: ReadToWriteRequest) -> dict[str, Any]:
    """Place the graph insight already promoted from marginalia into Write.

    The note text never crosses this boundary. The marginalia event resolves
    the existing user-authored insight, and the outline block references that
    same node. Stable block and event IDs make a retry converge on one handoff.
    """
    # Refuse before touching the outline when its terminating audit record
    # cannot be persisted. A retry can repair a rare post-commit append fault,
    # but an explicitly disabled event store must never create a silent seam.
    require_event_persistence()
    block_id = content_addressed_id(
        "oblk", f"read-to-write|{req.note_id}|{req.target_section_id}"
    )
    seam_event_id = content_addressed_id(
        "evt", f"read-to-write|{req.note_id}|{req.target_section_id}"
    )
    with _translate(), _write("write/read_handoff") as con:
        section = con.execute(
            "SELECT deliverable_id FROM deliverable_sections WHERE section_id = ?",
            [req.target_section_id],
        ).fetchone()
        if section is None:
            raise HTTPException(status_code=404, detail="target section not found")
        note_events = [
            event
            for event in trajectory(req.investigation_id)
            if event.get("action_type") == "marginalia.noted"
            and event.get("payload", {}).get("note_id") == req.note_id
            and event.get("payload", {}).get("source_kind") == "user"
        ]
        if len(note_events) != 1:
            raise HTTPException(
                status_code=404,
                detail="saved reader note is not uniquely authoritative",
            )
        node_id = insight_node_id(note_events[0]["payload"]["note_text"])
        promoted = con.execute(
            "SELECT 1 FROM nodes WHERE node_id = ? AND node_type = 'insight' "
            "AND json_extract_string(metadata, '$.source_kind') = 'user'",
            [node_id],
        ).fetchone()
        if promoted is None:
            raise HTTPException(
                status_code=404,
                detail="saved reader note has no promoted user insight",
            )
        receipt = con.execute(
            "SELECT json_extract_string(metadata, '$.seam_emitted_at') "
            "FROM outline_blocks WHERE outline_block_id = ?",
            [block_id],
        ).fetchone()
        seam_emitted_at = (
            receipt[0] if receipt is not None else datetime.now(UTC).isoformat()
        )
        next_index = con.execute(
            "SELECT COALESCE(MAX(block_index), -1) + 1 FROM outline_blocks "
            "WHERE section_id = ?",
            [req.target_section_id],
        ).fetchone()[0]
        outline_block_id = place_block(
            con,
            section_id=req.target_section_id,
            block_kind="insight",
            provenance_kind="graph_node",
            block_index=int(next_index),
            node_id=node_id,
            deliverable_id=section[0],
            investigation_id=req.investigation_id,
            outline_block_id=block_id,
            on_conflict="ignore",
            metadata={
                "seam_event_id": seam_event_id,
                "seam_emitted_at": seam_emitted_at,
            },
        )

    seam_event = prepare_typed_event(
        req.investigation_id,
        SeamReadToWritePayload(
            entity_id=node_id,
            provenance_ref=req.note_id,
            target_section_id=req.target_section_id,
        ),
        event_id=seam_event_id,
        role="write_composition",
        # The block atomically carries this receipt. A retry after an event-file
        # fault repairs the append with the exact original envelope.
        emitted_at=seam_emitted_at,
    )
    append_event_once(seam_event)
    return {
        "outline_block_id": outline_block_id,
        "node_id": node_id,
        "deliverable_id": section[0],
        "section_id": req.target_section_id,
        "seam_event_id": seam_event.event_id,
    }


@write_router.post("/blocks/{outline_block_id}/move", status_code=202)
def move_outline_block(
    outline_block_id: str,
    req: MoveBlockRequest,
    idempotency_key: str = Header(alias="Idempotency-Key"),
) -> dict[str, Any]:
    command_id = _validated_idempotency_key(idempotency_key)
    with _translate(), _write("write/move_block") as con:
        move_block(
            con, outline_block_id=outline_block_id,
            to_section_id=req.to_section_id, to_index=req.to_index,
            command_id=command_id,
        )
    return {"status": "moved"}


@write_router.delete("/blocks/{outline_block_id}", status_code=200)
def delete_outline_block(
    outline_block_id: str,
    idempotency_key: str = Header(alias="Idempotency-Key"),
) -> dict[str, Any]:
    command_id = _validated_idempotency_key(idempotency_key)
    with _translate(), _write("write/remove_block") as con:
        removed = remove_block(
            con,
            outline_block_id=outline_block_id,
            command_id=command_id,
        )
    if not removed:
        raise HTTPException(status_code=404, detail="outline block not found")
    return {"status": "removed"}


@write_router.get("/sections/{section_id}/blocks")
def get_section_blocks(section_id: str) -> dict[str, Any]:
    with _read() as con:
        blocks = list_section_blocks(con, section_id)
        # The routed outline renders block TEXT, never an id (SPR-07 M2:
        # "no UUID ever visible"). A graph-node block carries no `content`
        # (its text lives on the node), so resolve the node's canonical
        # label here and surface it as `node_label`. Read-only — no new
        # writer, single-writer untouched.
        node_ids = {b.node_id for b in blocks if b.node_id}
        labels: dict[str, str] = {}
        if node_ids:
            rows = con.execute(
                "SELECT node_id, canonical_label FROM nodes WHERE node_id = ANY(?)",
                [list(node_ids)],
            ).fetchall()
            labels = {nid: lbl for nid, lbl in rows}
    return {
        "count": len(blocks),
        "blocks": [
            {**_block_dict(b), "node_label": labels.get(b.node_id) if b.node_id else None}
            for b in blocks
        ],
    }


@write_router.get("/deliverables/{deliverable_id}/outline")
def get_outline(deliverable_id: str) -> dict[str, Any]:
    with _read() as con:
        roots = build_outline_tree(con, deliverable_id)
    return {"deliverable_id": deliverable_id, "roots": [_node_dict(n) for n in roots]}


@write_router.get("/blocks/{outline_block_id}/provenance")
def get_provenance(outline_block_id: str) -> dict[str, Any]:
    with _read() as con:
        if get_block(con, outline_block_id) is None:
            raise HTTPException(status_code=404, detail="outline block not found")
        chain = resolve_provenance(con, outline_block_id)
    return {
        "status": chain.status, "provenance_kind": chain.provenance_kind,
        "node_id": chain.node_id, "node_label": chain.node_label,
        "document_id": chain.document_id, "document_title": chain.document_title,
        "chunk_ids": chain.chunk_ids, "detail": chain.detail,
    }


# ---------------------------------------------------------------------------
# Trace-to-source (SPR-07) — the gated-source-no-leak gate
# ---------------------------------------------------------------------------


@write_router.get("/blocks/{outline_block_id}/trace")
def get_trace_target(outline_block_id: str) -> dict[str, Any]:
    with _read() as con:
        if get_block(con, outline_block_id) is None:
            raise HTTPException(status_code=404, detail="outline block not found")
        target = resolve_trace_target(con, outline_block_id)
    return {
        "kind": target.kind,
        "full_text_allowed": target.full_text_allowed,  # the no-leak bit
        "document_id": target.document_id, "document_title": target.document_title,
        "chunk_ids": target.chunk_ids, "servability_status": target.servability_status,
        "detail": target.detail,
    }


_WRITE_TO_READ_COMMANDS_SQL = """
CREATE TABLE IF NOT EXISTS write_to_read_handoff_commands (
    command_id TEXT PRIMARY KEY,
    fingerprint TEXT NOT NULL,
    seam_event_id TEXT NOT NULL,
    seam_emitted_at TEXT NOT NULL,
    outline_block_id TEXT NOT NULL,
    deliverable_id TEXT NOT NULL,
    source_document_id TEXT NOT NULL,
    source_region_id TEXT NOT NULL
)
"""


@write_router.post("/blocks/{outline_block_id}/read-handoffs", status_code=201)
def handoff_write_block_to_read(
    outline_block_id: str,
    req: WriteToReadRequest,
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
) -> dict[str, Any]:
    """Commit an explicit trace from a Write block into its readable source."""
    require_event_persistence()
    command_id = _validated_idempotency_key(idempotency_key)
    fingerprint = content_addressed_id(
        "cmd", f"write-to-read|{outline_block_id}|{req.deliverable_id}"
    )
    current_target = None
    with _translate(), _write("write/read_handoff") as con:
        con.execute(_WRITE_TO_READ_COMMANDS_SQL)
        receipt = con.execute(
            "SELECT fingerprint, seam_event_id, seam_emitted_at, "
            "source_document_id, source_region_id "
            "FROM write_to_read_handoff_commands WHERE command_id = ?",
            [command_id],
        ).fetchone()
        if receipt is not None and receipt[0] != fingerprint:
            raise HTTPException(
                status_code=409,
                detail="Idempotency-Key was already used for a different handoff",
            )
        owner = con.execute(
            "SELECT 1 FROM outline_blocks b "
            "JOIN deliverable_sections s ON s.section_id = b.section_id "
            "WHERE b.outline_block_id = ? AND s.deliverable_id = ?",
            [outline_block_id, req.deliverable_id],
        ).fetchone()
        if owner is None and receipt is None:
            raise HTTPException(status_code=404, detail="outline block not found in piece")
        if receipt is None:
            current_target = resolve_trace_target(con, outline_block_id)
            primary_chunk = (
                current_target.chunk_ids[0] if current_target.chunk_ids else None
            )
            if (
                not current_target.full_text_allowed
                or not current_target.document_id
                or not primary_chunk
            ):
                raise HTTPException(
                    status_code=409,
                    detail=current_target.detail or "source is not openable in Read",
                )
            seam_event_id = content_addressed_id("evt", f"write-to-read|{command_id}")
            seam_emitted_at = datetime.now(UTC).isoformat()
            con.execute(
                "INSERT INTO write_to_read_handoff_commands VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                [
                    command_id,
                    fingerprint,
                    seam_event_id,
                    seam_emitted_at,
                    outline_block_id,
                    req.deliverable_id,
                    current_target.document_id,
                    primary_chunk,
                ],
            )
            source_document_id = current_target.document_id
            source_region_id = primary_chunk
        else:
            seam_event_id, seam_emitted_at = receipt[1], receipt[2]
            source_document_id, source_region_id = receipt[3], receipt[4]
            if owner is not None:
                current_target = resolve_trace_target(con, outline_block_id)

    seam_event = prepare_typed_event(
        req.deliverable_id,
        SeamWriteToReadPayload(
            entity_id=outline_block_id,
            provenance_ref=outline_block_id,
            source_document_id=source_document_id,
            source_region_id=source_region_id,
        ),
        event_id=seam_event_id,
        role="write_composition",
        emitted_at=seam_emitted_at,
        document_id=source_document_id,
    )
    append_event_once(seam_event)
    if (
        current_target is None
        or not current_target.full_text_allowed
        or current_target.document_id != source_document_id
        or not current_target.chunk_ids
        or current_target.chunk_ids[0] != source_region_id
    ):
        raise HTTPException(
            status_code=409,
            detail="source authority changed after this handoff was accepted",
        )
    return {
        "kind": current_target.kind,
        "full_text_allowed": current_target.full_text_allowed,
        "document_id": current_target.document_id,
        "document_title": current_target.document_title,
        "chunk_ids": current_target.chunk_ids,
        "servability_status": current_target.servability_status,
        "detail": current_target.detail,
        "seam_event_id": seam_event.event_id,
    }


_WRITE_TO_SPEAK_COMMANDS_SQL = """
CREATE TABLE IF NOT EXISTS write_to_speak_handoff_commands (
    command_id TEXT PRIMARY KEY,
    fingerprint TEXT NOT NULL,
    seam_event_id TEXT NOT NULL,
    seam_emitted_at TEXT NOT NULL,
    outline_block_id TEXT NOT NULL,
    question_node_id TEXT NOT NULL,
    section_id TEXT NOT NULL,
    deliverable_id TEXT NOT NULL,
    speak_project_id TEXT NOT NULL
)
"""


@write_router.post("/blocks/{outline_block_id}/speak-handoffs", status_code=201)
def handoff_write_question_to_speak(
    outline_block_id: str,
    req: WriteToSpeakRequest,
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
) -> dict[str, Any]:
    """Commission a private Speak interview project from one outline question."""
    require_event_persistence()
    command_id = _validated_idempotency_key(idempotency_key)
    fingerprint = content_addressed_id(
        "cmd", f"write-to-speak|{outline_block_id}|{req.deliverable_id}"
    )
    with _translate(), _write("write/speak_handoff") as con:  # noqa: SIM117
        with _transaction(con):
            con.execute(_WRITE_TO_SPEAK_COMMANDS_SQL)
            receipt = con.execute(
                "SELECT fingerprint, seam_event_id, seam_emitted_at, "
                "question_node_id, section_id, speak_project_id "
                "FROM write_to_speak_handoff_commands WHERE command_id = ?",
                [command_id],
            ).fetchone()
            if receipt is not None and receipt[0] != fingerprint:
                raise HTTPException(
                    status_code=409,
                    detail="Idempotency-Key was already used for a different interview commission",
                )
            if receipt is None:
                receipt = con.execute(
                    "SELECT fingerprint, seam_event_id, seam_emitted_at, "
                    "question_node_id, section_id, speak_project_id "
                    "FROM write_to_speak_handoff_commands WHERE fingerprint = ? "
                    "ORDER BY command_id LIMIT 1",
                    [fingerprint],
                ).fetchone()
                if receipt is not None:
                    con.execute(
                        "INSERT INTO write_to_speak_handoff_commands "
                        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                        [
                            command_id,
                            fingerprint,
                            receipt[1],
                            receipt[2],
                            outline_block_id,
                            receipt[3],
                            receipt[4],
                            req.deliverable_id,
                            receipt[5],
                        ],
                    )
            if receipt is None:
                block_row = con.execute(
                    "SELECT b.node_id, b.section_id, d.title "
                    "FROM outline_blocks b "
                    "JOIN deliverable_sections s ON s.section_id = b.section_id "
                    "JOIN deliverables d ON d.deliverable_id = s.deliverable_id "
                    "JOIN nodes n ON n.node_id = b.node_id "
                    "WHERE b.outline_block_id = ? AND d.deliverable_id = ? "
                    "AND b.block_kind = 'open_question' "
                    "AND b.provenance_kind = 'graph_node' "
                    "AND n.node_type = 'question'",
                    [outline_block_id, req.deliverable_id],
                ).fetchone()
                if block_row is None:
                    raise HTTPException(
                        status_code=409,
                        detail="only a node-backed open question in this piece can commission interviews",
                    )
                question_node_id, section_id, deliverable_title = block_row
                speak_project_id = content_addressed_id(
                    "ivp", f"write-to-speak|{fingerprint}"
                )
                speak_project_mod.create_project(
                    con,
                    project_id=speak_project_id,
                    title=f"Interview research for {deliverable_title}",
                    publish_intent="private_never_published",
                    interview_guide={
                        "must_cover": [
                            {
                                "id": question_node_id,
                                "question_node_id": question_node_id,
                            }
                        ]
                    },
                    emit_event=False,
                )
                seam_event_id = content_addressed_id(
                    "evt", f"write-to-speak|{fingerprint}"
                )
                seam_emitted_at = datetime.now(UTC).isoformat()
                con.execute(
                    "INSERT INTO write_to_speak_handoff_commands "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    [
                        command_id,
                        fingerprint,
                        seam_event_id,
                        seam_emitted_at,
                        outline_block_id,
                        question_node_id,
                        section_id,
                        req.deliverable_id,
                        speak_project_id,
                    ],
                )
            else:
                seam_event_id, seam_emitted_at = receipt[1], receipt[2]
                question_node_id, section_id, speak_project_id = receipt[3:6]

    seam_event = prepare_typed_event(
        req.deliverable_id,
        SeamWriteToSpeakPayload(
            entity_id=question_node_id,
            provenance_ref=outline_block_id,
            outline_section_id=section_id,
        ),
        event_id=seam_event_id,
        emitted_at=seam_emitted_at,
        role="write_composition",
    )
    append_event_once(seam_event)
    return {
        "question_node_id": question_node_id,
        "section_id": section_id,
        "speak_project_id": speak_project_id,
        "speak_path": f"/speak/{speak_project_id}",
        "seam_event_id": seam_event.event_id,
    }


# ---------------------------------------------------------------------------
# Block repository + folders (SPR-03)
# ---------------------------------------------------------------------------


@write_router.post("/folders", status_code=201)
def create_folder(req: CreateFolderRequest) -> dict[str, Any]:
    with _write("write/create_folder") as con:
        fid = folders_mod.create_folder(con, name=req.name)
    return {"folder_id": fid}


@write_router.get("/folders")
def list_folders() -> dict[str, Any]:
    with _read() as con:
        items = folders_mod.list_folders(con)
    return {
        "count": len(items),
        "folders": [
            {"folder_id": f.folder_id, "name": f.name, "member_count": f.member_count}
            for f in items
        ],
    }


@write_router.post("/folders/{folder_id}/blocks", status_code=202)
def add_folder_block(folder_id: str, req: FolderMemberRequest) -> dict[str, Any]:
    with _write("write/add_folder_block") as con:
        created = folders_mod.add_block_to_folder(con, folder_id=folder_id, node_id=req.node_id)
    return {"status": "added" if created else "already_member"}


@write_router.delete("/folders/{folder_id}/blocks/{node_id}", status_code=200)
def remove_folder_block(folder_id: str, node_id: str) -> dict[str, Any]:
    with _write("write/remove_folder_block") as con:
        removed = folders_mod.remove_block_from_folder(con, folder_id=folder_id, node_id=node_id)
    return {"status": "removed" if removed else "not_member"}


@write_router.get("/blocks/search")
def search_repository(
    q: str = Query(default="", max_length=300),
    folder_id: str | None = Query(default=None),
    source_document_id: str | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
) -> dict[str, Any]:
    with _read() as con:
        hits = block_search.search_blocks(
            con, query=q, folder_id=folder_id,
            source_document_id=source_document_id, limit=limit,
        )
    return {
        "count": len(hits),
        "hits": [
            {
                "node_id": h.node_id, "label": h.label, "node_type": h.node_type,
                "source_tier": h.source_tier, "document_id": h.document_id,
                "document_title": h.document_title, "score": h.score,
            }
            for h in hits
        ],
    }


# ---------------------------------------------------------------------------
# Brainstorm → blocks (SPR-05)
# ---------------------------------------------------------------------------


@write_router.post("/brainstorm/emit-blocks", status_code=201)
def emit_brainstorm_blocks(req: BrainstormBlocksRequest) -> dict[str, Any]:
    drivers = DriverSet(
        insights=req.insights, questions=req.questions, data_points=req.data_points,
    )
    with _translate(), _write("write/brainstorm_blocks") as con:
        if con.execute(
            "SELECT 1 FROM deliverable_sections WHERE section_id = ?", [req.section_id]
        ).fetchone() is None:
            raise HTTPException(status_code=404, detail="section not found")
        result = drivers_to_blocks(
            con, section_id=req.section_id, drivers=drivers,
            deliverable_id=req.deliverable_id,
        )
    return {
        "block_ids": result.block_ids,
        "insight_count": result.insight_count,
        "question_count": result.question_count,
        "data_count": result.data_count,
        "skipped_duplicates": result.skipped_duplicates,
        "flagged_unverified": result.flagged_unverified,
    }


# ---------------------------------------------------------------------------
# Pre-outline context window → outline (SPR-08)
# ---------------------------------------------------------------------------


@write_router.post("/context/promote", status_code=201)
def promote_context(req: PromoteContextRequest) -> dict[str, Any]:
    specs = [
        ContextBlockSpec(
            block_kind=b.block_kind, provenance_kind=b.provenance_kind,
            node_id=b.node_id, content=b.content,
        )
        for b in req.blocks
    ]
    with _translate(), _write("write/promote_context") as con:
        result = promote_to_outline(
            con, title=req.title, deliverable_kind=req.deliverable_kind,
            specs=specs, objective=req.objective,
        )
    return {
        "deliverable_id": result.deliverable_id,
        "section_id": result.section_id,
        "block_ids": result.block_ids,
    }


# ---------------------------------------------------------------------------
# Draft generation (SPR-06)
# ---------------------------------------------------------------------------


@write_router.post("/sections/{section_id}/generate", status_code=200)
def generate_section_draft(section_id: str) -> dict[str, Any]:
    """Generate a section's prose from its attached OutlineBlocks.

    The no-blocks→gap path needs no model. The live generation path routes
    through ``substrate/dispatch`` (creative_writer) and so requires the
    role in the dispatch config + provider credentials; absent those it
    surfaces a clear 503 rather than fabricating prose."""
    with _read() as con:
        row = con.execute(
            "SELECT d.deliverable_id, d.title, d.deliverable_kind, s.title "
            "FROM deliverable_sections s JOIN deliverables d "
            "ON s.deliverable_id = d.deliverable_id WHERE s.section_id = ?",
            [section_id],
        ).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="section not found")
        deliverable_id, dtitle, dkind, stitle = row
        blocks = list_section_blocks(con, section_id)

        # Multi-section coherence (§10.6): give the role the deliverable's
        # other sections in outline order so it can keep a multi-section
        # deliverable coherent — prior sections carry their prose (so the
        # model does not repeat them), upcoming sections carry only a title
        # (so it can hand off). section_index/section_count come from the
        # real outline position, not a single-section placeholder.
        # Order by (section_index, section_id) — the SAME total order the
        # canonical outline reader uses (substrate/write/outline.py), because
        # section_index is sibling-scoped and carries no UNIQUE constraint, so
        # ordering by it alone is nondeterministic once nesting introduces
        # duplicate indices. The section_id tiebreaker makes this path agree
        # with every other reader of the outline.
        section_rows = con.execute(
            "SELECT section_id, title, prose_text "
            "FROM deliverable_sections WHERE deliverable_id = ? "
            "ORDER BY section_index, section_id",
            [deliverable_id],
        ).fetchall()
        section_count = len(section_rows)
        this_index = next(
            (i for i, r in enumerate(section_rows) if r[0] == section_id), 0
        )
        adjacent_sections = [
            AdjacentSection(
                section_index=i,
                title=r[1] or "",
                prose_text=(r[2] if i < this_index else None),
            )
            for i, r in enumerate(section_rows)
            if r[0] != section_id
        ]

        def _resolve_label(node_id: str) -> str:
            r = con.execute(
                "SELECT canonical_label FROM nodes WHERE node_id = ?", [node_id]
            ).fetchone()
            return r[0] if r else node_id

        ctx = build_creative_writer_context(
            deliverable_title=dtitle, deliverable_kind=dkind,
            section_title=stitle or "", section_index=this_index,
            section_count=section_count, blocks=blocks,
            adjacent_sections=adjacent_sections,
            node_label_resolver=_resolve_label,
        )

    if not ctx.blocks:
        # Honest gap — never fabricated prose.
        return {"status": "gap", "section_id": section_id,
                "detail": "no blocks attached — left as a gap, not fabricated"}

    try:
        from substrate.write.draft_generation import default_dispatch_fn, persist_section_draft
        result = generate_section(
            ctx=ctx, dispatch_fn=default_dispatch_fn(investigation_id=deliverable_id),
            section_id=section_id,
        )
    except KeyError as e:
        # creative_writer not wired into the dispatch config.
        raise HTTPException(
            status_code=503,
            detail="generation unavailable: creative_writer is not in the dispatch config",
        ) from e
    except Exception as e:  # provider/credential failure
        raise HTTPException(status_code=503, detail=f"generation unavailable: {e}") from e

    report = result.citation_report
    # M3: persist prose_provenance so the X-ray can read paragraph→blocks back.
    # ONLY on a clean generation (citation + voice gates passed, parser valid).
    # A rejected result never persists provenance (no half-written draft in the
    # graph). The persist + the audit event go
    # through the single-writer funnel together (db_lock + emit_typed),
    # mirroring patch_section_prose. See docs/decisions/spr-09-*.md (D-2).
    if result.status == "generated" and report is not None:
        with _translate(), _write("write/persist_draft") as con:
            persist_section_draft(
                con,
                section_id=section_id,
                deliverable_id=deliverable_id,
                result=result,
                report=report,
                investigation_id=deliverable_id,
            )
    return {
        "status": result.status, "section_id": section_id,
        "prose_text": result.prose_text, "detail": result.detail,
        "gate_passed": result.gate.passed if result.gate else None,
        "gate_score": result.gate.score if result.gate else None,
        "all_claims_cited": report.all_claims_cited if report else None,
        "unsupported_paragraphs": report.unsupported_paragraphs if report else [],
        "fabricated_citations": report.fabricated_citations if report else [],
        "provenance_mismatches": report.provenance_mismatches if report else [],
        # paragraph_index → [block_ids], so the client can render the X-ray
        # immediately AND a reload reads the same persisted map back.
        "prose_provenance": (
            {str(i): v for i, v in result.prose_provenance.items()}
            if result.status == "generated" else {}
        ),
    }


# ---------------------------------------------------------------------------
# Investigation → deliverable (WV-SPR-01) — the writing flywheel arm
# ---------------------------------------------------------------------------
# Appended at end-of-file deliberately: the declared-bar baseline keys
# existing write_routes.py violations by exact line number, so any mid-file
# insertion would orphan those keys and flag them NEW. An append-only edit
# shifts nothing above → the committed baseline stays exact → ADDED = NONE
# without depending on the (CI-only) mypy recapture. Same reason the import
# above stays a single line.


class FromInvestigationRequest(BaseModel):
    """Promote a completed investigation's synthesis into a seed deliverable
    (specs/write WV-SPR-01). The writing arm of the compounding flywheel."""

    investigation_id: str = Field(..., min_length=1)
    deliverable_kind: Literal[
        "research_memo", "book_chapter", "biography_section",
        "investor_brief", "general_essay",
    ] = "research_memo"
    title: str | None = Field(default=None, max_length=300)


class FromInvestigationResponse(BaseModel):
    deliverable_id: str
    section_id: str
    block_count: int
    dangling_count: int
    source_node_count: int
    insufficient_evidence: bool = Field(default=False, deprecated=True)
    synthesis_id: str | None = None
    synthesis_status: str | None = None
    synthesis_recommendation: str | None = None


class PromotionNotFoundDetail(BaseModel):
    error: Literal["no_synthesis"]
    reason: str
    investigation_id: str


class PromotionNotFoundResponse(BaseModel):
    detail: PromotionNotFoundDetail


class PromotionRefusalDetail(BaseModel):
    error: Literal["not_promotable"]
    reason: str
    gate_failed: Literal["status", "recommendation", "no_source_nodes", "all_dangling"]
    investigation_id: str
    synthesis_id: str
    synthesis_status: str
    synthesis_recommendation: str
    source_node_count: int
    live_source_node_count: int
    dangling_count: int


class PromotionRefusalResponse(BaseModel):
    detail: PromotionRefusalDetail


@write_router.post(
    "/deliverables/from-investigation",
    status_code=201,
    response_model=FromInvestigationResponse,
    responses={
        404: {
            "description": "No completed synthesis exists",
            "model": PromotionNotFoundResponse,
        },
        409: {
            "description": "Synthesis failed the writing-promotion evidence gate",
            "model": PromotionRefusalResponse,
        },
    },
)
def promote_investigation(req: FromInvestigationRequest) -> FromInvestigationResponse:
    """Seed a deliverable from a completed investigation's synthesis: one
    graph-node block per synthesis-pinned source node, each carrying
    provenance back to its graph node. The compounding flywheel's missing
    writing arm (specs/write WV-SPR-01).

    Honest status (never an empty 200 that reads as success):
    - no depositable synthesis for the investigation → 404 ``no_synthesis``;
    - an evidence-ineligible synthesis → 409 ``not_promotable``, with no rows
      created;
    - otherwise a deliverable is created → 201. ``dangling_count`` counts
      blocks whose source node was since deleted (seeded, not dropped)."""
    # Local import (mirrors generate_section_draft at the draft_generation
    # import): keeps the top-level promote_context import unchanged so the
    # declared-bar line-keyed baseline for this file does not shift.
    from substrate.write.promote_context import (
        InvestigationPromotionRefusal,
        promote_investigation_to_deliverable,
    )

    with _translate(), _write("write/promote_investigation") as con:
        result = promote_investigation_to_deliverable(
            con,
            req.investigation_id,
            deliverable_kind=req.deliverable_kind,
            title=req.title,
        )
    if result is None:
        raise HTTPException(
            status_code=404,
            detail={
                "error": "no_synthesis",
                "reason": (
                    f"investigation {req.investigation_id!r} has no depositable "
                    "(completed, non-draft) synthesis to promote"
                ),
                "investigation_id": req.investigation_id,
            },
        )
    if isinstance(result, InvestigationPromotionRefusal):
        reasons = {
            "status": (
                f"synthesis constraint-loop status {result.synthesis_status!r} "
                "did not converge"
            ),
            "recommendation": (
                f"synthesis recommendation {result.synthesis_recommendation!r} "
                "does not support promotion"
            ),
            "no_source_nodes": "synthesis pinned no source nodes",
            "all_dangling": "every synthesis-pinned source node is unavailable",
        }
        raise HTTPException(
            status_code=409,
            detail={
                "error": "not_promotable",
                "reason": reasons[result.gate_failed],
                "gate_failed": result.gate_failed,
                "investigation_id": req.investigation_id,
                "synthesis_id": result.synthesis_id,
                "synthesis_status": result.synthesis_status,
                "synthesis_recommendation": result.synthesis_recommendation,
                "source_node_count": result.source_node_count,
                "live_source_node_count": result.live_source_node_count,
                "dangling_count": result.dangling_count,
            },
        )
    return FromInvestigationResponse(
        deliverable_id=result.deliverable_id,
        section_id=result.section_id,
        block_count=result.block_count,
        dangling_count=result.dangling_count,
        source_node_count=result.source_node_count,
        synthesis_id=result.synthesis_id,
        synthesis_status=result.synthesis_status,
        synthesis_recommendation=result.synthesis_recommendation,
    )


# ---------------------------------------------------------------------------
# Cmd+K selection edit (CK-5) — the Cursor writing-flow affordance
# ---------------------------------------------------------------------------
# Appended at end-of-file for the same declared-bar reason as the investigation
# block above: the baseline keys this file's mypy violations by exact line
# number, so a mid-file insertion would orphan those keys and flag them NEW.
# An append shifts nothing above -> the committed baseline stays exact.


class EditSelectionRequest(BaseModel):
    """A highlighted span of deliverable prose + the writer's edit instruction.

    The span is deliverable prose (the model's own already-generated,
    citation-bearing output), not restricted source, so a stylistic edit
    introduces no source-redistribution concern and no new factual claims;
    the section's prose_provenance (paragraph -> blocks) stays valid."""

    deliverable_id: str
    section_id: str
    selection_text: str = Field(..., min_length=1, max_length=8000)
    instruction: str = Field(..., min_length=1, max_length=1000)


@write_router.post("/edit-selection", status_code=200)
def edit_selection(req: EditSelectionRequest) -> dict[str, Any]:
    """Rewrite a highlighted span of deliverable prose per a natural-language
    instruction — the Cursor Cmd+K writing-flow affordance.

    The selection is deliverable prose (the model's §9.0-cleared output, not
    restricted source), so a stylistic edit (stronger / more concise / rephrase)
    adds no source-redistribution concern and no new claims: the section's
    prose_provenance (paragraph -> OutlineBlocks) stays valid. Returns ONLY the
    edited span; the client replaces the selection in place and funnels the
    result through the existing patch_section_prose path, so provenance and the
    single-writer discipline are unchanged. This endpoint never persists on its
    own.

    Dispatches role=creative_writer (pro tier, GLM-5.2). Absent config or
    credentials it surfaces a clear 503 rather than fabricating prose. Cost is
    bounded by a selection-derived max_tokens cap."""
    # Cost bound: the edited span is at most ~2x the selection. tokens ~= chars/4,
    # so give 2x headroom over the selection with a 128-token floor, capped at 2048.
    max_tokens = min(2048, max(128, (len(req.selection_text) // 4) * 2 + 128))
    prompt = (
        "You are editing ONE highlighted span inside a longer document. Apply "
        "the writer's instruction to the span exactly. Return ONLY the edited "
        "span text with no preamble, no surrounding quotes, no explanation, and "
        "nothing beyond the span. This is a stylistic edit: do NOT add new "
        "factual claims, citations, or content that was not in the original "
        "span.\n\n"
        f"Instruction: {req.instruction}\n\n"
        f"Span to edit:\n{req.selection_text}"
    )
    try:
        from substrate.dispatch import dispatch

        result = dispatch(
            prompt=prompt,
            role="creative_writer",
            investigation_id=req.deliverable_id,
            max_tokens=max_tokens,
        )
    except KeyError as exc:
        # creative_writer not wired into the dispatch config.
        raise HTTPException(
            status_code=503,
            detail="edit unavailable: creative_writer is not in the dispatch config",
        ) from exc
    except Exception as exc:  # provider/credential failure
        raise HTTPException(status_code=503, detail=f"edit unavailable: {exc}") from exc
    return {
        "edited_text": result.text,
        "deliverable_id": req.deliverable_id,
        "section_id": req.section_id,
    }
