"""Ken Burns style video documentary assembly (multimedia SPR-05).

Build a deterministic manifest path for educational video: scene rows, visual
generation prompts, motion presets, captions, timeline entries, and a fake
render manifest with content hashes. The video consumes the SPR-04 audio asset
as timing truth (one scene per chapter, chapter duration = scene duration) and
does NOT call Krea or a local video renderer — it is the plan-before-render
layer, credential-free, so CI can assert determinism without paid media.

Craftsmanship invariants this module guarantees:

* AUDIO IS TIMING TRUTH. Every scene's ``duration_seconds`` comes from the
  audio chapter, never invented. The timeline's final offset equals the audio's
  total duration, so the video cannot drift from the narration.
* SCENES ARE HONEST AND PURPOSEFUL. A ``VideoScene`` validator rejects
  decorative/filler/atmosphere purposes (a scene must carry an information
  purpose) and rejects a generated visual whose prompt claims archival truth
  (generated imagery must disclose that it is generated, not pass as
  historical record).
* CAPTIONS ARE GROUNDED. A scene caption is derived from the chapter's CITED
  script-line texts (the planner's grounded lines), not an opaque transcript
  blob — so a viewer can trace a caption back to the source behind it.
* THE RENDER IS DETERMINISTIC. ``simulate_documentary_render`` hashes the
  timeline content, so the same plan + audio yields a byte-stable sha256 that
  CI can assert without a real encoder.
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from substrate.contracts.multimedia import (
    GeneratedFile,
    MediaSegment,
    MultimediaManifest,
    RoutePolicy,
)
from substrate.multimedia.audio_assembly import AudioExperience, ChapterAudio
from substrate.multimedia.planner import (
    CanonicalEvidenceChunk,
    MultimediaPlan,
    verify_canonical_evidence_bytes,
)
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
    audio: AudioExperience,
    *,
    canonical_chunks: Mapping[str, CanonicalEvidenceChunk] | None = None,
) -> tuple[VideoScene, ...]:
    """Create one scene per audio chapter, using audio duration as truth.

    The caption for each scene is derived from the chapter's CITED script-line
    texts (looked up from the planner's grounded ``script_lines``), so a viewer
    can trace a caption back to the evidence behind it — not an opaque
    transcript blob.
    """
    if plan.grounding_contract != "exact_extract_v2":
        raise ValueError("video production requires exact_extract_v2 grounding")
    if plan.unsourced_line_ids:
        raise ValueError("video production refuses unsourced factual narration")
    verify_canonical_evidence_bytes(plan, canonical_chunks)
    line_text_by_id = {line.line_id: line.text for line in plan.script_lines}
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
                script_line_ids=chapter.script_line_ids,
                visual_intent=f"Teach: {chapter.recap_prompt}",
                asset_prompt=prompt,
                motion=motion,
                caption=_caption_for_chapter(chapter, line_text_by_id),
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
        end = round(cursor + scene.duration_seconds, 3)
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
        f"{entry.scene_id}:{entry.start_seconds}:{entry.end_seconds}:{entry.motion}:"
        f"{entry.visual_label}:{entry.caption}:{','.join(entry.source_chunk_ids)}"
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
    audio: AudioExperience,
    *,
    asset_id: str,
    revision_id: str,
    canonical_chunks: Mapping[str, CanonicalEvidenceChunk] | None = None,
) -> VideoDocumentaryAsset:
    scenes = build_video_scenes(plan, audio, canonical_chunks=canonical_chunks)
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
    manifest = audio.manifest.model_copy(
        update={
            "asset_id": asset_id,
            "revision_id": revision_id,
            "files": (video_file, caption_file),
            "segments": segments,
            "captions_file_id": caption_file.file_id,
            "transcript_file_id": None,
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


def _caption_for_chapter(chapter: ChapterAudio, line_text_by_id: dict[str, str]) -> str:
    """Derive a caption from the chapter's CITED script-line texts.

    The chapter carries ``script_line_ids`` (the planner's grounded lines). Join
    their texts and truncate to a caption-length window. When no cited lines
    exist the chapter title stands in — never an invented claim.
    """
    words: list[str] = []
    for lid in chapter.script_line_ids:
        text = line_text_by_id.get(lid)
        if text:
            words.extend(text.split())
    return " ".join(words[:24]) if words else f"{chapter.title}."


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
