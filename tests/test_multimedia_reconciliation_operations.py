from __future__ import annotations

from dataclasses import asdict
from datetime import timedelta
from pathlib import Path

import pytest

import substrate.multimedia.chapter_tts_production as chapter_module
from runtime.db_lock import FlockWriteCoordinator
from substrate.multimedia.chapter_tts_production import produce_chapter_narration
from substrate.multimedia.operations import MultimediaExecutionUnavailable
from substrate.multimedia.reconciliation_operations import (
    get_chapter_tts_reconciliation,
    operator_quarantine_stale_send,
    operator_recover_unknown_send,
    operator_release_stale_seal,
)
from substrate.multimedia.tts_reconciliation import sign_provider_recovery_evidence
from tests.test_multimedia_tts_reconciliation import (
    EVIDENCE_KEY,
    KEY,
    NOW,
    RECOVERY_KEY,
    ProcessCrash,
    _execution_id,
    _produce_values,
    _recovery,
    _wav,
)


def _crashed_send(tmp_path: Path):
    values, _, authorization = _produce_values(tmp_path)
    with pytest.raises(ProcessCrash):
        produce_chapter_narration(
            **values,
            synthesize=lambda request: (_ for _ in ()).throw(ProcessCrash()),
        )  # type: ignore[arg-type]
    return values, authorization, _execution_id(authorization)


def test_status_redacts_secrets_and_enforces_ownership(tmp_path: Path) -> None:
    values, _, execution_id = _crashed_send(tmp_path)
    view = get_chapter_tts_reconciliation(
        db_path=str(values["db_path"]), execution_id=execution_id,
        authenticated_operator_id="operator-1", signing_key=KEY, now=NOW,
    )
    assert view.next_action == "wait"
    assert view.action_eligible is False
    stale = get_chapter_tts_reconciliation(
        db_path=str(values["db_path"]), execution_id=execution_id,
        authenticated_operator_id="operator-1", signing_key=KEY,
        now=NOW + timedelta(minutes=5),
    )
    assert stale.next_action == "quarantine_send"
    assert stale.action_eligible is True
    projected = repr(asdict(view))
    assert str(values["output_dir"]) not in projected
    assert "signature" not in projected and "recovery_key" not in projected
    with pytest.raises(MultimediaExecutionUnavailable):
        get_chapter_tts_reconciliation(
            db_path=str(values["db_path"]), execution_id=execution_id,
            authenticated_operator_id="operator-2", signing_key=KEY, now=NOW,
        )


def test_operator_flow_projects_charge_evidence_and_resume(tmp_path: Path) -> None:
    values, authorization, execution_id = _crashed_send(tmp_path)
    recovered_at = NOW + timedelta(minutes=10)
    quarantined = operator_quarantine_stale_send(
        authority=_recovery(execution_id, "quarantine_send", recovered_at),
        recovery_key=RECOVERY_KEY, authenticated_operator_id="operator-1",
        authorization=authorization, signing_key=KEY,
        db_path=str(values["db_path"]), now=recovered_at,
    )
    assert quarantined.next_action == "recover_unknown"
    assert quarantined.full_ceiling_charged is True
    assert quarantined.requires_external_provider_evidence is True

    audio = _wav()
    provider_request_id = "operator-recovery-job"
    signature = sign_provider_recovery_evidence(
        evidence_key=EVIDENCE_KEY, execution_id=execution_id,
        provider_request_id=provider_request_id, evidence_source="recovery-1",
        audio_bytes=audio, recorded_at=recovered_at,
    )
    received = operator_recover_unknown_send(
        authority=_recovery(execution_id, "recover_unknown", recovered_at),
        recovery_key=RECOVERY_KEY, authenticated_operator_id="operator-1",
        signing_key=KEY, db_path=str(values["db_path"]),
        output_dir=str(values["output_dir"]), provider_request_id=provider_request_id,
        audio_bytes=audio, evidence_source="recovery-1",
        evidence_verification_key=EVIDENCE_KEY, external_signature=signature,
        recorded_at=recovered_at,
    )
    assert received.next_action == "resume_narration"
    assert received.parent_resume_eligible is True
    assert received.raw_audio_present is True
    assert received.raw_audio_hash_valid is True

    private_audio = next((Path(str(values["output_dir"])) / ".chapter-tts-receipts").iterdir())
    private_audio.write_bytes(b"corrupt")
    corrupted = get_chapter_tts_reconciliation(
        db_path=str(values["db_path"]), execution_id=execution_id,
        authenticated_operator_id="operator-1", signing_key=KEY, now=recovered_at,
    )
    assert corrupted.raw_audio_hash_valid is False
    assert corrupted.safe_error_code == "raw_audio_invalid"
    assert corrupted.parent_resume_eligible is False
    assert corrupted.action_eligible is False


def test_wrong_operator_command_fails_before_mutation(tmp_path: Path) -> None:
    values, authorization, execution_id = _crashed_send(tmp_path)
    recovered_at = NOW + timedelta(minutes=10)
    with pytest.raises(MultimediaExecutionUnavailable):
        operator_quarantine_stale_send(
            authority=_recovery(execution_id, "quarantine_send", recovered_at),
            recovery_key=RECOVERY_KEY, authenticated_operator_id="operator-2",
            authorization=authorization, signing_key=KEY,
            db_path=str(values["db_path"]), now=recovered_at,
        )
    view = get_chapter_tts_reconciliation(
        db_path=str(values["db_path"]), execution_id=execution_id,
        authenticated_operator_id="operator-1", signing_key=KEY, now=recovered_at,
    )
    assert view.attempt_status == "sending"
    assert view.full_ceiling_charged is False


def test_accounting_corruption_fails_closed(tmp_path: Path) -> None:
    values, authorization, execution_id = _crashed_send(tmp_path)
    with FlockWriteCoordinator(str(values["db_path"])).acquire_write_context(
        "test.corrupt_reconciliation_accounting"
    ) as connection:
        connection.execute(
            "UPDATE midnight_oil_reservations SET held_cents=held_cents+1 WHERE run_id=?",
            [authorization.authorization_id],
        )
    with pytest.raises(MultimediaExecutionUnavailable):
        get_chapter_tts_reconciliation(
            db_path=str(values["db_path"]), execution_id=execution_id,
            authenticated_operator_id="operator-1", signing_key=KEY, now=NOW,
        )


def test_operator_projects_and_releases_only_expired_seal_lease(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    values, _, authorization = _produce_values(tmp_path)
    execution_id = _execution_id(authorization)
    original_run = chapter_module._run
    monkeypatch.setattr(
        chapter_module,
        "_run",
        lambda *args, **kwargs: (_ for _ in ()).throw(ProcessCrash()),
    )
    with pytest.raises(ProcessCrash):
        produce_chapter_narration(
            **values,
            synthesize=lambda request: chapter_module.ChapterTTSSynthesisResult(
                _wav(), "operator-seal-crash"
            ),
        )  # type: ignore[arg-type]

    fresh = get_chapter_tts_reconciliation(
        db_path=str(values["db_path"]), execution_id=execution_id,
        authenticated_operator_id="operator-1", signing_key=KEY,
        now=NOW + timedelta(minutes=1),
    )
    assert fresh.next_action == "wait"
    assert fresh.seal_age_seconds == 60
    assert fresh.safe_error_code == "seal_lease_fresh"

    stale = get_chapter_tts_reconciliation(
        db_path=str(values["db_path"]), execution_id=execution_id,
        authenticated_operator_id="operator-1", signing_key=KEY,
        now=NOW + timedelta(minutes=10),
    )
    assert stale.next_action == "release_seal"
    assert stale.action_eligible is True
    assert stale.seal_lease_id is not None
    reset = operator_release_stale_seal(
        authority=_recovery(
            execution_id,
            "release_seal",
            NOW + timedelta(minutes=10),
            stale.seal_lease_id,
        ),
        recovery_key=RECOVERY_KEY, authenticated_operator_id="operator-1",
        signing_key=KEY, db_path=str(values["db_path"]),
        now=NOW + timedelta(minutes=10),
    )
    assert reset.attempt_status == "received"
    assert reset.next_action == "resume_narration"
    monkeypatch.setattr(chapter_module, "_run", original_run)
