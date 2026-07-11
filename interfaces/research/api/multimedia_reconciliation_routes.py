"""Mounted operator API for redacted chapter TTS reconciliation."""

from __future__ import annotations

import base64
import binascii
import hashlib
import json
import os
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict

from runtime.db_lock import connect_read
from substrate.multimedia.chapter_tts_production import ChapterTTSProductionError
from substrate.multimedia.execution_authorization import (
    MultimediaExecutionAuthorizationV2,
    verify_async_execution_authorization,
)
from substrate.multimedia.narration_run import NarrationRunError, get_narration_run
from substrate.multimedia.operations import (
    MultimediaExecutionUnavailable,
    MultimediaOperationConflict,
)
from substrate.multimedia.provider_execution import (
    ProviderExecutionIntegrityError,
    get_provider_execution,
)
from substrate.multimedia.provider_recovery_adapter import (
    HttpProviderRecoveryTransport,
    ProviderAccountRecoveryAdapter,
    ProviderRecoveryError,
)
from substrate.multimedia.provider_recovery_adapter import (
    RecoveredProviderAudio as RecoveredChapterAudio,
)
from substrate.multimedia.reconciliation_operations import (
    get_chapter_tts_reconciliation,
    operator_quarantine_stale_send,
    operator_recover_unknown_send,
    operator_release_stale_seal,
)
from substrate.multimedia.reconciliation_read_model import ChapterTTSReconciliationView
from substrate.multimedia.tts_reconciliation import (
    ChapterTTSReconciliationError,
    issue_chapter_tts_recovery_authorization,
)

_AUTHENTICATED_METHODS = frozenset(
    {"antiek_session_cookie", "cloudflare_access_email", "cloudflare_service_token", "bearer_token"}
)
_CONFLICTS = (
    ChapterTTSProductionError,
    ChapterTTSReconciliationError,
    MultimediaOperationConflict,
    ProviderExecutionIntegrityError,
    ValueError,
)
_MAX_ASSET_EXECUTION_LINKS = 64
_MAX_ASSET_RUN_LINKS = 8


@dataclass(frozen=True)
class MultimediaReconciliationRuntime:
    db_path: str
    output_dir: str
    signing_key: bytes
    recovery_key: bytes
    evidence_verification_key: bytes
    authorization_resolver: Callable[[str], MultimediaExecutionAuthorizationV2]
    recovery_evidence_resolver: Callable[[str], RecoveredChapterAudio]
    asset_revision_resolver: Callable[[str, str], str] = (
        lambda asset_id, operator_id: (_ for _ in ()).throw(
            LookupError("multimedia asset is unavailable")
        )
    )
    clock: Callable[[], datetime] = lambda: datetime.now(UTC)
    stale_after: timedelta = timedelta(minutes=5)


class ChapterTTSReconciliationResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    execution_id: str
    asset_id: str
    revision_id: str
    attempt_status: str
    provider_status: str
    next_action: str
    action_eligible: bool
    send_age_seconds: int | None
    seal_age_seconds: int | None
    seal_lease_id: str | None
    charged_cents: int
    full_ceiling_charged: bool
    raw_audio_present: bool
    raw_audio_hash_valid: bool
    requires_signed_operator_authority: bool
    requires_external_provider_evidence: bool
    parent_resume_eligible: bool
    safe_error_code: str | None


class NarrationRunChildResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    chapter_id: str
    execution_id: str
    state: str
    next_action: str
    action_eligible: bool
    reconciliation: ChapterTTSReconciliationResponse | None


class NarrationRunReconciliationResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: str
    asset_id: str
    revision_id: str
    run_status: str
    blocked_chapter_count: int
    parent_resume_eligible: bool
    children: tuple[NarrationRunChildResponse, ...]


class AssetExecutionLinkResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    execution_id: str
    revision_id: str
    provider: str
    status: str
    reconciliation_available: bool


class AssetNarrationRunLinkResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: str
    revision_id: str
    status: str


class AssetReconciliationLinksResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    asset_id: str
    revision_id: str
    executions: tuple[AssetExecutionLinkResponse, ...]
    narration_runs: tuple[AssetNarrationRunLinkResponse, ...]


def get_multimedia_reconciliation_runtime() -> MultimediaReconciliationRuntime:
    raise HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="multimedia reconciliation runtime is unavailable",
    )


def multimedia_reconciliation_runtime_from_environment(
    environ: dict[str, str] | None = None,
) -> MultimediaReconciliationRuntime | None:
    values = os.environ if environ is None else environ
    db_path = values.get("ANTIEK_MULTIMEDIA_RECONCILIATION_DB_PATH", "").strip()
    output_dir = values.get("ANTIEK_MULTIMEDIA_RECONCILIATION_OUTPUT_DIR", "").strip()
    encoded_keys = (
        values.get("ANTIEK_MULTIMEDIA_SIGNING_KEY_B64", "").strip(),
        values.get("ANTIEK_MULTIMEDIA_RECOVERY_KEY_B64", "").strip(),
        values.get("ANTIEK_MULTIMEDIA_EVIDENCE_KEY_B64", "").strip(),
    )
    if not any((db_path, output_dir, *encoded_keys)):
        return None
    if not db_path or not output_dir or not all(encoded_keys):
        raise RuntimeError("multimedia reconciliation configuration is incomplete")
    signing_key, recovery_key, evidence_key = tuple(_decode_key(value) for value in encoded_keys)
    recovery_values = (
        values.get("ANTIEK_MULTIMEDIA_RECOVERY_ENDPOINT", "").strip(),
        values.get("ANTIEK_MULTIMEDIA_RECOVERY_TOKEN", "").strip(),
        values.get("ANTIEK_MULTIMEDIA_RECOVERY_OPERATOR_SHA256", "").strip(),
        values.get("ANTIEK_MULTIMEDIA_RECOVERY_ACCOUNT_SHA256", "").strip(),
        values.get("ANTIEK_MULTIMEDIA_RECOVERY_ALLOWED_HOST", "").strip(),
    )
    if any(recovery_values) and not all(recovery_values):
        raise RuntimeError("multimedia provider recovery configuration is incomplete")
    adapter = None
    if all(recovery_values):
        try:
            adapter = ProviderAccountRecoveryAdapter(
                transport=HttpProviderRecoveryTransport(
                    endpoint=recovery_values[0],
                    bearer_token=recovery_values[1],
                    allowed_host=recovery_values[4],
                ),
                antiek_owner_identity_digest=recovery_values[2],
                account_identity_digest=recovery_values[3],
                evidence_key=evidence_key,
            )
        except ValueError as exc:
            raise RuntimeError("multimedia provider recovery configuration is invalid") from exc

    def resolve_recovery(execution_id: str) -> RecoveredChapterAudio:
        if adapter is None:
            raise LookupError("provider recovery evidence is unavailable")
        execution = get_provider_execution(
            db_path=db_path, execution_id=execution_id, signing_key=signing_key
        )
        try:
            return adapter.resolve(execution, verified_at=datetime.now(UTC))
        except ProviderRecoveryError as exc:
            raise LookupError("provider recovery evidence is unavailable") from exc

    return MultimediaReconciliationRuntime(
        db_path=db_path,
        output_dir=output_dir,
        signing_key=signing_key,
        recovery_key=recovery_key,
        evidence_verification_key=evidence_key,
        authorization_resolver=lambda execution_id: _resolve_issued_authorization(
            db_path=db_path,
            signing_key=signing_key,
            execution_id=execution_id,
        ),
        recovery_evidence_resolver=resolve_recovery,
    )


def authenticated_multimedia_operator(request: Request) -> str:
    method = getattr(request.state, "auth_method", None)
    operator_id = getattr(request.state, "user_id", None)
    if method not in _AUTHENTICATED_METHODS or not isinstance(operator_id, str):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="authentication required")
    operator_id = operator_id.strip()
    if not operator_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="authentication required")
    return operator_id


multimedia_reconciliation_router = APIRouter(tags=["multimedia-reconciliation"])


@multimedia_reconciliation_router.get(
    "/assets/{asset_id}/reconciliation-links",
    response_model=AssetReconciliationLinksResponse,
)
def get_asset_reconciliation_links(
    asset_id: str,
    operator_id: str = Depends(authenticated_multimedia_operator),
    runtime: MultimediaReconciliationRuntime = Depends(get_multimedia_reconciliation_runtime),
) -> AssetReconciliationLinksResponse:
    try:
        revision_id = runtime.asset_revision_resolver(asset_id, operator_id)
        return _asset_links(runtime, asset_id, revision_id, operator_id)
    except (LookupError, MultimediaExecutionUnavailable, ProviderExecutionIntegrityError, NarrationRunError) as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="multimedia asset unavailable") from exc
    except _CONFLICTS as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="reconciliation state conflicts") from exc


@multimedia_reconciliation_router.get(
    "/executions/{execution_id}/tts-reconciliation",
    response_model=ChapterTTSReconciliationResponse,
)
def get_tts_reconciliation(
    execution_id: str,
    operator_id: str = Depends(authenticated_multimedia_operator),
    runtime: MultimediaReconciliationRuntime = Depends(get_multimedia_reconciliation_runtime),
) -> ChapterTTSReconciliationResponse:
    try:
        view = _view(runtime, execution_id, operator_id)
    except MultimediaExecutionUnavailable as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="execution unavailable") from exc
    except _CONFLICTS as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="reconciliation state conflicts") from exc
    return _response(view)


@multimedia_reconciliation_router.post(
    "/executions/{execution_id}/tts-reconciliation/actions/{action}",
    response_model=ChapterTTSReconciliationResponse,
)
def execute_tts_reconciliation_action(
    execution_id: str,
    action: Literal["quarantine_send", "recover_unknown", "release_seal"],
    operator_id: str = Depends(authenticated_multimedia_operator),
    runtime: MultimediaReconciliationRuntime = Depends(get_multimedia_reconciliation_runtime),
) -> ChapterTTSReconciliationResponse:
    now = runtime.clock()
    try:
        current = _view(runtime, execution_id, operator_id, now=now)
        if not current.action_eligible or current.next_action != action:
            raise ValueError("action is not eligible")
        authority = issue_chapter_tts_recovery_authorization(
            recovery_key=runtime.recovery_key,
            operator_id=operator_id,
            execution_id=execution_id,
            action=action,
            lease_id=current.seal_lease_id if action == "release_seal" else None,
            issued_at=now,
            expires_at=now + timedelta(minutes=10),
        )
        if action == "quarantine_send":
            result = operator_quarantine_stale_send(
                authority=authority,
                recovery_key=runtime.recovery_key,
                authenticated_operator_id=operator_id,
                authorization=runtime.authorization_resolver(execution_id),
                signing_key=runtime.signing_key,
                db_path=runtime.db_path,
                now=now,
                stale_after=runtime.stale_after,
            )
        elif action == "recover_unknown":
            evidence = runtime.recovery_evidence_resolver(execution_id)
            result = operator_recover_unknown_send(
                authority=authority,
                recovery_key=runtime.recovery_key,
                authenticated_operator_id=operator_id,
                signing_key=runtime.signing_key,
                db_path=runtime.db_path,
                output_dir=runtime.output_dir,
                provider_request_id=evidence.provider_request_id,
                audio_bytes=evidence.audio_bytes,
                evidence_source=evidence.evidence_source,
                evidence_verification_key=runtime.evidence_verification_key,
                external_signature=evidence.external_signature,
                recorded_at=evidence.recorded_at,
                verified_at=now,
            )
        else:
            result = operator_release_stale_seal(
                authority=authority,
                recovery_key=runtime.recovery_key,
                authenticated_operator_id=operator_id,
                signing_key=runtime.signing_key,
                db_path=runtime.db_path,
                now=now,
                stale_after=runtime.stale_after,
            )
    except MultimediaExecutionUnavailable as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="execution unavailable") from exc
    except LookupError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="required recovery evidence is unavailable",
        ) from exc
    except _CONFLICTS as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="reconciliation action conflicts") from exc
    return _response(result)


@multimedia_reconciliation_router.get(
    "/narration-runs/{run_id}/reconciliation",
    response_model=NarrationRunReconciliationResponse,
)
def get_narration_run_reconciliation(
    run_id: str,
    operator_id: str = Depends(authenticated_multimedia_operator),
    runtime: MultimediaReconciliationRuntime = Depends(get_multimedia_reconciliation_runtime),
) -> NarrationRunReconciliationResponse:
    try:
        run = get_narration_run(db_path=runtime.db_path, run_id=run_id, signing_key=runtime.signing_key)
        bindings = json.loads(run.chapter_bindings_json)
        if not isinstance(bindings, list) or not bindings:
            raise ValueError
        children: list[NarrationRunChildResponse] = []
        for sequence, binding in enumerate(bindings):
            if not isinstance(binding, list) or len(binding) != 4 or not isinstance(binding[0], str):
                raise ValueError
            chapter_id = binding[0]
            revision_id = _child_revision(run.revision_id, chapter_id, sequence)
            execution_id = _owned_child_execution_id(
                runtime, operator_id=operator_id, asset_id=run.asset_id, revision_id=revision_id
            )
            child_view = (
                _response(_view(runtime, execution_id, operator_id))
                if _chapter_attempt_exists(runtime, execution_id)
                else None
            )
            children.append(
                NarrationRunChildResponse(
                    chapter_id=chapter_id,
                    execution_id=execution_id,
                    state=child_view.attempt_status if child_view is not None else "pending",
                    next_action=child_view.next_action if child_view is not None else "wait",
                    action_eligible=child_view.action_eligible if child_view is not None else False,
                    reconciliation=child_view,
                )
            )
    except (NarrationRunError, MultimediaExecutionUnavailable, ValueError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="narration run unavailable") from exc
    blocked = sum(
        child.reconciliation is None or not child.reconciliation.parent_resume_eligible
        for child in children
    )
    return NarrationRunReconciliationResponse(
        run_id=run.run_id,
        asset_id=run.asset_id,
        revision_id=run.revision_id,
        run_status=run.status,
        blocked_chapter_count=blocked,
        parent_resume_eligible=run.status == "admitted" and blocked == 0,
        children=tuple(children),
    )


def _view(
    runtime: MultimediaReconciliationRuntime,
    execution_id: str,
    operator_id: str,
    *,
    now: datetime | None = None,
) -> ChapterTTSReconciliationView:
    return get_chapter_tts_reconciliation(
        db_path=runtime.db_path,
        execution_id=execution_id,
        authenticated_operator_id=operator_id,
        signing_key=runtime.signing_key,
        now=now or runtime.clock(),
        stale_after=runtime.stale_after,
    )


def _response(view: ChapterTTSReconciliationView) -> ChapterTTSReconciliationResponse:
    return ChapterTTSReconciliationResponse(
        **{**view.__dict__, "provider_status": view.provider_status.value}
    )


def _asset_links(
    runtime: MultimediaReconciliationRuntime,
    asset_id: str,
    revision_id: str,
    operator_id: str,
) -> AssetReconciliationLinksResponse:
    if not asset_id or not revision_id:
        raise ValueError("asset identity is invalid")
    allowed_revisions = {revision_id}
    run_links: list[AssetNarrationRunLinkResponse] = []
    with connect_read(runtime.db_path) as connection:
        has_runs = connection.execute(
            "SELECT count(*) FROM information_schema.tables "
            "WHERE table_name='multimedia_narration_runs'"
        ).fetchone()
        run_rows = (
            connection.execute(
                "SELECT run_id FROM multimedia_narration_runs "
                "WHERE asset_id=? AND revision_id=? ORDER BY run_id LIMIT ?",
                [asset_id, revision_id, _MAX_ASSET_RUN_LINKS + 1],
            ).fetchall()
            if has_runs and has_runs[0]
            else []
        )
    if len(run_rows) > _MAX_ASSET_RUN_LINKS:
        raise ValueError("asset narration run linkage exceeds its bound")
    for row in run_rows:
        if not isinstance(row[0], str):
            raise NarrationRunError("narration run identity is invalid")
        run = get_narration_run(
            db_path=runtime.db_path, run_id=row[0], signing_key=runtime.signing_key
        )
        bindings = json.loads(run.chapter_bindings_json)
        if not isinstance(bindings, list) or not bindings:
            raise NarrationRunError("narration run bindings are invalid")
        child_revisions: list[str] = []
        owned = True
        for sequence, binding in enumerate(bindings):
            if not isinstance(binding, list) or len(binding) != 4 or not isinstance(binding[0], str):
                raise NarrationRunError("narration run bindings are invalid")
            child_revision = _child_revision(revision_id, binding[0], sequence)
            try:
                _owned_child_execution_id(
                    runtime,
                    operator_id=operator_id,
                    asset_id=asset_id,
                    revision_id=child_revision,
                )
            except MultimediaExecutionUnavailable:
                owned = False
                break
            child_revisions.append(child_revision)
        if owned:
            allowed_revisions.update(child_revisions)
            run_links.append(
                AssetNarrationRunLinkResponse(
                    run_id=run.run_id,
                    revision_id=run.revision_id,
                    status=run.status,
                )
            )
    with connect_read(runtime.db_path) as connection:
        has_executions = connection.execute(
            "SELECT count(*) FROM information_schema.tables "
            "WHERE table_name='multimedia_provider_executions'"
        ).fetchone()
        execution_rows = (
            connection.execute(
                "SELECT execution_id FROM multimedia_provider_executions "
                "WHERE asset_id=? AND operator_id=? ORDER BY created_at, execution_id LIMIT ?",
                [asset_id, operator_id, _MAX_ASSET_EXECUTION_LINKS + 1],
            ).fetchall()
            if has_executions and has_executions[0]
            else []
        )
    if len(execution_rows) > _MAX_ASSET_EXECUTION_LINKS:
        raise ValueError("asset execution linkage exceeds its bound")
    execution_links: list[AssetExecutionLinkResponse] = []
    for row in execution_rows:
        if not isinstance(row[0], str):
            raise ProviderExecutionIntegrityError("provider execution identity is invalid")
        execution = get_provider_execution(
            db_path=runtime.db_path, execution_id=row[0], signing_key=runtime.signing_key
        )
        if (
            execution.operator_id != operator_id
            or execution.asset_id != asset_id
            or execution.revision_id not in allowed_revisions
        ):
            continue
        execution_links.append(
            AssetExecutionLinkResponse(
                execution_id=execution.execution_id,
                revision_id=execution.revision_id,
                provider=execution.provider,
                status=execution.status.value,
                reconciliation_available=_chapter_attempt_exists(
                    runtime, execution.execution_id
                ),
            )
        )
    return AssetReconciliationLinksResponse(
        asset_id=asset_id,
        revision_id=revision_id,
        executions=tuple(execution_links),
        narration_runs=tuple(run_links),
    )


def _owned_child_execution_id(
    runtime: MultimediaReconciliationRuntime,
    *,
    operator_id: str,
    asset_id: str,
    revision_id: str,
) -> str:
    with connect_read(runtime.db_path) as connection:
        rows = connection.execute(
            "SELECT execution_id, operator_id FROM multimedia_provider_executions "
            "WHERE asset_id=? AND revision_id=? LIMIT 2",
            [asset_id, revision_id],
        ).fetchall()
    if (
        len(rows) != 1
        or not isinstance(rows[0][0], str)
        or rows[0][1] != operator_id
    ):
        raise MultimediaExecutionUnavailable("multimedia execution is unavailable")
    execution = get_provider_execution(
        db_path=runtime.db_path,
        execution_id=rows[0][0],
        signing_key=runtime.signing_key,
    )
    if (
        execution.operator_id != operator_id
        or execution.asset_id != asset_id
        or execution.revision_id != revision_id
    ):
        raise MultimediaExecutionUnavailable("multimedia execution is unavailable")
    return execution.execution_id


def _resolve_issued_authorization(
    *, db_path: str, signing_key: bytes, execution_id: str
) -> MultimediaExecutionAuthorizationV2:
    execution = get_provider_execution(
        db_path=db_path, execution_id=execution_id, signing_key=signing_key
    )
    marker = f'%"authorization_id":"{execution.authorization_id}"%'
    with connect_read(db_path) as connection:
        rows = connection.execute(
            "SELECT receipt_json FROM multimedia_execution_authorization_issues "
            "WHERE receipt_json LIKE ? LIMIT 2",
            [marker],
        ).fetchall()
    if len(rows) != 1 or not isinstance(rows[0][0], str):
        raise LookupError("issued authorization is unavailable")
    try:
        decoded = json.loads(rows[0][0])
        if not isinstance(decoded, dict):
            raise ValueError
        authorization = MultimediaExecutionAuthorizationV2.from_dict(decoded)
        issued_at = datetime.fromisoformat(authorization.issued_at.replace("Z", "+00:00"))
        verify_async_execution_authorization(
            authorization,
            signing_key=signing_key,
            operator_id=execution.operator_id,
            asset_id=execution.asset_id,
            revision_id=execution.revision_id,
            provider=execution.provider,
            route_policy=execution.route_policy,
            model=execution.model,
            endpoint_capability=execution.endpoint_capability,
            catalog_version=execution.catalog_version,
            catalog_digest=execution.catalog_digest,
            quote_id=execution.quote_id,
            recovery_authority_id=execution.recovery_authority_id,
            recovery_verification_key_digest=execution.recovery_verification_key_digest,
            approved_ceiling_microdollars=execution.approved_ceiling_microdollars,
            request_body_digest=execution.request_body_digest,
            now=issued_at,
        )
    except Exception as exc:
        if isinstance(exc, (KeyboardInterrupt, SystemExit)):
            raise
        raise LookupError("issued authorization is unavailable") from None
    if authorization.authorization_id != execution.authorization_id:
        raise LookupError("issued authorization is unavailable")
    return authorization


def _decode_key(value: str) -> bytes:
    try:
        decoded = base64.b64decode(value, validate=True)
    except (ValueError, binascii.Error):
        raise RuntimeError("multimedia reconciliation key is invalid") from None
    if len(decoded) < 32:
        raise RuntimeError("multimedia reconciliation key is invalid")
    return decoded


def _chapter_attempt_exists(runtime: MultimediaReconciliationRuntime, execution_id: str) -> bool:
    with connect_read(runtime.db_path) as connection:
        table = connection.execute(
            "SELECT count(*) FROM information_schema.tables "
            "WHERE table_name='multimedia_chapter_tts_attempts'"
        ).fetchone()
        if table is None or not table[0]:
            return False
        row = connection.execute(
            "SELECT count(*) FROM multimedia_chapter_tts_attempts WHERE execution_id=?",
            [execution_id],
        ).fetchone()
    return bool(row and row[0] == 1)


def _child_revision(parent_revision: str, chapter_id: str, sequence: int) -> str:
    digest = hashlib.sha256(
        json.dumps([parent_revision, chapter_id, sequence], separators=(",", ":")).encode()
    ).hexdigest()[:32]
    return f"tts-{digest}"


__all__ = [
    "AssetReconciliationLinksResponse",
    "MultimediaReconciliationRuntime",
    "RecoveredChapterAudio",
    "authenticated_multimedia_operator",
    "get_multimedia_reconciliation_runtime",
    "multimedia_reconciliation_runtime_from_environment",
    "multimedia_reconciliation_router",
]
