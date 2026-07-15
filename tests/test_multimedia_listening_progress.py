"""Cycle 22 listening progress store and route tests."""

from __future__ import annotations

import hashlib
import json
import os
import stat
from pathlib import Path

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from substrate.multimedia.listening_progress import (
    AudioIdentity,
    ListeningProgressCheckpointRequest,
    ListeningProgressError,
    ListeningProgressIntegrityConflict,
    ListeningProgressStore,
    mint_session_id,
)


def _audio_identity(
    *,
    revision_id: str = "rev-1",
    audio_sha256: str | None = None,
    duration_seconds: float = 120.0,
) -> AudioIdentity:
    return AudioIdentity(
        revision_id=revision_id,
        audio_sha256=audio_sha256 or hashlib.sha256(b"audio-bytes").hexdigest(),
        duration_seconds=duration_seconds,
        kind="audio_experience",
        mode="audio",
    )


# ── Store tests ────────────────────────────────────────────────────


class TestListeningProgressStore:
    def test_read_returns_no_progress_when_absent(self, tmp_path: Path) -> None:
        store = ListeningProgressStore(tmp_path)
        identity = _audio_identity()
        result = store.read(
            "asset-1",
            owner_id="owner-a",
            revision_id="rev-1",
            audio_identity=identity,
        )
        assert result.resume_available is False
        assert result.position_milliseconds == 0
        assert result.duration_milliseconds == 120_000
        assert result.completed is False
        assert result.session_id == ""
        assert result.sequence == 0

    def test_checkpoint_write_and_read_round_trip(self, tmp_path: Path) -> None:
        store = ListeningProgressStore(tmp_path)
        identity = _audio_identity()
        session = mint_session_id()
        stored = store.checkpoint(
            "asset-1",
            ListeningProgressCheckpointRequest(
                revision_id="rev-1",
                position_milliseconds=30_000,
                session_id=session,
                sequence=1,
            ),
            owner_id="owner-a",
            audio_identity=identity,
        )
        assert stored.resume_available is True
        assert stored.position_milliseconds == 30_000
        assert stored.duration_milliseconds == 120_000
        assert stored.completed is False
        assert stored.session_id == session
        assert stored.sequence == 1
        assert stored.applied is True

        reopened = store.read(
            "asset-1",
            owner_id="owner-a",
            revision_id="rev-1",
            audio_identity=identity,
        )
        assert reopened.resume_available is True
        assert reopened.position_milliseconds == 30_000
        assert reopened.session_id == session

    def test_stale_sequence_is_idempotent(self, tmp_path: Path) -> None:
        store = ListeningProgressStore(tmp_path)
        identity = _audio_identity()
        session = mint_session_id()
        store.checkpoint(
            "asset-1",
            ListeningProgressCheckpointRequest(
                revision_id="rev-1",
                position_milliseconds=50_000,
                session_id=session,
                sequence=5,
            ),
            owner_id="owner-a",
            audio_identity=identity,
        )
        # Same session, lower sequence — stale write returns existing.
        stale = store.checkpoint(
            "asset-1",
            ListeningProgressCheckpointRequest(
                revision_id="rev-1",
                position_milliseconds=10_000,
                session_id=session,
                sequence=3,
            ),
            owner_id="owner-a",
            audio_identity=identity,
        )
        assert stale.position_milliseconds == 50_000
        assert stale.sequence == 5
        assert stale.applied is False

    def test_same_session_equal_sequence_is_stale(self, tmp_path: Path) -> None:
        store = ListeningProgressStore(tmp_path)
        identity = _audio_identity()
        session = mint_session_id()
        store.checkpoint(
            "asset-1",
            ListeningProgressCheckpointRequest(
                revision_id="rev-1",
                position_milliseconds=50_000,
                session_id=session,
                sequence=5,
            ),
            owner_id="owner-a",
            audio_identity=identity,
        )
        stale = store.checkpoint(
            "asset-1",
            ListeningProgressCheckpointRequest(
                revision_id="rev-1",
                position_milliseconds=10_000,
                session_id=session,
                sequence=5,
            ),
            owner_id="owner-a",
            audio_identity=identity,
        )
        assert stale.position_milliseconds == 50_000

    def test_different_session_replaces_by_arrival_order(self, tmp_path: Path) -> None:
        store = ListeningProgressStore(tmp_path)
        identity = _audio_identity()
        session_a = mint_session_id()
        session_b = mint_session_id()
        store.checkpoint(
            "asset-1",
            ListeningProgressCheckpointRequest(
                revision_id="rev-1",
                position_milliseconds=50_000,
                session_id=session_a,
                sequence=5,
            ),
            owner_id="owner-a",
            audio_identity=identity,
        )
        # Different session with lower sequence still replaces.
        replaced = store.checkpoint(
            "asset-1",
            ListeningProgressCheckpointRequest(
                revision_id="rev-1",
                position_milliseconds=20_000,
                session_id=session_b,
                sequence=1,
            ),
            owner_id="owner-a",
            audio_identity=identity,
        )
        assert replaced.position_milliseconds == 20_000
        assert replaced.session_id == session_b

    def test_completion_threshold(self, tmp_path: Path) -> None:
        store = ListeningProgressStore(tmp_path)
        identity = _audio_identity(duration_seconds=120.0)
        session = mint_session_id()
        # Within 5 seconds of end → complete.
        stored = store.checkpoint(
            "asset-1",
            ListeningProgressCheckpointRequest(
                revision_id="rev-1",
                position_milliseconds=116_000,
                session_id=session,
                sequence=1,
            ),
            owner_id="owner-a",
            audio_identity=identity,
        )
        assert stored.completed is True

    def test_not_complete_when_far_from_end(self, tmp_path: Path) -> None:
        store = ListeningProgressStore(tmp_path)
        identity = _audio_identity(duration_seconds=120.0)
        session = mint_session_id()
        stored = store.checkpoint(
            "asset-1",
            ListeningProgressCheckpointRequest(
                revision_id="rev-1",
                position_milliseconds=100_000,
                session_id=session,
                sequence=1,
            ),
            owner_id="owner-a",
            audio_identity=identity,
        )
        assert stored.completed is False

    def test_backward_seek_is_valid(self, tmp_path: Path) -> None:
        store = ListeningProgressStore(tmp_path)
        identity = _audio_identity()
        session = mint_session_id()
        store.checkpoint(
            "asset-1",
            ListeningProgressCheckpointRequest(
                revision_id="rev-1",
                position_milliseconds=80_000,
                session_id=session,
                sequence=1,
            ),
            owner_id="owner-a",
            audio_identity=identity,
        )
        # Later sequence with backward seek.
        stored = store.checkpoint(
            "asset-1",
            ListeningProgressCheckpointRequest(
                revision_id="rev-1",
                position_milliseconds=20_000,
                session_id=session,
                sequence=2,
            ),
            owner_id="owner-a",
            audio_identity=identity,
        )
        assert stored.position_milliseconds == 20_000

    def test_historical_revision_not_returned(self, tmp_path: Path) -> None:
        store = ListeningProgressStore(tmp_path)
        identity_v1 = _audio_identity(revision_id="rev-1")
        identity_v2 = _audio_identity(revision_id="rev-2")
        session = mint_session_id()
        store.checkpoint(
            "asset-1",
            ListeningProgressCheckpointRequest(
                revision_id="rev-1",
                position_milliseconds=50_000,
                session_id=session,
                sequence=1,
            ),
            owner_id="owner-a",
            audio_identity=identity_v1,
        )
        # Reading with new revision returns no progress.
        result = store.read(
            "asset-1",
            owner_id="owner-a",
            revision_id="rev-2",
            audio_identity=identity_v2,
        )
        assert result.resume_available is False

    def test_new_revision_replaces_historical_progress(self, tmp_path: Path) -> None:
        store = ListeningProgressStore(tmp_path)
        identity_v1 = _audio_identity(revision_id="rev-1")
        identity_v2 = _audio_identity(revision_id="rev-2")
        session = mint_session_id()
        store.checkpoint(
            "asset-1",
            ListeningProgressCheckpointRequest(
                revision_id="rev-1",
                position_milliseconds=50_000,
                session_id=session,
                sequence=1,
            ),
            owner_id="owner-a",
            audio_identity=identity_v1,
        )
        # Checkpoint with new revision replaces.
        stored = store.checkpoint(
            "asset-1",
            ListeningProgressCheckpointRequest(
                revision_id="rev-2",
                position_milliseconds=10_000,
                session_id=session,
                sequence=2,
            ),
            owner_id="owner-a",
            audio_identity=identity_v2,
        )
        assert stored.position_milliseconds == 10_000
        assert stored.revision_id == "rev-2"

    def test_audio_digest_conflict_raises(self, tmp_path: Path) -> None:
        store = ListeningProgressStore(tmp_path)
        identity_a = _audio_identity(audio_sha256="a" * 64)
        identity_b = _audio_identity(audio_sha256="b" * 64)
        session = mint_session_id()
        store.checkpoint(
            "asset-1",
            ListeningProgressCheckpointRequest(
                revision_id="rev-1",
                position_milliseconds=50_000,
                session_id=session,
                sequence=1,
            ),
            owner_id="owner-a",
            audio_identity=identity_a,
        )
        with pytest.raises(ListeningProgressIntegrityConflict):
            store.checkpoint(
                "asset-1",
                ListeningProgressCheckpointRequest(
                    revision_id="rev-1",
                    position_milliseconds=60_000,
                    session_id=session,
                    sequence=2,
                ),
                owner_id="owner-a",
                audio_identity=identity_b,
            )

    def test_position_out_of_range_raises(self, tmp_path: Path) -> None:
        store = ListeningProgressStore(tmp_path)
        identity = _audio_identity(duration_seconds=120.0)
        session = mint_session_id()
        with pytest.raises(ListeningProgressError, match="position_out_of_range"):
            store.checkpoint(
                "asset-1",
                ListeningProgressCheckpointRequest(
                    revision_id="rev-1",
                    position_milliseconds=121_000,
                    session_id=session,
                    sequence=1,
                ),
                owner_id="owner-a",
                audio_identity=identity,
            )

    def test_not_audio_asset_raises(self, tmp_path: Path) -> None:
        store = ListeningProgressStore(tmp_path)
        identity = AudioIdentity(
            revision_id="rev-1",
            audio_sha256="a" * 64,
            duration_seconds=120.0,
            kind="documentary_video",
            mode="video",
        )
        with pytest.raises(ListeningProgressError, match="not_audio"):
            store.read(
                "asset-1",
                owner_id="owner-a",
                revision_id="rev-1",
                audio_identity=identity,
            )

    def test_owner_isolation(self, tmp_path: Path) -> None:
        store = ListeningProgressStore(tmp_path)
        identity = _audio_identity()
        session = mint_session_id()
        store.checkpoint(
            "asset-1",
            ListeningProgressCheckpointRequest(
                revision_id="rev-1",
                position_milliseconds=50_000,
                session_id=session,
                sequence=1,
            ),
            owner_id="owner-a",
            audio_identity=identity,
        )
        # Different owner sees no progress.
        result = store.read(
            "asset-1",
            owner_id="owner-b",
            revision_id="rev-1",
            audio_identity=identity,
        )
        assert result.resume_available is False

    def test_private_file_permissions(self, tmp_path: Path) -> None:
        store = ListeningProgressStore(tmp_path)
        identity = _audio_identity()
        session = mint_session_id()
        store.checkpoint(
            "asset-1",
            ListeningProgressCheckpointRequest(
                revision_id="rev-1",
                position_milliseconds=50_000,
                session_id=session,
                sequence=1,
            ),
            owner_id="owner-a",
            audio_identity=identity,
        )
        owner_digest = hashlib.sha256(b"owner-a").hexdigest()
        progress_dir = tmp_path / "accounts" / owner_digest / "listening-progress"
        progress_file = progress_dir / "asset-1.json"
        assert progress_file.exists()
        metadata = progress_file.stat()
        assert stat.S_ISREG(metadata.st_mode)
        assert metadata.st_nlink == 1
        assert not (stat.S_IMODE(metadata.st_mode) & 0o077)

    def test_symlink_rejected(self, tmp_path: Path) -> None:
        store = ListeningProgressStore(tmp_path)
        owner_digest = hashlib.sha256(b"owner-a").hexdigest()
        account = tmp_path / "accounts" / owner_digest
        account.mkdir(parents=True, mode=0o700)
        progress_dir = account / "listening-progress"
        progress_dir.mkdir(mode=0o700)
        # Create a symlink instead of a regular file.
        link = progress_dir / "asset-1.json"
        link.symlink_to("/etc/passwd")
        identity = _audio_identity()
        with pytest.raises(ListeningProgressIntegrityConflict, match="path_unsafe"):
            store.read(
                "asset-1",
                owner_id="owner-a",
                revision_id="rev-1",
                audio_identity=identity,
            )

    def test_account_directory_symlink_rejected_as_integrity_conflict(
        self, tmp_path: Path
    ) -> None:
        store = ListeningProgressStore(tmp_path)
        owner_digest = hashlib.sha256(b"owner-a").hexdigest()
        (tmp_path / "accounts" / owner_digest).symlink_to(tmp_path)
        with pytest.raises(ListeningProgressIntegrityConflict, match="path_unsafe"):
            store.read(
                "asset-1",
                owner_id="owner-a",
                revision_id="rev-1",
                audio_identity=_audio_identity(),
            )

    def test_lock_symlink_rejected_as_integrity_conflict(self, tmp_path: Path) -> None:
        store = ListeningProgressStore(tmp_path)
        (tmp_path / ".listening-progress.lock").symlink_to("/etc/passwd")
        with pytest.raises(ListeningProgressIntegrityConflict, match="lock_unsafe"):
            store.read(
                "asset-1",
                owner_id="owner-a",
                revision_id="rev-1",
                audio_identity=_audio_identity(),
            )

    def test_corrupt_json_raises_integrity_conflict(self, tmp_path: Path) -> None:
        store = ListeningProgressStore(tmp_path)
        owner_digest = hashlib.sha256(b"owner-a").hexdigest()
        account = tmp_path / "accounts" / owner_digest
        account.mkdir(parents=True, mode=0o700)
        progress_dir = account / "listening-progress"
        progress_dir.mkdir(mode=0o700)
        corrupt = progress_dir / "asset-1.json"
        corrupt.write_bytes(b"not-json", )
        os.chmod(corrupt, 0o600)
        identity = _audio_identity()
        with pytest.raises(ListeningProgressIntegrityConflict, match="envelope_invalid"):
            store.read(
                "asset-1",
                owner_id="owner-a",
                revision_id="rev-1",
                audio_identity=identity,
            )

    def test_nested_owner_digest_must_match_envelope_and_account(
        self, tmp_path: Path
    ) -> None:
        store = ListeningProgressStore(tmp_path)
        identity = _audio_identity()
        store.checkpoint(
            "asset-1",
            ListeningProgressCheckpointRequest(
                revision_id="rev-1",
                position_milliseconds=50_000,
                session_id=mint_session_id(),
                sequence=1,
            ),
            owner_id="owner-a",
            audio_identity=identity,
        )
        owner_digest = hashlib.sha256(b"owner-a").hexdigest()
        progress_file = (
            tmp_path
            / "accounts"
            / owner_digest
            / "listening-progress"
            / "asset-1.json"
        )
        payload = json.loads(progress_file.read_text())
        payload["progress"]["owner_identity_digest"] = hashlib.sha256(
            b"owner-b"
        ).hexdigest()
        progress_file.write_text(json.dumps(payload))
        os.chmod(progress_file, 0o600)

        with pytest.raises(ListeningProgressIntegrityConflict, match="identity_conflict"):
            store.read(
                "asset-1",
                owner_id="owner-a",
                revision_id="rev-1",
                audio_identity=identity,
            )

    def test_mint_session_id_is_unique(self) -> None:
        ids = {mint_session_id() for _ in range(100)}
        assert len(ids) == 100
        for sid in ids:
            assert len(sid) >= 16


# ── Route tests ────────────────────────────────────────────────────


def _make_route_app(tmp_path: Path) -> tuple[TestClient, ListeningProgressStore]:
    from substrate.multimedia.listening_progress import ListeningProgressStore

    store = ListeningProgressStore(tmp_path)
    identity = _audio_identity()

    def resolve_audio_identity(asset_id: str, operator_id: str) -> AudioIdentity:
        if asset_id == "foreign-asset":
            raise KeyError(asset_id)
        if asset_id == "video-asset":
            return AudioIdentity(
                revision_id="rev-1",
                audio_sha256="a" * 64,
                duration_seconds=120.0,
                kind="documentary_video",
                mode="video",
            )
        return identity

    from interfaces.research.api.multimedia_listening_progress_routes import (
        ListeningProgressRouteRuntime,
        get_listening_progress_runtime,
        multimedia_listening_progress_router,
    )
    from interfaces.research.api.multimedia_reconciliation_routes import (
        authenticated_multimedia_operator,
    )

    runtime = ListeningProgressRouteRuntime(
        store=store,
        audio_identity_resolver=resolve_audio_identity,
    )

    app = FastAPI()
    app.include_router(multimedia_listening_progress_router, prefix="/multimedia")

    # Override the auth dependency to return a fixed operator.
    _current_operator = {"id": "owner-a"}

    def fake_auth(request: Request) -> str:
        # Check X-Operator-Id header; if absent, raise 401.
        operator_id = request.headers.get("X-Operator-Id", "").strip()
        if not operator_id:
            from fastapi import HTTPException, status
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="authentication required",
            )
        return operator_id

    app.dependency_overrides[authenticated_multimedia_operator] = fake_auth
    app.dependency_overrides[get_listening_progress_runtime] = lambda: runtime
    return TestClient(app, raise_server_exceptions=False), store


class TestListeningProgressRoutes:
    def test_get_returns_no_progress_when_absent(self, tmp_path: Path) -> None:
        client, _ = _make_route_app(tmp_path)
        resp = client.get(
            "/multimedia/assets/asset-1/listening-progress",
            params={"revision_id": "rev-1"},
            headers={"X-Operator-Id": "owner-a"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["resume_available"] is False
        assert body["position_milliseconds"] == 0
        assert body["duration_milliseconds"] == 120_000

    def test_put_write_and_get_round_trip(self, tmp_path: Path) -> None:
        client, store = _make_route_app(tmp_path)
        session = mint_session_id()
        resp = client.put(
            "/multimedia/assets/asset-1/listening-progress",
            json={
                "revision_id": "rev-1",
                "position_milliseconds": 30_000,
                "session_id": session,
                "sequence": 1,
            },
            headers={"X-Operator-Id": "owner-a"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["resume_available"] is True
        assert body["position_milliseconds"] == 30_000
        assert body["applied"] is True

        # GET returns the same.
        resp2 = client.get(
            "/multimedia/assets/asset-1/listening-progress",
            params={"revision_id": "rev-1"},
            headers={"X-Operator-Id": "owner-a"},
        )
        assert resp2.status_code == 200
        assert resp2.json()["position_milliseconds"] == 30_000

    def test_foreign_asset_returns_404(self, tmp_path: Path) -> None:
        client, _ = _make_route_app(tmp_path)
        resp = client.get(
            "/multimedia/assets/foreign-asset/listening-progress",
            params={"revision_id": "rev-1"},
            headers={"X-Operator-Id": "owner-a"},
        )
        assert resp.status_code == 404

    def test_video_asset_returns_404(self, tmp_path: Path) -> None:
        client, _ = _make_route_app(tmp_path)
        resp = client.get(
            "/multimedia/assets/video-asset/listening-progress",
            params={"revision_id": "rev-1"},
            headers={"X-Operator-Id": "owner-a"},
        )
        assert resp.status_code == 404

    def test_unauthenticated_returns_401(self, tmp_path: Path) -> None:
        client, _ = _make_route_app(tmp_path)
        resp = client.get(
            "/multimedia/assets/asset-1/listening-progress",
            params={"revision_id": "rev-1"},
        )
        assert resp.status_code == 401

    def test_no_store_headers(self, tmp_path: Path) -> None:
        client, _ = _make_route_app(tmp_path)
        resp = client.get(
            "/multimedia/assets/asset-1/listening-progress",
            params={"revision_id": "rev-1"},
            headers={"X-Operator-Id": "owner-a"},
        )
        assert resp.headers.get("cache-control") == "private, no-store"

    def test_malformed_body_returns_422(self, tmp_path: Path) -> None:
        client, _ = _make_route_app(tmp_path)
        resp = client.put(
            "/multimedia/assets/asset-1/listening-progress",
            json={"revision_id": "rev-1"},  # Missing required fields.
            headers={"X-Operator-Id": "owner-a"},
        )
        assert resp.status_code == 422

    def test_short_session_id_returns_422(self, tmp_path: Path) -> None:
        client, _ = _make_route_app(tmp_path)
        resp = client.put(
            "/multimedia/assets/asset-1/listening-progress",
            json={
                "revision_id": "rev-1",
                "position_milliseconds": 10_000,
                "session_id": "short",
                "sequence": 1,
            },
            headers={"X-Operator-Id": "owner-a"},
        )
        assert resp.status_code == 422
        assert resp.headers["cache-control"] == "private, no-store"

    @pytest.mark.parametrize("field,value", [("sequence", True), ("sequence", 2**53)])
    def test_checkpoint_rejects_non_safe_integer(
        self, tmp_path: Path, field: str, value: object
    ) -> None:
        client, _ = _make_route_app(tmp_path)
        body: dict[str, object] = {
            "revision_id": "rev-1",
            "position_milliseconds": 1_000,
            "session_id": mint_session_id(),
            "sequence": 1,
        }
        body[field] = value
        response = client.put(
            "/multimedia/assets/asset-1/listening-progress",
            json=body,
            headers={"X-Operator-Id": "owner-a"},
        )
        assert response.status_code == 422
        assert response.headers["cache-control"] == "private, no-store"
