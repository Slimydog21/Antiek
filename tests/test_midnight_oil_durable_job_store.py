from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path

import duckdb
import pytest

from substrate.midnight_oil.job_store import (
    MAX_APPROVED_CEILING_CENTS,
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
        approved_ceiling_cents=12_345,
        consent_receipt_id="receipt-safe-metadata",
        consent_config_hash="config-safe-metadata",
        consent_claimed_at_ms=100,
        operation_id=None,
        operation_state=OperationState.READY,
        dispatch_started_at_ms=None,
        dispatched_at_ms=None,
        completed_at_ms=None,
        payload={"goals": ["prove restart"], "display_usd": 123.45},
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
        store.put_job(replace(original, approved_ceiling_cents=1))
    assert store.get_job(owner_user_id="owner-a", job_id="job-1") == original


@pytest.mark.parametrize(
    ("overrides", "match"),
    [
        ({"approved_ceiling_cents": 1.5}, "authority bounds"),
        ({"approved_ceiling_cents": 0}, "authority bounds"),
        ({"approved_ceiling_cents": MAX_APPROVED_CEILING_CENTS + 1}, "authority bounds"),
        ({"operation_state": "invented"}, "closed state"),
        ({"state_version": True}, "state_version"),
    ],
)
def test_authority_input_is_closed(overrides: dict[str, object], match: str) -> None:
    store = MemoryStore()
    with pytest.raises(ValueError, match=match):
        store.put_job(replace(_job(), **overrides))  # type: ignore[arg-type]


def test_cas_rejects_stale_version_state_operation_and_owner_without_mutation(
    tmp_path: Path,
) -> None:
    store = DurableOwnerJobStore(tmp_path / "jobs.duckdb")
    store.put_job(_job())
    won = store.compare_and_set(
        owner_user_id="owner-a",
        job_id="job-1",
        expected_version=0,
        expected_state=OperationState.READY,
        operation_id="operation-1",
        next_state=OperationState.CLAIMED,
    )
    assert won.applied is True
    expected = won.job
    assert expected is not None and expected.state_version == 1

    attempts = (
        dict(
            expected_version=0,
            expected_state=OperationState.CLAIMED,
            operation_id="operation-1",
            next_state=OperationState.DISPATCHING,
        ),
        dict(
            expected_version=1,
            expected_state=OperationState.READY,
            operation_id="operation-1",
            next_state=OperationState.CLAIMED,
        ),
        dict(
            expected_version=1,
            expected_state=OperationState.CLAIMED,
            operation_id="operation-2",
            next_state=OperationState.DISPATCHING,
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
        expected_state=OperationState.CLAIMED,
        operation_id="operation-1",
        next_state=OperationState.DISPATCHING,
    )
    assert cross_owner.applied is False and cross_owner.job is None


def test_fifty_separate_store_contenders_have_one_winner(tmp_path: Path) -> None:
    path = tmp_path / "jobs.duckdb"
    DurableOwnerJobStore(path).put_job(_job())
    barrier = threading.Barrier(50)

    def contend(index: int) -> bool:
        contender = DurableOwnerJobStore(path)
        barrier.wait()
        return contender.compare_and_set(
            owner_user_id="owner-a",
            job_id="job-1",
            expected_version=0,
            expected_state=OperationState.READY,
            operation_id=f"operation-{index}",
            next_state=OperationState.CLAIMED,
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
    assert row is not None and row.approved_ceiling_cents == 1_234
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
    with pytest.raises(ValueError, match="token, key, or secret"):
        store.put_job(replace(_job(), payload={"provider_token": "must-not-persist"}))
    store.put_job(_job())
    with pytest.raises(ValueError, match="not allowed"):
        store.compare_and_set(
            owner_user_id="owner-a",
            job_id="job-1",
            expected_version=0,
            expected_state=OperationState.READY,
            operation_id="operation-1",
            next_state=OperationState.COMPLETE,
        )
    assert store.get_job(owner_user_id="owner-a", job_id="job-1") == _job()


def test_test_adapter_snapshots_cannot_mutate_authority() -> None:
    store = MemoryStore()
    store.put_job(_job())
    snapshot = store.get_job(owner_user_id="owner-a", job_id="job-1")
    assert snapshot is not None
    snapshot.payload["goals"] = ["attacker mutation"]
    reloaded = store.get_job(owner_user_id="owner-a", job_id="job-1")
    assert reloaded is not None and reloaded.payload["goals"] == ["prove restart"]
