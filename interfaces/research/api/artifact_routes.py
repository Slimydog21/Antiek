"""ResearchArtifact export + outline blocks (ANT-AHT)."""

from __future__ import annotations

import os
import sys
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

_PKG_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
if _PKG_ROOT not in sys.path:
    sys.path.insert(0, _PKG_ROOT)

from substrate.graph import default_db_path, ensure_initialized  # noqa: E402
from substrate.research_artifact import (  # noqa: E402
    build_html_only,
    compose_artifacts,
    export_research_artifact,
    import_agent_notes,
    list_outline_blocks,
    render_twin_notes_html,
)
from substrate.research_artifact.paths import artifact_path_for  # noqa: E402

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
    twin_notes_path: str
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


@artifact_router.post("/{investigation_id}/artifact/export", response_model=ExportOut)
async def post_export_artifact(investigation_id: str) -> ExportOut:
    try:
        res = export_research_artifact(investigation_id, db_path=_db())
    except Exception as exc:  # pragma: no cover — surface as 500 with message
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return ExportOut(
        investigation_id=res.investigation_id,
        path=str(res.path),
        twin_notes_path=str(res.twin_notes_path),
        content_hash=res.content_hash,
        size_bytes=res.size_bytes,
        event_id=res.event_id,
    )


@artifact_router.get("/{investigation_id}/artifact/html", response_class=HTMLResponse)
async def get_artifact_html(investigation_id: str) -> HTMLResponse:
    try:
        body, html = build_html_only(investigation_id, db_path=_db())
    except Exception as exc:  # pragma: no cover — surface as 500 with message
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return HTMLResponse(
        html,
        headers={
            "x-antiek-investigation-id": investigation_id,
            "x-antiek-content-hash": body.content_hash(),
        },
    )


@artifact_router.get("/{investigation_id}/artifact/twin-notes.html", response_class=HTMLResponse)
async def get_artifact_twin_notes_html(investigation_id: str) -> HTMLResponse:
    try:
        body, _html = build_html_only(investigation_id, db_path=_db())
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
