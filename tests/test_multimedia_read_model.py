"""SPR-09 multimedia API persistence/read-model tests."""

from __future__ import annotations

import hashlib
import os
import shutil
import stat
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor
from pathlib import Path

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from interfaces.research.api import multimedia_routes
from substrate.multimedia import read_model as multimedia_read_model
from substrate.multimedia.read_model import (
    ApplySteeringPreviewRequest,
    CreateMultimediaDraftRequest,
    MultimediaAssetStore,
    MultimediaJobRecord,
    SteeringPreviewConflict,
    SteeringPreviewRequest,
)

_PREVIEW_KEY = b"multimedia-steering-preview-test-key"


def _apply_steering_preview(
    store: MultimediaAssetStore,
    asset_id: str,
    request: SteeringPreviewRequest,
):
    preview = store.preview_steering(asset_id, request)
    assert preview.status == "ready"
    return store.apply_steering_preview(
        asset_id,
        ApplySteeringPreviewRequest(
            **request.model_dump(),
            preview_token=preview.preview_token,
        ),
    )


def _record_job_in_process(arguments: tuple[str, str, int]) -> int:
    root, asset_id, index = arguments
    record = MultimediaAssetStore(root).record_job(
        asset_id,
        kind="render",
        status="running",
        progress_percent=index,
        message=f"process {index}",
        owner_id="owner-a",
    )
    return record.jobs[-1].sequence


def test_store_create_approve_reopen_steer_and_harden(tmp_path):
    store = MultimediaAssetStore(tmp_path)

    draft = store.create_draft(
        CreateMultimediaDraftRequest(
            topic="widebody aircraft economics",
            target_minutes=20,
            mode="hybrid",
            route_policy="cheapest",
            sources=("High-bypass engines changed long-haul economics.",),
            must_cover=("engine reliability",),
        )
    )

    assert draft.asset.asset_id.startswith("mm-")
    assert draft.asset.status == "planned"
    reopened = store.get(draft.asset.asset_id)
    assert reopened.asset.revision_id == "rev-1"

    approved = store.approve_dry_run(draft.asset.asset_id)
    assert approved.asset.status == "ready"
    assert approved.asset.manifest.files
    assert approved.asset.manifest.transcript_file_id is not None
    assert approved.jobs[-1].kind == "render"
    assert approved.jobs[-1].status == "succeeded"

    steered = _apply_steering_preview(
        store,
        draft.asset.asset_id,
        SteeringPreviewRequest(
            expected_parent_revision_id=approved.asset.revision_id,
            prompt="go deeper on engines in chapter 2",
        ),
    )
    assert steered.asset.parent_revision_id == "rev-1"
    assert steered.asset.steering_event_id
    assert steered.latest_steering_intent is not None
    assert steered.jobs[-1].kind == "steering"

    hardened = store.run_hardening(draft.asset.asset_id)
    assert hardened.hardening_report is not None
    assert hardened.hardening_report.ship_status == "blocked"
    assert "cost_and_budget" in hardened.hardening_report.failed_gate_ids
    assert hardened.hardening_report.manual_gate_ids == ("rights_and_publication",)
    assert hardened.jobs[-1].kind == "hardening"
    assert hardened.jobs[-1].progress_percent == 100

    # A failed provider job (the failure contract is tested before any live
    # worker exists). Downgrade-to-cheapest stays a route-policy op, never a
    # mutation hidden inside render status.
    failed = store.record_job(
        draft.asset.asset_id,
        kind="provider_execution",
        status="failed",
        progress_percent=42,
        message="Krea render timed out before completion.",
        error_code="provider_timeout",
        retryable=True,
    )
    assert failed.jobs[-1].status == "failed"
    assert failed.jobs[-1].retryable is True
    assert failed.jobs[-1].error_code == "provider_timeout"

    # Reload from the JSON store: job history + latest summary survive a
    # fresh store instance (the persistence value — a model-only test is
    # insufficient per the SPR-11 rigor rubric).
    reloaded_store = MultimediaAssetStore(tmp_path)
    reloaded = reloaded_store.list_jobs(draft.asset.asset_id)
    assert reloaded.count == 4
    sequences = [job.sequence for job in reloaded.jobs]
    assert sequences == sorted(sequences)  # ordered by monotonic sequence
    assert [job.kind for job in reloaded.jobs] == [
        "render",
        "steering",
        "hardening",
        "provider_execution",
    ]
    latest_summary = reloaded_store.list_assets().assets[0]
    assert latest_summary.latest_job_kind == "provider_execution"
    assert latest_summary.latest_job_status == "failed"
    listed = store.list_assets()
    assert listed.count == 1
    assert listed.assets[0].asset_id == draft.asset.asset_id
    assert listed.assets[0].hardening_status == hardened.hardening_report.ship_status


def test_store_persists_raw_and_corrected_voice_steering(tmp_path: Path) -> None:
    store = MultimediaAssetStore(tmp_path)
    draft = store.create_draft(
        CreateMultimediaDraftRequest(
            topic="Aircraft engine reliability",
            target_minutes=20,
            mode="audio",
            route_policy="cheapest",
        )
    )

    steered = _apply_steering_preview(
        store,
        draft.asset.asset_id,
        SteeringPreviewRequest(
            expected_parent_revision_id=draft.asset.revision_id,
            prompt="go deeper on engines in chapter 2",
            raw_voice_transcript="go deeper on cabins in chapter 2",
            corrected_voice_transcript="go deeper on engines in chapter 2",
        ),
    )

    assert steered.latest_steering_intent is not None
    transcript = steered.latest_steering_intent.transcript
    assert transcript is not None
    assert transcript.raw_text == "go deeper on cabins in chapter 2"
    assert transcript.corrected_text == "go deeper on engines in chapter 2"


def test_store_parses_raw_voice_steering_without_a_correction(tmp_path: Path) -> None:
    store = MultimediaAssetStore(tmp_path)
    draft = store.create_draft(
        CreateMultimediaDraftRequest(
            topic="Aircraft engine reliability",
            target_minutes=20,
            mode="audio",
            route_policy="cheapest",
        )
    )

    steered = _apply_steering_preview(
        store,
        draft.asset.asset_id,
        SteeringPreviewRequest(
            expected_parent_revision_id=draft.asset.revision_id,
            prompt="go deeper on engines in chapter 2",
            raw_voice_transcript="go deeper on engines in chapter 2",
        ),
    )

    assert steered.latest_steering_intent is not None
    transcript = steered.latest_steering_intent.transcript
    assert transcript is not None
    assert transcript.raw_text == "go deeper on engines in chapter 2"
    assert transcript.corrected_text is None
    assert steered.latest_steering_intent.prompt == transcript.raw_text


def test_steering_preview_clarifies_without_mutating_store(tmp_path: Path) -> None:
    store = MultimediaAssetStore(tmp_path, preview_signing_key=_PREVIEW_KEY)
    draft = store.create_draft(
        CreateMultimediaDraftRequest(
            topic="Aircraft engine reliability",
            target_minutes=20,
            mode="audio",
            route_policy="cheapest",
        ),
        owner_id="owner-a",
    )
    record_path = next((tmp_path / "accounts").glob("*/*.json"))
    before_bytes = record_path.read_bytes()
    before_mtime = record_path.stat().st_mtime_ns

    preview = store.preview_steering(
        draft.asset.asset_id,
        SteeringPreviewRequest(
            expected_parent_revision_id=draft.asset.revision_id,
            prompt="make this better",
        ),
        owner_id="owner-a",
    )

    assert preview.status == "needs_clarification"
    assert preview.intent.clarifications
    assert not hasattr(preview, "preview_token")
    assert record_path.read_bytes() == before_bytes
    assert record_path.stat().st_mtime_ns == before_mtime
    assert store.get(draft.asset.asset_id, owner_id="owner-a") == draft


def test_ready_preview_exposes_scope_reuse_cost_and_applies_exact_snapshot(
    tmp_path: Path,
) -> None:
    store = MultimediaAssetStore(tmp_path, preview_signing_key=_PREVIEW_KEY)
    draft = store.create_draft(
        CreateMultimediaDraftRequest(
            topic="Aircraft engine reliability",
            target_minutes=20,
            mode="audio",
            route_policy="cheapest",
        ),
        owner_id="owner-a",
    )
    request = SteeringPreviewRequest(
        expected_parent_revision_id=draft.asset.revision_id,
        prompt="go deeper on chapter 2",
        raw_voice_transcript="go deeper on cabins in chapter 2",
        corrected_voice_transcript="go deeper on engines in chapter 2",
    )
    preview = store.preview_steering(draft.asset.asset_id, request, owner_id="owner-a")

    assert preview.status == "ready"
    assert preview.operations == preview.intent.operations
    assert preview.affected_segment_ids
    assert any(row.reused for row in preview.segment_reuse)
    assert all(len(value) == 64 for row in preview.segment_reuse for value in row.file_sha256s)
    assert preview.estimated_cost_delta_usd >= 0
    assert preview.intent.transcript is not None
    assert preview.intent.transcript.raw_text == "go deeper on cabins in chapter 2"
    assert preview.intent.prompt == "go deeper on engines in chapter 2"

    applied = store.apply_steering_preview(
        draft.asset.asset_id,
        ApplySteeringPreviewRequest(**request.model_dump(), preview_token=preview.preview_token),
        owner_id="owner-a",
    )
    assert applied.asset.parent_revision_id == draft.asset.revision_id
    assert applied.asset.revision_id == preview.proposed_revision_id
    assert applied.jobs[-1].kind == "steering"
    assert applied.latest_steering_intent == preview.intent

    with pytest.raises(SteeringPreviewConflict, match="stale_parent"):
        store.apply_steering_preview(
            draft.asset.asset_id,
            ApplySteeringPreviewRequest(**request.model_dump(), preview_token=preview.preview_token),
            owner_id="owner-a",
        )


def test_ready_preview_deduplicates_cost_when_operations_share_a_segment(
    tmp_path: Path,
) -> None:
    store = MultimediaAssetStore(tmp_path, preview_signing_key=_PREVIEW_KEY)
    draft = store.create_draft(
        CreateMultimediaDraftRequest(
            topic="Aircraft engine reliability",
            target_minutes=20,
            mode="video",
            route_policy="highest_quality",
        )
    )

    preview = store.preview_steering(
        draft.asset.asset_id,
        SteeringPreviewRequest(
            expected_parent_revision_id=draft.asset.revision_id,
            prompt="go deeper and regenerate chapter 2",
        ),
    )

    assert preview.status == "ready"
    assert len(preview.operations) == 2
    assert len(preview.affected_segment_ids) == 1
    assert preview.estimated_cost_delta_usd > 0
    assert all(
        change.estimated_cost_delta_usd == preview.estimated_cost_delta_usd
        for change in preview.changes
    )
    assert sum(change.estimated_cost_delta_usd for change in preview.changes) == (
        preview.estimated_cost_delta_usd * 2
    )


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("prompt", "go deeper on engines in chapter 3"),
        ("raw_voice_transcript", "go deeper on wings in chapter 2"),
        ("corrected_voice_transcript", "go deeper on engines in chapter 3"),
    ],
)
def test_apply_preview_rejects_changed_prompt_or_voice_without_mutation(
    tmp_path: Path, field: str, value: str
) -> None:
    store = MultimediaAssetStore(tmp_path, preview_signing_key=_PREVIEW_KEY)
    draft = store.create_draft(
        CreateMultimediaDraftRequest(topic="Aircraft engines", target_minutes=20, mode="audio")
    )
    request = SteeringPreviewRequest(
        expected_parent_revision_id=draft.asset.revision_id,
        prompt="go deeper on engines in chapter 2",
        raw_voice_transcript="go deeper on engine in chapter 2",
        corrected_voice_transcript="go deeper on engines in chapter 2",
    )
    preview = store.preview_steering(draft.asset.asset_id, request)
    assert preview.status == "ready"
    changed = request.model_dump()
    changed[field] = value

    with pytest.raises(SteeringPreviewConflict, match="content_mismatch"):
        store.apply_steering_preview(
            draft.asset.asset_id,
            ApplySteeringPreviewRequest(**changed, preview_token=preview.preview_token),
        )
    assert store.get(draft.asset.asset_id) == draft


def test_apply_preview_rejects_tampering_expiry_and_cross_owner(tmp_path: Path) -> None:
    now = [1000.0]
    store = MultimediaAssetStore(
        tmp_path,
        preview_signing_key=_PREVIEW_KEY,
        clock=lambda: now[0],
        preview_ttl_seconds=5,
    )
    draft = store.create_draft(
        CreateMultimediaDraftRequest(topic="Aircraft engines", target_minutes=20, mode="audio"),
        owner_id="owner-a",
    )
    request = SteeringPreviewRequest(
        expected_parent_revision_id=draft.asset.revision_id,
        prompt="go deeper on chapter 2",
    )
    preview = store.preview_steering(draft.asset.asset_id, request, owner_id="owner-a")
    assert preview.status == "ready"
    apply_request = ApplySteeringPreviewRequest(
        **request.model_dump(), preview_token=preview.preview_token
    )

    with pytest.raises(KeyError):
        store.apply_steering_preview(draft.asset.asset_id, apply_request, owner_id="owner-b")
    with pytest.raises(SteeringPreviewConflict, match="content_mismatch"):
        store.apply_steering_preview(
            draft.asset.asset_id,
            apply_request.model_copy(update={"preview_token": preview.preview_token + "x"}),
            owner_id="owner-a",
        )
    now[0] = 1006.0
    with pytest.raises(SteeringPreviewConflict, match="preview_expired"):
        store.apply_steering_preview(draft.asset.asset_id, apply_request, owner_id="owner-a")
    assert store.get(draft.asset.asset_id, owner_id="owner-a") == draft


def test_one_preview_authority_has_one_concurrent_winner(tmp_path: Path) -> None:
    store = MultimediaAssetStore(tmp_path, preview_signing_key=_PREVIEW_KEY)
    draft = store.create_draft(
        CreateMultimediaDraftRequest(topic="Aircraft engines", target_minutes=20, mode="audio")
    )
    request = SteeringPreviewRequest(
        expected_parent_revision_id=draft.asset.revision_id,
        prompt="go deeper on chapter 2",
    )
    preview = store.preview_steering(draft.asset.asset_id, request)
    assert preview.status == "ready"
    apply_request = ApplySteeringPreviewRequest(
        **request.model_dump(), preview_token=preview.preview_token
    )

    def apply_once() -> str:
        try:
            return store.apply_steering_preview(draft.asset.asset_id, apply_request).asset.revision_id
        except SteeringPreviewConflict as exc:
            return exc.code

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(lambda _: apply_once(), range(2)))
    assert outcomes.count(preview.proposed_revision_id) == 1
    assert outcomes.count("multimedia_steering_stale_parent") == 1


def test_preview_authority_binds_asset_and_complete_child_manifest(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = MultimediaAssetStore(tmp_path, preview_signing_key=_PREVIEW_KEY)
    request_data = CreateMultimediaDraftRequest(
        topic="Aircraft engines", target_minutes=20, mode="audio"
    )
    first = store.create_draft(request_data)
    second = store.create_draft(request_data)
    request = SteeringPreviewRequest(
        expected_parent_revision_id=first.asset.revision_id,
        prompt="go deeper on chapter 2",
    )
    preview = store.preview_steering(first.asset.asset_id, request)
    assert preview.status == "ready"
    authority = ApplySteeringPreviewRequest(
        **request.model_dump(), preview_token=preview.preview_token
    )

    with pytest.raises(SteeringPreviewConflict, match="content_mismatch"):
        store.apply_steering_preview(second.asset.asset_id, authority)

    original_plan_revision = multimedia_read_model.plan_revision

    def drift_manifest(parent, intent):  # type: ignore[no-untyped-def]
        revision = original_plan_revision(parent, intent)
        return revision.model_copy(
            update={
                "manifest": revision.manifest.model_copy(
                    update={"route_policy": "highest_quality"}
                )
            }
        )

    monkeypatch.setattr(multimedia_read_model, "plan_revision", drift_manifest)
    with pytest.raises(SteeringPreviewConflict, match="plan_mismatch"):
        store.apply_steering_preview(first.asset.asset_id, authority)
    assert store.get(first.asset.asset_id) == first
    assert store.get(second.asset.asset_id) == second


def test_auth_secret_derives_shared_preview_authority_across_store_instances(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("ANTIEK_MULTIMEDIA_STEERING_PREVIEW_KEY_HEX", raising=False)
    monkeypatch.setenv("ANTIEK_AUTH_SECRET", "shared-auth-secret-for-worker-key-derivation")
    first_store = MultimediaAssetStore(tmp_path)
    draft = first_store.create_draft(
        CreateMultimediaDraftRequest(
            topic="Aircraft engines", target_minutes=20, mode="audio"
        )
    )
    request = SteeringPreviewRequest(
        expected_parent_revision_id=draft.asset.revision_id,
        prompt="go deeper on chapter 2",
    )
    preview = first_store.preview_steering(draft.asset.asset_id, request)
    assert preview.status == "ready"

    second_store = MultimediaAssetStore(tmp_path)
    applied = second_store.apply_steering_preview(
        draft.asset.asset_id,
        ApplySteeringPreviewRequest(
            **request.model_dump(), preview_token=preview.preview_token
        ),
    )
    assert applied.asset.revision_id == preview.proposed_revision_id


def test_multimedia_routes_round_trip_without_provider_secrets(tmp_path, monkeypatch):
    monkeypatch.setattr(multimedia_routes, "_STORE", MultimediaAssetStore(tmp_path))
    app = FastAPI()

    @app.middleware("http")
    async def identity(request: Request, call_next):  # type: ignore[no-untyped-def]
        if request.headers.get("x-test-auth") == "yes":
            request.state.auth_method = "bearer_token"
            request.state.user_id = request.headers.get("x-test-user", "owner-a")
        return await call_next(request)

    multimedia_routes.register_multimedia_routes(app)
    client = TestClient(app)
    assert client.get("/multimedia/assets").status_code == 401
    client.headers.update({"x-test-auth": "yes", "x-test-user": "owner-a"})

    created = client.post(
        "/multimedia/assets",
        json={
            "topic": "swept wing history",
            "target_minutes": 20,
            "mode": "audio",
            "route_policy": "cheapest",
            "sources": ["Swept wings delayed shock waves and changed aircraft design."],
        },
    )
    assert created.status_code == 201
    asset_id = created.json()["asset"]["asset_id"]

    approved = client.post(f"/multimedia/assets/{asset_id}/approve-dry-run")
    assert approved.status_code == 200
    assert approved.json()["asset"]["status"] == "ready"

    previewed = client.post(
        f"/multimedia/assets/{asset_id}/steering-preview",
        json={
            "expected_parent_revision_id": "rev-1",
            "prompt": "make it 20 minutes and use cheapest",
        },
    )
    assert previewed.status_code == 200
    assert previewed.json()["status"] == "ready"
    steered = client.post(
        f"/multimedia/assets/{asset_id}/steer",
        json={
            "expected_parent_revision_id": "rev-1",
            "prompt": "make it 20 minutes and use cheapest",
            "preview_token": previewed.json()["preview_token"],
        },
    )
    assert steered.status_code == 200
    assert steered.json()["asset"]["parent_revision_id"] == "rev-1"

    hardened = client.post(f"/multimedia/assets/{asset_id}/hardening")
    assert hardened.status_code == 503
    assert hardened.json()["detail"] == "multimedia hardening runtime is unavailable"

    listed = client.get("/multimedia/assets")
    assert listed.status_code == 200
    assert listed.json()["count"] == 1

    # GET /jobs returns ordered job rows for the asset.
    jobs = client.get(f"/multimedia/assets/{asset_id}/jobs")
    assert jobs.status_code == 200
    jobs_body = jobs.json()
    # A missing cost-authority runtime cannot leave a hardening job row.
    assert jobs_body["count"] == 2
    assert [row["kind"] for row in jobs_body["jobs"]] == [
        "render",
        "steering",
    ]
    sequences = [row["sequence"] for row in jobs_body["jobs"]]
    assert sequences == sorted(sequences)
    assert all(isinstance(row["job_id"], str) for row in jobs_body["jobs"])
    assert isinstance(jobs_body["jobs"][0], dict)
    MultimediaJobRecord.model_validate(jobs_body["jobs"][0])

    missing = client.get("/multimedia/assets/mm-missing")
    assert missing.status_code == 404

    missing_jobs = client.get("/multimedia/assets/mm-missing/jobs")
    assert missing_jobs.status_code == 404
    assert client.post(
        f"/multimedia/assets/{asset_id}/prepare-live-execution", json={}
    ).status_code == 404
    assert client.post(
        f"/multimedia/assets/{asset_id}/execution-authorizations", json={}
    ).status_code == 404

    other = TestClient(app, headers={"x-test-auth": "yes", "x-test-user": "owner-b"})
    assert other.get("/multimedia/assets").json() == {"assets": [], "count": 0}
    assert other.get(f"/multimedia/assets/{asset_id}").status_code == 404
    denied = (
        other.get(f"/multimedia/assets/{asset_id}/jobs"),
        other.post(f"/multimedia/assets/{asset_id}/approve-dry-run"),
        other.post(
            f"/multimedia/assets/{asset_id}/steering-preview",
            json={"expected_parent_revision_id": "rev-1", "prompt": "steal"},
        ),
        other.post(
            f"/multimedia/assets/{asset_id}/steer",
            json={
                "expected_parent_revision_id": "rev-1",
                "prompt": "steal",
                "preview_token": "not-an-authority",
            },
        ),
        other.post(f"/multimedia/assets/{asset_id}/hardening"),
    )
    assert [response.status_code for response in denied] == [404, 404, 404, 404, 503]


def test_hybrid_approve_does_not_double_count_audio_cost_rows(tmp_path):
    store = MultimediaAssetStore(tmp_path)
    draft = store.create_draft(
        CreateMultimediaDraftRequest(
            topic="widebody aircraft economics",
            target_minutes=20,
            mode="hybrid",
            route_policy="cheapest",
            sources=("High-bypass engines changed long-haul economics.",),
        )
    )
    approved = store.approve_dry_run(draft.asset.asset_id)
    # assemble_video_documentary seeds the video manifest from audio.manifest,
    # so the video manifest already carries the audio TTS cost rows. Merging
    # audio's rows again would double them (10 rows with 5 duplicate call_ids).
    # FakeTTSProvider rows are free (cost 0), so the signal is row-count /
    # call-id uniqueness, not a non-zero sum.
    seen: set[str] = set()
    for row in approved.asset.manifest.cost_rows:
        assert row.call_id not in seen, f"duplicate cost row call_id {row.call_id!r}"
        seen.add(row.call_id)
    # The 5 chapter TTS rows appear exactly once (not twice).
    assert len(approved.asset.manifest.cost_rows) == len(seen)
    assert len(approved.asset.manifest.provider_calls) == len(
        {call.call_id for call in approved.asset.manifest.provider_calls}
    )


def test_account_store_serializes_jobs_across_processes(tmp_path) -> None:
    store = MultimediaAssetStore(tmp_path)
    draft = store.create_draft(
        CreateMultimediaDraftRequest(
            topic="cross-process locking",
            target_minutes=15,
            mode="audio",
            sources=("A source.",),
        ),
        owner_id="owner-a",
    )

    arguments = [(str(tmp_path), draft.asset.asset_id, index) for index in range(1, 9)]
    with ProcessPoolExecutor(max_workers=4) as executor:
        sequences = list(executor.map(_record_job_in_process, arguments))

    assert sorted(sequences) == list(range(1, 9))
    persisted = store.get(draft.asset.asset_id, owner_id="owner-a")
    assert [job.sequence for job in persisted.jobs] == list(range(1, 9))


def test_account_store_isolates_envelopes_and_preserves_concurrent_jobs(tmp_path) -> None:
    store = MultimediaAssetStore(tmp_path)
    request = CreateMultimediaDraftRequest(
        topic="account scoped aircraft history",
        target_minutes=20,
        mode="audio",
        route_policy="cheapest",
    )
    first = store.create_draft(request, owner_id="owner-a@example.test")
    second = store.create_draft(request, owner_id="owner-b@example.test")
    assert first.asset.owner_user_id == hashlib.sha256(b"owner-a@example.test").hexdigest()
    assert second.asset.owner_user_id == hashlib.sha256(b"owner-b@example.test").hexdigest()
    with pytest.raises(ValueError, match="owner conflicts"):
        store.save(
            first.model_copy(
                update={
                    "asset": first.asset.model_copy(update={"owner_user_id": "f" * 64})
                }
            ),
            owner_id="owner-a@example.test",
        )
    assert [row.asset_id for row in store.list_assets(owner_id="owner-a@example.test").assets] == [
        first.asset.asset_id
    ]
    assert [row.asset_id for row in store.list_assets(owner_id="owner-b@example.test").assets] == [
        second.asset.asset_id
    ]
    with pytest.raises(KeyError):
        store.get(first.asset.asset_id, owner_id="owner-b@example.test")

    account = tmp_path / "accounts" / hashlib.sha256(b"owner-a@example.test").hexdigest()
    envelope = account / f"{first.asset.asset_id}.json"
    assert stat.S_IMODE(account.stat().st_mode) == 0o700
    assert stat.S_IMODE(envelope.stat().st_mode) == 0o600
    assert "owner-a@example.test" not in str(envelope)
    assert "owner-a@example.test" not in envelope.read_text()

    def append(index: int) -> None:
        MultimediaAssetStore(tmp_path).record_job(
            first.asset.asset_id,
            owner_id="owner-a@example.test",
            kind="provider_execution",
            status="partial",
            progress_percent=index,
            message=f"worker {index}",
        )

    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(append, range(20)))
    jobs = MultimediaAssetStore(tmp_path).list_jobs(
        first.asset.asset_id, owner_id="owner-a@example.test"
    ).jobs
    assert len(jobs) == 20
    assert [row.sequence for row in jobs] == list(range(1, 21))


def test_legacy_assets_require_explicit_crash_idempotent_owner_migration(tmp_path) -> None:
    seed = MultimediaAssetStore(tmp_path)
    record = seed.create_draft(
        CreateMultimediaDraftRequest(
            topic="legacy aircraft archive",
            target_minutes=20,
            mode="audio",
            route_policy="cheapest",
        )
    )
    account_record = next((tmp_path / "accounts").glob("*/*.json"))
    account_record.unlink()
    legacy = tmp_path / f"{record.asset.asset_id}.json"
    legacy.write_text(record.model_dump_json(indent=2) + "\n")

    store = MultimediaAssetStore(tmp_path)
    with pytest.raises(KeyError):
        store.get(record.asset.asset_id, owner_id="owner-a")
    with pytest.raises(KeyError):
        store.get(record.asset.asset_id, owner_id="owner-b")
    assert store.migrate_legacy_assets(owner_id="owner-a") == 1
    migrated = store.get(record.asset.asset_id, owner_id="owner-a")
    assert migrated.asset.owner_user_id == hashlib.sha256(b"owner-a").hexdigest()
    with pytest.raises(KeyError):
        store.get(record.asset.asset_id, owner_id="owner-b")
    assert not legacy.exists()

    # Simulate a crash after destination publication but before legacy unlink.
    legacy.write_text(record.model_dump_json(indent=2) + "\n")
    assert store.migrate_legacy_assets(owner_id="owner-a") == 1
    assert not legacy.exists()
    assert store.get(record.asset.asset_id, owner_id="owner-a") == migrated

    conflict = record.model_copy(update={"style": "conflicting legacy"})
    legacy.write_text(conflict.model_dump_json(indent=2) + "\n")
    with pytest.raises(ValueError, match="migration conflicts"):
        store.migrate_legacy_assets(owner_id="owner-a")
    assert legacy.exists()
    assert store.get(record.asset.asset_id, owner_id="owner-a") == migrated


def test_legacy_migration_rejects_oversized_and_symlinked_records(tmp_path) -> None:
    store = MultimediaAssetStore(tmp_path)
    oversized = tmp_path / "mm-oversized.json"
    with oversized.open("wb") as stream:
        stream.truncate(32 * 1024 * 1024 + 1)
    with pytest.raises(ValueError, match="unsafe"):
        store.migrate_legacy_assets(owner_id="owner-a")
    oversized.unlink()

    target = tmp_path / "legacy-target"
    target.write_text("{}")
    alias = tmp_path / "mm-symlink.json"
    alias.symlink_to(target)
    with pytest.raises(ValueError, match="unsafe"):
        store.migrate_legacy_assets(owner_id="owner-a")


def test_account_store_rejects_aliases_relocation_and_invalid_owner(tmp_path) -> None:
    store = MultimediaAssetStore(tmp_path)
    record = store.create_draft(
        CreateMultimediaDraftRequest(
            topic="private aircraft record",
            target_minutes=20,
            mode="audio",
            route_policy="cheapest",
        ),
        owner_id="owner-a",
    )
    digest = hashlib.sha256(b"owner-a").hexdigest()
    source = tmp_path / "accounts" / digest / f"{record.asset.asset_id}.json"
    alias_id = "mm-alias"
    alias = source.with_name(f"{alias_id}.json")
    os.link(source, alias)
    with pytest.raises(ValueError, match="unsafe"):
        store.get(alias_id, owner_id="owner-a")
    alias.unlink()
    store.create_draft(
        CreateMultimediaDraftRequest(
            topic="second owner partition",
            target_minutes=20,
            mode="audio",
            route_policy="cheapest",
        ),
        owner_id="owner-b",
    )
    other_digest = hashlib.sha256(b"owner-b").hexdigest()
    relocated = tmp_path / "accounts" / other_digest / f"{record.asset.asset_id}.json"
    shutil.copyfile(source, relocated)
    os.chmod(relocated, 0o600)
    with pytest.raises(ValueError, match="identity conflicts"):
        store.get(record.asset.asset_id, owner_id="owner-b")
    with pytest.raises(ValueError, match="owner"):
        store.list_assets(owner_id="\n")


def test_route_registration_migrates_legacy_only_to_configured_owner(
    tmp_path, monkeypatch
) -> None:
    store = MultimediaAssetStore(tmp_path)
    record = store.create_draft(
        CreateMultimediaDraftRequest(
            topic="configured legacy owner",
            target_minutes=20,
            mode="audio",
            route_policy="cheapest",
        )
    )
    next((tmp_path / "accounts").glob("*/*.json")).unlink()
    legacy = tmp_path / f"{record.asset.asset_id}.json"
    legacy.write_text(record.model_dump_json(indent=2) + "\n")
    monkeypatch.setattr(multimedia_routes, "_STORE", MultimediaAssetStore(tmp_path))
    monkeypatch.setenv("ANTIEK_MULTIMEDIA_LEGACY_OWNER_ID", "owner-a")
    app = FastAPI()
    multimedia_routes.register_multimedia_routes(app)
    assert not legacy.exists()
    migrated = multimedia_routes.get_store().get(record.asset.asset_id, owner_id="owner-a")
    assert migrated.asset.owner_user_id == hashlib.sha256(b"owner-a").hexdigest()
    assert migrated.asset.model_copy(update={"owner_user_id": record.asset.owner_user_id}) == record.asset
    with pytest.raises(KeyError):
        multimedia_routes.get_store().get(record.asset.asset_id, owner_id="owner-b")
