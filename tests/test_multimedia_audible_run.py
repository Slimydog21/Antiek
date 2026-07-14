from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from substrate.multimedia.audible_run import (
    AudibleRunArtifact,
    AudibleRunManifest,
    RunTranscriptSpan,
    assemble_audible_run,
    prepare_audible_run_plan,
)
from substrate.multimedia.audio_assembly import assemble_audio_experience
from substrate.multimedia.planner import (
    EvidenceChunk,
    MultimediaPlanRequest,
    build_multimedia_plan,
)
from substrate.multimedia.tts import FakeTTSProvider, TTSRequest, TTSResult


def _plan():
    plan = build_multimedia_plan(
        MultimediaPlanRequest(
            topic="jet engine history",
            target_minutes=15,
            selected_arc_ids=("history", "mechanism"),
        ),
        evidence=(
            EvidenceChunk(
                chunk_id="chunk-whittle",
                document_id="doc-engines",
                text="Early jet engine history began with Frank Whittle's turbojet patent in 1930.",
                title="Early turbojets",
                section_path="history/whittle",
            ),
            EvidenceChunk(
                chunk_id="chunk-compressor",
                document_id="doc-engines",
                text="Axial compressors enabled high mass flow through compact engines.",
                title="Axial compression",
                section_path="mechanism/compressor",
            ),
        ),
    )
    assert not plan.unsourced_line_ids
    return plan


class _CountingTTS(FakeTTSProvider):
    def __init__(self) -> None:
        self.requests: list[TTSRequest] = []

    def synthesize(self, request: TTSRequest) -> TTSResult:
        self.requests.append(request)
        return super().synthesize(request)


class _FractionalTTS(FakeTTSProvider):
    def synthesize(self, request: TTSRequest) -> TTSResult:
        result = super().synthesize(request)
        return TTSResult(
            audio_bytes=result.audio_bytes,
            mime=result.mime,
            duration_seconds=0.0014,
            cost_usd=0,
            provider=self.name,
            voice=request.voice,
            speed=request.speed,
        )


def test_transform_inserts_audible_markers_with_exact_inherited_authority() -> None:
    original = _plan()
    transformed = prepare_audible_run_plan(original)
    original_by_chapter = {
        chapter.chapter_id: [
            line
            for line in original.script_lines
            if line.line_id.startswith(f"{chapter.chapter_id}-line-")
            and line.kind == "factual"
            and line.citations
        ]
        for chapter in original.chapters
    }
    for chapter in original.chapters:
        chapter_lines = [
            line
            for line in transformed.script_lines
            if line.line_id.startswith(f"{chapter.chapter_id}-line-")
        ]
        assert chapter_lines[0].line_id.endswith("-run-signpost")
        assert chapter_lines[0].kind == "transition"
        grounded = original_by_chapter[chapter.chapter_id]
        if not grounded:
            continue
        remember = next(line for line in chapter_lines if line.line_id.endswith("-run-remember"))
        recap = next(line for line in chapter_lines if line.line_id.endswith("-run-recap"))
        assert remember.text == "Remember this. " + grounded[0].text
        assert tuple(c.chunk_id for c in remember.citations) == tuple(
            c.chunk_id for c in grounded[0].citations
        )
        assert remember.evidence_derivation is None
        assert recap.text == "Chapter recap. " + " ".join(line.text for line in grounded)
        assert {citation.chunk_id for citation in recap.citations} == {
            citation.chunk_id for line in grounded for citation in line.citations
        }


def test_no_sourced_claims_refuses_to_manufacture_retention_content() -> None:
    plan = build_multimedia_plan(
        MultimediaPlanRequest(topic="unsupported topic", target_minutes=15), evidence=()
    )
    with pytest.raises(ValueError, match="sourced factual claim"):
        prepare_audible_run_plan(plan)


def test_legacy_citation_presence_cannot_enter_new_audible_production() -> None:
    plan = _plan().model_copy(update={"grounding_contract": "citation_presence_v1"})

    with pytest.raises(ValueError, match="exact_extract_v2"):
        prepare_audible_run_plan(plan)


def test_unsourced_or_orphan_lines_fail_before_synthesis() -> None:
    plan = _plan()
    values = plan.model_dump(mode="python")
    lines = list(plan.script_lines)
    first = lines[0].model_dump(mode="python")
    first["citations"] = ()
    first["evidence_derivation"] = None
    first["unsourced_reason"] = "not verified"
    lines[0] = type(lines[0]).model_validate(first)
    unsourced = plan.model_copy(
        update={
            "script_lines": tuple(lines),
            "unsourced_line_ids": (lines[0].line_id,),
        }
    )
    with pytest.raises(ValueError, match="unsourced factual"):
        prepare_audible_run_plan(unsourced)

    values = plan.model_dump(mode="python")
    lines = list(plan.script_lines)
    orphan = lines[0].model_dump(mode="python")
    orphan.update(
        line_id="orphan-line-0",
        sequence=len(lines),
        kind="transition",
        citations=(),
        evidence_derivation=None,
    )
    lines.append(type(lines[0]).model_validate(orphan))
    values["script_lines"] = tuple(lines)
    orphaned = type(plan).model_validate(values)
    with pytest.raises(ValueError, match="does not belong"):
        prepare_audible_run_plan(orphaned)


def test_one_synthesis_pass_produces_complete_timing_and_source_manifest() -> None:
    tts = _CountingTTS()
    bundle = assemble_audible_run(_plan(), tts, asset_id="asset-run", revision_id="revision-1")
    manifest = bundle.artifact.manifest
    assert len(tts.requests) == len(bundle.plan.script_lines)
    assert manifest.transcript_spans[0].start_offset_seconds == 0
    assert manifest.transcript_spans[-1].end_offset_seconds == pytest.approx(
        manifest.total_duration_seconds, abs=0.001
    )
    for left, right in zip(
        manifest.transcript_spans[:-1], manifest.transcript_spans[1:], strict=True
    ):
        assert left.end_offset_seconds == pytest.approx(right.start_offset_seconds, abs=0.001)
    line_by_id = {line.line_id: line for line in bundle.plan.script_lines}
    for span in manifest.transcript_spans:
        assert span.source_chunk_ids == tuple(
            citation.chunk_id for citation in line_by_id[span.line_id].citations
        )
    assert {marker.kind for marker in manifest.retention_markers} == {"remember", "recap"}
    assert all(marker.source_chunk_ids for marker in manifest.retention_markers)


def test_fractional_millisecond_durations_do_not_accumulate_timeline_drift() -> None:
    bundle = assemble_audible_run(
        _plan(), _FractionalTTS(), asset_id="fractional", revision_id="revision-1"
    )
    assert bundle.artifact.manifest.transcript_spans[-1].end_offset_seconds == pytest.approx(
        bundle.experience.total_duration_seconds, abs=0.001
    )
    assert bundle.experience.total_duration_seconds == round(
        len(bundle.plan.script_lines) * 0.0014, 3
    )


def test_post_listen_cards_only_expose_original_grounded_claims() -> None:
    bundle = assemble_audible_run(
        _plan(), FakeTTSProvider(), asset_id="asset-run", revision_id="revision-1"
    )
    cards = bundle.artifact.manifest.learned_claims
    assert cards
    assert all("-run-" not in card.line_id for card in cards)
    assert all(card.source_chunk_ids for card in cards)
    assert all(", ".join(card.source_chunk_ids) in card.follow_up_prompt for card in cards)


def test_artifact_round_trips_deterministically_and_rejects_tamper(tmp_path: Path) -> None:
    first = assemble_audible_run(
        _plan(), FakeTTSProvider(), asset_id="asset-run", revision_id="revision-1"
    ).artifact
    second = assemble_audible_run(
        _plan(), FakeTTSProvider(), asset_id="asset-run", revision_id="revision-1"
    ).artifact
    assert first == second
    payload = first.to_json()
    path = tmp_path / "audible-run.json"
    path.write_text(payload)
    assert AudibleRunArtifact.reopen(path.read_text()) == first
    tampered = json.loads(payload)
    tampered["manifest"]["asset_id"] = "other-asset"
    with pytest.raises(ValueError, match="digest"):
        AudibleRunArtifact.reopen(json.dumps(tampered))
    tampered["unexpected"] = True
    with pytest.raises(ValidationError):
        AudibleRunArtifact.reopen(json.dumps(tampered))


def test_manifest_rejects_timing_gap_duplicate_ids_and_ungrounded_marker() -> None:
    manifest = assemble_audible_run(
        _plan(), FakeTTSProvider(), asset_id="asset-run", revision_id="revision-1"
    ).artifact.manifest
    values = manifest.model_dump(mode="python")
    spans = [dict(span) for span in values["transcript_spans"]]
    spans[1]["start_offset_seconds"] += 0.1
    values["transcript_spans"] = spans
    with pytest.raises(ValidationError, match="gap or overlap"):
        AudibleRunManifest.model_validate(values)

    values = manifest.model_dump(mode="python")
    spans = [dict(span) for span in values["transcript_spans"]]
    spans[1]["paragraph_id"] = spans[0]["paragraph_id"]
    values["transcript_spans"] = spans
    with pytest.raises(ValidationError, match="paragraph ids"):
        AudibleRunManifest.model_validate(values)

    values = manifest.model_dump(mode="python")
    markers = [dict(marker) for marker in values["retention_markers"]]
    markers[0]["source_chunk_ids"] = ()
    values["retention_markers"] = markers
    with pytest.raises(ValidationError):
        AudibleRunManifest.model_validate(values)


@pytest.mark.parametrize(
    ("surface", "mutation", "message"),
    [
        (
            "retention_markers",
            lambda row: row.update(chapter_id="ghost-chapter"),
            "retention marker",
        ),
        (
            "learned_claims",
            lambda row: row.update(claim_text="fabricated learned claim"),
            "learned claim",
        ),
        (
            "transcript_spans",
            lambda row: row.update(chapter_id="ghost-chapter"),
            "unknown chapter",
        ),
    ],
)
def test_manifest_rejects_cross_reference_forgery(surface, mutation, message) -> None:
    manifest = assemble_audible_run(
        _plan(), FakeTTSProvider(), asset_id="asset-run", revision_id="revision-1"
    ).artifact.manifest
    values = manifest.model_dump(mode="python")
    rows = [dict(row) for row in values[surface]]
    mutation(rows[0])
    values[surface] = rows
    with pytest.raises(ValidationError, match=message):
        AudibleRunManifest.model_validate(values)


def test_seal_revalidates_model_construct_and_base_audio_remains_compatible() -> None:
    manifest = assemble_audible_run(
        _plan(), FakeTTSProvider(), asset_id="asset-run", revision_id="revision-1"
    ).artifact.manifest
    forged = AudibleRunManifest.model_construct(
        **{**manifest.model_dump(mode="python"), "transcript_spans": ()}
    )
    with pytest.raises(ValidationError):
        AudibleRunArtifact.seal(forged)

    base = assemble_audio_experience(
        _plan(), FakeTTSProvider(), asset_id="base-audio", revision_id="revision-1"
    )
    assert base.chapters
    assert all(chapter.paragraph_spans for chapter in base.chapters)
    assert all(
        span.marker_kind == "content"
        for chapter in base.chapters
        for span in chapter.paragraph_spans
    )


def test_manifest_requires_real_sourced_factual_content_and_bidirectional_status() -> None:
    manifest = assemble_audible_run(
        _plan(), FakeTTSProvider(), asset_id="asset-run", revision_id="revision-1"
    ).artifact.manifest
    values = manifest.model_dump(mode="python")
    first_chapter = manifest.chapters[0].chapter_id
    removed: set[str] = set()
    spans = [dict(span) for span in values["transcript_spans"]]
    for span in spans:
        if (
            span["chapter_id"] == first_chapter
            and span["marker_kind"] == "content"
            and span["line_kind"] == "factual"
        ):
            removed.add(span["line_id"])
            span["source_chunk_ids"] = ()
            span["grounding_status"] = "not_required"
    values["transcript_spans"] = spans
    values["learned_claims"] = tuple(
        card for card in values["learned_claims"] if card["line_id"] not in removed
    )
    with pytest.raises(ValidationError, match="sourced factual content"):
        AudibleRunManifest.model_validate(values)

    values = manifest.model_dump(mode="python")
    spans = [dict(span) for span in values["transcript_spans"]]
    signpost = next(span for span in spans if span["marker_kind"] == "signpost")
    signpost["grounding_status"] = "sourced"
    values["transcript_spans"] = spans
    with pytest.raises(ValidationError, match="grounding status"):
        AudibleRunManifest.model_validate(values)


def test_sourced_transition_is_supported_but_not_presented_as_learned_claim() -> None:
    plan = _plan()
    values = plan.model_dump(mode="python")
    lines = list(plan.script_lines)
    row = lines[0].model_dump(mode="python")
    row.update(
        line_id="intro-line-context",
        sequence=len(lines),
        kind="transition",
        text="The next source-backed section changes focus.",
        evidence_derivation=None,
    )
    lines.append(type(lines[0]).model_validate(row))
    values["script_lines"] = tuple(lines)
    plan = type(plan).model_validate(values)
    bundle = assemble_audible_run(
        plan, FakeTTSProvider(), asset_id="transition", revision_id="revision-1"
    )
    span = next(
        span
        for span in bundle.artifact.manifest.transcript_spans
        if span.line_id == "intro-line-context"
    )
    assert span.grounding_status == "sourced" and span.line_kind == "transition"
    assert span.line_id not in {card.line_id for card in bundle.artifact.manifest.learned_claims}


def test_marker_text_and_cardinality_are_derived_not_caller_asserted() -> None:
    manifest = assemble_audible_run(
        _plan(), FakeTTSProvider(), asset_id="asset-run", revision_id="revision-1"
    ).artifact.manifest
    values = manifest.model_dump(mode="python")
    spans = [dict(span) for span in values["transcript_spans"]]
    remember = next(span for span in spans if span["marker_kind"] == "remember")
    remember["spoken_text"] = "Remember this. A different unsupported claim."
    values["transcript_spans"] = spans
    with pytest.raises(ValidationError, match="remember marker"):
        AudibleRunManifest.model_validate(values)

    values = manifest.model_dump(mode="python")
    markers = [dict(marker) for marker in values["retention_markers"]]
    markers.append({**markers[0], "line_id": "invented-run-remember"})
    values["retention_markers"] = markers
    with pytest.raises(ValidationError):
        AudibleRunManifest.model_validate(values)


def test_seal_revalidates_bypass_constructed_nested_models() -> None:
    manifest = assemble_audible_run(
        _plan(), FakeTTSProvider(), asset_id="asset-run", revision_id="revision-1"
    ).artifact.manifest
    span_values = manifest.transcript_spans[0].model_dump(mode="python")
    span_values.update(source_chunk_ids=(), grounding_status="sourced")
    forged_span = RunTranscriptSpan.model_construct(**span_values)
    forged_manifest = AudibleRunManifest.model_construct(
        **{
            **manifest.model_dump(mode="python"),
            "transcript_spans": (forged_span, *manifest.transcript_spans[1:]),
        }
    )
    with pytest.raises(ValidationError, match="grounding status"):
        AudibleRunArtifact.seal(forged_manifest)
