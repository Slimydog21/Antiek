from __future__ import annotations

import hashlib
import io
import wave
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

import substrate.multimedia.chapter_tts_production as chapter_module
from substrate.contracts.multimedia import ScriptLine
from substrate.multimedia.chapter_tts_production import (
    ChapterTTSSynthesisResult,
    PreparedChapterTTSRequest,
    get_chapter_tts_attempt,
    prepare_chapter_tts_request,
    produce_chapter_narration,
)
from substrate.multimedia.execution_authorization import (
    MultimediaExecutionAuthorizationV2,
    issue_async_execution_authorization,
)
from substrate.multimedia.planner import ChapterPlan, MultimediaPlan, MultimediaPlanRequest
from substrate.multimedia.provider_execution import (
    ProviderExecutionStatus,
    get_provider_execution,
)
from substrate.multimedia.tts_reconciliation import (
    ChapterTTSReconciliationError,
    issue_chapter_tts_recovery_authorization,
    quarantine_stale_send,
    recover_unknown_send,
    release_stale_seal,
    sign_provider_recovery_evidence,
)

KEY = b"tts-reconciliation-signing-key-32b"
RECOVERY_KEY = b"operator-recovery-authorization-key!"
EVIDENCE_KEY = b"provider-evidence-verification-key!"
INTEGRITY_KEY = b"tts-reconciliation-integrity-key!"
NOW = datetime(2026, 7, 11, 19, 0, tzinfo=UTC)
CATALOG = hashlib.sha256(b"catalog").hexdigest()
EVIDENCE_DIGEST = hashlib.sha256(EVIDENCE_KEY).hexdigest()


class ProcessCrash(BaseException):
    pass


def _plan() -> MultimediaPlan:
    return MultimediaPlan(
        request=MultimediaPlanRequest(topic="Aircraft", target_minutes=15),
        suggestions=(),
        chosen_arc_ids=(),
        chapters=(
            ChapterPlan(
                chapter_id="chapter-0",
                title="Chapter 0",
                minutes=15,
                purpose="Explain evidence",
                arc_id="arc-0",
                source_chunk_ids=("chunk-0",),
            ),
        ),
        script_lines=(
            ScriptLine(
                line_id="chapter-0-line-0",
                sequence=0,
                text="Grounded narration.",
                kind="narration",
            ),
        ),
        scenes=(),
        unsourced_line_ids=(),
    )


def _prepared() -> PreparedChapterTTSRequest:
    return prepare_chapter_tts_request(
        _plan(),
        asset_id="asset-1",
        revision_id="revision-1",
        provider="openai",
        model="gpt-4o-mini-tts",
        voice="alloy",
        sample_rate_hz=8_000,
    )


def _authorization(prepared: PreparedChapterTTSRequest) -> MultimediaExecutionAuthorizationV2:
    return issue_async_execution_authorization(
        signing_key=KEY,
        request_id="tts-approval-1",
        operator_id="operator-1",
        asset_id=prepared.asset_id,
        revision_id=prepared.revision_id,
        provider=prepared.provider,
        route_policy=prepared.route_policy,
        model=prepared.model,
        endpoint_capability=prepared.endpoint_capability,
        catalog_version="catalog-1",
        catalog_digest=CATALOG,
        quote_id="quote-1",
        quote_expires_at=NOW + timedelta(hours=1),
        recovery_authority_id="recovery-1",
        recovery_verification_key_digest=EVIDENCE_DIGEST,
        approved_ceiling_microdollars=20_000,
        request_body_digest=prepared.body_digest,
        issued_at=NOW,
        expires_at=NOW + timedelta(hours=1),
    )


def _execution_id(authorization: MultimediaExecutionAuthorizationV2) -> str:
    return "mmexec_" + hashlib.sha256(
        f"{authorization.authorization_id}:{authorization.request_body_digest}".encode()
    ).hexdigest()


def _wav() -> bytes:
    output = io.BytesIO()
    with wave.open(output, "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(8_000)
        audio.writeframes((100).to_bytes(2, "little", signed=True) * 8_000)
    return output.getvalue()


def _produce_values(tmp_path: Path):
    output = tmp_path / "output"
    output.mkdir(mode=0o700)
    prepared = _prepared()
    authorization = _authorization(prepared)
    return {
        "plan": _plan(),
        "prepared": prepared,
        "authorization": authorization,
        "signing_key": KEY,
        "integrity_key": INTEGRITY_KEY,
        "operator_id": "operator-1",
        "catalog_version": authorization.catalog_version,
        "catalog_digest": authorization.catalog_digest,
        "quote_id": authorization.quote_id,
        "recovery_authority_id": authorization.recovery_authority_id,
        "recovery_verification_key_digest": authorization.recovery_verification_key_digest,
        "approved_ceiling_microdollars": authorization.approved_ceiling_microdollars,
        "db_path": str(tmp_path / "tts.duckdb"),
        "output_dir": str(output),
        "now": NOW,
    }, prepared, authorization


def _recovery(execution_id: str, action: str, now: datetime):
    return issue_chapter_tts_recovery_authorization(
        recovery_key=RECOVERY_KEY,
        operator_id="operator-1",
        execution_id=execution_id,
        action=action,  # type: ignore[arg-type]
        issued_at=now - timedelta(minutes=1),
        expires_at=now + timedelta(minutes=10),
    )


def test_stale_send_quarantines_then_recovers_authenticated_bytes(tmp_path: Path) -> None:
    values, prepared, authorization = _produce_values(tmp_path)
    execution_id = _execution_id(authorization)

    def crash(request: PreparedChapterTTSRequest) -> ChapterTTSSynthesisResult:
        raise ProcessCrash()

    with pytest.raises(ProcessCrash):
        produce_chapter_narration(**values, synthesize=crash)  # type: ignore[arg-type]
    attempt = get_chapter_tts_attempt(
        db_path=str(values["db_path"]), execution_id=execution_id, signing_key=KEY
    )
    assert attempt.status == "sending"

    with pytest.raises(Exception, match="not stale"):
        quarantine_stale_send(
            authority=_recovery(execution_id, "quarantine_send", NOW + timedelta(minutes=1)),
            recovery_key=RECOVERY_KEY,
            operator_id="operator-1",
            authorization=authorization,
            signing_key=KEY,
            db_path=str(values["db_path"]),
            now=NOW + timedelta(minutes=1),
        )

    recovered_at = NOW + timedelta(minutes=10)
    quarantined = quarantine_stale_send(
        authority=_recovery(execution_id, "quarantine_send", recovered_at),
        recovery_key=RECOVERY_KEY,
        operator_id="operator-1",
        authorization=authorization,
        signing_key=KEY,
        db_path=str(values["db_path"]),
        now=recovered_at,
    )
    assert quarantined.status == "outcome_unknown"
    from runtime.db_lock import FlockWriteCoordinator

    with FlockWriteCoordinator(str(values["db_path"])).acquire_write_context(
        "test.recovery_budget"
    ) as connection:
        hold_state = connection.execute(
            "SELECT state FROM midnight_oil_call_holds WHERE hold_id = ?",
            [quarantined.hold_id],
        ).fetchone()
        spent = connection.execute(
            "SELECT spent_cents FROM midnight_oil_reservations WHERE run_id = ?",
            [authorization.authorization_id],
        ).fetchone()
    assert hold_state == ("settled",)
    assert spent == (2,)

    audio = _wav()
    provider_request_id = "provider-recovered-1"
    signature = sign_provider_recovery_evidence(
        evidence_key=EVIDENCE_KEY,
        execution_id=execution_id,
        provider_request_id=provider_request_id,
        evidence_source="recovery-1",
        audio_bytes=audio,
        recorded_at=recovered_at,
    )
    received = recover_unknown_send(
        authority=_recovery(execution_id, "recover_unknown", recovered_at),
        recovery_key=RECOVERY_KEY,
        operator_id="operator-1",
        signing_key=KEY,
        db_path=str(values["db_path"]),
        output_dir=str(values["output_dir"]),
        provider_request_id=provider_request_id,
        audio_bytes=audio,
        evidence_source="recovery-1",
        evidence_verification_key=EVIDENCE_KEY,
        external_signature=signature,
        recorded_at=recovered_at,
    )
    assert received.status == "received"
    execution = get_provider_execution(
        db_path=str(values["db_path"]), execution_id=execution_id, signing_key=KEY
    )
    assert execution.status is ProviderExecutionStatus.SUCCEEDED
    replay = recover_unknown_send(
        authority=_recovery(execution_id, "recover_unknown", recovered_at),
        recovery_key=RECOVERY_KEY,
        operator_id="operator-1",
        signing_key=KEY,
        db_path=str(values["db_path"]),
        output_dir=str(values["output_dir"]),
        provider_request_id=provider_request_id,
        audio_bytes=audio,
        evidence_source="recovery-1",
        evidence_verification_key=EVIDENCE_KEY,
        external_signature=signature,
        recorded_at=recovered_at,
    )
    assert replay == received
    with pytest.raises(Exception, match="conflicts"):
        recover_unknown_send(
            authority=_recovery(execution_id, "recover_unknown", recovered_at),
            recovery_key=RECOVERY_KEY,
            operator_id="operator-1",
            signing_key=KEY,
            db_path=str(values["db_path"]),
            output_dir=str(values["output_dir"]),
            provider_request_id="different-job",
            audio_bytes=audio,
            evidence_source="recovery-1",
            evidence_verification_key=EVIDENCE_KEY,
            external_signature=signature,
            recorded_at=recovered_at,
        )

    calls: list[int] = []
    artifact = produce_chapter_narration(
        **{**values, "now": recovered_at},
        synthesize=lambda request: (
            calls.append(1)
            or ChapterTTSSynthesisResult(_wav(), "must-not-run")
        ),
    )  # type: ignore[arg-type]
    assert artifact.manifest.duration_seconds == 1.0
    assert calls == []


def test_stale_local_seal_releases_without_provider_retry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    values, _, authorization = _produce_values(tmp_path)
    execution_id = _execution_id(authorization)
    calls: list[int] = []

    def synthesize(request: PreparedChapterTTSRequest) -> ChapterTTSSynthesisResult:
        calls.append(1)
        return ChapterTTSSynthesisResult(_wav(), "provider-seal-crash")

    original_run = chapter_module._run
    monkeypatch.setattr(
        chapter_module,
        "_run",
        lambda *args, **kwargs: (_ for _ in ()).throw(ProcessCrash()),
    )
    with pytest.raises(ProcessCrash):
        produce_chapter_narration(**values, synthesize=synthesize)  # type: ignore[arg-type]
    attempt = get_chapter_tts_attempt(
        db_path=str(values["db_path"]), execution_id=execution_id, signing_key=KEY
    )
    assert attempt.status == "sealing"

    reset = release_stale_seal(
        authority=_recovery(execution_id, "release_seal", NOW + timedelta(minutes=1)),
        recovery_key=RECOVERY_KEY,
        operator_id="operator-1",
        signing_key=KEY,
        db_path=str(values["db_path"]),
        now=NOW + timedelta(minutes=1),
    )
    assert reset.status == "received"
    monkeypatch.setattr(chapter_module, "_run", original_run)
    artifact = produce_chapter_narration(
        **{**values, "now": NOW + timedelta(minutes=1)}, synthesize=synthesize
    )  # type: ignore[arg-type]
    assert artifact.manifest.duration_seconds == 1.0
    assert calls == [1]


def test_recovery_authority_rejects_tamper_wrong_action_and_expiry() -> None:
    execution_id = "mmexec_" + "a" * 64
    authority = _recovery(execution_id, "release_seal", NOW)
    with pytest.raises(ChapterTTSReconciliationError, match="signature"):
        release_stale_seal(
            authority=replace(authority, operator_id="attacker"),
            recovery_key=RECOVERY_KEY,
            operator_id="attacker",
            signing_key=KEY,
            db_path="/tmp/not-used.duckdb",
            now=NOW,
        )
    with pytest.raises(ChapterTTSReconciliationError, match="action"):
        quarantine_stale_send(
            authority=authority,
            recovery_key=RECOVERY_KEY,
            operator_id="operator-1",
            authorization=_authorization(_prepared()),
            signing_key=KEY,
            db_path="/tmp/not-used.duckdb",
            now=NOW,
        )
    with pytest.raises(ChapterTTSReconciliationError, match="not active"):
        release_stale_seal(
            authority=authority,
            recovery_key=RECOVERY_KEY,
            operator_id="operator-1",
            signing_key=KEY,
            db_path="/tmp/not-used.duckdb",
            now=NOW + timedelta(hours=1),
        )


def test_forged_provider_evidence_cannot_recover_unknown(tmp_path: Path) -> None:
    values, prepared, authorization = _produce_values(tmp_path)
    execution_id = _execution_id(authorization)
    with pytest.raises(ProcessCrash):
        produce_chapter_narration(
            **values,
            synthesize=lambda request: (_ for _ in ()).throw(ProcessCrash()),
        )  # type: ignore[arg-type]
    recovered_at = NOW + timedelta(minutes=10)
    quarantine_stale_send(
        authority=_recovery(execution_id, "quarantine_send", recovered_at),
        recovery_key=RECOVERY_KEY,
        operator_id="operator-1",
        authorization=authorization,
        signing_key=KEY,
        db_path=str(values["db_path"]),
        now=recovered_at,
    )
    with pytest.raises(Exception, match="signature"):
        recover_unknown_send(
            authority=_recovery(execution_id, "recover_unknown", recovered_at),
            recovery_key=RECOVERY_KEY,
            operator_id="operator-1",
            signing_key=KEY,
            db_path=str(values["db_path"]),
            output_dir=str(values["output_dir"]),
            provider_request_id="forged-job",
            audio_bytes=_wav(),
            evidence_source="recovery-1",
            evidence_verification_key=EVIDENCE_KEY,
            external_signature="0" * 64,
            recorded_at=recovered_at,
        )
