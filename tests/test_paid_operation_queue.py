from __future__ import annotations

import concurrent.futures
import sqlite3
from pathlib import Path

import pytest

from substrate.paid_operations import (
    ConsentKeyring,
    OperationConflict,
    PaidOperationConsentService,
    PaidOperationCorruptionError,
    PaidOperationStore,
    Subject,
)
from tests.test_paid_operation_store import collective_payload


def _subject() -> Subject:
    return Subject(owner_user_id="owner-1", account_id="acct-1")


def _service(db: Path, now: int = 1_100) -> PaidOperationConsentService:
    return PaidOperationConsentService(
        PaidOperationStore(db),
        ConsentKeyring(active_key_id="key-1", keys={"key-1": b"k" * 32}),
        clock_ms=lambda: now,
        nonce_factory=lambda: b"n" * 32,
        ttl_ms=700,
    )


def test_before_commit_restart_can_claim_consent_with_no_queue_row(tmp_path: Path) -> None:
    db = tmp_path / "authority.sqlite3"
    service = _service(db)
    service._store.create_or_replay(_subject(), "op-1", "collective_interrogation_v1", collective_payload())
    token = service.issue(_subject(), "op-1").token

    restarted = _service(db, now=1_200)
    result = restarted.claim(_subject(), "op-1", token=token, options={"attempt": 1})
    assert result.snapshot.state == "queued"
    assert result.queue.intent_hash == result.snapshot.intent_hash


def test_after_commit_restart_sees_exactly_one_matching_queue_row(tmp_path: Path) -> None:
    db = tmp_path / "authority.sqlite3"
    service = _service(db)
    service._store.create_or_replay(_subject(), "op-1", "collective_interrogation_v1", collective_payload())
    token = service.issue(_subject(), "op-1").token
    service.claim(_subject(), "op-1", token=token, options={"attempt": 1})

    restarted = PaidOperationStore(db)
    snapshot = restarted.get_owned(_subject(), "op-1")
    queue = restarted.get_queue(_subject(), "op-1")
    assert snapshot is not None
    assert queue is not None
    assert snapshot.state == "queued"
    assert queue.operation_id == snapshot.operation_id
    assert queue.owner_user_id == snapshot.owner_user_id
    assert queue.account_id == snapshot.account_id
    assert queue.intent_hash == snapshot.intent_hash


def test_concurrent_claims_enqueue_once(tmp_path: Path) -> None:
    db = tmp_path / "authority.sqlite3"
    service = _service(db)
    service._store.create_or_replay(_subject(), "op-1", "collective_interrogation_v1", collective_payload())
    token = service.issue(_subject(), "op-1").token

    def claim() -> str:
        local = _service(db, now=1_200)
        try:
            local.claim(_subject(), "op-1", token=token, options={"attempt": 1})
        except OperationConflict:
            return "conflict"
        return "success"

    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
        results = list(pool.map(lambda _: claim(), range(6)))
    assert results.count("success") == 6
    with sqlite3.connect(db) as con:
        count = con.execute("SELECT count(*) FROM paid_operation_queue").fetchone()[0]
    assert count == 1


def test_concurrent_drifted_claim_conflicts(tmp_path: Path) -> None:
    db = tmp_path / "authority.sqlite3"
    service = _service(db)
    service._store.create_or_replay(_subject(), "op-1", "collective_interrogation_v1", collective_payload())
    token = service.issue(_subject(), "op-1").token

    def claim(attempt: int) -> str:
        local = _service(db, now=1_200)
        try:
            local.claim(_subject(), "op-1", token=token, options={"attempt": attempt})
        except OperationConflict:
            return "conflict"
        return "success"

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(claim, (1, 2)))
    assert sorted(results) == ["conflict", "success"]
    with sqlite3.connect(db) as con:
        assert con.execute("SELECT count(*) FROM paid_operation_queue").fetchone()[0] == 1


def test_startup_validation_rejects_corrupt_boundaries(tmp_path: Path) -> None:
    db = tmp_path / "authority.sqlite3"
    service = _service(db)
    service._store.create_or_replay(_subject(), "op-1", "collective_interrogation_v1", collective_payload())
    token = service.issue(_subject(), "op-1").token
    service.claim(_subject(), "op-1", token=token, options={})
    with sqlite3.connect(db) as con:
        con.execute("UPDATE paid_operation_queue SET intent_hash = ? WHERE operation_id = ?", ("0" * 64, "op-1"))
    with pytest.raises(PaidOperationCorruptionError, match="queue row conflicts"):
        PaidOperationStore(db)


@pytest.mark.parametrize("corrupt", ['{"b":1,"a":2}', '{"a":1.0}', '{"label":"Cafe\\u0301"}'])
def test_startup_rejects_noncanonical_queue_options(tmp_path: Path, corrupt: str) -> None:
    db = tmp_path / "authority.sqlite3"
    service = _service(db)
    service._store.create_or_replay(_subject(), "op-1", "collective_interrogation_v1", collective_payload())
    token = service.issue(_subject(), "op-1").token
    service.claim(_subject(), "op-1", token=token, options={})
    with sqlite3.connect(db) as con:
        con.execute(
            "UPDATE paid_operation_queue SET canonical_options_json = ? WHERE operation_id = ?",
            (corrupt, "op-1"),
        )
    with pytest.raises(PaidOperationCorruptionError, match="canonical options"):
        PaidOperationStore(db)


def test_startup_rejects_claimed_consent_without_queue(tmp_path: Path) -> None:
    db = tmp_path / "authority.sqlite3"
    service = _service(db)
    service._store.create_or_replay(_subject(), "op-1", "collective_interrogation_v1", collective_payload())
    service.issue(_subject(), "op-1")
    with sqlite3.connect(db) as con:
        con.execute(
            "UPDATE paid_operations SET consent_claimed_at_ms = ? WHERE operation_id = ?",
            (1_200, "op-1"),
        )
    with pytest.raises(PaidOperationCorruptionError, match="claimed consent is missing queue row"):
        PaidOperationStore(db)


def test_startup_rejects_queued_authority_without_queue(tmp_path: Path) -> None:
    db = tmp_path / "authority.sqlite3"
    service = _service(db)
    service._store.create_or_replay(_subject(), "op-1", "collective_interrogation_v1", collective_payload())
    token = service.issue(_subject(), "op-1").token
    service.claim(_subject(), "op-1", token=token, options={})
    with sqlite3.connect(db) as con:
        con.execute("PRAGMA foreign_keys = OFF")
        con.execute("DELETE FROM paid_operation_queue WHERE operation_id = ?", ("op-1",))
    with pytest.raises(PaidOperationCorruptionError, match="missing queue row"):
        PaidOperationStore(db)


def test_queue_row_without_authority_is_fatal(tmp_path: Path) -> None:
    db = tmp_path / "authority.sqlite3"
    PaidOperationStore(db)
    with sqlite3.connect(db) as con:
        con.execute("PRAGMA foreign_keys = OFF")
        con.execute(
            "INSERT INTO paid_operation_queue ("
            "account_id, owner_user_id, operation_id, operation_kind, intent_hash, "
            "canonical_options_json, enqueued_at_ms, queue_state"
            ") VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            ("acct-1", "owner-1", "op-missing", "collective_interrogation_v1", "a" * 64, b"{}", 1, "queued"),
        )
    with pytest.raises(PaidOperationCorruptionError, match="missing authority"):
        PaidOperationStore(db)
