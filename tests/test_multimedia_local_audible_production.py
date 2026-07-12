from __future__ import annotations

import hashlib
import os
import subprocess
import wave
from pathlib import Path

import pytest

from substrate.multimedia.local_audible_bridge import compile_local_audible_inputs
from substrate.multimedia.local_audible_production import (
    LocalAudibleProductionArtifact,
    LocalAudibleProductionError,
    produce_local_audible_track,
)
from substrate.multimedia.local_audible_tts import prepare_local_audible_span_requests
from substrate.multimedia.local_tts import LocalTTSArtifact
from substrate.multimedia.planner import EvidenceChunk, MultimediaPlanRequest, build_multimedia_plan

KEY = b"local-audible-production-test-integrity-key"


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
    source_ids = tuple(citation.chunk_id for citation in authority)
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
            dict.fromkeys((*chapter.source_chunk_ids, *source_ids))
        )
        chapters.append(type(chapter).model_validate(row))
    values.update(script_lines=tuple(lines), chapters=tuple(chapters), unsourced_line_ids=())
    return type(plan).model_validate(values)


class _Resolver:
    def __init__(self, artifacts):  # noqa: ANN001
        self.artifacts = artifacts

    def reopen(self, request):  # noqa: ANN001, ANN201
        return self.artifacts[request.paragraph_id]


def _inputs(tmp_path: Path):
    plan = _plan()
    requests = prepare_local_audible_span_requests(
        plan, asset_id="asset-1", revision_id="revision-1"
    )
    source_root = tmp_path / "sources"
    source_root.mkdir(mode=0o700)
    artifacts = {}
    for request in requests:
        path = source_root / f"{request.sequence}.wav"
        with wave.open(str(path), "wb") as output:
            output.setnchannels(1)
            output.setsampwidth(2)
            output.setframerate(24_000)
            output.writeframes(b"\0\0" * 2_400)
        os.chmod(path, 0o600)
        artifacts[request.paragraph_id] = LocalTTSArtifact(
            request_id=f"tts-{request.sequence}",
            request_body_digest=request.body_digest,
            config_digest="a" * 64,
            output_path=str(path),
            output_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
            duration_seconds=0.1,
            sample_rate_hz=24_000,
            channels=1,
            synthesizer_digest="b" * 64,
            probe_digest="c" * 64,
            created_at="2026-07-13T00:00:00Z",
        )
    return compile_local_audible_inputs(plan, requests, resolver=_Resolver(artifacts))


def test_real_pcm_spans_publish_and_reopen_without_second_media_call(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    inputs = _inputs(tmp_path)
    output = tmp_path / "published"
    output.mkdir(mode=0o700)
    artifact = produce_local_audible_track(
        inputs, output_dir=str(output), integrity_key=KEY
    )
    assert artifact.manifest.duration_seconds == round(len(inputs.spans) * 0.1, 3)
    assert artifact.manifest.cost_usd == 0
    assert Path(artifact.manifest.output_path).read_bytes()[:4] == b"RIFF"
    assert Path(artifact.manifest.output_path).stat().st_mode & 0o777 == 0o600

    def no_media(*args, **kwargs):  # noqa: ANN002, ANN003, ANN202
        raise AssertionError("artifact reopen must not invoke a media process")

    monkeypatch.setattr(subprocess, "run", no_media)
    payload = Path(artifact.manifest.output_path).with_name("audible.json").read_bytes()
    assert LocalAudibleProductionArtifact.reopen(payload, KEY) == artifact


def test_output_and_manifest_tamper_fail_reopen(tmp_path: Path) -> None:
    inputs = _inputs(tmp_path)
    output = tmp_path / "published"
    output.mkdir(mode=0o700)
    artifact = produce_local_audible_track(
        inputs, output_dir=str(output), integrity_key=KEY
    )
    manifest_path = Path(artifact.manifest.output_path).with_name("audible.json")
    with pytest.raises(LocalAudibleProductionError, match="MAC"):
        LocalAudibleProductionArtifact.reopen(
            artifact.model_copy(update={"manifest_mac": "0" * 64}).to_json(), KEY
        )
    Path(artifact.manifest.output_path).write_bytes(b"RIFF" + b"tampered" * 8)
    with pytest.raises(LocalAudibleProductionError, match="evidence"):
        LocalAudibleProductionArtifact.reopen(manifest_path.read_bytes(), KEY)
