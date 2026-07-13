from __future__ import annotations

import hashlib
import io
import shutil
import wave
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from substrate.multimedia import authorized_production_worker as worker_module
from substrate.multimedia.authorized_production_worker import (
    AuthorizedProductionError,
    AuthorizedProductionRequest,
    AuthorizedProductionRuntime,
    ChapterNarrationAuthority,
    produce_authorized_multimedia,
)
from substrate.multimedia.chapter_tts_production import ChapterTTSSynthesisResult
from substrate.multimedia.execution_authorization import issue_async_execution_authorization
from substrate.multimedia.narration_run import prepare_narration_run
from substrate.multimedia.read_model import CreateMultimediaDraftRequest, MultimediaAssetStore
from substrate.multimedia.reviewed_visual_registry import ReviewedVisualRegistry
from substrate.multimedia.verified_playback import VerifiedPlaybackRuntime
from substrate.multimedia.visual_selection import (
    ReviewedVisualSelection,
    VerifiedVisualEvidence,
)

NOW = datetime(2026, 7, 12, tzinfo=UTC)
SIGNING_KEY = b"s" * 32
NARRATION_KEY = b"n" * 32
VISUAL_KEY = b"v" * 32
EVIDENCE_KEY = b"e" * 32
RENDER_KEY = b"r" * 32
RECEIPT_KEY = b"c" * 32


def _wav() -> bytes:
    payload = io.BytesIO()
    with wave.open(payload, "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(8_000)
        audio.writeframes(b"\x00\x00" * 8_000)
    return payload.getvalue()


def _state(tmp_path: Path):
    ffmpeg = shutil.which("ffmpeg")
    ffprobe = shutil.which("ffprobe")
    if not ffmpeg or not ffprobe:
        pytest.skip("FFmpeg is required for production-worker verification")
    store = MultimediaAssetStore(str(tmp_path / "assets"))
    draft = store.create_draft(
        CreateMultimediaDraftRequest(
            topic="Authorized production worker",
            target_minutes=15,
            mode="video",
            route_policy="balanced",
            sources=("Grounded production evidence.",),
        ),
        owner_id="owner-1",
    )
    ready = store.approve_dry_run(draft.asset.asset_id, owner_id="owner-1")
    routes = {
        chapter.chapter_id: ("trusted-tts", "voice-1")
        for chapter in ready.plan.chapters
        if any(
            line.line_id.split("-line-", 1)[0] == chapter.chapter_id
            for line in ready.plan.script_lines
        )
    }
    prepared = prepare_narration_run(
        ready.plan,
        asset_id=ready.asset.asset_id,
        revision_id=ready.asset.revision_id,
        routes=routes,
        sample_rate_hz=8_000,
    )
    authorities = tuple(
        ChapterNarrationAuthority(
            chapter_id=request.chapter_id,
            authorization=issue_async_execution_authorization(
                signing_key=SIGNING_KEY,
                request_id=f"authority-{index}",
                operator_id="owner-1",
                asset_id=ready.asset.asset_id,
                revision_id=request.revision_id,
                provider=request.provider,
                route_policy=ready.asset.route_policy,
                model=request.model,
                endpoint_capability="text-to-speech",
                catalog_version="catalog-1",
                catalog_digest="a" * 64,
                quote_id=f"quote-{index}",
                quote_expires_at=NOW + timedelta(hours=1),
                recovery_authority_id="recovery-1",
                recovery_verification_key_digest="b" * 64,
                approved_ceiling_microdollars=100_000,
                request_body_digest=request.body_digest,
                issued_at=NOW,
                expires_at=NOW + timedelta(hours=1),
            ),
        )
        for index, request in enumerate(prepared.chapters)
    )
    candidates = tmp_path / "candidates"
    candidates.mkdir(mode=0o700)
    selections = []
    for index, request in enumerate(prepared.chapters):
        path = candidates / f"still-{index}.ppm"
        path.write_bytes(b"P6\n1 1\n255\n" + bytes((index * 30 % 255, 80, 160)))
        selections.append(
            ReviewedVisualSelection(
                scene_id=f"scene-{request.chapter_id}",
                path=str(path),
                expected_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                visual_label="generated",
                source_chunk_ids=request.source_chunk_ids,
                execution_receipt_id=f"execution-{index}",
                artifact_receipt_id=f"artifact-{index}",
            )
        )
    registry = ReviewedVisualRegistry(
        db_path=str(tmp_path / "visuals.duckdb"), integrity_key=b"g" * 32
    )
    registry.register(
        owner_identity_digest=ready.asset.owner_user_id,
        asset_id=ready.asset.asset_id,
        revision_id=ready.asset.revision_id,
        request_id="visual-set-1",
        candidate_ids=tuple(f"candidate-{index}" for index in range(len(selections))),
        selections=tuple(selections),
        now=NOW,
    )
    for name in ("narration", "visual", "render", "receipt"):
        (tmp_path / name).mkdir(mode=0o700)
    playback = VerifiedPlaybackRuntime(
        receipt_root=str(tmp_path / "receipt"),
        receipt_key=RECEIPT_KEY,
        narration_key=NARRATION_KEY,
        visual_key=VISUAL_KEY,
        render_key=RENDER_KEY,
    )
    calls: list[str] = []

    def synthesize(request):
        calls.append(request.chapter_id)
        return ChapterTTSSynthesisResult(_wav(), f"provider-{request.chapter_id}")

    def verify(selection, digest):
        evidence_digest = hashlib.sha256(
            f"{selection.scene_id}\0{digest}".encode()
        ).hexdigest()
        return VerifiedVisualEvidence.issue(
            scene_id=selection.scene_id,
            visual_label=selection.visual_label,
            content_sha256=digest,
            evidence_digest=evidence_digest,
            authority_key=EVIDENCE_KEY,
        )

    runtime = AuthorizedProductionRuntime(
        store=store,
        reviewed_visual_registry=registry,
        playback=playback,
        signing_key=SIGNING_KEY,
        narration_integrity_key=NARRATION_KEY,
        visual_integrity_key=VISUAL_KEY,
        evidence_authority_key=EVIDENCE_KEY,
        render_integrity_key=RENDER_KEY,
        receipt_key=RECEIPT_KEY,
        db_path=str(tmp_path / "production.duckdb"),
        narration_output_dir=str(tmp_path / "narration"),
        visual_output_dir=str(tmp_path / "visual"),
        render_output_dir=str(tmp_path / "render"),
        receipt_output_dir=str(tmp_path / "receipt"),
        synthesize=synthesize,
        verify_evidence=verify,
        clock=lambda: NOW,
        ffmpeg_path=ffmpeg,
        ffprobe_path=ffprobe,
        width_px=320,
        height_px=240,
        fps=10,
        timeout_seconds=60,
    )
    request = AuthorizedProductionRequest(
        expected_revision_id=ready.asset.revision_id,
        chapter_authorities=authorities,
        sample_rate_hz=8_000,
    )
    return ready, runtime, request, calls


def test_produces_receipt_registers_playback_and_exactly_replays(tmp_path: Path) -> None:
    ready, runtime, request, calls = _state(tmp_path)
    first = produce_authorized_multimedia(
        ready.asset.asset_id, request, owner_id="owner-1", runtime=runtime
    )
    assert first.production_link is not None
    metadata = runtime.playback.metadata(
        asset_id=ready.asset.asset_id, revision_id=ready.asset.revision_id
    )
    assert metadata.video_size_bytes > 0
    assert metadata.audio_size_bytes > 0
    first_calls = tuple(calls)
    replay = produce_authorized_multimedia(
        ready.asset.asset_id, request, owner_id="owner-1", runtime=runtime
    )
    assert replay.production_link == first.production_link
    assert tuple(calls) == first_calls


def test_foreign_stale_incomplete_and_tampered_authority_fail_closed(tmp_path: Path) -> None:
    ready, runtime, request, calls = _state(tmp_path)
    with pytest.raises(AuthorizedProductionError, match="unavailable"):
        produce_authorized_multimedia(
            ready.asset.asset_id, request, owner_id="owner-2", runtime=runtime
        )
    with pytest.raises(AuthorizedProductionError, match="current"):
        produce_authorized_multimedia(
            ready.asset.asset_id,
            AuthorizedProductionRequest(
                expected_revision_id="rev-old",
                chapter_authorities=request.chapter_authorities,
                sample_rate_hz=8_000,
            ),
            owner_id="owner-1",
            runtime=runtime,
        )
    with pytest.raises(AuthorizedProductionError, match="incomplete"):
        produce_authorized_multimedia(
            ready.asset.asset_id,
            AuthorizedProductionRequest(
                expected_revision_id=ready.asset.revision_id,
                chapter_authorities=request.chapter_authorities[:-1],
                sample_rate_hz=8_000,
            ),
            owner_id="owner-1",
            runtime=runtime,
        )
    changed = replace(
        request.chapter_authorities[0].authorization,
        request_body_digest="f" * 64,
    )
    tampered = AuthorizedProductionRequest(
        expected_revision_id=ready.asset.revision_id,
        chapter_authorities=(
            ChapterNarrationAuthority(request.chapter_authorities[0].chapter_id, changed),
            *request.chapter_authorities[1:],
        ),
        sample_rate_hz=8_000,
    )
    with pytest.raises((AuthorizedProductionError, ValueError, RuntimeError)):
        produce_authorized_multimedia(
            ready.asset.asset_id, tampered, owner_id="owner-1", runtime=runtime
        )
    assert calls == []


def test_recovers_after_render_before_receipt_without_resynthesis(
    tmp_path: Path, monkeypatch
) -> None:
    ready, runtime, request, calls = _state(tmp_path)
    real_issue = worker_module.issue_educational_video_receipt
    attempts = 0

    def fail_once(**kwargs):
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise RuntimeError("injected post-render crash")
        return real_issue(**kwargs)

    monkeypatch.setattr(worker_module, "issue_educational_video_receipt", fail_once)
    with pytest.raises(RuntimeError, match="post-render"):
        produce_authorized_multimedia(
            ready.asset.asset_id, request, owner_id="owner-1", runtime=runtime
        )
    first_calls = tuple(calls)
    recovered = produce_authorized_multimedia(
        ready.asset.asset_id, request, owner_id="owner-1", runtime=runtime
    )
    assert recovered.production_link is not None
    assert tuple(calls) == first_calls
    assert attempts == 2


def test_recovers_after_receipt_before_registration_without_resynthesis(
    tmp_path: Path, monkeypatch
) -> None:
    ready, runtime, request, calls = _state(tmp_path)
    real_register = worker_module.register_multimedia_production
    attempts = 0

    def fail_once(*args, **kwargs):
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise RuntimeError("injected post-receipt crash")
        return real_register(*args, **kwargs)

    monkeypatch.setattr(worker_module, "register_multimedia_production", fail_once)
    with pytest.raises(RuntimeError, match="post-receipt"):
        produce_authorized_multimedia(
            ready.asset.asset_id, request, owner_id="owner-1", runtime=runtime
        )
    first_calls = tuple(calls)
    recovered = produce_authorized_multimedia(
        ready.asset.asset_id, request, owner_id="owner-1", runtime=runtime
    )
    assert recovered.production_link is not None
    assert tuple(calls) == first_calls
    assert attempts == 2
