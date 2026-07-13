from __future__ import annotations

from dataclasses import replace

import pytest

from substrate.multimedia.audible_run import compile_audible_run_manifest
from substrate.multimedia.local_audible_bridge import (
    LocalAudibleBridgeError,
    compile_local_audible_inputs,
)
from substrate.multimedia.local_audible_tts import prepare_local_audible_span_requests
from substrate.multimedia.local_tts import LocalTTSArtifact
from substrate.multimedia.planner import EvidenceChunk, MultimediaPlanRequest, build_multimedia_plan


def _plan():
    plan = build_multimedia_plan(
        MultimediaPlanRequest(
            topic="jet engine history", target_minutes=15, route_policy="cheapest"
        ),
        evidence=(
            EvidenceChunk(
                chunk_id="chunk-whittle",
                document_id="doc-engines",
                text="Frank Whittle patented a turbojet design in 1930.",
                title="Early turbojets",
                section_path="history/whittle",
            ),
        ),
    )
    authority = next(line.citations for line in plan.script_lines if line.citations)
    authority_ids = tuple(citation.chunk_id for citation in authority)
    values = plan.model_dump(mode="python")
    lines = []
    for line in plan.script_lines:
        row = line.model_dump(mode="python")
        if line.kind == "factual" and not line.citations:
            row.update(citations=authority, unsourced_reason=None)
        lines.append(type(line).model_validate(row))
    chapters = []
    for chapter in plan.chapters:
        row = chapter.model_dump(mode="python")
        row["source_chunk_ids"] = tuple(
            dict.fromkeys((*chapter.source_chunk_ids, *authority_ids))
        )
        chapters.append(type(chapter).model_validate(row))
    values.update(script_lines=tuple(lines), chapters=tuple(chapters), unsourced_line_ids=())
    return type(plan).model_validate(values)


class _Resolver:
    def __init__(self, requests, *, duration: float = 1.125):  # noqa: ANN001
        self.artifacts = {
            request.paragraph_id: LocalTTSArtifact(
                request_id=f"tts-{request.sequence}",
                request_body_digest=request.body_digest,
                config_digest="a" * 64,
                output_path=f"/private/audio/{request.sequence}.wav",
                output_sha256=f"{request.sequence + 1:064x}",
                duration_seconds=duration,
                sample_rate_hz=request.sample_rate_hz,
                channels=request.channels,
                synthesizer_digest="b" * 64,
                probe_digest="c" * 64,
                created_at="2026-07-13T00:00:00Z",
            )
            for request in requests
        }

    def reopen(self, request):  # noqa: ANN001, ANN201
        return self.artifacts[request.paragraph_id]


def test_measured_spans_compile_complete_audible_timeline() -> None:
    plan = _plan()
    requests = prepare_local_audible_span_requests(
        plan, asset_id="asset-1", revision_id="revision-1"
    )
    inputs = compile_local_audible_inputs(plan, requests, resolver=_Resolver(requests))

    manifest = inputs.audible_run.manifest
    assert len(inputs.spans) == len(requests) == len(manifest.transcript_spans)
    assert manifest.total_duration_seconds == round(len(requests) * 1.125, 3)
    assert manifest.transcript_spans[0].start_offset_seconds == 0
    assert manifest.transcript_spans[-1].end_offset_seconds == manifest.total_duration_seconds
    assert tuple(row.sequence for row in inputs.spans) == tuple(range(len(requests)))
    assert {marker.kind for marker in manifest.retention_markers} == {"remember", "recap"}
    assert manifest.learned_claims
    assert inputs.cost_usd == 0


def test_rederived_request_and_artifact_evidence_fail_closed() -> None:
    plan = _plan()
    requests = prepare_local_audible_span_requests(
        plan, asset_id="asset-1", revision_id="revision-1"
    )
    changed = (replace(requests[0], text=requests[0].text + " drift"), *requests[1:])
    with pytest.raises(LocalAudibleBridgeError, match="drifted"):
        compile_local_audible_inputs(plan, changed, resolver=_Resolver(requests))

    resolver = _Resolver(requests)
    first = requests[0]
    resolver.artifacts[first.paragraph_id] = replace(
        resolver.artifacts[first.paragraph_id], request_body_digest="d" * 64
    )
    with pytest.raises(LocalAudibleBridgeError, match="conflicts"):
        compile_local_audible_inputs(plan, requests, resolver=resolver)


def test_duplicate_local_artifact_identity_is_rejected() -> None:
    plan = _plan()
    requests = prepare_local_audible_span_requests(
        plan, asset_id="asset-1", revision_id="revision-1"
    )
    resolver = _Resolver(requests)
    second = requests[1]
    resolver.artifacts[second.paragraph_id] = replace(
        resolver.artifacts[second.paragraph_id], request_id="tts-0"
    )
    with pytest.raises(LocalAudibleBridgeError, match="conflicts"):
        compile_local_audible_inputs(plan, requests, resolver=resolver)


def test_public_manifest_compiler_refuses_empty_timeline() -> None:
    with pytest.raises(ValueError, match="measured transcript"):
        compile_audible_run_manifest(
            _plan(),
            asset_id="asset-1",
            revision_id="revision-1",
            transcript_file_id="transcript-1",
            chapters=(),
            transcript_spans=(),
        )
