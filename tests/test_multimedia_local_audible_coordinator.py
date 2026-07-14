from __future__ import annotations

import hashlib
import os
import wave
from datetime import UTC, datetime
from pathlib import Path

import pytest

from substrate.multimedia.local_audible_coordinator import (
    LocalAudibleCoordinator,
    LocalAudibleCoordinatorError,
    LocalAudibleOutcomeUnknown,
    LocalAudibleRunRequest,
)
from substrate.multimedia.local_audible_tts import prepare_local_audible_span_requests
from substrate.multimedia.local_tts import LocalTTSArtifact
from substrate.multimedia.local_zero_cost_evidence import (
    LocalZeroEvidenceUnavailable,
    build_local_audio_zero_cost_evidence,
    verify_local_zero_cost_evidence,
)
from substrate.multimedia.read_model import CreateMultimediaDraftRequest, MultimediaAssetStore

NOW = datetime(2026, 7, 13, tzinfo=UTC)
SIGNING_KEY = b"local-audible-coordinator-signing-key"
PRODUCTION_KEY = b"local-audible-coordinator-production-key"
RECEIPT_KEY = b"local-audible-coordinator-receipt-key"


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
            sources=(
                "Early jet engine history began with Frank Whittle's turbojet patent in 1930.",
            ),
            selected_arc_ids=("history",),
        ),
        owner_id="owner-1",
    )
    ready = store.approve_dry_run(draft.asset.asset_id, owner_id="owner-1")
    plan = ready.plan
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


def test_registered_audible_authority_reopens_full_chain(tmp_path: Path) -> None:
    coordinator, store, request = _fixture(tmp_path)
    first = coordinator.produce(request, now=NOW)
    authority = coordinator.registered_audible_authority(
        "owner-1", request.asset_id, request.expected_revision_id
    )
    assert authority.receipt == first.receipt
    assert authority.run_id == first.run_id
    assert authority.asset_id == request.asset_id
    assert authority.revision_id == request.expected_revision_id
    record = store.get(request.asset_id, owner_id="owner-1")
    assert authority.audio_production_link == record.audio_production_link


def test_registered_audible_authority_link_fields_match_receipt(tmp_path: Path) -> None:
    coordinator, store, request = _fixture(tmp_path)
    coordinator.produce(request, now=NOW)
    authority = coordinator.registered_audible_authority(
        "owner-1", request.asset_id, request.expected_revision_id
    )
    production = authority.receipt.production.manifest
    run = authority.receipt.audible_run.manifest
    link = authority.audio_production_link
    assert link.receipt_sha256 == hashlib.sha256(
        authority.receipt.to_json().encode("ascii")
    ).hexdigest()
    assert link.audio_sha256 == production.output_sha256
    assert link.duration_seconds == production.duration_seconds
    assert link.chapter_ids == tuple(ch.chapter_id for ch in run.chapters)
    assert link.retention_marker_count == len(run.retention_markers)
    assert link.learned_claim_count == len(run.learned_claims)


def test_missing_table_does_not_create_database_for_audible_authority(tmp_path: Path) -> None:
    coordinator, _store, request = _fixture(tmp_path)
    coordinator.produce(request, now=NOW)
    import duckdb

    with duckdb.connect(str(tmp_path / "audible.duckdb")) as conn:
        conn.execute("DROP TABLE IF EXISTS multimedia_local_audible_runs")
    # Clean up write.lock left by produce()
    for lock in tmp_path.glob("*.write.lock"):
        lock.unlink()
    with pytest.raises(LocalAudibleCoordinatorError, match="table is missing"):
        coordinator.registered_audible_authority(
            "owner-1", request.asset_id, request.expected_revision_id
        )
    assert not any(
        tmp_path.glob("*.write.lock")
    ), "authority must not leave a write lock"


def test_duplicate_registered_audible_row_fails_closed(tmp_path: Path) -> None:
    coordinator, _store, request = _fixture(tmp_path)
    coordinator.produce(request, now=NOW)
    import duckdb

    with duckdb.connect(str(tmp_path / "audible.duckdb")) as conn:
        row = conn.execute(
            "SELECT * FROM multimedia_local_audible_runs LIMIT 1"
        ).fetchone()
        dup = list(row)
        dup[0] = "duplicate-run-id"
        conn.execute(
            "INSERT INTO multimedia_local_audible_runs VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            dup,
        )
    with pytest.raises(LocalAudibleCoordinatorError, match="multiple"):
        coordinator.registered_audible_authority(
            "owner-1", request.asset_id, request.expected_revision_id
        )


def test_in_flight_audible_state_fails_authority(tmp_path: Path) -> None:
    coordinator, _store, request = _fixture(tmp_path)
    coordinator.produce(request, now=NOW)
    import duckdb

    with duckdb.connect(str(tmp_path / "audible.duckdb")) as conn:
        conn.execute("UPDATE multimedia_local_audible_runs SET status='producing'")
    with pytest.raises(
        LocalAudibleCoordinatorError,
        match="(registered row is missing|evidence_unavailable)",
    ):
        coordinator.registered_audible_authority(
            "owner-1", request.asset_id, request.expected_revision_id
        )


def test_wrong_owner_fails_audible_authority(tmp_path: Path) -> None:
    coordinator, _store, request = _fixture(tmp_path)
    coordinator.produce(request, now=NOW)
    # Store only has a record for owner-1, so owner-2 is unknown.
    with pytest.raises(LocalAudibleCoordinatorError):
        coordinator.registered_audible_authority(
            "owner-2", request.asset_id, request.expected_revision_id
        )


def test_bad_audible_mac_fails_authority(tmp_path: Path) -> None:
    coordinator, _store, request = _fixture(tmp_path)
    coordinator.produce(request, now=NOW)
    import duckdb

    with duckdb.connect(str(tmp_path / "audible.duckdb")) as conn:
        conn.execute(
            "UPDATE multimedia_local_audible_runs SET row_mac=?", ["0" * 64]
        )
    with pytest.raises(LocalAudibleCoordinatorError, match="integrity"):
        coordinator.registered_audible_authority(
            "owner-1", request.asset_id, request.expected_revision_id
        )


def test_tampered_production_fails_audible_authority(tmp_path: Path) -> None:
    coordinator, _store, request = _fixture(tmp_path)
    coordinator.produce(request, now=NOW)
    import duckdb

    with duckdb.connect(str(tmp_path / "audible.duckdb"), read_only=True) as connection:
        production_path = Path(connection.execute(
            "SELECT production_path FROM multimedia_local_audible_runs"
        ).fetchone()[0])
    production_path.write_bytes(b"tampered")
    production_path.chmod(0o600)
    with pytest.raises(RuntimeError):
        coordinator.registered_audible_authority(
            "owner-1", request.asset_id, request.expected_revision_id
        )


def test_tampered_receipt_fails_audible_authority(tmp_path: Path) -> None:
    coordinator, _store, request = _fixture(tmp_path)
    first = coordinator.produce(request, now=NOW)
    receipt_path = Path(first.receipt.production.manifest.output_path).parent / "receipt.json"
    receipt_path.write_text("tampered")
    receipt_path.chmod(0o600)
    with pytest.raises(RuntimeError):
        coordinator.registered_audible_authority(
            "owner-1", request.asset_id, request.expected_revision_id
        )


def test_audible_audio_tamper_fails_authority(tmp_path: Path) -> None:
    coordinator, _store, request = _fixture(tmp_path)
    first = coordinator.produce(request, now=NOW)
    audio_path = Path(first.receipt.production.manifest.output_path)
    audio_path.write_bytes(b"tampered")
    audio_path.chmod(0o600)
    with pytest.raises(RuntimeError, match="private"):
        coordinator.registered_audible_authority(
            "owner-1", request.asset_id, request.expected_revision_id
        )


def test_changed_executable_fails_audible_authority(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    coordinator, _store, request = _fixture(tmp_path)
    coordinator.produce(request, now=NOW)
    from substrate.multimedia import local_audible_coordinator as module

    monkeypatch.setattr(module, "_hash_file", lambda _path, _maximum: "0" * 64)
    with pytest.raises(LocalAudibleCoordinatorError, match="executable"):
        coordinator.registered_audible_authority(
            "owner-1", request.asset_id, request.expected_revision_id
        )


def test_audible_link_drift_fails_authority(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    coordinator, store, request = _fixture(tmp_path)
    coordinator.produce(request, now=NOW)
    authority = coordinator.registered_audible_authority(
        "owner-1", request.asset_id, request.expected_revision_id
    )
    link = authority.audio_production_link
    from substrate.multimedia.read_model import MultimediaAudioProductionLink

    drifted = MultimediaAudioProductionLink(
        owner_identity_digest=link.owner_identity_digest,
        asset_id=link.asset_id,
        revision_id=link.revision_id,
        receipt_sha256="0" * 64,
        audio_sha256=link.audio_sha256,
        duration_seconds=link.duration_seconds,
        chapter_ids=link.chapter_ids,
        retention_marker_count=link.retention_marker_count,
        learned_claim_count=link.learned_claim_count,
    )
    real_get = store.get

    def drifted_get(asset_id, *, owner_id):  # noqa: ANN001, ANN201
        record = real_get(asset_id, owner_id=owner_id)
        return record.model_copy(update={"audio_production_link": drifted})

    monkeypatch.setattr(store, "get", drifted_get)
    with pytest.raises(
        LocalAudibleCoordinatorError,
        match="(link identity|link changed|link receipt values)",
    ):
        coordinator.registered_audible_authority(
            "owner-1", request.asset_id, request.expected_revision_id
        )


def test_local_audio_zero_evidence_is_parent_scoped_and_strict(tmp_path: Path) -> None:
    coordinator, store, request = _fixture(tmp_path)
    coordinator.produce(request, now=NOW)
    import duckdb

    with duckdb.connect(str(tmp_path / "audible.duckdb")) as connection:
        connection.execute(
            "CREATE TABLE multimedia_provider_executions "
            "(operator_id TEXT, asset_id TEXT, revision_id TEXT)"
        )
    evidence = build_local_audio_zero_cost_evidence(
        coordinator=coordinator,
        db_path=str(tmp_path / "audible.duckdb"),
        snapshot_key=b"audio-local-zero-snapshot-key-32b",
        owner_id="owner-1",
        asset_id=request.asset_id,
        revision_id=request.expected_revision_id,
        now=NOW,
    )
    assert tuple(row.role for row in evidence.authorities) == ("local_audible",)
    assert evidence.excluded_revision_ids == (request.expected_revision_id,)
    assert "no provider child-revision namespace" in evidence.limitation
    verify_local_zero_cost_evidence(
        evidence,
        snapshot_key=b"audio-local-zero-snapshot-key-32b",
        owner_id="owner-1",
        asset_id=request.asset_id,
        revision_id=request.expected_revision_id,
    )
    hardened = store.run_hardening(
        request.asset_id,
        owner_id="owner-1",
        local_zero_cost_evidence=evidence,
        snapshot_key=b"audio-local-zero-snapshot-key-32b",
    )
    assert hardened.hardening_report is not None
    assert hardened.hardening_report.cost_snapshot is None
    assert hardened.hardening_report.local_zero_cost_evidence == evidence
    with pytest.raises(LocalZeroEvidenceUnavailable, match="evidence_unavailable"):
        verify_local_zero_cost_evidence(
            evidence,
            snapshot_key=b"wrong-audio-local-zero-key-32bytes",
            owner_id="owner-1",
            asset_id=request.asset_id,
            revision_id=request.expected_revision_id,
        )
    with pytest.raises(LocalZeroEvidenceUnavailable, match="evidence_unavailable"):
        verify_local_zero_cost_evidence(
            evidence,
            snapshot_key=b"audio-local-zero-snapshot-key-32b",
            owner_id="owner-2",
            asset_id=request.asset_id,
            revision_id=request.expected_revision_id,
        )
    changed = evidence.model_copy(update={"external_cost_cents": 1})
    with pytest.raises(LocalZeroEvidenceUnavailable, match="evidence_unavailable"):
        verify_local_zero_cost_evidence(
            changed,
            snapshot_key=b"audio-local-zero-snapshot-key-32b",
            owner_id="owner-1",
            asset_id=request.asset_id,
            revision_id=request.expected_revision_id,
        )
