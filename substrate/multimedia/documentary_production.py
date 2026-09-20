"""Fail-closed composition boundary for a reviewed Ken Burns documentary."""

from __future__ import annotations

import hashlib
import hmac
import os
import stat
from dataclasses import dataclass
from pathlib import Path

from .ken_burns_renderer import (
    KenBurnsRenderArtifact,
    SceneStillInput,
    render_ken_burns_documentary,
)
from .media_executables import DEFAULT_FFMPEG_PATH, DEFAULT_FFPROBE_PATH
from .video import TimelineEntry
from .visual_selection import (
    EvidenceVerifier,
    ReviewedVisualSelection,
    VisualSelectionPacket,
    compile_visual_selection_packet,
)


class DocumentaryProductionError(RuntimeError):
    """A composed documentary failed an authority or cross-artifact check."""


_MAX_NARRATION_BYTES = 512 * 1024 * 1024


@dataclass(frozen=True)
class DocumentaryProductionArtifact:
    visual_packet: VisualSelectionPacket
    render_artifact: KenBurnsRenderArtifact


def produce_ken_burns_documentary(
    *,
    asset_id: str,
    revision_id: str,
    timeline: tuple[TimelineEntry, ...],
    selections: tuple[ReviewedVisualSelection, ...],
    narration_path: str,
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
) -> DocumentaryProductionArtifact:
    """Verify selections, render them, and bind both sealed artifacts."""
    narration_sha256 = _hash_regular(narration_path)
    packet = compile_visual_selection_packet(
        asset_id=asset_id,
        revision_id=revision_id,
        timeline=timeline,
        selections=selections,
        output_dir=visual_output_dir,
        integrity_key=visual_integrity_key,
        evidence_authority_key=evidence_authority_key,
        verify_evidence=verify_evidence,
    )

    def render(stills: tuple[SceneStillInput, ...]) -> KenBurnsRenderArtifact:
        return render_ken_burns_documentary(
            asset_id=asset_id,
            revision_id=revision_id,
            timeline=timeline,
            stills=stills,
            narration_path=narration_path,
            output_dir=render_output_dir,
            integrity_key=render_integrity_key,
            ffmpeg_path=ffmpeg_path,
            ffprobe_path=ffprobe_path,
            width_px=width_px,
            height_px=height_px,
            fps=fps,
            timeout_seconds=timeout_seconds,
        )

    artifact = packet.consume_renderer_inputs(visual_integrity_key, render)
    verified = KenBurnsRenderArtifact.reopen(artifact.to_json(), render_integrity_key)
    _verify_cross_artifact_binding(
        packet,
        verified,
        timeline=timeline,
        narration_path=narration_path,
        narration_sha256=narration_sha256,
        render_output_dir=render_output_dir,
        width_px=width_px,
        height_px=height_px,
        fps=fps,
    )
    return DocumentaryProductionArtifact(packet, verified)


def reopen_ken_burns_documentary(
    *,
    asset_id: str,
    revision_id: str,
    timeline: tuple[TimelineEntry, ...],
    narration_path: str,
    visual_output_dir: str,
    render_output_dir: str,
    visual_integrity_key: bytes,
    render_integrity_key: bytes,
    width_px: int,
    height_px: int,
    fps: int,
) -> DocumentaryProductionArtifact:
    """Reopen an exact completed documentary after a post-render crash."""
    packet_path = (
        Path(visual_output_dir).resolve()
        / f"{asset_id}-{revision_id}-visuals"
        / "visual-packet.json"
    )
    render_path = (
        Path(render_output_dir).resolve()
        / f"{asset_id}-{revision_id}"
        / "render.json"
    )
    packet = VisualSelectionPacket.reopen(packet_path.read_bytes(), visual_integrity_key)
    artifact = KenBurnsRenderArtifact.reopen(
        render_path.read_bytes(), render_integrity_key
    )
    narration_sha256 = _hash_regular(narration_path)
    _verify_cross_artifact_binding(
        packet,
        artifact,
        timeline=timeline,
        narration_path=narration_path,
        narration_sha256=narration_sha256,
        render_output_dir=render_output_dir,
        width_px=width_px,
        height_px=height_px,
        fps=fps,
    )
    return DocumentaryProductionArtifact(packet, artifact)


def _verify_cross_artifact_binding(
    packet: VisualSelectionPacket,
    artifact: KenBurnsRenderArtifact,
    *,
    timeline: tuple[TimelineEntry, ...],
    narration_path: str,
    narration_sha256: str,
    render_output_dir: str,
    width_px: int,
    height_px: int,
    fps: int,
) -> None:
    manifest = artifact.manifest
    if (
        manifest.asset_id != packet.asset_id
        or manifest.revision_id != packet.revision_id
        or not hmac.compare_digest(manifest.timeline_sha256, packet.timeline_sha256)
    ):
        raise DocumentaryProductionError("render identity is not bound to the visual packet")
    bundle = Path(render_output_dir).resolve() / f"{packet.asset_id}-{packet.revision_id}"
    if (
        manifest.narration_path != str(Path(narration_path).resolve())
        or not hmac.compare_digest(manifest.narration_sha256, narration_sha256)
        or manifest.output_path != str(bundle / "documentary.mp4")
        or manifest.captions_path != str(bundle / "captions.vtt")
        or manifest.width_px != width_px
        or manifest.height_px != height_px
        or manifest.fps != fps
    ):
        raise DocumentaryProductionError("render request is not bound to the production artifact")
    expected_captions = tuple(
        (
            f"cue-{index:04d}",
            row.scene_id,
            row.chapter_id,
            row.start_seconds,
            row.end_seconds,
            row.caption,
            row.source_chunk_ids,
        )
        for index, row in enumerate(timeline)
    )
    rendered_captions = tuple(
        (
            row.cue_id,
            row.scene_id,
            row.chapter_id,
            row.start_seconds,
            row.end_seconds,
            row.text,
            row.source_chunk_ids,
        )
        for row in manifest.captions
    )
    if (
        manifest.scene_ids != tuple(row.scene_id for row in timeline)
        or manifest.chapter_ids != tuple(row.chapter_id for row in timeline)
        or manifest.motions != tuple(row.motion for row in timeline)
        or manifest.visual_labels != tuple(row.visual_label for row in timeline)
        or abs(manifest.duration_seconds - timeline[-1].end_seconds) > 0.001
        or rendered_captions != expected_captions
    ):
        raise DocumentaryProductionError("render timeline content is not bound to the request")
    packet_rows = tuple(
        (row.scene_id, row.path, row.sha256, row.visual_label, row.source_chunk_ids)
        for row in packet.visuals
    )
    render_rows = tuple(
        (row.scene_id, row.path, row.sha256, row.visual_label, row.source_chunk_ids)
        for row in manifest.inputs
    )
    if packet_rows != render_rows:
        raise DocumentaryProductionError("render inputs are not bound to the visual packet")


def _hash_regular(path: str) -> str:
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError:
        raise DocumentaryProductionError("narration input is unavailable") from None
    try:
        info = os.fstat(descriptor)
        if not stat.S_ISREG(info.st_mode) or info.st_size <= 0 or info.st_size > _MAX_NARRATION_BYTES:
            raise DocumentaryProductionError("narration input is not a bounded regular file")
        digest = hashlib.sha256()
        read = 0
        while chunk := os.read(descriptor, 1024 * 1024):
            read += len(chunk)
            if read > _MAX_NARRATION_BYTES:
                raise DocumentaryProductionError("narration input exceeds its byte ceiling")
            digest.update(chunk)
        return digest.hexdigest()
    finally:
        os.close(descriptor)


__all__ = [
    "DocumentaryProductionArtifact",
    "DocumentaryProductionError",
    "produce_ken_burns_documentary",
    "reopen_ken_burns_documentary",
]
