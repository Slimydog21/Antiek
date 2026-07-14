from __future__ import annotations

import hashlib
import hmac
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from pydantic import ValidationError

from interfaces.research.api import multimedia_routes
from interfaces.research.api.multimedia_hardening_routes import (
    MultimediaHardeningRuntime,
    get_multimedia_hardening_runtime,
)
from substrate.multimedia.paid_video_cost_authority import (
    PaidRegisteredVideoCostAuthorityV1,
    build_paid_registered_video_cost_authority,
    verify_paid_registered_video_cost_authority,
)
from substrate.multimedia.production_cost_projection import (
    ProductionByteConstituentV1,
    ProductionByteProjectionV1,
)
from substrate.multimedia.read_model import (
    MultimediaAssetStore,
    MultimediaAudioProductionLink,
    MultimediaProductionLink,
)
from substrate.multimedia.ship_cost_snapshot import (
    MultimediaShipCostEvidenceConflict,
    MultimediaShipCostEvidenceUnavailable,
    MultimediaShipCostExecutionV1,
    MultimediaShipCostSnapshotV1,
)

DIRECT_KEY = b"direct-paid-cost-snapshot-domain-1"
PRODUCTION_KEY = b"production-byte-cost-domain-key-2"
SIGNING_KEY = b"provider-execution-signing-domain-3"
NOW = datetime(2026, 7, 14, 8, 0, tzinfo=UTC)
CUTOFF = "2026-07-14T08:00:00.000000Z"


def _canonical(value: object) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        ensure_ascii=True,
        allow_nan=False,
        separators=(",", ":"),
    ).encode("ascii")


def _direct(owner_id: str, asset_id: str, revision_id: str) -> MultimediaShipCostSnapshotV1:
    execution = MultimediaShipCostExecutionV1(
        execution_id="execution-direct",
        authorization_id="authorization-direct",
        provider="krea",
        model="imagen",
        route_policy="balanced",
        capability="image",
        catalog_version="v1",
        catalog_digest="a" * 64,
        charged_cents=17,
        settled_at=CUTOFF,
    )
    unsigned = {
        "schema_version": "antiek.multimedia-ship-cost-snapshot.v1",
        "owner_identity_digest": hashlib.sha256(owner_id.encode()).hexdigest(),
        "asset_id": asset_id,
        "revision_id": revision_id,
        "generated_at_cutoff": CUTOFF,
        "basis": "direct_settled_provider_executions",
        "executions": (execution.model_dump(mode="json"),),
        "charged_cents": 17,
    }
    evidence_id = "mmscost_" + hashlib.sha256(_canonical(unsigned)).hexdigest()
    signed = {"evidence_id": evidence_id, **unsigned}
    return MultimediaShipCostSnapshotV1(
        **signed,
        snapshot_mac=hmac.new(DIRECT_KEY, _canonical(signed), hashlib.sha256).hexdigest(),
    )


def _projection(
    owner_id: str,
    asset_id: str,
    revision_id: str,
    receipt_digest: str,
) -> ProductionByteProjectionV1:
    constituent = ProductionByteConstituentV1(
        role="narration",
        chapter_id="chapter-1",
        execution_revision="narration-child",
        execution_id="execution-narration",
        authorization_id="authorization-narration",
        provider="elevenlabs",
        model="multilingual-v2",
        capability="text-to-speech",
        charged_cents=29,
        settled_at=CUTOFF,
    )
    unsigned = {
        "schema_version": "antiek.production-byte-projection.v1",
        "owner_identity_digest": hashlib.sha256(owner_id.encode()).hexdigest(),
        "asset_id": asset_id,
        "revision_id": revision_id,
        "generated_at_cutoff": CUTOFF,
        "basis": "production_byte_contributing_settled_provider_executions",
        "production_receipt_digest": receipt_digest,
        "reviewed_set_id": "reviewed-set-1",
        "narration_run_id": "narration-run-1",
        "constituents": (constituent.model_dump(mode="json"),),
        "charged_cents": 29,
    }
    evidence_id = "mmprodbyte_" + hashlib.sha256(_canonical(unsigned)).hexdigest()
    signed = {"evidence_id": evidence_id, **unsigned}
    return ProductionByteProjectionV1(
        **signed,
        projection_mac=hmac.new(
            PRODUCTION_KEY, _canonical(signed), hashlib.sha256
        ).hexdigest(),
    )


def _authority(
    owner_id: str, asset_id: str, revision_id: str, receipt_digest: str
) -> PaidRegisteredVideoCostAuthorityV1:
    return build_paid_registered_video_cost_authority(
        direct_cost_snapshot=_direct(owner_id, asset_id, revision_id),
        production_byte_projection=_projection(
            owner_id, asset_id, revision_id, receipt_digest
        ),
        direct_snapshot_key=DIRECT_KEY,
        production_snapshot_key=PRODUCTION_KEY,
        owner_id=owner_id,
        asset_id=asset_id,
        revision_id=revision_id,
        production_receipt_digest=receipt_digest,
    )


def test_compound_authority_binds_cutoff_identity_receipt_and_distinct_keys() -> None:
    authority = _authority("alice", "asset-1", "rev-1", "c" * 64)
    assert authority.direct_cost_snapshot.charged_cents == 17
    assert authority.production_byte_projection.charged_cents == 29
    verify_paid_registered_video_cost_authority(
        authority,
        direct_snapshot_key=DIRECT_KEY,
        production_snapshot_key=PRODUCTION_KEY,
        owner_id="alice",
        asset_id="asset-1",
        revision_id="rev-1",
        production_receipt_digest="c" * 64,
    )
    with pytest.raises(MultimediaShipCostEvidenceConflict):
        verify_paid_registered_video_cost_authority(
            authority,
            direct_snapshot_key=DIRECT_KEY,
            production_snapshot_key=DIRECT_KEY,
            owner_id="alice",
            asset_id="asset-1",
            revision_id="rev-1",
            production_receipt_digest="c" * 64,
        )
    with pytest.raises(MultimediaShipCostEvidenceConflict):
        verify_paid_registered_video_cost_authority(
            authority,
            direct_snapshot_key=DIRECT_KEY,
            production_snapshot_key=PRODUCTION_KEY,
            owner_id="alice",
            asset_id="asset-1",
            revision_id="rev-1",
            production_receipt_digest="d" * 64,
        )


def test_builder_reports_cross_child_cutoff_as_stable_conflict() -> None:
    direct = _direct("alice", "asset-1", "rev-1")
    projection = _projection("alice", "asset-1", "rev-1", "c" * 64).model_copy(
        update={"generated_at_cutoff": "2026-07-14T08:00:01.000000Z"}
    )
    with pytest.raises(MultimediaShipCostEvidenceConflict):
        build_paid_registered_video_cost_authority(
            direct_cost_snapshot=direct,
            production_byte_projection=projection,
            direct_snapshot_key=DIRECT_KEY,
            production_snapshot_key=PRODUCTION_KEY,
            owner_id="alice",
            asset_id="asset-1",
            revision_id="rev-1",
            production_receipt_digest="c" * 64,
        )


def test_compound_authority_rejects_different_child_cutoffs() -> None:
    direct = _direct("alice", "asset-1", "rev-1")
    projection = _projection("alice", "asset-1", "rev-1", "c" * 64)
    with pytest.raises(ValidationError):
        PaidRegisteredVideoCostAuthorityV1(
            generated_at_cutoff=CUTOFF,
            direct_cost_snapshot=direct,
            production_byte_projection=projection.model_copy(
                update={"generated_at_cutoff": "2026-07-14T08:00:01.000000Z"}
            ),
        )


def _client(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    projection_backend,
) -> tuple[TestClient, MultimediaAssetStore]:  # noqa: ANN001
    store = MultimediaAssetStore(tmp_path / "assets")
    monkeypatch.setattr(multimedia_routes, "_STORE", store)
    app = FastAPI()

    @app.middleware("http")
    async def identity(request: Request, call_next):  # type: ignore[no-untyped-def]
        request.state.auth_method = "bearer_token"
        request.state.user_id = "alice"
        return await call_next(request)

    multimedia_routes.register_multimedia_routes(app)
    app.dependency_overrides[get_multimedia_hardening_runtime] = lambda: (
        MultimediaHardeningRuntime(
            db_path=str(tmp_path / "unused.duckdb"),
            signing_key=SIGNING_KEY,
            snapshot_key=DIRECT_KEY,
            production_snapshot_key=PRODUCTION_KEY,
            production_video_backend=projection_backend,
            clock=lambda: NOW,
        )
    )
    return TestClient(app), store


def test_registered_paid_video_endpoint_persists_one_compound_family(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[datetime] = []
    receipt_digest = "c" * 64

    def backend(*, owner_id, asset_id, revision_id, now):  # noqa: ANN001, ANN202
        calls.append(now)
        return _projection(owner_id, asset_id, revision_id, receipt_digest)

    client, store = _client(tmp_path, monkeypatch, projection_backend=backend)
    created = client.post(
        "/multimedia/assets",
        json={
            "topic": "jet history",
            "target_minutes": 15,
            "mode": "video",
            "route_policy": "balanced",
            "sources": ["Jet propulsion history is grounded in reviewed evidence."],
            "selected_arc_ids": ["history"],
        },
    ).json()
    asset = created["asset"]
    client.post(f"/multimedia/assets/{asset['asset_id']}/approve-dry-run")
    store.attach_production_link(
        asset["asset_id"],
        MultimediaProductionLink(
            owner_identity_digest=hashlib.sha256(b"alice").hexdigest(),
            asset_id=asset["asset_id"],
            revision_id=asset["revision_id"],
            receipt_sha256=receipt_digest,
            video_sha256="a" * 64,
            audio_sha256="b" * 64,
            duration_seconds=90,
            width_px=1280,
            height_px=720,
            chapter_ids=("chapter-1",),
        ),
        expected_revision_id=asset["revision_id"],
        owner_id="alice",
    )
    monkeypatch.setattr(
        multimedia_routes,
        "build_multimedia_ship_cost_snapshot",
        lambda **_kwargs: _direct("alice", asset["asset_id"], asset["revision_id"]),
    )

    response = client.post(f"/multimedia/assets/{asset['asset_id']}/hardening")

    assert response.status_code == 200
    report = response.json()["hardening_report"]
    assert calls == [NOW]
    assert report["cost_snapshot"] is None
    assert report["local_zero_cost_evidence"] is None
    assert report["paid_registered_video_cost_authority"][
        "generated_at_cutoff"
    ] == CUTOFF


def test_projection_failure_never_falls_back_and_registered_paid_audio_is_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def unavailable(**_kwargs):  # noqa: ANN003, ANN202
        raise MultimediaShipCostEvidenceUnavailable("evidence_unavailable")

    client, store = _client(tmp_path, monkeypatch, projection_backend=unavailable)
    created = client.post(
        "/multimedia/assets",
        json={
            "topic": "jet history",
            "target_minutes": 15,
            "mode": "video",
            "route_policy": "balanced",
            "sources": ["Jet propulsion history is grounded in reviewed evidence."],
            "selected_arc_ids": ["history"],
        },
    ).json()["asset"]
    client.post(f"/multimedia/assets/{created['asset_id']}/approve-dry-run")
    store.attach_production_link(
        created["asset_id"],
        MultimediaProductionLink(
            owner_identity_digest=hashlib.sha256(b"alice").hexdigest(),
            asset_id=created["asset_id"],
            revision_id=created["revision_id"],
            receipt_sha256="c" * 64,
            video_sha256="a" * 64,
            audio_sha256="b" * 64,
            duration_seconds=90,
            width_px=1280,
            height_px=720,
            chapter_ids=("chapter-1",),
        ),
        expected_revision_id=created["revision_id"],
        owner_id="alice",
    )
    monkeypatch.setattr(
        multimedia_routes,
        "build_multimedia_ship_cost_snapshot",
        lambda **kwargs: _direct("alice", kwargs["asset_id"], kwargs["revision_id"]),
    )
    response = client.post(f"/multimedia/assets/{created['asset_id']}/hardening")
    assert response.status_code == 409
    assert response.json()["detail"] == "evidence_unavailable"


def test_direct_unavailable_registered_paid_video_never_calls_local_fallback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    local_calls = 0

    def projection_backend(**_kwargs):  # noqa: ANN003, ANN202
        raise AssertionError("projection is unreachable without direct evidence")

    client, store = _client(
        tmp_path, monkeypatch, projection_backend=projection_backend
    )
    runtime = client.app.dependency_overrides[get_multimedia_hardening_runtime]()

    def local_backend(**_kwargs):  # noqa: ANN003, ANN202
        nonlocal local_calls
        local_calls += 1
        raise AssertionError("paid registration must not use local-zero fallback")

    client.app.dependency_overrides[get_multimedia_hardening_runtime] = lambda: (
        MultimediaHardeningRuntime(
            db_path=runtime.db_path,
            signing_key=runtime.signing_key,
            snapshot_key=runtime.snapshot_key,
            production_snapshot_key=runtime.production_snapshot_key,
            local_zero_snapshot_key=b"local-zero-independent-domain-key",
            production_video_backend=projection_backend,
            local_video_backend=local_backend,
            clock=runtime.clock,
        )
    )
    created = client.post(
        "/multimedia/assets",
        json={
            "topic": "jet history",
            "target_minutes": 15,
            "mode": "video",
            "route_policy": "balanced",
            "sources": ["Jet propulsion history is grounded in reviewed evidence."],
            "selected_arc_ids": ["history"],
        },
    ).json()["asset"]
    client.post(f"/multimedia/assets/{created['asset_id']}/approve-dry-run")
    store.attach_production_link(
        created["asset_id"],
        MultimediaProductionLink(
            owner_identity_digest=hashlib.sha256(b"alice").hexdigest(),
            asset_id=created["asset_id"],
            revision_id=created["revision_id"],
            receipt_sha256="c" * 64,
            video_sha256="a" * 64,
            audio_sha256="b" * 64,
            duration_seconds=90,
            width_px=1280,
            height_px=720,
            chapter_ids=("chapter-1",),
        ),
        expected_revision_id=created["revision_id"],
        owner_id="alice",
    )

    response = client.post(f"/multimedia/assets/{created['asset_id']}/hardening")

    assert response.status_code == 409
    assert response.json()["detail"] == "evidence_unavailable"
    assert local_calls == 0

    monkeypatch.setattr(
        multimedia_routes,
        "build_multimedia_ship_cost_snapshot",
        lambda **kwargs: _direct("alice", kwargs["asset_id"], kwargs["revision_id"]),
    )
    audio = client.post(
        "/multimedia/assets",
        json={
            "topic": "jet history on a run",
            "target_minutes": 15,
            "mode": "audio",
            "route_policy": "balanced",
            "sources": ["Jet propulsion history is grounded in reviewed evidence."],
            "selected_arc_ids": ["history"],
        },
    ).json()["asset"]
    client.post(f"/multimedia/assets/{audio['asset_id']}/approve-dry-run")
    store.attach_audio_production_link(
        audio["asset_id"],
        MultimediaAudioProductionLink(
            owner_identity_digest=hashlib.sha256(b"alice").hexdigest(),
            asset_id=audio["asset_id"],
            revision_id=audio["revision_id"],
                receipt_sha256="d" * 64,
                audio_sha256="e" * 64,
                audio_size_bytes=4096,
                duration_seconds=90,
                chapter_ids=("chapter-1",),
                retention_marker_count=1,
                learned_claim_count=1,
                source_count=1,
        ),
        expected_revision_id=audio["revision_id"],
        owner_id="alice",
    )
    response = client.post(f"/multimedia/assets/{audio['asset_id']}/hardening")
    assert response.status_code == 409
    assert response.json()["detail"] == "evidence_unavailable"
