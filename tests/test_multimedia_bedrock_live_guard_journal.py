from __future__ import annotations

import hashlib
import os
import sqlite3
from pathlib import Path

import pytest

import substrate.multimedia.bedrock_live_guard_journal as journal_module
from substrate.multimedia.bedrock_live_guard_acquisition import (
    LiveGuardAcquisitionAttempt,
    LiveGuardAcquisitionCommand,
)
from substrate.multimedia.bedrock_live_guard_journal import (
    LiveGuardJournalConflict,
    LiveGuardJournalError,
    LiveGuardJournalUnavailable,
    SqliteLiveGuardAcquisitionJournal,
)
from tests.test_multimedia_bedrock_live_guard_acquisition import _command, _coordinator


def _root(tmp_path: Path) -> Path:
    tmp_path.chmod(0o700)
    return tmp_path


def _attempt(command: LiveGuardAcquisitionCommand, nonce: str = "c" * 32):
    trusted_start = "2026-07-15T01:00:00Z"
    attempt_id = "lga_" + hashlib.sha256(
        f"{command.digest}:{trusted_start}:{nonce}".encode("ascii")
    ).hexdigest()
    return LiveGuardAcquisitionAttempt(
        command_digest=command.digest,
        attempt_id=attempt_id,
        attempt_nonce=nonce,
        trusted_start=trusted_start,
    )


def _record_in_progress(journal: SqliteLiveGuardAcquisitionJournal):
    cycle34 = _coordinator()[0]
    command = _command(cycle34)
    attempt = _attempt(command)
    journal.record_intent(
        command_json=command.canonical_json,
        attempt_json=attempt.canonical_json,
    )
    return cycle34, command, attempt


def _complete_with_coordinator(journal: SqliteLiveGuardAcquisitionJournal):
    cycle34, coordinator, _, _, _, _, _, _ = _coordinator()
    coordinator.journal = journal
    receipt = coordinator.acquire(
        command=_command(cycle34),
        cycle34_receipt=cycle34,
        attempt_nonce="c" * 32,
    )
    return cycle34, receipt


def test_real_journal_survives_reopen_and_reports_exact_completion(tmp_path: Path) -> None:
    root = _root(tmp_path)
    journal = SqliteLiveGuardAcquisitionJournal(root)
    _, receipt = _complete_with_coordinator(journal)

    reopened = SqliteLiveGuardAcquisitionJournal(root)
    assert reopened.read_attempt(attempt_id=receipt.attempt_id) == receipt.canonical_json
    status = reopened.inspect_attempt(attempt_id=receipt.attempt_id)
    assert status.status == "completed"
    assert status.receipt_digest == receipt.digest
    assert status.production_eligible is False
    assert reopened.list_attempts(command_id=_command(_coordinator()[0]).command_id) == (status,)
    report = reopened.verify_all()
    assert (report.command_count, report.attempt_count, report.completion_count) == (1, 1, 1)
    assert report.in_progress_count == 0
    assert report.production_eligible is False


def test_incomplete_attempt_is_inspectable_but_has_no_receipt(tmp_path: Path) -> None:
    journal = SqliteLiveGuardAcquisitionJournal(_root(tmp_path))
    _, command, attempt = _record_in_progress(journal)
    assert journal.read_attempt(attempt_id=attempt.attempt_id) is None
    status = journal.inspect_attempt(attempt_id=attempt.attempt_id)
    assert status.status == "in_progress"
    assert status.receipt_digest is None
    assert journal.list_attempts(command_id=command.command_id) == (status,)
    report = journal.verify_all()
    assert report.in_progress_count == 1


def test_command_identity_reuse_with_changed_bytes_fails(tmp_path: Path) -> None:
    journal = SqliteLiveGuardAcquisitionJournal(_root(tmp_path))
    cycle34, command, _ = _record_in_progress(journal)
    changed = _command(cycle34, max_revocation_lag_seconds=61)
    changed_attempt = _attempt(changed, "d" * 32)
    with pytest.raises(LiveGuardJournalConflict, match="command identity"):
        journal.record_intent(
            command_json=changed.canonical_json,
            attempt_json=changed_attempt.canonical_json,
        )
    assert journal.list_attempts(command_id=command.command_id)[0].status == "in_progress"


@pytest.mark.parametrize(
    "stage",
    ["after_command_insert", "after_attempt_insert", "before_intent_commit"],
)
def test_intent_failure_before_commit_rolls_back_all_rows(tmp_path: Path, stage: str) -> None:
    def fail(current: str) -> None:
        if current == stage:
            raise RuntimeError("injected crash")

    root = _root(tmp_path)
    journal = SqliteLiveGuardAcquisitionJournal(root, failure_hook=fail)
    cycle34 = _coordinator()[0]
    command = _command(cycle34)
    attempt = _attempt(command)
    with pytest.raises(LiveGuardJournalError, match="intent transaction"):
        journal.record_intent(
            command_json=command.canonical_json,
            attempt_json=attempt.canonical_json,
        )
    clean = SqliteLiveGuardAcquisitionJournal(root)
    report = clean.verify_all()
    assert (report.command_count, report.attempt_count) == (0, 0)


def test_lost_intent_acknowledgment_reopens_exact_rows(tmp_path: Path) -> None:
    def fail(stage: str) -> None:
        if stage == "after_intent_commit":
            raise RuntimeError("acknowledgment lost")

    root = _root(tmp_path)
    journal = SqliteLiveGuardAcquisitionJournal(root, failure_hook=fail)
    cycle34 = _coordinator()[0]
    command = _command(cycle34)
    attempt = _attempt(command)
    with pytest.raises(LiveGuardJournalError):
        journal.record_intent(
            command_json=command.canonical_json,
            attempt_json=attempt.canonical_json,
        )
    reopened = SqliteLiveGuardAcquisitionJournal(root)
    assert reopened.inspect_attempt(attempt_id=attempt.attempt_id).status == "in_progress"
    reopened.record_intent(
        command_json=command.canonical_json,
        attempt_json=attempt.canonical_json,
    )


@pytest.mark.parametrize("stage", ["after_completion_insert", "before_completion_commit"])
def test_completion_failure_before_commit_preserves_in_progress(
    tmp_path: Path, stage: str
) -> None:
    root = _root(tmp_path)
    source_root = root / "receipt-source"
    source_root.mkdir(mode=0o700)
    base = SqliteLiveGuardAcquisitionJournal(source_root)
    _, receipt = _complete_with_coordinator(base)

    clean = SqliteLiveGuardAcquisitionJournal(root)
    cycle34, command, attempt = _record_in_progress(clean)
    assert cycle34.digest == receipt.cycle34_receipt_digest

    def fail(current: str) -> None:
        if current == stage:
            raise RuntimeError("injected crash")

    failing = SqliteLiveGuardAcquisitionJournal(root, failure_hook=fail)
    with pytest.raises(LiveGuardJournalError, match="completion transaction"):
        failing.commit_attempt(attempt_id=attempt.attempt_id, receipt_json=receipt.canonical_json)
    assert clean.inspect_attempt(attempt_id=attempt.attempt_id).status == "in_progress"
    assert command.digest == receipt.command_digest


def test_post_commit_error_is_recovered_by_cycle36_readback(tmp_path: Path) -> None:
    def fail(stage: str) -> None:
        if stage == "after_completion_commit":
            raise RuntimeError("acknowledgment lost")

    journal = SqliteLiveGuardAcquisitionJournal(_root(tmp_path), failure_hook=fail)
    _, receipt = _complete_with_coordinator(journal)
    assert journal.read_attempt(attempt_id=receipt.attempt_id) == receipt.canonical_json


def test_database_triggers_reject_update_and_delete(tmp_path: Path) -> None:
    journal = SqliteLiveGuardAcquisitionJournal(_root(tmp_path))
    _, receipt = _complete_with_coordinator(journal)
    connection = sqlite3.connect(journal.path)
    try:
        for table in (
            "live_guard_commands",
            "live_guard_attempts",
            "live_guard_completions",
        ):
            with pytest.raises(sqlite3.IntegrityError, match="append-only"):
                connection.execute(f"UPDATE {table} SET rowid=rowid")
            with pytest.raises(sqlite3.IntegrityError, match="append-only"):
                connection.execute(f"DELETE FROM {table}")
    finally:
        connection.close()
    assert journal.read_attempt(attempt_id=receipt.attempt_id) == receipt.canonical_json


def test_missing_trigger_or_index_fails_schema_verification(tmp_path: Path) -> None:
    journal = SqliteLiveGuardAcquisitionJournal(_root(tmp_path))
    _, _, attempt = _record_in_progress(journal)
    connection = sqlite3.connect(journal.path)
    connection.execute("DROP TRIGGER live_guard_attempts_no_update")
    connection.commit()
    connection.close()
    with pytest.raises(LiveGuardJournalError, match="trigger"):
        journal.inspect_attempt(attempt_id=attempt.attempt_id)


@pytest.mark.parametrize(
    ("table", "column", "changed"),
    [
        ("live_guard_commands", "command_id", "lgc_" + "f" * 32),
        ("live_guard_commands", "command_digest", "f" * 64),
        ("live_guard_commands", "command_json", "{}"),
        ("live_guard_attempts", "attempt_id", "lga_" + "f" * 64),
        ("live_guard_attempts", "command_id", "lgc_" + "f" * 32),
        ("live_guard_attempts", "command_digest", "f" * 64),
        ("live_guard_attempts", "attempt_digest", "f" * 64),
        ("live_guard_attempts", "attempt_json", "{}"),
        ("live_guard_attempts", "attempt_nonce", "f" * 32),
        ("live_guard_attempts", "trusted_start", "2026-07-15T02:00:00Z"),
        ("live_guard_completions", "attempt_id", "lga_" + "f" * 64),
        ("live_guard_completions", "receipt_digest", "f" * 64),
        ("live_guard_completions", "receipt_json", "{}"),
    ],
)
def test_every_stored_column_drift_fails_full_verification(
    tmp_path: Path, table: str, column: str, changed: str
) -> None:
    journal = SqliteLiveGuardAcquisitionJournal(_root(tmp_path))
    _complete_with_coordinator(journal)
    trigger_name = f"{table}_no_update"
    connection = sqlite3.connect(journal.path)
    trigger_sql = connection.execute(
        "SELECT sql FROM sqlite_master WHERE type='trigger' AND name=?", (trigger_name,)
    ).fetchone()[0]
    connection.execute(f"DROP TRIGGER {trigger_name}")
    connection.execute(f"UPDATE {table} SET {column}=?", (changed,))
    connection.execute(trigger_sql)
    connection.commit()
    connection.close()

    with pytest.raises(LiveGuardJournalError):
        journal.verify_all()


def test_database_path_replacement_during_sqlite_open_fails_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    journal = SqliteLiveGuardAcquisitionJournal(_root(tmp_path))
    _record_in_progress(journal)
    original_connect = sqlite3.connect

    def replace_then_connect(*args, **kwargs):
        displaced = journal.root / "displaced.sqlite3"
        os.replace(journal.path, displaced)
        replacement = original_connect(journal.path)
        replacement.close()
        journal.path.chmod(0o600)
        return original_connect(*args, **kwargs)

    monkeypatch.setattr(journal_module.sqlite3, "connect", replace_then_connect)
    with pytest.raises(LiveGuardJournalError, match="changed during open"):
        journal.verify_all()


def test_lock_timeout_is_controlled_and_leaves_no_partial_intent(tmp_path: Path) -> None:
    root = _root(tmp_path)
    journal = SqliteLiveGuardAcquisitionJournal(root, timeout_seconds=0.01)
    _record_in_progress(journal)
    lock = sqlite3.connect(journal.path, isolation_level=None)
    lock.execute("BEGIN EXCLUSIVE")
    try:
        cycle34 = _coordinator()[0]
        command = _command(cycle34, command_id="lgc_" + "d" * 32)
        attempt = _attempt(command, "d" * 32)
        with pytest.raises(LiveGuardJournalError):
            journal.record_intent(
                command_json=command.canonical_json,
                attempt_json=attempt.canonical_json,
            )
    finally:
        lock.rollback()
        lock.close()
    assert journal.verify_all().command_count == 1


def test_unsafe_root_file_modes_symlink_and_hardlink_fail(tmp_path: Path) -> None:
    root = _root(tmp_path)
    root.chmod(0o755)
    with pytest.raises(ValueError, match="0700"):
        SqliteLiveGuardAcquisitionJournal(root)
    root.chmod(0o700)
    journal = SqliteLiveGuardAcquisitionJournal(root)
    _record_in_progress(journal)
    journal.path.chmod(0o644)
    with pytest.raises(LiveGuardJournalError, match="private"):
        journal.verify_all()
    journal.path.chmod(0o600)
    hardlink = root / "journal-hardlink"
    os.link(journal.path, hardlink)
    with pytest.raises(LiveGuardJournalError, match="private"):
        journal.verify_all()


def test_missing_and_invalid_inspection_inputs_fail(tmp_path: Path) -> None:
    journal = SqliteLiveGuardAcquisitionJournal(_root(tmp_path))
    with pytest.raises(LiveGuardJournalUnavailable):
        journal.read_attempt(attempt_id="lga_" + "a" * 64)
    with pytest.raises(ValueError):
        journal.list_attempts(command_id="bad")
    with pytest.raises(ValueError):
        journal.list_attempts(command_id="lgc_" + "a" * 32, limit=101)
