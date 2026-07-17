"""ResearchArtifact export + outline blocks (ANT-AHT)."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

_PKG_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
if _PKG_ROOT not in sys.path:
    sys.path.insert(0, _PKG_ROOT)

from substrate.graph import default_db_path, ensure_initialized  # noqa: E402
from substrate.research_artifact import (  # noqa: E402
    compose_artifacts,
    export_research_artifact,
    import_agent_notes,
    list_outline_blocks,
)
from substrate.research_artifact.context import problem_question_from_events  # noqa: E402
from substrate.event_log import trajectory  # noqa: E402
from substrate.schemas import ActionType  # noqa: E402

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


class ComposeArtifactsIn(BaseModel):
    investigation_ids: list[str]


class ComposeBlockOut(BaseModel):
    node_id: str
    kind: str
    label: str
    investigation_id: str


class ComposeMemberOut(BaseModel):
    investigation_id: str
    question: str
    content_hash: str
    blocks: list[ComposeBlockOut]


class ComposeConflictOut(BaseModel):
    first_investigation_id: str
    second_investigation_id: str
    content_hash: str


class ComposeArtifactsOut(BaseModel):
    kind: Literal["artifact_index"] = "artifact_index"
    members: list[ComposeMemberOut]
    conflicts: list[ComposeConflictOut]


def _require_completed(investigation_id: str) -> None:
    """Reject unless the trajectory's current terminal verdict is completed."""
    completed = ActionType.INVESTIGATION_COMPLETED.value
    failed = ActionType.INVESTIGATION_FAILED.value
    halted = ActionType.INVESTIGATION_CHASE_HALTED.value
    started = ActionType.INVESTIGATION_START_REQUESTED.value
    terminal = next(
        (
            row
            for row in reversed(trajectory(investigation_id))
            if row.get("action_type") in (started, completed, failed, halted)
        ),
        None,
    )
    payload = terminal.get("payload") if terminal else None
    outcome = payload.get("outcome") if isinstance(payload, dict) else None
    if (
        terminal is None
        or terminal.get("action_type") != completed
        or outcome in ("stopped", "cancelled")
    ):
        raise HTTPException(
            status_code=409,
            detail=f"investigation is not terminal-completed: {investigation_id}",
        )


@artifact_router.post("/artifacts/compose", response_model=ComposeArtifactsOut)
async def post_compose_artifacts(body: ComposeArtifactsIn) -> ComposeArtifactsOut:
    ids = body.investigation_ids
    if not 2 <= len(ids) <= 8:
        raise HTTPException(status_code=422, detail="select between 2 and 8 investigations")
    if any(not iid or iid != iid.strip() for iid in ids):
        raise HTTPException(status_code=422, detail="investigation IDs must be non-empty and trimmed")
    if len(set(ids)) != len(ids):
        raise HTTPException(status_code=422, detail="investigation IDs must be unique")

    # Validate the whole basket before compose_artifacts performs any export.
    for investigation_id in ids:
        _require_completed(investigation_id)

    db_path = _db()
    composed = compose_artifacts(ids, db_path=db_path)
    members: list[ComposeMemberOut] = []
    hashes = {member.investigation_id: member.content_hash for member in composed.members}
    for member in composed.members:
        blocks = list_outline_blocks(member.investigation_id, db_path=db_path)
        members.append(
            ComposeMemberOut(
                investigation_id=member.investigation_id,
                question=(
                    problem_question_from_events(member.investigation_id)
                    or f"Investigation {member.investigation_id}"
                ),
                content_hash=member.content_hash,
                blocks=[
                    ComposeBlockOut(
                        node_id=block.node_id,
                        kind=block.kind,
                        label=block.label,
                        investigation_id=block.investigation_id,
                    )
                    for block in blocks
                ],
            )
        )
    return ComposeArtifactsOut(
        members=members,
        conflicts=[
            ComposeConflictOut(
                first_investigation_id=first,
                second_investigation_id=second,
                content_hash=hashes[first],
            )
            for first, second in composed.hash_conflicts
        ],
    )


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
