from __future__ import annotations

import hashlib
import os
import wave
from datetime import UTC, datetime
from pathlib import Path

import pytest

from substrate.multimedia.local_audible_coordinator import (
    LocalAudibleCoordinator,
    LocalAudibleOutcomeUnknown,
    LocalAudibleRunRequest,
)
from substrate.multimedia.local_audible_tts import prepare_local_audible_span_requests
from substrate.multimedia.local_tts import LocalTTSArtifact
from substrate.multimedia.read_model import CreateMultimediaDraftRequest, MultimediaAssetStore

NOW = datetime(2026, 7, 13, tzinfo=UTC)
SIGNING_KEY = b"local-audible-coordinator-signing-key"
PRODUCTION_KEY = b"local-audible-coordinator-production-key"
RECEIPT_KEY = b"local-audible-coordinator-receipt-key"


def _ground(plan):  # noqa: ANN001, ANN202
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
    def __init__(self, artifacts):  # noqa: ANN001
        self.artifacts = artifacts

    def reopen(self, request):  # noqa: ANN001, ANN201
        return self.artifacts[request.paragraph_id]


def _fixture(tmp_path: Path):  # noqa: ANN202
    store = MultimediaAssetStore(str(tmp_path / "assets"))
    draft = store.create_draft(
        CreateMultimediaDraftRequest(
            topic="jet engine history",
            target_minutes=15,
            mode="audio",
            route_policy="cheapest",
            sources=("Frank Whittle patented a turbojet design in 1930.",),
        ),
        owner_id="owner-1",
    )
    plan = _ground(draft.plan)
    store.save(draft.model_copy(update={"plan": plan}), owner_id="owner-1")
    ready = store.approve_dry_run(draft.asset.asset_id, owner_id="owner-1")
    requests = prepare_local_audible_span_requests(
        plan, asset_id=ready.asset.asset_id, revision_id=ready.asset.revision_id
    )
    source_root = tmp_path / "speech"
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
    root = tmp_path / "published"
    root.mkdir(mode=0o700)
    coordinator = LocalAudibleCoordinator(
        db_path=str(tmp_path / "audible.duckdb"),
        signing_key=SIGNING_KEY,
        production_integrity_key=PRODUCTION_KEY,
        receipt_key=RECEIPT_KEY,
        output_dir=str(root),
        store=store,
        tts_resolver=_Resolver(artifacts),
    )
    request = LocalAudibleRunRequest(
        owner_id="owner-1",
        asset_id=ready.asset.asset_id,
        expected_revision_id=ready.asset.revision_id,
        span_requests=requests,
    )
    return coordinator, store, request


def test_full_local_audible_run_registers_and_exactly_replays(tmp_path: Path) -> None:
    coordinator, store, request = _fixture(tmp_path)
    first = coordinator.produce(request, now=NOW)
    assert first.cost_usd == 0 and first.registered
    record = store.get(request.asset_id, owner_id="owner-1")
    assert record.audio_production_link is not None
    assert record.audio_production_link.receipt_sha256 == hashlib.sha256(
        first.receipt.to_json().encode("ascii")
    ).hexdigest()
    assert coordinator.receipt_path(
        request.asset_id, request.expected_revision_id
    ).name == "receipt.json"
    assert coordinator.produce(request, now=NOW) == first


def test_crash_after_track_publication_requires_recovery_without_duplicate_ffmpeg(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    coordinator, store, request = _fixture(tmp_path)
    from substrate.multimedia import local_audible_coordinator as module

    real_produce = module.produce_local_audible_track

    def publish_then_crash(*args, **kwargs):  # noqa: ANN002, ANN003, ANN202
        real_produce(*args, **kwargs)
        raise RuntimeError("injected post-publication crash")

    monkeypatch.setattr(module, "produce_local_audible_track", publish_then_crash)
    with pytest.raises(LocalAudibleOutcomeUnknown, match="explicit recovery"):
        coordinator.produce(request, now=NOW)
    with pytest.raises(LocalAudibleOutcomeUnknown, match="explicit recovery"):
        coordinator.produce(request, now=NOW)

    def no_second_production(*args, **kwargs):  # noqa: ANN002, ANN003, ANN202
        raise AssertionError("recovery must adopt the published artifact")

    monkeypatch.setattr(module, "produce_local_audible_track", no_second_production)
    recovered = coordinator.recover(request, now=NOW)
    assert recovered.registered
    assert store.get(request.asset_id, owner_id="owner-1").audio_production_link is not None


def test_crash_after_receipt_publication_recovers_without_duplicate_issuance(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    coordinator, store, request = _fixture(tmp_path)
    from substrate.multimedia import local_audible_coordinator as module

    real_issue = module.issue_audible_experience_receipt

    def issue_then_crash(*args, **kwargs):  # noqa: ANN002, ANN003, ANN202
        real_issue(*args, **kwargs)
        raise RuntimeError("injected post-receipt crash")

    monkeypatch.setattr(module, "issue_audible_experience_receipt", issue_then_crash)
    with pytest.raises(LocalAudibleOutcomeUnknown, match="receipt outcome"):
        coordinator.produce(request, now=NOW)

    calls = 0

    def exact_reopen(*args, **kwargs):  # noqa: ANN002, ANN003, ANN202
        nonlocal calls
        calls += 1
        return real_issue(*args, **kwargs)

    monkeypatch.setattr(module, "issue_audible_experience_receipt", exact_reopen)
    recovered = coordinator.recover(request, now=NOW)
    assert recovered.registered and calls == 1
    assert store.get(request.asset_id, owner_id="owner-1").audio_production_link is not None


def test_crash_after_registration_recovers_idempotently(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    coordinator, store, request = _fixture(tmp_path)
    from substrate.multimedia import local_audible_coordinator as module

    real_register = module.register_multimedia_audio_production

    def register_then_crash(*args, **kwargs):  # noqa: ANN002, ANN003, ANN202
        real_register(*args, **kwargs)
        raise RuntimeError("injected post-registration crash")

    monkeypatch.setattr(module, "register_multimedia_audio_production", register_then_crash)
    with pytest.raises(LocalAudibleOutcomeUnknown, match="registration outcome"):
        coordinator.produce(request, now=NOW)
    assert store.get(request.asset_id, owner_id="owner-1").audio_production_link is not None

    calls = 0

    def idempotent_register(*args, **kwargs):  # noqa: ANN002, ANN003, ANN202
        nonlocal calls
        calls += 1
        return real_register(*args, **kwargs)

    monkeypatch.setattr(module, "register_multimedia_audio_production", idempotent_register)
    recovered = coordinator.recover(request, now=NOW)
    assert recovered.registered and calls == 1
