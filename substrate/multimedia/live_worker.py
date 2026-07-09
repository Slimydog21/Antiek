"""No-spend worker preview for queued multimedia live execution.

This module deliberately stops short of provider execution. It consumes the
queued handoff plan, resolves the same deterministic route/cost preview the
future worker would use, and appends an audit row. Krea/network calls remain
outside this path.
"""

from __future__ import annotations

from substrate.contracts.multimedia import AssetKind
from substrate.multimedia.provider_router import (
    BudgetExceeded,
    GenerationKind,
    MediaGenerationRequest,
    route_media_request,
)
from substrate.multimedia.read_model import (
    LiveProviderArtifactReceipt,
    LiveProviderExecutionPlan,
    LiveProviderRoutePreview,
    MultimediaAssetRecord,
    MultimediaAssetStore,
    MultimediaJobRecord,
)


def record_provider_artifact_receipt(
    store: MultimediaAssetStore,
    asset_id: str,
    receipt: LiveProviderArtifactReceipt,
) -> MultimediaAssetRecord:
    """Append a no-spend provider artifact receipt from polling/webhook data."""

    record = store.get(asset_id)
    plan = _latest_execution_plan(record)
    if plan is None:
        return store.record_job(
            asset_id,
            kind="provider_execution",
            status="failed",
            progress_percent=0,
            message="No live execution plan is available for provider artifact receipt.",
            error_code="live_execution_plan_missing",
            retryable=False,
            artifact_receipt=receipt,
        )
    if plan.asset_id != record.asset.asset_id or plan.revision_id != record.asset.revision_id:
        return store.record_job(
            asset_id,
            kind="provider_execution",
            status="failed",
            progress_percent=0,
            message="Provider artifact receipt does not match the current asset revision.",
            error_code="live_execution_plan_stale",
            retryable=False,
            execution_plan=plan,
            artifact_receipt=receipt,
        )
    normalized_provider = receipt.provider.strip().lower()
    if normalized_provider not in plan.provider_families:
        return store.record_job(
            asset_id,
            kind="provider_execution",
            status="failed",
            progress_percent=0,
            message="Provider artifact receipt came from a provider outside the approved execution plan.",
            error_code="provider_family_mismatch",
            retryable=False,
            execution_plan=plan,
            artifact_receipt=receipt,
        )

    if receipt.status == "failed":
        return store.record_job(
            asset_id,
            kind="provider_execution",
            status="failed",
            progress_percent=70,
            message=receipt.message or f"Provider job {receipt.provider_job_id} failed.",
            error_code=receipt.error_code,
            retryable=True,
            execution_plan=plan,
            artifact_receipt=receipt,
        )

    progress = 80 if receipt.status == "succeeded" else 45
    message = receipt.message or f"Provider job {receipt.provider_job_id} reported {receipt.status}."
    return store.record_job(
        asset_id,
        kind="provider_execution",
        status="partial",
        progress_percent=progress,
        message=message,
        retryable=True,
        execution_plan=plan,
        artifact_receipt=receipt,
    )


def preview_next_live_execution(store: MultimediaAssetStore, asset_id: str) -> MultimediaAssetRecord:
    """Append a no-spend route preview for the latest queued live job."""

    record = store.get(asset_id)
    queued = _latest_queued_execution(record)
    if queued is None or queued.execution_plan is None:
        return store.record_job(
            asset_id,
            kind="provider_execution",
            status="failed",
            progress_percent=0,
            message="No queued live execution plan is available for worker preview.",
            error_code="live_execution_plan_missing",
            retryable=False,
        )

    plan = queued.execution_plan
    if plan.asset_id != record.asset.asset_id or plan.revision_id != record.asset.revision_id:
        return store.record_job(
            asset_id,
            kind="provider_execution",
            status="failed",
            progress_percent=0,
            message="Queued live execution plan is stale for the current asset revision.",
            error_code="live_execution_plan_stale",
            retryable=False,
            execution_plan=plan,
        )
    if plan.route_policy != record.asset.route_policy:
        return store.record_job(
            asset_id,
            kind="provider_execution",
            status="failed",
            progress_percent=0,
            message="Queued live execution plan route no longer matches the current asset.",
            error_code="live_execution_route_mismatch",
            retryable=False,
            execution_plan=plan,
        )

    request = _media_request_from_plan(record, plan)
    try:
        route = route_media_request(request)
    except BudgetExceeded as exc:
        return store.record_job(
            asset_id,
            kind="provider_execution",
            status="failed",
            progress_percent=0,
            message=str(exc),
            error_code=exc.code,
            retryable=False,
            execution_plan=plan,
        )

    preview = LiveProviderRoutePreview(
        provider=route.provider,
        model=route.model,
        route_policy=route.route_policy,
        quality_label=route.quality_label,
        estimated_cost_usd=route.estimated_cost_usd,
        resolution=route.resolution,
        duration_seconds=route.duration_seconds,
        status=route.status,
        reason=route.reason,
    )
    return store.record_job(
        asset_id,
        kind="provider_execution",
        status="partial",
        progress_percent=10,
        message=(
            "No-spend worker preview resolved "
            f"{route.provider}/{route.model} at ${route.estimated_cost_usd:.4f}."
        ),
        retryable=True,
        execution_plan=plan,
        route_preview=preview,
    )


def _latest_queued_execution(record: MultimediaAssetRecord) -> MultimediaJobRecord | None:
    for job in reversed(record.jobs):
        if job.kind == "provider_execution" and job.status == "queued" and job.execution_plan:
            return job
    return None


def _latest_execution_plan(record: MultimediaAssetRecord) -> LiveProviderExecutionPlan | None:
    for job in reversed(record.jobs):
        if job.kind == "provider_execution" and job.execution_plan:
            return job.execution_plan
    return None


def _media_request_from_plan(
    record: MultimediaAssetRecord,
    plan: LiveProviderExecutionPlan,
) -> MediaGenerationRequest:
    kind = _primary_generation_kind(record.asset.kind)
    duration_seconds = None
    if kind in {"image_to_video", "video"}:
        duration_seconds = float(record.asset.requested_duration_minutes * 60)
    return MediaGenerationRequest(
        kind=kind,
        prompt=record.asset.user_prompt,
        route_policy=plan.route_policy,
        duration_seconds=duration_seconds,
        budget_usd=plan.max_budget_usd,
        dry_run=True,
    )


def _primary_generation_kind(kind: AssetKind) -> GenerationKind:
    if kind == "audio_experience":
        return "image"
    return "video"


__all__ = ["preview_next_live_execution", "record_provider_artifact_receipt"]
