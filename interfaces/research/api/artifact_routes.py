"""ResearchArtifact export + outline blocks (ANT-AHT)."""

from __future__ import annotations

import hashlib
import json
import os
import sys
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict, Field

_PKG_ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)
if _PKG_ROOT not in sys.path:
    sys.path.insert(0, _PKG_ROOT)

from substrate.event_log import trajectory  # noqa: E402
from substrate.graph import default_db_path, ensure_initialized  # noqa: E402
from substrate.research_artifact import (  # noqa: E402
    compose_artifacts,
    export_research_artifact,
    import_agent_notes,
    list_outline_blocks,
    validate_investigation_ids,
)
from substrate.research_artifact import (  # noqa: E402
    read_composition_store_file as _read_store_file,
)
from substrate.research_artifact import (  # noqa: E402
    verify_composition_index as _verified_index,
)
from substrate.research_artifact.compose import ComposeResult  # noqa: E402
from substrate.research_artifact.composition_repository import (  # noqa: E402
    ResearchCompositionConflict,
    ResearchCompositionPrecondition,
    ResearchCompositionRepository,
    ResearchCompositionUnavailable,
    composition_etag,
)
from substrate.research_artifact.paths import (  # noqa: E402
    composition_member_path_for,
    composition_path_for,
)

artifact_router = APIRouter(prefix="/research", tags=["research-artifact"])


def _html_response(content: bytes) -> Response:
    return Response(
        content,
        media_type="text/html",
        headers={"Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff"},
    )


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
    model_config = ConfigDict(extra="forbid")
    investigation_ids: list[str] = Field(min_length=2, max_length=20)


def _trajectory_belongs_to_owner(rows: list[dict[str, object]], owner: str) -> bool:
    for row in rows:
        if row.get("action_type") != "investigation.start_requested":
            continue
        payload = row.get("payload")
        if not isinstance(payload, dict):
            return False
        recorded = payload.get("owner_user_id")
        return recorded == owner or (recorded is None and owner == "__operator__")
    return owner == "__operator__"


class ComposeMemberOut(BaseModel):
    investigation_id: str
    content_hash: str


class ComposeOut(BaseModel):
    composition_id: str
    url: str
    ordered_set_digest: str
    members: list[ComposeMemberOut]
    hash_conflicts: list[tuple[str, str]]


@artifact_router.post("/artifacts/compose", response_model=ComposeOut)
async def post_compose_artifacts(body: ComposeIn, request: Request, response: Response) -> ComposeOut:
    owner = getattr(request.state, "user_id", None)
    if not owner:
        raise HTTPException(status_code=401, detail="authentication required")
    try:
        validate_investigation_ids(body.investigation_ids)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    for iid in body.investigation_ids:
        rows = trajectory(iid)
        if not rows:
            raise HTTPException(status_code=404, detail=f"investigation {iid!r} was not found")
        if not _trajectory_belongs_to_owner(rows, owner):
            raise HTTPException(status_code=404, detail=f"investigation {iid!r} was not found")
        terminal_rows = [
            row
            for row in rows
            if row.get("action_type")
            in {
                "investigation.completed",
                "investigation.failed",
                "investigation.chase_halted",
            }
        ]
        terminal_actions = [str(row.get("action_type", "")) for row in terminal_rows]
        completion_outcome = (
            (terminal_rows[-1].get("payload") or {}).get("outcome") if terminal_rows else None
        )
        if (
            not terminal_actions
            or terminal_actions[-1] != "investigation.completed"
            or completion_outcome in {"stopped", "cancelled"}
        ):
            raise HTTPException(status_code=409, detail=f"investigation {iid!r} is not completed")
    try:
        db_path = _db()
        result = compose_artifacts(body.investigation_ids, db_path=db_path)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if isinstance(result, ComposeResult):
        try:
            authority = ResearchCompositionRepository(db_path=db_path).bind_created(
                owner_user_id=owner, result=result
            )
        except ResearchCompositionConflict as exc:
            raise HTTPException(status_code=409, detail="composition integrity conflict") from exc
        except (FileNotFoundError, OSError, KeyError, ValueError, json.JSONDecodeError) as exc:
            raise HTTPException(status_code=409, detail="composition integrity conflict") from exc
        response.headers["ETag"] = str(authority["etag"])
    else:  # Legacy test doubles still exercise the stable response contract.
        response.headers["ETag"] = composition_etag(
            result.composition_id, result.ordered_set_digest
        )
    return ComposeOut(
        composition_id=result.composition_id,
        url=f"/research/artifacts/compositions/{result.composition_id}",
        ordered_set_digest=result.ordered_set_digest,
        members=[
            ComposeMemberOut(investigation_id=m.investigation_id, content_hash=m.content_hash)
            for m in result.members
        ],
        hash_conflicts=result.hash_conflicts,
    )


@artifact_router.get("/artifacts/compositions/{composition_id}")
async def get_composed_artifact(composition_id: str, request: Request) -> Response:
    owner = getattr(request.state, "user_id", None)
    if not owner:
        raise HTTPException(status_code=401, detail="authentication required")
    try:
        path = composition_path_for(composition_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="composition not found") from exc
    try:
        authority = ResearchCompositionRepository(db_path=_db()).read(
            owner_user_id=owner, composition_id=composition_id
        )
        content = _read_store_file(path.name)
        _verified_index(content, composition_id)
    except (
        FileNotFoundError,
        NotADirectoryError,
        OSError,
        KeyError,
        ValueError,
        IndexError,
        json.JSONDecodeError, ResearchCompositionUnavailable,
    ):
        raise HTTPException(status_code=404, detail="composition not found") from None
    except ResearchCompositionConflict as exc:
        raise HTTPException(status_code=409, detail="composition integrity conflict") from exc
    response = _html_response(content)
    response.headers["ETag"] = str(authority["etag"])
    return response


@artifact_router.get("/artifacts/compositions/{composition_id}/{investigation_id}")
async def get_composed_member(
    composition_id: str, investigation_id: str, request: Request
) -> Response:
    owner = getattr(request.state, "user_id", None)
    if not owner:
        raise HTTPException(status_code=401, detail="authentication required")
    try:
        path = composition_member_path_for(composition_id, investigation_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="artifact not found") from exc
    try:
        authority = ResearchCompositionRepository(db_path=_db()).read(
            owner_user_id=owner, composition_id=composition_id
        )
        expected = next(
            member.rendered_sha256 for member in authority["composition"].members
            if member.investigation_id == investigation_id
        )
        content = _read_store_file(composition_id, path.name)
        if hashlib.sha256(content).hexdigest() != expected:
            raise FileNotFoundError
    except (
        FileNotFoundError,
        NotADirectoryError,
        OSError,
        KeyError,
        ValueError,
        IndexError,
        StopIteration,
        json.JSONDecodeError, ResearchCompositionUnavailable,
    ):
        raise HTTPException(status_code=404, detail="artifact not found") from None
    except ResearchCompositionConflict as exc:
        raise HTTPException(status_code=409, detail="composition integrity conflict") from exc
    return _html_response(content)


class CompositionLaunchIn(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    question: str = Field(min_length=3, max_length=8000)
    parent_investigation_id: str | None = Field(default=None, max_length=512)
    research_tier: Literal["fast", "deep"] | None = None


class CompositionLaunchOut(BaseModel):
    investigation_id: str
    status: str
    start_event_id: str


@artifact_router.post(
    "/artifacts/compositions/{composition_id}/launch",
    response_model=CompositionLaunchOut,
    status_code=202,
)
async def launch_composed_artifact(
    composition_id: str, body: CompositionLaunchIn, request: Request
) -> CompositionLaunchOut:
    from substrate.event_log import append_persisted_event
    from substrate.schemas import Event

    owner = getattr(request.state, "user_id", None)
    if not owner:
        raise HTTPException(401, "authentication required")
    if_match = request.headers.get("If-Match")
    key = request.headers.get("Idempotency-Key")
    if if_match is None or key is None:
        raise HTTPException(428, "If-Match and Idempotency-Key are required")
    repository = ResearchCompositionRepository(db_path=_db())
    try:
        prepared = repository.prepare_launch(
            owner_user_id=owner, composition_id=composition_id, if_match=if_match,
            idempotency_key=key, options=body.model_dump(mode="json"),
        )
    except ResearchCompositionUnavailable:
        raise HTTPException(404, "composition is unavailable") from None
    except ResearchCompositionPrecondition:
        raise HTTPException(412, "composition ETag is stale") from None
    except ResearchCompositionConflict:
        raise HTTPException(409, "composition integrity or idempotency conflict") from None
    except ValueError:
        raise HTTPException(422, "composition launch request is invalid") from None
    if prepared.replay_response is not None:
        return CompositionLaunchOut.model_validate(prepared.replay_response)
    if prepared.delivery_event is None or prepared.lease_token is None:
        raise HTTPException(409, "composition delivery integrity conflict")
    try:
        delivery_event = repository.verify_delivery(
            owner_user_id=owner, idempotency_key=key, lease_token=prepared.lease_token
        )
        event = Event.model_validate(delivery_event)
    except Exception as exc:
        raise HTTPException(409, "composition delivery integrity conflict") from exc
    try:
        append_persisted_event(event)
        # EventBus deduplicates event_id within a process. After a process crash,
        # rebroadcasting the durable event is required because subscribers restart.
        await request.app.state.broadcaster.broadcast(event)
    except Exception as exc:
        raise HTTPException(503, "composition event delivery is unavailable") from exc
    result = CompositionLaunchOut(
        investigation_id=prepared.investigation_id, status="started",
        start_event_id=event.event_id,
    )
    try:
        repository.complete_launch(
            owner_user_id=owner, idempotency_key=key, lease_token=prepared.lease_token,
            response=result.model_dump(mode="json"),
        )
    except Exception as exc:
        raise HTTPException(503, "composition receipt is unavailable") from exc
    return result


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
