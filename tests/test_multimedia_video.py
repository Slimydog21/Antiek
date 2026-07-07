"""SPR-05 multimedia video documentary pipeline tests."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from substrate.multimedia.audio import assemble_audio_experience
from substrate.multimedia.planner import EvidenceChunk, MultimediaPlanRequest, build_multimedia_plan
from substrate.multimedia.video import (
    VideoScene,
    assemble_video_documentary,
    build_video_scenes,
    captions_from_timeline,
    compile_ken_burns_timeline,
    plan_visual_generation,
    simulate_documentary_render,
)


def _plan_and_audio():
    evidence = (
        EvidenceChunk(
            chunk_id="chunk-history",
            document_id="doc-widebody",
            text="Early widebody history changed the airline market and passenger capacity.",
        ),
        EvidenceChunk(
            chunk_id="chunk-engine",
            document_id="doc-engine",
            text="High-bypass engine design made long-haul flight economics more viable.",
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
    audio = assemble_audio_experience(plan, asset_id="mm-video", revision_id="rev-audio")
    return plan, audio


def test_scene_manifest_has_learning_intent_labels_and_source_span():
    plan, audio = _plan_and_audio()

    scenes = build_video_scenes(plan, audio)

    assert len(scenes) == len(audio.chapters)
    assert all(scene.duration_seconds > 0 for scene in scenes)
    assert all(scene.visual_label == "generated" for scene in scenes)
    assert all("not archival" in scene.asset_prompt.lower() for scene in scenes)
    assert all(scene.source_purpose for scene in scenes)


def test_generated_scene_prompt_cannot_claim_archival_truth():
    with pytest.raises(ValidationError, match="archival truth"):
        VideoScene(
            scene_id="bad",
            chapter_id="intro",
            visual_intent="show a thing",
            asset_prompt="Generate archival photograph of the event",
            motion="hold",
            caption="bad",
            duration_seconds=1,
            visual_label="generated",
            source_purpose="explain source",
        )


def test_timeline_duration_matches_audio_duration_and_motion_preserves_duration():
    plan, audio = _plan_and_audio()
    scenes = build_video_scenes(plan, audio)

    timeline = compile_ken_burns_timeline(scenes)

    assert timeline[0].start_seconds == 0
    assert timeline[-1].end_seconds == audio.playback.total_duration_seconds
    for scene, entry in zip(scenes, timeline, strict=True):
        assert round(entry.end_seconds - entry.start_seconds, 2) == scene.duration_seconds
        assert entry.motion == scene.motion


def test_visual_generation_plan_uses_router_and_disclosure_labels():
    plan, audio = _plan_and_audio()
    scenes = build_video_scenes(plan, audio)

    visual_plan = plan_visual_generation(scenes, route_policy=plan.request.route_policy)

    assert len(visual_plan) == len(scenes)
    assert all(row.route.provider == "krea" for row in visual_plan)
    assert all(row.disclosure_label == "generated" for row in visual_plan)
    assert all(row.request.dry_run is True for row in visual_plan)


def test_captions_and_render_manifest_are_deterministic():
    plan, audio = _plan_and_audio()
    timeline = compile_ken_burns_timeline(build_video_scenes(plan, audio))

    captions = captions_from_timeline(timeline)
    first = simulate_documentary_render(asset_id="mm-video", revision_id="rev-video", timeline=timeline)
    second = simulate_documentary_render(asset_id="mm-video", revision_id="rev-video", timeline=timeline)

    assert captions
    assert all(cue.source_chunk_ids is not None for cue in captions)
    assert first == second
    assert first.sha256
    assert first.scene_ids == tuple(entry.scene_id for entry in timeline)


def test_video_documentary_manifest_has_video_captions_and_segments():
    plan, audio = _plan_and_audio()

    doc = assemble_video_documentary(plan, audio, asset_id="mm-video", revision_id="rev-video")

    file_kinds = {file.kind for file in doc.manifest.files}
    assert {"video", "caption"} <= file_kinds
    assert doc.manifest.captions_file_id == "video-captions"
    assert doc.manifest.segments
    assert all(segment.duration_seconds for segment in doc.manifest.segments)
    assert doc.render_manifest.duration_seconds == audio.playback.total_duration_seconds
