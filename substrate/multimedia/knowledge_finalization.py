"""Owner-bound orchestration from a ready multimedia asset to HTML twin knowledge."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from roles.note_taker import Distiller
from substrate.graph.schema import init_database_at_path
from substrate.multimedia.information_asset import (
    MultimediaInformationAssetError,
    project_multimedia_information_asset,
)
from substrate.multimedia.knowledge_registration import (
    MultimediaKnowledgeRegistrationError,
    MultimediaTwinResult,
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
    "finalize_multimedia_knowledge",
]
