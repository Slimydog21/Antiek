"""ResearchArtifact export + outline blocks (ANT-AHT)."""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel, Field

_PKG_ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)
if _PKG_ROOT not in sys.path:
    sys.path.insert(0, _PKG_ROOT)

from runtime.db_lock import connect_write  # noqa: E402
from services.html_projection.context import Provenance, RenderContext  # noqa: E402
from services.html_projection.gate import ScriptViolation, assert_script_free  # noqa: E402
from services.html_projection.renderer import render  # noqa: E402
from substrate.contracts.anti_ek_honesty import (  # noqa: E402
    html_projection_response_headers,
)
from substrate.graph import default_db_path, ensure_initialized  # noqa: E402
from substrate.research_artifact import (  # noqa: E402
    SourceMergeRestoreReceipt,
    compose_artifacts,
    import_agent_notes,
    list_outline_blocks,
    render_twin_notes_html,
    research_projection_doc_model,
    restore_source_merge_review,
)
from substrate.research_artifact.build_body import build_body_for_reader  # noqa: E402
from substrate.research_artifact.export import export_research_artifact_for_owner  # noqa: E402
from substrate.research_artifact.paths import (  # noqa: E402
    artifact_path_for,
    read_importable_artifact,
)
from substrate.research_artifact.store import ResearchArtifactStore  # noqa: E402

from .books import _reader_owner_id  # noqa: E402

artifact_router = APIRouter(prefix="/research", tags=["research-artifact"])


def _db() -> str:
    path = default_db_path()
    ensure_initialized(path)
    return path


class BlockOut(BaseModel):
    node_id: str
    kind: str
    label: str
    investigation_id: str
    artifact_path: str | None = None


class BlocksOut(BaseModel):
    investigation_id: str
    blocks: list[BlockOut]


class ExportOut(BaseModel):
    artifact_id: str
    investigation_id: str
    path: str
    twin_notes_path: str
    content_hash: str
    size_bytes: int
    event_id: str | None = None


class ArtifactStatusOut(BaseModel):
    artifact_id: str
    investigation_id: str
    selected_style: str | None
    latest_version: int


class ImportNotesIn(BaseModel):
    path: str


class ImportNotesOut(BaseModel):
    investigation_id: str
    notes_imported: int
    notes_skipped_duplicate: int
    event_ids: list[str]


class ComposeIn(BaseModel):
    investigation_ids: list[str]
    write_draft_merge: bool = True


class ComposeMemberOut(BaseModel):
    investigation_id: str
    content_hash: str
    artifact_path: str
    twin_notes_path: str


class ComposeOut(BaseModel):
    path: str
    draft_merge_path: str | None = None
    members: list[ComposeMemberOut]
    hash_conflicts: list[list[str]]


class SourceMergeRestoreIn(BaseModel):
    document_id: str = Field(min_length=1)
    parent_reading_thread_id: str = Field(min_length=1)
    source_revision_id: str = Field(min_length=1)
    twin_revision_id: str = Field(min_length=1)
    expected_after_source_hash: str = Field(min_length=1)
    expected_before_source_hash: str = Field(min_length=1)
    acknowledge_restore: bool = False
    operator_reviewer: str | None = Field(default=None, max_length=160)


class SourceMergeRestoreOut(BaseModel):
    status: str
    document_id: str
    source_revision_id: str
    twin_revision_id: str
    event_id: str
    before_source_hash: str
    restored_source_hash: str
    writes_performed: bool


def _raise_source_merge_refusal(detail: str, *, status_code: int = 409) -> None:
    raise HTTPException(status_code=status_code, detail=detail)


_SOURCE_MERGE_RETIRED_DESCRIPTION = "Retired: under T6 a merge never writes the source document"


def _source_merge_retired() -> JSONResponse:
    """The whole answer of a retired source-merge route, given before anything
    is opened, locked, read or written."""
    return JSONResponse(
        status_code=410,
        content={"reason": "retired", "alternatives": ["adopt_reading_version", "merge_into_write"]},
    )


@artifact_router.post("/{investigation_id}/artifact/export", response_model=ExportOut)
async def post_export_artifact(investigation_id: str, request: Request) -> ExportOut:
    owner_user_id = _reader_owner_id(request)
    def _sync_export():
        return export_research_artifact_for_owner(
            investigation_id, db_path=_db(), owner_user_id=owner_user_id,
        )

    try:
        res = await asyncio.to_thread(_sync_export)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail="investigation export access withheld") from exc
    except Exception as exc:  # pragma: no cover — surface as 500 with message
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return ExportOut(
        artifact_id=res.artifact_id,
        investigation_id=res.investigation_id,
        path=str(res.path),
        twin_notes_path=str(res.twin_notes_path),
        content_hash=res.content_hash,
        size_bytes=res.size_bytes,
        event_id=res.event_id,
    )


@artifact_router.get("/{investigation_id}/artifact", response_model=ArtifactStatusOut)
async def get_artifact_status(investigation_id: str, request: Request) -> ArtifactStatusOut:
    """Return the caller-owned durable identity and current style metadata."""
    owner_user_id = _reader_owner_id(request)
    store = ResearchArtifactStore(_db())
    record = store.get_for_investigation(investigation_id, owner_user_id)
    # Compatibility for the shipped deterministic identity contract. The
    # investigation lookup remains authoritative for future non-equal IDs.
    if record is None:
        candidate = store.get(investigation_id)
        if candidate is not None and candidate.owner_user_id == owner_user_id:
            record = candidate
    if record is None:
        raise HTTPException(status_code=404, detail="research artifact not found")
    return ArtifactStatusOut(
        artifact_id=record.artifact_id,
        investigation_id=record.investigation_id,
        selected_style=record.selected_style,
        latest_version=record.latest_version,
    )


@artifact_router.post("/{investigation_id}/artifact/import-notes", response_model=ImportNotesOut)
async def post_import_notes(investigation_id: str, body: ImportNotesIn) -> ImportNotesOut:
    # The path comes from the client: read it only from the artifacts
    # directory, through one anchored descriptor, before parsing anything.
    try:
        html_text = read_importable_artifact(body.path)
    except ValueError:
        raise HTTPException(status_code=400, detail="import_notes_path_invalid") from None
    try:
        res = import_agent_notes(
            Path(body.path), investigation_id=investigation_id, html_text=html_text
        )
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return ImportNotesOut(
        investigation_id=res.investigation_id,
        notes_imported=res.notes_imported,
        notes_skipped_duplicate=res.notes_skipped_duplicate,
        event_ids=res.event_ids,
    )



@artifact_router.get("/{investigation_id}/artifact/twin-notes.html", response_class=HTMLResponse)
async def get_artifact_twin_notes_html(investigation_id: str, request: Request) -> HTMLResponse:
    try:
        body = build_body_for_reader(
            investigation_id, db_path=_db(), owner_user_id=_reader_owner_id(request)
        )
        notes_html = render_twin_notes_html(body, artifact_path=artifact_path_for(investigation_id))
    except Exception as exc:  # pragma: no cover — surface as 500 with message
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return HTMLResponse(
        notes_html,
        headers={
            "x-antiek-investigation-id": investigation_id,
            "x-antiek-content-hash": body.content_hash(),
        },
    )


@artifact_router.get("/artifacts/compose/draft-merge.html", response_class=HTMLResponse)
async def get_compose_draft_merge_html(
    investigation_ids: list[str] = Query(default_factory=list),
) -> HTMLResponse:
    ids = [item.strip() for item in investigation_ids if item.strip()]
    if len(ids) < 2:
        raise HTTPException(status_code=400, detail="at least two investigation_ids required")
    try:
        res = compose_artifacts(
            ids,
            db_path=_db(),
            write_draft_merge=True,
        )
        if not res.draft_merge_path:
            raise RuntimeError("draft merge path was not written")
        html = res.draft_merge_path.read_text(encoding="utf-8")
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return HTMLResponse(
        html,
        headers={
            "x-antiek-compose-count": str(len(ids)),
            "x-antiek-compose-members": ",".join(ids),
        },
    )


@artifact_router.post("/artifacts/compose", response_model=ComposeOut)
async def post_compose_artifacts(body: ComposeIn) -> ComposeOut:
    ids = [item.strip() for item in body.investigation_ids if item.strip()]
    if len(ids) < 2:
        raise HTTPException(status_code=400, detail="at least two investigation_ids required")
    try:
        res = compose_artifacts(
            ids,
            db_path=_db(),
            write_draft_merge=body.write_draft_merge,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return ComposeOut(
        path=str(res.path),
        draft_merge_path=str(res.draft_merge_path) if res.draft_merge_path else None,
        members=[
            ComposeMemberOut(
                investigation_id=m.investigation_id,
                content_hash=m.content_hash,
                artifact_path=str(m.artifact_path),
                twin_notes_path=str(m.twin_notes_path),
            )
            for m in res.members
        ],
        hash_conflicts=[[a, b] for a, b in res.hash_conflicts],
    )


# Source merge: preview, apply and commit are retired. Under the operator's
# binding ruling T6 a merge never writes the source document; it either adopts
# a reformulation as the project's reading version or merges into a Write draft
# (THREAD-CONTRACT §1.11 "Source merge (corrected in rev 8.8)"). The paths stay
# registered so an old client gets one stable answer. Their handlers take no
# body parameter, so FastAPI never reads or validates the reviewed packet, and
# they return before touching the database, a lock, a file, a receipt or the
# event log. Restore stays live below: it is the undo for any merge already
# committed on prod.


@artifact_router.post(
    "/artifacts/source-merge/preview",
    status_code=410,
    deprecated=True,
    response_description=_SOURCE_MERGE_RETIRED_DESCRIPTION,
)
async def post_source_merge_preview() -> JSONResponse:
    """Retired: always 410.

    Preview computed the body a commit would write into the source document,
    and to do it took the DuckDB write lock and read the draft file the client
    named. T6 rules that a merge never writes the source (THREAD-CONTRACT
    §1.11 "Source merge (corrected in rev 8.8)"), so there is no source write
    left to preview.
    """
    return _source_merge_retired()


@artifact_router.post(
    "/artifacts/source-merge/apply",
    status_code=410,
    deprecated=True,
    response_description=_SOURCE_MERGE_RETIRED_DESCRIPTION,
)
async def post_source_merge_apply() -> JSONResponse:
    """Retired: always 410.

    Apply wrote the receipt and audit event that commit consumed before it
    rewrote the source document's body. T6 rules that a merge never writes the
    source (THREAD-CONTRACT §1.11 "Source merge (corrected in rev 8.8)"), so a
    receipt authorising that write must not be recorded.
    """
    return _source_merge_retired()


@artifact_router.post(
    "/artifacts/source-merge/commit",
    status_code=410,
    deprecated=True,
    response_description=_SOURCE_MERGE_RETIRED_DESCRIPTION,
)
async def post_source_merge_commit() -> JSONResponse:
    """Retired: always 410.

    Commit rewrote a source document's body from a reviewed twin-note merge,
    the write T6 forbids: a merge adopts a reformulation as the reading version
    or merges into a Write draft, never into the source (THREAD-CONTRACT §1.11
    "Source merge (corrected in rev 8.8)"). The contract once said
    ``validate_commit_boundary`` refused this route, but that function has no
    production caller; this handler is the refusal.
    """
    return _source_merge_retired()


@artifact_router.post("/artifacts/source-merge/restore", response_model=SourceMergeRestoreOut)
async def post_source_merge_restore(body: SourceMergeRestoreIn) -> SourceMergeRestoreOut:
    """Restore source body from a prior source-merge commit snapshot."""

    if not body.acknowledge_restore:
        _raise_source_merge_refusal("source_merge_restore_acknowledgement_required")
    db_path = _db()
    def _restore_sync() -> SourceMergeRestoreReceipt:
        with connect_write(db_path, purpose="research_artifact/source_merge_restore") as con:
            return restore_source_merge_review(
                con,
                document_id=body.document_id,
                parent_reading_thread_id=body.parent_reading_thread_id,
                source_revision_id=body.source_revision_id,
                twin_revision_id=body.twin_revision_id,
                expected_after_source_hash=body.expected_after_source_hash,
                expected_before_source_hash=body.expected_before_source_hash,
                operator_reviewer=body.operator_reviewer,
            )

    try:
        receipt = await asyncio.to_thread(_restore_sync)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return SourceMergeRestoreOut(
        status=receipt.status,
        document_id=receipt.document_id,
        source_revision_id=receipt.source_revision_id,
        twin_revision_id=receipt.twin_revision_id,
        event_id=receipt.event_id or "",
        before_source_hash=receipt.before_source_hash,
        restored_source_hash=receipt.restored_source_hash,
        writes_performed=receipt.writes_performed,
    )


@artifact_router.get(
    "/{investigation_id}/artifact.html",
    response_class=HTMLResponse,
    summary="HTML-native research outcome view (script-free projection)",
)
async def get_artifact_html(investigation_id: str, request: Request) -> HTMLResponse:
    """Serve Profile B research findings as a script-free HTML projection.

    DuckDB/graph remains source of truth; this is a Lemon/HTML projection for
    daily reading (html-first thesis). Rights-aware synthesis excerpt follows
    ``build_body`` (§9.0). Distinct from POST ``/artifact/export`` which writes
    the editable agent-channel HTML (may include note-taking script) to disk.
    """
    try:
        body = build_body_for_reader(
            investigation_id, db_path=_db(), owner_user_id=_reader_owner_id(request)
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    doc_model = research_projection_doc_model(body)
    ctx = RenderContext(
        provenance=Provenance(
            document_id=investigation_id,
            title=body.problem_question or investigation_id,
            content_class="research_artifact",
            schema_version="1",
        )
    )
    html = render(doc_model, ctx)
    try:
        assert_script_free(html)
    except ScriptViolation as err:
        raise HTTPException(
            status_code=500,
            detail="artifact failed the zero-script gate; refused",
        ) from err
    headers = html_projection_response_headers(
        filename=f"research-{investigation_id}.html",
        disposition="inline",
    )
    # Provenance headers (branch feature): the rendered artifact always names
    # the investigation it was projected from and pins its content hash.
    headers["x-antiek-investigation-id"] = investigation_id
    headers["x-antiek-content-hash"] = body.content_hash()
    return HTMLResponse(content=html, headers=headers)


@artifact_router.get("/{investigation_id}/artifact/blocks", response_model=BlocksOut)
async def get_artifact_blocks(investigation_id: str) -> BlocksOut:
    blocks = list_outline_blocks(investigation_id, db_path=_db())
    return BlocksOut(
        investigation_id=investigation_id,
        blocks=[BlockOut(**b.__dict__) for b in blocks],
    )
