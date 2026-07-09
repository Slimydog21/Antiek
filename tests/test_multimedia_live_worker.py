"""No-spend multimedia live-worker preview tests."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from substrate.contracts.multimedia import GeneratedFile
from substrate.multimedia.live_worker import (
    preview_next_live_execution,
    record_provider_artifact_receipt,
)
from substrate.multimedia.read_model import (
    CreateMultimediaDraftRequest,
    LiveProviderArtifactReceipt,
    LiveProviderExecutionRequest,
    MultimediaAssetStore,
)

SHA = "e" * 64


def test_live_worker_preview_consumes_queued_plan_without_provider_call(tmp_path, monkeypatch):
    monkeypatch.setenv("KREA_API_KEY", "presence-only-not-a-real-secret")
    store = MultimediaAssetStore(tmp_path)
    draft = store.create_draft(
        CreateMultimediaDraftRequest(
            topic="Asianometry style history of fly-by-wire aircraft",
            target_minutes=20,
            mode="video",
            route_policy="balanced",
            sources=("Digital flight controls changed aircraft design and safety cases.",),
        )
    )
    store.approve_dry_run(draft.asset.asset_id)
    queued = store.prepare_live_execution(
        draft.asset.asset_id,
        LiveProviderExecutionRequest(
            max_budget_usd=100,
            route_policy="balanced",
            operator_acknowledged_spend=True,
            dry_run_revision_id=draft.asset.revision_id,
        ),
    )

    previewed = preview_next_live_execution(store, draft.asset.asset_id)
    job = previewed.jobs[-1]

    assert queued.jobs[-1].status == "queued"
    assert job.status == "partial"
    assert job.progress_percent == 10
    assert job.execution_plan == queued.jobs[-1].execution_plan
    assert job.route_preview is not None
    assert job.route_preview.provider == "krea"
    assert job.route_preview.model == "krea-video-standard"
    assert job.route_preview.route_policy == "balanced"
    assert job.route_preview.status == "dry_run"
    assert job.route_preview.duration_seconds == 1200
    assert job.route_preview.estimated_cost_usd == 72

    reloaded = MultimediaAssetStore(tmp_path).list_jobs(draft.asset.asset_id)
    assert reloaded.jobs[-1].route_preview == job.route_preview
    for row in reloaded.jobs:
        assert "presence-only-not-a-real-secret" not in row.model_dump_json()


def test_live_worker_preview_fails_without_queued_plan(tmp_path):
    store = MultimediaAssetStore(tmp_path)
    draft = store.create_draft(
        CreateMultimediaDraftRequest(
            topic="history of variable sweep wings",
            target_minutes=20,
            mode="video",
            route_policy="balanced",
        )
    )

    previewed = preview_next_live_execution(store, draft.asset.asset_id)

    assert previewed.jobs[-1].status == "failed"
    assert previewed.jobs[-1].error_code == "live_execution_plan_missing"
    assert previewed.jobs[-1].retryable is False
    assert previewed.jobs[-1].route_preview is None


def test_live_worker_preview_respects_route_budget_ceiling(tmp_path, monkeypatch):
    monkeypatch.setenv("KREA_API_KEY", "presence-only-not-a-real-secret")
    store = MultimediaAssetStore(tmp_path)
    draft = store.create_draft(
        CreateMultimediaDraftRequest(
            topic="Ken Burns documentary on the Concorde program",
            target_minutes=20,
            mode="video",
            route_policy="highest_quality",
            sources=("Supersonic transport economics depended on fuel, noise, and routes.",),
        )
    )
    store.approve_dry_run(draft.asset.asset_id)
    queued = store.prepare_live_execution(
        draft.asset.asset_id,
        LiveProviderExecutionRequest(
            max_budget_usd=25,
            route_policy="highest_quality",
            operator_acknowledged_spend=True,
            dry_run_revision_id=draft.asset.revision_id,
        ),
    )
    assert queued.jobs[-1].status == "queued"

    previewed = preview_next_live_execution(store, draft.asset.asset_id)

    assert previewed.jobs[-1].status == "failed"
    assert previewed.jobs[-1].error_code == "budget_exceeded"
    assert previewed.jobs[-1].retryable is False
    assert previewed.jobs[-1].execution_plan == queued.jobs[-1].execution_plan
    assert previewed.jobs[-1].route_preview is None


def test_provider_artifact_receipt_records_progress_without_manifest_attachment(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setenv("KREA_API_KEY", "presence-only-not-a-real-secret")
    store = MultimediaAssetStore(tmp_path)
    draft = store.create_draft(
        CreateMultimediaDraftRequest(
            topic="documentary on composite airframes",
            target_minutes=20,
            mode="video",
            route_policy="balanced",
            sources=("Composite materials changed fatigue, maintenance, and weight tradeoffs.",),
        )
    )
    approved = store.approve_dry_run(draft.asset.asset_id)
    queued = store.prepare_live_execution(
        draft.asset.asset_id,
        LiveProviderExecutionRequest(
            max_budget_usd=100,
            route_policy="balanced",
            operator_acknowledged_spend=True,
            dry_run_revision_id=draft.asset.revision_id,
        ),
    )
    preview_next_live_execution(store, draft.asset.asset_id)
    receipt = LiveProviderArtifactReceipt(
        provider_job_id="krea-job-1",
        provider="krea",
        status="succeeded",
        files=(
            GeneratedFile(
                file_id="krea-file-1",
                kind="video",
                storage_uri="s3://antiek/multimedia/krea-file-1.mp4",
                sha256=SHA,
                mime="video/mp4",
                provider="krea",
                duration_seconds=1200,
                width_px=1280,
                height_px=720,
            ),
        ),
    )

    recorded = record_provider_artifact_receipt(store, draft.asset.asset_id, receipt)
    job = recorded.jobs[-1]

    assert job.status == "partial"
    assert job.progress_percent == 80
    assert job.execution_plan == queued.jobs[-1].execution_plan
    assert job.artifact_receipt == receipt
    assert job.artifact_receipt.files[0].sha256 == SHA
    assert recorded.asset.manifest.files == approved.asset.manifest.files

    reloaded = MultimediaAssetStore(tmp_path).list_jobs(draft.asset.asset_id)
    assert reloaded.jobs[-1].artifact_receipt == receipt
    for row in reloaded.jobs:
        assert "presence-only-not-a-real-secret" not in row.model_dump_json()


def test_provider_artifact_receipt_rejects_provider_outside_plan(tmp_path, monkeypatch):
    monkeypatch.setenv("KREA_API_KEY", "presence-only-not-a-real-secret")
    store = MultimediaAssetStore(tmp_path)
    draft = store.create_draft(
        CreateMultimediaDraftRequest(
            topic="documentary on aircraft certification",
            target_minutes=20,
            mode="video",
            route_policy="balanced",
        )
    )
    store.approve_dry_run(draft.asset.asset_id)
    queued = store.prepare_live_execution(
        draft.asset.asset_id,
        LiveProviderExecutionRequest(
            max_budget_usd=100,
            route_policy="balanced",
            operator_acknowledged_spend=True,
            dry_run_revision_id=draft.asset.revision_id,
        ),
    )
    receipt = LiveProviderArtifactReceipt(
        provider_job_id="other-job-1",
        provider="other",
        status="running",
    )

    recorded = record_provider_artifact_receipt(store, draft.asset.asset_id, receipt)

    assert recorded.jobs[-1].status == "failed"
    assert recorded.jobs[-1].error_code == "provider_family_mismatch"
    assert recorded.jobs[-1].execution_plan == queued.jobs[-1].execution_plan
    assert recorded.jobs[-1].artifact_receipt == receipt


@pytest.mark.parametrize(
    "receipt_kwargs, message",
    [
        (
            {"provider_job_id": "job-1", "provider": "krea", "status": "succeeded"},
            "succeeded artifact receipts require at least one generated file",
        ),
        (
            {"provider_job_id": "job-1", "provider": "krea", "status": "failed"},
            "failed artifact receipts require error_code",
        ),
        (
            {"provider_job_id": "job-1", "provider": "secret-token-value", "status": "running"},
            "provider must name a provider",
        ),
    ],
)
def test_provider_artifact_receipt_validation(receipt_kwargs, message):
    with pytest.raises(ValidationError, match=message):
        LiveProviderArtifactReceipt(**receipt_kwargs)
