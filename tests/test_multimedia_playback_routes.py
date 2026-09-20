from __future__ import annotations

import io
import tempfile
from dataclasses import dataclass
from unittest.mock import Mock

from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

import interfaces.research.api.multimedia_routes as multimedia_routes_module
from interfaces.research.api.multimedia_playback_routes import (
    MultimediaPlaybackRouteRuntime,
    get_multimedia_playback_runtime,
    multimedia_playback_router,
    multimedia_playback_runtime_from_environment,
)
from substrate.multimedia.read_model import (
    CreateMultimediaDraftRequest,
    MultimediaAssetStore,
    MultimediaProductionLink,
)
from substrate.multimedia.verified_playback import (
    MediaByteRange,
    PlaybackMediaMetadata,
    UnsatisfiableMediaRange,
)

last_stream: io.BytesIO | None = None


@dataclass
class FakePlayback:
    def metadata(self, *, asset_id: str, revision_id: str) -> PlaybackMediaMetadata:
        return PlaybackMediaMetadata(asset_id, revision_id, "c" * 64, 12.5, "a" * 64, "b" * 64, 10, 8, 1920, 1080, ("ch-1",))

    def read(self, *, asset_id: str, revision_id: str, kind: str, range_header: str | None) -> MediaByteRange:
        global last_stream
        assert (asset_id, revision_id, kind) == ("mm-1", "rev-1", "video")
        if range_header == "bytes=99-100":
            raise UnsatisfiableMediaRange(10)
        if range_header is None:
            last_stream = io.BytesIO(b"full-video")
            return MediaByteRange(None, last_stream, 0, 9, 10, "a" * 64, "c" * 64, "video/mp4")
        assert range_header == "bytes=2-4"
        return MediaByteRange(b"deo", None, 2, 4, 10, "a" * 64, "c" * 64, "video/mp4")


def _client(owner: str = "owner-1", production_registrar=None) -> TestClient:
    app = FastAPI()

    @app.middleware("http")
    async def authenticate(request: Request, call_next):
        request.state.auth_method = "antiek_session_cookie"
        request.state.user_id = owner
        return await call_next(request)

    app.include_router(multimedia_playback_router, prefix="/api/multimedia")
    link = MultimediaProductionLink(
        owner_identity_digest="d" * 64,
        asset_id="mm-1",
        revision_id="rev-1",
        receipt_sha256="c" * 64,
        video_sha256="a" * 64,
        audio_sha256="b" * 64,
        duration_seconds=12.5,
        width_px=1920,
        height_px=1080,
        chapter_ids=("ch-1",),
    )
    runtime = MultimediaPlaybackRouteRuntime(
        playback=FakePlayback(),  # type: ignore[arg-type]
        asset_authority_resolver=lambda asset_id, operator_id: ("rev-1", link)
        if (asset_id, operator_id) == ("mm-1", "owner-1")
        else (_ for _ in ()).throw(LookupError()),
        production_registrar=production_registrar
        or (lambda *_args: (_ for _ in ()).throw(LookupError())),
    )
    app.dependency_overrides[get_multimedia_playback_runtime] = lambda: runtime
    return TestClient(app)


def test_metadata_and_partial_media_are_owner_and_revision_bound() -> None:
    client = _client()
    metadata = client.get("/api/multimedia/assets/mm-1/playback", params={"revision_id": "rev-1"})
    assert metadata.status_code == 200
    assert metadata.json()["video_url"] == "/multimedia/assets/mm-1/playback/rev-1/video"

    media = client.get(
        "/api/multimedia/assets/mm-1/playback/rev-1/video", headers={"Range": "bytes=2-4"}
    )
    assert media.status_code == 206
    assert media.content == b"deo"
    assert media.headers["content-range"] == "bytes 2-4/10"
    assert media.headers["cache-control"] == "private, no-store"

    unsatisfiable = client.get(
        "/api/multimedia/assets/mm-1/playback/rev-1/video", headers={"Range": "bytes=99-100"}
    )
    assert unsatisfiable.status_code == 416
    assert unsatisfiable.headers["content-range"] == "bytes */10"

    full = client.get("/api/multimedia/assets/mm-1/playback/rev-1/video")
    assert full.status_code == 200
    assert full.content == b"full-video"
    assert last_stream is not None and last_stream.closed


def test_foreign_and_stale_requests_fail_without_playback_disclosure() -> None:
    foreign = _client("owner-2").get(
        "/api/multimedia/assets/mm-1/playback", params={"revision_id": "rev-1"}
    )
    assert foreign.status_code == 404
    stale = _client().get(
        "/api/multimedia/assets/mm-1/playback", params={"revision_id": "rev-old"}
    )
    assert stale.status_code == 409


def test_registration_route_returns_only_the_registrar_bound_record() -> None:
    with tempfile.TemporaryDirectory() as root:
        store = MultimediaAssetStore(root)
        draft = store.create_draft(
            CreateMultimediaDraftRequest(
                topic="Production registration",
                target_minutes=15,
                mode="video",
                route_policy="balanced",
                sources=("Early production history is grounded in reviewed evidence.",),
                selected_arc_ids=("history",),
            ),
            owner_id="owner-1",
        )
        ready = store.approve_dry_run(draft.asset.asset_id, owner_id="owner-1")
        link = MultimediaProductionLink(
            owner_identity_digest=ready.asset.owner_user_id,
            asset_id=ready.asset.asset_id,
            revision_id="rev-1",
            receipt_sha256="c" * 64,
            video_sha256="a" * 64,
            audio_sha256="b" * 64,
            duration_seconds=12.5,
            width_px=1920,
            height_px=1080,
            chapter_ids=("ch-1",),
        )
        produced = store.attach_production_link(
            ready.asset.asset_id,
            link,
            expected_revision_id="rev-1",
            owner_id="owner-1",
        )
        registrar = Mock(return_value=produced)
        response = _client(production_registrar=registrar).post(
            f"/api/multimedia/assets/{ready.asset.asset_id}/production-registration",
            json={"expected_revision_id": "rev-1"},
        )
        assert response.status_code == 200
        assert response.json()["production_link"]["receipt_sha256"] == "c" * 64
        registrar.assert_called_once_with(ready.asset.asset_id, "rev-1", "owner-1")


def test_environment_configuration_is_all_or_nothing(tmp_path) -> None:
    assert multimedia_playback_runtime_from_environment({}) is None
    incomplete = {"ANTIEK_MULTIMEDIA_PLAYBACK_ENABLED": "true"}
    try:
        multimedia_playback_runtime_from_environment(incomplete)
    except RuntimeError as exc:
        assert "incomplete" in str(exc)
    else:
        raise AssertionError("partial playback configuration must fail")

    configured = {
        "ANTIEK_MULTIMEDIA_PLAYBACK_ENABLED": "true",
        "ANTIEK_MULTIMEDIA_VIDEO_RECEIPT_ROOT": str(tmp_path),
        "ANTIEK_MULTIMEDIA_VIDEO_RECEIPT_KEY_HEX": "11" * 32,
        "ANTIEK_MULTIMEDIA_NARRATION_KEY_HEX": "22" * 32,
        "ANTIEK_MULTIMEDIA_VISUAL_KEY_HEX": "33" * 32,
        "ANTIEK_MULTIMEDIA_RENDER_KEY_HEX": "44" * 32,
    }
    assert multimedia_playback_runtime_from_environment(configured) is not None

    configured["ANTIEK_MULTIMEDIA_VIDEO_RECEIPT_ROOT"] = str(tmp_path / "missing")
    try:
        multimedia_playback_runtime_from_environment(configured)
    except ValueError as exc:
        assert "receipt root" in str(exc)
    else:
        raise AssertionError("invalid playback root must fail at configuration time")


def test_app_registration_composes_playback_runtime_fields(monkeypatch) -> None:
    link = MultimediaProductionLink(
        owner_identity_digest="d" * 64,
        asset_id="mm-1",
        revision_id="rev-1",
        receipt_sha256="c" * 64,
        video_sha256="a" * 64,
        audio_sha256="b" * 64,
        duration_seconds=12.5,
        width_px=1920,
        height_px=1080,
        chapter_ids=("ch-1",),
    )
    runtime = MultimediaPlaybackRouteRuntime(
        playback=FakePlayback(),  # type: ignore[arg-type]
        asset_authority_resolver=lambda *_args: ("rev-1", link),
        production_registrar=lambda *_args: (_ for _ in ()).throw(LookupError()),
    )
    monkeypatch.setattr(
        multimedia_routes_module, "multimedia_reconciliation_runtime_from_environment", lambda: None
    )
    monkeypatch.setattr(
        multimedia_routes_module, "multimedia_knowledge_runtime_from_environment", lambda: None
    )
    monkeypatch.setattr(
        multimedia_routes_module, "multimedia_playback_runtime_from_environment", lambda: runtime
    )
    app = FastAPI()
    multimedia_routes_module.register_multimedia_routes(app)
    configured = app.dependency_overrides[get_multimedia_playback_runtime]()
    assert configured.playback is runtime.playback
    assert configured.asset_authority_resolver
    assert configured.production_registrar
