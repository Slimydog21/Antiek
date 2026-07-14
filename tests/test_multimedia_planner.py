"""SPR-02 multimedia curriculum/storyboard planner tests."""

from __future__ import annotations

import hashlib

import pytest
from pydantic import ValidationError

from substrate.contracts.multimedia import MultimediaManifest
from substrate.multimedia.planner import (
    EvidenceChunk,
    MultimediaPlanRequest,
    StoryboardScene,
    build_multimedia_plan,
    verify_canonical_evidence_bytes,
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


def test_new_plans_use_exact_bounded_evidence_extracts_for_factual_narration():
    evidence = _evidence()
    by_chunk = {chunk.chunk_id: chunk for chunk in evidence}

    plan = build_multimedia_plan(
        MultimediaPlanRequest(topic="Boeing 747", target_minutes=20), evidence
    )

    assert plan.grounding_contract == "exact_extract_v2"
    sourced = [line for line in plan.script_lines if line.kind == "factual" and line.citations]
    assert sourced
    for line in sourced:
        assert len(line.citations) == 1
        citation = line.citations[0]
        assert line.text in by_chunk[citation.chunk_id].text
        assert len(line.text) <= 700
        assert line.evidence_derivation is not None
        span = line.evidence_derivation.spans[0]
        assert span.chunk_id == citation.chunk_id
        assert span.exact_text == line.text
        assert span.span_sha256 == hashlib.sha256(line.text.encode("utf-8")).hexdigest()


def test_exact_extract_plan_rejects_unbound_or_multi_source_factual_lines():
    plan = build_multimedia_plan(
        MultimediaPlanRequest(topic="Boeing 747", target_minutes=20), _evidence()
    )
    values = plan.model_dump(mode="python")
    lines = list(values["script_lines"])
    sourced_index = next(index for index, line in enumerate(lines) if line["citations"])
    forged = dict(lines[sourced_index])
    forged["evidence_derivation"] = None
    lines[sourced_index] = forged
    values["script_lines"] = tuple(lines)

    with pytest.raises(ValidationError, match="exact_extract_v2"):
        type(plan).model_validate(values)


def test_verbatim_derivation_uses_canonical_utf8_byte_offsets():
    text = "  مقدمة ✈️ with a combining e\u0301. " + "x" * 900
    chunk = EvidenceChunk(chunk_id="unicode", document_id="doc", text=text)

    plan = build_multimedia_plan(
        MultimediaPlanRequest(
            topic="Unicode aviation",
            target_minutes=15,
            selected_arc_ids=("history",),
        ),
        (chunk,),
    )

    line = next(row for row in plan.script_lines if row.citations)
    assert line.evidence_derivation is not None
    span = line.evidence_derivation.spans[0]
    canonical = text.encode("utf-8")
    assert canonical[span.start_utf8_byte : span.end_utf8_byte].decode("utf-8") == line.text


def test_canonical_derivation_must_reopen_exact_graph_bytes_before_production():
    source = "Early aviation history began with controlled glider experiments."
    plan = build_multimedia_plan(
        MultimediaPlanRequest(
            topic="aviation", target_minutes=15, selected_arc_ids=("history",)
        ),
        (
            EvidenceChunk(
                chunk_id="canonical-history",
                document_id="doc",
                text=source,
                authority_kind="canonical_graph",
            ),
        ),
    )

    with pytest.raises(ValueError, match="canonical graph bytes"):
        verify_canonical_evidence_bytes(plan, None)
    verify_canonical_evidence_bytes(plan, {"canonical-history": ("doc", source)})
    with pytest.raises(ValueError, match="digest drifted"):
        verify_canonical_evidence_bytes(
            plan, {"canonical-history": ("doc", source + " drift")}
        )
    with pytest.raises(ValueError, match="document identity drifted"):
        verify_canonical_evidence_bytes(
            plan, {"canonical-history": ("different-doc", source)}
        )


def test_operator_excerpt_derivation_is_explicitly_not_graph_authority():
    plan = build_multimedia_plan(
        MultimediaPlanRequest(
            topic="aviation", target_minutes=15, selected_arc_ids=("history",)
        ),
        (
            EvidenceChunk(
                chunk_id="operator-history",
                document_id="operator",
                text="Early aviation history began with controlled glider experiments.",
            ),
        ),
    )

    spans = [
        span
        for line in plan.script_lines
        if line.evidence_derivation is not None
        for span in line.evidence_derivation.spans
    ]
    assert spans and {span.authority_kind for span in spans} == {"operator_excerpt"}
    verify_canonical_evidence_bytes(plan, None)


def test_planner_metadata_cannot_launder_itself_into_sourced_factual_text():
    fabricated = "The aircraft reached Mach 99 in 1901."
    evidence = (
        EvidenceChunk(
            chunk_id="history",
            document_id="doc",
            text="Early aviation history began with controlled glider experiments.",
        ),
    )
    plan = build_multimedia_plan(
        MultimediaPlanRequest(
            topic=fabricated,
            target_minutes=15,
            must_cover=(fabricated,),
            selected_arc_ids=("history",),
        ),
        evidence,
    )

    assert all(
        fabricated not in line.text
        for line in plan.script_lines
        if line.kind == "factual" and line.citations
    )


def test_exact_extract_plan_rejects_broadened_chapter_and_scene_authority():
    plan = build_multimedia_plan(
        MultimediaPlanRequest(topic="Boeing 747", target_minutes=20), _evidence()
    )
    values = plan.model_dump(mode="python")
    chapter = dict(values["chapters"][0])
    chapter["source_chunk_ids"] = (*chapter["source_chunk_ids"], "unused-chunk")
    values["chapters"] = (chapter, *values["chapters"][1:])

    with pytest.raises(ValidationError, match="chapter source authority"):
        type(plan).model_validate(values)


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
