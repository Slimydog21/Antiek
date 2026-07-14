"""SPR-02 multimedia curriculum/storyboard planner tests."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from substrate.contracts.multimedia import MultimediaManifest
from substrate.multimedia.planner import (
    EvidenceChunk,
    MultimediaPlanRequest,
    StoryboardScene,
    build_multimedia_plan,
)


def _evidence() -> tuple[EvidenceChunk, ...]:
    return (
        EvidenceChunk(
            chunk_id="chunk-history",
            document_id="doc-747",
            title="747 history",
            section_path="Page 4",
            text="The Boeing 747 began as a response to airline demand and early widebody history.",
        ),
        EvidenceChunk(
            chunk_id="chunk-engine",
            document_id="doc-747",
            title="747 engines",
            section_path="Page 9",
            text="High-bypass engine design and aerodynamic choices changed long-haul economics.",
        ),
        EvidenceChunk(
            chunk_id="chunk-safety",
            document_id="doc-747",
            title="747 safety",
            section_path="Page 12",
            text="The aircraft changed market capacity, safety procedures, and airport operations.",
        ),
    )


def test_request_duration_is_first_class_and_bounded():
    assert MultimediaPlanRequest(topic="airliners", target_minutes=15).target_minutes == 15
    assert MultimediaPlanRequest(topic="airliners", target_minutes=45).target_minutes == 45

    with pytest.raises(ValidationError):
        MultimediaPlanRequest(topic="airliners", target_minutes=14)
    with pytest.raises(ValidationError):
        MultimediaPlanRequest(topic="airliners", target_minutes=46)


def test_request_mode_supports_video_audio_and_hybrid():
    assert MultimediaPlanRequest(topic="planes", target_minutes=20, mode="video").mode == "video"
    assert MultimediaPlanRequest(topic="planes", target_minutes=20, mode="audio").mode == "audio"
    assert MultimediaPlanRequest(topic="planes", target_minutes=20, mode="hybrid").mode == "hybrid"

    with pytest.raises(ValidationError):
        MultimediaPlanRequest(topic="planes", target_minutes=20, mode="slides")  # type: ignore[arg-type]


def test_coverage_suggestions_cite_graph_evidence_and_offer_alternates():
    request = MultimediaPlanRequest(
        topic="Boeing 747",
        target_minutes=30,
        mode="hybrid",
        selected_arc_ids=("history", "mechanism"),
    )

    plan = build_multimedia_plan(request, _evidence())

    assert len(plan.suggestions) >= 4
    assert {s.arc_id for s in plan.suggestions} >= {"history", "mechanism", "comparison"}
    assert any(s.evidence for s in plan.suggestions)
    assert plan.chosen_arc_ids == ("history", "mechanism")


@pytest.mark.parametrize(
    "selected",
    [("history", "history"), ("history", "unsupported")],
)
def test_selected_coverage_arcs_reject_duplicate_or_unknown_ids(selected):
    with pytest.raises(ValidationError):
        MultimediaPlanRequest(
            topic="Boeing 747",
            target_minutes=30,
            selected_arc_ids=selected,
        )


def test_duration_math_sums_to_requested_minutes_and_reports_cuts():
    request = MultimediaPlanRequest(
        topic="Boeing 747",
        target_minutes=15,
        depth="deep",
        must_cover=("procurement politics", "engine design", "safety", "airports", "747SP"),
    )

    plan = build_multimedia_plan(request, _evidence())

    assert abs(plan.total_minutes - 15) <= plan.duration_tolerance_minutes
    assert any(chapter.cuts for chapter in plan.chapters)
    assert any("Must-cover item omitted" in omission for omission in plan.omissions)


def test_script_lines_are_grounded_or_flagged_before_render():
    request = MultimediaPlanRequest(topic="thinly sourced aircraft story", target_minutes=20)

    plan = build_multimedia_plan(request, ())

    assert plan.unsourced_line_ids
    assert set(plan.unsourced_line_ids) == {
        line.line_id for line in plan.script_lines if line.kind == "factual" and not line.citations
    }
    assert any("weak source coverage" in omission for omission in plan.omissions)


def test_each_scene_has_information_purpose_not_decorative_filler():
    request = MultimediaPlanRequest(topic="Boeing 747", target_minutes=20, mode="video")

    plan = build_multimedia_plan(request, _evidence())

    assert all(scene.information_purpose for scene in plan.scenes)
    assert all("Ken Burns" in scene.visual_intent for scene in plan.scenes)
    with pytest.raises(ValidationError, match="information purpose"):
        StoryboardScene(
            scene_id="bad",
            chapter_id="ch",
            visual_intent="Pretty background",
            information_purpose="decorative",
        )


def test_plan_compiles_to_multimedia_manifest_contract():
    request = MultimediaPlanRequest(
        topic="Boeing 747",
        target_minutes=25,
        route_policy="cheapest",
        selected_arc_ids=("history", "mechanism", "consequences"),
    )
    plan = build_multimedia_plan(request, _evidence())

    manifest = plan.to_manifest(asset_id="mm-747", revision_id="rev-plan")

    assert isinstance(manifest, MultimediaManifest)
    assert manifest.asset_id == "mm-747"
    assert manifest.route_policy == "cheapest"
    assert manifest.segments
    assert manifest.claim_to_chunk
    assert all(row.chunk_ids for row in manifest.claim_to_chunk)
