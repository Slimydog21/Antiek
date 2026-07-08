"""SPR-09 multimedia API persistence/read-model tests."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from interfaces.research.api import multimedia_routes
from substrate.multimedia.read_model import (
    CreateMultimediaDraftRequest,
    LiveProviderExecutionRequest,
    MultimediaAssetStore,
    ProviderExecutionWorkerRequest,
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

    reloaded_jobs = store.list_jobs(draft.asset.asset_id)
    assert [job.sequence for job in reloaded_jobs.jobs] == [1, 2, 3, 4]
    assert reloaded_jobs.jobs[-1].error_code == "provider_timeout"

    no_ack = store.prepare_live_execution(
        draft.asset.asset_id,
        LiveProviderExecutionRequest(
            max_budget_usd=10,
            route_policy="cheapest",
            operator_acknowledged_spend=False,
        ),
    )
    assert no_ack.jobs[-1].status == "failed"
    assert no_ack.jobs[-1].error_code == "spend_not_acknowledged"

    listed = store.list_assets()
    assert listed.count == 1
    assert listed.assets[0].asset_id == draft.asset.asset_id
    assert listed.assets[0].hardening_status == hardened.hardening_report.ship_status
    assert listed.assets[0].latest_job_kind == "provider_execution"
    assert listed.assets[0].latest_job_status == "failed"


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
    assert approved.status_code == 200
    assert approved.json()["asset"]["status"] == "ready"
    assert approved.json()["jobs"][-1]["kind"] == "render"

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
    assert "rights_and_publication" in report["manual_gate_ids"]

    jobs = client.get(f"/multimedia/assets/{asset_id}/jobs")
    assert jobs.status_code == 200
    assert [job["kind"] for job in jobs.json()["jobs"]] == ["render", "steering", "hardening"]

    listed = client.get("/multimedia/assets")
    assert listed.status_code == 200
    assert listed.json()["count"] == 1
    assert listed.json()["assets"][0]["latest_job_status"] == "succeeded"

    missing = client.get("/multimedia/assets/mm-missing")
    assert missing.status_code == 404
    missing_jobs = client.get("/multimedia/assets/mm-missing/jobs")
    assert missing_jobs.status_code == 404


def test_live_provider_budget_gates_without_paid_calls(tmp_path, monkeypatch):
    monkeypatch.delenv("KREA_API_KEY", raising=False)
    store = MultimediaAssetStore(tmp_path)
    draft = store.create_draft(
        CreateMultimediaDraftRequest(
            topic="jet engine reliability",
            target_minutes=20,
            mode="video",
            route_policy="balanced",
            sources=("Engine reliability improved long-range routing.",),
        )
    )
    approved = store.approve_dry_run(draft.asset.asset_id)
    sufficient_budget = 50.0

    too_low = store.prepare_live_execution(
        draft.asset.asset_id,
        LiveProviderExecutionRequest(
            max_budget_usd=0.01,
            route_policy="balanced",
            operator_acknowledged_spend=True,
        ),
    )
    assert too_low.jobs[-1].status == "failed"
    assert too_low.jobs[-1].error_code == "budget_below_estimate"
    assert too_low.asset.status == "ready"

    missing_provider = store.prepare_live_execution(
        draft.asset.asset_id,
        LiveProviderExecutionRequest(
            max_budget_usd=sufficient_budget,
            route_policy="balanced",
            operator_acknowledged_spend=True,
        ),
    )
    assert missing_provider.jobs[-1].status == "failed"
    assert missing_provider.jobs[-1].error_code == "provider_unconfigured"
    assert "KREA_API_KEY" not in missing_provider.jobs[-1].message

    mismatch = store.prepare_live_execution(
        draft.asset.asset_id,
        LiveProviderExecutionRequest(
            max_budget_usd=sufficient_budget,
            route_policy="balanced",
            operator_acknowledged_spend=True,
            dry_run_revision_id="rev-stale",
        ),
    )
    assert mismatch.jobs[-1].error_code == "revision_mismatch"

    monkeypatch.setenv("KREA_API_KEY", "fake-test-key")
    queued = store.prepare_live_execution(
        draft.asset.asset_id,
        LiveProviderExecutionRequest(
            max_budget_usd=sufficient_budget,
            route_policy="balanced",
            operator_acknowledged_spend=True,
            dry_run_revision_id=approved.asset.revision_id,
        ),
    )
    assert queued.jobs[-1].status == "queued"
    assert queued.jobs[-1].kind == "provider_execution"
    assert queued.jobs[-1].progress_percent == 0
    assert "fake-test-key" not in queued.jobs[-1].message

    worked = store.run_provider_execution_worker(draft.asset.asset_id)
    assert [job.status for job in worked.jobs[-2:]] == ["running", "succeeded"]
    assert worked.jobs[-2].kind == "provider_execution"
    assert worked.jobs[-1].progress_percent == 100
    assert "fake-test-key" not in worked.jobs[-1].message
    assert worked.asset.status == "ready"

    unchanged = store.run_provider_execution_worker(draft.asset.asset_id)
    assert len(unchanged.jobs) == len(worked.jobs)

    blocked = store.run_provider_execution_worker(
        draft.asset.asset_id,
        request=ProviderExecutionWorkerRequest(dry_run=False),
    )
    assert blocked.jobs[-1].status == "failed"
    assert blocked.jobs[-1].error_code == "live_worker_disabled"


def test_live_provider_budget_route_without_provider_secrets(tmp_path, monkeypatch):
    monkeypatch.delenv("KREA_API_KEY", raising=False)
    monkeypatch.setattr(multimedia_routes, "_STORE", MultimediaAssetStore(tmp_path))
    app = FastAPI()
    multimedia_routes.register_multimedia_routes(app)
    client = TestClient(app)

    created = client.post(
        "/multimedia/assets",
        json={
            "topic": "airframe composites",
            "target_minutes": 20,
            "mode": "video",
            "route_policy": "balanced",
            "sources": ["Composite airframes changed maintenance and weight tradeoffs."],
        },
    )
    asset_id = created.json()["asset"]["asset_id"]
    approved = client.post(f"/multimedia/assets/{asset_id}/approve-dry-run")
    assert approved.status_code == 200
    sufficient_budget = 50.0

    no_ack = client.post(
        f"/multimedia/assets/{asset_id}/prepare-live-execution",
        json={
            "max_budget_usd": sufficient_budget,
            "route_policy": "balanced",
            "operator_acknowledged_spend": False,
        },
    )
    assert no_ack.status_code == 200
    assert no_ack.json()["jobs"][-1]["error_code"] == "spend_not_acknowledged"

    monkeypatch.setenv("KREA_API_KEY", "fake-route-key")
    queued = client.post(
        f"/multimedia/assets/{asset_id}/prepare-live-execution",
        json={
            "max_budget_usd": sufficient_budget,
            "route_policy": "balanced",
            "operator_acknowledged_spend": True,
            "provider_families": ["krea"],
            "dry_run_revision_id": "rev-1",
        },
    )
    assert queued.status_code == 200
    latest = queued.json()["jobs"][-1]
    assert latest["status"] == "queued"
    assert latest["error_code"] is None
    assert "fake-route-key" not in latest["message"]

    worked = client.post(f"/multimedia/assets/{asset_id}/run-provider-worker", json={"dry_run": True})
    assert worked.status_code == 200
    statuses = [job["status"] for job in worked.json()["jobs"][-2:]]
    assert statuses == ["running", "succeeded"]
    assert "fake-route-key" not in worked.json()["jobs"][-1]["message"]
