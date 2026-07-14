from __future__ import annotations

import hashlib
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from interfaces.research.api.multimedia_local_audible_routes import (
    get_multimedia_local_audible_runtime,
    get_multimedia_local_audible_runtime_optional,
)
from interfaces.research.api.multimedia_local_audible_runtime import (
    MultimediaLocalAudibleRuntime,
)
from interfaces.research.api.multimedia_reconciliation_routes import (
    authenticated_multimedia_operator,
)
from interfaces.research.api.multimedia_routes import multimedia_router
from substrate.multimedia.local_audible_workstation import (
    LocalAudiblePreparedChapter,
    LocalAudiblePreparedSet,
)
from substrate.multimedia.read_model import MultimediaAudioProductionLink
from substrate.multimedia.verified_audio_playback import (
    AudioLearnedClaimMetadata,
    AudioPlaybackMetadata,
)
from substrate.multimedia.verified_playback import MediaByteRange

SET_ID = "mmlocalaudibleset_" + "a" * 64
OWNER_DIGEST = hashlib.sha256(b"owner-1").hexdigest()


def _prepared(status: str = "ready_to_produce") -> LocalAudiblePreparedSet:
    return LocalAudiblePreparedSet(
        set_id=SET_ID,
        asset_id="asset-1",
        revision_id="revision-1",
        status=status,  # type: ignore[arg-type]
        recoverable=status in {"preparation_unknown", "production_unknown"},
        playback_ready=status == "registered",
        total_duration_seconds=10,
        chapters=(
            LocalAudiblePreparedChapter(
                chapter_id="chapter-1",
                title="Flow",
                span_count=4,
                ready_span_count=4,
                duration_seconds=10,
                source_count=1,
                remember_ready=True,
                recap_ready=True,
                learned_claim_count=1,
            ),
        ),
    )


class _Workstation:
    def __init__(self) -> None:
        self.calls = []

    def prepare(self, asset_id, revision_id, *, owner_id):  # noqa: ANN001, ANN201
        self.calls.append(("prepare", asset_id, revision_id, owner_id))
        return _prepared()

    def inspect(self, asset_id, revision_id, set_id, *, owner_id):  # noqa: ANN001, ANN201
        self.calls.append(("inspect", asset_id, revision_id, set_id, owner_id))
        return _prepared()

    def produce(self, asset_id, revision_id, set_id, *, owner_id):  # noqa: ANN001, ANN201
        self.calls.append(("produce", asset_id, revision_id, set_id, owner_id))
        return _prepared("registered")

    def recover(self, asset_id, revision_id, set_id, *, owner_id):  # noqa: ANN001, ANN201
        self.calls.append(("recover", asset_id, revision_id, set_id, owner_id))
        return _prepared("registered")


class _Playback:
    def metadata(self, *, asset_id, revision_id, owner_digest):  # noqa: ANN001, ANN201
        return AudioPlaybackMetadata(
            asset_id=asset_id,
            revision_id=revision_id,
            receipt_sha256="a" * 64,
            audio_sha256="b" * 64,
            audio_size_bytes=44,
            duration_seconds=10,
            chapter_ids=("chapter-1",),
            retention_marker_count=2,
            learned_claim_count=1,
            source_count=1,
            learned_claims=(
                AudioLearnedClaimMetadata(
                    chapter_id="chapter-1",
                    claim_text="Verified claim",
                    source_count=1,
                    follow_up_prompt="Review the source.",
                ),
            ),
        )

    def read(self, *, asset_id, revision_id, owner_digest, range_header):  # noqa: ANN001, ANN201
        return MediaByteRange(
            payload=b"RIFFfixture",
            stream=None,
            start=0,
            end=10,
            total=44,
            sha256="b" * 64,
            receipt_sha256="a" * 64,
            media_type="audio/wav",
        )


class _Store:
    def get(self, asset_id, *, owner_id):  # noqa: ANN001, ANN201
        link = MultimediaAudioProductionLink(
            owner_identity_digest=OWNER_DIGEST,
            asset_id=asset_id,
            revision_id="revision-1",
            receipt_sha256="a" * 64,
            audio_sha256="b" * 64,
            audio_size_bytes=44,
            duration_seconds=10,
            chapter_ids=("chapter-1",),
            retention_marker_count=2,
            learned_claim_count=1,
            source_count=1,
        )
        return SimpleNamespace(
            asset=SimpleNamespace(revision_id="revision-1", owner_user_id=OWNER_DIGEST),
            audio_production_link=link,
        )


def _runtime() -> MultimediaLocalAudibleRuntime:
    return MultimediaLocalAudibleRuntime(
        workstation=_Workstation(),  # type: ignore[arg-type]
        playback=_Playback(),  # type: ignore[arg-type]
        store=_Store(),  # type: ignore[arg-type]
    )


def _client(runtime=None) -> TestClient:  # noqa: ANN001
    app = FastAPI()
    app.include_router(multimedia_router)
    app.dependency_overrides[authenticated_multimedia_operator] = lambda: "owner-1"
    app.dependency_overrides[get_multimedia_local_audible_runtime_optional] = lambda: runtime
    if runtime is not None:
        app.dependency_overrides[get_multimedia_local_audible_runtime] = lambda: runtime
    return TestClient(app)


def test_capability_and_authenticated_commands_use_only_opaque_set_authority() -> None:
    runtime = _runtime()
    client = _client(runtime)
    assert client.get("/multimedia/local-audible/capability").json() == {
        "available": True,
        "reason": "ready",
        "route_policy": "cheapest",
        "cost_usd": 0.0,
    }
    body = {"expected_revision_id": "revision-1", "set_id": SET_ID}
    assert (
        client.post(
            "/multimedia/assets/asset-1/local-audible/prepare",
            json={"expected_revision_id": "revision-1"},
        ).status_code
        == 200
    )
    assert (
        client.get(f"/multimedia/assets/asset-1/local-audible/revision-1/{SET_ID}").status_code
        == 200
    )
    assert (
        client.post("/multimedia/assets/asset-1/local-audible/produce", json=body).json()["status"]
        == "registered"
    )
    assert (
        client.post("/multimedia/assets/asset-1/local-audible/recover", json=body).status_code
        == 200
    )
    assert all(call[-1] == "owner-1" for call in runtime.workstation.calls)  # type: ignore[attr-defined]
    assert (
        client.post(
            "/multimedia/assets/asset-1/local-audible/produce",
            json={**body, "output_path": "/tmp/forged"},
        ).status_code
        == 422
    )


def test_registered_metadata_and_audio_range_are_private_and_link_verified() -> None:
    client = _client(_runtime())
    metadata = client.get(
        "/multimedia/assets/asset-1/local-audible/playback",
        params={"revision_id": "revision-1"},
    )
    assert metadata.status_code == 200
    assert metadata.json()["audio_url"].endswith("/revision-1/audio")
    assert metadata.json()["learned_claims"] == [
        {
            "chapter_id": "chapter-1",
            "claim_text": "Verified claim",
            "source_count": 1,
            "follow_up_prompt": "Review the source.",
        }
    ]
    assert "output_path" not in metadata.text and "manifest_mac" not in metadata.text
    assert "source_chunk" not in metadata.text
    audio = client.get(
        "/multimedia/assets/asset-1/local-audible/playback/revision-1/audio",
        headers={"Range": "bytes=0-10"},
    )
    assert audio.status_code == 206 and audio.content == b"RIFFfixture"
    assert audio.headers["cache-control"] == "private, no-store"
    assert audio.headers["accept-ranges"] == "bytes"
    assert audio.headers["content-range"] == "bytes 0-10/44"


def test_absent_runtime_is_opaque_and_commands_are_503() -> None:
    client = _client()
    assert client.get("/multimedia/local-audible/capability").json()["available"] is False
    response = client.post(
        "/multimedia/assets/asset-1/local-audible/prepare",
        json={"expected_revision_id": "revision-1"},
    )
    assert response.status_code == 503
    assert response.json() == {"detail": "local audible runtime is unavailable"}
