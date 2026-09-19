"""ResearchArtifact export + outline blocks (ANT-AHT)."""

from __future__ import annotations

import os
import sys
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

_PKG_ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)
if _PKG_ROOT not in sys.path:
    sys.path.insert(0, _PKG_ROOT)

from services.html_projection.context import Provenance, RenderContext  # noqa: E402
from services.html_projection.gate import ScriptViolation, assert_script_free  # noqa: E402
from substrate.contracts.anti_ek_honesty import (  # noqa: E402
    html_projection_response_headers,
)
from services.html_projection.renderer import render  # noqa: E402
from substrate.graph import default_db_path, ensure_initialized  # noqa: E402
from substrate.research_artifact import (  # noqa: E402
    build_body,
    export_research_artifact,
    import_agent_notes,
    list_outline_blocks,
    research_projection_doc_model,
)
from substrate.research_artifact.store import ResearchArtifactStore  # noqa: E402

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


@artifact_router.post("/{investigation_id}/artifact/export", response_model=ExportOut)
async def post_export_artifact(investigation_id: str, request: Request) -> ExportOut:
    try:
        owner_user_id = str(getattr(request.state, "user_id", None) or "__operator__")
        res = export_research_artifact(investigation_id, db_path=_db(), owner_user_id=owner_user_id)
    except Exception as exc:  # pragma: no cover — surface as 500 with message
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return ExportOut(
        artifact_id=res.artifact_id,
        investigation_id=res.investigation_id,
        path=str(res.path),
        content_hash=res.content_hash,
        size_bytes=res.size_bytes,
        event_id=res.event_id,
    )


@artifact_router.get("/{investigation_id}/artifact", response_model=ArtifactStatusOut)
async def get_artifact_status(investigation_id: str, request: Request) -> ArtifactStatusOut:
    """Return the caller-owned durable identity and current style metadata."""
    owner_user_id = str(getattr(request.state, "user_id", None) or "__operator__")
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
        body = build_body(investigation_id, db_path=_db())
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
    return HTMLResponse(
        content=html,
        headers=html_projection_response_headers(
            filename=f"research-{investigation_id}.html",
            disposition="inline",
        ),
    )


@artifact_router.get("/{investigation_id}/artifact/blocks", response_model=BlocksOut)
async def get_artifact_blocks(investigation_id: str) -> BlocksOut:
    blocks = list_outline_blocks(investigation_id, db_path=_db())
    return BlocksOut(
        investigation_id=investigation_id,
        blocks=[BlockOut(**b.__dict__) for b in blocks],
    )
