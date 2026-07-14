"""Compose signed narration and reviewed visuals into registered playback."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Literal

from .audio_assembly import AudioExperience, ChapterAudio
from .chapter_tts_production import ChapterTTSSynthesisResult, PreparedChapterTTSRequest
from .documentary_production import reopen_ken_burns_documentary
from .educational_video_production import (
    EducationalVideoProductionArtifact,
    produce_educational_video,
)
from .educational_video_receipt import issue as issue_educational_video_receipt
from .execution_authorization import MultimediaExecutionAuthorizationV2
from .graph_evidence import (
    MultimediaGraphEvidenceUnavailable,
    load_canonical_multimedia_chunks,
)
from .media_executables import DEFAULT_FFMPEG_PATH, DEFAULT_FFPROBE_PATH
from .narration_production import NarrationProductionArtifact
from .narration_run import (
    authorize_narration_run,
    prepare_narration_run,
    produce_narration_run,
)
from .planner import verify_canonical_evidence_bytes
from .production_registration import (
    MultimediaProductionRegistrationRequest,
    register_multimedia_production,
)
from .read_model import MultimediaAssetRecord, MultimediaAssetStore
from .reviewed_visual_registry import (
    ReviewedVisualRegistry,
    ReviewedVisualRegistryError,
    get_reviewed_visuals,
)
from .verified_playback import VerifiedPlaybackError, VerifiedPlaybackRuntime
from .video import VideoScene, build_video_scenes, compile_ken_burns_timeline
from .visual_selection import EvidenceVerifier


class AuthorizedProductionError(RuntimeError):
    """The exact owner-bound documentary command cannot safely continue."""


class AuthorizedProductionUnavailable(AuthorizedProductionError):
    """The owner-scoped asset or required reviewed authority is unavailable."""


@dataclass(frozen=True)
class ChapterNarrationAuthority:
    chapter_id: str
    authorization: MultimediaExecutionAuthorizationV2


@dataclass(frozen=True)
class AuthorizedProductionRequest:
    expected_revision_id: str
    chapter_authorities: tuple[ChapterNarrationAuthority, ...]
    voice: str = "narrator"
    speed: float = 1.0
    sample_rate_hz: int = 24_000
    channels: Literal[1, 2] = 1


@dataclass(frozen=True, repr=False)
class AuthorizedProductionRuntime:
    store: MultimediaAssetStore
    reviewed_visual_registry: ReviewedVisualRegistry
    playback: VerifiedPlaybackRuntime
    signing_key: bytes
    narration_integrity_key: bytes
    visual_integrity_key: bytes
    evidence_authority_key: bytes
    render_integrity_key: bytes
    receipt_key: bytes
    db_path: str
    narration_output_dir: str
    visual_output_dir: str
    render_output_dir: str
    receipt_output_dir: str
    synthesize: Callable[[PreparedChapterTTSRequest], ChapterTTSSynthesisResult]
    verify_evidence: EvidenceVerifier
    clock: Callable[[], datetime]
    ffmpeg_path: str = DEFAULT_FFMPEG_PATH
    ffprobe_path: str = DEFAULT_FFPROBE_PATH
    width_px: int = 1280
    height_px: int = 720
    fps: int = 30
    timeout_seconds: int = 300


def produce_authorized_multimedia(
    asset_id: str,
    request: AuthorizedProductionRequest,
    *,
    owner_id: str,
    runtime: AuthorizedProductionRuntime,
) -> MultimediaAssetRecord:
    record = _current_record(asset_id, request.expected_revision_id, owner_id, runtime.store)
    if str(record.asset.status) != "ready":
        raise AuthorizedProductionError("multimedia production requires a ready asset")
    if record.mode == "audio" or str(record.asset.kind) == "audio_experience":
        raise AuthorizedProductionError("multimedia production requires a video asset")
    if record.asset.route_policy == "cheapest":
        raise AuthorizedProductionError("cheapest route cannot run paid production")

    spoken_chapters = tuple(
        chapter
        for chapter in record.plan.chapters
        if any(
            line.line_id.split("-line-", 1)[0] == chapter.chapter_id
            for line in record.plan.script_lines
        )
    )
    chapter_ids = tuple(chapter.chapter_id for chapter in spoken_chapters)
    if tuple(binding.chapter_id for binding in request.chapter_authorities) != chapter_ids:
        raise AuthorizedProductionError("narration authorization set is incomplete")
    authorizations = {
        binding.chapter_id: binding.authorization
        for binding in request.chapter_authorities
    }
    if len(authorizations) != len(chapter_ids):
        raise AuthorizedProductionError("narration authorization set is invalid")

    try:
        reviewed = get_reviewed_visuals(
            asset_id,
            request.expected_revision_id,
            owner_id=owner_id,
            store=runtime.store,
            registry=runtime.reviewed_visual_registry,
        )
    except ReviewedVisualRegistryError as exc:
        raise AuthorizedProductionUnavailable("reviewed visual set is unavailable") from exc
    if reviewed.receipt.chapter_ids != chapter_ids:
        raise AuthorizedProductionError("reviewed visual set conflicts with spoken chapters")

    prepared = prepare_narration_run(
        record.plan,
        asset_id=asset_id,
        revision_id=request.expected_revision_id,
        routes={
            chapter_id: (
                authorizations[chapter_id].provider,
                authorizations[chapter_id].model,
            )
            for chapter_id in chapter_ids
        },
        voice=request.voice,
        speed=request.speed,
        sample_rate_hz=request.sample_rate_hz,
        channels=request.channels,
    )
    try:
        authorized = authorize_narration_run(prepared, authorizations)
    except ValueError as exc:
        raise AuthorizedProductionError(str(exc)) from exc
    canonical_ids = tuple(
        dict.fromkeys(
            span.chunk_id
            for line in record.plan.script_lines
            if line.evidence_derivation is not None
            for span in line.evidence_derivation.spans
            if span.authority_kind == "canonical_graph"
        )
    )
    try:
        canonical_chunks = (
            load_canonical_multimedia_chunks(
                runtime.db_path, canonical_ids, owner_id=owner_id
            )
            if canonical_ids
            else None
        )
        verify_canonical_evidence_bytes(record.plan, canonical_chunks)
    except (MultimediaGraphEvidenceUnavailable, OSError, RuntimeError, ValueError) as exc:
        raise AuthorizedProductionError("canonical narration evidence is unavailable") from exc
    now = runtime.clock()
    narration = produce_narration_run(
        plan=record.plan,
        prepared=authorized,
        authorizations=authorizations,
        operator_id=owner_id,
        signing_key=runtime.signing_key,
        integrity_key=runtime.narration_integrity_key,
        db_path=runtime.db_path,
        output_dir=runtime.narration_output_dir,
        now=now,
        synthesize=runtime.synthesize,
        ffmpeg_path=runtime.ffmpeg_path,
        ffprobe_path=runtime.ffprobe_path,
        timeout_seconds=runtime.timeout_seconds,
    )
    current = _current_record(
        asset_id, request.expected_revision_id, owner_id, runtime.store
    )
    try:
        runtime.playback.metadata(
            asset_id=asset_id, revision_id=request.expected_revision_id
        )
    except VerifiedPlaybackError:
        pass
    else:
        return register_multimedia_production(
            asset_id,
            MultimediaProductionRegistrationRequest(
                expected_revision_id=request.expected_revision_id
            ),
            owner_id=owner_id,
            store=runtime.store,
            playback=runtime.playback,
        )

    audio = _audio_experience(current, narration)
    base_scenes = build_video_scenes(
        current.plan, audio, canonical_chunks=canonical_chunks
    )
    if tuple(scene.scene_id for scene in base_scenes) != reviewed.receipt.scene_ids:
        raise AuthorizedProductionError("reviewed visual scenes conflict with narration")
    scenes = tuple(
        VideoScene.model_validate(
            {
                **scene.model_dump(mode="python"),
                "visual_label": selection.visual_label,
            }
        )
        for scene, selection in zip(base_scenes, reviewed.selections, strict=True)
    )
    timeline = compile_ken_burns_timeline(scenes)
    render_manifest = (
        Path(runtime.render_output_dir)
        / f"{asset_id}-{request.expected_revision_id}"
        / "render.json"
    )
    if render_manifest.is_file():
        documentary = reopen_ken_burns_documentary(
            asset_id=asset_id,
            revision_id=request.expected_revision_id,
            timeline=timeline,
            narration_path=narration.manifest.output_path,
            visual_output_dir=runtime.visual_output_dir,
            render_output_dir=runtime.render_output_dir,
            visual_integrity_key=runtime.visual_integrity_key,
            render_integrity_key=runtime.render_integrity_key,
            width_px=runtime.width_px,
            height_px=runtime.height_px,
            fps=runtime.fps,
        )
        production = EducationalVideoProductionArtifact(narration, documentary)
    else:
        production = produce_educational_video(
            asset_id=asset_id,
            revision_id=request.expected_revision_id,
            narration=narration,
            narration_integrity_key=runtime.narration_integrity_key,
            timeline=timeline,
            selections=reviewed.selections,
            visual_output_dir=runtime.visual_output_dir,
            render_output_dir=runtime.render_output_dir,
            visual_integrity_key=runtime.visual_integrity_key,
            evidence_authority_key=runtime.evidence_authority_key,
            render_integrity_key=runtime.render_integrity_key,
            verify_evidence=runtime.verify_evidence,
            ffmpeg_path=runtime.ffmpeg_path,
            ffprobe_path=runtime.ffprobe_path,
            width_px=runtime.width_px,
            height_px=runtime.height_px,
            fps=runtime.fps,
            timeout_seconds=runtime.timeout_seconds,
        )
    _current_record(asset_id, request.expected_revision_id, owner_id, runtime.store)
    issue_educational_video_receipt(
        artifact=production,
        receipt_key=runtime.receipt_key,
        narration_key=runtime.narration_integrity_key,
        visual_key=runtime.visual_integrity_key,
        render_key=runtime.render_integrity_key,
        output_dir=runtime.receipt_output_dir,
    )
    _current_record(asset_id, request.expected_revision_id, owner_id, runtime.store)
    return register_multimedia_production(
        asset_id,
        MultimediaProductionRegistrationRequest(
            expected_revision_id=request.expected_revision_id
        ),
        owner_id=owner_id,
        store=runtime.store,
        playback=runtime.playback,
    )


def _audio_experience(
    record: MultimediaAssetRecord, narration: NarrationProductionArtifact
) -> AudioExperience:
    manifest = narration.manifest
    chapter_by_id = {chapter.chapter_id: chapter for chapter in record.plan.chapters}
    binding_by_id = {binding.chapter_id: binding for binding in manifest.chapter_bindings}
    chapters: list[ChapterAudio] = []
    offset = 0.0
    for source in manifest.sources:
        plan_chapter = chapter_by_id.get(source.chapter_id)
        binding = binding_by_id.get(source.chapter_id)
        if plan_chapter is None or binding is None:
            raise AuthorizedProductionError("narration chapter binding is incomplete")
        chapters.append(
            ChapterAudio(
                chapter_id=source.chapter_id,
                title=plan_chapter.title,
                sequence=source.sequence,
                audio_file_id=source.audio_file_id,
                duration_seconds=source.duration_seconds,
                start_offset_seconds=offset,
                script_line_ids=binding.script_line_ids,
                source_chunk_ids=binding.source_chunk_ids,
                paragraph_ids=binding.paragraph_ids,
                recap_prompt="Recall the chapter evidence.",
            )
        )
        offset = round(offset + source.duration_seconds, 3)
    return AudioExperience(
        manifest=record.asset.manifest,
        chapters=tuple(chapters),
        total_duration_seconds=manifest.duration_seconds,
        transcript_file_id="production-transcript",
    )


def _current_record(
    asset_id: str,
    revision_id: str,
    owner_id: str,
    store: MultimediaAssetStore,
) -> MultimediaAssetRecord:
    try:
        record = store.get(asset_id, owner_id=owner_id)
    except (KeyError, ValueError) as exc:
        raise AuthorizedProductionUnavailable("multimedia asset is unavailable") from exc
    if record.asset.revision_id != revision_id:
        raise AuthorizedProductionError("multimedia production revision is not current")
    return record


__all__ = [
    "AuthorizedProductionError",
    "AuthorizedProductionRequest",
    "AuthorizedProductionRuntime",
    "AuthorizedProductionUnavailable",
    "ChapterNarrationAuthority",
    "produce_authorized_multimedia",
]
