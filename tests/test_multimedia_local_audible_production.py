from __future__ import annotations

import hashlib
import os
import subprocess
import wave
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from substrate.multimedia.audible_experience_receipt import (
    AudibleExperienceReceipt,
    AudibleExperienceReceiptError,
    issue_audible_experience_receipt,
)
from substrate.multimedia.local_audible_bridge import compile_local_audible_inputs
from substrate.multimedia.local_audible_production import (
    LocalAudibleProductionArtifact,
    LocalAudibleProductionError,
    produce_local_audible_track,
)
from substrate.multimedia.local_audible_tts import prepare_local_audible_span_requests
from substrate.multimedia.local_tts import LocalTTSArtifact
from substrate.multimedia.planner import EvidenceChunk, MultimediaPlanRequest, build_multimedia_plan
from substrate.multimedia.verified_audio_playback import VerifiedAudioPlaybackRuntime
from substrate.multimedia.verified_playback import UnsatisfiableMediaRange, VerifiedPlaybackError

KEY = b"local-audible-production-test-integrity-key"
RECEIPT_KEY = b"local-audible-receipt-test-signing-key"
NOW = datetime(2026, 7, 13, tzinfo=UTC)


def _plan():
    plan = build_multimedia_plan(
        MultimediaPlanRequest(
            topic="jet engine history",
            target_minutes=15,
            route_policy="cheapest",
            selected_arc_ids=("history",),
        ),
        evidence=(
            EvidenceChunk(
                chunk_id="chunk-whittle",
                document_id="doc-engines",
                text="Early jet engine history began with Frank Whittle's turbojet patent in 1930.",
                title="Early turbojets",
                section_path="history/whittle",
            ),
        ),
    )
    assert not plan.unsourced_line_ids
    return plan


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


def test_audio_only_receipt_cross_binds_and_issues_idempotently(tmp_path: Path) -> None:
    inputs = _inputs(tmp_path)
    output = tmp_path / "published"
    output.mkdir(mode=0o700)
    production = produce_local_audible_track(
        inputs, output_dir=str(output), integrity_key=KEY
    )
    owner_digest = hashlib.sha256(b"owner-1").hexdigest()
    first = issue_audible_experience_receipt(
        owner_digest=owner_digest,
        production=production,
        audible_run=inputs.audible_run,
        signing_key=RECEIPT_KEY,
        production_integrity_key=KEY,
        now=NOW,
    )
    replay = issue_audible_experience_receipt(
        owner_digest=owner_digest,
        production=production,
        audible_run=inputs.audible_run,
        signing_key=RECEIPT_KEY,
        production_integrity_key=KEY,
        now=NOW + timedelta(hours=1),
    )
    assert replay == first and first.cost_usd == 0
    assert "visual" not in first.to_json() and "video" not in first.to_json()
    receipt_path = Path(production.manifest.output_path).with_name("receipt.json")
    assert receipt_path.stat().st_mode & 0o777 == 0o600
    assert (
        AudibleExperienceReceipt.reopen_from_file(
            receipt_path,
            signing_key=RECEIPT_KEY,
            production_integrity_key=KEY,
        )
        == first
    )


def test_receipt_issuance_recovers_partial_and_post_link_pending_files(
    tmp_path: Path,
) -> None:
    inputs = _inputs(tmp_path)
    output = tmp_path / "published"
    output.mkdir(mode=0o700)
    production = produce_local_audible_track(
        inputs, output_dir=str(output), integrity_key=KEY
    )
    owner_digest = hashlib.sha256(b"owner-1").hexdigest()
    receipt_path = Path(production.manifest.output_path).with_name("receipt.json")
    pending = receipt_path.with_name(".receipt.pending.json")
    pending.write_bytes(b'{"partial":')
    os.chmod(pending, 0o600)
    receipt = issue_audible_experience_receipt(
        owner_digest=owner_digest,
        production=production,
        audible_run=inputs.audible_run,
        signing_key=RECEIPT_KEY,
        production_integrity_key=KEY,
        now=NOW,
    )
    assert receipt_path.exists() and not pending.exists()

    os.link(receipt_path, pending)
    assert receipt_path.stat().st_nlink == 2
    replay = issue_audible_experience_receipt(
        owner_digest=owner_digest,
        production=production,
        audible_run=inputs.audible_run,
        signing_key=RECEIPT_KEY,
        production_integrity_key=KEY,
        now=NOW + timedelta(hours=1),
    )
    assert replay == receipt and receipt_path.stat().st_nlink == 1
    assert not pending.exists()


def test_receipt_rejects_wrong_owner_authority_and_keys(tmp_path: Path) -> None:
    inputs = _inputs(tmp_path)
    output = tmp_path / "published"
    output.mkdir(mode=0o700)
    production = produce_local_audible_track(
        inputs, output_dir=str(output), integrity_key=KEY
    )
    owner_digest = hashlib.sha256(b"owner-1").hexdigest()
    receipt = issue_audible_experience_receipt(
        owner_digest=owner_digest,
        production=production,
        audible_run=inputs.audible_run,
        signing_key=RECEIPT_KEY,
        production_integrity_key=KEY,
        now=NOW,
    )
    with pytest.raises(AudibleExperienceReceiptError, match="MAC"):
        AudibleExperienceReceipt.reopen(
            receipt.to_json(),
            signing_key=b"wrong-receipt-signing-key-material-123",
            production_integrity_key=KEY,
        )
    with pytest.raises(LocalAudibleProductionError, match="MAC"):
        AudibleExperienceReceipt.reopen(
            receipt.to_json(),
            signing_key=RECEIPT_KEY,
            production_integrity_key=b"wrong-production-key-material-12345",
        )
    with pytest.raises(AudibleExperienceReceiptError, match="conflicts"):
        issue_audible_experience_receipt(
            owner_digest=hashlib.sha256(b"owner-2").hexdigest(),
            production=production,
            audible_run=inputs.audible_run,
            signing_key=RECEIPT_KEY,
            production_integrity_key=KEY,
            now=NOW,
        )


def test_verified_audio_metadata_and_ranges_are_owner_bound(tmp_path: Path) -> None:
    inputs = _inputs(tmp_path)
    output = tmp_path / "published"
    output.mkdir(mode=0o700)
    production = produce_local_audible_track(
        inputs, output_dir=str(output), integrity_key=KEY
    )
    owner_digest = hashlib.sha256(b"owner-1").hexdigest()
    issue_audible_experience_receipt(
        owner_digest=owner_digest,
        production=production,
        audible_run=inputs.audible_run,
        signing_key=RECEIPT_KEY,
        production_integrity_key=KEY,
        now=NOW,
    )
    receipt_path = Path(production.manifest.output_path).with_name("receipt.json")
    runtime = VerifiedAudioPlaybackRuntime(
        receipt_path_resolver=lambda _asset, _revision: receipt_path,
        receipt_key=RECEIPT_KEY,
        production_integrity_key=KEY,
    )
    metadata = runtime.metadata(
        asset_id="asset-1", revision_id="revision-1", owner_digest=owner_digest
    )
    assert metadata.audio_sha256 == production.manifest.output_sha256
    assert metadata.chapter_ids == tuple(
        row.chapter_id for row in inputs.audible_run.manifest.chapters
    )
    assert metadata.retention_marker_count and metadata.learned_claim_count
    result = runtime.read(
        asset_id="asset-1",
        revision_id="revision-1",
        owner_digest=owner_digest,
        range_header="bytes=0-11",
    )
    assert result.payload is not None and result.payload[:4] == b"RIFF"
    assert result.start == 0 and result.end == 11 and result.media_type == "audio/wav"
    with pytest.raises(UnsatisfiableMediaRange):
        runtime.read(
            asset_id="asset-1",
            revision_id="revision-1",
            owner_digest=owner_digest,
            range_header=f"bytes={metadata.audio_size_bytes}-",
        )
    with pytest.raises(VerifiedPlaybackError, match="identity"):
        runtime.metadata(
            asset_id="asset-1",
            revision_id="revision-1",
            owner_digest="0" * 64,
        )
