"""Authenticated Krea locator rematerialization into private quarantine."""

from __future__ import annotations

import hashlib
import hmac
from dataclasses import dataclass
from datetime import datetime
from urllib.parse import urlsplit

from integrations.krea.client import KreaClient
from runtime.db_lock import connect_read

from .artifact_quarantine import Resolver, Transport, quarantine_artifact
from .provider_execution import (
    ProviderExecutionIntegrityError,
    ProviderExecutionStatus,
    _evidence_mac,
    get_provider_execution,
)
from .read_model import MultimediaAssetStore
from .visual_authorization import VisualAuthorizationRegistry, VisualAuthorizationTerms


class VisualCandidateMaterializationError(RuntimeError):
    """Provider results cannot become trusted local candidate bytes."""


@dataclass(frozen=True)
class MaterializedVisualCandidate:
    candidate_id: str
    artifact_receipt_id: str
    media_type: str
    byte_count: int


def materialize_visual_candidates(
    *,
    asset_id: str,
    execution_id: str,
    authority_request_id: str,
    expected_revision_id: str,
    owner_id: str,
    store: MultimediaAssetStore,
    registry: VisualAuthorizationRegistry,
    terms: VisualAuthorizationTerms,
    db_path: str,
    signing_key: bytes,
    client: KreaClient,
    resolver: Resolver,
    transport: Transport,
    allowlisted_hosts: frozenset[str],
    quarantine_dir: str,
    now: datetime,
) -> tuple[MaterializedVisualCandidate, ...]:
    try:
        authority = registry.reopen(
            asset_id=asset_id, request_id=authority_request_id,
            expected_revision_id=expected_revision_id, owner_id=owner_id,
            store=store, terms=terms, now=now,
        )
        execution = get_provider_execution(
            db_path=db_path, execution_id=execution_id, signing_key=signing_key
        )
    except (KeyError, ValueError, ProviderExecutionIntegrityError, RuntimeError) as exc:
        raise VisualCandidateMaterializationError("visual candidate authority is unavailable") from exc
    if (
        execution.operator_id != owner_id or execution.asset_id != asset_id
        or execution.revision_id != expected_revision_id
        or execution.authorization_id != authority.authorization.authorization_id
        or execution.status is not ProviderExecutionStatus.SUCCEEDED
        or execution.provider != "krea" or execution.provider_job_id is None
    ):
        raise VisualCandidateMaterializationError("visual candidate authority conflicts")
    try:
        observation = client.poll(execution.provider_job_id)
    except Exception as exc:
        raise VisualCandidateMaterializationError("visual candidate locator poll failed") from exc
    if (
        observation.job_id != execution.provider_job_id or observation.status != "completed"
        or observation.account_identity_digest != client.account_identity_digest
    ):
        raise VisualCandidateMaterializationError("visual candidate locator authority conflicts")
    rows = _candidate_rows(db_path, execution_id, signing_key)
    if not rows or len(rows) != len(observation.results):
        raise VisualCandidateMaterializationError("visual candidate locator coverage conflicts")
    receipts: list[MaterializedVisualCandidate] = []
    for row, locator in zip(rows, observation.results, strict=True):
        if hashlib.sha256(locator.encode()).hexdigest() != row[3]:
            raise VisualCandidateMaterializationError("visual candidate locator digest conflicts")
        parsed = urlsplit(locator)
        if parsed.scheme != "https" or parsed.hostname not in allowlisted_hosts:
            raise VisualCandidateMaterializationError("visual candidate locator origin is unavailable")
        try:
            receipt = quarantine_artifact(
                db_path=db_path, execution_id=execution_id, candidate_id=str(row[0]),
                url=locator, allowlisted_hosts=allowlisted_hosts, resolver=resolver,
                transport=transport, quarantine_dir=quarantine_dir,
                signing_key=signing_key, now=now,
            )
        except Exception as exc:
            raise VisualCandidateMaterializationError("visual candidate quarantine failed") from exc
        receipts.append(
            MaterializedVisualCandidate(
                candidate_id=receipt.candidate_id,
                artifact_receipt_id=receipt.receipt_id,
                media_type=receipt.media_type,
                byte_count=receipt.byte_count,
            )
        )
    return tuple(receipts)


def _candidate_rows(
    db_path: str, execution_id: str, key: bytes
) -> tuple[tuple[object, ...], ...]:
    try:
        with connect_read(db_path) as connection:
            rows = connection.execute(
                "SELECT candidate_id, execution_id, ordinal, source_locator_digest, "
                "declared_media_type, candidate_mac FROM multimedia_provider_artifact_candidates "
                "WHERE execution_id=? ORDER BY ordinal",
                [execution_id],
            ).fetchall()
    except Exception as exc:
        raise VisualCandidateMaterializationError("visual candidate authority is unavailable") from exc
    for ordinal, row in enumerate(rows):
        if (
            len(row) != 6 or row[1] != execution_id or row[2] != ordinal
            or not isinstance(row[5], str)
            or not hmac.compare_digest(row[5], _evidence_mac(key, list(row[:5])))
        ):
            raise VisualCandidateMaterializationError("visual candidate integrity failed")
    return tuple(rows)


__all__ = [
    "MaterializedVisualCandidate", "VisualCandidateMaterializationError",
    "materialize_visual_candidates",
]
