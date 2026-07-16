from __future__ import annotations

import errno
import json
import multiprocessing
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

import pytest

import runtime.provider_broker.ledger as broker_ledger_module
from runtime.provider_broker.ledger import (
    BrokerConflict,
    BrokerDispatchIntent,
    BrokerIntegrityError,
    BrokerTransition,
    BrokerTransitionRefused,
    BrokerUnavailable,
    LookupDisposition,
    PrimaryBrokerLedger,
    provider_idempotency_token,
)
from runtime.provider_broker.protocol import (
    BrokerAuthorization,
    BrokerReceiptState,
    authorization_from_mapping,
)

FIXTURE = Path(__file__).parent / "fixtures/provider_broker_protocol_vectors.json"
NOW = datetime(2026, 7, 16, 18, 30, tzinfo=UTC)
INTENT = BrokerDispatchIntent(
    "1" * 64,
    provider_idempotency_token("1" * 64, "2" * 64, "3" * 64),
    "2" * 64,
    "3" * 64,
    "2026-07-17T00:00:00Z",
)


def _authorization() -> BrokerAuthorization:
    vectors = json.loads(FIXTURE.read_text(encoding="utf-8"))
    return authorization_from_mapping(vectors["authorization"])


def _ledger(path: Path, *, now: datetime = NOW, timeout: float = 1.0) -> PrimaryBrokerLedger:
    return PrimaryBrokerLedger(path, clock=lambda: now, lock_timeout_seconds=timeout)


def _ready(path: Path) -> PrimaryBrokerLedger:
    ledger = _ledger(path)
    ledger.ensure_schema()
    return ledger


def _hold_key_lock(
    path: str, ready: multiprocessing.Queue[bool], release: multiprocessing.Queue[bool]
) -> None:
    ledger = PrimaryBrokerLedger(path, lock_timeout_seconds=2.0)
    with ledger._key_lock("tenant-1", "missing-key"):  # noqa: SLF001
        ready.put(True)
        release.get(timeout=5)


def test_schema_v1_migrates_transactionally_to_v2(tmp_path: Path) -> None:
    source_path = tmp_path / "source.sqlite"
    source = _ready(source_path)
    source.authorize(_authorization())
    path = tmp_path / "broker.sqlite"
    with sqlite3.connect(source_path) as source_db, sqlite3.connect(path) as db:
        source_db.row_factory = sqlite3.Row
        db.executescript(broker_ledger_module._MIGRATION_1)  # noqa: SLF001
        operation_columns = [row[1] for row in db.execute("PRAGMA table_info(broker_operations)")]
        operation = source_db.execute(
            f"SELECT {','.join(operation_columns)} FROM broker_operations"  # noqa: S608
        ).fetchone()
        db.execute(
            f"INSERT INTO broker_operations ({','.join(operation_columns)}) "  # noqa: S608
            f"VALUES ({','.join('?' for _ in operation_columns)})",
            tuple(operation),
        )
        command = source_db.execute("SELECT * FROM broker_commands").fetchone()
        db.execute("INSERT INTO broker_commands VALUES (?,?,?,?,?)", tuple(command))
        event = dict(source_db.execute("SELECT * FROM broker_audit").fetchone())
        legacy_result = json.loads(event["result_json"])
        del legacy_result["dispatch_intent"]
        event["result_json"] = json.dumps(legacy_result, sort_keys=True, separators=(",", ":"))
        event["result_digest"] = broker_ledger_module.hashlib.sha256(
            event["result_json"].encode("ascii")
        ).hexdigest()
        event["event_hash"] = broker_ledger_module._event_hash(  # noqa: SLF001
            operation_id=event["operation_id"],
            sequence=event["sequence"],
            from_state=event["from_state"],
            to_state=event["to_state"],
            version=event["version"],
            command_id=event["command_id"],
            command_digest=event["command_digest"],
            result_digest=event["result_digest"],
            recorded_at=event["recorded_at"],
            previous_hash=event["previous_hash"],
        )
        db.execute(
            "INSERT INTO broker_audit VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            tuple(event.values()),
        )
        audit_before = db.execute("SELECT * FROM broker_audit").fetchall()
    ledger = _ledger(path)
    ledger.ensure_schema()
    with sqlite3.connect(path) as db:
        assert db.execute("SELECT version FROM broker_schema").fetchone() == (2,)
        columns = {row[1] for row in db.execute("PRAGMA table_info(broker_operations)")}
        assert db.execute("SELECT * FROM broker_audit").fetchall() == audit_before
    assert {
        "request_envelope_digest",
        "provider_idempotency_token",
        "adapter_contract_digest",
        "qualification_digest",
        "replay_expires_at",
    } <= columns
    assert ledger.verify_integrity() == 1


def test_dispatch_intent_is_audited_immutable_and_command_replay_exact(tmp_path: Path) -> None:
    path = tmp_path / "broker.sqlite"
    ledger = _ready(path)
    ledger.authorize(_authorization())
    command = BrokerTransition(
        "dispatch-intent",
        0,
        BrokerReceiptState.DISPATCH_POSSIBLE,
        attempt_id="attempt-1",
        dispatch_intent=INTENT,
    )
    marked = ledger.transition("tenant-1", "op-key-1", command)
    assert marked.dispatch_intent == INTENT
    assert ledger.transition("tenant-1", "op-key-1", command) == marked
    with pytest.raises(BrokerConflict, match="different bytes"):
        ledger.transition(
            "tenant-1",
            "op-key-1",
            replace(
                command,
                dispatch_intent=replace(
                    INTENT,
                    qualification_digest="4" * 64,
                    provider_idempotency_token=provider_idempotency_token(
                        INTENT.request_envelope_digest,
                        INTENT.adapter_contract_digest,
                        "4" * 64,
                    ),
                ),
            ),
        )
    with sqlite3.connect(path) as db, pytest.raises(sqlite3.IntegrityError, match="immutable"):
        db.execute(
            "UPDATE broker_operations SET qualification_digest=? WHERE operation_id=?",
            ("4" * 64, marked.operation_id),
        )
    assert ledger.verify_integrity() == 1


def test_schema_trigger_refuses_retrofit_on_legacy_marked_row(tmp_path: Path) -> None:
    path = tmp_path / "broker.sqlite"
    ledger = _ready(path)
    ledger.authorize(_authorization())
    marked = ledger.transition(
        "tenant-1",
        "op-key-1",
        BrokerTransition(
            "dispatch-intent",
            0,
            BrokerReceiptState.DISPATCH_POSSIBLE,
            attempt_id="attempt-1",
            dispatch_intent=INTENT,
        ),
    )
    with sqlite3.connect(path) as db:
        db.execute("DROP TRIGGER broker_dispatch_intent_immutable")
        db.execute(
            "UPDATE broker_operations SET request_envelope_digest=NULL,"
            "provider_idempotency_token=NULL,adapter_contract_digest=NULL,"
            "qualification_digest=NULL,replay_expires_at=NULL WHERE operation_id=?",
            (marked.operation_id,),
        )
        db.execute(
            broker_ledger_module._EXPECTED_TRIGGER_SQL[  # noqa: SLF001
                "broker_dispatch_intent_immutable"
            ]
        )
        with pytest.raises(sqlite3.IntegrityError, match="immutable"):
            db.execute(
                "UPDATE broker_operations SET request_envelope_digest=?,"
                "provider_idempotency_token=?,adapter_contract_digest=?,"
                "qualification_digest=?,replay_expires_at=? WHERE operation_id=?",
                (
                    INTENT.request_envelope_digest,
                    INTENT.provider_idempotency_token,
                    INTENT.adapter_contract_digest,
                    INTENT.qualification_digest,
                    INTENT.replay_expires_at,
                    marked.operation_id,
                ),
            )


def test_missing_is_authoritative_only_after_primary_schema_and_transaction(
    tmp_path: Path,
) -> None:
    path = tmp_path / "broker.sqlite"
    with pytest.raises(BrokerUnavailable, match="does not exist"):
        _ledger(path).lookup("tenant-1", "key-1")

    result = _ready(path).lookup("tenant-1", "key-1")
    assert result.disposition is LookupDisposition.AUTHORITATIVE_MISSING
    assert result.operation is None


def test_authorize_exact_replay_returns_one_operation_and_audit(tmp_path: Path) -> None:
    ledger = _ready(tmp_path / "broker.sqlite")
    first = ledger.authorize(_authorization())
    replay = ledger.authorize(_authorization())

    assert replay == first
    assert first.state is BrokerReceiptState.AUTHORIZED
    assert first.version == 0
    assert first.send_marker is False
    assert ledger.verify_integrity() == 1


@pytest.mark.parametrize(
    "now",
    [
        datetime(2026, 7, 16, 17, 59, 59, tzinfo=UTC),
        datetime(2026, 7, 17, 0, 0, tzinfo=UTC),
    ],
)
def test_authorize_refuses_authority_outside_its_validity(tmp_path: Path, now: datetime) -> None:
    ledger = _ledger(tmp_path / "broker.sqlite", now=now)
    ledger.ensure_schema()
    with pytest.raises(BrokerTransitionRefused, match="not currently valid"):
        ledger.authorize(_authorization())


def test_exact_committed_authorization_replays_after_expiry(tmp_path: Path) -> None:
    clock = [NOW]
    ledger = PrimaryBrokerLedger(tmp_path / "broker.sqlite", clock=lambda: clock[0])
    ledger.ensure_schema()
    original = ledger.authorize(_authorization())
    clock[0] = datetime(2026, 7, 17, 0, 0, tzinfo=UTC)
    assert ledger.authorize(_authorization()) == original


def test_idempotency_and_operation_digest_substitutions_conflict(tmp_path: Path) -> None:
    ledger = _ready(tmp_path / "broker.sqlite")
    authorization = _authorization()
    ledger.authorize(authorization)

    with pytest.raises(BrokerConflict, match="different authorization"):
        ledger.authorize(replace(authorization, maximum_charge_cents=124))
    with pytest.raises(BrokerConflict, match="different idempotency"):
        ledger.authorize(replace(authorization, idempotency_key="op-key-2"))


def test_concurrent_exact_authorize_serializes_to_one_operation(tmp_path: Path) -> None:
    path = tmp_path / "broker.sqlite"
    ledger = _ready(path)
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(lambda _: ledger.authorize(_authorization()), range(24)))

    assert {result.operation_id for result in results} == {results[0].operation_id}
    assert ledger.verify_integrity() == 1


def test_dispatch_unknown_bound_and_charge_are_conditional_and_audited(
    tmp_path: Path,
) -> None:
    ledger = _ready(tmp_path / "broker.sqlite")
    authorization = _authorization()
    ledger.authorize(authorization)
    dispatch = BrokerTransition(
        "dispatch-1",
        0,
        BrokerReceiptState.DISPATCH_POSSIBLE,
        attempt_id="attempt-1",
        dispatch_intent=INTENT,
    )
    sent = ledger.transition("tenant-1", "op-key-1", dispatch)
    assert sent.version == 1 and sent.send_marker and sent.attempt_id == "attempt-1"
    assert ledger.transition("tenant-1", "op-key-1", dispatch) == sent

    unknown = ledger.transition(
        "tenant-1",
        "op-key-1",
        BrokerTransition("unknown-1", 1, BrokerReceiptState.UNKNOWN),
    )
    assert unknown.state is BrokerReceiptState.UNKNOWN
    bound = ledger.transition(
        "tenant-1",
        "op-key-1",
        BrokerTransition(
            "bound-1",
            2,
            BrokerReceiptState.UPSTREAM_BOUND,
            evidence_digest="b" * 64,
        ),
    )
    charged = ledger.transition(
        "tenant-1",
        "op-key-1",
        BrokerTransition(
            "charged-1",
            3,
            BrokerReceiptState.CHARGED,
            charge_cents=117,
            evidence_digest="b" * 64,
            output_digest="c" * 64,
        ),
    )
    assert bound.state is BrokerReceiptState.UPSTREAM_BOUND
    assert charged.state is BrokerReceiptState.CHARGED
    assert charged.charge_cents == 117
    assert charged.provider_charge_cents == 117
    assert charged.broker_loss_cents == 0
    delayed_dispatch_replay = ledger.transition("tenant-1", "op-key-1", dispatch)
    assert delayed_dispatch_replay.state is BrokerReceiptState.DISPATCH_POSSIBLE
    assert delayed_dispatch_replay.version == 1
    assert delayed_dispatch_replay.attempt_id == "attempt-1"
    assert ledger.verify_integrity() == 1


def test_provider_overage_charges_client_cap_and_records_broker_loss(tmp_path: Path) -> None:
    ledger = _ready(tmp_path / "broker.sqlite")
    authorization = _authorization()
    ledger.authorize(authorization)
    ledger.transition(
        "tenant-1",
        "op-key-1",
        BrokerTransition(
            "dispatch-1",
            0,
            BrokerReceiptState.DISPATCH_POSSIBLE,
            attempt_id="attempt-1",
            dispatch_intent=INTENT,
        ),
    )
    result = ledger.transition(
        "tenant-1",
        "op-key-1",
        BrokerTransition(
            "charged-1",
            1,
            BrokerReceiptState.CHARGED,
            charge_cents=150,
            evidence_digest="b" * 64,
            output_digest="c" * 64,
        ),
    )
    assert result.charge_cents == authorization.maximum_charge_cents
    assert result.provider_charge_cents == 150
    assert result.broker_loss_cents == 25
    assert ledger.verify_integrity() == 1


def test_command_replay_conflict_stale_version_and_terminal_mutation_fail(
    tmp_path: Path,
) -> None:
    ledger = _ready(tmp_path / "broker.sqlite")
    ledger.authorize(_authorization())
    dispatch = BrokerTransition(
        "dispatch-1",
        0,
        BrokerReceiptState.DISPATCH_POSSIBLE,
        attempt_id="attempt-1",
        dispatch_intent=INTENT,
    )
    ledger.transition("tenant-1", "op-key-1", dispatch)
    with pytest.raises(BrokerConflict, match="different bytes"):
        ledger.transition(
            "tenant-1",
            "op-key-1",
            replace(dispatch, attempt_id="attempt-2"),
        )
    with pytest.raises(BrokerTransitionRefused, match="stale"):
        ledger.transition(
            "tenant-1",
            "op-key-1",
            BrokerTransition("unknown-1", 0, BrokerReceiptState.UNKNOWN),
        )
    with pytest.raises(BrokerTransitionRefused, match="attempt identity is immutable"):
        ledger.transition(
            "tenant-1",
            "op-key-1",
            BrokerTransition(
                "unknown-with-new-attempt",
                1,
                BrokerReceiptState.UNKNOWN,
                attempt_id="attempt-2",
            ),
        )

    terminal = ledger.transition(
        "tenant-1",
        "op-key-1",
        BrokerTransition(
            "charged-1",
            1,
            BrokerReceiptState.CHARGED,
            charge_cents=1,
            evidence_digest="b" * 64,
            output_digest="c" * 64,
        ),
    )
    assert terminal.state is BrokerReceiptState.CHARGED
    with pytest.raises(BrokerTransitionRefused, match="terminal"):
        ledger.transition(
            "tenant-1",
            "op-key-1",
            BrokerTransition("later", 2, BrokerReceiptState.UNKNOWN),
        )


def test_not_found_requires_unexpired_authorized_without_send_marker(tmp_path: Path) -> None:
    path = tmp_path / "broker.sqlite"
    ledger = _ready(path)
    ledger.authorize(_authorization())
    result = ledger.transition(
        "tenant-1",
        "op-key-1",
        BrokerTransition(
            "missing-1",
            0,
            BrokerReceiptState.NOT_FOUND,
            charge_cents=0,
            evidence_digest="b" * 64,
        ),
    )
    assert result.state is BrokerReceiptState.NOT_FOUND

    expired_path = tmp_path / "expired.sqlite"
    clock = [NOW]
    expired = PrimaryBrokerLedger(expired_path, clock=lambda: clock[0])
    expired.ensure_schema()
    expired.authorize(_authorization())
    clock[0] = datetime(2026, 7, 17, 0, 0, tzinfo=UTC)
    with pytest.raises(BrokerTransitionRefused, match="unexpired"):
        expired.transition(
            "tenant-1",
            "op-key-1",
            BrokerTransition(
                "missing-1",
                0,
                BrokerReceiptState.NOT_FOUND,
                charge_cents=0,
                evidence_digest="b" * 64,
            ),
        )


def test_not_found_uses_one_clock_read_for_validation_and_audit(tmp_path: Path) -> None:
    path = tmp_path / "broker.sqlite"
    readings = iter(
        [
            NOW,
            datetime(2026, 7, 16, 23, 59, 59, tzinfo=UTC),
            datetime(2026, 7, 17, 0, 0, tzinfo=UTC),
        ]
    )
    ledger = PrimaryBrokerLedger(path, clock=lambda: next(readings))
    ledger.ensure_schema()
    ledger.authorize(_authorization())
    result = ledger.transition(
        "tenant-1",
        "op-key-1",
        BrokerTransition(
            "missing-1",
            0,
            BrokerReceiptState.NOT_FOUND,
            charge_cents=0,
            evidence_digest="b" * 64,
        ),
    )
    assert result.updated_at == "2026-07-16T23:59:59Z"
    assert ledger.verify_integrity() == 1


def test_not_found_is_forbidden_after_dispatch_marker(tmp_path: Path) -> None:
    ledger = _ready(tmp_path / "broker.sqlite")
    ledger.authorize(_authorization())
    ledger.transition(
        "tenant-1",
        "op-key-1",
        BrokerTransition(
            "dispatch-1",
            0,
            BrokerReceiptState.DISPATCH_POSSIBLE,
            attempt_id="attempt-1",
            dispatch_intent=INTENT,
        ),
    )
    with pytest.raises(BrokerTransitionRefused, match="forbidden"):
        ledger.transition(
            "tenant-1",
            "op-key-1",
            BrokerTransition(
                "missing-1",
                1,
                BrokerReceiptState.NOT_FOUND,
                charge_cents=0,
                evidence_digest="b" * 64,
            ),
        )


def test_lock_timeout_is_unavailable_never_authoritative_missing(tmp_path: Path) -> None:
    path = tmp_path / "broker.sqlite"
    _ready(path)
    context = multiprocessing.get_context("spawn")
    ready: multiprocessing.Queue[bool] = context.Queue()
    release: multiprocessing.Queue[bool] = context.Queue()
    process = context.Process(target=_hold_key_lock, args=(str(path), ready, release))
    process.start()
    assert ready.get(timeout=5) is True
    try:
        with pytest.raises(BrokerUnavailable, match="timed out"):
            _ledger(path, timeout=0.05).lookup("tenant-1", "missing-key")
    finally:
        release.put(True)
        process.join(timeout=5)
    assert process.exitcode == 0


def test_lock_file_setup_failure_is_unavailable(tmp_path: Path) -> None:
    path = tmp_path / "broker.sqlite"
    ledger = _ready(path)
    lock_dir = Path(f"{path.resolve()}.broker-locks")
    for child in lock_dir.iterdir():
        child.unlink()
    lock_dir.rmdir()
    lock_dir.write_text("not a directory", encoding="ascii")
    with pytest.raises(BrokerUnavailable, match="lock authority"):
        ledger.lookup("tenant-1", "key-1")


def test_flock_authority_failure_is_unavailable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ledger = _ready(tmp_path / "broker.sqlite")
    real_flock = broker_ledger_module.fcntl.flock

    def fail_lock(descriptor: int, operation: int) -> None:
        if operation & broker_ledger_module.fcntl.LOCK_NB:
            raise OSError(errno.ENOLCK, "no locks available")
        real_flock(descriptor, operation)

    monkeypatch.setattr(broker_ledger_module.fcntl, "flock", fail_lock)
    with pytest.raises(BrokerUnavailable, match="lock authority"):
        ledger.lookup("tenant-1", "key-1")


def test_transition_rejects_charge_outside_sqlite_integer_authority() -> None:
    with pytest.raises(ValueError, match="integer cents"):
        BrokerTransition(
            "charged-1",
            1,
            BrokerReceiptState.CHARGED,
            charge_cents=1 << 63,
            evidence_digest="b" * 64,
            output_digest="c" * 64,
        )


def test_failed_audit_append_rolls_back_state_and_command(tmp_path: Path) -> None:
    ledger = _ready(tmp_path / "broker.sqlite")
    original = ledger.authorize(_authorization())
    real_append = ledger._append_event  # noqa: SLF001

    def fail_append(*args: object, **kwargs: object) -> None:
        raise sqlite3.OperationalError("injected crash")

    ledger._append_event = fail_append  # type: ignore[method-assign]  # noqa: SLF001
    with pytest.raises(BrokerUnavailable, match="transaction failed"):
        ledger.transition(
            "tenant-1",
            "op-key-1",
            BrokerTransition(
                "dispatch-1",
                0,
                BrokerReceiptState.DISPATCH_POSSIBLE,
                attempt_id="attempt-1",
                dispatch_intent=INTENT,
            ),
        )
    ledger._append_event = real_append  # type: ignore[method-assign]  # noqa: SLF001
    assert ledger.lookup("tenant-1", "op-key-1").operation == original
    assert ledger.verify_integrity() == 1


def test_database_triggers_enforce_append_only_audit_and_terminal_rows(
    tmp_path: Path,
) -> None:
    path = tmp_path / "broker.sqlite"
    ledger = _ready(path)
    ledger.authorize(_authorization())
    ledger.transition(
        "tenant-1",
        "op-key-1",
        BrokerTransition(
            "missing-1",
            0,
            BrokerReceiptState.NOT_FOUND,
            charge_cents=0,
            evidence_digest="b" * 64,
        ),
    )
    connection = sqlite3.connect(path)
    with pytest.raises(sqlite3.IntegrityError, match="append-only"):
        connection.execute("DELETE FROM broker_audit")
    with pytest.raises(sqlite3.IntegrityError, match="immutable"):
        connection.execute("UPDATE broker_operations SET state='authorized'")
    with pytest.raises(sqlite3.IntegrityError, match="durable"):
        connection.execute("DELETE FROM broker_operations")
    connection.close()


def test_existing_lookup_and_replay_refuse_corrupted_authority(tmp_path: Path) -> None:
    path = tmp_path / "broker.sqlite"
    ledger = _ready(path)
    ledger.authorize(_authorization())
    connection = sqlite3.connect(path)
    connection.execute("UPDATE broker_operations SET authorization_digest=?", ("d" * 64,))
    connection.commit()
    connection.close()
    with pytest.raises(BrokerIntegrityError, match="authorization digest differs"):
        ledger.lookup("tenant-1", "op-key-1")
    with pytest.raises(BrokerIntegrityError, match="authorization digest differs"):
        ledger.authorize(_authorization())


def test_corrupted_authorization_json_is_integrity_failure_not_caller_conflict(
    tmp_path: Path,
) -> None:
    path = tmp_path / "broker.sqlite"
    ledger = _ready(path)
    ledger.authorize(_authorization())
    connection = sqlite3.connect(path)
    connection.execute("UPDATE broker_operations SET authorization_json='{}'")
    connection.commit()
    connection.close()
    with pytest.raises(BrokerIntegrityError, match="operation row is malformed"):
        ledger.authorize(_authorization())


def test_integrity_binds_canonical_command_and_result_bytes(tmp_path: Path) -> None:
    path = tmp_path / "broker.sqlite"
    ledger = _ready(path)
    ledger.authorize(_authorization())
    ledger.transition(
        "tenant-1",
        "op-key-1",
        BrokerTransition(
            "dispatch-1",
            0,
            BrokerReceiptState.DISPATCH_POSSIBLE,
            attempt_id="attempt-1",
            dispatch_intent=INTENT,
        ),
    )
    ledger.transition(
        "tenant-1",
        "op-key-1",
        BrokerTransition(
            "charged-1",
            1,
            BrokerReceiptState.CHARGED,
            charge_cents=117,
            evidence_digest="b" * 64,
            output_digest="c" * 64,
        ),
    )
    connection = sqlite3.connect(path)
    connection.execute("DROP TRIGGER broker_terminal_no_update")
    connection.execute(
        "UPDATE broker_operations SET charge_cents=116,provider_charge_cents=116,"
        "broker_loss_cents=0,evidence_digest=?,output_digest=?",
        ("d" * 64, "e" * 64),
    )
    connection.execute(
        "CREATE TRIGGER broker_terminal_no_update BEFORE UPDATE ON broker_operations "
        "WHEN OLD.state IN ('charged','not_found') "
        "BEGIN SELECT RAISE(ABORT, 'terminal broker operation is immutable'); END"
    )
    connection.commit()
    connection.close()
    with pytest.raises(BrokerIntegrityError, match="result tip differs"):
        ledger.verify_integrity()


@pytest.mark.parametrize(
    ("statement", "message"),
    [
        (
            "UPDATE broker_operations SET authorization_digest='" + "d" * 64 + "'",
            "authorization digest differs",
        ),
        ("UPDATE broker_audit SET event_hash='" + "d" * 64 + "'", "event hash differs"),
        ("DELETE FROM broker_audit", "audit length differs"),
    ],
)
def test_integrity_verifier_rejects_authority_and_audit_corruption(
    tmp_path: Path, statement: str, message: str
) -> None:
    path = tmp_path / "broker.sqlite"
    ledger = _ready(path)
    ledger.authorize(_authorization())
    connection = sqlite3.connect(path)
    if "broker_audit" in statement:
        connection.execute("DROP TRIGGER broker_audit_no_update")
        connection.execute("DROP TRIGGER broker_audit_no_delete")
    connection.execute(statement)
    if "broker_audit" in statement:
        connection.execute(
            "CREATE TRIGGER broker_audit_no_update BEFORE UPDATE ON broker_audit "
            "BEGIN SELECT RAISE(ABORT, 'broker audit is append-only'); END"
        )
        connection.execute(
            "CREATE TRIGGER broker_audit_no_delete BEFORE DELETE ON broker_audit "
            "BEGIN SELECT RAISE(ABORT, 'broker audit is append-only'); END"
        )
    connection.commit()
    connection.close()

    with pytest.raises(BrokerIntegrityError, match=message):
        ledger.verify_integrity()


def test_unknown_schema_version_fails_closed(tmp_path: Path) -> None:
    path = tmp_path / "broker.sqlite"
    ledger = _ready(path)
    connection = sqlite3.connect(path)
    connection.execute("PRAGMA ignore_check_constraints=ON")
    connection.execute("UPDATE broker_schema SET version=99")
    connection.commit()
    connection.close()
    with pytest.raises(BrokerIntegrityError, match="unsupported"):
        ledger.ensure_schema()
    with pytest.raises(BrokerIntegrityError, match="unsupported"):
        ledger.lookup("tenant-1", "key-1")


def test_startup_refuses_existing_schema_without_immutability_trigger(
    tmp_path: Path,
) -> None:
    path = tmp_path / "broker.sqlite"
    ledger = _ready(path)
    connection = sqlite3.connect(path)
    connection.execute("DROP TRIGGER broker_audit_no_update")
    connection.commit()
    connection.close()
    with pytest.raises(BrokerIntegrityError, match="trigger definitions differ"):
        ledger.ensure_schema()


def test_startup_refuses_weakened_trigger_under_expected_name(tmp_path: Path) -> None:
    path = tmp_path / "broker.sqlite"
    ledger = _ready(path)
    connection = sqlite3.connect(path)
    connection.execute("DROP TRIGGER broker_audit_no_update")
    connection.execute(
        "CREATE TRIGGER broker_audit_no_update BEFORE UPDATE ON broker_audit BEGIN SELECT 1; END"
    )
    connection.commit()
    connection.close()
    with pytest.raises(BrokerIntegrityError, match="trigger definitions differ"):
        ledger.ensure_schema()


def test_verifier_rejects_orphaned_command_and_audit_authority(tmp_path: Path) -> None:
    path = tmp_path / "broker.sqlite"
    ledger = _ready(path)
    ledger.authorize(_authorization())
    connection = sqlite3.connect(path)
    connection.execute("DROP TRIGGER broker_operations_no_delete")
    connection.execute("DELETE FROM broker_operations")
    connection.execute(
        "CREATE TRIGGER broker_operations_no_delete BEFORE DELETE ON broker_operations "
        "BEGIN SELECT RAISE(ABORT, 'broker operations are durable'); END"
    )
    connection.commit()
    connection.close()
    with pytest.raises(BrokerIntegrityError, match="orphaned authority"):
        ledger.verify_integrity()


def test_verifier_rejects_coherently_rehashed_result_that_differs_from_command(
    tmp_path: Path,
) -> None:
    path = tmp_path / "broker.sqlite"
    ledger = _ready(path)
    ledger.authorize(_authorization())
    ledger.transition(
        "tenant-1",
        "op-key-1",
        BrokerTransition(
            "dispatch-1",
            0,
            BrokerReceiptState.DISPATCH_POSSIBLE,
            attempt_id="attempt-1",
            dispatch_intent=INTENT,
        ),
    )
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    connection.execute("DROP TRIGGER broker_audit_no_update")
    event = connection.execute("SELECT * FROM broker_audit WHERE sequence=1").fetchone()
    changed_result = json.loads(event["result_json"])
    changed_result["attempt_id"] = "attempt-2"
    result_json = json.dumps(changed_result, sort_keys=True, separators=(",", ":"))
    result_digest = broker_ledger_module.hashlib.sha256(result_json.encode("ascii")).hexdigest()
    event_hash = broker_ledger_module._event_hash(  # noqa: SLF001
        operation_id=event["operation_id"],
        sequence=event["sequence"],
        from_state=event["from_state"],
        to_state=event["to_state"],
        version=event["version"],
        command_id=event["command_id"],
        command_digest=event["command_digest"],
        result_digest=result_digest,
        recorded_at=event["recorded_at"],
        previous_hash=event["previous_hash"],
    )
    connection.execute(
        "UPDATE broker_audit SET result_json=?,result_digest=?,event_hash=? WHERE sequence=1",
        (result_json, result_digest, event_hash),
    )
    connection.execute("UPDATE broker_operations SET attempt_id='attempt-2'")
    connection.execute(
        "CREATE TRIGGER broker_audit_no_update BEFORE UPDATE ON broker_audit "
        "BEGIN SELECT RAISE(ABORT, 'broker audit is append-only'); END"
    )
    connection.commit()
    connection.close()
    with pytest.raises(BrokerIntegrityError, match="command semantics differ"):
        ledger.verify_integrity()
