from __future__ import annotations

import json
import sqlite3
import threading
from dataclasses import replace
from typing import cast

import pytest

from substrate.midnight_oil.job import MidnightOilJob, MidnightOilJobAuthority
from substrate.midnight_oil.job_store import (
    SqliteDurableJobStore,
    create_production_job_store,
)


def _seed_legacy_db(db_path) -> tuple[str, tuple[object, ...]]:
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE midnight_oil_jobs (
                job_id TEXT PRIMARY KEY,
                goals_json TEXT NOT NULL,
                duration_minutes INTEGER NOT NULL,
                model_id TEXT,
                recommended_price_ceiling_usd REAL NOT NULL,
                status TEXT NOT NULL,
                approved_ceiling_usd REAL,
                spent_usd REAL NOT NULL DEFAULT 0,
                asset_id TEXT,
                spawn_ids_json TEXT NOT NULL,
                started_at_ms INTEGER,
                elapsed_ms INTEGER NOT NULL DEFAULT 0,
                force_below_recommended INTEGER NOT NULL DEFAULT 0,
                notes TEXT NOT NULL DEFAULT ''
            )
            """
        )
        row: tuple[object, ...] = (
            "legacy-job",
            json.dumps(["legacy goal"]),
            15,
            "glm-5.2",
            4.56,
            "approved",
            1.009,
            0.25,
            "legacy-asset",
            json.dumps(["spawn-legacy"]),
            10,
            20,
            0,
            "legacy row",
        )
        conn.execute(
            "INSERT INTO midnight_oil_jobs VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            row,
        )
        schema = conn.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name='midnight_oil_jobs'"
        ).fetchone()[0]
    return schema, row


def _job(
    *,
    owner_user_id: str = "owner-a",
    job_id: str = "job-1",
    state_version: int = 0,
    operation_state: str = "approved",
    operation_id: str | None = None,
    approved_ceiling_cents: int | None = 1234,
) -> MidnightOilJob:
    return MidnightOilJob(
        job_id=job_id,
        goals=("map durable CAS",),
        duration_minutes=30,
        model_id="glm-5.2",
        recommended_price_ceiling_usd=15.0,
        status="approved",
        approved_ceiling_usd=12.34,
        spent_usd=1.25,
        asset_id="asset-1",
        spawn_ids=("spawn-1",),
        started_at_ms=101,
        elapsed_ms=202,
        force_below_recommended=False,
        notes="operator approved",
        research_tier="deep",
        fanout_depth=3,
        authority=MidnightOilJobAuthority(
            owner_user_id=owner_user_id,
            state_version=state_version,
            approved_ceiling_cents=approved_ceiling_cents,
            consent_granted_by_user_id="approver-7",
            consent_recorded_at_ms=333,
            consent_note="ticket-42",
            operation_state=cast(object, operation_state),
            operation_id=operation_id,
            dispatch_claimed_at_ms=444 if operation_id else None,
            dispatch_started_at_ms=555 if operation_id else None,
            dispatch_completed_at_ms=None,
        ),
    )


def test_schema_migration_is_idempotent_and_backfills_approved_cents(tmp_path) -> None:
    db_path = tmp_path / "midnight-oil.sqlite"
    _seed_legacy_db(db_path)

    store = SqliteDurableJobStore(str(db_path))
    store.ensure_schema()
    store.ensure_schema()

    with sqlite3.connect(db_path) as conn:
        columns = [row[1] for row in conn.execute("PRAGMA table_info(midnight_oil_jobs)")]
        for required in (
            "owner_user_id",
            "state_version",
            "approved_ceiling_cents",
            "consent_granted_by_user_id",
            "consent_recorded_at_ms",
            "consent_note",
            "operation_state",
            "dispatch_claimed_at_ms",
            "dispatch_started_at_ms",
            "dispatch_completed_at_ms",
        ):
            assert required in columns
        assert all(
            "token" not in column and "secret" not in column and "signing" not in column
            for column in columns
        )
        row = conn.execute(
            """
            SELECT owner_user_id, state_version, approved_ceiling_cents,
                   consent_granted_by_user_id, operation_state, status
            FROM midnight_oil_jobs
            WHERE job_id = ?
            """,
            ("legacy-job",),
        ).fetchone()

    assert row == ("__operator__", 0, None, None, "failed_closed", "failed")
    loaded = store.get_job_for_owner("legacy-job", "__operator__")
    assert loaded is not None
    assert loaded.approved_ceiling_usd == pytest.approx(1.009)
    assert loaded.authority is not None
    assert loaded.goals == ("legacy goal",)
    assert loaded.spawn_ids == ("spawn-legacy",)
    assert loaded.notes == "legacy row"
    assert loaded.authority.approved_ceiling_cents is None
    assert loaded.authority.consent_granted_by_user_id is None
    assert loaded.authority.operation_state == "failed_closed"
    assert loaded.status == "failed"


def test_owner_scoped_roundtrip_survives_restart_and_hides_cross_owner(tmp_path) -> None:
    db_path = tmp_path / "midnight-oil.sqlite"
    store = SqliteDurableJobStore(str(db_path))
    expected = _job(operation_id="op-7", operation_state="dispatch_started", state_version=9)
    stored = store.put_job_for_owner("owner-a", expected)

    reopened = SqliteDurableJobStore(str(db_path))
    loaded = reopened.get_job_for_owner(expected.job_id, "owner-a")

    assert stored == expected
    assert loaded == expected
    assert reopened.get_job_for_owner(expected.job_id, "owner-b") is None


def test_unknown_persisted_authority_state_fails_closed(tmp_path) -> None:
    db_path = tmp_path / "midnight-oil.sqlite"
    store = SqliteDurableJobStore(str(db_path))
    store.put_job_for_owner("owner-a", _job())

    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            UPDATE midnight_oil_jobs
            SET operation_state = 'corrupted-state'
            WHERE owner_user_id = ? AND job_id = ?
            """,
            ("owner-a", "job-1"),
        )

    with pytest.raises(ValueError, match="unknown Midnight Oil authority state"):
        store.get_job_for_owner("job-1", "owner-a")


def test_malformed_persisted_timestamp_fails_closed(tmp_path) -> None:
    db_path = tmp_path / "midnight-oil.sqlite"
    store = SqliteDurableJobStore(str(db_path))
    store.put_job_for_owner("owner-a", _job())
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "UPDATE midnight_oil_jobs SET consent_recorded_at_ms = 'not-a-time' "
            "WHERE owner_user_id = 'owner-a' AND job_id = 'job-1'"
        )
    with pytest.raises(ValueError, match="consent_recorded_at_ms"):
        store.get_job_for_owner("job-1", "owner-a")


@pytest.mark.parametrize(
    ("column", "value", "message"),
    [
        ("status", "invented", "unknown Midnight Oil job status"),
        ("goals_json", '"goal"', "goals_json must be an array of strings"),
        ("goals_json", '{"goal": true}', "goals_json must be an array of strings"),
        ("goals_json", '["goal", 7]', "goals_json must be an array of strings"),
        ("spawn_ids_json", '"spawn"', "spawn_ids_json must be an array of strings"),
        ("spawn_ids_json", '["spawn", null]', "spawn_ids_json must be an array of strings"),
    ],
)
def test_corrupt_status_and_json_collections_fail_closed(
    tmp_path, column: str, value: str, message: str
) -> None:
    db_path = tmp_path / "jobs.sqlite"
    store = SqliteDurableJobStore(str(db_path))
    store.put_job_for_owner("owner-a", _job())
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            f"UPDATE midnight_oil_jobs SET {column} = ? "
            "WHERE owner_user_id = 'owner-a' AND job_id = 'job-1'",
            (value,),
        )
    with pytest.raises(ValueError, match=message):
        store.get_job_for_owner("job-1", "owner-a")


@pytest.mark.parametrize("approved_cents", [None, 0])
def test_approval_requires_positive_ceiling_and_complete_consent_without_mutation(
    tmp_path, approved_cents: int | None
) -> None:
    store = SqliteDurableJobStore(str(tmp_path / "jobs.sqlite"))
    awaiting = replace(
        _job(),
        status="awaiting_approval",
        approved_ceiling_usd=None,
        authority=MidnightOilJobAuthority(owner_user_id="owner-a"),
    )
    original = store.put_job_for_owner("owner-a", awaiting)
    with pytest.raises(ValueError, match="positive approved ceiling"):
        store.compare_and_set_authority(
            "job-1",
            "owner-a",
            expected_version=0,
            expected_state="awaiting_approval",
            expected_operation_id=None,
            operation_id=None,
            next_state="approved",
            approved_ceiling_cents=approved_cents,
            consent_granted_by_user_id="approver-7",
            consent_recorded_at_ms=10,
        )
    assert store.get_job_for_owner("job-1", "owner-a") == original


@pytest.mark.parametrize(
    ("approver", "consent_at"),
    [(None, None), ("approver-7", None), (None, 10)],
)
def test_approval_requires_complete_consent_without_mutation(
    tmp_path, approver: str | None, consent_at: int | None
) -> None:
    store = SqliteDurableJobStore(str(tmp_path / "jobs.sqlite"))
    awaiting = replace(
        _job(),
        status="awaiting_approval",
        approved_ceiling_usd=None,
        authority=MidnightOilJobAuthority(owner_user_id="owner-a"),
    )
    original = store.put_job_for_owner("owner-a", awaiting)
    with pytest.raises(ValueError, match="consent"):
        store.compare_and_set_authority(
            "job-1",
            "owner-a",
            expected_version=0,
            expected_state="awaiting_approval",
            expected_operation_id=None,
            operation_id=None,
            next_state="approved",
            approved_ceiling_cents=1234,
            consent_granted_by_user_id=approver,
            consent_recorded_at_ms=consent_at,
        )
    assert store.get_job_for_owner("job-1", "owner-a") == original


@pytest.mark.parametrize("invalid", [0, 1, "true", None])
def test_force_below_cas_requires_strict_boolean_without_mutation(
    tmp_path, invalid: object
) -> None:
    store = SqliteDurableJobStore(str(tmp_path / "jobs.sqlite"))
    original = store.put_job_for_owner(
        "owner-a",
        replace(
            _job(),
            status="awaiting_approval",
            approved_ceiling_usd=None,
            force_below_recommended=False,
            authority=MidnightOilJobAuthority(owner_user_id="owner-a"),
        ),
    )
    with pytest.raises(ValueError, match="force_below_recommended"):
        store.compare_and_set_authority(
            "job-1",
            "owner-a",
            expected_version=0,
            expected_state="awaiting_approval",
            expected_operation_id=None,
            operation_id="op-1",
            next_state="approved",
            approved_ceiling_cents=1234,
            consent_granted_by_user_id="owner-a",
            consent_recorded_at_ms=10,
            force_below_recommended=invalid,
        )
    assert store.get_job_for_owner("job-1", "owner-a") == original


def test_force_below_is_atomic_durable_and_stale_cas_cannot_change_it(tmp_path) -> None:
    path = str(tmp_path / "jobs.sqlite")
    store = SqliteDurableJobStore(path)
    store.put_job_for_owner(
        "owner-a",
        replace(
            _job(),
            status="awaiting_approval",
            approved_ceiling_usd=None,
            force_below_recommended=False,
            authority=MidnightOilJobAuthority(owner_user_id="owner-a"),
        ),
    )
    approved = store.compare_and_set_authority(
        "job-1",
        "owner-a",
        expected_version=0,
        expected_state="awaiting_approval",
        expected_operation_id=None,
        operation_id="op-1",
        next_state="approved",
        approved_ceiling_cents=1234,
        consent_granted_by_user_id="owner-a",
        consent_recorded_at_ms=10,
        force_below_recommended=True,
    )
    assert approved is not None and approved.force_below_recommended is True
    stale = store.compare_and_set_authority(
        "job-1",
        "owner-a",
        expected_version=0,
        expected_state="awaiting_approval",
        expected_operation_id=None,
        operation_id="op-stale",
        next_state="approved",
        approved_ceiling_cents=999,
        consent_granted_by_user_id="owner-a",
        consent_recorded_at_ms=11,
        force_below_recommended=False,
    )
    assert stale is None
    reopened = SqliteDurableJobStore(path).get_job_for_owner("job-1", "owner-a")
    assert reopened == approved
    assert reopened.force_below_recommended is True


@pytest.mark.parametrize(
    "authority_change",
    [
        {"approved_ceiling_cents": None},
        {"approved_ceiling_cents": 999},
        {"consent_granted_by_user_id": None},
        {"consent_granted_by_user_id": "other-approver"},
        {"consent_recorded_at_ms": None},
        {"consent_recorded_at_ms": 334},
        {"consent_note": None},
        {"consent_note": "different-ticket"},
    ],
)
def test_cas_cannot_clear_or_change_approval_evidence(
    tmp_path, authority_change: dict[str, object]
) -> None:
    store = SqliteDurableJobStore(str(tmp_path / "jobs.sqlite"))
    original = store.put_job_for_owner("owner-a", _job())
    with pytest.raises(ValueError):
        store.compare_and_set_authority(
            "job-1",
            "owner-a",
            expected_version=0,
            expected_state="approved",
            expected_operation_id=None,
            operation_id="op-1",
            next_state="dispatch_claimed",
            dispatch_claimed_at_ms=10,
            **authority_change,
        )
    assert store.get_job_for_owner("job-1", "owner-a") == original


@pytest.mark.parametrize(
    ("operation_id", "claimed_at"),
    [("op-1", None), ("op-1", 10), (None, 10)],
)
def test_failed_closed_with_dispatch_history_requires_approval_on_persistence(
    tmp_path, operation_id: str | None, claimed_at: int | None
) -> None:
    store = SqliteDurableJobStore(str(tmp_path / "jobs.sqlite"))
    authority = MidnightOilJobAuthority(
        owner_user_id="owner-a",
        operation_state="failed_closed",
        operation_id=operation_id,
        dispatch_claimed_at_ms=claimed_at,
    )
    failed = replace(_job(), status="failed", authority=authority)
    with pytest.raises(ValueError, match="positive approved ceiling"):
        store.put_job_for_owner("owner-a", failed)
    assert store.get_job_for_owner("job-1", "owner-a") is None


@pytest.mark.parametrize(("operation_id", "claimed_at"), [("op-1", None), ("op-1", 10), (None, 10)])
def test_cas_cannot_fail_closed_with_dispatch_history_without_approval(
    tmp_path, operation_id: str | None, claimed_at: int | None
) -> None:
    store = SqliteDurableJobStore(str(tmp_path / "jobs.sqlite"))
    awaiting = replace(
        _job(),
        status="awaiting_approval",
        approved_ceiling_usd=None,
        authority=MidnightOilJobAuthority(owner_user_id="owner-a"),
    )
    original = store.put_job_for_owner("owner-a", awaiting)
    with pytest.raises(ValueError, match="positive approved ceiling"):
        store.compare_and_set_authority(
            "job-1",
            "owner-a",
            expected_version=0,
            expected_state="awaiting_approval",
            expected_operation_id=None,
            operation_id=operation_id,
            next_state="failed_closed",
            dispatch_claimed_at_ms=claimed_at,
        )
    assert store.get_job_for_owner("job-1", "owner-a") == original


def test_compare_and_set_allows_exactly_one_concurrent_winner(tmp_path) -> None:
    db_path = tmp_path / "midnight-oil.sqlite"
    SqliteDurableJobStore(str(db_path)).put_job_for_owner("owner-a", _job())
    barrier = threading.Barrier(51)
    winners: list[str] = []
    failures: list[str] = []
    exceptions: list[BaseException] = []
    lock = threading.Lock()

    def contender(index: int) -> None:
        try:
            contender_store = SqliteDurableJobStore(str(db_path))
            operation_id = f"op-{index}"
            barrier.wait()
            result = contender_store.compare_and_set_authority(
                "job-1",
                "owner-a",
                expected_version=0,
                expected_state="approved",
                expected_operation_id=None,
                operation_id=operation_id,
                next_state="dispatch_claimed",
                dispatch_claimed_at_ms=1_000 + index,
            )
            with lock:
                (failures if result is None else winners).append(operation_id)
        except BaseException as exc:
            with lock:
                exceptions.append(exc)

    threads = [threading.Thread(target=contender, args=(index,)) for index in range(50)]
    for thread in threads:
        thread.start()
    barrier.wait()
    for thread in threads:
        thread.join()

    assert exceptions == []
    assert len(winners) == 1
    assert len(failures) == 49
    final_job = SqliteDurableJobStore(str(db_path)).get_job_for_owner("job-1", "owner-a")
    assert final_job is not None
    assert final_job.authority is not None
    assert final_job.authority.state_version == 1
    assert final_job.authority.operation_state == "dispatch_claimed"
    assert final_job.authority.operation_id == winners[0]
    assert final_job.authority.dispatch_claimed_at_ms is not None


def test_stale_version_state_and_operation_reject_without_mutation(tmp_path) -> None:
    db_path = tmp_path / "midnight-oil.sqlite"
    store = SqliteDurableJobStore(str(db_path))
    store.put_job_for_owner("owner-a", _job())
    winner = store.compare_and_set_authority(
        "job-1",
        "owner-a",
        expected_version=0,
        expected_state="approved",
        expected_operation_id=None,
        operation_id="op-win",
        next_state="dispatch_claimed",
        dispatch_claimed_at_ms=900,
    )
    assert winner is not None

    stale_version = store.compare_and_set_authority(
        "job-1",
        "owner-a",
        expected_version=0,
        expected_state="dispatch_claimed",
        expected_operation_id="op-win",
        operation_id="op-stale-version",
        next_state="dispatch_started",
    )
    stale_state = store.compare_and_set_authority(
        "job-1",
        "owner-a",
        expected_version=1,
        expected_state="approved",
        expected_operation_id="op-win",
        operation_id="op-stale-state",
        next_state="dispatch_started",
    )
    stale_operation = store.compare_and_set_authority(
        "job-1",
        "owner-a",
        expected_version=1,
        expected_state="dispatch_claimed",
        expected_operation_id="wrong-op",
        operation_id="op-stale-operation",
        next_state="dispatch_started",
    )

    assert stale_version is None
    assert stale_state is None
    assert stale_operation is None
    final_job = store.get_job_for_owner("job-1", "owner-a")
    assert final_job == winner


@pytest.mark.parametrize("bad_cents", [True, 1.5, -1, 2**63])
def test_integer_cents_reject_bool_float_negative_and_overflow(
    tmp_path,
    bad_cents: object,
) -> None:
    db_path = tmp_path / "midnight-oil.sqlite"
    store = SqliteDurableJobStore(str(db_path))
    bad_job = _job(
        approved_ceiling_cents=cast(int | None, bad_cents),
    )

    with pytest.raises(ValueError, match="approved_ceiling_cents"):
        store.put_job_for_owner("owner-a", bad_job)


def test_create_cannot_overwrite_authority_after_cas(tmp_path) -> None:
    store = SqliteDurableJobStore(str(tmp_path / "jobs.sqlite"))
    original = _job()
    store.put_job_for_owner("owner-a", original)
    claimed = store.compare_and_set_authority(
        "job-1",
        "owner-a",
        expected_version=0,
        expected_state="approved",
        expected_operation_id=None,
        operation_id="op-1",
        next_state="dispatch_claimed",
        dispatch_claimed_at_ms=10,
    )
    assert claimed is not None

    with pytest.raises(ValueError, match="authority changes require CAS"):
        store.put_job_for_owner("owner-a", original)
    assert store.get_job_for_owner("job-1", "owner-a") == claimed


def test_illegal_transition_identity_change_and_bad_timestamps_do_not_mutate(tmp_path) -> None:
    store = SqliteDurableJobStore(str(tmp_path / "jobs.sqlite"))
    original = store.put_job_for_owner("owner-a", _job())
    bad_calls = (
        dict(operation_id="op-1", next_state="dispatch_finished", dispatch_completed_at_ms=30),
        dict(operation_id="op-1", next_state="dispatch_claimed", dispatch_claimed_at_ms=-1),
    )
    for changes in bad_calls:
        with pytest.raises(ValueError):
            store.compare_and_set_authority(
                "job-1",
                "owner-a",
                expected_version=0,
                expected_state="approved",
                expected_operation_id=None,
                **changes,
            )
        assert store.get_job_for_owner("job-1", "owner-a") == original

    claimed = store.compare_and_set_authority(
        "job-1",
        "owner-a",
        expected_version=0,
        expected_state="approved",
        expected_operation_id=None,
        operation_id="op-1",
        next_state="dispatch_claimed",
        dispatch_claimed_at_ms=20,
    )
    assert claimed is not None
    for changed_id in (None, "op-2"):
        with pytest.raises(ValueError, match="operation identity"):
            store.compare_and_set_authority(
                "job-1",
                "owner-a",
                expected_version=1,
                expected_state="dispatch_claimed",
                expected_operation_id="op-1",
                operation_id=changed_id,
                next_state="dispatch_started",
                dispatch_started_at_ms=30,
            )
        assert store.get_job_for_owner("job-1", "owner-a") == claimed


def test_concurrent_schema_migration_converges(tmp_path) -> None:
    db_path = tmp_path / "jobs.sqlite"
    _seed_legacy_db(db_path)
    errors: list[BaseException] = []

    def migrate() -> None:
        try:
            SqliteDurableJobStore(str(db_path)).ensure_schema()
        except BaseException as exc:
            errors.append(exc)

    threads = [threading.Thread(target=migrate) for _ in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert errors == []
    with sqlite3.connect(db_path) as conn:
        assert conn.execute("PRAGMA user_version").fetchone()[0] == 2
        columns = {row[1] for row in conn.execute("PRAGMA table_info(midnight_oil_jobs)")}
        row = conn.execute(
            "SELECT job_id, approved_ceiling_cents, consent_granted_by_user_id, "
            "operation_state, status, goals_json, spawn_ids_json, notes "
            "FROM midnight_oil_jobs"
        ).fetchone()
    assert set(("owner_user_id", "job_id", "state_version")) <= columns
    assert row == (
        "legacy-job",
        None,
        None,
        "failed_closed",
        "failed",
        '["legacy goal"]',
        '["spawn-legacy"]',
        "legacy row",
    )


def test_failed_migration_rolls_back_original_table(tmp_path, monkeypatch) -> None:
    db_path = tmp_path / "jobs.sqlite"
    original_schema, original_row = _seed_legacy_db(db_path)
    store = SqliteDurableJobStore(str(db_path))

    def fail(_conn: sqlite3.Connection) -> None:
        raise RuntimeError("injected migration failure")

    monkeypatch.setattr(store, "_backfill_legacy_approved_ceiling_cents", fail)
    with pytest.raises(RuntimeError, match="injected migration failure"):
        store.ensure_schema()
    with sqlite3.connect(db_path) as conn:
        assert conn.execute("PRAGMA user_version").fetchone()[0] == 0
        schema = conn.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name='midnight_oil_jobs'"
        ).fetchone()[0]
        row = conn.execute("SELECT * FROM midnight_oil_jobs").fetchone()
    assert schema == original_schema
    assert row == original_row


@pytest.mark.parametrize("path", [None, "", "   "])
def test_production_factory_requires_durable_path(path: str | None) -> None:
    with pytest.raises(RuntimeError, match="durable Midnight Oil database path"):
        create_production_job_store(path)
