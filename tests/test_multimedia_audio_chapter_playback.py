from __future__ import annotations

import math
from types import SimpleNamespace

import pytest

from substrate.multimedia.planner import (
    EvidenceChunk,
    MultimediaPlanRequest,
    build_multimedia_plan,
)
from substrate.multimedia.verified_audio_playback import (
    AudioChapterPlaybackMetadata,
    VerifiedPlaybackError,
    project_audio_claims_for_plan,
    project_audio_learned_claims,
    project_legacy_audio_learned_claims,
    validate_audio_chapters,
)


def _chapter(
    chapter_id: str = "chapter-1",
    *,
    sequence: int = 0,
    start: float = 0.0,
    end: float = 10.0,
) -> AudioChapterPlaybackMetadata:
    return AudioChapterPlaybackMetadata(chapter_id, "Exact title", sequence, start, end)


def test_audio_chapter_timeline_accepts_exact_contiguous_projection() -> None:
    chapters = (_chapter(end=4.25), _chapter("chapter-2", sequence=1, start=4.25))
    assert validate_audio_chapters(
        chapters, chapter_ids=("chapter-1", "chapter-2"), duration_seconds=10.0
    ) == chapters


@pytest.mark.parametrize(
    ("chapters", "chapter_ids", "duration"),
    [
        ((_chapter(start=0.1),), ("chapter-1",), 10.0),
        ((_chapter(end=4.0), _chapter("chapter-2", sequence=1, start=4.1)),
         ("chapter-1", "chapter-2"), 10.0),
        ((_chapter(end=4.0), _chapter("chapter-2", sequence=1, start=3.9)),
         ("chapter-1", "chapter-2"), 10.0),
        ((_chapter(sequence=1),), ("chapter-1",), 10.0),
        ((_chapter(),), ("chapter-2",), 10.0),
        ((_chapter(), _chapter()), ("chapter-1", "chapter-1"), 20.0),
        ((_chapter(end=9.998),), ("chapter-1",), 10.0),
        ((_chapter(end=math.inf),), ("chapter-1",), 10.0),
    ],
)
def test_audio_chapter_timeline_rejects_malformed_timing_order_and_ids(
    chapters: tuple[AudioChapterPlaybackMetadata, ...],
    chapter_ids: tuple[str, ...],
    duration: float,
) -> None:
    with pytest.raises(VerifiedPlaybackError, match="chapter"):
        validate_audio_chapters(chapters, chapter_ids=chapter_ids, duration_seconds=duration)


def test_audio_claim_projection_preserves_exact_plan_evidence() -> None:
    plan = build_multimedia_plan(
        MultimediaPlanRequest(topic="jet history", target_minutes=15),
        (
            EvidenceChunk(
                chunk_id="chunk-1",
                document_id="doc-1",
                title="Jet history",
                section_path="Origins / Whittle",
                text="Frank Whittle patented an early turbojet design in 1930.",
                authority_kind="canonical_graph",
            ),
        ),
    )
    line = next(
        row
        for row in plan.script_lines
        if row.kind == "factual" and row.evidence_derivation is not None
    )
    claim = SimpleNamespace(
        line_id=line.line_id,
        chapter_id=line.line_id.split("-line-", 1)[0],
        claim_text=line.text,
        source_chunk_ids=tuple(row.chunk_id for row in line.citations),
        follow_up_prompt="Review the exact source.",
    )

    projected = project_audio_learned_claims((claim,), plan=plan)

    assert projected[0].line_id == line.line_id
    assert projected[0].evidence_sources[0].exact_text == line.text
    assert projected[0].evidence_sources[0].document_id == "doc-1"
    assert projected[0].evidence_sources[0].authority_kind == "canonical_graph"


@pytest.mark.parametrize("field", ["line_id", "claim_text", "source_chunk_ids"])
def test_audio_claim_projection_rejects_receipt_plan_drift(field: str) -> None:
    plan = build_multimedia_plan(
        MultimediaPlanRequest(topic="jet history", target_minutes=15),
        (
            EvidenceChunk(
                chunk_id="chunk-1",
                document_id="doc-1",
                text="Jet history evidence.",
            ),
        ),
    )
    line = next(
        row
        for row in plan.script_lines
        if row.kind == "factual" and row.evidence_derivation is not None
    )
    values = {
        "line_id": line.line_id,
        "chapter_id": line.line_id.split("-line-", 1)[0],
        "claim_text": line.text,
        "source_chunk_ids": tuple(row.chunk_id for row in line.citations),
        "follow_up_prompt": "Review the exact source.",
    }
    values[field] = "wrong" if field != "source_chunk_ids" else ("wrong",)

    with pytest.raises(VerifiedPlaybackError, match="claim evidence"):
        project_audio_learned_claims((SimpleNamespace(**values),), plan=plan)


def test_legacy_audio_claim_projection_preserves_playback_without_exact_excerpt() -> None:
    plan = build_multimedia_plan(
        MultimediaPlanRequest(topic="jet history", target_minutes=15),
        (EvidenceChunk(chunk_id="chunk-1", document_id="doc-1", text="Jet history evidence."),),
    )
    line = next(
        row
        for row in plan.script_lines
        if row.kind == "factual" and row.evidence_derivation is not None
    )
    legacy_line = line.model_copy(update={"evidence_derivation": None})
    legacy_plan = plan.model_copy(
        update={
            "script_lines": tuple(
                legacy_line if row.line_id == line.line_id else row
                for row in plan.script_lines
            )
        }
    )
    claim = SimpleNamespace(
        line_id=line.line_id,
        chapter_id=line.line_id.split("-line-", 1)[0],
        claim_text=line.text,
        source_chunk_ids=tuple(row.chunk_id for row in line.citations),
        follow_up_prompt="Review the source record.",
    )

    projected = project_legacy_audio_learned_claims((claim,), plan=legacy_plan)

    assert projected[0].evidence_status == "unavailable_legacy"
    assert projected[0].source_chunk_ids == ("chunk-1",)
    assert projected[0].evidence_sources == ()

    assert project_audio_claims_for_plan((claim,), plan=legacy_plan) == projected


def test_audio_claim_projection_rejects_missing_and_partially_migrated_lines() -> None:
    plan = build_multimedia_plan(
        MultimediaPlanRequest(topic="jet history", target_minutes=15),
        (EvidenceChunk(chunk_id="chunk-1", document_id="doc-1", text="Jet history evidence."),),
    )
    lines = [row for row in plan.script_lines if row.kind == "factual"]
    claim = SimpleNamespace(
        line_id="missing-line",
        chapter_id="missing",
        claim_text="missing",
        source_chunk_ids=("chunk-1",),
        follow_up_prompt="Review the source.",
    )
    with pytest.raises(VerifiedPlaybackError, match="conflicts"):
        project_audio_claims_for_plan((claim,), plan=plan)

    if len(lines) < 2:
        pytest.skip("planner fixture did not produce two factual lines")
    mixed_plan = plan.model_copy(
        update={
            "script_lines": tuple(
                row.model_copy(update={"evidence_derivation": None})
                if row.line_id == lines[0].line_id
                else row
                for row in plan.script_lines
            )
        }
    )
    claims = tuple(
        SimpleNamespace(
            line_id=row.line_id,
            chapter_id=row.line_id.split("-line-", 1)[0],
            claim_text=row.text,
            source_chunk_ids=tuple(citation.chunk_id for citation in row.citations),
            follow_up_prompt="Review the source.",
        )
        for row in lines[:2]
    )
    with pytest.raises(VerifiedPlaybackError, match="partially migrated"):
        project_audio_claims_for_plan(claims, plan=mixed_plan)
