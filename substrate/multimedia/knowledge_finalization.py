"""Owner-bound orchestration from a ready multimedia asset to HTML twin knowledge."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from roles.note_taker import Distiller
from runtime.db_lock import connect_read
from services.html_projection.gate import ScriptViolation, assert_script_free
from substrate.books.serve_guard import serve_full_text_guarded
from substrate.graph.schema import init_database_at_path
from substrate.multimedia.information_asset import (
    MultimediaInformationAssetError,
    project_multimedia_information_asset,
)
from substrate.multimedia.knowledge_registration import (
    MultimediaDistillationState,
    MultimediaKnowledgeRegistrationError,
    MultimediaTwinResult,
    authorize_multimedia_distillation_recovery,
    get_multimedia_distillation_state,
    register_multimedia_with_twin,
)
from substrate.multimedia.read_model import (
    MultimediaAssetRecord,
    MultimediaAssetStore,
    MultimediaKnowledgeLink,
)


class MultimediaKnowledgeFinalizationError(RuntimeError):
    """The requested asset cannot be safely finalized as knowledge."""


class MultimediaKnowledgeFinalizationRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", str_strip_whitespace=True)

    expected_revision_id: str = Field(min_length=1, max_length=128)
    operator_acknowledged_model_use: bool = False


class MultimediaKnowledgeFinalizationResponse(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    asset: MultimediaAssetRecord
    knowledge_link: MultimediaKnowledgeLink


class MultimediaKnowledgeFinalizationStatus(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    asset_id: str
    revision_id: str
    asset_status: str
    distillation: MultimediaDistillationState
    knowledge_link: MultimediaKnowledgeLink | None = None


class MultimediaKnowledgeRecoveryRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", str_strip_whitespace=True)

    expected_revision_id: str = Field(min_length=1, max_length=128)
    operator_acknowledged_model_use: bool = False
    operator_acknowledged_duplicate_model_risk: bool = False


class MultimediaTwinDocument(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    asset_id: str
    revision_id: str
    source_document_id: str
    twin_document_id: str
    title: str
    html: str = Field(max_length=8 * 1024 * 1024)
    html_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


async def finalize_multimedia_knowledge(
    asset_id: str,
    request: MultimediaKnowledgeFinalizationRequest,
    *,
    owner_id: str,
    store: MultimediaAssetStore,
    db_path: str,
    distiller_factory: Callable[[], Distiller],
    events_dir: str | None = None,
    embedding_provider: Any = None,
    distillation_recovery_token: str | None = None,
) -> MultimediaKnowledgeFinalizationResponse:
    if not request.operator_acknowledged_model_use:
        raise MultimediaKnowledgeFinalizationError(
            "multimedia knowledge finalization requires explicit model-use acknowledgement"
        )
    try:
        record = store.reserve_knowledge_finalization(
            asset_id,
            expected_revision_id=request.expected_revision_id,
            owner_id=owner_id,
        )
    except KeyError as exc:
        raise MultimediaKnowledgeFinalizationError("multimedia asset is unavailable") from exc
    except ValueError as exc:
        raise MultimediaKnowledgeFinalizationError(str(exc)) from exc

    init_database_at_path(db_path)
    try:
        information_asset = project_multimedia_information_asset(record, owner_id=owner_id)
        result = await register_multimedia_with_twin(
            information_asset,
            db_path=db_path,
            owner_id=owner_id,
            distiller=distiller_factory(),
            events_dir=events_dir,
            embedding_provider=embedding_provider,
            distillation_recovery_token=distillation_recovery_token,
        )
    except (MultimediaInformationAssetError, MultimediaKnowledgeRegistrationError) as exc:
        raise MultimediaKnowledgeFinalizationError(str(exc)) from exc
    link = _link(result)
    try:
        linked = store.attach_knowledge_link(
            asset_id,
            link,
            expected_revision_id=request.expected_revision_id,
            owner_id=owner_id,
        )
    except (KeyError, ValueError) as exc:
        raise MultimediaKnowledgeFinalizationError(str(exc)) from exc
    return MultimediaKnowledgeFinalizationResponse(asset=linked, knowledge_link=link)


def inspect_multimedia_knowledge_finalization(
    asset_id: str,
    *,
    owner_id: str,
    store: MultimediaAssetStore,
    db_path: str,
) -> MultimediaKnowledgeFinalizationStatus:
    try:
        record = store.get(asset_id, owner_id=owner_id)
    except KeyError as exc:
        raise MultimediaKnowledgeFinalizationError("multimedia asset is unavailable") from exc
    if str(record.asset.status) != "ready":
        return MultimediaKnowledgeFinalizationStatus(
            asset_id=record.asset.asset_id,
            revision_id=record.asset.revision_id,
            asset_status=str(record.asset.status),
            distillation=MultimediaDistillationState(state="not_started", recovery_eligible=False),
            knowledge_link=record.knowledge_link,
        )
    init_database_at_path(db_path)
    asset = project_multimedia_information_asset(record, owner_id=owner_id)
    try:
        state = get_multimedia_distillation_state(asset, db_path=db_path, owner_id=owner_id)
    except MultimediaKnowledgeRegistrationError as exc:
        raise MultimediaKnowledgeFinalizationError(str(exc)) from exc
    return MultimediaKnowledgeFinalizationStatus(
        asset_id=record.asset.asset_id,
        revision_id=record.asset.revision_id,
        asset_status=str(record.asset.status),
        distillation=state,
        knowledge_link=record.knowledge_link,
    )


async def recover_multimedia_knowledge_finalization(
    asset_id: str,
    request: MultimediaKnowledgeRecoveryRequest,
    *,
    owner_id: str,
    store: MultimediaAssetStore,
    db_path: str,
    distiller_factory: Callable[[], Distiller],
    events_dir: str | None = None,
    embedding_provider: Any = None,
) -> MultimediaKnowledgeFinalizationResponse:
    if not request.operator_acknowledged_model_use:
        raise MultimediaKnowledgeFinalizationError(
            "multimedia recovery requires explicit model-use acknowledgement"
        )
    if not request.operator_acknowledged_duplicate_model_risk:
        raise MultimediaKnowledgeFinalizationError(
            "multimedia recovery requires duplicate-model-risk acknowledgement"
        )
    try:
        record = store.reserve_knowledge_finalization(
            asset_id,
            expected_revision_id=request.expected_revision_id,
            owner_id=owner_id,
        )
    except KeyError as exc:
        raise MultimediaKnowledgeFinalizationError("multimedia asset is unavailable") from exc
    except ValueError as exc:
        raise MultimediaKnowledgeFinalizationError(str(exc)) from exc
    init_database_at_path(db_path)
    asset = project_multimedia_information_asset(record, owner_id=owner_id)
    try:
        recovery_token = authorize_multimedia_distillation_recovery(
            asset, db_path=db_path, owner_id=owner_id
        )
    except MultimediaKnowledgeRegistrationError as exc:
        raise MultimediaKnowledgeFinalizationError(str(exc)) from exc
    return await finalize_multimedia_knowledge(
        asset_id,
        MultimediaKnowledgeFinalizationRequest(
            expected_revision_id=request.expected_revision_id,
            operator_acknowledged_model_use=True,
        ),
        owner_id=owner_id,
        store=store,
        db_path=db_path,
        distiller_factory=distiller_factory,
        events_dir=events_dir,
        embedding_provider=embedding_provider,
        distillation_recovery_token=recovery_token,
    )


def read_multimedia_twin_document(
    asset_id: str,
    *,
    owner_id: str,
    store: MultimediaAssetStore,
    db_path: str,
) -> MultimediaTwinDocument:
    try:
        record = store.get(asset_id, owner_id=owner_id)
    except KeyError as exc:
        raise MultimediaKnowledgeFinalizationError("multimedia twin is unavailable") from exc
    link = record.knowledge_link
    if link is None:
        raise MultimediaKnowledgeFinalizationError("multimedia twin is unavailable")
    owner_digest = hashlib.sha256(owner_id.encode()).hexdigest()
    identity_seed = f"{owner_digest}:{record.asset.asset_id}:{record.asset.revision_id}"
    identity_suffix = hashlib.sha256(identity_seed.encode()).hexdigest()[:24]
    if (
        link.asset_id != record.asset.asset_id
        or link.revision_id != record.asset.revision_id
        or link.source_document_id != f"mm-info-{identity_suffix}"
        or link.twin_document_id != f"mm-twin-{identity_suffix}"
        or link.graph_node_id != f"mm-entity-{identity_suffix}"
    ):
        raise MultimediaKnowledgeFinalizationError("multimedia twin integrity conflicts")

    with connect_read(db_path) as connection:
        row = connection.execute(
            "SELECT twin.source_uri, twin.title, twin.source_tier, twin.document_type, "
            "twin.investigation_id, twin.metadata, twin.content_class, "
            "twin.owner_user_id, source.investigation_id, source.owner_user_id, "
            "source.document_type, source.content_class, source.source_uri "
            "FROM documents AS twin LEFT JOIN documents AS source "
            "ON source.document_id=? WHERE twin.document_id=?",
            [link.source_document_id, link.twin_document_id],
        ).fetchone()
        twin_served = serve_full_text_guarded(connection, link.twin_document_id, owner=True)
        source_served = serve_full_text_guarded(connection, link.source_document_id, owner=True)
    if row is None:
        raise MultimediaKnowledgeFinalizationError("multimedia twin is unavailable")
    expected_uri = f"antiek-mm://{record.asset.asset_id}/{record.asset.revision_id}/twin.html"
    expected_title = f"Twin notes: {record.asset.title}"
    investigation_id = row[8]
    if (
        tuple(row[:5])
        != (
            expected_uri,
            expected_title,
            1,
            "multimedia_twin",
            investigation_id,
        )
        or not isinstance(investigation_id, str)
        or not investigation_id
        or tuple(row[6:])
        != (
            "personal_reading",
            owner_id,
            investigation_id,
            owner_id,
            "multimedia_html",
            "personal_reading",
            f"antiek-mm://{record.asset.asset_id}/{record.asset.revision_id}/information.html",
        )
    ):
        raise MultimediaKnowledgeFinalizationError("multimedia twin integrity conflicts")
    raw_html = twin_served.full_text
    if not isinstance(raw_html, str) or len(raw_html.encode()) > 8 * 1024 * 1024:
        raise MultimediaKnowledgeFinalizationError("multimedia twin integrity conflicts")
    source_html = source_served.full_text
    if (
        not isinstance(source_html, str)
        or hashlib.sha256(source_html.encode()).hexdigest() != link.source_html_sha256
    ):
        raise MultimediaKnowledgeFinalizationError("multimedia twin integrity conflicts")
    digest = hashlib.sha256(raw_html.encode()).hexdigest()
    if digest != link.twin_html_sha256:
        raise MultimediaKnowledgeFinalizationError("multimedia twin integrity conflicts")
    try:
        metadata = json.loads(row[5])
    except (TypeError, json.JSONDecodeError) as exc:
        raise MultimediaKnowledgeFinalizationError("multimedia twin integrity conflicts") from exc
    expected_metadata = {
        "schema_version": "antiek.multimedia-twin.v1",
        "owner_identity_digest": owner_digest,
        "asset_id": record.asset.asset_id,
        "revision_id": record.asset.revision_id,
        "source_html_sha256": link.source_html_sha256,
        "twin_html_sha256": link.twin_html_sha256,
    }
    if metadata != expected_metadata:
        raise MultimediaKnowledgeFinalizationError("multimedia twin integrity conflicts")
    try:
        assert_script_free(raw_html)
    except ScriptViolation as exc:
        raise MultimediaKnowledgeFinalizationError("multimedia twin integrity conflicts") from exc
    try:
        current = store.get(asset_id, owner_id=owner_id)
    except KeyError as exc:
        raise MultimediaKnowledgeFinalizationError("multimedia twin is unavailable") from exc
    if current.asset.revision_id != record.asset.revision_id or current.knowledge_link != link:
        raise MultimediaKnowledgeFinalizationError("multimedia twin integrity conflicts")
    return MultimediaTwinDocument(
        asset_id=record.asset.asset_id,
        revision_id=record.asset.revision_id,
        source_document_id=link.source_document_id,
        twin_document_id=link.twin_document_id,
        title=expected_title,
        html=raw_html,
        html_sha256=digest,
    )


def _link(result: MultimediaTwinResult) -> MultimediaKnowledgeLink:
    return MultimediaKnowledgeLink(
        asset_id=result.registration.asset_id,
        revision_id=result.registration.revision_id,
        source_document_id=result.source_document_id,
        source_event_id=result.source_event_id,
        graph_node_id=result.registration.graph_node_id,
        twin_document_id=result.registration.twin_document_id,
        source_html_sha256=result.registration.html_sha256,
        twin_html_sha256=result.twin_html_sha256,
        insight_node_ids=result.insight_node_ids,
        question_node_ids=result.question_node_ids,
    )


__all__ = [
    "MultimediaKnowledgeFinalizationError",
    "MultimediaKnowledgeFinalizationRequest",
    "MultimediaKnowledgeFinalizationResponse",
    "MultimediaKnowledgeFinalizationStatus",
    "MultimediaKnowledgeRecoveryRequest",
    "MultimediaTwinDocument",
    "finalize_multimedia_knowledge",
    "inspect_multimedia_knowledge_finalization",
    "recover_multimedia_knowledge_finalization",
    "read_multimedia_twin_document",
]
