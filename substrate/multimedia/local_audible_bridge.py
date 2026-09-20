"""Bind verified local span speech to an exact AudibleRun timeline."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal, Protocol, cast

from .audible_run import (
    AudibleRunArtifact,
    RunChapter,
    RunTranscriptSpan,
    compile_audible_run_manifest,
    prepare_audible_run_plan,
)
from .local_audible_tts import (
    PreparedAudibleSpanTTSRequest,
    prepare_local_audible_span_requests,
)
from .local_tts import LocalTTSArtifact
from .planner import CanonicalEvidenceChunk, MultimediaPlan


class LocalAudibleBridgeError(RuntimeError):
    """Local span evidence drifted from its canonical audible plan."""


class LocalAudibleArtifactResolver(Protocol):
    def reopen(self, request: PreparedAudibleSpanTTSRequest) -> LocalTTSArtifact: ...


@dataclass(frozen=True)
class LocalAudibleSpanInput:
    sequence: int
    request_id: str
    paragraph_id: str
    chapter_id: str
    path: str
    sha256: str
    duration_seconds: float


@dataclass(frozen=True)
class LocalAudibleInputs:
    asset_id: str
    revision_id: str
    input_digest: str
    run_plan: MultimediaPlan
    spans: tuple[LocalAudibleSpanInput, ...]
    audible_run: AudibleRunArtifact
    sample_rate_hz: int
    channels: Literal[1, 2]
    cost_usd: float = 0.0


def compile_local_audible_inputs(
    plan: MultimediaPlan,
    requests: tuple[PreparedAudibleSpanTTSRequest, ...],
    *,
    resolver: LocalAudibleArtifactResolver,
    canonical_chunks: Mapping[str, CanonicalEvidenceChunk] | None = None,
) -> LocalAudibleInputs:
    """Re-derive all span calls and compile timing from probed local WAVs."""
    if not requests or len(requests) > 4096 or plan.request.route_policy != "cheapest":
        raise ValueError("local audible inputs require a bounded cheapest span set")
    first = requests[0]
    expected = prepare_local_audible_span_requests(
        plan,
        asset_id=first.asset_id,
        revision_id=first.revision_id,
        voice=first.voice,
        speed=first.speed,
        sample_rate_hz=first.sample_rate_hz,
        channels=first.channels,
        canonical_chunks=canonical_chunks,
    )
    if requests != expected:
        raise LocalAudibleBridgeError("local audible requests drifted from the canonical plan")
    run_plan = prepare_audible_run_plan(plan, canonical_chunks=canonical_chunks)
    lines = {line.line_id: line for line in run_plan.script_lines}
    chapter_rows: list[RunChapter] = []
    transcript_rows: list[RunTranscriptSpan] = []
    input_rows: list[LocalAudibleSpanInput] = []
    request_ids: set[str] = set()
    offset = 0.0
    request_index = 0
    for chapter_sequence, chapter in enumerate(run_plan.chapters):
        chapter_start = round(offset, 3)
        chapter_sources: list[str] = []
        chapter_count = 0
        while request_index < len(requests):
            request = requests[request_index]
            if request.chapter_id != chapter.chapter_id:
                break
            try:
                artifact = resolver.reopen(request)
            except Exception as exc:
                raise LocalAudibleBridgeError("local audible span is unavailable") from exc
            if (
                artifact.request_body_digest != request.body_digest
                or artifact.sample_rate_hz != request.sample_rate_hz
                or artifact.channels != request.channels
                or artifact.duration_seconds <= 0
                or artifact.request_id in request_ids
            ):
                raise LocalAudibleBridgeError("local audible span evidence conflicts")
            line = lines[request.line_id]
            start = round(offset, 3)
            offset += artifact.duration_seconds
            end = round(offset, 3)
            grounding = (
                "sourced"
                if request.source_chunk_ids
                else "unsourced"
                if line.kind == "factual"
                else "not_required"
            )
            transcript_rows.append(
                RunTranscriptSpan(
                    paragraph_id=request.paragraph_id,
                    line_id=request.line_id,
                    chapter_id=request.chapter_id,
                    spoken_text=request.text,
                    line_kind=line.kind,
                    start_offset_seconds=start,
                    end_offset_seconds=end,
                    source_chunk_ids=request.source_chunk_ids,
                    marker_kind=request.marker_kind,
                    grounding_status=cast(
                        Literal["sourced", "unsourced", "not_required"], grounding
                    ),
                )
            )
            input_rows.append(
                LocalAudibleSpanInput(
                    sequence=request.sequence,
                    request_id=artifact.request_id,
                    paragraph_id=request.paragraph_id,
                    chapter_id=request.chapter_id,
                    path=artifact.output_path,
                    sha256=artifact.output_sha256,
                    duration_seconds=round(artifact.duration_seconds, 3),
                )
            )
            request_ids.add(artifact.request_id)
            chapter_sources.extend(request.source_chunk_ids)
            chapter_count += 1
            request_index += 1
        if chapter_count == 0:
            raise LocalAudibleBridgeError("local audible chapter has no measured spans")
        chapter_rows.append(
            RunChapter(
                chapter_id=chapter.chapter_id,
                title=chapter.title,
                sequence=chapter_sequence,
                start_offset_seconds=chapter_start,
                end_offset_seconds=round(offset, 3),
                source_chunk_ids=tuple(
                    dict.fromkeys((*chapter.source_chunk_ids, *chapter_sources))
                ),
            )
        )
    if request_index != len(requests):
        raise LocalAudibleBridgeError("local audible spans escape the chapter order")
    manifest = compile_audible_run_manifest(
        run_plan,
        asset_id=first.asset_id,
        revision_id=first.revision_id,
        transcript_file_id=f"transcript-{first.asset_id}",
        chapters=tuple(chapter_rows),
        transcript_spans=tuple(transcript_rows),
    )
    audible_run = AudibleRunArtifact.seal(manifest)
    authority = {
        "audible_run_sha256": audible_run.manifest_sha256,
        "requests": [json.loads(request.body_json) for request in requests],
        "schema_version": "antiek.local-audible-inputs.v1",
        "spans": [row.__dict__ for row in input_rows],
    }
    digest = hashlib.sha256(
        json.dumps(
            authority,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        ).encode("ascii")
    ).hexdigest()
    return LocalAudibleInputs(
        asset_id=first.asset_id,
        revision_id=first.revision_id,
        input_digest=digest,
        run_plan=run_plan,
        spans=tuple(input_rows),
        audible_run=audible_run,
        sample_rate_hz=first.sample_rate_hz,
        channels=first.channels,
    )


__all__ = [
    "LocalAudibleArtifactResolver",
    "LocalAudibleBridgeError",
    "LocalAudibleInputs",
    "LocalAudibleSpanInput",
    "compile_local_audible_inputs",
]
