"""End-to-end local production of one evidence-backed educational video."""

from __future__ import annotations

import hmac
from dataclasses import dataclass

from .documentary_production import (
    DocumentaryProductionArtifact,
    produce_ken_burns_documentary,
)
from .media_executables import DEFAULT_FFMPEG_PATH, DEFAULT_FFPROBE_PATH
from .narration_production import NarrationProductionArtifact
from .video import TimelineEntry
from .visual_selection import EvidenceVerifier, ReviewedVisualSelection


class EducationalVideoProductionError(RuntimeError):
    """The narration and documentary authorities could not be composed."""


@dataclass(frozen=True)
class EducationalVideoProductionArtifact:
    narration: NarrationProductionArtifact
    documentary: DocumentaryProductionArtifact


def produce_educational_video(
    *,
    asset_id: str,
    revision_id: str,
    narration: NarrationProductionArtifact,
    narration_integrity_key: bytes,
    timeline: tuple[TimelineEntry, ...],
    selections: tuple[ReviewedVisualSelection, ...],
    visual_output_dir: str,
    render_output_dir: str,
    visual_integrity_key: bytes,
    evidence_authority_key: bytes,
    render_integrity_key: bytes,
    verify_evidence: EvidenceVerifier,
    ffmpeg_path: str = DEFAULT_FFMPEG_PATH,
    ffprobe_path: str = DEFAULT_FFPROBE_PATH,
    width_px: int = 1280,
    height_px: int = 720,
    fps: int = 30,
    timeout_seconds: int = 300,
) -> EducationalVideoProductionArtifact:
    verified_narration = NarrationProductionArtifact.reopen(
        narration.to_json(), narration_integrity_key
    )
    manifest = verified_narration.manifest
    if manifest.asset_id != asset_id or manifest.revision_id != revision_id:
        raise EducationalVideoProductionError(
            "narration identity is not bound to the documentary request"
        )
    if not timeline or timeline[-1].end_seconds != manifest.duration_seconds:
        raise EducationalVideoProductionError(
            "narration duration is not bound to the documentary timeline"
        )
    expected_boundaries: list[tuple[str, float]] = []
    chapter_end = 0.0
    for source in manifest.sources:
        chapter_end = round(chapter_end + source.duration_seconds, 3)
        expected_boundaries.append((source.chapter_id, chapter_end))
    timeline_boundaries = tuple((row.chapter_id, row.end_seconds) for row in timeline)
    if timeline_boundaries != tuple(expected_boundaries):
        raise EducationalVideoProductionError(
            "narration chapter boundaries are not bound to the documentary timeline"
        )
    documentary = produce_ken_burns_documentary(
        asset_id=asset_id,
        revision_id=revision_id,
        timeline=timeline,
        selections=selections,
        narration_path=manifest.output_path,
        visual_output_dir=visual_output_dir,
        render_output_dir=render_output_dir,
        visual_integrity_key=visual_integrity_key,
        evidence_authority_key=evidence_authority_key,
        render_integrity_key=render_integrity_key,
        verify_evidence=verify_evidence,
        ffmpeg_path=ffmpeg_path,
        ffprobe_path=ffprobe_path,
        width_px=width_px,
        height_px=height_px,
        fps=fps,
        timeout_seconds=timeout_seconds,
    )
    rendered = documentary.render_artifact.manifest
    if (
        rendered.narration_path != manifest.output_path
        or not hmac.compare_digest(rendered.narration_sha256, manifest.output_sha256)
    ):
        raise EducationalVideoProductionError(
            "rendered narration is not bound to narration production authority"
        )
    return EducationalVideoProductionArtifact(verified_narration, documentary)


__all__ = [
    "EducationalVideoProductionArtifact",
    "EducationalVideoProductionError",
    "produce_educational_video",
]
