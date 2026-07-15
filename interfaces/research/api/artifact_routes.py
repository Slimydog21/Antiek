"""ResearchArtifact export + outline blocks (ANT-AHT)."""

from __future__ import annotations

import hashlib
import json
import os
import stat
import sys
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import Response
from pydantic import BaseModel, Field

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
)
from substrate.research_artifact.compose import (  # noqa: E402
    composition_id_for,
    render_composition_index,
    validate_investigation_ids,
)
from substrate.research_artifact.paths import (  # noqa: E402
    composition_member_path_for,
    composition_path_for,
)

artifact_router = APIRouter(prefix="/research", tags=["research-artifact"])


def _read_store_file(*parts: str) -> bytes:
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    directory_flags = flags | getattr(os, "O_DIRECTORY", 0)
    root = os.open(os.fspath(composition_path_for("cmp-" + "0" * 64).parent), directory_flags)
    descriptor = root
    try:
        for part in parts[:-1]:
            next_descriptor = os.open(part, directory_flags, dir_fd=descriptor)
            if descriptor != root:
                os.close(descriptor)
            descriptor = next_descriptor
        file_descriptor = os.open(parts[-1], flags, dir_fd=descriptor)
        try:
            info = os.fstat(file_descriptor)
            if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
                raise FileNotFoundError
            chunks: list[bytes] = []
            while chunk := os.read(file_descriptor, 1024 * 1024):
                chunks.append(chunk)
            return b"".join(chunks)
        finally:
            os.close(file_descriptor)
    finally:
        if descriptor != root:
            os.close(descriptor)
        os.close(root)


def _html_response(content: bytes) -> Response:
    return Response(
        content,
        media_type="text/html",
        headers={"Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff"},
    )


def _verified_index(content: bytes, composition_id: str) -> dict[str, object]:
    marker = b'id="composition-metadata">'
    metadata = json.loads(content.split(marker, 1)[1].split(b"</script>", 1)[0])
    members = metadata["members"]
    if (
        not isinstance(members, list)
        or not 2 <= len(members) <= 20
        or any(
            not isinstance(member, dict)
            or set(member) != {"investigation_id", "content_hash", "rendered_sha256"}
            or not isinstance(member.get("investigation_id"), str)
            or not isinstance(member.get("content_hash"), str)
            or not isinstance(member.get("rendered_sha256"), str)
            or len(member["content_hash"]) != 64
            or len(member["rendered_sha256"]) != 64
            for member in members
        )
    ):
        raise ValueError("invalid composition members")
    identity = [
        (
            str(member["investigation_id"]),
            str(member["content_hash"]),
            str(member["rendered_sha256"]),
        )
        for member in members
    ]
    expected_conflicts: list[list[str]] = []
    first_by_hash: dict[str, str] = {}
    for investigation_id, content_hash, _rendered_sha256 in identity:
        if content_hash in first_by_hash:
            expected_conflicts.append([first_by_hash[content_hash], investigation_id])
        else:
            first_by_hash[content_hash] = investigation_id
    if (
        set(metadata)
        != {
            "composition_id",
            "hash_conflicts",
            "members",
            "ordered_set_digest",
            "schema_version",
        }
        or type(metadata.get("schema_version")) is not int
        or metadata.get("schema_version") != 1
        or metadata.get("hash_conflicts") != expected_conflicts
        or metadata.get("composition_id") != composition_id
        or metadata.get("ordered_set_digest") != composition_id.removeprefix("cmp-")
        or composition_id_for(identity) != composition_id
        or render_composition_index(metadata).encode("utf-8") != content
    ):
        raise ValueError("composition index integrity failure")
    return metadata


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
    investigation_ids: list[str] = Field(min_length=2, max_length=20)


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
async def post_compose_artifacts(body: ComposeIn, request: Request) -> ComposeOut:
    # Authentication and identity derivation happen in app middleware. Research
    # event storage currently has no owner field, so owner-level filtering cannot
    # honestly be enforced here; no owner value is accepted from the caller.
    if not getattr(request.state, "user_id", None):
        raise HTTPException(status_code=401, detail="authentication required")
    try:
        validate_investigation_ids(body.investigation_ids)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    for iid in body.investigation_ids:
        rows = trajectory(iid)
        if not rows:
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
        result = compose_artifacts(body.investigation_ids, db_path=_db())
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
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
    if not getattr(request.state, "user_id", None):
        raise HTTPException(status_code=401, detail="authentication required")
    try:
        path = composition_path_for(composition_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="composition not found") from exc
    try:
        content = _read_store_file(path.name)
        _verified_index(content, composition_id)
    except (
        FileNotFoundError,
        NotADirectoryError,
        OSError,
        KeyError,
        ValueError,
        IndexError,
        json.JSONDecodeError,
    ):
        raise HTTPException(status_code=404, detail="composition not found") from None
    return _html_response(content)


@artifact_router.get("/artifacts/compositions/{composition_id}/{investigation_id}")
async def get_composed_member(
    composition_id: str, investigation_id: str, request: Request
) -> Response:
    if not getattr(request.state, "user_id", None):
        raise HTTPException(status_code=401, detail="authentication required")
    try:
        path = composition_member_path_for(composition_id, investigation_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="artifact not found") from exc
    try:
        index_content = _read_store_file(f"{composition_id}.html")
        metadata = _verified_index(index_content, composition_id)
        expected = next(
            member["rendered_sha256"]
            for member in metadata["members"]
            if member["investigation_id"] == investigation_id
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
        json.JSONDecodeError,
    ):
        raise HTTPException(status_code=404, detail="artifact not found") from None
    return _html_response(content)


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
