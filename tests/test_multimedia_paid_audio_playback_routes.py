from __future__ import annotations

import io
from dataclasses import dataclass

from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from interfaces.research.api.multimedia_paid_audio_playback_routes import (
    PaidAudioPlaybackRouteRuntime,
    get_multimedia_paid_audio_playback_runtime,
    multimedia_paid_audio_playback_router,
)
from substrate.multimedia.read_model import MultimediaAudioProductionLink
from substrate.multimedia.verified_audio_playback import (
    AudioLearnedClaimMetadata,
    AudioPlaybackMetadata,
)
from substrate.multimedia.verified_playback import MediaByteRange, UnsatisfiableMediaRange


@dataclass
class FakePlayback:
    def metadata(self, *, asset_id: str, revision_id: str, owner_digest: str):
        assert owner_digest == "d" * 64
        return AudioPlaybackMetadata(
            asset_id,
            revision_id,
            "c" * 64,
            "a" * 64,
            10,
            12.5,
            ("ch-1",),
            1,
            1,
            1,
            (AudioLearnedClaimMetadata("ch-1", "claim", 1, "Next?"),),
        )

    def read(self, *, asset_id: str, revision_id: str, owner_digest: str, range_header: str | None):
        assert owner_digest == "d" * 64
        if range_header == "bytes=99-100":
            raise UnsatisfiableMediaRange(10)
        if range_header is None:
            return MediaByteRange(
                None, io.BytesIO(b"0123456789"), 0, 9, 10, "a" * 64, "c" * 64, "audio/wav"
            )
        assert range_header == "bytes=2-4"
        return MediaByteRange(b"234", None, 2, 4, 10, "a" * 64, "c" * 64, "audio/wav")


def _client(owner: str = "owner-1", *, receipt: str = "c" * 64) -> TestClient:
    app = FastAPI()

    @app.middleware("http")
    async def authenticate(request: Request, call_next):
        request.state.auth_method = "antiek_session_cookie"
        request.state.user_id = owner
        return await call_next(request)

    app.include_router(multimedia_paid_audio_playback_router, prefix="/api/multimedia")
    link = MultimediaAudioProductionLink(
        owner_identity_digest="d" * 64,
        asset_id="mm-1",
        revision_id="rev-1",
        receipt_sha256=receipt,
        audio_sha256="a" * 64,
        audio_size_bytes=10,
        duration_seconds=12.5,
        chapter_ids=("ch-1",),
        retention_marker_count=1,
        learned_claim_count=1,
        source_count=1,
    )
    runtime = PaidAudioPlaybackRouteRuntime(
        playback=FakePlayback(),  # type: ignore[arg-type]
        asset_authority_resolver=lambda asset_id, operator_id: (
            ("rev-1", link)
            if (asset_id, operator_id) == ("mm-1", "owner-1")
            else (_ for _ in ()).throw(LookupError())
        ),
    )
    app.dependency_overrides[get_multimedia_paid_audio_playback_runtime] = lambda: runtime
    return TestClient(app)


def test_paid_audio_metadata_and_ranges_are_owner_revision_and_link_bound() -> None:
    client = _client()
    metadata = client.get(
        "/api/multimedia/assets/mm-1/audio-playback", params={"revision_id": "rev-1"}
    )
    assert metadata.status_code == 200
    assert metadata.json()["audio_url"] == "/multimedia/assets/mm-1/audio-playback/rev-1/audio"
    partial = client.get(
        "/api/multimedia/assets/mm-1/audio-playback/rev-1/audio", headers={"Range": "bytes=2-4"}
    )
    assert partial.status_code == 206
    assert partial.content == b"234"
    assert partial.headers["content-range"] == "bytes 2-4/10"
    assert (
        client.get(
            "/api/multimedia/assets/mm-1/audio-playback/rev-1/audio",
            headers={"Range": "bytes=99-100"},
        ).status_code
        == 416
    )


def test_paid_audio_foreign_stale_and_link_tamper_fail_closed() -> None:
    assert (
        _client("owner-2")
        .get("/api/multimedia/assets/mm-1/audio-playback", params={"revision_id": "rev-1"})
        .status_code
        == 404
    )
    assert (
        _client()
        .get("/api/multimedia/assets/mm-1/audio-playback", params={"revision_id": "old"})
        .status_code
        == 409
    )
    assert (
        _client(receipt="b" * 64)
        .get("/api/multimedia/assets/mm-1/audio-playback", params={"revision_id": "rev-1"})
        .status_code
        == 409
    )
