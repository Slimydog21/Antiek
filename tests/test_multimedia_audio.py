"""Multimedia SPR-04 — audio experience pipeline: narration, TTS seam, chaptered
assembly, and the playback read-model.

Exercises the REAL production path: ``build_multimedia_plan`` -> normalized
narration -> fake TTS -> ``assemble_audio_experience`` -> SPR-01 manifest ->
``build_playback_read_model``. No provider key is required (CI uses the
deterministic fake TTS); a real voice is operator-gated via ``ANTIEK_TTS_PROVIDER``.

Verification gates from the sprint spec:
* Audio manifest — fixture fake-TTS run yields chapters, durations, hashes,
  transcript.
* Grounding — no spoken factual paragraph lacks a status (sourced OR explicitly
  unsourced).
Plus the four milestones: normalization, TTS seam, chaptered assembly, listening
UX hooks (current chapter + source cards + steering target).
"""

from __future__ import annotations

import pytest

from substrate.contracts.multimedia import MultimediaManifest, SourceCitation
from substrate.multimedia import (
    AudioExperience,
    FakeTTSProvider,
    MultimediaPlanRequest,
    PlaybackReadModel,
    TTSRequest,
    assemble_audio_experience,
    build_multimedia_plan,
    build_playback_read_model,
    make_tts_provider,
    normalize_line,
    normalize_script,
)
from substrate.multimedia.planner import EvidenceChunk, ScriptLine

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

EVIDENCE = (
    EvidenceChunk(
        chunk_id="c-1",
        document_id="d-1",
        text="Wide-bandgap semiconductors such as silicon carbide handle high voltages efficiently.",
        title="Wide-bandgap materials",
        section_path="§2",
    ),
    EvidenceChunk(
        chunk_id="c-2",
        document_id="d-1",
        text="Gallium nitride switching frequencies reach the megahertz range for compact power converters.",
        title="Gallium nitride",
        section_path="§3",
    ),
)


@pytest.fixture
def plan():
    return build_multimedia_plan(
        MultimediaPlanRequest(topic="wide-bandgap semiconductors", target_minutes=15),
        evidence=EVIDENCE,
    )


@pytest.fixture
def experience(plan):
    return assemble_audio_experience(
        plan,
        FakeTTSProvider(),
        asset_id="asset-1",
        revision_id="rev-1",
    )


# ---------------------------------------------------------------------------
# Milestone 1 — narration script normalization
# ---------------------------------------------------------------------------


def test_normalize_expands_abbreviations_and_strips_markdown():
    line = ScriptLine(
        line_id="ch1-line-1",
        kind="factual",
        sequence=0,
        text="**Note:** e.g. SiC (vs. GaN) is **fast**.",
        citations=(SourceCitation(chunk_id="c-1", document_id="d-1"),),
    )
    para = normalize_line(line, pronunciation_notes={"SiC": "silicon carbide"})
    assert "for example" in para.text
    assert "versus" in para.text
    assert "silicon carbide" in para.text
    assert "**" not in para.text
    assert para.source_chunk_ids == ("c-1",)
    assert para.unsourced is False


def test_normalize_flags_unsourced_factual_line_not_drops_it():
    line = ScriptLine(
        line_id="ch1-line-9",
        kind="factual",
        sequence=9,
        text="A speculative aside with no citation.",
        citations=(),
        unsourced_reason="operator speculation",
    )
    para = normalize_line(line)
    assert para.unsourced is True
    assert para.source_chunk_ids == ()


def test_normalize_preserves_source_alignment_per_paragraph():
    lines = (
        ScriptLine(
            line_id="ch1-line-1",
            kind="factual",
            sequence=0,
            text="First cited claim.",
            citations=(SourceCitation(chunk_id="c-1", document_id="d-1"),),
        ),
        ScriptLine(
            line_id="ch1-line-2",
            kind="factual",
            sequence=1,
            text="Second cited claim.",
            citations=(SourceCitation(chunk_id="c-2", document_id="d-1"),),
        ),
    )
    paras = normalize_script(lines)
    assert [p.line_id for p in paras] == ["ch1-line-1", "ch1-line-2"]
    assert paras[0].source_chunk_ids == ("c-1",)
    assert paras[1].source_chunk_ids == ("c-2",)


def test_normalize_rejects_empty_script():
    with pytest.raises(ValueError, match="empty script"):
        normalize_script(())


# ---------------------------------------------------------------------------
# Milestone 2 — TTS provider seam
# ---------------------------------------------------------------------------


def test_fake_tts_is_deterministic():
    tts = FakeTTSProvider()
    a = tts.synthesize(TTSRequest(text="the same paragraph", voice="narrator", speed=1.0))
    b = tts.synthesize(TTSRequest(text="the same paragraph", voice="narrator", speed=1.0))
    assert a.sha256 == b.sha256
    assert a.duration_seconds == b.duration_seconds > 0
    assert a.audio_bytes  # never empty


def test_make_tts_provider_defaults_to_fake_without_credentials():
    provider = make_tts_provider()
    assert provider.name == "fake"


def test_tts_request_rejects_empty_text_and_nonpositive_speed():
    with pytest.raises(ValueError):
        TTSRequest(text="   ")
    with pytest.raises(ValueError):
        TTSRequest(text="ok", speed=0)


# ---------------------------------------------------------------------------
# Milestone 3 — chaptered audio assembly (verification gate: audio manifest)
# ---------------------------------------------------------------------------


def test_assembly_emits_valid_manifest_with_chapters_durations_hashes(experience):
    assert isinstance(experience, AudioExperience)
    assert isinstance(experience.manifest, MultimediaManifest)
    # Manifest referential integrity is enforced in the contract constructor; if
    # assembly built a malformed manifest, construction would have raised.
    assert len(experience.chapters) >= 1
    for chapter in experience.chapters:
        assert chapter.duration_seconds > 0
        assert chapter.audio_file_id
        assert chapter.start_offset_seconds < chapter.end_offset_seconds
    assert experience.total_duration_seconds == pytest.approx(
        sum(c.duration_seconds for c in experience.chapters), abs=0.01
    )
    # Every audio + transcript file carries a valid 64-hex sha256.
    for f in experience.manifest.files:
        assert len(f.sha256) == 64
        assert all(ch in "0123456789abcdef" for ch in f.sha256)


def test_assembly_is_deterministic(plan):
    exp1 = assemble_audio_experience(
        plan, FakeTTSProvider(), asset_id="a", revision_id="r"
    )
    exp2 = assemble_audio_experience(
        plan, FakeTTSProvider(), asset_id="a", revision_id="r"
    )
    hashes1 = {f.file_id: f.sha256 for f in exp1.manifest.files}
    hashes2 = {f.file_id: f.sha256 for f in exp2.manifest.files}
    assert hashes1 == hashes2  # byte-stable manifest under the fake TTS


def test_assembly_produces_replayable_independent_chapter_files(experience):
    file_ids = {c.audio_file_id for c in experience.chapters}
    # Each chapter is its own audio file (independently replayable).
    assert len(file_ids) == len(experience.chapters)
    # Each chapter segment references exactly its own audio file.
    seg_by_id = {s.segment_id: s for s in experience.manifest.segments}
    for chapter in experience.chapters:
        seg = seg_by_id[f"seg-{chapter.chapter_id}"]
        assert seg.file_ids == (chapter.audio_file_id,)


def test_assembly_grounds_every_cited_paragraph(experience):
    # Verification gate: grounding — no spoken factual paragraph lacks status.
    # Sourced paragraphs appear in claim_to_chunk; unsourced ones are surfaced
    # honestly in unsourced_paragraph_ids rather than hidden.
    cited_line_ids = {claim.script_line_id for claim in experience.manifest.claim_to_chunk}
    for chapter in experience.chapters:
        for line_id in chapter.script_line_ids:
            line = next(
                ln for ln in experience.manifest.script_lines if ln.line_id == line_id
            )
            if line.kind == "factual":
                is_sourced = bool(line.citations) and line_id in cited_line_ids
                is_marked_unsourced = any(
                    line_id in p for p in experience.unsourced_paragraph_ids
                ) or line.unsourced_reason is not None
                assert is_sourced or is_marked_unsourced, (
                    f"factual line {line_id} is neither sourced nor marked unsourced"
                )


def test_assembly_transcript_covers_full_duration(experience):
    transcript = next(
        f for f in experience.manifest.files if f.file_id == experience.transcript_file_id
    )
    assert transcript.kind == "transcript"
    assert transcript.duration_seconds == pytest.approx(
        experience.total_duration_seconds, abs=0.01
    )
    assert experience.manifest.transcript_file_id == transcript.file_id


def test_assembly_raises_when_no_chapter_has_narration():
    # A plan whose chapters exist but map to no script lines cannot be assembled
    # through the public path; emulate by building a plan then clearing script.
    plan = build_multimedia_plan(
        MultimediaPlanRequest(topic="topic x", target_minutes=15), evidence=()
    )
    plan = plan.model_copy(update={"script_lines": ()})
    with pytest.raises(ValueError, match="no chapters|empty script"):
        assemble_audio_experience(
            plan, FakeTTSProvider(), asset_id="a", revision_id="r"
        )


# ---------------------------------------------------------------------------
# Milestone 4 — listening UX hooks (playback read-model + steering)
# ---------------------------------------------------------------------------


def test_playback_resolves_current_chapter_by_offset(experience):
    model = build_playback_read_model(experience)
    assert isinstance(model, PlaybackReadModel)
    first = model.chapters[0]
    # Mid-first-chapter resolves to the first chapter.
    assert model.chapter_at_offset(first.duration_seconds / 2).chapter_id == first.chapter_id
    # Before zero is None.
    assert model.chapter_at_offset(-1) is None


def test_playback_source_cards_surface_chapter_provenance(experience):
    model = build_playback_read_model(experience)
    for chapter in model.chapters:
        # Every source card carries the chunk id and the chapter's spoken lines.
        for card in chapter.source_cards:
            assert card.chunk_id
            assert card.line_ids == chapter.script_line_ids


def test_steering_targets_one_chapter_for_regeneration(experience):
    model = build_playback_read_model(experience)
    target_chapter = experience.chapters[0]
    target = model.steering_target(
        target_chapter.chapter_id,
        instruction="make the opening more concrete with an analogy",
        voice="narrator",
        speed=1.0,
    )
    assert target.chapter_id == target_chapter.chapter_id
    assert target.instruction.startswith("make the opening")


def test_steering_rejects_unknown_chapter_and_empty_instruction(experience):
    model = build_playback_read_model(experience)
    with pytest.raises(KeyError):
        model.steering_target("no-such-chapter", instruction="x", voice="n", speed=1.0)
    real = experience.chapters[0].chapter_id
    with pytest.raises(ValueError):
        model.steering_target(real, instruction="   ", voice="n", speed=1.0)


def test_playback_total_and_transcript_match_experience(experience):
    model = build_playback_read_model(experience)
    assert model.total_duration_seconds == experience.total_duration_seconds
    assert model.transcript_file_id == experience.transcript_file_id
    assert model.asset_id == experience.manifest.asset_id
