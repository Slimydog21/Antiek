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
  • trace-to-source (SPR-07): the trace TARGET (the gated-source-no-leak
    gate). The reader that opens it is DRW SPR-10, still unbuilt;
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
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from roles.interviewer.drivers import DriverSet
from runtime.db_lock import connect_read, connect_write
from substrate.graph import default_db_path, ensure_initialized
from substrate.write import block_search
from substrate.write import folders as folders_mod
from substrate.write.brainstorm_blocks import drivers_to_blocks
from substrate.write.draft_generation import build_creative_writer_context, generate_section
from substrate.write.outline import OutlineError, OutlineNode, build_outline_tree
from substrate.write.outline_block import (
    OutlineBlock,
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


@contextmanager
def _write(purpose: str) -> Iterator[Any]:
    con = connect_write(_db(), purpose=purpose)
    try:
        folders_mod.ensure_folders_schema(con)
        yield con
    finally:
        con.close()


@contextmanager
def _read() -> Iterator[Any]:
    con = connect_read(_db())
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
    except (OutlineBlockError, OutlineError) as e:
        raise HTTPException(status_code=400, detail=str(e))


# ---------------------------------------------------------------------------
# Serialization
# ---------------------------------------------------------------------------


def _block_dict(b: OutlineBlock) -> dict:
    return {
        "outline_block_id": b.outline_block_id, "section_id": b.section_id,
        "block_kind": b.block_kind, "provenance_kind": b.provenance_kind,
        "node_id": b.node_id, "content": b.content, "block_index": b.block_index,
        "cluster_id": b.cluster_id, "is_user_originated": b.is_user_originated,
    }


def _node_dict(n: OutlineNode) -> dict:
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
def place_outline_block(req: PlaceBlockRequest) -> dict:
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


@write_router.post("/blocks/{outline_block_id}/move", status_code=202)
def move_outline_block(outline_block_id: str, req: MoveBlockRequest) -> dict:
    with _translate(), _write("write/move_block") as con:
        move_block(
            con, outline_block_id=outline_block_id,
            to_section_id=req.to_section_id, to_index=req.to_index,
        )
    return {"status": "moved"}


@write_router.delete("/blocks/{outline_block_id}", status_code=200)
def delete_outline_block(outline_block_id: str) -> dict:
    with _write("write/remove_block") as con:
        removed = remove_block(con, outline_block_id=outline_block_id)
    if not removed:
        raise HTTPException(status_code=404, detail="outline block not found")
    return {"status": "removed"}


@write_router.get("/sections/{section_id}/blocks")
def get_section_blocks(section_id: str) -> dict:
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
def get_outline(deliverable_id: str) -> dict:
    with _read() as con:
        roots = build_outline_tree(con, deliverable_id)
    return {"deliverable_id": deliverable_id, "roots": [_node_dict(n) for n in roots]}


@write_router.get("/blocks/{outline_block_id}/provenance")
def get_provenance(outline_block_id: str) -> dict:
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
def get_trace_target(outline_block_id: str) -> dict:
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


# ---------------------------------------------------------------------------
# Block repository + folders (SPR-03)
# ---------------------------------------------------------------------------


@write_router.post("/folders", status_code=201)
def create_folder(req: CreateFolderRequest) -> dict:
    with _write("write/create_folder") as con:
        fid = folders_mod.create_folder(con, name=req.name)
    return {"folder_id": fid}


@write_router.get("/folders")
def list_folders() -> dict:
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
def add_folder_block(folder_id: str, req: FolderMemberRequest) -> dict:
    with _write("write/add_folder_block") as con:
        created = folders_mod.add_block_to_folder(con, folder_id=folder_id, node_id=req.node_id)
    return {"status": "added" if created else "already_member"}


@write_router.delete("/folders/{folder_id}/blocks/{node_id}", status_code=200)
def remove_folder_block(folder_id: str, node_id: str) -> dict:
    with _write("write/remove_folder_block") as con:
        removed = folders_mod.remove_block_from_folder(con, folder_id=folder_id, node_id=node_id)
    return {"status": "removed" if removed else "not_member"}


@write_router.get("/blocks/search")
def search_repository(
    q: str = Query(default="", max_length=300),
    folder_id: str | None = Query(default=None),
    source_document_id: str | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
) -> dict:
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
def emit_brainstorm_blocks(req: BrainstormBlocksRequest) -> dict:
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
def promote_context(req: PromoteContextRequest) -> dict:
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
def generate_section_draft(section_id: str) -> dict:
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

        def _resolve_label(node_id: str) -> str:
            r = con.execute(
                "SELECT canonical_label FROM nodes WHERE node_id = ?", [node_id]
            ).fetchone()
            return r[0] if r else node_id

        ctx = build_creative_writer_context(
            deliverable_title=dtitle, deliverable_kind=dkind,
            section_title=stitle or "", section_index=0, section_count=1,
            blocks=blocks, node_label_resolver=_resolve_label,
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
    except KeyError:
        # creative_writer not wired into the dispatch config.
        raise HTTPException(
            status_code=503,
            detail="generation unavailable: creative_writer is not in the dispatch config",
        )
    except Exception as e:  # provider/credential failure
        raise HTTPException(status_code=503, detail=f"generation unavailable: {e}")

    report = result.citation_report
    # M3: persist prose_provenance so the X-ray can read paragraph→blocks back.
    # ONLY on a clean generation (gate passed, parser valid). A gate_failed /
    # invalid result never ships, so it never persists provenance either (no
    # half-written draft in the graph). The persist + the audit event go
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
        # paragraph_index → [block_ids], so the client can render the X-ray
        # immediately AND a reload reads the same persisted map back.
        "prose_provenance": (
            {str(i): v for i, v in result.prose_provenance.items()}
            if result.status == "generated" else {}
        ),
    }
