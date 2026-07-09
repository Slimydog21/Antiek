"""No-spend multimedia live-worker preview tests."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from substrate.contracts.multimedia import GeneratedFile
from substrate.multimedia.hardening import (
    GateFinding,
    GateResult,
    MultimediaHardeningReport,
)
from substrate.multimedia.live_worker import (
    attach_provider_artifacts_to_manifest,
    evaluate_public_export_gate,
    plan_provider_artifact_attachment,
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


def test_provider_artifact_attachment_plan_validates_receipt_without_manifest_mutation(
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
    previewed = preview_next_live_execution(store, draft.asset.asset_id)
    route_preview = previewed.jobs[-1].route_preview
    assert route_preview is not None
    receipt = LiveProviderArtifactReceipt(
        provider_job_id="krea-job-2",
        provider="krea",
        status="succeeded",
        files=(
            GeneratedFile(
                file_id="krea-file-2",
                kind="video",
                storage_uri="s3://antiek/multimedia/krea-file-2.mp4",
                sha256=SHA,
                mime="video/mp4",
                provider="krea",
                duration_seconds=route_preview.duration_seconds,
                width_px=route_preview.resolution[0] if route_preview.resolution else None,
                height_px=route_preview.resolution[1] if route_preview.resolution else None,
            ),
        ),
    )
    recorded = record_provider_artifact_receipt(store, draft.asset.asset_id, receipt)

    planned = plan_provider_artifact_attachment(store, draft.asset.asset_id)
    job = planned.jobs[-1]

    assert job.status == "partial"
    assert job.progress_percent == 90
    assert job.execution_plan == queued.jobs[-1].execution_plan
    assert job.route_preview == route_preview
    assert job.artifact_receipt == recorded.jobs[-1].artifact_receipt
    assert job.attachment_plan is not None
    assert job.attachment_plan.provider_job_id == "krea-job-2"
    assert job.attachment_plan.route_model == "krea-video-standard"
    assert job.attachment_plan.manifest_revision_id == draft.asset.revision_id
    assert job.attachment_plan.files == receipt.files
    assert planned.asset.manifest.files == approved.asset.manifest.files

    reloaded = MultimediaAssetStore(tmp_path).list_jobs(draft.asset.asset_id)
    assert reloaded.jobs[-1].attachment_plan == job.attachment_plan


def test_attach_provider_artifacts_to_manifest_after_validated_plan(tmp_path, monkeypatch):
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
    store.prepare_live_execution(
        draft.asset.asset_id,
        LiveProviderExecutionRequest(
            max_budget_usd=100,
            route_policy="balanced",
            operator_acknowledged_spend=True,
            dry_run_revision_id=draft.asset.revision_id,
        ),
    )
    previewed = preview_next_live_execution(store, draft.asset.asset_id)
    route_preview = previewed.jobs[-1].route_preview
    assert route_preview is not None
    provider_file = GeneratedFile(
        file_id="krea-file-attach",
        kind="video",
        storage_uri="s3://antiek/multimedia/krea-file-attach.mp4",
        sha256=SHA,
        mime="video/mp4",
        provider="krea",
        duration_seconds=route_preview.duration_seconds,
        width_px=route_preview.resolution[0] if route_preview.resolution else None,
        height_px=route_preview.resolution[1] if route_preview.resolution else None,
    )
    record_provider_artifact_receipt(
        store,
        draft.asset.asset_id,
        LiveProviderArtifactReceipt(
            provider_job_id="krea-job-attach",
            provider="krea",
            status="succeeded",
            files=(provider_file,),
        ),
    )
    planned = plan_provider_artifact_attachment(store, draft.asset.asset_id)
    attachment_plan = planned.jobs[-1].attachment_plan
    assert attachment_plan is not None

    attached = attach_provider_artifacts_to_manifest(store, draft.asset.asset_id)
    job = attached.jobs[-1]

    assert job.status == "succeeded"
    assert job.progress_percent == 100
    assert job.attachment_plan == attachment_plan
    assert attached.asset.manifest.files == approved.asset.manifest.files + (provider_file,)
    assert attached.asset.manifest.files[-1].storage_uri == "s3://antiek/multimedia/krea-file-attach.mp4"

    reloaded = MultimediaAssetStore(tmp_path).get(draft.asset.asset_id)
    assert reloaded.asset.manifest.files[-1] == provider_file
    assert reloaded.jobs[-1].status == "succeeded"
    for row in reloaded.jobs:
        assert "presence-only-not-a-real-secret" not in row.model_dump_json()


def test_attach_provider_artifacts_to_manifest_requires_attachment_plan(tmp_path):
    store = MultimediaAssetStore(tmp_path)
    draft = store.create_draft(
        CreateMultimediaDraftRequest(
            topic="documentary on inertial navigation",
            target_minutes=20,
            mode="video",
            route_policy="balanced",
        )
    )

    attached = attach_provider_artifacts_to_manifest(store, draft.asset.asset_id)

    assert attached.jobs[-1].status == "failed"
    assert attached.jobs[-1].error_code == "artifact_attachment_plan_missing"
    assert attached.jobs[-1].attachment_plan is None


def test_attach_provider_artifacts_to_manifest_rejects_duplicate_file_ids(tmp_path, monkeypatch):
    monkeypatch.setenv("KREA_API_KEY", "presence-only-not-a-real-secret")
    store = MultimediaAssetStore(tmp_path)
    draft = store.create_draft(
        CreateMultimediaDraftRequest(
            topic="documentary on cockpit voice recorders",
            target_minutes=20,
            mode="video",
            route_policy="balanced",
        )
    )
    approved = store.approve_dry_run(draft.asset.asset_id)
    existing_file = approved.asset.manifest.files[0]
    store.prepare_live_execution(
        draft.asset.asset_id,
        LiveProviderExecutionRequest(
            max_budget_usd=100,
            route_policy="balanced",
            operator_acknowledged_spend=True,
            dry_run_revision_id=draft.asset.revision_id,
        ),
    )
    previewed = preview_next_live_execution(store, draft.asset.asset_id)
    route_preview = previewed.jobs[-1].route_preview
    assert route_preview is not None
    duplicate_file = existing_file.model_copy(
        update={
            "provider": "krea",
            "duration_seconds": route_preview.duration_seconds,
            "width_px": route_preview.resolution[0] if route_preview.resolution else None,
            "height_px": route_preview.resolution[1] if route_preview.resolution else None,
        }
    )
    record_provider_artifact_receipt(
        store,
        draft.asset.asset_id,
        LiveProviderArtifactReceipt(
            provider_job_id="krea-job-duplicate",
            provider="krea",
            status="succeeded",
            files=(duplicate_file,),
        ),
    )
    planned = plan_provider_artifact_attachment(store, draft.asset.asset_id)
    assert planned.jobs[-1].attachment_plan is not None

    attached = attach_provider_artifacts_to_manifest(store, draft.asset.asset_id)

    assert attached.jobs[-1].status == "failed"
    assert attached.jobs[-1].error_code == "artifact_file_duplicate"
    assert attached.asset.manifest.files == approved.asset.manifest.files


def test_public_export_gate_blocks_without_attached_files(tmp_path):
    store = MultimediaAssetStore(tmp_path)
    draft = store.create_draft(
        CreateMultimediaDraftRequest(
            topic="documentary on VOR navigation",
            target_minutes=20,
            mode="video",
            route_policy="balanced",
        )
    )

    gated = evaluate_public_export_gate(store, draft.asset.asset_id)
    job = gated.jobs[-1]

    assert job.kind == "export_gate"
    assert job.status == "failed"
    assert job.error_code == "public_export_no_attached_files"
    assert job.public_export_gate is not None
    assert job.public_export_gate.status == "blocked"
    assert job.public_export_gate.public_export_enabled is False
    assert job.public_export_gate.required_gate_ids == ("provider_artifact_attachment",)


def test_public_export_gate_requires_manual_review_after_attachment(tmp_path, monkeypatch):
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
    store.approve_dry_run(draft.asset.asset_id)
    store.prepare_live_execution(
        draft.asset.asset_id,
        LiveProviderExecutionRequest(
            max_budget_usd=100,
            route_policy="balanced",
            operator_acknowledged_spend=True,
            dry_run_revision_id=draft.asset.revision_id,
        ),
    )
    previewed = preview_next_live_execution(store, draft.asset.asset_id)
    route_preview = previewed.jobs[-1].route_preview
    assert route_preview is not None
    provider_file = GeneratedFile(
        file_id="krea-file-public-gate",
        kind="video",
        storage_uri="s3://antiek/multimedia/krea-file-public-gate.mp4",
        sha256=SHA,
        mime="video/mp4",
        provider="krea",
        duration_seconds=route_preview.duration_seconds,
        width_px=route_preview.resolution[0] if route_preview.resolution else None,
        height_px=route_preview.resolution[1] if route_preview.resolution else None,
    )
    record_provider_artifact_receipt(
        store,
        draft.asset.asset_id,
        LiveProviderArtifactReceipt(
            provider_job_id="krea-job-public-gate",
            provider="krea",
            status="succeeded",
            files=(provider_file,),
        ),
    )
    plan_provider_artifact_attachment(store, draft.asset.asset_id)
    attach_provider_artifacts_to_manifest(store, draft.asset.asset_id)

    gated = evaluate_public_export_gate(store, draft.asset.asset_id)
    job = gated.jobs[-1]

    assert job.kind == "export_gate"
    assert job.status == "partial"
    assert job.public_export_gate is not None
    assert job.public_export_gate.status == "manual_review"
    assert job.public_export_gate.public_export_enabled is False
    assert job.public_export_gate.attached_file_ids[-1] == "krea-file-public-gate"
    assert job.public_export_gate.required_gate_ids == ("hardening", "rights_and_publication")
    assert "presence-only-not-a-real-secret" not in job.model_dump_json()


def test_public_export_gate_blocks_failed_hardening(tmp_path, monkeypatch):
    monkeypatch.setenv("KREA_API_KEY", "presence-only-not-a-real-secret")
    store = MultimediaAssetStore(tmp_path)
    draft = store.create_draft(
        CreateMultimediaDraftRequest(
            topic="documentary on fly-by-wire certification",
            target_minutes=20,
            mode="video",
            route_policy="balanced",
        )
    )
    store.approve_dry_run(draft.asset.asset_id)
    store.prepare_live_execution(
        draft.asset.asset_id,
        LiveProviderExecutionRequest(
            max_budget_usd=100,
            route_policy="balanced",
            operator_acknowledged_spend=True,
            dry_run_revision_id=draft.asset.revision_id,
        ),
    )
    previewed = preview_next_live_execution(store, draft.asset.asset_id)
    route_preview = previewed.jobs[-1].route_preview
    assert route_preview is not None
    provider_file = GeneratedFile(
        file_id="krea-file-blocked-hardening",
        kind="video",
        storage_uri="s3://antiek/multimedia/krea-file-blocked-hardening.mp4",
        sha256=SHA,
        mime="video/mp4",
        provider="krea",
        duration_seconds=route_preview.duration_seconds,
        width_px=route_preview.resolution[0] if route_preview.resolution else None,
        height_px=route_preview.resolution[1] if route_preview.resolution else None,
    )
    record_provider_artifact_receipt(
        store,
        draft.asset.asset_id,
        LiveProviderArtifactReceipt(
            provider_job_id="krea-job-blocked-hardening",
            provider="krea",
            status="succeeded",
            files=(provider_file,),
        ),
    )
    plan_provider_artifact_attachment(store, draft.asset.asset_id)
    attached = attach_provider_artifacts_to_manifest(store, draft.asset.asset_id)
    failed_report = MultimediaHardeningReport(
        asset_id=draft.asset.asset_id,
        revision_id=draft.asset.revision_id,
        ship_status="blocked",
        gates=(
            GateResult(
                gate_id="grounding_and_disclosure",
                status="fail",
                findings=(
                    GateFinding(
                        code="unsourced_factual_claim",
                        severity="error",
                        message="Synthetic test failure.",
                    ),
                ),
            ),
        ),
    )
    store.save(attached.model_copy(update={"hardening_report": failed_report}))

    gated = evaluate_public_export_gate(store, draft.asset.asset_id)

    assert gated.jobs[-1].status == "failed"
    assert gated.jobs[-1].error_code == "public_export_hardening_blocked"
    assert gated.jobs[-1].public_export_gate is not None
    assert gated.jobs[-1].public_export_gate.status == "blocked"
    assert gated.jobs[-1].public_export_gate.hardening_status == "blocked"
    assert gated.jobs[-1].public_export_gate.required_gate_ids == ("grounding_and_disclosure",)


def test_provider_artifact_attachment_plan_requires_successful_receipt(tmp_path, monkeypatch):
    monkeypatch.setenv("KREA_API_KEY", "presence-only-not-a-real-secret")
    store = MultimediaAssetStore(tmp_path)
    draft = store.create_draft(
        CreateMultimediaDraftRequest(
            topic="documentary on aircraft displays",
            target_minutes=20,
            mode="video",
            route_policy="balanced",
        )
    )
    store.approve_dry_run(draft.asset.asset_id)
    store.prepare_live_execution(
        draft.asset.asset_id,
        LiveProviderExecutionRequest(
            max_budget_usd=100,
            route_policy="balanced",
            operator_acknowledged_spend=True,
            dry_run_revision_id=draft.asset.revision_id,
        ),
    )
    preview_next_live_execution(store, draft.asset.asset_id)

    planned = plan_provider_artifact_attachment(store, draft.asset.asset_id)

    assert planned.jobs[-1].status == "failed"
    assert planned.jobs[-1].error_code == "artifact_attachment_prerequisite_missing"
    assert planned.jobs[-1].attachment_plan is None


def test_provider_artifact_attachment_plan_rejects_shape_mismatch(tmp_path, monkeypatch):
    monkeypatch.setenv("KREA_API_KEY", "presence-only-not-a-real-secret")
    store = MultimediaAssetStore(tmp_path)
    draft = store.create_draft(
        CreateMultimediaDraftRequest(
            topic="documentary on winglets",
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
    preview_next_live_execution(store, draft.asset.asset_id)
    receipt = LiveProviderArtifactReceipt(
        provider_job_id="krea-job-bad-shape",
        provider="krea",
        status="succeeded",
        files=(
            GeneratedFile(
                file_id="krea-file-bad-shape",
                kind="video",
                storage_uri="s3://antiek/multimedia/krea-file-bad-shape.mp4",
                sha256=SHA,
                mime="video/mp4",
                provider="krea",
                duration_seconds=1200,
                width_px=1920,
                height_px=1080,
            ),
        ),
    )
    recorded = record_provider_artifact_receipt(store, draft.asset.asset_id, receipt)

    planned = plan_provider_artifact_attachment(store, draft.asset.asset_id)

    assert planned.jobs[-1].status == "failed"
    assert planned.jobs[-1].error_code == "artifact_shape_mismatch"
    assert planned.jobs[-1].execution_plan == queued.jobs[-1].execution_plan
    assert planned.jobs[-1].artifact_receipt == recorded.jobs[-1].artifact_receipt
    assert planned.jobs[-1].attachment_plan is None


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
