"""Owner-bound composition of exact visual authority and Krea execution."""

from __future__ import annotations

import hmac
from dataclasses import dataclass
from datetime import datetime

from integrations.krea.client import KreaClient
from runtime.db_lock import connect_read

from .krea_reconcile import observe_provider_job
from .krea_submit import submit_krea_job
from .provider_execution import (
    ProviderExecutionIntegrityError,
    ProviderExecutionRecord,
    _evidence_mac,
    get_provider_execution,
)
from .read_model import MultimediaAssetStore
from .visual_authorization import VisualAuthorizationRegistry, VisualAuthorizationTerms


class VisualGenerationError(RuntimeError):
    """The visual execution is unavailable, stale, or conflicting."""


@dataclass(frozen=True)
class VisualGenerationResult:
    execution_id: str
    authorization_id: str
    provider_job_id: str | None
    status: str
    candidate_count: int


def submit_visual_generation(
    *,
    asset_id: str,
    request_id: str,
    expected_revision_id: str,
    owner_id: str,
    store: MultimediaAssetStore,
    registry: VisualAuthorizationRegistry,
    terms: VisualAuthorizationTerms,
    db_path: str,
    signing_key: bytes,
    client: KreaClient,
    now: datetime,
) -> VisualGenerationResult:
    authority = registry.reopen(
        asset_id=asset_id, request_id=request_id,
        expected_revision_id=expected_revision_id, owner_id=owner_id,
        store=store, terms=terms, now=now,
    )
    execution = submit_krea_job(
        db_path=db_path, authorization=authority.authorization,
        signing_key=signing_key, now=now, request=authority.provider_request,
        quote=authority.quote, client=client,
    )
    return _result(execution, db_path=db_path, signing_key=signing_key)


def poll_visual_generation(
    *,
    asset_id: str,
    execution_id: str,
    expected_revision_id: str,
    owner_id: str,
    store: MultimediaAssetStore,
    db_path: str,
    signing_key: bytes,
    client: KreaClient,
    now: datetime,
) -> VisualGenerationResult:
    try:
        record = store.get(asset_id, owner_id=owner_id)
        execution = get_provider_execution(
            db_path=db_path, execution_id=execution_id, signing_key=signing_key
        )
    except (KeyError, ValueError, ProviderExecutionIntegrityError) as exc:
        raise VisualGenerationError("visual generation is unavailable") from exc
    if (
        record.asset.revision_id != expected_revision_id
        or execution.operator_id != owner_id
        or execution.asset_id != asset_id
        or execution.revision_id != expected_revision_id
    ):
        raise VisualGenerationError("visual generation authority conflicts")
    try:
        observed = observe_provider_job(
            db_path=db_path, execution_id=execution_id, client=client,
            signing_key=signing_key, observed_at=now,
        )
    except (ProviderExecutionIntegrityError, RuntimeError, ValueError) as exc:
        raise VisualGenerationError("visual generation observation failed") from exc
    return _result(observed, db_path=db_path, signing_key=signing_key)


def _result(
    execution: ProviderExecutionRecord, *, db_path: str, signing_key: bytes
) -> VisualGenerationResult:
    count = 0
    try:
        with connect_read(db_path) as connection:
            rows = connection.execute(
                "SELECT candidate_id, execution_id, ordinal, source_locator_digest, "
                "declared_media_type, candidate_mac FROM multimedia_provider_artifact_candidates "
                "WHERE execution_id=? ORDER BY ordinal",
                [execution.execution_id],
            ).fetchall()
    except Exception as exc:
        raise VisualGenerationError("visual candidate authority is unavailable") from exc
    for row in rows:
        if len(row) != 6 or not isinstance(row[5], str) or not hmac.compare_digest(
            row[5], _evidence_mac(signing_key, list(row[:5]))
        ):
            raise VisualGenerationError("visual candidate integrity failed")
        count += 1
    return VisualGenerationResult(
        execution_id=execution.execution_id,
        authorization_id=execution.authorization_id,
        provider_job_id=execution.provider_job_id,
        status=execution.status.value,
        candidate_count=count,
    )


__all__ = [
    "VisualGenerationError", "VisualGenerationResult", "poll_visual_generation",
    "submit_visual_generation",
]
