"""SPR-09 multimedia API persistence/read-model tests."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from interfaces.research.api import multimedia_routes
from substrate.multimedia.read_model import (
    CreateMultimediaDraftRequest,
    MultimediaAssetStore,
    MultimediaJobRecord,
    SteeringRequest,
)


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

    steered = store.apply_steering(
        draft.asset.asset_id,
        SteeringRequest(prompt="go deeper on engines in chapter 2"),
    )
    assert steered.asset.parent_revision_id == "rev-1"
    assert steered.asset.steering_event_id
    assert steered.latest_steering_intent is not None
    assert steered.jobs[-1].kind == "steering"

    hardened = store.run_hardening(draft.asset.asset_id)
    assert hardened.hardening_report is not None
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


def test_multimedia_routes_round_trip_without_provider_secrets(tmp_path, monkeypatch):
    monkeypatch.setattr(multimedia_routes, "_STORE", MultimediaAssetStore(tmp_path))
    app = FastAPI()
    multimedia_routes.register_multimedia_routes(app)
    client = TestClient(app)

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

    steered = client.post(
        f"/multimedia/assets/{asset_id}/steer",
        json={"prompt": "make it 20 minutes and use cheapest"},
    )
    assert steered.status_code == 200
    assert steered.json()["asset"]["parent_revision_id"] == "rev-1"

    hardened = client.post(f"/multimedia/assets/{asset_id}/hardening")
    assert hardened.status_code == 200
    report = hardened.json()["hardening_report"]
    assert report["ship_status"] in {"manual_review", "blocked"}
    # manual_gate_ids is a Python @property (not serialized); derive the manual
    # gate from the serialized `gates` tuple, which is the JSON source of truth.
    assert any(
        gate["status"] == "manual" and gate["gate_id"] == "rights_and_publication"
        for gate in report["gates"]
    )

    listed = client.get("/multimedia/assets")
    assert listed.status_code == 200
    assert listed.json()["count"] == 1

    # GET /jobs returns ordered job rows for the asset.
    jobs = client.get(f"/multimedia/assets/{asset_id}/jobs")
    assert jobs.status_code == 200
    jobs_body = jobs.json()
    # approve + steer + harden each left one job row.
    assert jobs_body["count"] == 3
    assert [row["kind"] for row in jobs_body["jobs"]] == [
        "render",
        "steering",
        "hardening",
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
