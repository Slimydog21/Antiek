"""ResearchArtifact export + outline blocks (ANT-AHT)."""

from __future__ import annotations

import os
import sys
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

_PKG_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
if _PKG_ROOT not in sys.path:
    sys.path.insert(0, _PKG_ROOT)

from runtime.db_lock import connect_write  # noqa: E402
from substrate.graph import default_db_path, ensure_initialized  # noqa: E402
from substrate.research_artifact import (  # noqa: E402
    apply_source_merge_review,
    build_html_only,
    compose_artifacts,
    export_research_artifact,
    import_agent_notes,
    list_outline_blocks,
    render_twin_notes_html,
)
from substrate.research_artifact.build_body import build_body  # noqa: E402
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


class SourceMergeReviewPacketIn(BaseModel):
    kind: str
    document_id: str = Field(min_length=1)
    title: str | None = None
    parent_reading_thread_id: str = Field(min_length=1)
    draft_merge_path: str = Field(min_length=1)
    compose_index_path: str = Field(min_length=1)
    member_investigation_ids: list[str] = Field(min_length=2)
    requested_investigation_ids: list[str] = Field(default_factory=list)
    hash_conflict_count: int = Field(ge=0)
    hash_conflicts: list[list[str]] = Field(default_factory=list)
    source_book_mutated: bool
    twin_document_mutated: bool
    no_spend: bool


class SourceMergeApplyIn(BaseModel):
    reviewed_packet: SourceMergeReviewPacketIn
    expected_content_hashes: dict[str, str] = Field(default_factory=dict)
    acknowledge_reviewed_draft: bool = False
    acknowledge_source_book_mutation: bool = False
    acknowledge_twin_document_mutation: bool = False
    acknowledge_hash_conflicts: bool = False
    operator_reviewer: str | None = Field(default=None, max_length=160)


class SourceMergeApplyOut(BaseModel):
    status: str
    document_id: str
    source_revision_id: str
    twin_revision_id: str
    event_id: str
    member_investigation_ids: list[str]
    hash_conflicts_acknowledged: bool


def _clean_member_ids(raw_ids: list[str]) -> list[str]:
    ids: list[str] = []
    for item in raw_ids:
        iid = item.strip()
        if iid and iid not in ids:
            ids.append(iid)
    return ids


def _raise_source_merge_refusal(detail: str, *, status_code: int = 409) -> None:
    raise HTTPException(status_code=status_code, detail=detail)


def _validate_source_merge_preflight(body: SourceMergeApplyIn, *, db_path: str) -> list[str]:
    packet = body.reviewed_packet
    if packet.kind != "antiek.reader.source_merge_review_packet":
        _raise_source_merge_refusal("invalid_source_merge_review_packet", status_code=400)
    if packet.source_book_mutated or packet.twin_document_mutated:
        _raise_source_merge_refusal("source_merge_packet_already_mutated")
    if not packet.no_spend:
        _raise_source_merge_refusal("source_merge_packet_must_be_no_spend", status_code=400)
    member_ids = _clean_member_ids(packet.member_investigation_ids)
    if len(member_ids) < 2:
        _raise_source_merge_refusal("source_merge_requires_two_members", status_code=400)
    if len(packet.hash_conflicts) != packet.hash_conflict_count:
        _raise_source_merge_refusal("source_merge_conflict_count_mismatch", status_code=400)
    if (
        not body.acknowledge_reviewed_draft
        or not body.acknowledge_source_book_mutation
        or not body.acknowledge_twin_document_mutation
    ):
        _raise_source_merge_refusal("source_merge_operator_acknowledgement_required")
    if packet.hash_conflicts and not body.acknowledge_hash_conflicts:
        _raise_source_merge_refusal("source_merge_hash_conflicts_acknowledgement_required")

    missing_hashes = [iid for iid in member_ids if not body.expected_content_hashes.get(iid)]
    if missing_hashes:
        _raise_source_merge_refusal("source_merge_expected_content_hashes_required", status_code=400)
    stale_ids: list[str] = []
    for iid in member_ids:
        current_hash = build_body(iid, db_path=db_path).content_hash()
        if current_hash != body.expected_content_hashes[iid]:
            stale_ids.append(iid)
    if stale_ids:
        _raise_source_merge_refusal("source_merge_stale_review_packet")
    return member_ids


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


@artifact_router.post("/artifacts/source-merge/apply", response_model=SourceMergeApplyOut)
async def post_source_merge_apply(body: SourceMergeApplyIn) -> SourceMergeApplyOut:
    """Preflight the irreversible source-book/twin apply boundary.

    This route validates the reviewed packet and all mutation acknowledgements,
    then records the first durable apply receipt under the DuckDB write lock.
    The receipt is a metadata ledger entry: the source book body and twin body
    are not rewritten by this milestone.
    """

    db_path = _db()
    member_ids = _validate_source_merge_preflight(body, db_path=db_path)
    packet = body.reviewed_packet
    try:
        with connect_write(db_path, purpose="research_artifact/source_merge_apply") as con:
            receipt = apply_source_merge_review(
                con,
                document_id=packet.document_id,
                parent_reading_thread_id=packet.parent_reading_thread_id,
                draft_merge_path=packet.draft_merge_path,
                compose_index_path=packet.compose_index_path,
                member_investigation_ids=member_ids,
                expected_content_hashes=body.expected_content_hashes,
                hash_conflicts=packet.hash_conflicts,
                hash_conflicts_acknowledged=body.acknowledge_hash_conflicts,
                operator_reviewer=body.operator_reviewer,
            )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return SourceMergeApplyOut(
        status=receipt.status,
        document_id=receipt.document_id,
        source_revision_id=receipt.source_revision_id,
        twin_revision_id=receipt.twin_revision_id,
        event_id=receipt.event_id or "",
        member_investigation_ids=receipt.member_investigation_ids,
        hash_conflicts_acknowledged=receipt.hash_conflicts_acknowledged,
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
