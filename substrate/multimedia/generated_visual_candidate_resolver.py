"""Resolve a generated visual through its complete durable authority chain."""

from __future__ import annotations

import hmac

from runtime.db_lock import connect_read

from .artifact_quarantine import ArtifactQuarantineError, reopen_quarantined_artifact
from .provider_execution import (
    ProviderExecutionIntegrityError,
    ProviderExecutionStatus,
    _evidence_mac,
    get_provider_execution,
)
from .read_model import MultimediaAssetRecord
from .visual_authorization import VisualAuthorizationError, VisualAuthorizationRegistry
from .visual_evidence_authority import VisualEvidenceAuthority, VisualEvidenceAuthorityError
from .visual_selection import ReviewedVisualSelection


class GeneratedVisualCandidateError(LookupError):
    """A candidate is absent or fails its signed authority chain."""


class GeneratedVisualCandidateResolver:
    def __init__(
        self,
        *,
        execution_db_path: str,
        execution_signing_key: bytes,
        authorization_registry: VisualAuthorizationRegistry,
        evidence_authority: VisualEvidenceAuthority,
    ) -> None:
        if not execution_db_path or len(execution_signing_key) < 32:
            raise ValueError("generated visual candidate resolver configuration is invalid")
        self._db_path = execution_db_path
        self._key = execution_signing_key
        self._authorizations = authorization_registry
        self._evidence = evidence_authority

    def __call__(
        self,
        record: MultimediaAssetRecord,
        owner_id: str,
        chapter_id: str,
        candidate_id: str,
    ) -> ReviewedVisualSelection:
        try:
            with connect_read(self._db_path) as connection:
                row = connection.execute(
                    "SELECT candidate_id, execution_id, ordinal, source_locator_digest, "
                    "declared_media_type, candidate_mac "
                    "FROM multimedia_provider_artifact_candidates WHERE candidate_id=?",
                    [candidate_id],
                ).fetchone()
            if row is None or len(row) != 6 or not isinstance(row[5], str):
                raise GeneratedVisualCandidateError("candidate is unavailable")
            if not hmac.compare_digest(row[5], _evidence_mac(self._key, list(row[:5]))):
                raise GeneratedVisualCandidateError("candidate is unavailable")
            execution = get_provider_execution(
                db_path=self._db_path, execution_id=str(row[1]), signing_key=self._key
            )
            if (
                execution.status is not ProviderExecutionStatus.SUCCEEDED
                or execution.operator_id != owner_id
                or execution.asset_id != record.asset.asset_id
                or execution.revision_id != record.asset.revision_id
            ):
                raise GeneratedVisualCandidateError("candidate is unavailable")
            binding = self._authorizations.resolve_binding(
                authorization_id=execution.authorization_id,
                owner_id=owner_id,
                asset_id=record.asset.asset_id,
                revision_id=record.asset.revision_id,
            )
            if binding.chapter_id != chapter_id:
                raise GeneratedVisualCandidateError("candidate is unavailable")
            chapter = next(
                row for row in record.plan.chapters if row.chapter_id == chapter_id
            )
            scene = next(row for row in record.plan.scenes if row.scene_id == binding.scene_id)
            if scene.chapter_id != chapter_id or tuple(scene.source_chunk_ids) != tuple(
                chapter.source_chunk_ids
            ):
                raise GeneratedVisualCandidateError("candidate is unavailable")
            receipt = reopen_quarantined_artifact(
                db_path=self._db_path, candidate_id=candidate_id, signing_key=self._key
            )
            if receipt.execution_id != execution.execution_id or receipt.media_type not in {
                "image/png",
                "image/jpeg",
            }:
                raise GeneratedVisualCandidateError("candidate is unavailable")
            selection = ReviewedVisualSelection(
                scene_id=binding.scene_id,
                path=receipt.quarantine_path,
                expected_sha256=receipt.sha256,
                visual_label="generated",
                source_chunk_ids=chapter.source_chunk_ids,
                execution_receipt_id=execution.execution_id,
                artifact_receipt_id=receipt.receipt_id,
            )
            self._evidence(selection, receipt.sha256)
            return selection
        except GeneratedVisualCandidateError:
            raise
        except (
            ArtifactQuarantineError,
            ProviderExecutionIntegrityError,
            StopIteration,
            VisualAuthorizationError,
            VisualEvidenceAuthorityError,
        ) as exc:
            raise GeneratedVisualCandidateError("candidate is unavailable") from exc
        except Exception as exc:
            raise RuntimeError("generated visual candidate authority is unavailable") from exc


__all__ = ["GeneratedVisualCandidateError", "GeneratedVisualCandidateResolver"]
