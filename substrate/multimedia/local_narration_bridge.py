"""Bind verified local chapter speech to canonical narration-production inputs."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Protocol

from ..contracts.multimedia import GeneratedFile
from .audio_assembly import ChapterAudio
from .chapter_tts_production import (
    PreparedChapterTTSRequest,
    prepare_chapter_tts_request,
)
from .local_tts import LocalTTSArtifact
from .planner import MultimediaPlan


class LocalNarrationBridgeError(RuntimeError):
    """Verified local speech did not match the canonical cheapest plan."""


class LocalTTSArtifactResolver(Protocol):
    """Read-only local speech authority used by the coordinator."""

    def reopen(self, request: PreparedChapterTTSRequest) -> LocalTTSArtifact: ...


@dataclass(frozen=True)
class LocalNarrationInputs:
    asset_id: str
    revision_id: str
    input_digest: str
    chapters: tuple[ChapterAudio, ...]
    generated_files: tuple[GeneratedFile, ...]
    chapter_paths: dict[str, str]
    request_ids: tuple[str, ...]
    chapter_texts: tuple[str, ...]
    cost_usd: float = 0.0


def compile_local_narration_inputs(
    plan: MultimediaPlan,
    requests: tuple[PreparedChapterTTSRequest, ...],
    *,
    resolver: LocalTTSArtifactResolver,
) -> LocalNarrationInputs:
    """Re-derive and verify all local chapters before canonical concatenation."""
    if not requests or len(requests) > 64 or plan.request.route_policy != "cheapest":
        raise ValueError("local narration requires a bounded cheapest chapter set")
    asset_id = requests[0].asset_id
    revision_id = requests[0].revision_id
    if any(
        request.sample_rate_hz != requests[0].sample_rate_hz
        or request.channels != requests[0].channels
        for request in requests
    ):
        raise LocalNarrationBridgeError("local narration chapters require one audio shape")
    spoken_chapters = tuple(
        chapter
        for chapter in plan.chapters
        if any(
            line.line_id.split("-line-", 1)[0] == chapter.chapter_id
            for line in plan.script_lines
        )
    )
    if len(requests) != len(spoken_chapters):
        raise LocalNarrationBridgeError("local narration requests do not exactly cover chapters")

    artifacts: list[LocalTTSArtifact] = []
    chapter_rows: list[ChapterAudio] = []
    files: list[GeneratedFile] = []
    paths: dict[str, str] = {}
    offset = 0.0
    for sequence, (chapter, request) in enumerate(zip(spoken_chapters, requests, strict=True)):
        if request.asset_id != asset_id or request.revision_id != revision_id:
            raise LocalNarrationBridgeError("local narration identity conflicts across chapters")
        expected = prepare_chapter_tts_request(
            plan,
            asset_id=asset_id,
            revision_id=revision_id,
            provider="local_executable_tts",
            model="macos-say-v1",
            voice=request.voice,
            speed=request.speed,
            sample_rate_hz=request.sample_rate_hz,
            channels=request.channels,
            chapter_id=chapter.chapter_id,
        )
        if request != expected:
            raise LocalNarrationBridgeError("local narration request drifted from canonical plan")
        try:
            artifact = resolver.reopen(expected)
        except Exception as exc:
            raise LocalNarrationBridgeError("local narration artifact is unavailable") from exc
        if (
            artifact.request_body_digest != expected.body_digest
            or artifact.sample_rate_hz != expected.sample_rate_hz
            or artifact.channels != expected.channels
            or artifact.duration_seconds <= 0
        ):
            raise LocalNarrationBridgeError("local narration artifact conflicts with request")
        audio_file_id = artifact.request_id
        if audio_file_id in paths:
            raise LocalNarrationBridgeError("local narration artifact IDs must be unique")
        duration = round(artifact.duration_seconds, 3)
        chapter_rows.append(
            ChapterAudio(
                chapter_id=chapter.chapter_id,
                title=chapter.title,
                sequence=sequence,
                audio_file_id=audio_file_id,
                duration_seconds=duration,
                start_offset_seconds=round(offset, 3),
                script_line_ids=expected.script_line_ids,
                source_chunk_ids=expected.source_chunk_ids,
                paragraph_ids=expected.paragraph_ids,
                recap_prompt=f"Recall the evidence for {chapter.title}.",
                assembled_end_offset_seconds=round(offset + duration, 3),
            )
        )
        files.append(
            GeneratedFile(
                file_id=audio_file_id,
                kind="audio",
                storage_uri=f"antiek-mm://{asset_id}/{revision_id}/{audio_file_id}.wav",
                sha256=artifact.output_sha256,
                mime="audio/wav",
                provider="local_executable_tts",
                duration_seconds=duration,
            )
        )
        paths[audio_file_id] = artifact.output_path
        artifacts.append(artifact)
        offset += duration

    authority = {
        "artifacts": [artifact.__dict__ for artifact in artifacts],
        "asset_id": asset_id,
        "cost_usd": 0.0,
        "plan": plan.model_dump(mode="json"),
        "requests": [json.loads(request.body_json) for request in requests],
        "revision_id": revision_id,
        "schema_version": "antiek.local-narration-inputs.v1",
    }
    input_digest = hashlib.sha256(
        json.dumps(
            authority,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        ).encode("ascii")
    ).hexdigest()
    return LocalNarrationInputs(
        asset_id=asset_id,
        revision_id=revision_id,
        input_digest=input_digest,
        chapters=tuple(chapter_rows),
        generated_files=tuple(files),
        chapter_paths=paths,
        request_ids=tuple(artifact.request_id for artifact in artifacts),
        chapter_texts=tuple(request.text for request in requests),
    )


__all__ = [
    "LocalNarrationBridgeError",
    "LocalNarrationInputs",
    "LocalTTSArtifactResolver",
    "compile_local_narration_inputs",
]
