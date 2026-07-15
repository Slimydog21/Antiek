from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any, cast

import pytest

from substrate.paid_operations import (
    ConsentKeyring,
    FakePaidOperationProvider,
    OperationConflict,
    OperatorSubject,
    PaidOperationConsentService,
    PaidOperationCorruptionError,
    PaidOperationLedger,
    PaidOperationReconciler,
    PaidOperationStore,
    PaidOperationWorker,
    ProviderCapabilityAttestation,
    ProviderResult,
    ReconciliationCommand,
    Subject,
    UnknownProviderOutcome,
)
from tests.test_paid_operation_store import collective_payload


class Clock:
    value = 1_200

    def __call__(self) -> int:
        return self.value


def _cap() -> ProviderCapabilityAttestation:
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
        enabled=True,
        documentation_hash="b" * 64,
        behavior_evidence_hash="c" * 64,
        live_smoke_operator_id="operator-1",
        live_smoke_authorization_hash="d" * 64,
    )


def _reconciler(
    db: Path,
    clock: Clock,
    *,
    authorized: frozenset[str] = frozenset({"operator-1"}),
) -> PaidOperationReconciler:
    return PaidOperationReconciler(
        db,
        clock_ms=clock,
        authorize_operator=lambda operator_user_id: operator_user_id in authorized,
    )


def _unknown(
    db: Path,
    clock: Clock,
    *,
    subject: Subject | None = None,
    operation_id: str = "op-1",
    outcome: UnknownProviderOutcome | ProviderResult | None = None,
) -> None:
    store = PaidOperationStore(db)
    service = PaidOperationConsentService(
        store,
        ConsentKeyring(active_key_id="key-1", keys={"key-1": b"k" * 32}),
        clock_ms=lambda: 1_100,
        nonce_factory=lambda: b"n" * 32,
    )
    subject = subject or Subject("owner-1", "acct-1")
    store.create_or_replay(subject, operation_id, "collective_interrogation_v1", collective_payload())
    token = service.issue(subject, operation_id).token
    service.claim(subject, operation_id, token=token, options={})
    PaidOperationLedger(db).set_account_budget(subject.account_id, "period-1", 100)
    provider = FakePaidOperationProvider(
        _cap(),
        results={"dispatch": outcome or UnknownProviderOutcome("lost")},
    )
    receipt = PaidOperationWorker(db, provider, clock_ms=clock).execute_one("worker-1", lease_ms=500)
    assert receipt is not None
    assert receipt.state == "failed_reconcile"
    assert len(provider.calls) == 1


def test_over_reserve_checkpoint_evidence_survives_operator_reconciliation(tmp_path: Path) -> None:
    db = tmp_path / "authority.sqlite3"
    clock = Clock()
    _unknown(
        db,
        clock,
        outcome=ProviderResult({"answer": "definite"}, "receipt-over", 21),
    )
    failed = PaidOperationStore(db).get_owned(Subject("owner-1", "acct-1"), "op-1")
    assert failed is not None
    assert failed.result_checkpoint_hash is not None

    _reconciler(db, clock).reconcile(
        OperatorSubject("operator-1"),
        ReconciliationCommand(
            command_id="recon-1",
            subject=Subject("owner-1", "acct-1"),
            operation_id="op-1",
            operation_version=failed.version,
            evidence_hash="b" * 64,
            decision="confirm_not_charged",
            reason="billing evidence proved no charge",
        ),
    )

    final = PaidOperationStore(db).get_owned(Subject("owner-1", "acct-1"), "op-1")
    assert final is not None
    assert final.state == "complete"
    assert final.result_checkpoint_hash == failed.result_checkpoint_hash
    with sqlite3.connect(db) as con:
        assert con.execute("SELECT response_body_json FROM paid_operation_checkpoints").fetchone()[0] == (
            '{"answer":"definite"}'
        )


def test_over_reserve_external_charge_settles_only_authorized_hold_and_replays(
    tmp_path: Path,
) -> None:
    db = tmp_path / "authority.sqlite3"
    clock = Clock()
    _unknown(
        db,
        clock,
        outcome=ProviderResult({"answer": "definite"}, "receipt-over", 21),
    )
    subject = Subject("owner-1", "acct-1")
    failed = PaidOperationStore(db).get_owned(subject, "op-1")
    assert failed is not None
    assert failed.ceiling_cents == 20
    command = ReconciliationCommand(
        command_id="recon-overage-1",
        subject=subject,
        operation_id="op-1",
        operation_version=failed.version,
        evidence_hash="b" * 64,
        decision="confirm_charged",
        charged_cents=21,
        reason="provider receipt and invoice confirm the external charge",
    )

    checkpoint_conflict = ReconciliationCommand(**{**command.__dict__, "charged_cents": 22})
    with pytest.raises(OperationConflict, match="provider checkpoint"):
        _reconciler(db, clock).reconcile(OperatorSubject("operator-1"), checkpoint_conflict)
    first = _reconciler(db, clock).reconcile(OperatorSubject("operator-1"), command)
    assert first.authorized_settled_cents == first.movement.cents == 20
    assert first.external_charged_cents == 21
    assert first.external_overage_cents == 1

    restarted = PaidOperationStore(db)
    final = restarted.get_owned(subject, "op-1")
    assert final is not None
    assert final.settled_cents == 20
    assert final.external_charged_cents == 21
    assert final.external_overage_cents == 1
    replay = _reconciler(db, clock).reconcile(OperatorSubject("operator-1"), command)
    assert replay == first
    conflict = ReconciliationCommand(**{**command.__dict__, "charged_cents": 22})
    with pytest.raises(OperationConflict, match="replay conflicts"):
        _reconciler(db, clock).reconcile(OperatorSubject("operator-1"), conflict)

    budget = PaidOperationLedger(db).get_budget("acct-1")
    assert budget is not None
    assert budget.reserved_cents == 0
    assert budget.settled_cents == final.ceiling_cents == 20
    assert budget.reserved_cents + budget.settled_cents <= budget.limit_cents
    with sqlite3.connect(db) as con:
        audit = con.execute(
            "SELECT charged_cents, authorized_settled_cents "
            "FROM paid_operation_reconciliation_audit"
        ).fetchone()
        checkpoint_charge = con.execute(
            "SELECT observed_cost_cents FROM paid_operation_checkpoints"
        ).fetchone()[0]
        releases = con.execute(
            "SELECT COUNT(*) FROM paid_operation_ledger WHERE movement_type = 'release'"
        ).fetchone()[0]
    assert audit == (21, 20)
    assert checkpoint_charge == 21
    assert releases == 0


@pytest.mark.parametrize(
    ("sql", "message"),
    [
        (
            "UPDATE paid_operation_reconciliation_audit SET charged_cents = 22",
            "external charge conflicts with checkpoint",
        ),
        (
            "UPDATE paid_operation_reconciliation_audit SET authorized_settled_cents = 19",
            "authorized settlement conflicts",
        ),
        (
            "UPDATE paid_operations SET external_charged_cents = 22",
            "terminal is incoherent",
        ),
    ],
)
def test_startup_rejects_over_reserve_external_or_authorized_settlement_drift(
    tmp_path: Path,
    sql: str,
    message: str,
) -> None:
    db = tmp_path / "authority.sqlite3"
    clock = Clock()
    _unknown(
        db,
        clock,
        outcome=ProviderResult({"answer": "definite"}, "receipt-over", 21),
    )
    subject = Subject("owner-1", "acct-1")
    failed = PaidOperationStore(db).get_owned(subject, "op-1")
    assert failed is not None
    _reconciler(db, clock).reconcile(
        OperatorSubject("operator-1"),
        ReconciliationCommand(
            command_id="recon-overage-1",
            subject=subject,
            operation_id="op-1",
            operation_version=failed.version,
            evidence_hash="b" * 64,
            decision="confirm_charged",
            charged_cents=21,
            reason="provider receipt and invoice confirm the external charge",
        ),
    )
    with sqlite3.connect(db) as con:
        con.execute(sql)

    with pytest.raises(PaidOperationCorruptionError, match=message):
        PaidOperationStore(db)


def test_unknown_outcome_retains_hold_then_operator_releases_with_replay(tmp_path: Path) -> None:
    db = tmp_path / "authority.sqlite3"
    clock = Clock()
    _unknown(db, clock)
    budget = PaidOperationLedger(db).get_budget("acct-1")
    assert budget is not None
    assert budget.reserved_cents == 20
    store = PaidOperationStore(db)
    failed = store.get_owned(Subject("owner-1", "acct-1"), "op-1")
    assert failed is not None
    assert failed.state == "failed_reconcile"
    command = ReconciliationCommand(
        command_id="recon-1",
        subject=Subject("owner-1", "acct-1"),
        operation_id="op-1",
        operation_version=failed.version,
        evidence_hash="b" * 64,
        decision="confirm_not_charged",
        reason="billing report showed no charge",
    )
    reconciler = _reconciler(db, clock)
    operator = OperatorSubject("operator-1", frozenset({"paid_operation_reconciler"}))
    first = reconciler.reconcile(operator, command)
    replay = reconciler.reconcile(operator, command)
    assert replay == first
    final_budget = PaidOperationLedger(db).get_budget("acct-1")
    assert final_budget is not None
    assert final_budget.reserved_cents == final_budget.settled_cents == 0
    assert PaidOperationStore(db).get_owned(Subject("owner-1", "acct-1"), "op-1").state == "complete"  # type: ignore[union-attr]


def test_confirm_not_charged_requires_zero_charged_cents(tmp_path: Path) -> None:
    db = tmp_path / "authority.sqlite3"
    clock = Clock()
    _unknown(db, clock)
    failed = PaidOperationStore(db).get_owned(Subject("owner-1", "acct-1"), "op-1")
    assert failed is not None
    command = ReconciliationCommand(
        command_id="recon-1",
        subject=Subject("owner-1", "acct-1"),
        operation_id="op-1",
        operation_version=failed.version,
        evidence_hash="b" * 64,
        decision="confirm_not_charged",
        charged_cents=1,
        reason="billing report showed no charge",
    )

    with pytest.raises(OperationConflict, match="zero cents"):
        _reconciler(db, clock).reconcile(
            OperatorSubject("operator-1", frozenset({"paid_operation_reconciler"})),
            command,
        )


def test_reconciliation_requires_operator_and_conflicts_on_changed_evidence(tmp_path: Path) -> None:
    db = tmp_path / "authority.sqlite3"
    clock = Clock()
    _unknown(db, clock)
    failed = PaidOperationStore(db).get_owned(Subject("owner-1", "acct-1"), "op-1")
    assert failed is not None
    command = ReconciliationCommand(
        command_id="recon-1",
        subject=Subject("owner-1", "acct-1"),
        operation_id="op-1",
        operation_version=failed.version,
        evidence_hash="b" * 64,
        decision="confirm_charged",
        charged_cents=12,
        reason="provider receipt matched invoice",
    )
    denied = _reconciler(db, clock, authorized=frozenset())
    with pytest.raises(OperationConflict, match="not authorized"):
        denied.reconcile(
            OperatorSubject("operator-1", frozenset({"paid_operation_reconciler", "admin"})),
            command,
        )
    reconciler = _reconciler(db, clock)
    operator = OperatorSubject("operator-1")
    reconciler.reconcile(operator, command)
    drift = ReconciliationCommand(**{**command.__dict__, "evidence_hash": "c" * 64})
    with pytest.raises(OperationConflict, match="replay conflicts"):
        reconciler.reconcile(operator, drift)
    charged_drift = ReconciliationCommand(**{**command.__dict__, "charged_cents": 13})
    with pytest.raises(OperationConflict, match="replay conflicts"):
        reconciler.reconcile(operator, charged_drift)
    step_drift = ReconciliationCommand(**{**command.__dict__, "step_id": "other-step"})
    with pytest.raises(OperationConflict, match="replay conflicts"):
        reconciler.reconcile(operator, step_drift)
    budget = PaidOperationLedger(db).get_budget("acct-1")
    assert budget is not None
    assert budget.reserved_cents == 0
    assert budget.settled_cents == 12


@pytest.mark.parametrize(
    "command_patch",
    [
        {"command_id": "NOT-CANONICAL"},
        {"operation_version": True},
        {"evidence_hash": "not-a-hash"},
        {"decision": "trust_me"},
        {"reason": ""},
        {"charged_cents": True},
        {"step_id": "NOT-CANONICAL"},
    ],
)
def test_invalid_reconciliation_command_material_cannot_mutate_or_poison_startup(
    tmp_path: Path,
    command_patch: dict[str, Any],
) -> None:
    db = tmp_path / "authority.sqlite3"
    clock = Clock()
    _unknown(db, clock)
    failed = PaidOperationStore(db).get_owned(Subject("owner-1", "acct-1"), "op-1")
    assert failed is not None
    material: dict[str, Any] = {
        "command_id": "recon-1",
        "subject": Subject("owner-1", "acct-1"),
        "operation_id": "op-1",
        "operation_version": failed.version,
        "evidence_hash": "b" * 64,
        "decision": "confirm_charged",
        "reason": "provider receipt matched invoice",
        "charged_cents": 12,
        "step_id": "dispatch",
    }
    material.update(command_patch)

    with pytest.raises(OperationConflict):
        _reconciler(db, clock).reconcile(OperatorSubject("operator-1"), ReconciliationCommand(**material))

    with sqlite3.connect(db) as con:
        assert con.execute("SELECT COUNT(*) FROM paid_operation_reconciliation_audit").fetchone()[0] == 0
        assert con.execute("SELECT COUNT(*) FROM paid_operation_ledger").fetchone()[0] == 2
    assert PaidOperationStore(db).get_owned(Subject("owner-1", "acct-1"), "op-1") is not None


@pytest.mark.parametrize(
    ("decision", "charged_cents", "message"),
    [
        ("confirm_charged", 12, "reconciliation movement requires exactly one audit"),
        ("confirm_not_charged", 0, "reconciled terminal requires exactly one audit"),
    ],
)
def test_startup_reverse_validates_reconciled_terminal_and_movement_audits(
    tmp_path: Path,
    decision: str,
    charged_cents: int,
    message: str,
) -> None:
    db = tmp_path / "authority.sqlite3"
    clock = Clock()
    _unknown(db, clock)
    failed = PaidOperationStore(db).get_owned(Subject("owner-1", "acct-1"), "op-1")
    assert failed is not None
    _reconciler(db, clock).reconcile(
        OperatorSubject("operator-1"),
        ReconciliationCommand(
            command_id="recon-1",
            subject=Subject("owner-1", "acct-1"),
            operation_id="op-1",
            operation_version=failed.version,
            evidence_hash="b" * 64,
            decision=cast(Any, decision),
            charged_cents=charged_cents,
            reason="server-verified billing evidence",
        ),
    )
    with sqlite3.connect(db) as con:
        con.execute("DELETE FROM paid_operation_reconciliation_audit")

    with pytest.raises(PaidOperationCorruptionError, match=message):
        PaidOperationStore(db)


def test_reconciliation_command_identity_is_tenant_scoped(tmp_path: Path) -> None:
    db = tmp_path / "authority.sqlite3"
    clock = Clock()
    _unknown(db, clock, subject=Subject("owner-1", "acct-1"))
    _unknown(db, clock, subject=Subject("owner-1", "acct-2"))
    reconciler = _reconciler(db, clock)
    operator = OperatorSubject("operator-1", frozenset({"paid_operation_reconciler"}))
    first_failed = PaidOperationStore(db).get_owned(Subject("owner-1", "acct-1"), "op-1")
    second_failed = PaidOperationStore(db).get_owned(Subject("owner-1", "acct-2"), "op-1")
    assert first_failed is not None
    assert second_failed is not None

    for subject, version in (
        (Subject("owner-1", "acct-1"), first_failed.version),
        (Subject("owner-1", "acct-2"), second_failed.version),
    ):
        reconciler.reconcile(
            operator,
            ReconciliationCommand(
                command_id="recon-1",
                subject=subject,
                operation_id="op-1",
                operation_version=version,
                evidence_hash="b" * 64,
                decision="confirm_not_charged",
                reason="tenant-local command id",
            ),
        )

    assert PaidOperationStore(db).get_owned(Subject("owner-1", "acct-1"), "op-1").state == "complete"  # type: ignore[union-attr]
    assert PaidOperationStore(db).get_owned(Subject("owner-1", "acct-2"), "op-1").state == "complete"  # type: ignore[union-attr]


def test_reconciliation_rolls_back_movement_when_terminal_write_fails(tmp_path: Path) -> None:
    db = tmp_path / "authority.sqlite3"
    clock = Clock()
    _unknown(db, clock)
    failed = PaidOperationStore(db).get_owned(Subject("owner-1", "acct-1"), "op-1")
    assert failed is not None
    command = ReconciliationCommand(
        command_id="recon-1",
        subject=Subject("owner-1", "acct-1"),
        operation_id="op-1",
        operation_version=failed.version,
        evidence_hash="b" * 64,
        decision="confirm_charged",
        charged_cents=12,
        reason="provider receipt matched invoice",
    )
    reconciler = _reconciler(db, clock)
    original = reconciler.ledger._movement_in_tx  # noqa: SLF001

    def fail_on_release(*args: Any, **kwargs: Any) -> object:
        if kwargs.get("movement_type") == "release":
            raise RuntimeError("simulated terminal-phase failure")
        return original(*args, **kwargs)

    cast(Any, reconciler.ledger)._movement_in_tx = fail_on_release  # noqa: SLF001
    with pytest.raises(RuntimeError, match="simulated"):
        reconciler.reconcile(
            OperatorSubject("operator-1", frozenset({"paid_operation_reconciler"})),
            command,
        )

    with sqlite3.connect(db) as con:
        movement_count = con.execute(
            "SELECT COUNT(*) FROM paid_operation_ledger WHERE movement_type = 'reconcile'"
        ).fetchone()[0]
        audit_count = con.execute("SELECT COUNT(*) FROM paid_operation_reconciliation_audit").fetchone()[0]
    budget = PaidOperationLedger(db).get_budget("acct-1")
    assert movement_count == 0
    assert audit_count == 0
    assert budget is not None
    assert budget.reserved_cents == 20
    assert budget.settled_cents == 0
    assert PaidOperationStore(db).get_owned(Subject("owner-1", "acct-1"), "op-1").state == "failed_reconcile"  # type: ignore[union-attr]


def test_startup_rejects_reconciliation_audit_with_nonzero_not_charged(tmp_path: Path) -> None:
    db = tmp_path / "authority.sqlite3"
    clock = Clock()
    _unknown(db, clock)
    failed = PaidOperationStore(db).get_owned(Subject("owner-1", "acct-1"), "op-1")
    assert failed is not None
    _reconciler(db, clock).reconcile(
        OperatorSubject("operator-1", frozenset({"paid_operation_reconciler"})),
        ReconciliationCommand(
            command_id="recon-1",
            subject=Subject("owner-1", "acct-1"),
            operation_id="op-1",
            operation_version=failed.version,
            evidence_hash="b" * 64,
            decision="confirm_not_charged",
            reason="billing report showed no charge",
        ),
    )
    with sqlite3.connect(db) as con:
        con.execute(
            "UPDATE paid_operation_reconciliation_audit SET charged_cents = 1 "
            "WHERE account_id = 'acct-1'"
        )

    with pytest.raises(PaidOperationCorruptionError, match="zero cents"):
        PaidOperationStore(db)


def test_startup_rejects_reconciliation_audit_movement_type_conflict(tmp_path: Path) -> None:
    db = tmp_path / "authority.sqlite3"
    clock = Clock()
    _unknown(db, clock)
    failed = PaidOperationStore(db).get_owned(Subject("owner-1", "acct-1"), "op-1")
    assert failed is not None
    _reconciler(db, clock).reconcile(
        OperatorSubject("operator-1", frozenset({"paid_operation_reconciler"})),
        ReconciliationCommand(
            command_id="recon-1",
            subject=Subject("owner-1", "acct-1"),
            operation_id="op-1",
            operation_version=failed.version,
            evidence_hash="b" * 64,
            decision="confirm_not_charged",
            reason="billing report showed no charge",
        ),
    )
    with sqlite3.connect(db) as con:
        retain_key = con.execute(
            "SELECT movement_key FROM paid_operation_ledger WHERE movement_type = 'retain'"
        ).fetchone()[0]
        con.execute(
            "UPDATE paid_operation_reconciliation_audit SET movement_key = ? "
            "WHERE account_id = 'acct-1'",
            (retain_key,),
        )

    with pytest.raises(PaidOperationCorruptionError, match="movement type conflicts"):
        PaidOperationStore(db)


def test_startup_rejects_reconciliation_audit_cross_tenant_movement(tmp_path: Path) -> None:
    db = tmp_path / "authority.sqlite3"
    clock = Clock()
    _unknown(db, clock, subject=Subject("owner-1", "acct-1"))
    _unknown(db, clock, subject=Subject("owner-1", "acct-2"))
    reconciler = _reconciler(db, clock)
    operator = OperatorSubject("operator-1", frozenset({"paid_operation_reconciler"}))
    first_failed = PaidOperationStore(db).get_owned(Subject("owner-1", "acct-1"), "op-1")
    second_failed = PaidOperationStore(db).get_owned(Subject("owner-1", "acct-2"), "op-1")
    assert first_failed is not None
    assert second_failed is not None
    for subject, version in (
        (Subject("owner-1", "acct-1"), first_failed.version),
        (Subject("owner-1", "acct-2"), second_failed.version),
    ):
        reconciler.reconcile(
            operator,
            ReconciliationCommand(
                command_id="recon-1",
                subject=subject,
                operation_id="op-1",
                operation_version=version,
                evidence_hash="b" * 64,
                decision="confirm_not_charged",
                reason="tenant-local command id",
            ),
        )
    with sqlite3.connect(db) as con:
        other_release = con.execute(
            "SELECT movement_key FROM paid_operation_ledger "
            "WHERE account_id = 'acct-2' AND movement_type = 'release'"
        ).fetchone()[0]
        con.execute(
            "UPDATE paid_operation_reconciliation_audit SET movement_key = ? "
            "WHERE account_id = 'acct-1'",
            (other_release,),
        )

    with pytest.raises(PaidOperationCorruptionError, match="identity conflicts"):
        PaidOperationStore(db)


def test_startup_rejects_reconciliation_terminal_incoherence(tmp_path: Path) -> None:
    db = tmp_path / "authority.sqlite3"
    clock = Clock()
    _unknown(db, clock)
    failed = PaidOperationStore(db).get_owned(Subject("owner-1", "acct-1"), "op-1")
    assert failed is not None
    _reconciler(db, clock).reconcile(
        OperatorSubject("operator-1", frozenset({"paid_operation_reconciler"})),
        ReconciliationCommand(
            command_id="recon-1",
            subject=Subject("owner-1", "acct-1"),
            operation_id="op-1",
            operation_version=failed.version,
            evidence_hash="b" * 64,
            decision="confirm_not_charged",
            reason="billing report showed no charge",
        ),
    )
    with sqlite3.connect(db) as con:
        con.execute(
            "UPDATE paid_operations SET terminal_code = 'reconciled_charged' "
            "WHERE account_id = 'acct-1'"
        )

    with pytest.raises(PaidOperationCorruptionError, match="terminal is incoherent"):
        PaidOperationStore(db)
