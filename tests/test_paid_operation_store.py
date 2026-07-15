from __future__ import annotations

import concurrent.futures
import sqlite3
from pathlib import Path

import pytest

from substrate.paid_operations import (
    OperationConflict,
    OperationStateError,
    PaidOperationStore,
    Subject,
)

HASH_A = "a" * 64
HASH_B = "b" * 64
HASH_C = "c" * 64
HASH_D = "d" * 64


def collective_payload() -> dict[str, object]:
    return {
        "schema_version": 1,
        "quote_cents": 12,
        "ceiling_cents": 20,
        "pricing_snapshot_id": "price-1",
        "pricing_snapshot_hash": HASH_A,
        "created_at_ms": 1_000,
        "expires_at_ms": 2_000,
        "compose_id": "compose-1",
        "compose_fingerprint": HASH_B,
        "frozen_member_ids": ["member-1", "member-2"],
        "frozen_member_body_hashes": [HASH_A, HASH_C],
        "question": "Where do these sources disagree?",
        "context_packet_hash": HASH_C,
        "context_packet_bytes": 2048,
        "route_id": "route-1",
        "provider_id": "provider-1",
        "model_id": "model-1",
        "temperature_millionths": 250_000,
        "max_input_tokens": 4096,
        "max_output_tokens": 1024,
        "source_policy_version": "source-policy-v1",
        "answer_schema_version": "answer-schema-v1",
    }


def _store(tmp_path: Path) -> PaidOperationStore:
    return PaidOperationStore(tmp_path / "authority.sqlite3")


def _subject() -> Subject:
    return Subject(owner_user_id="owner-1", account_id="acct-1")


def _consent_patch(updated_at_ms: int = 1_100) -> dict[str, object]:
    return {
        "updated_at_ms": updated_at_ms,
        "consent_token_hash": HASH_D,
        "consent_key_id": "key-1",
        "consent_issued_at_ms": updated_at_ms,
        "consent_expires_at_ms": 1_900,
    }


def test_create_exact_replay_conflict_and_cross_owner_same_operation_id(tmp_path: Path) -> None:
    store = _store(tmp_path)
    first = store.create_or_replay(
        _subject(), "op-1", "collective_interrogation_v1", collective_payload()
    )
    replay = store.create_or_replay(
        _subject(), "op-1", "collective_interrogation_v1", collective_payload()
    )
    assert replay == first

    changed = collective_payload()
    changed["question"] = "Different?"
    with pytest.raises(OperationConflict, match="different material"):
        store.create_or_replay(_subject(), "op-1", "collective_interrogation_v1", changed)

    other_owner = Subject(owner_user_id="owner-2", account_id="acct-1")
    second = store.create_or_replay(
        other_owner,
        "op-1",
        "collective_interrogation_v1",
        collective_payload(),
    )
    assert second.operation_id == first.operation_id
    assert second.owner_user_id == "owner-2"
    assert second.intent_hash != first.intent_hash


def test_get_and_cas_are_subject_scoped_non_enumerating(tmp_path: Path) -> None:
    store = _store(tmp_path)
    store.create_or_replay(_subject(), "op-1", "collective_interrogation_v1", collective_payload())
    foreign = Subject(owner_user_id="owner-2", account_id="acct-1")
    assert store.get_owned(foreign, "op-1") is None
    with pytest.raises(OperationConflict, match="CAS"):
        store.compare_and_swap(foreign, "op-1", 0, ["intent_created"], "consent_issued", _consent_patch())


def test_restart_reads_same_authority_row(tmp_path: Path) -> None:
    path = tmp_path / "authority.sqlite3"
    first = PaidOperationStore(path).create_or_replay(
        _subject(), "op-1", "collective_interrogation_v1", collective_payload()
    )
    reopened = PaidOperationStore(path).get_owned(_subject(), "op-1")
    assert reopened == first


def test_cas_transition_stale_version_and_invalid_transition(tmp_path: Path) -> None:
    store = _store(tmp_path)
    created = store.create_or_replay(
        _subject(), "op-1", "collective_interrogation_v1", collective_payload()
    )
    issued = store.compare_and_swap(
        _subject(),
        "op-1",
        created.version,
        ["intent_created"],
        "consent_issued",
        _consent_patch(),
    )
    assert issued.state == "consent_issued"
    assert issued.version == 1
    with pytest.raises(OperationConflict, match="CAS"):
        store.compare_and_swap(
            _subject(),
            "op-1",
            created.version,
            ["intent_created"],
            "consent_issued",
            _consent_patch(1_200),
        )
    with pytest.raises(OperationStateError, match="invalid transition"):
        store.compare_and_swap(_subject(), "op-1", issued.version, ["consent_issued"], "running")


def test_two_simultaneous_cas_attempts_yield_one_success(tmp_path: Path) -> None:
    db = tmp_path / "authority.sqlite3"
    store = PaidOperationStore(db)
    created = store.create_or_replay(
        _subject(), "op-1", "collective_interrogation_v1", collective_payload()
    )

    def attempt(worker: str) -> str:
        local = PaidOperationStore(db)
        try:
            local.compare_and_swap(
                _subject(),
                "op-1",
                created.version,
                ["intent_created"],
                "consent_issued",
                {
                    **_consent_patch(),
                    "consent_key_id": worker,
                    "consent_token_hash": HASH_A if worker == "key-1" else HASH_B,
                },
            )
        except OperationConflict:
            return "conflict"
        return "success"

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(attempt, ["key-1", "key-2"]))
    assert sorted(results) == ["conflict", "success"]
    assert PaidOperationStore(db).get_owned(_subject(), "op-1").version == 1  # type: ignore[union-attr]


def test_malformed_rows_fail_closed(tmp_path: Path) -> None:
    db = tmp_path / "authority.sqlite3"
    store = PaidOperationStore(db)
    store.create_or_replay(_subject(), "op-1", "collective_interrogation_v1", collective_payload())
    with sqlite3.connect(db) as con:
        con.execute("UPDATE paid_operations SET intent_hash = ? WHERE operation_id = ?", ("0" * 64, "op-1"))
    with pytest.raises(OperationStateError, match="canonical intent conflicts"):
        PaidOperationStore(db).get_owned(_subject(), "op-1")


def test_forbidden_patch_escalation_fails(tmp_path: Path) -> None:
    store = _store(tmp_path)
    created = store.create_or_replay(
        _subject(), "op-1", "collective_interrogation_v1", collective_payload()
    )
    with pytest.raises(OperationStateError, match="forbidden"):
        store.compare_and_swap(
            _subject(),
            "op-1",
            created.version,
            ["intent_created"],
            "consent_issued",
            {**_consent_patch(), "lease_worker_id": "worker-1"},
        )
    with pytest.raises(ValueError, match="updated_at_ms is required"):
        store.compare_and_swap(
            _subject(),
            "op-1",
            created.version,
            ["intent_created"],
            "consent_issued",
            {"consent_token_hash": HASH_D},
        )


def test_spr02_only_opens_consent_issued_to_queued_transition(tmp_path: Path) -> None:
    store = _store(tmp_path)
    created = store.create_or_replay(
        _subject(), "op-1", "collective_interrogation_v1", collective_payload()
    )
    issued = store.compare_and_swap(
        _subject(), "op-1", created.version, ["intent_created"], "consent_issued", _consent_patch()
    )
    queued = store.compare_and_swap(
        _subject(),
        "op-1",
        issued.version,
        ["consent_issued"],
        "queued",
        {"updated_at_ms": 1_200, "consent_claimed_at_ms": 1_200},
    )
    assert queued.state == "queued"
    for target in ("running", "complete", "failed", "budget_halted", "timed_out", "failed_reconcile"):
        with pytest.raises(OperationStateError, match="invalid transition"):
            store.compare_and_swap(
                _subject(),
                "op-1",
                queued.version,
                ["consent_issued"],
                target,
                {"updated_at_ms": 1_300},
            )
    with pytest.raises(OperationStateError, match="invalid transition"):
        store.compare_and_swap(
            _subject(),
            "op-1",
            queued.version,
            ["queued"],
            "complete",
            {"updated_at_ms": 1_300, "lease_generation": 1},
        )


@pytest.mark.parametrize(
    "column,value,match",
    [
        ("consent_token_hash", HASH_A.upper(), "lowercase sha256"),
        ("consent_key_id", "Key-1", "lowercase canonical identifier"),
        ("consent_issued_at_ms", 999, "issued before creation"),
        ("consent_expires_at_ms", 1_000, "expires before issuance"),
        ("consent_claimed_at_ms", 1_000, "claimed before issuance"),
        ("lease_worker_id", "", "non-empty string"),
        ("lease_expires_at_ms", 2_500, "lease expiry requires lease generation"),
        ("terminal_code", "done", "nonterminal state"),
        ("terminal_reason", "Cafe\u0301", "NFC-normalized"),
        ("reconciliation_status", "Waiting", "lowercase canonical identifier"),
        ("result_checkpoint_hash", HASH_A.upper(), "lowercase sha256"),
        ("settled_cents", 1, "nonterminal state"),
        ("external_charged_cents", 1, "nonterminal state"),
    ],
)
def test_optional_column_corruption_fails_closed(
    tmp_path: Path,
    column: str,
    value: object,
    match: str,
) -> None:
    db = tmp_path / "authority.sqlite3"
    store = PaidOperationStore(db)
    created = store.create_or_replay(
        _subject(), "op-1", "collective_interrogation_v1", collective_payload()
    )
    store.compare_and_swap(
        _subject(), "op-1", created.version, ["intent_created"], "consent_issued", _consent_patch()
    )
    with sqlite3.connect(db) as con:
        con.execute(
            f"UPDATE paid_operations SET {column} = ? "
            "WHERE operation_id = ? AND owner_user_id = ? AND account_id = ?",
            (value, "op-1", "owner-1", "acct-1"),
        )
    with pytest.raises(OperationStateError, match=match):
        PaidOperationStore(db).get_owned(_subject(), "op-1")


@pytest.mark.parametrize(
    "column",
    [
        "consent_issued_at_ms",
        "consent_expires_at_ms",
        "consent_claimed_at_ms",
        "lease_generation",
        "lease_expires_at_ms",
        "settled_cents",
        "external_charged_cents",
    ],
)
def test_sqlite_checks_reject_invalid_nullable_integer_columns(
    tmp_path: Path,
    column: str,
) -> None:
    db = tmp_path / "authority.sqlite3"
    store = PaidOperationStore(db)
    store.create_or_replay(_subject(), "op-1", "collective_interrogation_v1", collective_payload())
    with sqlite3.connect(db) as con, pytest.raises(sqlite3.IntegrityError):
        con.execute(
            f"UPDATE paid_operations SET {column} = ? "
            "WHERE operation_id = ? AND owner_user_id = ? AND account_id = ?",
            (-1, "op-1", "owner-1", "acct-1"),
        )


@pytest.mark.parametrize(
    "column",
    [
        "quote_cents",
        "ceiling_cents",
        "version",
        "created_at_ms",
        "updated_at_ms",
        "expires_at_ms",
        "consent_issued_at_ms",
        "consent_expires_at_ms",
        "consent_claimed_at_ms",
        "lease_generation",
        "lease_expires_at_ms",
        "settled_cents",
        "external_charged_cents",
    ],
)
def test_bool_as_int_is_rejected_by_snapshot_validation(column: str) -> None:
    values: dict[str, object] = {
        "operation_id": "op-1",
        "owner_user_id": "owner-1",
        "account_id": "acct-1",
        "kind": "collective_interrogation_v1",
        "intent_hash": HASH_A,
        "canonical_intent_json": "{}",
        "quote_cents": 1,
        "ceiling_cents": 1,
        "state": "intent_created",
        "version": 0,
        "created_at_ms": 1,
        "updated_at_ms": 1,
        "expires_at_ms": 2,
        "consent_token_hash": None,
        "consent_key_id": None,
        "consent_issued_at_ms": None,
        "consent_expires_at_ms": None,
        "consent_claimed_at_ms": None,
        "lease_worker_id": None,
        "lease_generation": None,
        "lease_expires_at_ms": None,
        "terminal_code": None,
        "terminal_reason": None,
        "reconciliation_status": None,
        "result_checkpoint_hash": None,
        "settled_cents": None,
        "external_charged_cents": None,
    }
    values[column] = True
    from substrate.paid_operations.store import OperationSnapshot, _validate_snapshot

    with pytest.raises(OperationStateError, match="exact integer"):
        _validate_snapshot(OperationSnapshot(**values))  # type: ignore[arg-type]


def test_sqlite_checks_reject_invalid_money(tmp_path: Path) -> None:
    db = tmp_path / "authority.sqlite3"
    PaidOperationStore(db)
    with sqlite3.connect(db) as con, pytest.raises(sqlite3.IntegrityError):
        con.execute(
            "INSERT INTO paid_operations ("
            "operation_id, owner_user_id, account_id, kind, intent_hash, canonical_intent_json, "
            "quote_cents, ceiling_cents, state, version, created_at_ms, updated_at_ms, expires_at_ms"
            ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                "op-x",
                "owner-1",
                "acct-1",
                "collective_interrogation_v1",
                "a" * 64,
                b"{}",
                -1,
                0,
                "intent_created",
                0,
                1,
                1,
                2,
            ),
        )
