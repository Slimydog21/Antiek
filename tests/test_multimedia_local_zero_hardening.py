from __future__ import annotations

import hashlib
import hmac
import json
from datetime import UTC, datetime

import duckdb
import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from interfaces.research.api import multimedia_routes
from interfaces.research.api.multimedia_hardening_routes import (
    MultimediaHardeningRuntime,
    get_multimedia_hardening_runtime,
)
from substrate.multimedia.local_provider_exclusion import LocalZeroEvidenceConflict
from substrate.multimedia.local_zero_cost_evidence import (
    LocalZeroExternalCostEvidenceV1,
    LocalZeroRunAuthorityV1,
)
from substrate.multimedia.read_model import MultimediaAssetStore
from substrate.multimedia.ship_cost_snapshot import MultimediaShipCostEvidenceConflict

NOW = datetime(2026, 7, 13, tzinfo=UTC)
PAID_KEY = b"paid-provider-signing-key-material"
PAID_SNAPSHOT_KEY = b"paid-snapshot-signing-key-material"
LOCAL_KEY = b"local-zero-signing-key-material-32"


def _canonical(value: object) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("ascii")


def _audio_evidence(
    *, owner_id: str, asset_id: str, revision_id: str
) -> LocalZeroExternalCostEvidenceV1:
    owner_digest = hashlib.sha256(owner_id.encode()).hexdigest()
    input_digest = "1" * 64
    config_digest = "2" * 64
    run_id = "mmlocalaudible_" + hashlib.sha256(
        f"{owner_digest}\0{input_digest}\0{config_digest}".encode("ascii")
    ).hexdigest()
    authority = LocalZeroRunAuthorityV1(
        role="local_audible",
        run_id=run_id,
        input_digest=input_digest,
        config_digest=config_digest,
        terminal_status="registered",
        artifact_digest="3" * 64,
        receipt_digest="4" * 64,
        updated_at="2026-07-13T00:00:00Z",
    )
    unsigned = {
        "schema_version": "antiek.local-zero-external-cost-evidence.v1",
        "owner_identity_digest": owner_digest,
        "asset_id": asset_id,
        "revision_id": revision_id,
        "generated_at_cutoff": "2026-07-13T00:00:00Z",
        "run_kind": "audio",
        "basis": "local_registered_zero_external_provider_charge",
        "authorities": (authority.model_dump(mode="json"),),
        "production_receipt_digest": "4" * 64,
        "current_link_digest": "5" * 64,
        "excluded_revision_ids": (revision_id,),
        "provider_execution_count": 0,
        "external_cost_cents": 0,
        "limitation": (
            "Zero external provider charge is limited to the exact parent revision; v1 "
            "defines no provider child-revision namespace for AudibleRun."
        ),
    }
    evidence_id = "mmlocalzero_" + hashlib.sha256(_canonical(unsigned)).hexdigest()
    signed = {"evidence_id": evidence_id, **unsigned}
    mac = hmac.new(LOCAL_KEY, _canonical(signed), hashlib.sha256).hexdigest()
    return LocalZeroExternalCostEvidenceV1(**signed, snapshot_mac=mac)


def _video_evidence(
    *, owner_id: str, asset_id: str, revision_id: str
) -> LocalZeroExternalCostEvidenceV1:
    owner_digest = hashlib.sha256(owner_id.encode()).hexdigest()
    narration_input = "6" * 64
    narration_config = "7" * 64
    narration_id = "mmlocalrun_" + hashlib.sha256(
        f"{owner_digest}\0{narration_input}\0{narration_config}".encode()
    ).hexdigest()
    video_input = "8" * 64
    video_config = "9" * 64
    video_id = "mmlocalvideo_" + hashlib.sha256(
        f"{narration_id}\0{owner_digest}\0{video_input}\0{video_config}".encode()
    ).hexdigest()
    authorities = (
        LocalZeroRunAuthorityV1(
            role="local_narration",
            run_id=narration_id,
            input_digest=narration_input,
            config_digest=narration_config,
            terminal_status="narration_succeeded",
            artifact_digest="a" * 64,
            updated_at="2026-07-13T00:00:00Z",
        ),
        LocalZeroRunAuthorityV1(
            role="local_video",
            run_id=video_id,
            input_digest=video_input,
            config_digest=video_config,
            terminal_status="registered",
            artifact_digest="b" * 64,
            receipt_digest="c" * 64,
            updated_at="2026-07-13T00:00:00Z",
        ),
    )
    unsigned = {
        "schema_version": "antiek.local-zero-external-cost-evidence.v1",
        "owner_identity_digest": owner_digest,
        "asset_id": asset_id,
        "revision_id": revision_id,
        "generated_at_cutoff": "2026-07-13T00:00:00Z",
        "run_kind": "video",
        "basis": "local_registered_zero_external_provider_charge",
        "authorities": tuple(row.model_dump(mode="json") for row in authorities),
        "production_receipt_digest": "c" * 64,
        "current_link_digest": "d" * 64,
        "excluded_revision_ids": tuple(sorted((revision_id, "tts-" + "e" * 32))),
        "provider_execution_count": 0,
        "external_cost_cents": 0,
        "limitation": (
            "Zero external provider charge is limited to the exact parent revision and "
            "deterministic narration child revisions represented by this registered local video."
        ),
    }
    evidence_id = "mmlocalzero_" + hashlib.sha256(_canonical(unsigned)).hexdigest()
    signed = {"evidence_id": evidence_id, **unsigned}
    mac = hmac.new(LOCAL_KEY, _canonical(signed), hashlib.sha256).hexdigest()
    return LocalZeroExternalCostEvidenceV1(**signed, snapshot_mac=mac)


def _client(
    tmp_path, monkeypatch: pytest.MonkeyPatch, *, video_backend=None, audio_backend=None
):  # noqa: ANN001, ANN202
    store = MultimediaAssetStore(tmp_path / "assets")
    db_path = tmp_path / "accounting.duckdb"
    with duckdb.connect(str(db_path)) as connection:
        connection.execute(
            "CREATE TABLE multimedia_provider_executions "
            "(operator_id TEXT, asset_id TEXT, revision_id TEXT)"
        )
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
            db_path=str(db_path),
            signing_key=PAID_KEY,
            snapshot_key=PAID_SNAPSHOT_KEY,
            local_zero_snapshot_key=LOCAL_KEY,
            local_video_backend=video_backend,
            local_audio_backend=audio_backend,
            clock=lambda: NOW,
        )
    )
    return TestClient(app), store


def test_api_paid_unavailable_falls_back_to_selected_audio_backend(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:  # noqa: ANN001
    calls = 0

    def audio_backend(*, owner_id, asset_id, revision_id, now):  # noqa: ANN001, ANN202
        nonlocal calls
        calls += 1
        assert now == NOW
        return _audio_evidence(
            owner_id=owner_id, asset_id=asset_id, revision_id=revision_id
        )

    client, _store = _client(tmp_path, monkeypatch, audio_backend=audio_backend)
    created = client.post(
        "/multimedia/assets",
        json={"topic": "jet history", "target_minutes": 15, "mode": "audio"},
    ).json()
    response = client.post(f"/multimedia/assets/{created['asset']['asset_id']}/hardening")
    assert response.status_code == 200
    report = response.json()["hardening_report"]
    assert calls == 1
    assert report["cost_snapshot"] is None
    assert report["local_zero_cost_evidence"]["external_cost_cents"] == 0


def test_api_paid_unavailable_falls_back_to_selected_video_backend(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:  # noqa: ANN001
    calls = 0

    def video_backend(*, owner_id, asset_id, revision_id, now):  # noqa: ANN001, ANN202
        nonlocal calls
        calls += 1
        assert now == NOW
        return _video_evidence(
            owner_id=owner_id, asset_id=asset_id, revision_id=revision_id
        )

    client, _store = _client(tmp_path, monkeypatch, video_backend=video_backend)
    created = client.post(
        "/multimedia/assets",
        json={"topic": "jet history", "target_minutes": 15, "mode": "video"},
    ).json()
    response = client.post(f"/multimedia/assets/{created['asset']['asset_id']}/hardening")
    assert response.status_code == 200
    report = response.json()["hardening_report"]
    assert calls == 1
    assert report["cost_snapshot"] is None
    assert report["local_zero_cost_evidence"]["run_kind"] == "video"


def test_audio_asset_does_not_consult_video_backend(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:  # noqa: ANN001
    def video_backend(**_kwargs):  # noqa: ANN003, ANN202
        raise AssertionError("audio hardening must not consult the video backend")

    client, _store = _client(
        tmp_path, monkeypatch, video_backend=video_backend
    )
    created = client.post(
        "/multimedia/assets",
        json={"topic": "jet history", "target_minutes": 15, "mode": "audio"},
    ).json()
    response = client.post(f"/multimedia/assets/{created['asset']['asset_id']}/hardening")
    assert response.status_code == 409
    assert response.json()["detail"] == "evidence_unavailable"


def test_paid_conflict_never_calls_local_fallback(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:  # noqa: ANN001
    calls = 0

    def audio_backend(**_kwargs):  # noqa: ANN003, ANN202
        nonlocal calls
        calls += 1
        raise AssertionError("local fallback must not run")

    client, _store = _client(tmp_path, monkeypatch, audio_backend=audio_backend)
    created = client.post(
        "/multimedia/assets",
        json={"topic": "jet history", "target_minutes": 15, "mode": "audio"},
    ).json()
    monkeypatch.setattr(
        multimedia_routes,
        "build_multimedia_ship_cost_snapshot",
        lambda **_kwargs: (_ for _ in ()).throw(
            MultimediaShipCostEvidenceConflict("evidence_conflict")
        ),
    )
    response = client.post(f"/multimedia/assets/{created['asset']['asset_id']}/hardening")
    assert response.status_code == 409
    assert response.json()["detail"] == "evidence_conflict"
    assert calls == 0


def test_read_model_rejects_both_cost_authorities_before_persisting(tmp_path) -> None:  # noqa: ANN001
    store = MultimediaAssetStore(tmp_path / "assets")
    draft = store.create_draft(
        multimedia_routes.CreateMultimediaDraftRequest(
            topic="jet history", target_minutes=15, mode="audio"
        ),
        owner_id="alice",
    )
    evidence = _audio_evidence(
        owner_id="alice",
        asset_id=draft.asset.asset_id,
        revision_id=draft.asset.revision_id,
    )
    with pytest.raises(LocalZeroEvidenceConflict, match="evidence_conflict"):
        store.run_hardening(
            draft.asset.asset_id,
            owner_id="alice",
            cost_snapshot=object(),  # type: ignore[arg-type]
            local_zero_cost_evidence=evidence,
            snapshot_key=LOCAL_KEY,
        )
