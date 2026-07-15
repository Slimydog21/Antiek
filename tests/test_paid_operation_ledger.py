from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from substrate.paid_operations import (
    BudgetExceeded,
    ConsentKeyring,
    LeaseFence,
    OperationConflict,
    PaidOperationConsentService,
    PaidOperationCorruptionError,
    PaidOperationLedger,
    PaidOperationStore,
    Subject,
    logical_movement_key,
)
from tests.test_paid_operation_store import collective_payload


def _running_fence(
    db: Path,
    *,
    subject: Subject | None = None,
    operation_id: str = "op-1",
    worker_id: str = "worker-1",
) -> LeaseFence:
    store = PaidOperationStore(db)
    service = PaidOperationConsentService(
        store,
        ConsentKeyring(active_key_id="key-1", keys={"key-1": b"k" * 32}),
        clock_ms=lambda: 1_100,
        nonce_factory=lambda: b"n" * 32,
    )
    subject = subject or Subject("owner-1", "acct-1")
    created = store.create_or_replay(subject, operation_id, "collective_interrogation_v1", collective_payload())
    token = service.issue(subject, operation_id).token
    service.claim(subject, operation_id, token=token, options={})
    with sqlite3.connect(db) as con:
        con.execute(
            "UPDATE paid_operations SET state='running', lease_worker_id=?, "
            "lease_generation=1, lease_expires_at_ms=2000, version=version+1 "
            "WHERE account_id=? AND owner_user_id=? AND operation_id=?",
            (worker_id, subject.account_id, subject.owner_user_id, operation_id),
        )
        version = con.execute(
            "SELECT version FROM paid_operations WHERE account_id=? AND owner_user_id=? AND operation_id=?",
            (subject.account_id, subject.owner_user_id, operation_id),
        ).fetchone()[0]
    return LeaseFence(
        subject.account_id,
        subject.owner_user_id,
        operation_id,
        created.intent_hash,
        worker_id,
        1,
        version,
    )


def test_account_budget_period_limit_and_exact_movement_replay(tmp_path: Path) -> None:
    db = tmp_path / "authority.sqlite3"
    fence = _running_fence(db)
    ledger = PaidOperationLedger(db)
    budget = ledger.set_account_budget("acct-1", "period-1", 30)
    assert budget.available_cents == 30
    reserve = ledger.reserve(fence, 20, step_id="dispatch", now_ms=1_200)
    assert ledger.reserve(fence, 20, step_id="dispatch", now_ms=1_300) == reserve
    with pytest.raises(OperationConflict, match="replay conflicts"):
        ledger.reserve(fence, 19, step_id="dispatch", now_ms=1_300)
    assert ledger.get_budget("acct-1").reserved_cents == 20  # type: ignore[union-attr]


def test_movement_keys_and_prior_reserve_lookup_are_tenant_scoped(tmp_path: Path) -> None:
    db = tmp_path / "authority.sqlite3"
    fence = _running_fence(db, subject=Subject("owner-1", "acct-1"))
    other = _running_fence(db, subject=Subject("owner-1", "acct-2"))
    ledger = PaidOperationLedger(db)
    ledger.set_account_budget("acct-1", "period-1", 50)
    ledger.set_account_budget("acct-2", "period-1", 50)

    reserve = ledger.reserve(fence, 10, step_id="dispatch", now_ms=1_200)
    other_reserve = ledger.reserve(other, 10, step_id="dispatch", now_ms=1_200)
    other = other.after(other_reserve)

    assert reserve.movement_key != other_reserve.movement_key
    with pytest.raises(OperationConflict, match="existing reserve"):
        ledger.settle(other, 1, step_id="dispatch", reserve_key=reserve.movement_key, now_ms=1_201)


def test_operation_ceiling_is_cumulative_across_step_reserves(tmp_path: Path) -> None:
    db = tmp_path / "authority.sqlite3"
    fence = _running_fence(db)
    ledger = PaidOperationLedger(db)
    ledger.set_account_budget("acct-1", "period-1", 100)

    reserve = ledger.reserve(fence, 12, step_id="step-a", now_ms=1_200)
    fence = fence.after(reserve)
    with pytest.raises(BudgetExceeded):
        ledger.reserve(fence, 9, step_id="step-b", now_ms=1_201)


def test_settle_releases_and_retain_semantics_preserve_aggregates(tmp_path: Path) -> None:
    db = tmp_path / "authority.sqlite3"
    fence = _running_fence(db)
    ledger = PaidOperationLedger(db)
    ledger.set_account_budget("acct-1", "period-1", 50)
    reserve = ledger.reserve(fence, 20, step_id="dispatch", now_ms=1_200)
    fence = fence.after(reserve)
    settle = ledger.settle(fence, 7, step_id="dispatch", reserve_key=reserve.movement_key, now_ms=1_201)
    fence = fence.after(settle)
    release = ledger.release(fence, 13, step_id="dispatch", reserve_key=reserve.movement_key, now_ms=1_202)
    assert settle.movement_type == "settle"
    assert release.movement_type == "release"
    budget = ledger.get_budget("acct-1")
    assert budget is not None
    assert budget.reserved_cents == 0
    assert budget.settled_cents == 7


def test_movement_requires_operation_to_still_be_running(tmp_path: Path) -> None:
    db = tmp_path / "authority.sqlite3"
    fence = _running_fence(db)
    ledger = PaidOperationLedger(db)
    ledger.set_account_budget("acct-1", "period-1", 50)
    reserve = ledger.reserve(fence, 20, step_id="dispatch", now_ms=1_200)
    fence = fence.after(reserve)
    with sqlite3.connect(db) as con:
        con.execute(
            "UPDATE paid_operations SET state = 'complete', terminal_code = 'complete', "
            "terminal_reason = 'done', reconciliation_status = 'none', settled_cents = 0 "
            "WHERE account_id = ? AND owner_user_id = ? AND operation_id = ?",
            (fence.account_id, fence.owner_user_id, fence.operation_id),
        )

    with pytest.raises(OperationConflict, match="operation state"):
        ledger.settle(fence, 1, step_id="dispatch", reserve_key=reserve.movement_key, now_ms=1_201)


def test_reserve_insufficient_account_budget_fails_closed(tmp_path: Path) -> None:
    db = tmp_path / "authority.sqlite3"
    fence = _running_fence(db)
    ledger = PaidOperationLedger(db)
    ledger.set_account_budget("acct-1", "period-1", 5)
    with pytest.raises(BudgetExceeded):
        ledger.reserve(fence, 20, step_id="dispatch", now_ms=1_200)
    budget = ledger.get_budget("acct-1")
    assert budget is not None
    assert budget.reserved_cents == budget.settled_cents == 0


def test_startup_rejects_account_aggregate_drift(tmp_path: Path) -> None:
    db = tmp_path / "authority.sqlite3"
    fence = _running_fence(db)
    ledger = PaidOperationLedger(db)
    ledger.set_account_budget("acct-1", "period-1", 50)
    ledger.reserve(fence, 20, step_id="dispatch", now_ms=1_200)
    with sqlite3.connect(db) as con:
        con.execute("UPDATE paid_account_budgets SET reserved_cents = 19 WHERE account_id = 'acct-1'")
    with pytest.raises(PaidOperationCorruptionError, match="aggregate drift"):
        PaidOperationStore(db)


def test_new_budget_period_resets_current_counters_without_deleting_history(tmp_path: Path) -> None:
    db = tmp_path / "authority.sqlite3"
    fence = _running_fence(db)
    ledger = PaidOperationLedger(db)
    ledger.set_account_budget("acct-1", "period-1", 50)
    reserve = ledger.reserve(fence, 20, step_id="dispatch", now_ms=1_200)
    fence = fence.after(reserve)
    ledger.settle(fence, 20, step_id="dispatch", reserve_key=reserve.movement_key, now_ms=1_201)
    budget = ledger.set_account_budget("acct-1", "period-2", 5)
    assert budget.reserved_cents == budget.settled_cents == 0
    with sqlite3.connect(db) as con:
        assert con.execute("SELECT COUNT(*) FROM paid_operation_ledger WHERE account_id='acct-1'").fetchone()[0] == 2


def test_budget_period_rollover_refuses_unresolved_reserves(tmp_path: Path) -> None:
    db = tmp_path / "authority.sqlite3"
    fence = _running_fence(db)
    ledger = PaidOperationLedger(db)
    ledger.set_account_budget("acct-1", "period-1", 50)
    ledger.reserve(fence, 20, step_id="dispatch", now_ms=1_200)

    with pytest.raises(BudgetExceeded, match="unresolved reserves"):
        ledger.set_account_budget("acct-1", "period-2", 50)


def test_startup_rejects_erased_prior_period_unresolved_reserve(tmp_path: Path) -> None:
    db = tmp_path / "authority.sqlite3"
    fence = _running_fence(db)
    ledger = PaidOperationLedger(db)
    ledger.set_account_budget("acct-1", "period-1", 50)
    ledger.reserve(fence, 20, step_id="dispatch", now_ms=1_200)
    with sqlite3.connect(db) as con:
        con.execute(
            "UPDATE paid_account_budgets SET period_id='period-2', reserved_cents=0 "
            "WHERE account_id='acct-1'"
        )

    with pytest.raises(PaidOperationCorruptionError, match="outside current budget period"):
        PaidOperationStore(db)


def test_startup_rejects_resolved_cumulative_reserves_over_operation_ceiling(tmp_path: Path) -> None:
    db = tmp_path / "authority.sqlite3"
    fence = _running_fence(db)
    ledger = PaidOperationLedger(db)
    ledger.set_account_budget("acct-1", "period-1", 100)
    reserve = ledger.reserve(fence, 20, step_id="dispatch", now_ms=1_200)
    fence = fence.after(reserve)
    release = ledger.release(fence, 20, step_id="dispatch", reserve_key=reserve.movement_key, now_ms=1_201)
    fence = fence.after(release)
    second_reserve = logical_movement_key("acct-1", "owner-1", "op-1", "second", "reserve")
    second_release = logical_movement_key("acct-1", "owner-1", "op-1", "second", "release")
    with sqlite3.connect(db) as con:
        con.executemany(
            "INSERT INTO paid_operation_ledger ("
            "movement_key, account_id, owner_user_id, operation_id, period_id, intent_hash, "
            "step_id, movement_type, cents, lease_worker_id, lease_generation, expected_operation_version, "
            "operation_version, prior_movement_key, created_at_ms"
            ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                (
                    second_reserve,
                    "acct-1",
                    "owner-1",
                    "op-1",
                    "period-1",
                    fence.intent_hash,
                    "second",
                    "reserve",
                    1,
                    "worker-1",
                    1,
                    fence.expected_operation_version,
                    fence.expected_operation_version + 1,
                    None,
                    1_202,
                ),
                (
                    second_release,
                    "acct-1",
                    "owner-1",
                    "op-1",
                    "period-1",
                    fence.intent_hash,
                    "second",
                    "release",
                    1,
                    "worker-1",
                    1,
                    fence.expected_operation_version + 1,
                    fence.expected_operation_version + 2,
                    second_reserve,
                    1_203,
                ),
            ],
        )
        con.execute(
            "UPDATE paid_operations SET version = ? WHERE account_id='acct-1' AND owner_user_id='owner-1' "
            "AND operation_id='op-1'",
            (fence.expected_operation_version + 2,),
        )

    with pytest.raises(PaidOperationCorruptionError, match="cumulative reserves exceed ceiling"):
        PaidOperationStore(db)
