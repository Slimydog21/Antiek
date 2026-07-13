from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path

import duckdb
import pytest

from substrate.midnight_oil.contracts import (
    ResearchAcceptancePolicy,
    research_acceptance_policy_authority_fields,
)
from substrate.midnight_oil.job_store import (
    SCHEMA_VERSION,
    DurableOwnerJobStore,
    InvalidStoredJob,
    OperationState,
    OwnerJob,
    StoreConstructionError,
    construct_job_store,
)
from substrate.midnight_oil.job_store import (
    TestOnlyInMemoryOwnerJobStore as MemoryStore,
)


def _job(owner: str = "owner-a", job_id: str = "job-1") -> OwnerJob:
    return OwnerJob(
        owner_user_id=owner,
        job_id=job_id,
        state_version=0,
        approved_ceiling_cents=None,
        consent_receipt_id=None,
        consent_config_hash=None,
        consent_issued_at_ms=None,
        consent_expires_at_ms=None,
        consent_claimed_at_ms=None,
        operation_id=None,
        operation_state=OperationState.NONE,
        dispatch_started_at_ms=None,
        dispatched_at_ms=None,
        completed_at_ms=None,
        payload={
            "goals": ["prove restart"],
            "display_usd": 123.45,
            **research_acceptance_policy_authority_fields(
                ResearchAcceptancePolicy()
            ),
        },
    )


def _publish(store: object, *, expected_version: int = 0):
    return store.publish_consent(  # type: ignore[attr-defined,no-any-return]
        owner_user_id="owner-a",
        job_id="job-1",
        expected_version=expected_version,
        operation_id="operation-1",
        approved_ceiling_cents=12_345,
        consent_receipt_id="receipt-safe-metadata",
        consent_config_hash="config-safe-metadata",
        consent_issued_at_ms=100,
        consent_expires_at_ms=10_000,
    )


def test_restart_round_trip_preserves_authority_and_owner_scope(tmp_path: Path) -> None:
    path = tmp_path / "jobs.duckdb"
    first = DurableOwnerJobStore(path)
    expected = _job()
    first.put_job(expected)

    restarted = DurableOwnerJobStore(path)
    assert restarted.get_job(owner_user_id="owner-a", job_id="job-1") == expected
    assert restarted.get_job(owner_user_id="owner-b", job_id="job-1") is None
    assert restarted.get_job(owner_user_id="owner-a", job_id="missing") is None


def test_duplicate_insert_cannot_blindly_replace_authority(tmp_path: Path) -> None:
    store = DurableOwnerJobStore(tmp_path / "jobs.duckdb")
    original = _job()
    store.put_job(original)
    with pytest.raises(ValueError, match="compare_and_set"):
        store.put_job(replace(original, payload={"goals": ["changed"]}))
    assert store.get_job(owner_user_id="owner-a", job_id="job-1") == original


@pytest.mark.parametrize(
    ("overrides", "match"),
    [
        ({"state_version": -1}, "state_version"),
        ({"operation_state": "invented"}, "closed state"),
        ({"state_version": True}, "state_version"),
    ],
)
def test_authority_input_is_closed(overrides: dict[str, object], match: str) -> None:
    store = MemoryStore()
    with pytest.raises(ValueError, match=match):
        store.put_job(replace(_job(), **overrides))  # type: ignore[arg-type]


def test_reconciliation_cannot_claim_dispatch_without_consent_claim() -> None:
    store = MemoryStore()
    with pytest.raises(ValueError, match="authorization order"):
        store.put_job(
            replace(
                _job(),
                state_version=3,
                approved_ceiling_cents=100,
                consent_receipt_id="receipt",
                consent_config_hash="c" * 64,
                consent_issued_at_ms=100,
                consent_expires_at_ms=1_000,
                operation_id="operation-1",
                operation_state=OperationState.FAILED_RECONCILE,
                dispatch_started_at_ms=300,
                completed_at_ms=400,
            )
        )


def test_cas_rejects_stale_version_state_operation_and_owner_without_mutation(
    tmp_path: Path,
) -> None:
    store = DurableOwnerJobStore(tmp_path / "jobs.duckdb")
    store.put_job(_job())
    won = _publish(store)
    assert won.applied is True
    expected = won.job
    assert expected is not None and expected.state_version == 1

    attempts = (
        dict(
            expected_version=0,
            expected_state=OperationState.CONSENT_ISSUED,
            operation_id="operation-1",
            next_state=OperationState.QUEUED,
            consent_claimed_at_ms=101,
        ),
        dict(
            expected_version=1,
            expected_state=OperationState.QUEUED,
            operation_id="operation-1",
            next_state=OperationState.RUNNING,
            dispatch_started_at_ms=102,
        ),
        dict(
            expected_version=1,
            expected_state=OperationState.CONSENT_ISSUED,
            operation_id="operation-2",
            next_state=OperationState.QUEUED,
            consent_claimed_at_ms=101,
        ),
    )
    for attempt in attempts:
        rejected = store.compare_and_set(
            owner_user_id="owner-a",
            job_id="job-1",
            **attempt,
        )
        assert rejected.applied is False
        assert store.get_job(owner_user_id="owner-a", job_id="job-1") == expected
    cross_owner = store.compare_and_set(
        owner_user_id="owner-b",
        job_id="job-1",
        expected_version=1,
        expected_state=OperationState.CONSENT_ISSUED,
        operation_id="operation-1",
        next_state=OperationState.QUEUED,
        consent_claimed_at_ms=101,
    )
    assert cross_owner.applied is False and cross_owner.job is None


def test_fifty_separate_store_contenders_have_one_winner(tmp_path: Path) -> None:
    path = tmp_path / "jobs.duckdb"
    DurableOwnerJobStore(path).put_job(_job())
    barrier = threading.Barrier(50)

    def contend(index: int) -> bool:
        contender = DurableOwnerJobStore(path)
        barrier.wait()
        return contender.publish_consent(
            owner_user_id="owner-a",
            job_id="job-1",
            expected_version=0,
            operation_id=f"operation-{index}",
            approved_ceiling_cents=12_345,
            consent_receipt_id=f"receipt-{index}",
            consent_config_hash="config-safe-metadata",
            consent_issued_at_ms=100,
            consent_expires_at_ms=10_000,
        ).applied

    with ThreadPoolExecutor(max_workers=50) as pool:
        results = list(pool.map(contend, range(50)))
    assert sum(results) == 1
    final = DurableOwnerJobStore(path).get_job(owner_user_id="owner-a", job_id="job-1")
    assert final is not None and final.state_version == 1


def test_legacy_float_migrates_once_with_decimal_floor_and_is_idempotent(tmp_path: Path) -> None:
    path = tmp_path / "legacy.duckdb"
    connection = duckdb.connect(str(path))
    connection.execute(
        "CREATE TABLE midnight_oil_jobs ("
        "owner_user_id TEXT, job_id TEXT, approved_ceiling_usd DOUBLE, payload_json TEXT)"
    )
    connection.execute(
        "INSERT INTO midnight_oil_jobs VALUES (?, ?, ?, ?)",
        ["owner-a", "job-1", 12.349, '{"display_usd":12.349}'],
    )
    connection.close()

    migrated = DurableOwnerJobStore(path)
    row = migrated.get_job(owner_user_id="owner-a", job_id="job-1")
    assert row is not None and row.approved_ceiling_cents is None
    assert row.payload["display_usd"] == 12.349
    assert DurableOwnerJobStore(path).get_job(owner_user_id="owner-a", job_id="job-1") == row
    inspection = duckdb.connect(str(path), read_only=True)
    try:
        columns = {
            entry[1]
            for entry in inspection.execute("PRAGMA table_info('midnight_oil_jobs')").fetchall()
        }
        assert "approved_ceiling_usd" not in columns
        assert inspection.execute("SELECT schema_version FROM midnight_oil_jobs").fetchone() == (
            SCHEMA_VERSION,
        )
    finally:
        inspection.close()


def test_exact_v1_safe_ready_row_migrates_and_active_row_fails_closed(tmp_path: Path) -> None:
    ddl = (
        "CREATE TABLE midnight_oil_jobs (owner_user_id TEXT, job_id TEXT, state_version BIGINT, "
        "approved_ceiling_cents BIGINT, consent_receipt_id TEXT, consent_config_hash TEXT, "
        "consent_claimed_at_ms BIGINT, operation_id TEXT, operation_state TEXT, "
        "dispatch_started_at_ms BIGINT, dispatched_at_ms BIGINT, completed_at_ms BIGINT, "
        "payload_json TEXT, schema_version INTEGER)"
    )
    safe_path = tmp_path / "v1-safe.duckdb"
    connection = duckdb.connect(str(safe_path))
    connection.execute(ddl)
    connection.execute(
        "INSERT INTO midnight_oil_jobs VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [
            "owner-a",
            "job-1",
            0,
            None,
            None,
            None,
            None,
            None,
            "ready",
            None,
            None,
            None,
            '{"goals":["safe"]}',
            1,
        ],
    )
    connection.close()
    migrated = DurableOwnerJobStore(safe_path).get_job(owner_user_id="owner-a", job_id="job-1")
    assert migrated is not None and migrated.operation_state is OperationState.NONE

    active_path = tmp_path / "v1-active.duckdb"
    connection = duckdb.connect(str(active_path))
    connection.execute(ddl)
    connection.execute(
        "INSERT INTO midnight_oil_jobs VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [
            "owner-a",
            "job-1",
            1,
            100,
            "receipt",
            "config",
            10,
            "operation",
            "claimed",
            None,
            None,
            None,
            '{"goals":["unsafe"]}',
            1,
        ],
    )
    connection.close()
    with pytest.raises(InvalidStoredJob, match="reconciliation"):
        DurableOwnerJobStore(active_path)
    check = duckdb.connect(str(active_path), read_only=True)
    try:
        assert check.execute("SELECT operation_state FROM midnight_oil_jobs").fetchone() == (
            "claimed",
        )
    finally:
        check.close()


def test_hostile_legacy_owner_or_state_fails_closed_without_destroying_source(
    tmp_path: Path,
) -> None:
    for suffix, ddl, values in (
        ("owner", "job_id TEXT, payload_json TEXT", ["job-1", "{}"]),
        (
            "state",
            "owner_user_id TEXT, job_id TEXT, operation_state TEXT, payload_json TEXT",
            ["owner-a", "job-1", "surprise", "{}"],
        ),
    ):
        path = tmp_path / f"bad-{suffix}.duckdb"
        connection = duckdb.connect(str(path))
        connection.execute(f"CREATE TABLE midnight_oil_jobs ({ddl})")
        connection.execute(
            f"INSERT INTO midnight_oil_jobs VALUES ({', '.join('?' for _ in values)})", values
        )
        connection.close()
        with pytest.raises((InvalidStoredJob, ValueError)):
            DurableOwnerJobStore(path)
        check = duckdb.connect(str(path), read_only=True)
        try:
            assert check.execute("SELECT COUNT(*) FROM midnight_oil_jobs").fetchone() == (1,)
        finally:
            check.close()


def test_production_construction_fails_closed_and_memory_is_explicit() -> None:
    with pytest.raises(StoreConstructionError, match="durable"):
        construct_job_store(durable_path=None, production=True)
    with pytest.raises(StoreConstructionError, match="durable"):
        DurableOwnerJobStore(":memory:")
    assert isinstance(
        construct_job_store(durable_path=None, production=False),
        MemoryStore,
    )


def test_schema_and_rows_contain_no_token_or_key_authority(tmp_path: Path) -> None:
    path = tmp_path / "jobs.duckdb"
    store = DurableOwnerJobStore(path)
    store.put_job(_job())
    connection = duckdb.connect(str(path), read_only=True)
    try:
        columns = [
            str(row[1]).lower()
            for row in connection.execute("PRAGMA table_info('midnight_oil_jobs')").fetchall()
        ]
        serialized = " ".join(
            str(value).lower()
            for value in connection.execute("SELECT * FROM midnight_oil_jobs").fetchone()
        )
    finally:
        connection.close()
    assert all("token" not in column and "key" not in column for column in columns)
    assert "secret" not in serialized and "api_key" not in serialized


def test_payload_rejects_sensitive_fields_and_state_machine_is_closed(tmp_path: Path) -> None:
    store = DurableOwnerJobStore(tmp_path / "jobs.duckdb")
    with pytest.raises(ValueError, match="closed job configuration"):
        store.put_job(replace(_job(), payload={"provider_token": "must-not-persist"}))
    store.put_job(_job())
    with pytest.raises(ValueError, match="not allowed"):
        store.compare_and_set(
            owner_user_id="owner-a",
            job_id="job-1",
            expected_version=0,
            expected_state=OperationState.NONE,
            operation_id="operation-1",
            next_state=OperationState.COMPLETE,
        )
    assert store.get_job(owner_user_id="owner-a", job_id="job-1") == _job()


def test_publish_consent_atomically_binds_complete_authority_and_expiry(tmp_path: Path) -> None:
    store = DurableOwnerJobStore(tmp_path / "jobs.duckdb")
    store.put_job(_job())
    result = _publish(store)
    assert result.applied and result.job is not None
    assert result.job.operation_state is OperationState.CONSENT_ISSUED
    assert result.job.approved_ceiling_cents == 12_345
    assert result.job.consent_expires_at_ms == 10_000
    assert _publish(store).applied is False


def test_state_timestamps_are_required_and_monotonic() -> None:
    store = MemoryStore()
    store.put_job(_job())
    issued = _publish(store).job
    assert issued is not None
    with pytest.raises(ValueError, match="immutable audit timestamps"):
        store.compare_and_set(
            owner_user_id="owner-a",
            job_id="job-1",
            expected_version=1,
            expected_state=OperationState.CONSENT_ISSUED,
            operation_id="operation-1",
            next_state=OperationState.QUEUED,
        )
    queued = store.compare_and_set(
        owner_user_id="owner-a",
        job_id="job-1",
        expected_version=1,
        expected_state=OperationState.CONSENT_ISSUED,
        operation_id="operation-1",
        next_state=OperationState.QUEUED,
        consent_claimed_at_ms=200,
    ).job
    assert queued is not None
    with pytest.raises(ValueError, match="monotonic"):
        store.compare_and_set(
            owner_user_id="owner-a",
            job_id="job-1",
            expected_version=2,
            expected_state=OperationState.QUEUED,
            operation_id="operation-1",
            next_state=OperationState.RUNNING,
            dispatch_started_at_ms=199,
        )
    with pytest.raises(ValueError, match="immutable audit timestamps"):
        store.compare_and_set(
            owner_user_id="owner-a",
            job_id="job-1",
            expected_version=2,
            expected_state=OperationState.QUEUED,
            operation_id="operation-1",
            next_state=OperationState.RUNNING,
            consent_claimed_at_ms=201,
            dispatch_started_at_ms=202,
        )


def test_expired_consent_cannot_publish_or_queue() -> None:
    store = MemoryStore()
    store.put_job(_job())
    with pytest.raises(ValueError, match="expiry|complete consent authority"):
        store.publish_consent(
            owner_user_id="owner-a",
            job_id="job-1",
            expected_version=0,
            operation_id="operation-1",
            approved_ceiling_cents=100,
            consent_receipt_id="receipt",
            consent_config_hash="config",
            consent_issued_at_ms=100,
            consent_expires_at_ms=100,
        )
    _publish(store)
    for invalid_claim_time in (99, 10_000, 10_001):
        with pytest.raises(ValueError, match="validity interval"):
            store.compare_and_set(
                owner_user_id="owner-a",
                job_id="job-1",
                expected_version=1,
                expected_state=OperationState.CONSENT_ISSUED,
                operation_id="operation-1",
                next_state=OperationState.QUEUED,
                consent_claimed_at_ms=invalid_claim_time,
            )


@pytest.mark.parametrize("durable", [False, True])
def test_unclaimed_expired_consent_can_be_atomically_replaced(
    tmp_path: Path, durable: bool
) -> None:
    store = DurableOwnerJobStore(tmp_path / "renewal.duckdb") if durable else MemoryStore()
    store.put_job(_job())
    _publish(store)
    too_early = store.replace_expired_consent(
        owner_user_id="owner-a",
        job_id="job-1",
        expected_version=1,
        now_ms=9_999,
        operation_id="operation-2",
        approved_ceiling_cents=12_345,
        consent_receipt_id="receipt-renewed",
        consent_config_hash="config-safe-metadata",
        consent_issued_at_ms=9_999,
        consent_expires_at_ms=20_000,
    )
    assert too_early.applied is False
    renewed = store.replace_expired_consent(
        owner_user_id="owner-a",
        job_id="job-1",
        expected_version=1,
        now_ms=10_000,
        operation_id="operation-2",
        approved_ceiling_cents=12_345,
        consent_receipt_id="receipt-renewed",
        consent_config_hash="config-safe-metadata",
        consent_issued_at_ms=10_000,
        consent_expires_at_ms=20_000,
    )
    assert renewed.applied is True
    assert renewed.job is not None
    assert renewed.job.state_version == 2
    assert renewed.job.operation_state is OperationState.CONSENT_ISSUED
    assert renewed.job.operation_id == "operation-2"
    assert renewed.job.consent_receipt_id == "receipt-renewed"


def test_job_id_is_globally_unique_before_owner_unqualified_ledger_wiring(tmp_path: Path) -> None:
    store = DurableOwnerJobStore(tmp_path / "jobs.duckdb")
    store.put_job(_job(owner="owner-a", job_id="shared"))
    with pytest.raises(duckdb.ConstraintException):
        store.put_job(_job(owner="owner-b", job_id="shared"))
    memory = MemoryStore()
    memory.put_job(_job(owner="owner-a", job_id="shared"))
    with pytest.raises(ValueError, match="globally unique"):
        memory.put_job(_job(owner="owner-b", job_id="shared"))


def test_current_columns_without_authority_constraints_fail_startup(tmp_path: Path) -> None:
    path = tmp_path / "constraintless.duckdb"
    DurableOwnerJobStore(path)
    connection = duckdb.connect(str(path))
    connection.execute("CREATE TABLE unsafe AS SELECT * FROM midnight_oil_jobs")
    connection.execute("DROP TABLE midnight_oil_jobs")
    connection.execute("ALTER TABLE unsafe RENAME TO midnight_oil_jobs")
    connection.close()
    with pytest.raises(InvalidStoredJob, match="constraints"):
        DurableOwnerJobStore(path)


def test_test_adapter_snapshots_cannot_mutate_authority() -> None:
    store = MemoryStore()
    store.put_job(_job())
    snapshot = store.get_job(owner_user_id="owner-a", job_id="job-1")
    assert snapshot is not None
    snapshot.payload["goals"] = ["attacker mutation"]
    reloaded = store.get_job(owner_user_id="owner-a", job_id="job-1")
    assert reloaded is not None and reloaded.payload["goals"] == ["prove restart"]
