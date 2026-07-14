from __future__ import annotations

import io
import shutil
import wave
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

from substrate.multimedia.authorized_production_worker import (
    AuthorizedProductionError,
    AuthorizedProductionRequest,
    AuthorizedProductionRuntime,
    ChapterNarrationAuthority,
    produce_authorized_audio,
)
from substrate.multimedia.chapter_tts_production import ChapterTTSSynthesisResult
from substrate.multimedia.execution_authorization_issuer import ExecutionAuthorizationIssuer
from substrate.multimedia.narration_authorization import (
    NarrationAuthorizationRequest,
    TrustedNarrationTerms,
    authorize_multimedia_chapter_narration,
)
from substrate.multimedia.paid_audio_receipt import PaidAudioReceipt, paid_audio_receipt_path
from substrate.multimedia.read_model import CreateMultimediaDraftRequest, MultimediaAssetStore
from substrate.multimedia.reviewed_visual_registry import ReviewedVisualRegistry
from substrate.multimedia.verified_paid_audio_playback import VerifiedPaidAudioPlaybackRuntime
from substrate.multimedia.verified_playback import VerifiedPlaybackRuntime

NOW = datetime(2026, 7, 14, tzinfo=UTC)
SIGNING_KEY = b"s" * 32
NARRATION_KEY = b"n" * 32
RECEIPT_KEY = b"p" * 32


def _wav() -> bytes:
    payload = io.BytesIO()
    with wave.open(payload, "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(8_000)
        audio.writeframes(b"\x00\x00" * 8_000)
    return payload.getvalue()


def test_paid_audio_transforms_authority_registers_and_replays(tmp_path: Path) -> None:
    ffmpeg, ffprobe = shutil.which("ffmpeg"), shutil.which("ffprobe")
    if not ffmpeg or not ffprobe:
        pytest.skip("FFmpeg is required")
    store = MultimediaAssetStore(str(tmp_path / "assets"))
    draft = store.create_draft(
        CreateMultimediaDraftRequest(
            topic="Paid audible lesson",
            target_minutes=15,
            mode="audio",
            route_policy="balanced",
            sources=("One exact grounded audio fact.",),
            selected_arc_ids=("history",),
        ),
        owner_id="owner-1",
    )
    ready = store.approve_dry_run(draft.asset.asset_id, owner_id="owner-1")
    terms = TrustedNarrationTerms(
        provider="trusted-tts",
        model="voice-1",
        endpoint_capability="text-to-speech",
        catalog_version="catalog-1",
        catalog_digest="a" * 64,
        quote_id="quote-1",
        quote_ttl_seconds=600,
        recovery_authority_id="recovery-1",
        recovery_verification_key_digest="b" * 64,
        maximum_ceiling_microdollars=100_000,
    )
    issuer = ExecutionAuthorizationIssuer(
        db_path=str(tmp_path / "authorization.duckdb"), signing_key=SIGNING_KEY
    )
    authorities = tuple(
        ChapterNarrationAuthority(
            chapter_id=chapter.chapter_id,
            authorization=authorize_multimedia_chapter_narration(
                ready.asset.asset_id,
                NarrationAuthorizationRequest(
                    request_id=f"paid-{index}",
                    expected_revision_id=ready.asset.revision_id,
                    chapter_id=chapter.chapter_id,
                    approved_ceiling_microdollars=100_000,
                    operator_acknowledged_spend=True,
                    sample_rate_hz=8_000,
                ),
                owner_id="owner-1",
                store=store,
                terms_resolver=lambda _record, _chapter_id: terms,
                issuer=issuer,
                clock=lambda: NOW,
            ).authorization,
        )
        for index, chapter in enumerate(ready.plan.chapters)
    )
    for name in ("narration", "visual", "render", "receipt"):
        (tmp_path / name).mkdir(mode=0o700)
    calls: list[str] = []
    times = [NOW]

    def synthesize(row):
        calls.append(row.chapter_id)
        return ChapterTTSSynthesisResult(_wav(), f"provider-{row.chapter_id}")

    audio_playback = VerifiedPaidAudioPlaybackRuntime(
        receipt_root=str(tmp_path / "receipt"),
        receipt_key=RECEIPT_KEY,
        narration_key=NARRATION_KEY,
    )
    runtime = AuthorizedProductionRuntime(
        store=store,
        reviewed_visual_registry=ReviewedVisualRegistry(
            db_path=str(tmp_path / "visuals.duckdb"), integrity_key=b"g" * 32
        ),
        playback=VerifiedPlaybackRuntime(
            receipt_root=str(tmp_path / "receipt"),
            receipt_key=RECEIPT_KEY,
            narration_key=NARRATION_KEY,
            visual_key=b"v" * 32,
            render_key=b"r" * 32,
        ),
        signing_key=SIGNING_KEY,
        narration_integrity_key=NARRATION_KEY,
        visual_integrity_key=b"v" * 32,
        evidence_authority_key=b"e" * 32,
        render_integrity_key=b"r" * 32,
        receipt_key=RECEIPT_KEY,
        db_path=str(tmp_path / "production.duckdb"),
        narration_output_dir=str(tmp_path / "narration"),
        visual_output_dir=str(tmp_path / "visual"),
        render_output_dir=str(tmp_path / "render"),
        receipt_output_dir=str(tmp_path / "receipt"),
        synthesize=synthesize,
        verify_evidence=lambda *_args: pytest.fail("audio must not request visuals"),
        clock=lambda: times[-1],
        audio_playback=audio_playback,
        ffmpeg_path=ffmpeg,
        ffprobe_path=ffprobe,
    )
    request = AuthorizedProductionRequest(
        expected_revision_id=ready.asset.revision_id,
        chapter_authorities=authorities,
        sample_rate_hz=8_000,
    )
    first = produce_authorized_audio(
        ready.asset.asset_id, request, owner_id="owner-1", runtime=runtime
    )
    assert first.audio_production_link is not None
    assert first.production_link is None
    receipt = PaidAudioReceipt.reopen_from_file(
        paid_audio_receipt_path(
            tmp_path / "receipt", ready.asset.asset_id, ready.asset.revision_id
        ),
        receipt_key=RECEIPT_KEY,
        narration_key=NARRATION_KEY,
    )
    assert receipt.schema_version == "antiek.paid-audio-receipt.v1"
    assert receipt.transformed_plan.grounding_contract == "audible_transform_v1"
    assert receipt.retention_markers and receipt.learned_claims
    first_calls = tuple(calls)
    times.append(datetime(2026, 7, 14, 1, tzinfo=UTC))
    replay = produce_authorized_audio(
        ready.asset.asset_id, request, owner_id="owner-1", runtime=runtime
    )
    assert replay.audio_production_link == first.audio_production_link
    assert tuple(calls) == first_calls


def test_paid_audio_rejects_cheapest_before_synthesis(tmp_path: Path) -> None:
    store = MultimediaAssetStore(str(tmp_path / "assets"))
    draft = store.create_draft(
        CreateMultimediaDraftRequest(
            topic="Local only",
            target_minutes=15,
            mode="audio",
            route_policy="cheapest",
            sources=("Grounded local fact.",),
            selected_arc_ids=("history",),
        ),
        owner_id="owner-1",
    )
    ready = store.approve_dry_run(draft.asset.asset_id, owner_id="owner-1")
    with pytest.raises(AuthorizedProductionError, match="cheapest"):
        produce_authorized_audio(
            ready.asset.asset_id,
            AuthorizedProductionRequest(
                expected_revision_id=ready.asset.revision_id, chapter_authorities=()
            ),
            owner_id="owner-1",
            runtime=SimpleNamespace(store=store),  # type: ignore[arg-type]
        )
