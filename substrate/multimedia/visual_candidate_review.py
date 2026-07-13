"""Owner-bound preview and explicit generated-provenance attestation."""

from __future__ import annotations

import hashlib
import os
import stat
from dataclasses import dataclass
from datetime import datetime

from .artifact_quarantine import ArtifactQuarantineReceipt, reopen_quarantined_artifact
from .provider_execution import ProviderExecutionIntegrityError, get_provider_execution
from .read_model import MultimediaAssetStore
from .visual_evidence_authority import (
    VisualEvidenceAuthorityError,
    attest_generated_visual,
)


class VisualCandidateReviewError(RuntimeError):
    """Candidate bytes or generated provenance cannot be safely reviewed."""


@dataclass(frozen=True)
class VisualCandidatePreview:
    candidate_id: str
    media_type: str
    content: bytes


@dataclass(frozen=True)
class VisualCandidateAttestation:
    artifact_receipt_id: str
    reviewer_id: str
    attested_at: str


def preview_visual_candidate(
    *,
    asset_id: str,
    candidate_id: str,
    expected_revision_id: str,
    owner_id: str,
    store: MultimediaAssetStore,
    db_path: str,
    quarantine_signing_key: bytes,
) -> VisualCandidatePreview:
    receipt = _authorized_receipt(
        asset_id=asset_id, candidate_id=candidate_id,
        expected_revision_id=expected_revision_id, owner_id=owner_id,
        store=store, db_path=db_path, quarantine_signing_key=quarantine_signing_key,
    )
    content = _read_verified(receipt.quarantine_path)
    if (
        len(content) != receipt.byte_count
        or hashlib.sha256(content).hexdigest() != receipt.sha256
    ):
        raise VisualCandidateReviewError("visual candidate bytes conflict")
    return VisualCandidatePreview(candidate_id, receipt.media_type, content)


def attest_visual_candidate(
    *,
    asset_id: str,
    candidate_id: str,
    expected_revision_id: str,
    owner_id: str,
    operator_acknowledged_generated_provenance: bool,
    store: MultimediaAssetStore,
    db_path: str,
    quarantine_signing_key: bytes,
    operator_signing_key: bytes,
    now: datetime,
) -> VisualCandidateAttestation:
    if not operator_acknowledged_generated_provenance:
        raise VisualCandidateReviewError("generated provenance acknowledgement is required")
    receipt = _authorized_receipt(
        asset_id=asset_id, candidate_id=candidate_id,
        expected_revision_id=expected_revision_id, owner_id=owner_id,
        store=store, db_path=db_path, quarantine_signing_key=quarantine_signing_key,
    )
    try:
        attestation = attest_generated_visual(
            db_path=db_path, receipt_id=receipt.receipt_id, reviewer_id=owner_id,
            quarantine_signing_key=quarantine_signing_key,
            operator_signing_key=operator_signing_key, attested_at=now,
        )
    except (VisualEvidenceAuthorityError, ValueError) as exc:
        raise VisualCandidateReviewError("generated visual attestation failed") from exc
    return VisualCandidateAttestation(
        artifact_receipt_id=attestation.receipt_id,
        reviewer_id=attestation.reviewer_id,
        attested_at=attestation.attested_at,
    )


def _authorized_receipt(
    *,
    asset_id: str,
    candidate_id: str,
    expected_revision_id: str,
    owner_id: str,
    store: MultimediaAssetStore,
    db_path: str,
    quarantine_signing_key: bytes,
) -> ArtifactQuarantineReceipt:
    try:
        record = store.get(asset_id, owner_id=owner_id)
        receipt = reopen_quarantined_artifact(
            db_path=db_path, candidate_id=candidate_id,
            signing_key=quarantine_signing_key,
        )
        execution = get_provider_execution(
            db_path=db_path, execution_id=receipt.execution_id,
            signing_key=quarantine_signing_key,
        )
    except (KeyError, ValueError, RuntimeError, ProviderExecutionIntegrityError) as exc:
        raise VisualCandidateReviewError("visual candidate is unavailable") from exc
    if (
        record.asset.revision_id != expected_revision_id
        or execution.operator_id != owner_id or execution.asset_id != asset_id
        or execution.revision_id != expected_revision_id
        or receipt.candidate_id != candidate_id
    ):
        raise VisualCandidateReviewError("visual candidate authority conflicts")
    return receipt


def _read_verified(path_value: str) -> bytes:
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(path_value, flags)
    except OSError:
        raise VisualCandidateReviewError("visual candidate bytes are unavailable") from None
    try:
        metadata = os.fstat(fd)
        if (
            not stat.S_ISREG(metadata.st_mode) or metadata.st_uid != os.getuid()
            or stat.S_IMODE(metadata.st_mode) != 0o600
            or metadata.st_size < 1 or metadata.st_size > 100 * 1024 * 1024
        ):
            raise VisualCandidateReviewError("visual candidate bytes are unavailable")
        chunks: list[bytes] = []
        while chunk := os.read(fd, 1024 * 1024):
            chunks.append(chunk)
        return b"".join(chunks)
    finally:
        os.close(fd)


__all__ = [
    "VisualCandidateAttestation", "VisualCandidatePreview", "VisualCandidateReviewError",
    "attest_visual_candidate", "preview_visual_candidate",
]
