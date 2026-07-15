"""Multimedia REST routes.

Dry-run only: these routes persist/reopen multimedia assets and run deterministic
planner/audio/video/steering/hardening seams without live provider spend.
"""

from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from decimal import ROUND_CEILING, Decimal, InvalidOperation
from pathlib import Path
from typing import Any, cast

import yaml
from fastapi import APIRouter, Depends, FastAPI, HTTPException, Request

from roles.note_taker import DispatchDistiller, Distiller
from substrate.multimedia.authorized_production_worker import AuthorizedProductionRuntime
from substrate.multimedia.graph_evidence import (
    CreateGroundedMultimediaDraftRequest,
    MultimediaEvidenceSearchRequest,
    MultimediaEvidenceSearchResult,
    MultimediaGraphEvidence,
    MultimediaGraphEvidenceUnavailable,
    load_canonical_multimedia_chunks,
)
from substrate.multimedia.knowledge_finalization import (
    MultimediaKnowledgeFinalizationError,
    MultimediaKnowledgeFinalizationRequest,
    MultimediaKnowledgeFinalizationResponse,
    MultimediaKnowledgeFinalizationStatus,
    MultimediaKnowledgeRecoveryRequest,
    MultimediaTwinDocument,
    finalize_multimedia_knowledge,
    inspect_multimedia_knowledge_finalization,
    read_multimedia_twin_document,
    recover_multimedia_knowledge_finalization,
)
from substrate.multimedia.listening_progress import (
    AudioIdentity,
    ListeningProgressError,
    ListeningProgressStore,
)
from substrate.multimedia.local_audible_coordinator import LocalAudibleCoordinator
from substrate.multimedia.local_production_coordinator import (
    LocalVideoProductionCoordinator,
)
from substrate.multimedia.local_provider_exclusion import (
    LocalZeroEvidenceUnavailable,
)
from substrate.multimedia.local_zero_cost_evidence import (
    LocalZeroExternalCostEvidenceV1,
    build_local_audio_zero_cost_evidence,
    build_local_video_zero_cost_evidence,
)
from substrate.multimedia.paid_video_cost_authority import (
    build_paid_registered_video_cost_authority,
)
from substrate.multimedia.production_cost_closure import (
    build_production_byte_cost_closure,
)
from substrate.multimedia.production_cost_projection import ProductionByteProjectionV1
from substrate.multimedia.production_registration import (
    MultimediaProductionRegistrationRequest,
    register_multimedia_production,
)
from substrate.multimedia.read_model import (
    ApplySteeringPreviewRequest,
    CreateMultimediaDraftRequest,
    MultimediaAssetList,
    MultimediaAssetRecord,
    MultimediaAssetStore,
    MultimediaJobList,
    SteeringPreviewConflict,
    SteeringPreviewRequest,
    SteeringPreviewResponse,
)
from substrate.multimedia.research_intent import ResearchIntentLedger
from substrate.multimedia.research_plan import (
    InvestigationActivationQuote,
    PreparedInvestigation,
    ResearchPlanLedger,
)
from substrate.multimedia.ship_cost_snapshot import (
    MultimediaShipCostEvidenceConflict,
    MultimediaShipCostEvidenceUnavailable,
    build_multimedia_ship_cost_snapshot,
)
from substrate.multimedia.verified_audio_playback import AudioPlaybackMetadata
from substrate.multimedia.verified_playback import VerifiedPlaybackError

from .multimedia_hardening_routes import (
    MultimediaHardeningRuntime,
    get_multimedia_hardening_runtime,
    multimedia_hardening_runtime_from_environment,
)
from .multimedia_listening_progress_routes import (
    get_listening_progress_runtime,
    listening_progress_runtime,
    multimedia_listening_progress_router,
)
from .multimedia_local_audible_routes import (
    get_multimedia_local_audible_runtime,
    get_multimedia_local_audible_runtime_optional,
    multimedia_local_audible_router,
)
from .multimedia_local_audible_runtime import (
    MultimediaLocalAudibleRuntime,
    multimedia_local_audible_runtime_from_environment,
)
from .multimedia_local_routes import (
    get_multimedia_local_runtime,
    get_multimedia_local_runtime_optional,
    multimedia_local_router,
)
from .multimedia_local_runtime import multimedia_local_runtime_from_environment
from .multimedia_narration_authorization_routes import (
    get_multimedia_narration_authorization_runtime,
    multimedia_narration_authorization_router,
    multimedia_narration_authorization_runtime_from_environment,
)
from .multimedia_paid_audio_playback_routes import (
    PaidAudioPlaybackRouteRuntime,
    get_multimedia_paid_audio_playback_runtime,
    multimedia_paid_audio_playback_router,
)
from .multimedia_playback_routes import (
    get_multimedia_playback_runtime,
    multimedia_playback_router,
    multimedia_playback_runtime_from_environment,
)
from .multimedia_production_worker_routes import (
    get_multimedia_production_worker_runtime,
    multimedia_production_worker_router,
)
from .multimedia_production_worker_runtime import (
    multimedia_production_worker_runtime_from_environment,
)
from .multimedia_reconciliation_routes import (
    authenticated_multimedia_operator,
    authenticated_multimedia_policy_tag,
    get_multimedia_reconciliation_runtime,
    multimedia_reconciliation_router,
    multimedia_reconciliation_runtime_from_environment,
)
from .multimedia_research_intent_routes import (
    ResearchIntentRouteRuntime,
    get_multimedia_research_intent_runtime,
    multimedia_research_intent_router,
)
from .multimedia_research_plan_routes import (
    ResearchPlanRouteRuntime,
    get_multimedia_research_plan_runtime,
    multimedia_research_plan_router,
)
from .multimedia_reviewed_visual_routes import (
    get_multimedia_reviewed_visual_runtime,
    multimedia_reviewed_visual_router,
    multimedia_reviewed_visual_runtime_from_environment,
)
from .multimedia_tts_gateway_routes import (
    get_multimedia_tts_gateway_runtime,
    multimedia_tts_gateway_router,
    multimedia_tts_gateway_runtime_from_environment,
)
from .multimedia_visual_authorization_routes import (
    get_multimedia_visual_authorization_runtime,
    multimedia_visual_authorization_router,
    multimedia_visual_authorization_runtime_from_environment,
)
from .multimedia_visual_candidate_routes import (
    get_multimedia_visual_candidate_runtime,
    multimedia_visual_candidate_router,
    multimedia_visual_candidate_runtime_from_environment,
)
from .multimedia_visual_generation_routes import (
    get_multimedia_visual_generation_runtime,
    multimedia_visual_generation_router,
    multimedia_visual_generation_runtime_from_environment,
)
from .multimedia_visual_quality_routes import (
    get_multimedia_visual_quality_runtime,
    multimedia_visual_quality_router,
    multimedia_visual_quality_runtime_from_environment,
)
from .multimedia_visual_review_routes import (
    get_multimedia_visual_review_runtime,
    multimedia_visual_review_router,
    multimedia_visual_review_runtime_from_environment,
)

multimedia_router = APIRouter(prefix="/multimedia", tags=["multimedia"])
multimedia_router.include_router(multimedia_reconciliation_router)
multimedia_router.include_router(multimedia_local_router)

_ACTIVATION_POLICY_TIERS = {
    "cheapest": "flash",
    "balanced": "pro",
    "highest_quality": "synthesis",
}
_DISPATCH_CONFIG_PATH = Path(__file__).parents[3] / "substrate" / "dispatch" / "config.yaml"
_PRICING_SOURCE = "substrate/dispatch/config.yaml"
_MILLION = Decimal(1_000_000)
_MAX_QUOTE_CENTS = 9_223_372_036_854_775_807


class _DecimalSafeLoader(yaml.SafeLoader):
    pass


def _decimal_yaml(loader: yaml.SafeLoader, node: yaml.Node) -> Decimal:
    return Decimal(loader.construct_scalar(node))


_DecimalSafeLoader.add_constructor("tag:yaml.org,2002:float", _decimal_yaml)


def _jsonable(value: object) -> object:
    if isinstance(value, Decimal):
        return {"decimal": str(value)}
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_jsonable(item) for item in value]
    return value


def _canonical_digest(value: object) -> str:
    return hashlib.sha256(json.dumps(
        _jsonable(value), ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")).hexdigest()


def _production_activation_quote_resolver(
    config_path: Path = _DISPATCH_CONFIG_PATH,
    *,
    clock: Callable[[], datetime] = lambda: datetime.now(UTC),
) -> Callable[[PreparedInvestigation, str], InvestigationActivationQuote]:
    """Build quotes without dispatching work.

    The ceiling assumes one uncached provider call for every prepared tree node
    and one additional call for every leaf question.  Every assumed call is
    charged the tier's full ``context_budget_tokens`` as input and full
    ``max_tokens`` as output.  This deliberately conservative bound includes
    decomposition/internal-node work and leaf retrieval/synthesis work; cached
    pricing is never assumed.
    """
    def resolve(prepared: PreparedInvestigation, route_policy: str) -> InvestigationActivationQuote:
        tier_name = _ACTIVATION_POLICY_TIERS.get(route_policy)
        if tier_name is None:
            raise ValueError("activation quote unavailable")
        try:
            raw = config_path.read_bytes()
            config = yaml.load(raw, Loader=_DecimalSafeLoader)
            if not isinstance(config, dict):
                raise ValueError
            tiers = config["tiers"]
            defaults = config["tier_defaults"]
            tier = tiers[tier_name]
            limits = defaults[tier_name]
            if not isinstance(tiers, dict) or not isinstance(defaults, dict):
                raise ValueError
            if not isinstance(tier, dict) or not isinstance(limits, dict):
                raise ValueError
            provider, model, pricing = tier["provider"], tier["model"], tier["pricing"]
            if not isinstance(provider, str) or not provider or not isinstance(model, str) or not model:
                raise ValueError
            if not isinstance(pricing, dict):
                raise ValueError
            input_rate = Decimal(str(pricing["input_per_mtok"]))
            output_rate = Decimal(str(pricing["output_per_mtok"]))
            cached_rate = Decimal(str(pricing["cached_input_per_mtok"]))
            context_tokens = limits["context_budget_tokens"]
            output_tokens = limits["max_tokens"]
            if (type(context_tokens) is not int or context_tokens <= 0
                    or type(output_tokens) is not int or output_tokens <= 0
                    or any(not rate.is_finite() or rate <= 0
                           for rate in (input_rate, output_rate, cached_rate))):
                raise ValueError
            call_count = prepared.total_node_count + prepared.leaf_question_count
            if (type(prepared.total_node_count) is not int
                    or type(prepared.leaf_question_count) is not int or call_count <= 0):
                raise ValueError
            ceiling_usd = Decimal(call_count) * (
                Decimal(context_tokens) * input_rate
                + Decimal(output_tokens) * output_rate
            ) / _MILLION
            ceiling_cents = int((ceiling_usd * 100).to_integral_value(rounding=ROUND_CEILING))
            if not 0 < ceiling_cents <= _MAX_QUOTE_CENTS:
                raise ValueError
        except (
            KeyError, OSError, OverflowError, TypeError, ValueError,
            InvalidOperation, yaml.YAMLError,
        ) as exc:
            raise ValueError("activation quote unavailable") from exc

        dispatch_digest = _canonical_digest(config)
        pricing_binding = {
            "model": model,
            "pricing": {
                "cached_input_per_mtok": str(cached_rate),
                "input_per_mtok": str(input_rate),
                "output_per_mtok": str(output_rate),
            },
            "pricing_source": _PRICING_SOURCE,
            "provider": provider,
            "resolved_tier": tier_name,
        }
        pricing_digest = _canonical_digest(pricing_binding)
        prepared_digest = _canonical_digest(vars(prepared))
        workload_digest = _canonical_digest({
            "investigation_id": prepared.investigation_id,
            "prepared_integrity_digest": prepared_digest,
            "total_node_count": prepared.total_node_count,
            "leaf_question_count": prepared.leaf_question_count,
        })
        quote_id = "aq_" + _canonical_digest({
            "dispatch_config_digest": dispatch_digest,
            "pricing_digest": pricing_digest,
            "route_policy": route_policy,
            "workload_digest": workload_digest,
        })[:48]
        clock_value = clock()
        if clock_value.tzinfo is None or clock_value.utcoffset() is None:
            raise ValueError("activation quote unavailable")
        issued = clock_value.astimezone(UTC).replace(microsecond=0)
        expires = issued + timedelta(hours=24)
        return InvestigationActivationQuote(
            schema_version=1, route_policy=route_policy, resolved_tier=tier_name,
            provider=provider, model=model, dispatch_config_digest=dispatch_digest,
            pricing_source=_PRICING_SOURCE, pricing_digest=pricing_digest,
            workload_digest=workload_digest, quoted_ceiling_cents=ceiling_cents,
            quote_id=quote_id, issued_at=issued.isoformat().replace("+00:00", "Z"),
            expires_at=expires.isoformat().replace("+00:00", "Z"),
        )

    return resolve
multimedia_router.include_router(multimedia_local_audible_router)
multimedia_router.include_router(multimedia_playback_router)
multimedia_router.include_router(multimedia_paid_audio_playback_router)
multimedia_router.include_router(multimedia_listening_progress_router)
multimedia_router.include_router(multimedia_research_intent_router)
multimedia_router.include_router(multimedia_research_plan_router)
multimedia_router.include_router(multimedia_narration_authorization_router)
multimedia_router.include_router(multimedia_reviewed_visual_router)
multimedia_router.include_router(multimedia_production_worker_router)
multimedia_router.include_router(multimedia_tts_gateway_router)
multimedia_router.include_router(multimedia_visual_authorization_router)
multimedia_router.include_router(multimedia_visual_generation_router)
multimedia_router.include_router(multimedia_visual_candidate_router)
multimedia_router.include_router(multimedia_visual_review_router)
multimedia_router.include_router(multimedia_visual_quality_router)
_STORE = MultimediaAssetStore()


@dataclass(frozen=True)
class MultimediaKnowledgeRuntime:
    db_path: str
    distiller_factory: Callable[[], Distiller]
    events_dir: str | None = None
    embedding_provider: Any = None


@dataclass(frozen=True)
class MultimediaEvidenceRuntime:
    db_path: str
    embedding_provider_factory: Callable[[], Any]


def get_store() -> MultimediaAssetStore:
    return _STORE


def get_multimedia_knowledge_runtime() -> MultimediaKnowledgeRuntime:
    raise HTTPException(status_code=503, detail="multimedia knowledge runtime is unavailable")


def get_multimedia_evidence_runtime() -> MultimediaEvidenceRuntime:
    raise HTTPException(status_code=503, detail="multimedia evidence runtime is unavailable")


def get_multimedia_evidence_runtime_optional() -> MultimediaEvidenceRuntime | None:
    return None


def multimedia_evidence_runtime_from_environment(
    environ: dict[str, str] | None = None,
) -> MultimediaEvidenceRuntime | None:
    values = os.environ if environ is None else environ
    enabled = values.get("ANTIEK_MULTIMEDIA_EVIDENCE_ENABLED", "").strip().lower()
    db_path = values.get("ANTIEK_MULTIMEDIA_EVIDENCE_DB_PATH", "").strip()
    if not any((enabled, db_path)):
        return None
    if enabled not in {"1", "true"} or not db_path:
        raise RuntimeError("multimedia evidence configuration is incomplete")

    def provider() -> Any:
        from processing.embedding import default_embedding_provider

        return default_embedding_provider()

    return MultimediaEvidenceRuntime(db_path=db_path, embedding_provider_factory=provider)


def multimedia_knowledge_runtime_from_environment(
    environ: dict[str, str] | None = None,
) -> MultimediaKnowledgeRuntime | None:
    values = os.environ if environ is None else environ
    enabled = values.get("ANTIEK_MULTIMEDIA_KNOWLEDGE_ENABLED", "").strip().lower()
    db_path = values.get("ANTIEK_MULTIMEDIA_KNOWLEDGE_DB_PATH", "").strip()
    events_dir = values.get("ANTIEK_MULTIMEDIA_KNOWLEDGE_EVENTS_DIR", "").strip()
    if not any((enabled, db_path, events_dir)):
        return None
    if enabled not in {"1", "true"} or not db_path:
        raise RuntimeError("multimedia knowledge configuration is incomplete")
    return MultimediaKnowledgeRuntime(
        db_path=db_path,
        events_dir=events_dir or None,
        distiller_factory=DispatchDistiller,
    )


@multimedia_router.post("/assets", response_model=MultimediaAssetRecord, status_code=201)
def create_multimedia_asset(
    request: CreateMultimediaDraftRequest,
    operator_id: str = Depends(authenticated_multimedia_operator),
) -> MultimediaAssetRecord:
    return get_store().create_draft(request, owner_id=operator_id)


@multimedia_router.get("/assets", response_model=MultimediaAssetList)
def list_multimedia_assets(
    operator_id: str = Depends(authenticated_multimedia_operator),
) -> MultimediaAssetList:
    return get_store().list_assets(owner_id=operator_id)


@multimedia_router.get("/assets/{asset_id}", response_model=MultimediaAssetRecord)
def get_multimedia_asset(
    asset_id: str,
    operator_id: str = Depends(authenticated_multimedia_operator),
) -> MultimediaAssetRecord:
    try:
        return get_store().get(asset_id, owner_id=operator_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="multimedia asset not found") from exc


@multimedia_router.post(
    "/assets/{asset_id}/evidence-search",
    response_model=MultimediaEvidenceSearchResult,
)
def search_multimedia_asset_evidence(
    asset_id: str,
    request: Request,
    payload: MultimediaEvidenceSearchRequest,
    operator_id: str = Depends(authenticated_multimedia_operator),
    runtime: MultimediaEvidenceRuntime = Depends(get_multimedia_evidence_runtime),
) -> MultimediaEvidenceSearchResult:
    try:
        record = get_store().get(asset_id, owner_id=operator_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="multimedia asset not found") from exc
    if record.asset.revision_id != payload.expected_revision_id:
        raise HTTPException(status_code=409, detail="multimedia evidence parent revision is stale")
    query = " ".join(
        part
        for part in (
            record.plan.request.topic,
            record.plan.request.source_scope or "",
            *record.plan.request.must_cover,
        )
        if part.strip()
    )
    query = " ".join(query.split())[:4096].rstrip()
    try:
        evidence = MultimediaGraphEvidence(
            db_path=runtime.db_path,
            embedding_provider=runtime.embedding_provider_factory(),
        )
        result = evidence.search(
            owner_id=operator_id,
            asset_id=asset_id,
            revision_id=record.asset.revision_id,
            query=query,
            limit=payload.limit,
            policy_tag=authenticated_multimedia_policy_tag(request),
        )
        current = get_store().get(asset_id, owner_id=operator_id)
    except (MultimediaGraphEvidenceUnavailable, OSError, RuntimeError) as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if current.asset.revision_id != payload.expected_revision_id:
        raise HTTPException(status_code=409, detail="multimedia evidence parent revision is stale")
    return result


@multimedia_router.post(
    "/assets/{asset_id}/grounded-drafts",
    response_model=MultimediaAssetRecord,
    status_code=201,
)
def create_grounded_multimedia_asset(
    asset_id: str,
    request: CreateGroundedMultimediaDraftRequest,
    operator_id: str = Depends(authenticated_multimedia_operator),
    runtime: MultimediaEvidenceRuntime = Depends(get_multimedia_evidence_runtime),
) -> MultimediaAssetRecord:
    try:
        evidence = MultimediaGraphEvidence(
            db_path=runtime.db_path,
            embedding_provider=runtime.embedding_provider_factory(),
        )
        chunks = evidence.resolve(request.selections, owner_id=operator_id)
        return get_store().create_grounded_draft(
            asset_id,
            expected_parent_revision_id=request.expected_parent_revision_id,
            evidence=chunks,
            owner_id=operator_id,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="multimedia asset not found") from exc
    except (MultimediaGraphEvidenceUnavailable, OSError, RuntimeError) as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@multimedia_router.get("/assets/{asset_id}/jobs", response_model=MultimediaJobList)
def list_multimedia_jobs(
    asset_id: str,
    operator_id: str = Depends(authenticated_multimedia_operator),
) -> MultimediaJobList:
    try:
        return get_store().list_jobs(asset_id, owner_id=operator_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="multimedia asset not found") from exc


@multimedia_router.post("/assets/{asset_id}/approve-dry-run", response_model=MultimediaAssetRecord)
def approve_multimedia_dry_run(
    asset_id: str,
    operator_id: str = Depends(authenticated_multimedia_operator),
    evidence_runtime: MultimediaEvidenceRuntime | None = Depends(
        get_multimedia_evidence_runtime_optional
    ),
) -> MultimediaAssetRecord:
    try:
        record = get_store().get(asset_id, owner_id=operator_id)
        canonical_ids = tuple(
            dict.fromkeys(
                span.chunk_id
                for line in record.plan.script_lines
                if line.evidence_derivation is not None
                for span in line.evidence_derivation.spans
                if span.authority_kind == "canonical_graph"
            )
        )
        canonical_chunks = (
            load_canonical_multimedia_chunks(
                evidence_runtime.db_path, canonical_ids, owner_id=operator_id
            )
            if canonical_ids and evidence_runtime is not None
            else None
        )
        return get_store().approve_dry_run(
            asset_id,
            owner_id=operator_id,
            canonical_chunks=canonical_chunks,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="multimedia asset not found") from exc
    except (MultimediaGraphEvidenceUnavailable, OSError, RuntimeError) as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@multimedia_router.post(
    "/assets/{asset_id}/steering-preview", response_model=SteeringPreviewResponse
)
def preview_multimedia_steering(
    asset_id: str,
    request: SteeringPreviewRequest,
    operator_id: str = Depends(authenticated_multimedia_operator),
) -> SteeringPreviewResponse:
    try:
        return get_store().preview_steering(asset_id, request, owner_id=operator_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="multimedia asset not found") from exc
    except SteeringPreviewConflict as exc:
        raise HTTPException(status_code=409, detail=exc.code) from exc


@multimedia_router.post("/assets/{asset_id}/steer", response_model=MultimediaAssetRecord)
def steer_multimedia_asset(
    asset_id: str,
    request: ApplySteeringPreviewRequest,
    operator_id: str = Depends(authenticated_multimedia_operator),
) -> MultimediaAssetRecord:
    try:
        return get_store().apply_steering_preview(asset_id, request, owner_id=operator_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="multimedia asset not found") from exc
    except SteeringPreviewConflict as exc:
        raise HTTPException(status_code=409, detail=exc.code) from exc


@multimedia_router.post("/assets/{asset_id}/hardening", response_model=MultimediaAssetRecord)
def run_multimedia_hardening(
    asset_id: str,
    operator_id: str = Depends(authenticated_multimedia_operator),
    runtime: MultimediaHardeningRuntime = Depends(get_multimedia_hardening_runtime),
    evidence_runtime: MultimediaEvidenceRuntime | None = Depends(
        get_multimedia_evidence_runtime_optional
    ),
) -> MultimediaAssetRecord:
    try:
        record = get_store().get(asset_id, owner_id=operator_id)
        canonical_ids = tuple(
            dict.fromkeys(
                span.chunk_id
                for line in record.plan.script_lines
                if line.evidence_derivation is not None
                for span in line.evidence_derivation.spans
                if span.authority_kind == "canonical_graph"
            )
        )
        canonical_chunks = (
            load_canonical_multimedia_chunks(
                evidence_runtime.db_path, canonical_ids, owner_id=operator_id
            )
            if canonical_ids and evidence_runtime is not None
            else None
        )
        now = runtime.clock()
        try:
            snapshot = build_multimedia_ship_cost_snapshot(
                db_path=runtime.db_path,
                signing_key=runtime.signing_key,
                snapshot_key=runtime.snapshot_key,
                owner_id=operator_id,
                asset_id=record.asset.asset_id,
                revision_id=record.asset.revision_id,
                now=now,
            )
        except MultimediaShipCostEvidenceConflict:
            raise
        except MultimediaShipCostEvidenceUnavailable:
            has_registered_media = (
                record.production_link is not None
                or record.audio_production_link is not None
            )
            if has_registered_media and str(record.asset.route_policy) != "cheapest":
                raise
            backend = (
                runtime.local_audio_backend
                if record.mode == "audio" or str(record.asset.kind) == "audio_experience"
                else runtime.local_video_backend
            )
            if backend is None or runtime.local_zero_snapshot_key is None:
                raise LocalZeroEvidenceUnavailable("evidence_unavailable") from None
            evidence = backend(
                owner_id=operator_id,
                asset_id=record.asset.asset_id,
                revision_id=record.asset.revision_id,
                now=now,
            )
            return get_store().run_hardening(
                asset_id,
                owner_id=operator_id,
                canonical_chunks=canonical_chunks,
                local_zero_cost_evidence=evidence,
                snapshot_key=runtime.local_zero_snapshot_key,
            )
        if record.audio_production_link is not None:
            raise MultimediaShipCostEvidenceUnavailable("evidence_unavailable")
        if record.production_link is not None:
            if (
                runtime.production_video_backend is None
                or runtime.production_snapshot_key is None
            ):
                raise MultimediaShipCostEvidenceUnavailable("evidence_unavailable")
            projection = runtime.production_video_backend(
                owner_id=operator_id,
                asset_id=record.asset.asset_id,
                revision_id=record.asset.revision_id,
                now=now,
            )
            authority = build_paid_registered_video_cost_authority(
                direct_cost_snapshot=snapshot,
                production_byte_projection=projection,
                direct_snapshot_key=runtime.snapshot_key,
                production_snapshot_key=runtime.production_snapshot_key,
                owner_id=operator_id,
                asset_id=record.asset.asset_id,
                revision_id=record.asset.revision_id,
                production_receipt_digest=record.production_link.receipt_sha256,
            )
            return get_store().run_hardening(
                asset_id,
                owner_id=operator_id,
                paid_registered_video_cost_authority=authority,
                snapshot_key=runtime.snapshot_key,
                production_snapshot_key=runtime.production_snapshot_key,
            )
        return get_store().run_hardening(
            asset_id,
            owner_id=operator_id,
            canonical_chunks=canonical_chunks,
            cost_snapshot=snapshot,
            snapshot_key=runtime.snapshot_key,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="multimedia asset not found") from exc
    except MultimediaShipCostEvidenceUnavailable as exc:
        raise HTTPException(status_code=409, detail=exc.code) from exc
    except LocalZeroEvidenceUnavailable as exc:
        raise HTTPException(status_code=409, detail=exc.code) from exc
    except (MultimediaGraphEvidenceUnavailable, OSError, RuntimeError) as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@multimedia_router.post(
    "/assets/{asset_id}/finalize-knowledge",
    response_model=MultimediaKnowledgeFinalizationResponse,
)
async def finalize_multimedia_asset_knowledge(
    asset_id: str,
    request: MultimediaKnowledgeFinalizationRequest,
    operator_id: str = Depends(authenticated_multimedia_operator),
    runtime: MultimediaKnowledgeRuntime = Depends(get_multimedia_knowledge_runtime),
) -> MultimediaKnowledgeFinalizationResponse:
    try:
        return await finalize_multimedia_knowledge(
            asset_id,
            request,
            owner_id=operator_id,
            store=get_store(),
            db_path=runtime.db_path,
            distiller_factory=runtime.distiller_factory,
            events_dir=runtime.events_dir,
            embedding_provider=runtime.embedding_provider,
        )
    except MultimediaKnowledgeFinalizationError as exc:
        status_code = 404 if str(exc) == "multimedia asset is unavailable" else 409
        raise HTTPException(status_code=status_code, detail=str(exc)) from exc


@multimedia_router.get(
    "/assets/{asset_id}/knowledge-twin",
    response_model=MultimediaTwinDocument,
)
def get_multimedia_asset_knowledge_twin(
    asset_id: str,
    operator_id: str = Depends(authenticated_multimedia_operator),
    runtime: MultimediaKnowledgeRuntime = Depends(get_multimedia_knowledge_runtime),
) -> MultimediaTwinDocument:
    try:
        return read_multimedia_twin_document(
            asset_id,
            owner_id=operator_id,
            store=get_store(),
            db_path=runtime.db_path,
        )
    except MultimediaKnowledgeFinalizationError as exc:
        status_code = 404 if str(exc) == "multimedia twin is unavailable" else 409
        raise HTTPException(status_code=status_code, detail=str(exc)) from exc


@multimedia_router.get(
    "/assets/{asset_id}/knowledge-finalization",
    response_model=MultimediaKnowledgeFinalizationStatus,
)
def get_multimedia_asset_knowledge_finalization(
    asset_id: str,
    operator_id: str = Depends(authenticated_multimedia_operator),
    runtime: MultimediaKnowledgeRuntime = Depends(get_multimedia_knowledge_runtime),
) -> MultimediaKnowledgeFinalizationStatus:
    try:
        return inspect_multimedia_knowledge_finalization(
            asset_id,
            owner_id=operator_id,
            store=get_store(),
            db_path=runtime.db_path,
        )
    except MultimediaKnowledgeFinalizationError as exc:
        status_code = 404 if str(exc) == "multimedia asset is unavailable" else 409
        raise HTTPException(status_code=status_code, detail=str(exc)) from exc


@multimedia_router.post(
    "/assets/{asset_id}/recover-knowledge-finalization",
    response_model=MultimediaKnowledgeFinalizationResponse,
)
async def recover_multimedia_asset_knowledge_finalization(
    asset_id: str,
    request: MultimediaKnowledgeRecoveryRequest,
    operator_id: str = Depends(authenticated_multimedia_operator),
    runtime: MultimediaKnowledgeRuntime = Depends(get_multimedia_knowledge_runtime),
) -> MultimediaKnowledgeFinalizationResponse:
    try:
        return await recover_multimedia_knowledge_finalization(
            asset_id,
            request,
            owner_id=operator_id,
            store=get_store(),
            db_path=runtime.db_path,
            distiller_factory=runtime.distiller_factory,
            events_dir=runtime.events_dir,
            embedding_provider=runtime.embedding_provider,
        )
    except MultimediaKnowledgeFinalizationError as exc:
        status_code = 404 if str(exc) == "multimedia asset is unavailable" else 409
        raise HTTPException(status_code=status_code, detail=str(exc)) from exc


def _resolve_research_audio_authority(
    *,
    store: MultimediaAssetStore,
    local_audible_runtime: MultimediaLocalAudibleRuntime | None,
    production_worker_runtime: AuthorizedProductionRuntime | None,
    asset_id: str,
    revision_id: str,
    operator_id: str,
) -> AudioPlaybackMetadata:
    try:
        record = store.get(asset_id, owner_id=operator_id)
    except (KeyError, ValueError) as exc:
        raise LookupError("research intent authority is unavailable") from exc
    if record.asset.revision_id != revision_id:
        raise ValueError("research intent revision is not current")
    link = record.audio_production_link
    if link is None or link.revision_id != revision_id or link.asset_id != asset_id:
        raise LookupError("research intent authority is unavailable")
    try:
        if record.asset.route_policy == "cheapest":
            if local_audible_runtime is None:
                raise LookupError("research intent authority is unavailable")
            metadata = local_audible_runtime.playback.metadata(
                asset_id=asset_id,
                revision_id=revision_id,
                owner_digest=link.owner_identity_digest,
                plan=record.plan,
            )
        else:
            if production_worker_runtime is None or production_worker_runtime.audio_playback is None:
                raise LookupError("research intent authority is unavailable")
            metadata = production_worker_runtime.audio_playback.metadata(
                asset_id=asset_id,
                revision_id=revision_id,
                owner_digest=link.owner_identity_digest,
            )
    except VerifiedPlaybackError as exc:
        raise LookupError("research intent authority is unavailable") from exc
    if (
        metadata.receipt_sha256 != link.receipt_sha256
        or metadata.audio_sha256 != link.audio_sha256
        or metadata.audio_size_bytes != link.audio_size_bytes
        or metadata.duration_seconds != link.duration_seconds
        or metadata.chapter_ids != link.chapter_ids
        or metadata.retention_marker_count != link.retention_marker_count
        or metadata.learned_claim_count != link.learned_claim_count
        or metadata.source_count != link.source_count
    ):
        raise ValueError("research intent audio registration conflicts")
    return metadata


def register_multimedia_routes(app: FastAPI) -> None:
    legacy_owner = os.environ.get("ANTIEK_MULTIMEDIA_LEGACY_OWNER_ID", "").strip()
    if legacy_owner:
        get_store().migrate_legacy_assets(owner_id=legacy_owner)
    app.include_router(multimedia_router)
    runtime = multimedia_reconciliation_runtime_from_environment()
    if runtime is not None:
        runtime = replace(
            runtime,
            asset_revision_resolver=lambda asset_id, operator_id: (
                get_store().get(asset_id, owner_id=operator_id).asset.revision_id
            ),
        )
        app.dependency_overrides[get_multimedia_reconciliation_runtime] = lambda: runtime
    knowledge_runtime = multimedia_knowledge_runtime_from_environment()
    if knowledge_runtime is not None:
        app.dependency_overrides[get_multimedia_knowledge_runtime] = lambda: knowledge_runtime
    evidence_runtime = multimedia_evidence_runtime_from_environment()
    if evidence_runtime is not None:
        app.dependency_overrides[get_multimedia_evidence_runtime] = lambda: evidence_runtime
        app.dependency_overrides[get_multimedia_evidence_runtime_optional] = lambda: (
            evidence_runtime
        )
    local_runtime = multimedia_local_runtime_from_environment(store=get_store())
    if local_runtime is not None:
        app.dependency_overrides[get_multimedia_local_runtime_optional] = lambda: local_runtime
        app.dependency_overrides[get_multimedia_local_runtime] = lambda: local_runtime
    local_audible_runtime = multimedia_local_audible_runtime_from_environment(store=get_store())
    if local_audible_runtime is not None:
        app.dependency_overrides[get_multimedia_local_audible_runtime_optional] = lambda: (
            local_audible_runtime
        )
        app.dependency_overrides[get_multimedia_local_audible_runtime] = lambda: (
            local_audible_runtime
        )
    production_worker_runtime = multimedia_production_worker_runtime_from_environment(
        store=get_store()
    )
    if production_worker_runtime is not None:
        app.dependency_overrides[get_multimedia_production_worker_runtime] = (
            lambda: production_worker_runtime
        )
    hardening_runtime = multimedia_hardening_runtime_from_environment()
    if hardening_runtime is not None:
        local_zero_key = hardening_runtime.local_zero_snapshot_key
        hardening_db_path = hardening_runtime.db_path
        video_coordinator = (
            cast(LocalVideoProductionCoordinator, local_runtime.video)
            if local_runtime is not None and local_zero_key is not None
            else None
        )
        audio_coordinator = (
            cast(LocalAudibleCoordinator, local_audible_runtime.workstation.production)
            if local_audible_runtime is not None and local_zero_key is not None
            else None
        )
        production_snapshot_key = hardening_runtime.production_snapshot_key
        if production_worker_runtime is not None and production_snapshot_key is not None:
            if (
                production_worker_runtime.db_path != hardening_runtime.db_path
                or production_worker_runtime.signing_key != hardening_runtime.signing_key
            ):
                raise RuntimeError(
                    "multimedia hardening and production accounting authorities conflict"
                )
            if production_snapshot_key in {
                production_worker_runtime.signing_key,
                production_worker_runtime.narration_integrity_key,
                production_worker_runtime.visual_integrity_key,
                production_worker_runtime.evidence_authority_key,
                production_worker_runtime.render_integrity_key,
                production_worker_runtime.receipt_key,
            }:
                raise RuntimeError(
                    "multimedia hardening signing keys must be independent"
                )
            production_worker_runtime.reviewed_visual_registry.assert_independent_snapshot_key(
                production_snapshot_key
            )
        if video_coordinator is not None:
            assert local_zero_key is not None
            video_coordinator.assert_independent_snapshot_key(local_zero_key)
        if audio_coordinator is not None:
            assert local_zero_key is not None
            audio_coordinator.assert_independent_snapshot_key(local_zero_key)

        def video_backend(
            *, owner_id: str, asset_id: str, revision_id: str, now: datetime
        ) -> LocalZeroExternalCostEvidenceV1:
            if video_coordinator is None or local_zero_key is None:
                raise RuntimeError("local video evidence backend is unavailable")
            return build_local_video_zero_cost_evidence(
                coordinator=video_coordinator,
                db_path=hardening_db_path,
                snapshot_key=local_zero_key,
                owner_id=owner_id,
                asset_id=asset_id,
                revision_id=revision_id,
                now=now,
            )

        def audio_backend(
            *, owner_id: str, asset_id: str, revision_id: str, now: datetime
        ) -> LocalZeroExternalCostEvidenceV1:
            if audio_coordinator is None or local_zero_key is None:
                raise RuntimeError("local audio evidence backend is unavailable")
            return build_local_audio_zero_cost_evidence(
                coordinator=audio_coordinator,
                db_path=hardening_db_path,
                snapshot_key=local_zero_key,
                owner_id=owner_id,
                asset_id=asset_id,
                revision_id=revision_id,
                now=now,
            )

        def production_video_backend(
            *, owner_id: str, asset_id: str, revision_id: str, now: datetime
        ) -> ProductionByteProjectionV1:
            if production_worker_runtime is None or production_snapshot_key is None:
                raise RuntimeError("production byte evidence backend is unavailable")
            closure = build_production_byte_cost_closure(
                asset_id=asset_id,
                owner_id=owner_id,
                db_path=production_worker_runtime.db_path,
                store=production_worker_runtime.store,
                playback=production_worker_runtime.playback,
                registry=production_worker_runtime.reviewed_visual_registry,
                signing_key=production_worker_runtime.signing_key,
                snapshot_key=production_snapshot_key,
                narration_key=production_worker_runtime.narration_integrity_key,
                now=now,
            )
            if closure.production_byte_projection.revision_id != revision_id:
                raise MultimediaShipCostEvidenceConflict("evidence_conflict")
            return closure.production_byte_projection

        hardening_runtime = replace(
            hardening_runtime,
            local_video_backend=video_backend if video_coordinator is not None else None,
            local_audio_backend=audio_backend if audio_coordinator is not None else None,
            production_video_backend=(
                production_video_backend
                if production_worker_runtime is not None
                and production_snapshot_key is not None
                else None
            ),
        )
        app.dependency_overrides[get_multimedia_hardening_runtime] = lambda: hardening_runtime
    playback_runtime = multimedia_playback_runtime_from_environment()
    if playback_runtime is not None:
        playback = playback_runtime.playback
        playback_runtime = replace(
            playback_runtime,
            asset_authority_resolver=lambda asset_id, operator_id: (
                (record := get_store().get(asset_id, owner_id=operator_id)).asset.revision_id,
                record.production_link,
            ),
            production_registrar=lambda asset_id, revision_id, operator_id: (
                register_multimedia_production(
                    asset_id,
                    MultimediaProductionRegistrationRequest(expected_revision_id=revision_id),
                    owner_id=operator_id,
                    store=get_store(),
                    playback=playback,
                )
            ),
        )
        app.dependency_overrides[get_multimedia_playback_runtime] = lambda: playback_runtime
    narration_runtime = multimedia_narration_authorization_runtime_from_environment(
        store=get_store()
    )
    if narration_runtime is not None:
        app.dependency_overrides[get_multimedia_narration_authorization_runtime] = lambda: (
            narration_runtime
        )
    reviewed_visual_runtime = multimedia_reviewed_visual_runtime_from_environment(store=get_store())
    if reviewed_visual_runtime is not None:
        app.dependency_overrides[get_multimedia_reviewed_visual_runtime] = lambda: (
            reviewed_visual_runtime
        )
    if (
        production_worker_runtime is not None
        and production_worker_runtime.audio_playback is not None
    ):
        paid_audio_runtime = PaidAudioPlaybackRouteRuntime(
            playback=production_worker_runtime.audio_playback,
            asset_authority_resolver=lambda asset_id, operator_id: (
                (record := get_store().get(asset_id, owner_id=operator_id)).asset.revision_id,
                record.audio_production_link,
            ),
        )
        app.dependency_overrides[get_multimedia_paid_audio_playback_runtime] = lambda: (
            paid_audio_runtime
        )
    def _owner_digest(operator_id: str) -> str:
        encoded = operator_id.strip().encode("utf-8")
        if not encoded or len(encoded) > 512 or any(byte < 32 or byte == 127 for byte in encoded):
            raise ValueError("multimedia owner identity is invalid")
        return hashlib.sha256(encoded).hexdigest()

    def _resolve_research_audio(
        asset_id: str, revision_id: str, operator_id: str
    ) -> AudioPlaybackMetadata:
        return _resolve_research_audio_authority(
            store=get_store(),
            local_audible_runtime=local_audible_runtime,
            production_worker_runtime=production_worker_runtime,
            asset_id=asset_id,
            revision_id=revision_id,
            operator_id=operator_id,
        )

    if local_audible_runtime is not None or (
        production_worker_runtime is not None
        and production_worker_runtime.audio_playback is not None
    ):
        research_intent_runtime = ResearchIntentRouteRuntime(
            ledger=ResearchIntentLedger(get_store().root),
            owner_digest_resolver=_owner_digest,
            audio_authority_resolver=_resolve_research_audio,
        )
        app.dependency_overrides[get_multimedia_research_intent_runtime] = lambda: (
            research_intent_runtime
        )
        research_plan_runtime = ResearchPlanRouteRuntime(
            plans=ResearchPlanLedger(get_store().root),
            intents=research_intent_runtime.ledger,
            owner_digest_resolver=_owner_digest,
            activation_quote_resolver=_production_activation_quote_resolver(),
        )
        app.dependency_overrides[get_multimedia_research_plan_runtime] = lambda: (
            research_plan_runtime
        )
    # Listening progress: resolve audio identity from the store's audio_production_link
    # or the local audible playback runtime.  Both local and paid audio use the same
    # progress contract and store.
    def _resolve_audio_identity(asset_id: str, operator_id: str) -> AudioIdentity:
        record = get_store().get(asset_id, owner_id=operator_id)
        if str(record.asset.kind) != "audio_experience" or record.mode != "audio":
            raise ListeningProgressError("listening_progress_not_audio_asset")
        link = record.audio_production_link
        if link is None:
            raise LookupError("listening progress audio identity unavailable")
        return AudioIdentity(
            revision_id=link.revision_id,
            audio_sha256=link.audio_sha256,
            duration_seconds=link.duration_seconds,
            kind=str(record.asset.kind),
            mode=record.mode,
        )
    # Always available — the store is always present; the audio_identity_resolver
    # raises LookupError when the asset has no registered audio.
    _lp_store = ListeningProgressStore(get_store().root)
    lp_runtime = listening_progress_runtime(
        store=_lp_store,
        audio_identity_resolver=_resolve_audio_identity,
    )
    app.dependency_overrides[get_listening_progress_runtime] = lambda: lp_runtime
    tts_gateway_runtime = multimedia_tts_gateway_runtime_from_environment()
    if tts_gateway_runtime is not None:
        app.dependency_overrides[get_multimedia_tts_gateway_runtime] = lambda: tts_gateway_runtime
    visual_authorization_runtime = multimedia_visual_authorization_runtime_from_environment(
        store=get_store()
    )
    if visual_authorization_runtime is not None:
        app.dependency_overrides[get_multimedia_visual_authorization_runtime] = lambda: (
            visual_authorization_runtime
        )
    visual_generation_runtime = multimedia_visual_generation_runtime_from_environment(
        store=get_store()
    )
    if visual_generation_runtime is not None:
        app.dependency_overrides[get_multimedia_visual_generation_runtime] = lambda: (
            visual_generation_runtime
        )
    visual_candidate_runtime = multimedia_visual_candidate_runtime_from_environment(
        store=get_store()
    )
    if visual_candidate_runtime is not None:
        app.dependency_overrides[get_multimedia_visual_candidate_runtime] = lambda: (
            visual_candidate_runtime
        )
    visual_review_runtime = multimedia_visual_review_runtime_from_environment(store=get_store())
    if visual_review_runtime is not None:
        app.dependency_overrides[get_multimedia_visual_review_runtime] = lambda: (
            visual_review_runtime
        )
    visual_quality_runtime = multimedia_visual_quality_runtime_from_environment(
        store=get_store(), generation_runtime=visual_generation_runtime
    )
    if visual_quality_runtime is not None:
        app.dependency_overrides[get_multimedia_visual_quality_runtime] = lambda: (
            visual_quality_runtime
        )


__all__ = [
    "MultimediaKnowledgeRuntime",
    "get_multimedia_knowledge_runtime",
    "get_store",
    "multimedia_knowledge_runtime_from_environment",
    "multimedia_router",
    "register_multimedia_routes",
]
