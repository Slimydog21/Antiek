"""Ken Burns style video documentary assembly.

SPR-05 builds a deterministic manifest path for educational video: scene rows,
visual generation prompts, motion presets, captions, timeline entries, and a
fake render manifest with hashes. It consumes the SPR-04 audio asset as timing
truth and does not call Krea or a local video renderer.
"""

from __future__ import annotations

import hashlib
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from substrate.contracts.multimedia import (
    GeneratedFile,
    MediaSegment,
    MultimediaManifest,
    RoutePolicy,
)
from substrate.multimedia.audio import AudioExperienceAsset
from substrate.multimedia.planner import MultimediaPlan
from substrate.multimedia.provider_router import (
    MediaGenerationRequest,
    ProviderRoute,
    route_media_request,
)

VisualLabel = Literal["generated", "sourced", "archival", "diagram", "omitted"]
MotionPreset = Literal[
    "pan_left",
    "pan_right",
    "slow_zoom_in",
    "slow_zoom_out",
    "hold",
    "map_callout",
]

_MOTIONS: tuple[MotionPreset, ...] = (
    "slow_zoom_in",
    "pan_left",
    "slow_zoom_out",
    "pan_right",
    "hold",
    "map_callout",
)


class _VideoBase(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class VideoScene(_VideoBase):
    scene_id: str
    chapter_id: str
    script_line_ids: tuple[str, ...] = Field(default_factory=tuple)
    visual_intent: str = Field(min_length=1)
    asset_prompt: str = Field(min_length=1)
    motion: MotionPreset
    caption: str = Field(min_length=1)
    duration_seconds: float = Field(ge=0)
    visual_label: VisualLabel
    source_purpose: str = Field(min_length=1)
    source_chunk_ids: tuple[str, ...] = Field(default_factory=tuple)
    gap_reason: str | None = None

    @model_validator(mode="after")
    def scene_is_honest_and_purposeful(self) -> VideoScene:
        if self.source_purpose.strip().lower() in {"decorative", "filler", "atmosphere"}:
            raise ValueError("video scenes require an information purpose")
        prompt = self.asset_prompt.lower()
        claims_archival = "archival" in prompt and "not archival" not in prompt
        if self.visual_label == "generated" and claims_archival:
            raise ValueError("generated visual prompts must not claim archival truth")
        if self.duration_seconds == 0 and not self.gap_reason:
            raise ValueError("zero-duration scenes require gap_reason")
        return self


class VisualGenerationPlan(_VideoBase):
    scene_id: str
    request: MediaGenerationRequest
    route: ProviderRoute
    disclosure_label: VisualLabel


class TimelineEntry(_VideoBase):
    scene_id: str
    chapter_id: str
    start_seconds: float
    end_seconds: float
    motion: MotionPreset
    visual_label: VisualLabel
    caption: str
    source_chunk_ids: tuple[str, ...] = Field(default_factory=tuple)


class CaptionCue(_VideoBase):
    cue_id: str
    scene_id: str
    chapter_id: str
    start_seconds: float
    end_seconds: float
    text: str
    source_chunk_ids: tuple[str, ...] = Field(default_factory=tuple)


class VideoRenderManifest(_VideoBase):
    output_uri: str
    sha256: str = Field(pattern="^[0-9a-f]{64}$")
    width_px: int = Field(ge=1)
    height_px: int = Field(ge=1)
    duration_seconds: float = Field(ge=0)
    scene_ids: tuple[str, ...]
    visual_labels: tuple[VisualLabel, ...]
    captions: tuple[CaptionCue, ...]
    chapter_ids: tuple[str, ...]


class VideoDocumentaryAsset(_VideoBase):
    asset_id: str
    revision_id: str
    scenes: tuple[VideoScene, ...]
    visual_plan: tuple[VisualGenerationPlan, ...]
    timeline: tuple[TimelineEntry, ...]
    render_manifest: VideoRenderManifest
    manifest: MultimediaManifest


def build_video_scenes(
    plan: MultimediaPlan,
    audio: AudioExperienceAsset,
) -> tuple[VideoScene, ...]:
    """Create one scene per audio chapter, using audio duration as truth."""

    line_ids_by_chapter = _script_lines_by_chapter(plan)
    scenes: list[VideoScene] = []
    for index, chapter in enumerate(audio.chapters):
        motion = _MOTIONS[index % len(_MOTIONS)]
        source_chunks = chapter.source_chunk_ids
        prompt = (
            f"Generated educational visual for '{chapter.title}'. "
            "Clearly not archival footage or a historical photograph. "
            "Use diagrammatic/source-card composition when facts are specific."
        )
        scenes.append(
            VideoScene(
                scene_id=f"scene-{chapter.chapter_id}",
                chapter_id=chapter.chapter_id,
                script_line_ids=tuple(line_ids_by_chapter.get(chapter.chapter_id, ())),
                visual_intent=f"Teach: {chapter.recap_prompt}",
                asset_prompt=prompt,
                motion=motion,
                caption=_caption_from_transcript(chapter.transcript),
                duration_seconds=chapter.duration_seconds,
                visual_label="generated",
                source_purpose="explain the chapter's learning objective with labeled generated imagery",
                source_chunk_ids=source_chunks,
            )
        )
    return tuple(scenes)


def plan_visual_generation(
    scenes: tuple[VideoScene, ...],
    *,
    route_policy: RoutePolicy,
) -> tuple[VisualGenerationPlan, ...]:
    plans: list[VisualGenerationPlan] = []
    for scene in scenes:
        req = MediaGenerationRequest(
            kind="image",
            prompt=scene.asset_prompt,
            route_policy=route_policy,
            dry_run=True,
        )
        plans.append(
            VisualGenerationPlan(
                scene_id=scene.scene_id,
                request=req,
                route=route_media_request(req),
                disclosure_label=scene.visual_label,
            )
        )
    return tuple(plans)


def compile_ken_burns_timeline(scenes: tuple[VideoScene, ...]) -> tuple[TimelineEntry, ...]:
    cursor = 0.0
    entries: list[TimelineEntry] = []
    for scene in scenes:
        end = round(cursor + scene.duration_seconds, 2)
        entries.append(
            TimelineEntry(
                scene_id=scene.scene_id,
                chapter_id=scene.chapter_id,
                start_seconds=cursor,
                end_seconds=end,
                motion=scene.motion,
                visual_label=scene.visual_label,
                caption=scene.caption,
                source_chunk_ids=scene.source_chunk_ids,
            )
        )
        cursor = end
    return tuple(entries)


def captions_from_timeline(timeline: tuple[TimelineEntry, ...]) -> tuple[CaptionCue, ...]:
    return tuple(
        CaptionCue(
            cue_id=f"cap-{index:03d}",
            scene_id=entry.scene_id,
            chapter_id=entry.chapter_id,
            start_seconds=entry.start_seconds,
            end_seconds=entry.end_seconds,
            text=entry.caption,
            source_chunk_ids=entry.source_chunk_ids,
        )
        for index, entry in enumerate(timeline)
    )


def simulate_documentary_render(
    *,
    asset_id: str,
    revision_id: str,
    timeline: tuple[TimelineEntry, ...],
    width_px: int = 1280,
    height_px: int = 720,
) -> VideoRenderManifest:
    captions = captions_from_timeline(timeline)
    duration = timeline[-1].end_seconds if timeline else 0.0
    payload = "|".join(
        f"{entry.scene_id}:{entry.start_seconds}:{entry.end_seconds}:{entry.motion}:{entry.visual_label}"
        for entry in timeline
    )
    sha = hashlib.sha256(payload.encode()).hexdigest()
    return VideoRenderManifest(
        output_uri=f"memory://multimedia/{asset_id}/{revision_id}/documentary.mp4",
        sha256=sha,
        width_px=width_px,
        height_px=height_px,
        duration_seconds=duration,
        scene_ids=tuple(entry.scene_id for entry in timeline),
        visual_labels=tuple(entry.visual_label for entry in timeline),
        captions=captions,
        chapter_ids=tuple(dict.fromkeys(entry.chapter_id for entry in timeline)),
    )


def assemble_video_documentary(
    plan: MultimediaPlan,
    audio: AudioExperienceAsset,
    *,
    asset_id: str,
    revision_id: str,
) -> VideoDocumentaryAsset:
    scenes = build_video_scenes(plan, audio)
    visual_plan = plan_visual_generation(scenes, route_policy=plan.request.route_policy)
    timeline = compile_ken_burns_timeline(scenes)
    render = simulate_documentary_render(
        asset_id=asset_id,
        revision_id=revision_id,
        timeline=timeline,
    )
    caption_text = "\n".join(
        f"{cue.start_seconds:.2f} --> {cue.end_seconds:.2f} {cue.text}"
        for cue in render.captions
    )
    video_file = GeneratedFile(
        file_id="video-documentary",
        kind="video",
        storage_uri=render.output_uri,
        sha256=render.sha256,
        mime="video/mp4",
        provider="local_ken_burns_simulator",
        duration_seconds=render.duration_seconds,
        width_px=render.width_px,
        height_px=render.height_px,
    )
    caption_file = GeneratedFile(
        file_id="video-captions",
        kind="caption",
        storage_uri=f"memory://multimedia/{asset_id}/{revision_id}/captions.vtt",
        sha256=hashlib.sha256(caption_text.encode()).hexdigest(),
        mime="text/vtt",
        provider="local_ken_burns_simulator",
        duration_seconds=render.duration_seconds,
    )
    segments = tuple(
        MediaSegment(
            segment_id=f"video-seg-{scene.scene_id}",
            sequence=index,
            title=scene.visual_intent,
            media_kind="motion",
            script_line_ids=scene.script_line_ids,
            file_ids=(video_file.file_id, caption_file.file_id),
            source_chunk_ids=scene.source_chunk_ids,
            duration_seconds=scene.duration_seconds,
        )
        for index, scene in enumerate(scenes)
    )
    manifest = plan.to_manifest(asset_id=asset_id, revision_id=revision_id).model_copy(
        update={
            "files": (video_file, caption_file),
            "segments": segments,
            "captions_file_id": caption_file.file_id,
        }
    )
    return VideoDocumentaryAsset(
        asset_id=asset_id,
        revision_id=revision_id,
        scenes=scenes,
        visual_plan=visual_plan,
        timeline=timeline,
        render_manifest=render,
        manifest=manifest,
    )


def _script_lines_by_chapter(plan: MultimediaPlan) -> dict[str, list[str]]:
    result: dict[str, list[str]] = {}
    chapter_ids = {chapter.chapter_id for chapter in plan.chapters}
    for line in plan.script_lines:
        chapter_id = line.line_id.split("-line-", 1)[0]
        if chapter_id not in chapter_ids:
            chapter_id = "intro"
        result.setdefault(chapter_id, []).append(line.line_id)
    return result


def _caption_from_transcript(transcript: str) -> str:
    words = transcript.split()
    return " ".join(words[:24]) if words else "Chapter narration."


__all__ = [
    "CaptionCue",
    "MotionPreset",
    "TimelineEntry",
    "VideoDocumentaryAsset",
    "VideoRenderManifest",
    "VideoScene",
    "VisualGenerationPlan",
    "VisualLabel",
    "assemble_video_documentary",
    "build_video_scenes",
    "captions_from_timeline",
    "compile_ken_burns_timeline",
    "plan_visual_generation",
    "simulate_documentary_render",
]
