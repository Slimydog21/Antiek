from __future__ import annotations

import hashlib
import hmac
import json
import os
import struct
import zlib
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import duckdb
import pytest
from nacl.signing import SigningKey

from runtime.db_lock import connect_write
from substrate.multimedia.artifact_quarantine import TransportResponse, quarantine_artifact
from substrate.multimedia.visual_evidence_authority import (
    VisualEvidenceAuthority,
    VisualEvidenceAuthorityError,
    attest_generated_visual,
    issue_visual_rights_decision,
)
from substrate.multimedia.visual_selection import ReviewedVisualSelection

QKEY = b"quarantine-signing-key-is-32-bytes"
OPERATOR_SEED = b"operator-ed25519-seed-32-bytes!!"
EVIDENCE_KEY = b"visual-verdict-key-is-32-bytes!!"
VERIFY_KEY = bytes(SigningKey(OPERATOR_SEED).verify_key)
NOW = datetime(2026, 7, 11, tzinfo=UTC)


def _png() -> bytes:
    def chunk(kind: bytes, payload: bytes) -> bytes:
        return (
            struct.pack(">I", len(payload))
            + kind
            + payload
            + struct.pack(">I", zlib.crc32(kind + payload) & 0xFFFFFFFF)
        )

    scanline = zlib.compress(b"\x00\x00\x00\x00\x00")
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 6, 0, 0, 0))
        + chunk(b"IDAT", scanline)
        + chunk(b"IEND", b"")
    )


@dataclass
class Resolver:
    def resolve(self, hostname: str) -> tuple[str, ...]:
        assert hostname == "cdn.example.test"
        return ("8.8.8.8",)


@dataclass
class Transport:
    def get(self, **kwargs: object) -> TransportResponse:
        return TransportResponse(
            200,
            {"Content-Type": "image/png", "Content-Length": str(len(_png()))},
            "8.8.8.8",
            [_png()],
        )


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _seed_candidate(db: Path) -> None:
    url = "https://cdn.example.test/a.png"
    values: list[object] = [
        "candidate-1",
        "execution-1",
        0,
        hashlib.sha256(url.encode()).hexdigest(),
        "unknown",
    ]
    mac = hmac.new(
        QKEY,
        json.dumps(values, ensure_ascii=True, separators=(",", ":")).encode(),
        hashlib.sha256,
    ).hexdigest()
    with connect_write(str(db), purpose="test.visual_evidence.seed_candidate") as connection:
        connection.execute(
            "CREATE TABLE multimedia_provider_artifact_candidates ("
            "candidate_id TEXT PRIMARY KEY, execution_id TEXT, ordinal INTEGER, "
            "source_locator_digest TEXT, declared_media_type TEXT, candidate_mac TEXT)"
        )
        connection.execute(
            "INSERT INTO multimedia_provider_artifact_candidates VALUES (?, ?, ?, ?, ?, ?)",
            [*values, mac],
        )


def _generated(db: Path, root: Path) -> ReviewedVisualSelection:
    _seed_candidate(db)
    receipt = quarantine_artifact(
        db_path=str(db),
        execution_id="execution-1",
        candidate_id="candidate-1",
        url="https://cdn.example.test/a.png",
        allowlisted_hosts=frozenset({"cdn.example.test"}),
        resolver=Resolver(),
        transport=Transport(),
        quarantine_dir=str(root / "quarantine"),
        signing_key=QKEY,
        now=NOW,
    )
    attest_generated_visual(
        db_path=str(db),
        receipt_id=receipt.receipt_id,
        reviewer_id="operator-1",
        quarantine_signing_key=QKEY,
        operator_signing_key=OPERATOR_SEED,
        attested_at=NOW,
    )
    return ReviewedVisualSelection(
        scene_id="scene-1",
        path=receipt.quarantine_path,
        expected_sha256=receipt.sha256,
        visual_label="generated",
        source_chunk_ids=("chunk-1",),
        execution_receipt_id="execution-1",
        artifact_receipt_id=receipt.receipt_id,
    )


def _sourced(db: Path, image: Path) -> ReviewedVisualSelection:
    issue_visual_rights_decision(
        db_path=str(db),
        decision_id="rights-1",
        source_locator_digest="1" * 64,
        content_sha256=_sha(image),
        authority_path=str(image),
        visual_label="sourced",
        rights_basis="licensed",
        reviewer_id="operator-1",
        operator_signing_key=OPERATOR_SEED,
        decided_at=NOW,
    )
    return ReviewedVisualSelection(
        scene_id="scene-2",
        path=str(image),
        expected_sha256=_sha(image),
        visual_label="sourced",
        source_chunk_ids=("chunk-2",),
        source_locator_digest="1" * 64,
        rights_basis="licensed",
        rights_review_id="rights-1",
    )


def _authority(db: Path, reviewers: frozenset[str] = frozenset({"operator-1"})):
    return VisualEvidenceAuthority(
        db_path=str(db),
        operator_verify_key=VERIFY_KEY,
        evidence_authority_key=EVIDENCE_KEY,
        authorized_reviewer_ids=reviewers,
    )


@pytest.fixture
def media(tmp_path: Path):
    db = tmp_path / "authority.duckdb"
    sourced = tmp_path / "sourced.jpg"
    sourced.write_bytes(b"sourced-image")
    sourced.chmod(0o600)
    return db, sourced, tmp_path


def test_real_quarantine_receipt_and_sourced_decision_resolve(media) -> None:
    db, sourced, root = media
    generated_selection = _generated(db, root)
    sourced_selection = _sourced(db, sourced)
    authority = _authority(db)
    generated = authority(generated_selection, generated_selection.expected_sha256)
    reviewed = authority(sourced_selection, sourced_selection.expected_sha256)
    assert generated.visual_label == "generated"
    assert reviewed.visual_label == "sourced"
    assert generated.evidence_digest != reviewed.evidence_digest


def test_verifier_has_public_key_only_and_rejects_forged_records(media) -> None:
    db, sourced, root = media
    selection = _generated(db, root)
    assert not hasattr(_authority(db), "_quarantine_key")
    with duckdb.connect(str(db)) as connection:
        connection.execute(
            "UPDATE multimedia_generated_visual_attestations SET receipt_digest=?",
            ["0" * 64],
        )
    with pytest.raises(VisualEvidenceAuthorityError, match="signature"):
        _authority(db)(selection, selection.expected_sha256)
    rights = _sourced(db, sourced)
    with duckdb.connect(str(db)) as connection:
        connection.execute(
            "UPDATE multimedia_visual_rights_decisions SET rights_basis='operator_owned'"
        )
    with pytest.raises(VisualEvidenceAuthorityError, match="signature"):
        _authority(db)(rights, rights.expected_sha256)


def test_reviewer_allowlist_and_wrong_public_key_fail(media) -> None:
    db, sourced, _ = media
    selection = _sourced(db, sourced)
    with pytest.raises(VisualEvidenceAuthorityError, match="not authorized"):
        _authority(db, frozenset({"operator-2"}))(selection, selection.expected_sha256)
    wrong = SigningKey(hashlib.sha256(b"wrong operator").digest())
    authority = VisualEvidenceAuthority(
        db_path=str(db),
        operator_verify_key=bytes(wrong.verify_key),
        evidence_authority_key=EVIDENCE_KEY,
        authorized_reviewer_ids=frozenset({"operator-1"}),
    )
    with pytest.raises(VisualEvidenceAuthorityError, match="signature"):
        authority(selection, selection.expected_sha256)


def test_generated_cross_execution_copy_hardlink_and_byte_drift_fail(media) -> None:
    db, _, root = media
    selection = _generated(db, root)
    authority = _authority(db)
    crossed = selection.model_copy(update={"execution_receipt_id": "execution-2"})
    with pytest.raises(VisualEvidenceAuthorityError, match="binding"):
        authority(crossed, selection.expected_sha256)
    source = Path(selection.path)
    copy = root / "copy.png"
    copy.write_bytes(source.read_bytes())
    copy.chmod(0o600)
    for alias in (copy, root / "hardlink.png"):
        if not alias.exists():
            os.link(source, alias)
        changed = selection.model_copy(update={"path": str(alias)})
        with pytest.raises(VisualEvidenceAuthorityError, match="path binding"):
            authority(changed, selection.expected_sha256)
    source.chmod(0o600)
    source.write_bytes(b"drift")
    with pytest.raises(VisualEvidenceAuthorityError, match="size|digest"):
        authority(selection, selection.expected_sha256)


def test_sourced_path_digest_locator_label_and_basis_are_authoritative(media) -> None:
    db, sourced, root = media
    selection = _sourced(db, sourced)
    authority = _authority(db)
    copy = root / "copy.jpg"
    copy.write_bytes(sourced.read_bytes())
    copy.chmod(0o600)
    changes = (
        {"path": str(copy)},
        {"source_locator_digest": "2" * 64},
        {"visual_label": "archival"},
        {"rights_basis": "operator_owned"},
    )
    for change in changes:
        crossed = selection.model_copy(update=change)
        with pytest.raises((VisualEvidenceAuthorityError, ValueError)):
            authority(crossed, selection.expected_sha256)


def test_exact_replay_and_concurrent_issuance_are_single_record(media) -> None:
    db, sourced, _ = media

    def issue() -> str:
        return issue_visual_rights_decision(
            db_path=str(db),
            decision_id="rights-1",
            source_locator_digest="1" * 64,
            content_sha256=_sha(sourced),
            authority_path=str(sourced),
            visual_label="sourced",
            rights_basis="licensed",
            reviewer_id="operator-1",
            operator_signing_key=OPERATOR_SEED,
            decided_at=NOW,
        ).signature

    with ThreadPoolExecutor(max_workers=8) as pool:
        signatures = tuple(pool.map(lambda _: issue(), range(16)))
    assert len(set(signatures)) == 1
    with duckdb.connect(str(db)) as connection:
        assert (
            connection.execute(
                "SELECT count(*) FROM multimedia_visual_rights_decisions"
            ).fetchone()[0]
            == 1
        )


def test_conflicting_replay_and_concurrent_conflict_fail(media) -> None:
    db, sourced, _ = media
    _sourced(db, sourced)

    def conflict(rights_basis: str) -> str:
        try:
            issue_visual_rights_decision(
                db_path=str(db),
                decision_id="rights-1",
                source_locator_digest="1" * 64,
                content_sha256=_sha(sourced),
                authority_path=str(sourced),
                visual_label="sourced",
                rights_basis=rights_basis,
                reviewer_id="operator-1",
                operator_signing_key=OPERATOR_SEED,
                decided_at=NOW,
            )
            return "accepted"
        except (VisualEvidenceAuthorityError, ValueError):
            return "rejected"

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = tuple(pool.map(conflict, ("licensed", "operator_owned")))
    assert results.count("accepted") == 1 and results.count("rejected") == 1


def test_parent_directory_symlinks_are_never_authority_paths(media) -> None:
    db, sourced, root = media
    directory = root / "real"
    directory.mkdir()
    target = directory / "image.jpg"
    target.write_bytes(sourced.read_bytes())
    target.chmod(0o600)
    link = root / "link"
    link.symlink_to(directory, target_is_directory=True)
    with pytest.raises(ValueError, match="symlinks"):
        issue_visual_rights_decision(
            db_path=str(db),
            decision_id="rights-link",
            source_locator_digest="1" * 64,
            content_sha256=_sha(target),
            authority_path=str(link / "image.jpg"),
            visual_label="sourced",
            rights_basis="licensed",
            reviewer_id="operator-1",
            operator_signing_key=OPERATOR_SEED,
            decided_at=NOW,
        )


def test_diagram_model_copy_unknown_records_and_non_private_files_fail(media) -> None:
    db, sourced, _ = media
    diagram = ReviewedVisualSelection(
        scene_id="scene-d",
        path=str(sourced),
        expected_sha256=_sha(sourced),
        visual_label="diagram",
        source_chunk_ids=("chunk-1",),
    )
    with pytest.raises(VisualEvidenceAuthorityError, match="graph-chunk"):
        _authority(db)(diagram, diagram.expected_sha256)
    bypass = diagram.model_copy(update={"visual_label": "generated"})
    with pytest.raises(ValueError, match="execution and artifact"):
        _authority(db)(bypass, bypass.expected_sha256)
    sourced.chmod(0o644)
    with pytest.raises(VisualEvidenceAuthorityError, match="file binding"):
        issue_visual_rights_decision(
            db_path=str(db),
            decision_id="rights-x",
            source_locator_digest="1" * 64,
            content_sha256=_sha(sourced),
            authority_path=str(sourced),
            visual_label="sourced",
            rights_basis="licensed",
            reviewer_id="operator-1",
            operator_signing_key=OPERATOR_SEED,
            decided_at=NOW,
        )


def test_closed_enums_time_keys_and_empty_reviewer_set_fail(media) -> None:
    db, sourced, _ = media
    common = dict(
        db_path=str(db),
        decision_id="rights-1",
        source_locator_digest="1" * 64,
        content_sha256=_sha(sourced),
        authority_path=str(sourced),
        reviewer_id="operator-1",
        operator_signing_key=OPERATOR_SEED,
        decided_at=NOW,
    )
    with pytest.raises(ValueError, match="rights-reviewable"):
        issue_visual_rights_decision(**common, visual_label="generated", rights_basis="licensed")
    with pytest.raises(ValueError, match="recognized"):
        issue_visual_rights_decision(**common, visual_label="sourced", rights_basis="unknown")
    with pytest.raises(ValueError, match="timezone-aware"):
        issue_visual_rights_decision(
            **{**common, "decided_at": datetime(2026, 7, 11)},
            visual_label="sourced",
            rights_basis="licensed",
        )
    with pytest.raises(ValueError, match="non-empty"):
        _authority(db, frozenset())
