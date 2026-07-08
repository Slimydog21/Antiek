"""SPR-07 multimedia steering and revision tests."""

from __future__ import annotations

import pytest

from substrate.contracts.multimedia import MultimediaAssetContract
from substrate.multimedia.audio_assembly import assemble_audio_experience
from substrate.multimedia.planner import EvidenceChunk, MultimediaPlanRequest, build_multimedia_plan
from substrate.multimedia.provider_router import BudgetExceeded
from substrate.multimedia.steering import (
    SteeringTranscript,
    build_revision_asset,
    parse_steering_prompt,
    plan_revision,
)
from substrate.multimedia.tts import FakeTTSProvider
from substrate.multimedia.video import assemble_video_documentary


def _parent_asset() -> MultimediaAssetContract:
    evidence = (
        EvidenceChunk(
            chunk_id="chunk-history",
            document_id="doc-widebody",
            text="Widebody history changed long-haul airline capacity and economics.",
        ),
        EvidenceChunk(
            chunk_id="chunk-engine",
            document_id="doc-engine",
            text="High-bypass engines made long-haul widebody flights more viable.",
        ),
    )
    plan = build_multimedia_plan(
        MultimediaPlanRequest(
            topic="widebody aircraft",
            target_minutes=20,
            mode="video",
            route_policy="balanced",
            selected_arc_ids=("history", "mechanism"),
        ),
        evidence,
    )
    audio = assemble_audio_experience(plan, FakeTTSProvider(), asset_id="mm-steer", revision_id="rev-audio")
    video = assemble_video_documentary(plan, audio, asset_id="mm-steer", revision_id="rev-1")
    return MultimediaAssetContract(
        asset_id="mm-steer",
        kind="documentary_video",
        title="Widebody aircraft documentary",
        user_prompt="Make a grounded documentary about widebody aircraft.",
        status="ready",
        route_policy="balanced",
        requested_duration_minutes=20,
        revision_id="rev-1",
        manifest=video.manifest,
    )


def test_ambiguous_steering_prompt_requests_clarification_not_operations():
    parent = _parent_asset()

    intent = parse_steering_prompt("make this better", parent.manifest)

    assert intent.status == "needs_clarification"
    assert not intent.operations
    assert any("shorten" in message for message in intent.clarifications)


def test_corrected_voice_transcript_is_the_text_that_gets_parsed():
    parent = _parent_asset()
    transcript = SteeringTranscript(
        transcript_id="voice-1",
        raw_text="go deeper on cabins",
        corrected_text="go deeper on engines in chapter 2",
        confidence=0.72,
    )

    intent = parse_steering_prompt("ignored when transcript is supplied", parent.manifest, transcript=transcript)

    assert intent.status == "ready"
    assert intent.prompt == "go deeper on engines in chapter 2"
    assert intent.transcript == transcript
    assert {operation.kind for operation in intent.operations} == {"deepen"}
    assert all(operation.target_id == parent.manifest.segments[1].segment_id for operation in intent.operations)


def test_prompt_with_duration_and_topic_targets_global_and_local_operations():
    parent = _parent_asset()

    intent = parse_steering_prompt(
        "make it 20 minutes, go deeper on engines in chapter 2, and use cheapest",
        parent.manifest,
    )

    assert intent.status == "ready"
    by_kind = {operation.kind: operation for operation in intent.operations}
    assert by_kind["shorten"].target_id == parent.asset_id
    assert by_kind["shorten"].value == "20 minutes"
    assert by_kind["deepen"].target_id == parent.manifest.segments[1].segment_id
    assert by_kind["change_tier"].value == "cheapest"

    revision = plan_revision(parent, intent, revision_id="rev-cheap")
    assert revision.route_policy == "cheapest"
    assert revision.estimated_cost_delta_usd == 0


def test_revision_plan_preserves_original_and_reuses_unchanged_segment_hashes():
    parent = _parent_asset()
    target = parent.manifest.segments[1]
    intent = parse_steering_prompt("go deeper on engines in chapter 2", parent.manifest)

    revision = plan_revision(parent, intent, revision_id="rev-2")

    assert parent.revision_id == "rev-1"
    assert revision.revision_id == "rev-2"
    assert revision.parent_revision_id == "rev-1"
    assert revision.affected_segment_ids == (target.segment_id,)
    assert revision.estimated_cost_delta_usd > 0
    assert revision.manifest.revision_id == "rev-2"
    assert revision.manifest.prompts[-1].purpose == "revision"
    assert revision.manifest.provider_calls[-1].status == "planned"
    assert revision.manifest.cost_rows[-1].cost_usd == revision.estimated_cost_delta_usd

    reused = {row.segment_id: row for row in revision.segment_reuse}
    assert reused[target.segment_id].reused is False
    unchanged = [row for row in reused.values() if row.segment_id != target.segment_id]
    assert unchanged
    assert all(row.reused for row in unchanged)
    assert all(row.file_sha256s for row in unchanged)


def test_revision_asset_carries_parent_revision_and_steering_event():
    parent = _parent_asset()
    intent = parse_steering_prompt("regenerate chapter 1 with more concrete visuals", parent.manifest)
    revision = plan_revision(parent, intent, revision_id="rev-regen")

    child = build_revision_asset(parent, revision)

    assert child.asset_id == parent.asset_id
    assert child.revision_id == "rev-regen"
    assert child.parent_revision_id == "rev-1"
    assert child.steering_event_id == intent.steering_event_id
    assert child.status == "planned"
    assert child.manifest.revision_id == "rev-regen"


def test_clarification_intent_cannot_be_planned():
    parent = _parent_asset()
    intent = parse_steering_prompt("maybe adjust something", parent.manifest)

    with pytest.raises(ValueError, match="clarification intent"):
        plan_revision(parent, intent)


def test_incidental_positional_words_do_not_manufacture_reorder():
    parent = _parent_asset()
    intent = parse_steering_prompt("go deeper on engines before chapter 1", parent.manifest)
    kinds = {operation.kind for operation in intent.operations}
    assert "reorder" not in kinds
    assert "deepen" in kinds


def test_remove_does_not_also_trigger_reorder():
    parent = _parent_asset()
    intent = parse_steering_prompt("remove chapter 1", parent.manifest)
    assert {operation.kind for operation in intent.operations} == {"skip"}


def test_aggregate_over_budget_revision_raises_budget_exceeded():
    parent = _parent_asset()
    one = parse_steering_prompt("regenerate chapter 1", parent.manifest)
    single = plan_revision(parent, one, revision_id="probe").estimated_cost_delta_usd
    both = parse_steering_prompt("regenerate chapter 1 and chapter 2", parent.manifest)
    with pytest.raises(BudgetExceeded):
        plan_revision(parent, both, revision_id="rev-over", budget_usd=single + 0.01)
