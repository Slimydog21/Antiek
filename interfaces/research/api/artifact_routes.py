"""ResearchArtifact export + outline blocks (ANT-AHT)."""

from __future__ import annotations

import os
import stat
import sys
from pathlib import Path
from urllib.parse import quote

from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

_PKG_ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)
if _PKG_ROOT not in sys.path:
    sys.path.insert(0, _PKG_ROOT)

from substrate.graph import default_db_path, ensure_initialized  # noqa: E402
from substrate.research_artifact import (  # noqa: E402
    StaleArtifactError,
    append_note,
    export_research_artifact,
    import_agent_notes,
    list_outline_blocks,
)
from substrate.research_artifact.paths import artifact_path_for  # noqa: E402

artifact_router = APIRouter(prefix="/research", tags=["research-artifact"])

_MAX_ARTIFACT_VIEW_BYTES = 2 * 1024 * 1024
_ARTIFACT_VIEW_HEADERS = {
    "Cache-Control": "no-store",
    "X-Content-Type-Options": "nosniff",
    "Content-Security-Policy": (
        "sandbox allow-scripts; default-src 'none'; "
        "style-src 'unsafe-inline'; script-src 'unsafe-inline'; "
        "base-uri 'none'; form-action 'none'; connect-src 'none'; "
        "img-src data:; font-src data:"
    ),
}


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
    view_url: str


class ImportNotesIn(BaseModel):
    path: str


class ImportNotesOut(BaseModel):
    investigation_id: str
    notes_imported: int
    notes_skipped_duplicate: int
    event_ids: list[str]


class AppendNoteIn(BaseModel):
    note: str
    expected_content_hash: str


class AppendNoteOut(BaseModel):
    investigation_id: str
    notes_persisted: int
    notes_skipped_duplicate: int
    current_content_hash: str
    event_pending: bool


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
        view_url=(f"/research/{quote(investigation_id, safe='')}/artifact/view"),
    )


def _read_canonical_artifact(investigation_id: str) -> str:
    """Read the canonical artifact without following or accepting unsafe files."""
    path = artifact_path_for(investigation_id)
    try:
        before = path.lstat()
    except OSError as exc:
        raise HTTPException(status_code=404, detail="artifact unavailable") from exc

    if (
        not stat.S_ISREG(before.st_mode)
        or before.st_nlink != 1
        or before.st_size > _MAX_ARTIFACT_VIEW_BYTES
    ):
        raise HTTPException(status_code=404, detail="artifact unavailable")

    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(path, flags)
    except OSError as exc:
        raise HTTPException(status_code=404, detail="artifact unavailable") from exc

    try:
        opened = os.fstat(fd)
        if (
            not stat.S_ISREG(opened.st_mode)
            or opened.st_nlink != 1
            or opened.st_size > _MAX_ARTIFACT_VIEW_BYTES
            or (opened.st_dev, opened.st_ino) != (before.st_dev, before.st_ino)
        ):
            raise HTTPException(status_code=404, detail="artifact unavailable")
        with os.fdopen(fd, "rb", closefd=True) as artifact:
            fd = -1
            raw = artifact.read(_MAX_ARTIFACT_VIEW_BYTES + 1)
    finally:
        if fd >= 0:
            os.close(fd)

    if len(raw) > _MAX_ARTIFACT_VIEW_BYTES:
        raise HTTPException(status_code=404, detail="artifact unavailable")
    try:
        return raw.decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise HTTPException(status_code=404, detail="artifact unavailable") from exc


@artifact_router.get("/{investigation_id}/artifact/view", response_class=HTMLResponse)
async def get_artifact_view(investigation_id: str) -> HTMLResponse:
    return HTMLResponse(
        content=_read_canonical_artifact(investigation_id),
        headers=_ARTIFACT_VIEW_HEADERS,
    )


@artifact_router.post("/{investigation_id}/artifact/notes", response_model=AppendNoteOut)
async def post_artifact_note(investigation_id: str, body: AppendNoteIn) -> AppendNoteOut:
    try:
        result = append_note(
            investigation_id,
            body.note,
            body.expected_content_hash,
            events_dir=os.environ.get("ANTIEK_RESEARCH_EVENTS_DIR"),
        )
    except StaleArtifactError as exc:
        raise HTTPException(status_code=409, detail="artifact content hash is stale") from exc
    except (OSError, UnicodeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return AppendNoteOut(
        investigation_id=result.investigation_id,
        notes_persisted=result.notes_persisted,
        notes_skipped_duplicate=result.notes_skipped_duplicate,
        current_content_hash=result.current_content_hash,
        event_pending=result.event_pending,
    )


@artifact_router.post("/{investigation_id}/artifact/import-notes", response_model=ImportNotesOut)
async def post_import_notes(investigation_id: str, body: ImportNotesIn) -> ImportNotesOut:
    try:
        res = import_agent_notes(Path(body.path), investigation_id=investigation_id)
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
