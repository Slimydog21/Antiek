from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from substrate.multimedia.local_audible_coordinator import LocalAudibleOutcomeUnknown
from substrate.multimedia.local_audible_workstation import (
    LocalAudibleWorkstationError,
    LocalAudibleWorkstationRuntime,
)
from substrate.multimedia.local_tts import LocalTTSArtifact, LocalTTSOutcomeUnknown
from substrate.multimedia.read_model import CreateMultimediaDraftRequest, MultimediaAssetStore

NOW = datetime(2026, 7, 13, tzinfo=UTC)
KEY = b"local-audible-workstation-test-signing-key"


def _store(tmp_path: Path, *, mode: str = "audio"):
    store = MultimediaAssetStore(str(tmp_path / "assets"))
    draft = store.create_draft(
        CreateMultimediaDraftRequest(
            topic="jet engine history",
            target_minutes=15,
            mode=mode,
            route_policy="cheapest",
            sources=(
                "Early jet engine history began with Frank Whittle's turbojet patent in 1930.",
            ),
            selected_arc_ids=("history",),
        ),
        owner_id="owner-1",
    )
    ready = store.approve_dry_run(draft.asset.asset_id, owner_id="owner-1")
    return store, ready.asset.asset_id, ready.asset.revision_id


class _TTS:
    def __init__(self) -> None:
        self.artifacts = {}
        self.unknown_once = False
        self._raised = False

    def _artifact(self, request):  # noqa: ANN001, ANN202
        return LocalTTSArtifact(
            request_id=f"tts-{request.sequence}",
            request_body_digest=request.body_digest,
            config_digest="a" * 64,
            output_path=f"/private/audio/{request.sequence}.wav",
            output_sha256=f"{request.sequence + 1:064x}",
            duration_seconds=1.25,
            sample_rate_hz=request.sample_rate_hz,
            channels=request.channels,
            synthesizer_digest="b" * 64,
            probe_digest="c" * 64,
            created_at="2026-07-13T00:00:00Z",
        )

    def synthesize(self, request, *, now):  # noqa: ANN001, ANN201
        if self.unknown_once and not self._raised and request.sequence > 0:
            self._raised = True
            raise LocalTTSOutcomeUnknown("injected unknown")
        return self.artifacts.setdefault(request.paragraph_id, self._artifact(request))

    def recover(self, request):  # noqa: ANN001, ANN201
        return self.artifacts.setdefault(request.paragraph_id, self._artifact(request))

    def reopen(self, request):  # noqa: ANN001, ANN201
        try:
            return self.artifacts[request.paragraph_id]
        except KeyError:
            raise ValueError("unavailable") from None


class _Production:
    def __init__(self) -> None:
        self.unknown = False
        self.produce_calls = 0
        self.recover_calls = 0

    def produce(self, request, *, now):  # noqa: ANN001, ANN201
        self.produce_calls += 1
        if self.unknown:
            raise LocalAudibleOutcomeUnknown("injected unknown")
        return object()

    def recover(self, request, *, now):  # noqa: ANN001, ANN201
        self.recover_calls += 1
        return object()


def _runtime(tmp_path: Path, *, tts=None, production=None):  # noqa: ANN001, ANN202
    store, asset_id, revision_id = _store(tmp_path)
    runtime = LocalAudibleWorkstationRuntime(
        db_path=str(tmp_path / "workstation.duckdb"),
        signing_key=KEY,
        store=store,
        tts=tts or _TTS(),
        production=production or _Production(),
        clock=lambda: NOW,
    )
    return runtime, asset_id, revision_id


def test_prepare_exposes_retention_readiness_and_produces_registered_audio(
    tmp_path: Path,
) -> None:
    production = _Production()
    runtime, asset_id, revision_id = _runtime(tmp_path, production=production)
    prepared = runtime.prepare(asset_id, revision_id, owner_id="owner-1")
    assert prepared.status == "ready_to_produce" and prepared.cost_usd == 0
    assert prepared.total_duration_seconds > 0
    assert all(
        chapter.ready_span_count == chapter.span_count
        and chapter.remember_ready
        and chapter.recap_ready
        and chapter.learned_claim_count > 0
        for chapter in prepared.chapters
    )
    registered = runtime.produce(
        asset_id, revision_id, prepared.set_id, owner_id="owner-1"
    )
    assert registered.status == "registered" and registered.playback_ready
    assert production.produce_calls == 1


def test_preparation_unknown_recovers_exact_span_set(tmp_path: Path) -> None:
    tts = _TTS()
    tts.unknown_once = True
    runtime, asset_id, revision_id = _runtime(tmp_path, tts=tts)
    prepared = runtime.prepare(asset_id, revision_id, owner_id="owner-1")
    assert prepared.status == "preparation_unknown" and prepared.recoverable
    recovered = runtime.recover(
        asset_id, revision_id, prepared.set_id, owner_id="owner-1"
    )
    assert recovered.status == "ready_to_produce"
    assert all(chapter.ready_span_count == chapter.span_count for chapter in recovered.chapters)


def test_production_unknown_replaces_produce_with_explicit_recovery(tmp_path: Path) -> None:
    production = _Production()
    runtime, asset_id, revision_id = _runtime(tmp_path, production=production)
    prepared = runtime.prepare(asset_id, revision_id, owner_id="owner-1")
    production.unknown = True
    unknown = runtime.produce(
        asset_id, revision_id, prepared.set_id, owner_id="owner-1"
    )
    assert unknown.status == "production_unknown" and unknown.recoverable
    recovered = runtime.recover(
        asset_id, revision_id, prepared.set_id, owner_id="owner-1"
    )
    assert recovered.status == "registered" and production.recover_calls == 1


def test_foreign_stale_and_video_assets_fail_before_synthesis(tmp_path: Path) -> None:
    tts = _TTS()
    runtime, asset_id, revision_id = _runtime(tmp_path, tts=tts)
    with pytest.raises(LocalAudibleWorkstationError, match="unavailable"):
        runtime.prepare(asset_id, revision_id, owner_id="owner-2")
    with pytest.raises(LocalAudibleWorkstationError, match="current ready"):
        runtime.prepare(asset_id, "old", owner_id="owner-1")
    video_store, video_id, video_revision = _store(tmp_path / "video", mode="video")
    video_runtime = LocalAudibleWorkstationRuntime(
        db_path=str(tmp_path / "video-workstation.duckdb"),
        signing_key=KEY,
        store=video_store,
        tts=tts,
        production=_Production(),
        clock=lambda: NOW,
    )
    with pytest.raises(LocalAudibleWorkstationError, match="audio revision"):
        video_runtime.prepare(video_id, video_revision, owner_id="owner-1")
    assert not tts.artifacts
