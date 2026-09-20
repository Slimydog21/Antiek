"""Public-key evidence authority for documentary visual selections."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import stat
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal

from nacl.exceptions import BadSignatureError
from nacl.signing import SigningKey, VerifyKey

from runtime.db_lock import FlockWriteCoordinator, connect_read

from .visual_selection import ReviewedVisualSelection, VerifiedVisualEvidence

_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_DIGEST = re.compile(r"^[0-9a-f]{64}$")
_MAX_FILE_BYTES = 100 * 1024 * 1024
RightsBasis = Literal["public_domain", "licensed", "operator_owned"]

_ATTESTATION_DDL = """
CREATE TABLE IF NOT EXISTS multimedia_generated_visual_attestations (
 receipt_id TEXT PRIMARY KEY, receipt_digest TEXT NOT NULL, reviewer_id TEXT NOT NULL,
 attested_at TEXT NOT NULL, signature TEXT NOT NULL)
"""
_RIGHTS_DDL = """
CREATE TABLE IF NOT EXISTS multimedia_visual_rights_decisions (
 decision_id TEXT PRIMARY KEY, source_locator_digest TEXT NOT NULL,
 content_sha256 TEXT NOT NULL, authority_path TEXT NOT NULL, visual_label TEXT NOT NULL,
 rights_basis TEXT NOT NULL, reviewer_id TEXT NOT NULL, decided_at TEXT NOT NULL,
 signature TEXT NOT NULL)
"""


class VisualEvidenceAuthorityError(RuntimeError):
    """Evidence could not be proved by the configured authority stores."""


@dataclass(frozen=True)
class GeneratedVisualAttestation:
    receipt_id: str
    receipt_digest: str
    reviewer_id: str
    attested_at: str
    signature: str


@dataclass(frozen=True)
class VisualRightsDecision:
    decision_id: str
    source_locator_digest: str
    content_sha256: str
    authority_path: str
    visual_label: Literal["sourced", "archival"]
    rights_basis: RightsBasis
    reviewer_id: str
    decided_at: str
    signature: str


def attest_generated_visual(
    *,
    db_path: str,
    receipt_id: str,
    reviewer_id: str,
    quarantine_signing_key: bytes,
    operator_signing_key: bytes,
    attested_at: datetime,
) -> GeneratedVisualAttestation:
    """Verify a canonical quarantine receipt, then sign its immutable digest."""
    receipt_id = _identifier(receipt_id, "receipt_id")
    reviewer_id = _identifier(reviewer_id, "reviewer_id")
    timestamp = _timestamp(attested_at, "attested_at")
    receipt = _load_receipt(db_path, receipt_id)
    values = list(receipt[:8])
    if not isinstance(receipt[8], str) or not hmac.compare_digest(
        receipt[8], _hmac(_symmetric_key(quarantine_signing_key), values)
    ):
        raise VisualEvidenceAuthorityError("generated artifact receipt MAC is invalid")
    _verify_file(str(receipt[6]), str(receipt[6]), _stored_int(receipt[4]), str(receipt[5]))
    receipt_digest = _record_digest(values)
    signed_values: list[object] = [receipt_id, receipt_digest, reviewer_id, timestamp]
    signature = _sign(operator_signing_key, signed_values)
    coordinator = FlockWriteCoordinator(db_path)
    with coordinator.acquire_write_context("multimedia.generated_visual.attest") as connection:
        connection.execute(_ATTESTATION_DDL)
        existing = connection.execute(
            "SELECT receipt_id, receipt_digest, reviewer_id, attested_at, signature "
            "FROM multimedia_generated_visual_attestations WHERE receipt_id=?",
            [receipt_id],
        ).fetchone()
        row = tuple([*signed_values, signature])
        if existing is None:
            connection.execute(
                "INSERT INTO multimedia_generated_visual_attestations VALUES (?, ?, ?, ?, ?)",
                list(row),
            )
        else:
            existing_values = list(existing[:4])
            if (
                existing[0] != receipt_id or existing[1] != receipt_digest
                or existing[2] != reviewer_id
            ):
                raise VisualEvidenceAuthorityError("generated visual attestation conflicts")
            _verify_signature(
                SigningKey(operator_signing_key).verify_key,
                existing_values,
                str(existing[4]),
            )
            return GeneratedVisualAttestation(
                str(existing[0]), str(existing[1]), str(existing[2]),
                str(existing[3]), str(existing[4]),
            )
    return GeneratedVisualAttestation(receipt_id, receipt_digest, reviewer_id, timestamp, signature)


def issue_visual_rights_decision(
    *,
    db_path: str,
    decision_id: str,
    source_locator_digest: str,
    content_sha256: str,
    authority_path: str,
    visual_label: Literal["sourced", "archival"],
    rights_basis: RightsBasis,
    reviewer_id: str,
    operator_signing_key: bytes,
    decided_at: datetime,
) -> VisualRightsDecision:
    """Sign and persist one operator decision bound to exact source bytes and path."""
    decision_id = _identifier(decision_id, "decision_id")
    reviewer_id = _identifier(reviewer_id, "reviewer_id")
    source_locator_digest = _digest(source_locator_digest, "source_locator_digest")
    content_sha256 = _digest(content_sha256, "content_sha256")
    if visual_label not in {"sourced", "archival"}:
        raise ValueError("visual_label is not rights-reviewable")
    if rights_basis not in {"public_domain", "licensed", "operator_owned"}:
        raise ValueError("rights_basis is not recognized")
    timestamp = _timestamp(decided_at, "decided_at")
    canonical_path = _canonical_path(authority_path)
    _verify_file(canonical_path, canonical_path, None, content_sha256)
    signed_values: list[object] = [
        decision_id,
        source_locator_digest,
        content_sha256,
        canonical_path,
        visual_label,
        rights_basis,
        reviewer_id,
        timestamp,
    ]
    signature = _sign(operator_signing_key, signed_values)
    coordinator = FlockWriteCoordinator(db_path)
    with coordinator.acquire_write_context("multimedia.visual_rights.issue") as connection:
        connection.execute(_RIGHTS_DDL)
        existing = connection.execute(
            "SELECT decision_id, source_locator_digest, content_sha256, authority_path, "
            "visual_label, rights_basis, reviewer_id, decided_at, signature "
            "FROM multimedia_visual_rights_decisions WHERE decision_id=?",
            [decision_id],
        ).fetchone()
        row = tuple([*signed_values, signature])
        if existing is None:
            connection.execute(
                "INSERT INTO multimedia_visual_rights_decisions VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                list(row),
            )
        elif tuple(existing) != row:
            raise VisualEvidenceAuthorityError("visual rights decision conflicts")
    return VisualRightsDecision(
        decision_id,
        source_locator_digest,
        content_sha256,
        canonical_path,
        visual_label,
        rights_basis,
        reviewer_id,
        timestamp,
        signature,
    )


class VisualEvidenceAuthority:
    """Read-only resolver holding no issuance or quarantine signing secret."""

    def __init__(
        self,
        *,
        db_path: str,
        operator_verify_key: bytes,
        evidence_authority_key: bytes,
        authorized_reviewer_ids: frozenset[str],
    ) -> None:
        self._db_path = db_path
        self._verify_key = _verify_key(operator_verify_key)
        self._evidence_key = _symmetric_key(evidence_authority_key)
        if not authorized_reviewer_ids or len(authorized_reviewer_ids) > 32:
            raise ValueError("authorized_reviewer_ids must be a bounded non-empty set")
        self._reviewers = frozenset(
            _identifier(value, "authorized_reviewer_id") for value in authorized_reviewer_ids
        )

    def __call__(
        self, selection: ReviewedVisualSelection, content_sha256: str
    ) -> VerifiedVisualEvidence:
        selection = ReviewedVisualSelection.model_validate(selection.model_dump(mode="python"))
        content_sha256 = _digest(content_sha256, "content_sha256")
        if not hmac.compare_digest(content_sha256, selection.expected_sha256):
            raise VisualEvidenceAuthorityError("selection content digest is not reviewed")
        if selection.visual_label == "generated":
            evidence_digest = self._verify_generated(selection, content_sha256)
        elif selection.visual_label in {"sourced", "archival"}:
            evidence_digest = self._verify_rights(selection, content_sha256)
        else:
            raise VisualEvidenceAuthorityError(
                "diagram evidence requires a canonical graph-chunk authority"
            )
        return VerifiedVisualEvidence.issue(
            scene_id=selection.scene_id,
            visual_label=selection.visual_label,
            content_sha256=content_sha256,
            evidence_digest=evidence_digest,
            authority_key=self._evidence_key,
        )

    def _verify_generated(self, selection: ReviewedVisualSelection, content_sha256: str) -> str:
        receipt = _load_receipt(self._db_path, str(selection.artifact_receipt_id))
        try:
            with connect_read(self._db_path) as connection:
                attestation = connection.execute(
                    "SELECT receipt_id, receipt_digest, reviewer_id, attested_at, signature "
                    "FROM multimedia_generated_visual_attestations WHERE receipt_id=?",
                    [selection.artifact_receipt_id],
                ).fetchone()
        except Exception:
            raise VisualEvidenceAuthorityError(
                "generated visual attestation is unavailable"
            ) from None
        if attestation is None or len(attestation) != 5:
            raise VisualEvidenceAuthorityError("generated visual attestation is unavailable")
        values = list(attestation[:4])
        self._verify_operator_record(values, str(attestation[4]), str(attestation[2]))
        receipt_values = list(receipt[:8])
        if (
            attestation[0] != selection.artifact_receipt_id
            or attestation[1] != _record_digest(receipt_values)
            or receipt[1] != selection.execution_receipt_id
            or receipt[0] != selection.artifact_receipt_id
            or receipt[3] not in {"image/png", "image/jpeg"}
            or receipt[5] != content_sha256
        ):
            raise VisualEvidenceAuthorityError("generated artifact authority binding is invalid")
        _verify_file(selection.path, str(receipt[6]), _stored_int(receipt[4]), content_sha256)
        return _record_digest([*receipt_values, *values])

    def _verify_rights(self, selection: ReviewedVisualSelection, content_sha256: str) -> str:
        try:
            with connect_read(self._db_path) as connection:
                row = connection.execute(
                    "SELECT decision_id, source_locator_digest, content_sha256, authority_path, "
                    "visual_label, rights_basis, reviewer_id, decided_at, signature "
                    "FROM multimedia_visual_rights_decisions WHERE decision_id=?",
                    [selection.rights_review_id],
                ).fetchone()
        except Exception:
            raise VisualEvidenceAuthorityError("visual rights decision is unavailable") from None
        if row is None or len(row) != 9:
            raise VisualEvidenceAuthorityError("visual rights decision is unavailable")
        values = list(row[:8])
        self._verify_operator_record(values, str(row[8]), str(row[6]))
        if (
            row[0] != selection.rights_review_id
            or row[1] != selection.source_locator_digest
            or row[2] != content_sha256
            or row[3] != _canonical_path(selection.path)
            or row[4] != selection.visual_label
            or row[5] != selection.rights_basis
        ):
            raise VisualEvidenceAuthorityError("visual rights decision binding is invalid")
        _verify_file(selection.path, str(row[3]), None, content_sha256)
        return _record_digest(values)

    def _verify_operator_record(
        self, values: list[object], signature: str, reviewer_id: str
    ) -> None:
        if reviewer_id not in self._reviewers:
            raise VisualEvidenceAuthorityError("visual reviewer is not authorized")
        _verify_signature(self._verify_key, values, signature)


def _load_receipt(db_path: str, receipt_id: str) -> tuple[object, ...]:
    try:
        with connect_read(db_path) as connection:
            row = connection.execute(
                "SELECT receipt_id, execution_id, candidate_id, media_type, byte_count, sha256, "
                "quarantine_path, created_at, receipt_mac "
                "FROM multimedia_artifact_quarantine_receipts WHERE receipt_id=?",
                [receipt_id],
            ).fetchone()
    except Exception:
        raise VisualEvidenceAuthorityError("generated artifact receipt is unavailable") from None
    if row is None or len(row) != 9:
        raise VisualEvidenceAuthorityError("generated artifact receipt is unavailable")
    return tuple(row)


def _verify_file(
    selected_path: str,
    authority_path: str,
    expected_size: int | None,
    expected_digest: str,
) -> None:
    selected_canonical = _canonical_path(selected_path)
    authority_canonical = _canonical_path(authority_path)
    if selected_canonical != authority_canonical:
        raise VisualEvidenceAuthorityError("visual authority path binding is invalid")
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        selected_fd = os.open(selected_canonical, flags)
        authority_fd = os.open(authority_canonical, flags)
    except OSError:
        raise VisualEvidenceAuthorityError("visual authority file is unavailable") from None
    try:
        selected_meta = os.fstat(selected_fd)
        authority_meta = os.fstat(authority_fd)
        if (
            not stat.S_ISREG(selected_meta.st_mode)
            or (selected_meta.st_dev, selected_meta.st_ino)
            != (authority_meta.st_dev, authority_meta.st_ino)
            or selected_meta.st_uid != os.getuid()
            or stat.S_IMODE(selected_meta.st_mode) != 0o600
        ):
            raise VisualEvidenceAuthorityError("visual authority file binding is invalid")
        if selected_meta.st_size <= 0 or selected_meta.st_size > _MAX_FILE_BYTES:
            raise VisualEvidenceAuthorityError("visual authority file is outside byte limits")
        if expected_size is not None and selected_meta.st_size != expected_size:
            raise VisualEvidenceAuthorityError("visual authority file size is invalid")
        actual = _hash_fd(selected_fd)
    finally:
        os.close(authority_fd)
        os.close(selected_fd)
    if not hmac.compare_digest(actual, expected_digest):
        raise VisualEvidenceAuthorityError("visual authority file digest is invalid")


def _canonical_path(value: str) -> str:
    if not isinstance(value, str) or not value or len(value.encode()) > 4096:
        raise ValueError("authority_path is invalid")
    absolute = os.path.abspath(value)
    resolved = os.path.realpath(value)
    if absolute != resolved:
        raise ValueError("authority_path cannot traverse symlinks")
    return absolute


def _hash_fd(fd: int) -> str:
    digest = hashlib.sha256()
    read = 0
    while chunk := os.read(fd, 1024 * 1024):
        read += len(chunk)
        if read > _MAX_FILE_BYTES:
            raise VisualEvidenceAuthorityError("visual authority file exceeds byte limits")
        digest.update(chunk)
    return digest.hexdigest()


def _timestamp(value: datetime, field: str) -> str:
    if value.tzinfo is None:
        raise ValueError(f"{field} must be timezone-aware")
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _stored_int(value: object) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise VisualEvidenceAuthorityError("authority record integer is invalid")
    return value


def _identifier(value: str, field: str) -> str:
    if not isinstance(value, str) or not _ID.fullmatch(value):
        raise ValueError(f"{field} is not a bounded identifier")
    return value


def _digest(value: str, field: str) -> str:
    if not isinstance(value, str) or not _DIGEST.fullmatch(value):
        raise ValueError(f"{field} is not a SHA-256 digest")
    return value


def _symmetric_key(value: bytes) -> bytes:
    if not isinstance(value, bytes) or len(value) < 32:
        raise ValueError("symmetric key must contain at least 32 bytes")
    return value


def _sign(signing_key: bytes, values: list[object]) -> str:
    if not isinstance(signing_key, bytes) or len(signing_key) != 32:
        raise ValueError("operator_signing_key must be a 32-byte Ed25519 seed")
    return SigningKey(signing_key).sign(_canonical(values)).signature.hex()


def _verify_key(value: bytes) -> VerifyKey:
    if not isinstance(value, bytes) or len(value) != 32:
        raise ValueError("operator_verify_key must be 32 bytes")
    return VerifyKey(value)


def _verify_signature(key: VerifyKey, values: list[object], signature: str) -> None:
    try:
        raw = bytes.fromhex(signature)
        key.verify(_canonical(values), raw)
    except (BadSignatureError, ValueError):
        raise VisualEvidenceAuthorityError("operator evidence signature is invalid") from None


def _canonical(values: list[object]) -> bytes:
    return json.dumps(values, ensure_ascii=True, separators=(",", ":")).encode()


def _hmac(key: bytes, values: list[object]) -> str:
    return hmac.new(key, _canonical(values), hashlib.sha256).hexdigest()


def _record_digest(values: list[object]) -> str:
    return hashlib.sha256(_canonical(values)).hexdigest()


__all__ = [
    "GeneratedVisualAttestation",
    "VisualEvidenceAuthority",
    "VisualEvidenceAuthorityError",
    "VisualRightsDecision",
    "attest_generated_visual",
    "issue_visual_rights_decision",
]
