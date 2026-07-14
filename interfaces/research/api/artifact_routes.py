"""ResearchArtifact export + outline blocks (ANT-AHT)."""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Response
from pydantic import BaseModel, Field

from runtime.db_lock import connect_read

_PKG_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
if _PKG_ROOT not in sys.path:
    sys.path.insert(0, _PKG_ROOT)

from substrate.event_log import ActionType, trajectory  # noqa: E402
from substrate.graph import default_db_path, ensure_initialized  # noqa: E402
from substrate.research_artifact import (  # noqa: E402
    ComposeResult,
    StaleComposePreview,
    create_compose_draft,
    delete_compose_draft,
    export_research_artifact,
    import_agent_notes,
    list_outline_blocks,
    load_compose_draft,
    preview_artifacts,
)
from substrate.research_artifact.paths import compose_member_path  # noqa: E402
from substrate.write.promote_compose import (  # noqa: E402
    ComposeIntegrityError,
    promote_compose_to_write,
)

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
    investigation_id: str
    path: str
    content_hash: str
    size_bytes: int
    event_id: str | None = None


class ImportNotesIn(BaseModel):
    path: str


class ImportNotesOut(BaseModel):
    investigation_id: str
    notes_imported: int
    notes_skipped_duplicate: int
    event_ids: list[str]


class ComposeIn(BaseModel):
    investigation_ids: list[str]
    selection_fingerprint: str | None = None


class ComposeMemberOut(BaseModel):
    investigation_id: str
    content_hash: str


class ComposeOut(BaseModel):
    compose_id: str
    selection_fingerprint: str
    members: list[ComposeMemberOut]
    identical_content: list[tuple[str, str]]
    view_url: str | None = None
    reused: bool = False


class ComposeWriteIn(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=300)
    deliverable_kind: Literal[
        "research_memo", "book_chapter", "biography_section",
        "investor_brief", "general_essay",
    ] = "research_memo"


class ComposeWriteOut(BaseModel):
    compose_id: str
    deliverable_id: str
    section_id: str
    write_url: str
    member_count: int
    snapshot_occurrence_count: int
    unique_block_count: int
    duplicate_count: int
    kind_conflict_count: int
    dangling_count: int
    reused: bool


def _compose_out(result: ComposeResult, *, include_url: bool = False) -> ComposeOut:
    assert result.compose_id and result.selection_fingerprint
    return ComposeOut(
        compose_id=result.compose_id,
        selection_fingerprint=result.selection_fingerprint,
        members=[ComposeMemberOut(investigation_id=m.investigation_id, content_hash=m.content_hash) for m in result.members],
        identical_content=result.hash_conflicts,
        view_url=f"/research/artifact-composes/{result.compose_id}/view" if include_url else None,
        reused=result.reused,
    )


def _require_completed(investigation_ids: list[str]) -> None:
    for investigation_id in investigation_ids:
        if (
            not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,199}", investigation_id)
            or ".." in investigation_id
        ):
            raise HTTPException(status_code=422, detail="invalid investigation id")
        rows = trajectory(investigation_id)
        terminal: tuple[str, dict[str, Any]] | None = None
        for row in rows:
            action = row.get("action_type")
            if action in {
                ActionType.INVESTIGATION_COMPLETED.value,
                ActionType.INVESTIGATION_FAILED.value,
                ActionType.INVESTIGATION_CHASE_HALTED.value,
            }:
                terminal = (action, row.get("payload") or {})
        completed = bool(
            terminal
            and terminal[0] == ActionType.INVESTIGATION_COMPLETED.value
            and terminal[1].get("outcome") not in {"stopped", "cancelled"}
        )
        if not completed:
            raise HTTPException(
                status_code=409,
                detail=f"{investigation_id} is not a completed research",
            )


@artifact_router.post("/artifact-composes/preview", response_model=ComposeOut)
async def post_compose_preview(body: ComposeIn) -> ComposeOut:
    _require_completed(body.investigation_ids)
    try:
        return _compose_out(preview_artifacts(body.investigation_ids, db_path=_db()))
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@artifact_router.post("/artifact-composes", response_model=ComposeOut)
async def post_compose(body: ComposeIn) -> ComposeOut:
    if not body.selection_fingerprint:
        raise HTTPException(status_code=422, detail="selection_fingerprint is required")
    _require_completed(body.investigation_ids)
    try:
        result = create_compose_draft(
            body.investigation_ids,
            expected_fingerprint=body.selection_fingerprint,
            db_path=_db(),
        )
        # The canonical body and terminal state live in separate stores. Check
        # again after snapshot publication; if the lifecycle changed during
        # creation, remove the draft before returning any successful receipt.
        try:
            _require_completed(body.investigation_ids)
        except HTTPException:
            delete_compose_draft(result.compose_id or "")
            raise
    except StaleComposePreview as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return _compose_out(result, include_url=True)


@artifact_router.get("/artifact-composes/{compose_id}", response_model=ComposeOut)
async def get_compose(compose_id: str) -> ComposeOut:
    try:
        return _compose_out(load_compose_draft(compose_id), include_url=True)
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=404, detail="compose draft not found") from exc


@artifact_router.post(
    "/artifact-composes/{compose_id}/write-workspace",
    response_model=ComposeWriteOut,
    status_code=201,
)
async def post_compose_write_workspace(
    compose_id: str, body: ComposeWriteIn, response: Response,
) -> ComposeWriteOut:
    try:
        result = promote_compose_to_write(
            compose_id,
            title=body.title,
            deliverable_kind=body.deliverable_kind,
            # The promoter validates every frozen member before it initializes
            # or opens DuckDB; do not call this module's eager `_db()` first.
            db_path=default_db_path(),
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="compose draft not found") from exc
    except ComposeIntegrityError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    response.status_code = 200 if result.reused else 201
    return ComposeWriteOut(**result.__dict__, write_url=f"/write/{result.deliverable_id}")


@artifact_router.get("/artifact-composes/{compose_id}/view")
async def get_compose_view(compose_id: str) -> Response:
    try:
        result = load_compose_draft(compose_id)
        content = result.path.read_text(encoding="utf-8")
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=404, detail="compose draft not found") from exc
    return Response(content, media_type="text/html", headers={
        "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'",
        "X-Content-Type-Options": "nosniff",
    })


@artifact_router.get("/artifact-composes/{compose_id}/member/{member_index}")
async def get_compose_member(compose_id: str, member_index: int) -> Response:
    try:
        result = load_compose_draft(compose_id)
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=404, detail="compose draft not found") from exc
    if member_index < 0 or member_index >= len(result.members):
        raise HTTPException(status_code=404, detail="compose member not found")
    try:
        content = compose_member_path(compose_id, member_index).read_text(encoding="utf-8")
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=404, detail="compose member not found") from exc
    return Response(content, media_type="text/html", headers={
        "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'",
        "X-Content-Type-Options": "nosniff",
    })


@artifact_router.delete("/artifact-composes/{compose_id}", status_code=204)
async def delete_compose(compose_id: str) -> Response:
    # A promoted compose is the immutable provenance anchor for its Write
    # workspace. Removing it would make source order unreconstructable.
    db_path = _db()

    def may_delete() -> bool:
        with connect_read(db_path) as con:
            return con.execute(
                "SELECT 1 FROM artifact_compose_write_workspaces "
                "WHERE compose_id = ? LIMIT 1",
                [compose_id],
            ).fetchone() is None

    try:
        delete_compose_draft(compose_id, before_delete=may_delete)
    except PermissionError as exc:
        raise HTTPException(
            status_code=409,
            detail="compose is the provenance source for a Write workspace",
        ) from exc
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=404, detail="compose draft not found") from exc
    return Response(status_code=204)


@artifact_router.post("/{investigation_id}/artifact/export", response_model=ExportOut)
async def post_export_artifact(investigation_id: str) -> ExportOut:
    try:
        res = export_research_artifact(investigation_id, db_path=_db())
    except Exception as exc:  # pragma: no cover — surface as 500 with message
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return ExportOut(
        investigation_id=res.investigation_id,
        path=str(res.path),
        content_hash=res.content_hash,
        size_bytes=res.size_bytes,
        event_id=res.event_id,
    )


@artifact_router.post(
    "/{investigation_id}/artifact/import-notes", response_model=ImportNotesOut
)
async def post_import_notes(
    investigation_id: str, body: ImportNotesIn
) -> ImportNotesOut:
    try:
        res = import_agent_notes(
            Path(body.path), investigation_id=investigation_id
        )
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return ImportNotesOut(
        investigation_id=res.investigation_id,
        notes_imported=res.notes_imported,
        notes_skipped_duplicate=res.notes_skipped_duplicate,
        event_ids=res.event_ids,
    )


@artifact_router.get("/{investigation_id}/artifact/blocks", response_model=BlocksOut)
async def get_artifact_blocks(investigation_id: str) -> BlocksOut:
    blocks = list_outline_blocks(investigation_id, db_path=_db())
    return BlocksOut(
        investigation_id=investigation_id,
        blocks=[BlockOut(**b.__dict__) for b in blocks],
    )
