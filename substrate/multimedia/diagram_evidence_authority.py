"""Graph-backed authority for educational diagram visuals."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import stat
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from nacl.exceptions import BadSignatureError
from nacl.signing import SigningKey, VerifyKey

from runtime.db_lock import FlockWriteCoordinator, connect_read

from .visual_selection import ReviewedVisualSelection, VerifiedVisualEvidence

_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_DIGEST = re.compile(r"^[0-9a-f]{64}$")
_MAX_CHUNKS = 32
_MAX_FILE_BYTES = 100 * 1024 * 1024
EvidenceVerifier = Callable[[ReviewedVisualSelection, str], VerifiedVisualEvidence]

_DDL = """
CREATE TABLE IF NOT EXISTS multimedia_diagram_attestations (
 attestation_id TEXT PRIMARY KEY, content_sha256 TEXT NOT NULL, authority_path TEXT NOT NULL,
 chunk_snapshot_json TEXT NOT NULL, reviewer_id TEXT NOT NULL, attested_at TEXT NOT NULL,
 signature TEXT NOT NULL)
"""


class DiagramEvidenceAuthorityError(RuntimeError):
    """Diagram evidence could not be proved from canonical graph state."""


@dataclass(frozen=True)
class DiagramAttestation:
    attestation_id: str
    content_sha256: str
    authority_path: str
    chunk_snapshot_json: str
    reviewer_id: str
    attested_at: str
    signature: str


def attest_diagram(
    *,
    db_path: str,
    diagram_path: str,
    content_sha256: str,
    source_chunk_ids: tuple[str, ...],
    reviewer_id: str,
    operator_signing_key: bytes,
    attested_at: datetime,
) -> DiagramAttestation:
    """Snapshot canonical chunks and sign their exact relationship to one diagram."""
    content_sha256 = _digest(content_sha256, "content_sha256")
    reviewer_id = _identifier(reviewer_id, "reviewer_id")
    authority_path = _private_file(diagram_path, content_sha256)
    timestamp = _timestamp(attested_at)
    attestation_id = _attestation_id(content_sha256, source_chunk_ids)
    coordinator = FlockWriteCoordinator(db_path)
    with coordinator.acquire_write_context("multimedia.diagram.attest") as connection:
        connection.execute(_DDL)
        snapshot_json = _canonical_json(_chunk_snapshot_on(connection, source_chunk_ids))
        values: list[object] = [
            attestation_id,
            content_sha256,
            authority_path,
            snapshot_json,
            reviewer_id,
            timestamp,
        ]
        signature = _sign(operator_signing_key, values)
        existing = connection.execute(
            "SELECT attestation_id, content_sha256, authority_path, chunk_snapshot_json, "
            "reviewer_id, attested_at, signature FROM multimedia_diagram_attestations "
            "WHERE attestation_id=?",
            [attestation_id],
        ).fetchone()
        row = tuple([*values, signature])
        if existing is None:
            connection.execute(
                "INSERT INTO multimedia_diagram_attestations VALUES (?, ?, ?, ?, ?, ?, ?)",
                list(row),
            )
        elif tuple(existing) != row:
            raise DiagramEvidenceAuthorityError("diagram attestation conflicts")
    return DiagramAttestation(
        attestation_id,
        content_sha256,
        authority_path,
        snapshot_json,
        reviewer_id,
        timestamp,
        signature,
    )


class DiagramEvidenceAuthority:
    """Composite evidence verifier adding diagram authority to an accepted fallback."""

    def __init__(
        self,
        *,
        db_path: str,
        operator_verify_key: bytes,
        evidence_authority_key: bytes,
        authorized_reviewer_ids: frozenset[str],
        fallback: EvidenceVerifier,
    ) -> None:
        self._db_path = db_path
        self._verify_key = _verify_key(operator_verify_key)
        self._evidence_key = _key(evidence_authority_key)
        if not authorized_reviewer_ids or len(authorized_reviewer_ids) > 32:
            raise ValueError("authorized_reviewer_ids must be a bounded non-empty set")
        self._reviewers = frozenset(
            _identifier(value, "authorized_reviewer_id") for value in authorized_reviewer_ids
        )
        self._fallback = fallback

    def __call__(
        self, selection: ReviewedVisualSelection, content_sha256: str
    ) -> VerifiedVisualEvidence:
        selection = ReviewedVisualSelection.model_validate(selection.model_dump(mode="python"))
        content_sha256 = _digest(content_sha256, "content_sha256")
        if selection.visual_label != "diagram":
            return VerifiedVisualEvidence.model_validate(
                self._fallback(selection, content_sha256).model_dump(mode="python")
            )
        if not hmac.compare_digest(content_sha256, selection.expected_sha256):
            raise DiagramEvidenceAuthorityError("diagram content digest is not reviewed")
        attestation_id = _attestation_id(content_sha256, selection.source_chunk_ids)
        try:
            with connect_read(self._db_path) as connection:
                connection.execute("BEGIN TRANSACTION")
                row = connection.execute(
                    "SELECT attestation_id, content_sha256, authority_path, chunk_snapshot_json, "
                    "reviewer_id, attested_at, signature FROM multimedia_diagram_attestations "
                    "WHERE attestation_id=?",
                    [attestation_id],
                ).fetchone()
                if row is None or len(row) != 7:
                    raise DiagramEvidenceAuthorityError("diagram attestation is unavailable")
                current_snapshot = _canonical_json(
                    _chunk_snapshot_on(connection, selection.source_chunk_ids)
                )
        except DiagramEvidenceAuthorityError:
            raise
        except Exception:
            raise DiagramEvidenceAuthorityError("diagram attestation is unavailable") from None
        values = list(row[:6])
        reviewer_id = str(row[4])
        if reviewer_id not in self._reviewers:
            raise DiagramEvidenceAuthorityError("diagram reviewer is not authorized")
        _verify_signature(self._verify_key, values, str(row[6]))
        if row[0] != attestation_id or row[1] != content_sha256 or row[3] != current_snapshot:
            raise DiagramEvidenceAuthorityError("diagram graph snapshot binding is invalid")
        canonical_path = _private_file(selection.path, content_sha256)
        if row[2] != canonical_path:
            raise DiagramEvidenceAuthorityError("diagram path binding is invalid")
        evidence_digest = hashlib.sha256(_canonical(values)).hexdigest()
        return VerifiedVisualEvidence.issue(
            scene_id=selection.scene_id,
            visual_label="diagram",
            content_sha256=content_sha256,
            evidence_digest=evidence_digest,
            authority_key=self._evidence_key,
        )


def _validate_chunk_ids(chunk_ids: tuple[str, ...]) -> None:
    if not chunk_ids or len(chunk_ids) > _MAX_CHUNKS or len(set(chunk_ids)) != len(chunk_ids):
        raise ValueError("source_chunk_ids must be bounded, non-empty, and unique")
    for chunk_id in chunk_ids:
        _identifier(chunk_id, "source_chunk_id")


def _chunk_snapshot_on(connection: Any, chunk_ids: tuple[str, ...]) -> list[list[str | None]]:
    _validate_chunk_ids(chunk_ids)
    placeholders = ",".join("?" for _ in chunk_ids)
    try:
        rows = connection.execute(
            "SELECT c.chunk_id, c.document_id, c.text, CAST(c.chunk_index AS VARCHAR), "
            "c.section_path, CAST(c.token_count AS VARCHAR), "
            "CASE WHEN c.embedding IS NULL THEN NULL ELSE sha256(to_json(c.embedding)) END, "
            "d.source_uri, d.title, d.author, "
            "CAST(d.published_at AS VARCHAR), CAST(d.acquired_at AS VARCHAR), "
            "CAST(d.source_tier AS VARCHAR), d.document_type, d.investigation_id, "
            "CASE WHEN d.raw_text IS NULL THEN NULL ELSE sha256(d.raw_text) END, "
            "CASE WHEN d.metadata IS NULL THEN NULL ELSE sha256(d.metadata) END, "
            "d.owner_user_id FROM chunks c JOIN documents d ON d.document_id=c.document_id "
            f"WHERE c.chunk_id IN ({placeholders})",
            list(chunk_ids),
        ).fetchall()
    except Exception:
        raise DiagramEvidenceAuthorityError("canonical graph chunks are unavailable") from None
    by_id = {str(row[0]): row for row in rows}
    if len(by_id) != len(chunk_ids):
        raise DiagramEvidenceAuthorityError("canonical graph chunk is missing")
    snapshot: list[list[str | None]] = []
    for chunk_id in chunk_ids:
        row = by_id[chunk_id]
        document_id, text = str(row[1]), str(row[2])
        _identifier(document_id, "document_id")
        if not text.strip() or len(text.encode()) > 1024 * 1024:
            raise DiagramEvidenceAuthorityError("canonical graph chunk text is invalid")
        provenance = [None if value is None else str(value) for value in row[3:]]
        snapshot.append(
            [chunk_id, document_id, hashlib.sha256(text.encode()).hexdigest(), *provenance]
        )
    return snapshot


def _private_file(value: str, expected_digest: str) -> str:
    if not isinstance(value, str) or not value or len(value.encode()) > 4096:
        raise ValueError("diagram_path is invalid")
    absolute, resolved = os.path.abspath(value), os.path.realpath(value)
    if absolute != resolved:
        raise ValueError("diagram_path cannot traverse symlinks")
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(absolute, flags)
    except OSError:
        raise DiagramEvidenceAuthorityError("diagram file is unavailable") from None
    try:
        metadata = os.fstat(fd)
        if (
            not stat.S_ISREG(metadata.st_mode)
            or metadata.st_uid != os.getuid()
            or stat.S_IMODE(metadata.st_mode) != 0o600
            or metadata.st_size <= 0
            or metadata.st_size > _MAX_FILE_BYTES
        ):
            raise DiagramEvidenceAuthorityError("diagram file is not private and bounded")
        digest = hashlib.sha256()
        while chunk := os.read(fd, 1024 * 1024):
            digest.update(chunk)
    finally:
        os.close(fd)
    if not hmac.compare_digest(digest.hexdigest(), expected_digest):
        raise DiagramEvidenceAuthorityError("diagram file digest is invalid")
    return absolute


def _attestation_id(content_sha256: str, chunk_ids: tuple[str, ...]) -> str:
    payload = _canonical([content_sha256, list(chunk_ids)])
    return "mmdiagram_" + hashlib.sha256(payload).hexdigest()


def _sign(seed: bytes, values: list[object]) -> str:
    if not isinstance(seed, bytes) or len(seed) != 32:
        raise ValueError("operator_signing_key must be a 32-byte Ed25519 seed")
    return SigningKey(seed).sign(_canonical(values)).signature.hex()


def _verify_key(value: bytes) -> VerifyKey:
    if not isinstance(value, bytes) or len(value) != 32:
        raise ValueError("operator_verify_key must be 32 bytes")
    return VerifyKey(value)


def _verify_signature(key: VerifyKey, values: list[object], signature: str) -> None:
    try:
        key.verify(_canonical(values), bytes.fromhex(signature))
    except (BadSignatureError, ValueError):
        raise DiagramEvidenceAuthorityError("diagram signature is invalid") from None


def _canonical(values: list[object]) -> bytes:
    return json.dumps(values, ensure_ascii=True, separators=(",", ":")).encode()


def _canonical_json(values: list[list[str | None]]) -> str:
    return json.dumps(values, ensure_ascii=True, separators=(",", ":"))


def _timestamp(value: datetime) -> str:
    if value.tzinfo is None:
        raise ValueError("attested_at must be timezone-aware")
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _identifier(value: str, field: str) -> str:
    if not isinstance(value, str) or not _ID.fullmatch(value):
        raise ValueError(f"{field} is not a bounded identifier")
    return value


def _digest(value: str, field: str) -> str:
    if not isinstance(value, str) or not _DIGEST.fullmatch(value):
        raise ValueError(f"{field} is not a SHA-256 digest")
    return value


def _key(value: bytes) -> bytes:
    if not isinstance(value, bytes) or len(value) < 32:
        raise ValueError("evidence_authority_key must contain at least 32 bytes")
    return value


__all__ = [
    "DiagramAttestation",
    "DiagramEvidenceAuthority",
    "DiagramEvidenceAuthorityError",
    "attest_diagram",
]
