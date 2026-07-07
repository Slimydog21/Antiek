"""SPR-04 multimedia audio experience pipeline tests."""

from __future__ import annotations

from substrate.multimedia.audio import (
    TTSResult,
    assemble_audio_experience,
    normalize_script_for_audio,
)
from substrate.multimedia.planner import (
    EvidenceChunk,
    MultimediaPlanRequest,
    build_multimedia_plan,
)


def _plan():
    evidence = (
        EvidenceChunk(
            chunk_id="chunk-ai",
            document_id="doc-ai",
            text="AI systems changed avionics analysis and cockpit training.",
        ),
        EvidenceChunk(
            chunk_id="chunk-history",
            document_id="doc-history",
            text="The early history of widebody aircraft changed airline economics.",
        ),
    )
    return build_multimedia_plan(
        MultimediaPlanRequest(
            topic="AI and widebody aircraft",
            target_minutes=20,
            mode="audio",
            selected_arc_ids=("history", "mechanism"),
            route_policy="cheapest",
        ),
        evidence,
    )


def test_normalization_keeps_source_alignment_and_pronunciation_notes():
    plan = _plan()

    paragraphs = normalize_script_for_audio(plan)

    assert paragraphs
    assert any("A I" in paragraph.text for paragraph in paragraphs)
    assert any(paragraph.pronunciation_notes for paragraph in paragraphs)
    assert all(paragraph.script_line_ids for paragraph in paragraphs)
    assert all(paragraph.source_status in {"sourced", "unsourced", "instruction"} for paragraph in paragraphs)


def test_fake_tts_audio_manifest_has_hashes_transcripts_and_chapters():
    plan = _plan()

    asset = assemble_audio_experience(plan, asset_id="mm-audio", revision_id="rev-audio")

    audio_files = [file for file in asset.manifest.files if file.kind == "audio"]
    transcript_files = [file for file in asset.manifest.files if file.kind == "transcript"]
    assert len(audio_files) == len(asset.chapters)
    assert len(transcript_files) == len(asset.chapters)
    assert all(file.sha256 and file.duration_seconds and file.mime for file in audio_files)
    assert all(chapter.transcript for chapter in asset.chapters)
    assert all(chapter.audio_file_id in {file.file_id for file in audio_files} for chapter in asset.chapters)
    assert asset.playback.total_duration_seconds == round(
        sum(chapter.duration_seconds for chapter in asset.chapters),
        2,
    )


def test_every_spoken_factual_paragraph_has_status_before_render():
    thin = build_multimedia_plan(
        MultimediaPlanRequest(topic="unsourced plane rumor", target_minutes=15),
        (),
    )

    asset = assemble_audio_experience(thin, asset_id="mm-thin", revision_id="rev-thin")

    assert any(paragraph.source_status == "unsourced" for paragraph in asset.paragraphs)
    assert all(paragraph.source_status for paragraph in asset.paragraphs)


def test_playback_model_exposes_current_chapter_sources_and_steering_target():
    asset = assemble_audio_experience(_plan(), asset_id="mm-audio", revision_id="rev-audio")

    first = asset.playback.chapter_at(0)
    assert first is not None
    assert first.chapter_id == asset.chapters[0].chapter_id
    assert first.steering_target == first.chapter_id
    assert first.source_cards == asset.chapters[0].source_chunk_ids

    later = asset.playback.chapter_at(asset.chapters[0].duration_seconds + 0.01)
    assert later is not None
    assert later.chapter_id == asset.chapters[1].chapter_id


def test_transcript_delta_is_recorded_when_provider_differs():
    class MutatingTTS:
        name = "mutating"
        model = "test"

        def synthesize(self, request):
            return TTSResult(
                audio_bytes=b"audio",
                duration_seconds=1.0,
                transcript=request.text + " changed",
                provider=self.name,
                model=self.model,
            )

    asset = assemble_audio_experience(
        _plan(),
        asset_id="mm-audio",
        revision_id="rev-mutating",
        provider=MutatingTTS(),
    )

    assert any(not chapter.transcript_matches_audio for chapter in asset.chapters)
    assert all(chapter.transcript_delta for chapter in asset.chapters)
