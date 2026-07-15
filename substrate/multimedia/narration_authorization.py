"""Server-derived V2 authorization for one exact chapter narration call."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Literal, Protocol

from .audible_run import prepare_audible_run_plan
from .chapter_tts_production import PreparedChapterTTSRequest, prepare_chapter_tts_request
from .execution_authorization import MultimediaExecutionAuthorizationV2
from .execution_authorization_issuer import (
    AsyncExecutionAuthorizationIssueRequest,
    ExecutionAuthorizationIssueConflict,
)
from .graph_evidence import MultimediaGraphEvidenceUnavailable, load_canonical_multimedia_chunks
from .narration_run import narration_child_revision
from .read_model import MultimediaAssetRecord, MultimediaAssetStore


class NarrationAuthorizationError(RuntimeError):
    """The requested chapter authority is unavailable or conflicts."""


@dataclass(frozen=True)
class NarrationAuthorizationRequest:
    request_id: str
    expected_revision_id: str
    chapter_id: str
    approved_ceiling_microdollars: int
    operator_acknowledged_spend: bool
    voice: str = "narrator"
    speed: float = 1.0
    sample_rate_hz: int = 24_000
    channels: Literal[1, 2] = 1
    ttl_seconds: int = 900


@dataclass(frozen=True)
class TrustedNarrationTerms:
    provider: str
    model: str
    endpoint_capability: Literal["text-to-speech"]
    catalog_version: str
    catalog_digest: str
    quote_id: str
    quote_ttl_seconds: int
    recovery_authority_id: str
    recovery_verification_key_digest: str
    maximum_ceiling_microdollars: int


@dataclass(frozen=True)
class NarrationAuthorizationResult:
    prepared: PreparedChapterTTSRequest
    authorization: MultimediaExecutionAuthorizationV2


class AsyncAuthorizationIssuer(Protocol):
    def issue_async(
        self, request: AsyncExecutionAuthorizationIssueRequest, *, now: datetime
    ) -> MultimediaExecutionAuthorizationV2: ...


def authorize_multimedia_chapter_narration(
    asset_id: str,
    request: NarrationAuthorizationRequest,
    *,
    owner_id: str,
    store: MultimediaAssetStore,
    terms_resolver: Callable[[MultimediaAssetRecord, str], TrustedNarrationTerms],
    issuer: AsyncAuthorizationIssuer,
    clock: Callable[[], datetime],
    db_path: str | None = None,
) -> NarrationAuthorizationResult:
    try:
        record = store.get(asset_id, owner_id=owner_id)
    except (KeyError, ValueError) as exc:
        raise NarrationAuthorizationError("multimedia asset is unavailable") from exc
    if record.asset.revision_id != request.expected_revision_id:
        raise NarrationAuthorizationError("multimedia narration revision is not current")
    if str(record.asset.status) != "ready":
        raise NarrationAuthorizationError("multimedia narration requires a ready asset")
    if record.asset.route_policy == "cheapest":
        raise NarrationAuthorizationError("cheapest route cannot authorize paid narration")
    if not request.operator_acknowledged_spend:
        raise NarrationAuthorizationError("operator spend acknowledgement is required")
    ceiling = request.approved_ceiling_microdollars
    if isinstance(ceiling, bool) or not isinstance(ceiling, int) or ceiling <= 0:
        raise NarrationAuthorizationError("approved narration ceiling is invalid")

    authorization_plan = record.plan
    if record.mode == "audio" or str(record.asset.kind) == "audio_experience":
        canonical_ids = tuple(
            dict.fromkeys(
                span.chunk_id
                for line in record.plan.script_lines
                if line.evidence_derivation is not None
                for span in line.evidence_derivation.spans
                if span.authority_kind == "canonical_graph"
            )
        )
        try:
            canonical_chunks = (
                load_canonical_multimedia_chunks(db_path, canonical_ids, owner_id=owner_id)
                if canonical_ids and db_path is not None
                else None
            )
            if canonical_ids and canonical_chunks is None:
                raise NarrationAuthorizationError("canonical narration evidence is unavailable")
            authorization_plan = prepare_audible_run_plan(
                record.plan, canonical_chunks=canonical_chunks
            )
        except (MultimediaGraphEvidenceUnavailable, OSError, RuntimeError, ValueError) as exc:
            raise NarrationAuthorizationError(
                "canonical narration evidence is unavailable"
            ) from exc

    spoken_chapters = tuple(
        chapter.chapter_id
        for chapter in authorization_plan.chapters
        if any(
            line.line_id.split("-line-", 1)[0] == chapter.chapter_id
            for line in authorization_plan.script_lines
        )
    )
    try:
        sequence = spoken_chapters.index(request.chapter_id)
        terms = terms_resolver(record, request.chapter_id)
    except (LookupError, ValueError) as exc:
        raise NarrationAuthorizationError(
            "narration chapter or trusted terms are unavailable"
        ) from exc
    if terms.endpoint_capability != "text-to-speech":
        raise NarrationAuthorizationError("trusted narration capability conflicts")
    if ceiling > terms.maximum_ceiling_microdollars:
        raise NarrationAuthorizationError("approved narration ceiling exceeds trusted quote")

    child_revision = narration_child_revision(
        request.expected_revision_id, request.chapter_id, sequence
    )
    try:
        prepared = prepare_chapter_tts_request(
            authorization_plan,
            asset_id=asset_id,
            revision_id=child_revision,
            provider=terms.provider,
            model=terms.model,
            chapter_id=request.chapter_id,
            voice=request.voice,
            speed=request.speed,
            sample_rate_hz=request.sample_rate_hz,
            channels=request.channels,
        )
        authorization = issuer.issue_async(
            AsyncExecutionAuthorizationIssueRequest(
                request_id=request.request_id,
                operator_id=owner_id,
                asset_id=asset_id,
                revision_id=child_revision,
                provider=terms.provider,
                route_policy=record.asset.route_policy,
                model=terms.model,
                endpoint_capability=terms.endpoint_capability,
                catalog_version=terms.catalog_version,
                catalog_digest=terms.catalog_digest,
                quote_id=terms.quote_id,
                quote_ttl_seconds=terms.quote_ttl_seconds,
                recovery_authority_id=terms.recovery_authority_id,
                recovery_verification_key_digest=terms.recovery_verification_key_digest,
                approved_ceiling_microdollars=ceiling,
                request_body_digest=prepared.body_digest,
                ttl_seconds=request.ttl_seconds,
            ),
            now=clock(),
        )
    except (ExecutionAuthorizationIssueConflict, ValueError) as exc:
        raise NarrationAuthorizationError(str(exc)) from exc
    return NarrationAuthorizationResult(prepared=prepared, authorization=authorization)


__all__ = [
    "NarrationAuthorizationError",
    "NarrationAuthorizationRequest",
    "NarrationAuthorizationResult",
    "TrustedNarrationTerms",
    "authorize_multimedia_chapter_narration",
]
