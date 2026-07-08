"""SPR-09 multimedia API persistence/read-model tests."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from interfaces.research.api import multimedia_routes
from substrate.multimedia.read_model import (
    CreateMultimediaDraftRequest,
    MultimediaAssetStore,
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

    steered = store.apply_steering(
        draft.asset.asset_id,
        SteeringRequest(prompt="go deeper on engines in chapter 2"),
    )
    assert steered.asset.parent_revision_id == "rev-1"
    assert steered.asset.steering_event_id
    assert steered.latest_steering_intent is not None

    hardened = store.run_hardening(draft.asset.asset_id)
    assert hardened.hardening_report is not None
    assert hardened.hardening_report.manual_gate_ids == ("rights_and_publication",)

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
    assert "rights_and_publication" in report["manual_gate_ids"]

    listed = client.get("/multimedia/assets")
    assert listed.status_code == 200
    assert listed.json()["count"] == 1

    missing = client.get("/multimedia/assets/mm-missing")
    assert missing.status_code == 404


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
