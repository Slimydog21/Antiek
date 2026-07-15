from __future__ import annotations

import concurrent.futures
import sqlite3
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

from substrate.paid_operations import (
    BudgetExceeded,
    ConsentKeyring,
    FakePaidOperationProvider,
    OperationConflict,
    PaidOperationConsentService,
    PaidOperationCorruptionError,
    PaidOperationLedger,
    PaidOperationStore,
    PaidOperationWorker,
    ProviderCapabilityAttestation,
    ProviderCapabilityError,
    ProviderRequest,
    ProviderResult,
    Subject,
    UnknownProviderOutcome,
    stable_idempotency_key,
)
from tests.test_paid_operation_contracts import midnight_payload
from tests.test_paid_operation_store import collective_payload


class Clock:
    value = 1_200

    def __call__(self) -> int:
        return self.value


def _cap(*, enabled: bool = True) -> ProviderCapabilityAttestation:
    return ProviderCapabilityAttestation(
        provider_id="provider-1",
        endpoint_id="route-1",
        operation_kind="collective_interrogation_v1",
        api_version="fake-v1",
        retention_window_ms=86_400_000,
        documentation_url="https://example.invalid/fake",
        request_body_scope="intent+step",
        duplicate_same_body_behavior="same logical result",
        duplicate_changed_body_behavior="conflict",
        billing_semantics="one charge per idempotency key",
        live_smoke_receipt_hash="a" * 64,
        expires_at_ms=9_999_999,
        enabled=enabled,
        documentation_hash="b" * 64,
        behavior_evidence_hash="c" * 64,
        live_smoke_operator_id="operator-1",
        live_smoke_authorization_hash="d" * 64,
    )


def _queued(
    db: Path,
    *,
    subject: Subject | None = None,
    operation_id: str = "op-1",
    kind: str = "collective_interrogation_v1",
    payload: dict[str, object] | None = None,
) -> None:
    store = PaidOperationStore(db)
    service = PaidOperationConsentService(
        store,
        ConsentKeyring(active_key_id="key-1", keys={"key-1": b"k" * 32}),
        clock_ms=lambda: 1_100,
        nonce_factory=lambda: b"n" * 32,
    )
    subject = subject or Subject("owner-1", "acct-1")
    store.create_or_replay(subject, operation_id, kind, payload or collective_payload())
    token = service.issue(subject, operation_id).token
    service.claim(subject, operation_id, token=token, options={})


def test_default_worker_clock_is_real_epoch_milliseconds(tmp_path: Path) -> None:
    db = tmp_path / "authority.sqlite3"
    _queued(db)
    capability = replace(_cap(), expires_at_ms=9_000_000_000_000_000_000)

    leased = PaidOperationWorker(db, FakePaidOperationProvider(capability)).claim_next(
        "worker-1",
        lease_ms=500,
    )

    assert leased is not None
    assert leased.lease_expires_at_ms > 1_000_000_000_000


@pytest.mark.parametrize(
    ("capability_patch", "message"),
    [
        ({"documentation_hash": None}, "documentation_hash"),
        ({"documentation_url": "http://example.test/docs"}, "HTTPS"),
        ({"duplicate_same_body_behavior": "header accepted"}, "attested behavior"),
        ({"live_smoke_receipt_hash": "not-a-hash"}, "sha256"),
        ({"live_smoke_operator_id": None}, "operator-authorized"),
        ({"live_smoke_authorization_hash": None}, "authorization_hash"),
    ],
)
def test_enabled_capability_requires_complete_attested_evidence(
    tmp_path: Path,
    capability_patch: dict[str, Any],
    message: str,
) -> None:
    capability = replace(_cap(), **capability_patch)

    with pytest.raises(ProviderCapabilityError, match=message):
        PaidOperationWorker(tmp_path / "authority.sqlite3", FakePaidOperationProvider(capability), clock_ms=Clock())


@pytest.mark.parametrize(
    "capability_patch",
    [
        {"provider_id": "provider-2"},
        {"endpoint_id": "route-2"},
    ],
)
def test_claim_is_bound_to_immutable_intent_provider_and_route(
    tmp_path: Path,
    capability_patch: dict[str, Any],
) -> None:
    db = tmp_path / "authority.sqlite3"
    _queued(db)
    provider = FakePaidOperationProvider(replace(_cap(), **capability_patch))
    worker = PaidOperationWorker(db, provider, clock_ms=Clock())

    assert worker.claim_next("worker-1", lease_ms=500) is None
    assert provider.calls == []
    snapshot = PaidOperationStore(db).get_owned(Subject("owner-1", "acct-1"), "op-1")
    assert snapshot is not None
    assert snapshot.state == "queued"


def test_dispatch_rechecks_claimed_immutable_provider_route_before_reserve_or_call(tmp_path: Path) -> None:
    db = tmp_path / "authority.sqlite3"
    _queued(db)
    ledger = PaidOperationLedger(db)
    ledger.set_account_budget("acct-1", "period-1", 100)
    provider = FakePaidOperationProvider(_cap())
    worker = PaidOperationWorker(db, provider, clock_ms=Clock())
    leased = worker.claim_next("worker-1", lease_ms=500)
    assert leased is not None
    provider.capability = replace(_cap(), endpoint_id="route-2")

    with pytest.raises(ProviderCapabilityError, match="provider route mismatch"):
        worker.execute_leased(leased)

    assert provider.calls == []
    assert ledger.get_budget("acct-1").reserved_cents == 0  # type: ignore[union-attr]


def test_two_worker_race_dispatches_once_with_stable_idempotency_key(tmp_path: Path) -> None:
    db = tmp_path / "authority.sqlite3"
    _queued(db)
    PaidOperationLedger(db).set_account_budget("acct-1", "period-1", 100)
    provider = FakePaidOperationProvider(
        _cap(),
        results={"dispatch": ProviderResult({"answer": "ok"}, "receipt-1", 7)},
    )
    clock = Clock()

    def run(worker: str) -> str:
        receipt = PaidOperationWorker(db, provider, clock_ms=clock).execute_one(worker, lease_ms=500)
        return "none" if receipt is None else receipt.state

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(run, ["worker-1", "worker-2"]))

    assert sorted(results) == ["complete", "none"]
    assert len(provider.calls) == 1
    call = provider.calls[0]
    assert call.idempotency_key == stable_idempotency_key(
        "acct-1",
        "owner-1",
        "op-1",
        "dispatch",
        call.intent_hash,
    )
    assert PaidOperationStore(db).get_owned(Subject("owner-1", "acct-1"), "op-1").state == "complete"  # type: ignore[union-attr]


def test_expired_lease_takeover_fences_stale_worker(tmp_path: Path) -> None:
    db = tmp_path / "authority.sqlite3"
    _queued(db)
    PaidOperationLedger(db).set_account_budget("acct-1", "period-1", 100)
    clock = Clock()
    provider = FakePaidOperationProvider(_cap())
    worker = PaidOperationWorker(db, provider, clock_ms=clock)
    stale = worker.claim_next("worker-1", lease_ms=5)
    assert stale is not None
    clock.value = 1_300
    fresh = worker.claim_next("worker-2", lease_ms=500)
    assert fresh is not None
    with pytest.raises(OperationConflict, match="lease fence"):
        worker.ledger.reserve(stale.fence, stale.ceiling_cents, step_id="dispatch", now_ms=clock())
    assert fresh.lease_generation == stale.lease_generation + 1


def test_renew_cas_invalidates_same_generation_handle(tmp_path: Path) -> None:
    db = tmp_path / "authority.sqlite3"
    _queued(db)
    PaidOperationLedger(db).set_account_budget("acct-1", "period-1", 100)
    clock = Clock()
    worker = PaidOperationWorker(db, FakePaidOperationProvider(_cap()), clock_ms=clock)
    stale = worker.claim_next("worker-1", lease_ms=500)
    assert stale is not None

    renewed = worker.renew(stale, lease_ms=600)

    assert renewed.lease_generation == stale.lease_generation
    assert renewed.version == stale.version + 1
    with pytest.raises(OperationConflict, match="CAS precondition"):
        worker.ledger.reserve(stale.fence, stale.ceiling_cents, step_id="dispatch", now_ms=clock())
    reserve = worker.ledger.reserve(renewed.fence, renewed.ceiling_cents, step_id="dispatch", now_ms=clock())
    assert reserve.expected_operation_version == renewed.version


def test_exact_expiry_boundary_rejects_all_worker_mutations_and_allows_takeover(tmp_path: Path) -> None:
    db = tmp_path / "authority.sqlite3"
    _queued(db)
    PaidOperationLedger(db).set_account_budget("acct-1", "period-1", 100)
    clock = Clock()
    worker = PaidOperationWorker(db, FakePaidOperationProvider(_cap()), clock_ms=clock)
    expired = worker.claim_next("worker-1", lease_ms=5)
    assert expired is not None
    reserve = worker.ledger.reserve(expired.fence, expired.ceiling_cents, step_id="dispatch", now_ms=clock())
    expired = expired.after_movement(reserve)
    clock.value = expired.lease_expires_at_ms

    with pytest.raises(OperationConflict, match="expired"):
        worker.ledger.reserve(expired.fence, 0, step_id="second", now_ms=clock())
    with pytest.raises(OperationConflict, match="expired"):
        worker.ledger.settle(
            expired.fence,
            1,
            step_id="dispatch",
            reserve_key=reserve.movement_key,
            now_ms=clock(),
        )
    with pytest.raises(OperationConflict, match="expired"):
        worker._write_checkpoint(  # noqa: SLF001
            expired,
            "dispatch",
            stable_idempotency_key(
                expired.account_id,
                expired.owner_user_id,
                expired.operation_id,
                "dispatch",
                expired.intent_hash,
            ),
            ProviderResult({"answer": "late"}, "receipt-late", 1),
        )
    with pytest.raises(OperationConflict, match="lease fence"):
        worker._complete(expired, "a" * 64, 1)  # noqa: SLF001

    takeover = worker.claim_next("worker-2", lease_ms=500)
    assert takeover is not None
    assert takeover.lease_generation == expired.lease_generation + 1


def test_takeover_worker_reuses_prior_reserve_and_stale_worker_is_fenced(tmp_path: Path) -> None:
    db = tmp_path / "authority.sqlite3"
    _queued(db)
    PaidOperationLedger(db).set_account_budget("acct-1", "period-1", 100)
    clock = Clock()
    provider = FakePaidOperationProvider(_cap())
    worker = PaidOperationWorker(db, provider, clock_ms=clock)
    stale = worker.claim_next("worker-1", lease_ms=5)
    assert stale is not None
    reserve = worker.ledger.reserve(stale.fence, stale.ceiling_cents, step_id="dispatch", now_ms=clock())
    stale = stale.after_movement(reserve)

    clock.value = 1_300
    fresh = worker.claim_next("worker-2", lease_ms=500)
    assert fresh is not None

    replay = worker.ledger.reserve(fresh.fence, fresh.ceiling_cents, step_id="dispatch", now_ms=clock())
    assert replay == reserve
    with pytest.raises(OperationConflict, match="lease fence"):
        worker.ledger.settle(stale.fence, 1, step_id="dispatch", reserve_key=reserve.movement_key, now_ms=clock())
    assert PaidOperationStore(db).get_owned(Subject("owner-1", "acct-1"), "op-1") is not None


def test_checkpoint_crash_takeover_reuses_checkpoint_without_redispatch(tmp_path: Path) -> None:
    db = tmp_path / "authority.sqlite3"
    _queued(db)
    PaidOperationLedger(db).set_account_budget("acct-1", "period-1", 100)
    clock = Clock()
    provider = FakePaidOperationProvider(_cap())
    worker = PaidOperationWorker(db, provider, clock_ms=clock)
    stale = worker.claim_next("worker-1", lease_ms=5)
    assert stale is not None
    reserve = worker.ledger.reserve(stale.fence, stale.ceiling_cents, step_id="dispatch", now_ms=clock())
    stale = stale.after_movement(reserve)
    idempotency_key = stable_idempotency_key(
        stale.account_id,
        stale.owner_user_id,
        stale.operation_id,
        "dispatch",
        stale.intent_hash,
    )
    checkpoint = worker._write_checkpoint(  # noqa: SLF001
        stale,
        "dispatch",
        idempotency_key,
        ProviderResult({"answer": "already accepted"}, "receipt-1", 7),
    )

    clock.value = 1_300
    assert PaidOperationStore(db).get_owned(Subject("owner-1", "acct-1"), "op-1") is not None
    recovery_provider = FakePaidOperationProvider(
        _cap(),
        results={"dispatch": ProviderResult({"answer": "should-not-call"}, "receipt-2", 9)},
    )
    receipt = PaidOperationWorker(db, recovery_provider, clock_ms=clock).execute_one("worker-2", lease_ms=500)

    assert receipt is not None
    assert receipt.state == "complete"
    assert receipt.reserve == reserve
    assert receipt.checkpoint_hash == checkpoint.response_body_hash
    assert recovery_provider.calls == []
    budget = PaidOperationLedger(db).get_budget("acct-1")
    assert budget is not None
    assert budget.reserved_cents == 0
    assert budget.settled_cents == 7


def test_over_reserve_checkpoint_crash_recovers_to_quarantine_without_redispatch(tmp_path: Path) -> None:
    db = tmp_path / "authority.sqlite3"
    _queued(db)
    PaidOperationLedger(db).set_account_budget("acct-1", "period-1", 100)
    clock = Clock()
    worker = PaidOperationWorker(db, FakePaidOperationProvider(_cap()), clock_ms=clock)
    crashed = worker.claim_next("worker-1", lease_ms=5)
    assert crashed is not None
    reserve = worker.ledger.reserve(crashed.fence, crashed.ceiling_cents, step_id="dispatch", now_ms=clock())
    crashed = crashed.after_movement(reserve)
    checkpoint = worker._write_checkpoint(  # noqa: SLF001
        crashed,
        "dispatch",
        stable_idempotency_key(
            crashed.account_id,
            crashed.owner_user_id,
            crashed.operation_id,
            "dispatch",
            crashed.intent_hash,
        ),
        ProviderResult({"answer": "definite"}, "receipt-over", 21),
    )
    clock.value = crashed.lease_expires_at_ms
    recovery_provider = FakePaidOperationProvider(_cap())

    receipt = PaidOperationWorker(db, recovery_provider, clock_ms=clock).execute_one(
        "worker-2",
        lease_ms=500,
    )

    assert receipt is not None
    assert receipt.state == "failed_reconcile"
    assert receipt.checkpoint_hash == checkpoint.response_body_hash
    assert recovery_provider.calls == []
    assert PaidOperationStore(db).get_owned(Subject("owner-1", "acct-1"), "op-1") is not None


def test_partial_settlement_crash_recovers_release_without_redispatch(tmp_path: Path) -> None:
    db = tmp_path / "authority.sqlite3"
    _queued(db)
    PaidOperationLedger(db).set_account_budget("acct-1", "period-1", 100)
    clock = Clock()
    provider = FakePaidOperationProvider(_cap())
    worker = PaidOperationWorker(db, provider, clock_ms=clock)
    crashed = worker.claim_next("worker-1", lease_ms=5)
    assert crashed is not None
    reserve = worker.ledger.reserve(crashed.fence, crashed.ceiling_cents, step_id="dispatch", now_ms=clock())
    crashed = crashed.after_movement(reserve)
    checkpoint = worker._write_checkpoint(  # noqa: SLF001
        crashed,
        "dispatch",
        stable_idempotency_key(
            crashed.account_id,
            crashed.owner_user_id,
            crashed.operation_id,
            "dispatch",
            crashed.intent_hash,
        ),
        ProviderResult({"answer": "accepted"}, "receipt-1", 7),
    )
    crashed = crashed.after_checkpoint(checkpoint)
    settlement = worker.ledger.settle(
        crashed.fence,
        7,
        step_id="dispatch",
        reserve_key=reserve.movement_key,
        now_ms=clock(),
    )
    crashed = crashed.after_movement(settlement)
    clock.value = crashed.lease_expires_at_ms

    recovery_provider = FakePaidOperationProvider(_cap())
    receipt = PaidOperationWorker(db, recovery_provider, clock_ms=clock).execute_one("worker-2", lease_ms=500)

    assert receipt is not None
    assert receipt.state == "complete"
    assert recovery_provider.calls == []
    budget = PaidOperationLedger(db).get_budget("acct-1")
    assert budget is not None
    assert budget.reserved_cents == 0
    assert budget.settled_cents == 7


def test_provider_result_after_expiry_is_recovered_by_same_idempotency_key(tmp_path: Path) -> None:
    db = tmp_path / "authority.sqlite3"
    _queued(db)
    PaidOperationLedger(db).set_account_budget("acct-1", "period-1", 100)
    clock = Clock()
    provider = FakePaidOperationProvider(
        _cap(),
        results={"dispatch": ProviderResult({"answer": "accepted"}, "receipt-1", 7)},
    )
    worker = PaidOperationWorker(db, provider, clock_ms=clock)
    expired = worker.claim_next("worker-1", lease_ms=5)
    assert expired is not None
    dispatch = provider.dispatch

    def dispatch_then_expire(request: ProviderRequest) -> ProviderResult:
        result = dispatch(request)
        clock.value = expired.lease_expires_at_ms
        return result

    provider.dispatch = dispatch_then_expire  # type: ignore[method-assign]
    with pytest.raises(OperationConflict, match="expired"):
        worker.execute_leased(expired)

    provider.dispatch = dispatch  # type: ignore[method-assign]
    receipt = PaidOperationWorker(db, provider, clock_ms=clock).execute_one("worker-2", lease_ms=500)

    assert receipt is not None
    assert receipt.state == "complete"
    assert len(provider.calls) == 2
    assert provider.calls[0].idempotency_key == provider.calls[1].idempotency_key
    assert len(provider.logical_results) == 1
    snapshot = PaidOperationStore(db).get_owned(Subject("owner-1", "acct-1"), "op-1")
    assert snapshot is not None
    assert snapshot.state == "complete"


def test_recovery_after_provider_idempotency_window_quarantines_without_redispatch(tmp_path: Path) -> None:
    db = tmp_path / "authority.sqlite3"
    _queued(db)
    PaidOperationLedger(db).set_account_budget("acct-1", "period-1", 100)
    clock = Clock()
    capability = _cap()
    capability = ProviderCapabilityAttestation(
        **{**capability.__dict__, "retention_window_ms": 10}
    )
    provider = FakePaidOperationProvider(capability)
    worker = PaidOperationWorker(db, provider, clock_ms=clock)
    crashed = worker.claim_next("worker-1", lease_ms=5)
    assert crashed is not None
    worker.ledger.reserve(crashed.fence, crashed.ceiling_cents, step_id="dispatch", now_ms=clock())
    clock.value += 10

    receipt = PaidOperationWorker(db, provider, clock_ms=clock).execute_one("worker-2", lease_ms=500)

    assert receipt is not None
    assert receipt.state == "failed_reconcile"
    assert provider.calls == []
    snapshot = PaidOperationStore(db).get_owned(Subject("owner-1", "acct-1"), "op-1")
    assert snapshot is not None
    assert snapshot.terminal_reason == "provider_idempotency_window_expired"


def test_checkpoint_insert_rejects_stale_worker_after_takeover(tmp_path: Path) -> None:
    db = tmp_path / "authority.sqlite3"
    _queued(db)
    PaidOperationLedger(db).set_account_budget("acct-1", "period-1", 100)
    clock = Clock()
    worker = PaidOperationWorker(db, FakePaidOperationProvider(_cap()), clock_ms=clock)
    stale = worker.claim_next("worker-1", lease_ms=5)
    assert stale is not None
    clock.value = 1_300
    assert worker.claim_next("worker-2", lease_ms=500) is not None

    with pytest.raises(OperationConflict, match="lease fence"):
        worker._write_checkpoint(  # noqa: SLF001
            stale,
            "dispatch",
            stable_idempotency_key(
                stale.account_id,
                stale.owner_user_id,
                stale.operation_id,
                "dispatch",
                stale.intent_hash,
            ),
            ProviderResult({"answer": "stale"}, "receipt-stale", 1),
        )

    with sqlite3.connect(db) as con:
        assert con.execute("SELECT COUNT(*) FROM paid_operation_checkpoints").fetchone()[0] == 0


def test_provider_idempotency_key_is_tenant_scoped(tmp_path: Path) -> None:
    db = tmp_path / "authority.sqlite3"
    _queued(db, subject=Subject("owner-1", "acct-1"))
    _queued(db, subject=Subject("owner-1", "acct-2"))
    PaidOperationLedger(db).set_account_budget("acct-1", "period-1", 100)
    PaidOperationLedger(db).set_account_budget("acct-2", "period-1", 100)
    provider = FakePaidOperationProvider(_cap())
    clock = Clock()

    PaidOperationWorker(db, provider, clock_ms=clock).execute_one("worker-1", lease_ms=500)
    PaidOperationWorker(db, provider, clock_ms=clock).execute_one("worker-2", lease_ms=500)

    assert len(provider.calls) == 2
    assert provider.calls[0].operation_id == provider.calls[1].operation_id == "op-1"
    assert provider.calls[0].idempotency_key != provider.calls[1].idempotency_key


def test_claim_next_skips_unrelated_provider_kind_without_halting_it(tmp_path: Path) -> None:
    db = tmp_path / "authority.sqlite3"
    _queued(db, operation_id="op-1", kind="midnight_oil_v1", payload=midnight_payload())
    _queued(db, operation_id="op-2", kind="collective_interrogation_v1", payload=collective_payload())
    PaidOperationLedger(db).set_account_budget("acct-1", "period-1", 100)
    worker = PaidOperationWorker(db, FakePaidOperationProvider(_cap()), clock_ms=Clock())

    leased = worker.claim_next("worker-1", lease_ms=500)

    assert leased is not None
    assert leased.operation_id == "op-2"
    unrelated = PaidOperationStore(db).get_owned(Subject("owner-1", "acct-1"), "op-1")
    assert unrelated is not None
    assert unrelated.state == "queued"


def test_disabled_capability_halts_without_provider_or_budget_debit(tmp_path: Path) -> None:
    db = tmp_path / "authority.sqlite3"
    _queued(db)
    ledger = PaidOperationLedger(db)
    ledger.set_account_budget("acct-1", "period-1", 100)
    provider = FakePaidOperationProvider(_cap(enabled=False))
    with pytest.raises(ProviderCapabilityError):
        PaidOperationWorker(db, provider, clock_ms=Clock()).execute_one("worker-1", lease_ms=500)
    assert provider.calls == []
    assert ledger.get_budget("acct-1").reserved_cents == 0  # type: ignore[union-attr]


def test_capability_is_revalidated_at_dispatch_after_claim(tmp_path: Path) -> None:
    db = tmp_path / "authority.sqlite3"
    _queued(db)
    ledger = PaidOperationLedger(db)
    ledger.set_account_budget("acct-1", "period-1", 100)
    clock = Clock()
    provider = FakePaidOperationProvider(replace(_cap(), expires_at_ms=1_300))
    worker = PaidOperationWorker(db, provider, clock_ms=clock)
    leased = worker.claim_next("worker-1", lease_ms=500)
    assert leased is not None
    clock.value = 1_300

    with pytest.raises(ProviderCapabilityError, match="expired"):
        worker.execute_leased(leased)

    assert provider.calls == []
    assert ledger.get_budget("acct-1").reserved_cents == 0  # type: ignore[union-attr]
    snapshot = PaidOperationStore(db).get_owned(Subject("owner-1", "acct-1"), "op-1")
    assert snapshot is not None
    assert snapshot.state == "budget_halted"


def test_zero_cent_ceiling_fails_closed_before_reserve_or_provider_call(tmp_path: Path) -> None:
    db = tmp_path / "authority.sqlite3"
    payload = collective_payload()
    payload["quote_cents"] = 0
    payload["ceiling_cents"] = 0
    _queued(db, payload=payload)
    ledger = PaidOperationLedger(db)
    ledger.set_account_budget("acct-1", "period-1", 100)
    provider = FakePaidOperationProvider(
        _cap(),
        results={"dispatch": UnknownProviderOutcome("could not retain zero hold")},
    )

    with pytest.raises(BudgetExceeded, match="zero-cent reserve"):
        PaidOperationWorker(db, provider, clock_ms=Clock()).execute_one("worker-1", lease_ms=500)

    assert provider.calls == []
    with sqlite3.connect(db) as con:
        assert con.execute("SELECT COUNT(*) FROM paid_operation_ledger").fetchone()[0] == 0
    snapshot = PaidOperationStore(db).get_owned(Subject("owner-1", "acct-1"), "op-1")
    assert snapshot is not None
    assert snapshot.state == "budget_halted"
    assert snapshot.terminal_reason == "zero_reserve_cannot_retain_unknown_outcome"


def test_insufficient_budget_halts_before_provider_call(tmp_path: Path) -> None:
    db = tmp_path / "authority.sqlite3"
    _queued(db)
    ledger = PaidOperationLedger(db)
    ledger.set_account_budget("acct-1", "period-1", 10)
    provider = FakePaidOperationProvider(_cap())
    with pytest.raises(BudgetExceeded):
        PaidOperationWorker(db, provider, clock_ms=Clock()).execute_one("worker-1", lease_ms=500)
    assert provider.calls == []
    assert PaidOperationStore(db).get_owned(Subject("owner-1", "acct-1"), "op-1").state == "budget_halted"  # type: ignore[union-attr]


def test_over_reserve_response_is_checkpointed_before_coherent_quarantine(tmp_path: Path) -> None:
    db = tmp_path / "authority.sqlite3"
    _queued(db)
    PaidOperationLedger(db).set_account_budget("acct-1", "period-1", 100)
    provider = FakePaidOperationProvider(
        _cap(),
        results={"dispatch": ProviderResult({"answer": "definite"}, "receipt-over", 21)},
    )

    receipt = PaidOperationWorker(db, provider, clock_ms=Clock()).execute_one("worker-1", lease_ms=500)

    assert receipt is not None
    assert receipt.state == "failed_reconcile"
    assert receipt.checkpoint_hash is not None
    assert len(provider.calls) == 1
    with sqlite3.connect(db) as con:
        checkpoint = con.execute(
            "SELECT response_body_hash, response_body_json, provider_receipt, observed_cost_cents "
            "FROM paid_operation_checkpoints"
        ).fetchone()
    assert checkpoint == (receipt.checkpoint_hash, '{"answer":"definite"}', "receipt-over", 21)
    snapshot = PaidOperationStore(db).get_owned(Subject("owner-1", "acct-1"), "op-1")
    assert snapshot is not None
    assert snapshot.state == "failed_reconcile"
    assert snapshot.result_checkpoint_hash == receipt.checkpoint_hash
    budget = PaidOperationLedger(db).get_budget("acct-1")
    assert budget is not None
    assert budget.reserved_cents == 20
    assert budget.settled_cents == 0


@pytest.mark.parametrize(
    "provider_outcome",
    [
        UnknownProviderOutcome("lost"),
        ProviderResult({"answer": "too much"}, "receipt-over", 21),
    ],
)
def test_retain_and_failed_reconcile_terminal_are_atomic(
    tmp_path: Path,
    provider_outcome: UnknownProviderOutcome | ProviderResult,
) -> None:
    db = tmp_path / "authority.sqlite3"
    _queued(db)
    PaidOperationLedger(db).set_account_budget("acct-1", "period-1", 100)
    clock = Clock()
    provider = FakePaidOperationProvider(_cap(), results={"dispatch": provider_outcome})
    worker = PaidOperationWorker(db, provider, clock_ms=clock)
    leased = worker.claim_next("worker-1", lease_ms=500)
    assert leased is not None

    def fail_terminal(*args: object, **kwargs: object) -> None:
        raise RuntimeError("simulated terminal failure")

    worker._terminal_in_tx = fail_terminal  # type: ignore[method-assign]  # noqa: SLF001
    with pytest.raises(RuntimeError, match="simulated terminal failure"):
        worker.execute_leased(leased)

    with sqlite3.connect(db) as con:
        retain_count = con.execute(
            "SELECT COUNT(*) FROM paid_operation_ledger WHERE movement_type = 'retain'"
        ).fetchone()[0]
    budget = PaidOperationLedger(db).get_budget("acct-1")
    snapshot = PaidOperationStore(db).get_owned(Subject("owner-1", "acct-1"), "op-1")
    assert retain_count == 0
    assert budget is not None
    assert budget.reserved_cents == 20
    assert budget.settled_cents == 0
    assert snapshot is not None
    assert snapshot.state == "running"


@pytest.mark.parametrize(
    ("column", "value", "message"),
    [
        ("provider_id", "other-provider", "provider route"),
        ("provider_receipt", "other-receipt", "provider material hash"),
        ("response_body_json", '{"answer":"tampered"}', "response body hash"),
        ("idempotency_key", "b" * 64, "idempotency material"),
        ("observed_cost_cents", 6, "provider material hash"),
    ],
)
def test_startup_rejects_corrupt_checkpoint_material(
    tmp_path: Path,
    column: str,
    value: object,
    message: str,
) -> None:
    db = tmp_path / "authority.sqlite3"
    _queued(db)
    PaidOperationLedger(db).set_account_budget("acct-1", "period-1", 100)
    provider = FakePaidOperationProvider(
        _cap(), results={"dispatch": ProviderResult({"answer": "ok"}, "receipt-1", 7)}
    )
    PaidOperationWorker(db, provider, clock_ms=Clock()).execute_one("worker-1", lease_ms=500)
    statements = {
        "provider_id": "UPDATE paid_operation_checkpoints SET provider_id = ?",
        "provider_receipt": "UPDATE paid_operation_checkpoints SET provider_receipt = ?",
        "response_body_json": "UPDATE paid_operation_checkpoints SET response_body_json = ?",
        "idempotency_key": "UPDATE paid_operation_checkpoints SET idempotency_key = ?",
        "observed_cost_cents": "UPDATE paid_operation_checkpoints SET observed_cost_cents = ?",
    }
    with sqlite3.connect(db) as con:
        con.execute(statements[column], (value,))

    with pytest.raises(PaidOperationCorruptionError, match=message):
        PaidOperationStore(db)


def test_startup_rejects_checkpoint_ledger_corruption(tmp_path: Path) -> None:
    db = tmp_path / "authority.sqlite3"
    _queued(db)
    PaidOperationLedger(db).set_account_budget("acct-1", "period-1", 100)
    provider = FakePaidOperationProvider(
        _cap(), results={"dispatch": ProviderResult({"answer": "ok"}, "receipt-1", 7)}
    )
    PaidOperationWorker(db, provider, clock_ms=Clock()).execute_one("worker-1", lease_ms=500)
    with sqlite3.connect(db) as con:
        con.execute("DELETE FROM paid_operation_ledger WHERE movement_type = 'release'")
        con.execute("UPDATE paid_account_budgets SET reserved_cents = 13")

    with pytest.raises(PaidOperationCorruptionError, match="ledger is incomplete"):
        PaidOperationStore(db)


def test_startup_rejects_terminal_result_checkpoint_hash_corruption(tmp_path: Path) -> None:
    db = tmp_path / "authority.sqlite3"
    _queued(db)
    PaidOperationLedger(db).set_account_budget("acct-1", "period-1", 100)
    provider = FakePaidOperationProvider(
        _cap(), results={"dispatch": ProviderResult({"answer": "ok"}, "receipt-1", 7)}
    )
    PaidOperationWorker(db, provider, clock_ms=Clock()).execute_one("worker-1", lease_ms=500)
    with sqlite3.connect(db) as con:
        con.execute(
            "UPDATE paid_operations SET result_checkpoint_hash = ?",
            ("b" * 64,),
        )
    with pytest.raises(PaidOperationCorruptionError, match="checkpoint hash"):
        PaidOperationStore(db)
