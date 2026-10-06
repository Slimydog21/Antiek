"""Real temporary SQLite tests for owner escrow and provider attempts."""

from __future__ import annotations

import hashlib
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from threading import Barrier

import pytest

from substrate.byot_usage.actions import (
    MAX_MONEY,
    ApprovedOwnerRoute,
    AttemptProposal,
    CanonicalInputBinding,
    FinalSendFacts,
    OwnerActionDecision,
    VerifiedAttemptFacts,
)
from substrate.byot_usage.ledger import (
    ByotUsageLedger,
    OperationConflict,
    SettlementEvidenceError,
)


def decision(action_id: str = "action", budget: int = 100, owner: str = "owner") -> OwnerActionDecision:
    return OwnerActionDecision(
        owner, action_id, "long_document_wrestling", budget, "b" * 64, "d" * 64,
        (ApprovedOwnerRoute("record-a", "provider", "model", "a" * 64),
         ApprovedOwnerRoute("record-b", "provider", "model", "a" * 64)),
    )


def proposal(
    attempt_id: str = "attempt", reserved: int = 30, record: str = "record-a",
    *, parent: str | None = None, epoch: int = 0,
) -> AttemptProposal:
    return AttemptProposal(
        attempt_id, record, "provider", "model", "a" * 64, "c" * 64, "e" * 64,
        reserved, epoch, parent_operation_id=parent,
        attempt_kind="prime_child" if parent else "canonical",
    )


def send_facts(attempt: AttemptProposal) -> FinalSendFacts:
    return FinalSendFacts(
        "f" * 64, attempt.authority_digest, attempt.route_digest, attempt.rate_limit_digest,
        "b" * 64, hashlib.sha256(attempt.operation_id.encode()).hexdigest(), attempt.action_epoch,
    )


def result(attempt: AttemptProposal, cents: int = 10, *, micro_usd: int | None = None) -> VerifiedAttemptFacts:
    return VerifiedAttemptFacts(
        attempt.provider_id, attempt.model_id, f"event-{attempt.operation_id}",
        "2" * 64, "f" * 64, cents * 10000 if micro_usd is None else micro_usd,
        result_reference=f"evidence/{attempt.operation_id}", result_text="stored answer",
    )


def allocated(ledger: ByotUsageLedger, attempt: AttemptProposal) -> None:
    ledger.allocate_action_attempt("owner", "action", attempt)


def sent(ledger: ByotUsageLedger, attempt: AttemptProposal) -> None:
    allocated(ledger, attempt)
    assert ledger.claim_action_attempt("owner", attempt.operation_id, send_facts(attempt)).won


def settled(ledger: ByotUsageLedger, attempt: AttemptProposal, cents: int = 10) -> None:
    sent(ledger, attempt)
    ledger.record_action_attempt_result("owner", attempt.operation_id, result(attempt, cents))
    ledger.settle_action_attempt("owner", attempt.operation_id)


def test_canonical_input_is_atomic_and_separate_from_wire_claim(tmp_path: Path) -> None:
    ledger = ByotUsageLedger(tmp_path / "usage.sqlite3")
    ledger.begin_action(decision())
    attempt = proposal()
    binding = CanonicalInputBinding("1" * 64, "2" * 64)
    ledger.allocate_action_attempt("owner", "action", attempt, canonical_input=binding)
    assert ledger.canonical_input_binding("owner", "attempt") == binding
    assert ledger.owner_usage("owner").held_cents == 100
    for other in (None, replace(binding, logical_digest="3" * 64)):
        with pytest.raises(OperationConflict, match="cannot be rebound"):
            ledger.allocate_action_attempt("owner", "action", attempt, canonical_input=other)
        with pytest.raises(OperationConflict, match="differs from allocation"):
            ledger.claim_action_attempt(
                "owner", "attempt", replace(send_facts(attempt), canonical_input=other),
            )
    assert ledger.action_attempt("owner", "attempt").operation.state == "allocated"
    claimed = ledger.claim_action_attempt(
        "owner", "attempt", replace(send_facts(attempt), canonical_input=binding),
    )
    assert claimed.won and claimed.attempt.request_digest == "f" * 64
    assert claimed.attempt.request_digest != binding.logical_digest
    assert ledger.canonical_input_binding("owner", "attempt") == binding
    assert ledger.owner_usage("owner").held_cents == 100


def test_canonical_binding_failure_rolls_back_new_operation(tmp_path: Path) -> None:
    path = tmp_path / "usage.sqlite3"
    ledger = ByotUsageLedger(path)
    ledger.begin_action(decision())
    with sqlite3.connect(path) as con:
        con.execute(
            "CREATE TRIGGER reject_input BEFORE INSERT ON byot_canonical_input"
            " BEGIN SELECT RAISE(ABORT,'private injected binding failure'); END"
        )
    with pytest.raises(sqlite3.IntegrityError, match="binding failure"):
        ledger.allocate_action_attempt(
            "owner", "action", proposal(),
            canonical_input=CanonicalInputBinding("1" * 64, "2" * 64),
        )
    assert ledger.operation("owner", "attempt") is None
    assert ledger.canonical_input_binding("owner", "attempt") is None
    assert ledger.action("owner", "action").reserved_cents == 0
    assert ledger.owner_usage("owner").held_cents == 100


def test_v5_request_digest_remains_legacy_after_canonical_upgrade(tmp_path: Path) -> None:
    path = tmp_path / "usage.sqlite3"
    ledger = ByotUsageLedger(path)
    ledger.begin_action(decision())
    attempt = proposal()
    sent(ledger, attempt)
    before = ledger.action_attempt("owner", "attempt")
    with sqlite3.connect(path) as con:
        con.execute("DROP TABLE byot_canonical_input")
        con.execute("UPDATE byot_usage_meta SET value='5' WHERE key='schema_version'")
    upgraded = ByotUsageLedger(path)
    assert upgraded.action_attempt("owner", "attempt") == before
    assert upgraded.canonical_input_binding("owner", "attempt") is None
    with pytest.raises(OperationConflict, match="differs from allocation"):
        upgraded.claim_action_attempt(
            "owner", "attempt", replace(
                send_facts(attempt), canonical_input=CanonicalInputBinding("1" * 64, "2" * 64),
            ),
        )
    assert upgraded.action_attempt("owner", "attempt") == before


def _seed_v3(path: Path) -> tuple[list[tuple[object, ...]], list[tuple[object, ...]]]:
    with sqlite3.connect(path) as con:
        con.executescript("""
            CREATE TABLE byot_usage_meta(key TEXT PRIMARY KEY,value TEXT NOT NULL);
            INSERT INTO byot_usage_meta VALUES('schema_version','3');
            CREATE TABLE byot_key_usage(api_key_id TEXT NOT NULL,owner_user_id TEXT NOT NULL,
                used_cents INTEGER NOT NULL DEFAULT 0,limit_cents INTEGER,last_settled_at TEXT,
                updated_at TEXT NOT NULL,PRIMARY KEY(api_key_id,owner_user_id));
            CREATE TABLE byot_operation_journal(api_key_id TEXT NOT NULL,owner_user_id TEXT NOT NULL,
                operation_id TEXT NOT NULL,state TEXT NOT NULL,reserved_cents INTEGER NOT NULL,
                actual_cents INTEGER,authority_digest TEXT NOT NULL,evidence_sha256 TEXT,
                provider_id TEXT,model_id TEXT,dispatch_event_id TEXT,result_text TEXT,
                created_at TEXT NOT NULL,updated_at TEXT NOT NULL,
                PRIMARY KEY(owner_user_id,operation_id));
            INSERT INTO byot_key_usage VALUES('legacy','owner',13,500,'prior','prior');
        """)
        for state in ("prepared", "sent", "settlement_pending", "settled", "unknown", "cancelled"):
            con.execute(
                "INSERT INTO byot_operation_journal VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                ("legacy", "owner", state, state, 7, 5 if state in ("settled", "settlement_pending") else None,
                 "a" * 64, "b" * 64, "provider", "model", "event", "result", "prior", "prior"),
            )
        return (con.execute("SELECT * FROM byot_key_usage").fetchall(),
                con.execute("SELECT * FROM byot_operation_journal ORDER BY operation_id").fetchall())


def test_v3_migration_preserves_every_legacy_state_and_result(tmp_path: Path) -> None:
    path = tmp_path / "usage.sqlite3"
    keys, operations = _seed_v3(path)
    ledger = ByotUsageLedger(path)
    with sqlite3.connect(path) as con:
        assert con.execute("SELECT * FROM byot_key_usage").fetchall() == keys
        migrated = con.execute("SELECT * FROM byot_operation_journal ORDER BY operation_id").fetchall()
        assert [row[:14] for row in migrated] == operations
        assert all(row[14] is None for row in migrated)
        assert con.execute("SELECT value FROM byot_usage_meta WHERE key='schema_version'").fetchone() == ("6",)
        journal_id = con.execute("SELECT value FROM byot_usage_meta WHERE key='journal_id'").fetchone()
    assert ledger.key_usage("legacy", "owner").held_cents == 28  # type: ignore[union-attr]
    ByotUsageLedger(path)
    with sqlite3.connect(path) as con:
        assert con.execute("SELECT value FROM byot_usage_meta WHERE key='journal_id'").fetchone() == journal_id


def test_two_migration_openers_share_one_durable_journal(tmp_path: Path) -> None:
    path = tmp_path / "usage.sqlite3"
    _seed_v3(path)
    barrier = Barrier(2)

    def open_ledger(_: int) -> int:
        barrier.wait()
        return ByotUsageLedger(path).owner_usage("owner").used_cents

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert list(pool.map(open_ledger, range(2))) == [13, 13]
    with sqlite3.connect(path) as con:
        assert con.execute("SELECT COUNT(*) FROM byot_usage_meta WHERE key='journal_id'").fetchone() == (1,)


def test_future_schema_is_refused_without_version_or_schema_rewrite(tmp_path: Path) -> None:
    path = tmp_path / "usage.sqlite3"
    with sqlite3.connect(path) as con:
        con.execute("CREATE TABLE byot_usage_meta(key TEXT PRIMARY KEY,value TEXT NOT NULL)")
        con.execute("INSERT INTO byot_usage_meta VALUES('schema_version','99')")
    with pytest.raises(ValueError, match="unsupported"):
        ByotUsageLedger(path)
    with sqlite3.connect(path) as con:
        assert con.execute("SELECT value FROM byot_usage_meta").fetchall() == [("99",)]
        assert con.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall() == [("byot_usage_meta",)]


def test_parent_escrow_and_record_allocations_do_not_double_hold(tmp_path: Path) -> None:
    ledger = ByotUsageLedger(tmp_path / "usage.sqlite3")
    ledger.set_owner_limit("owner", 100)
    action = ledger.begin_action(decision())
    assert action.ref.epoch == 0
    root = proposal("canonical", 30)
    child = proposal("child", 40, "record-b", parent="canonical")
    sent(ledger, root)
    sent(ledger, child)
    assert ledger.owner_usage("owner").held_cents == 100
    assert [(row.api_key_id, row.used_cents, row.held_cents) for row in ledger.snapshot("owner")] == [
        ("record-a", 0, 30), ("record-b", 0, 40),
    ]
    ledger.record_action_attempt_result("owner", "canonical", result(root))
    ledger.settle_action_attempt("owner", "canonical")
    action = ledger.action("owner", "action")
    assert action is not None
    assert (action.settled_cents, action.reserved_cents, action.available_cents, action.owner_held_cents) == (10, 40, 50, 90)
    usage = ledger.owner_usage("owner")
    assert (usage.used_cents, usage.held_cents, usage.available_cents) == (10, 90, 0)
    closed = ledger.close_action("owner", "action", expected_epoch=0)
    assert (closed.state, closed.epoch, closed.owner_held_cents) == ("closing", 1, 40)
    ledger.mark_action_attempt_unknown("owner", "child")
    assert ledger.owner_usage("owner").held_cents == 40
    ledger.reconcile_action_attempt_usage("owner", "child", result(child, 20))
    action = ledger.action("owner", "action")
    assert action is not None and action.state == "closed"
    assert (ledger.owner_usage("owner").used_cents, ledger.owner_usage("owner").held_cents) == (30, 0)
    assert len(ledger.pending_projection_events()) == 2


def test_unused_allocation_returns_to_parent_slack_and_close_fences_claim(tmp_path: Path) -> None:
    ledger = ByotUsageLedger(tmp_path / "usage.sqlite3")
    ledger.begin_action(decision())
    attempt = proposal()
    allocated(ledger, attempt)
    cancelled = ledger.cancel_action_attempt("owner", "attempt", expected_epoch=0)
    assert cancelled.operation.state == "cancelled"
    assert ledger.owner_usage("owner").held_cents == 100
    assert ledger.action("owner", "action").available_cents == 100  # type: ignore[union-attr]
    with pytest.raises(OperationConflict):
        ledger.claim_action_attempt("owner", "attempt", send_facts(attempt))
    closed = ledger.close_action("owner", "action", expected_epoch=0)
    assert closed.state == "closed" and closed.owner_held_cents == 0
    assert ledger.close_action("owner", "action", expected_epoch=0) == closed
    assert ledger.begin_action(decision()) == closed
    with pytest.raises(OperationConflict):
        allocated(ledger, proposal("another"))


def test_replay_binds_every_action_and_attempt_field(tmp_path: Path) -> None:
    ledger = ByotUsageLedger(tmp_path / "usage.sqlite3")
    original = decision()
    action = ledger.begin_action(original)
    assert ledger.begin_action(original) == action
    for changed in (replace(original, budget_cents=101), replace(original, body_authority_digest="1" * 64),
                    replace(original, owner_decision_digest="2" * 64),
                    replace(original, approved_routes=original.approved_routes[::-1])):
        with pytest.raises(OperationConflict):
            ledger.begin_action(changed)
    attempt = proposal()
    first = ledger.allocate_action_attempt("owner", "action", attempt)
    assert ledger.allocate_action_attempt("owner", "action", attempt) == first
    for changed in (replace(attempt, reserved_cents=31), replace(attempt, rate_limit_digest="1" * 64),
                    replace(attempt, user_model_id="record-b")):
        with pytest.raises(OperationConflict):
            allocated(ledger, changed)
    ledger.begin_action(decision("another"))
    with pytest.raises(OperationConflict):
        ledger.allocate_action_attempt("owner", "another", attempt)


def test_unapproved_route_parent_and_cross_owner_are_refused(tmp_path: Path) -> None:
    ledger = ByotUsageLedger(tmp_path / "usage.sqlite3")
    ledger.begin_action(decision())
    with pytest.raises(OperationConflict):
        allocated(ledger, replace(proposal(), route_digest="1" * 64))
    with pytest.raises(OperationConflict):
        allocated(ledger, proposal(parent="absent"))
    assert ledger.action("other", "action") is None
    assert ledger.action_attempt("other", "attempt") is None
    with pytest.raises(OperationConflict):
        ledger.allocate_action_attempt("other", "action", proposal())
    ledger.begin_action(decision(owner="other"))
    ledger.allocate_action_attempt("other", "action", proposal())
    assert ledger.owner_usage("owner").used_cents == 0
    assert ledger.owner_usage("other").held_cents == 100


def test_two_simultaneous_owner_admissions_cannot_cross_limit(tmp_path: Path) -> None:
    path = tmp_path / "usage.sqlite3"
    ledger = ByotUsageLedger(path)
    ledger.set_owner_limit("owner", 100)
    barrier = Barrier(2)

    def admit(index: int) -> bool:
        local = ByotUsageLedger(path)
        barrier.wait()
        try:
            local.begin_action(decision(f"action-{index}", 60))
        except OperationConflict:
            return False
        return True

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(admit, range(2))) == [False, True]
    assert ledger.owner_usage("owner").held_cents == 60


def test_two_simultaneous_allocations_share_action_headroom(tmp_path: Path) -> None:
    path = tmp_path / "usage.sqlite3"
    ledger = ByotUsageLedger(path)
    ledger.begin_action(decision())
    barrier = Barrier(2)

    def allocate(index: int) -> bool:
        local = ByotUsageLedger(path)
        barrier.wait()
        try:
            allocated(local, proposal(f"attempt-{index}", 60, f"record-{'a' if index else 'b'}"))
        except OperationConflict:
            return False
        return True

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(allocate, range(2))) == [False, True]
    assert ledger.action("owner", "action").reserved_cents == 60  # type: ignore[union-attr]
    assert ledger.owner_usage("owner").held_cents == 100


def test_ordinary_reservation_racing_action_obeys_owner_limit(tmp_path: Path) -> None:
    path = tmp_path / "usage.sqlite3"
    ledger = ByotUsageLedger(path)
    ledger.set_owner_limit("owner", 100)
    barrier = Barrier(2)

    def reserve(action: bool) -> bool:
        local = ByotUsageLedger(path)
        barrier.wait()
        try:
            if action:
                local.begin_action(decision(budget=60))
            else:
                local.prepare_operation("legacy", "owner", "legacy", 60, "a" * 64)
        except OperationConflict:
            return False
        return True

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(reserve, [True, False])) == [False, True]
    assert ledger.owner_usage("owner").held_cents == 60


def test_duplicate_claim_has_one_winner_and_never_resends(tmp_path: Path) -> None:
    path = tmp_path / "usage.sqlite3"
    ledger = ByotUsageLedger(path)
    ledger.begin_action(decision())
    attempt = proposal()
    allocated(ledger, attempt)
    barrier = Barrier(2)

    def claim(_: int) -> bool:
        local = ByotUsageLedger(path)
        barrier.wait()
        return local.claim_action_attempt("owner", "attempt", send_facts(attempt)).won

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(claim, range(2))) == [False, True]
    with pytest.raises(OperationConflict):
        ledger.claim_action_attempt("owner", "attempt", replace(send_facts(attempt), request_digest="1" * 64))
    assert ledger.action_attempt("owner", "attempt").operation.state == "sent"  # type: ignore[union-attr]


def test_claim_rechecks_lowered_record_limit_without_reserving_twice(tmp_path: Path) -> None:
    ledger = ByotUsageLedger(tmp_path / "usage.sqlite3")
    ledger.set_limit("record-a", "owner", 100)
    ledger.begin_action(decision())
    attempt = proposal(reserved=10)
    allocated(ledger, attempt)
    ledger.set_limit("record-a", "owner", 5)
    with pytest.raises(OperationConflict, match="current local record limit"):
        ledger.claim_action_attempt("owner", "attempt", send_facts(attempt))
    snapshot = ledger.action_attempt("owner", "attempt")
    assert snapshot is not None and snapshot.operation.state == "allocated"
    assert snapshot.request_digest is None and snapshot.claim_nonce_digest is None
    ledger.set_limit("record-a", "owner", 10)
    assert ledger.claim_action_attempt("owner", "attempt", send_facts(attempt)).won
    assert ledger.key_usage("record-a", "owner").held_cents == 10  # type: ignore[union-attr]
    assert not ledger.claim_action_attempt("owner", "attempt", send_facts(attempt)).won


def test_claim_rechecks_lowered_owner_policy_and_changed_body_facts(tmp_path: Path) -> None:
    ledger = ByotUsageLedger(tmp_path / "usage.sqlite3")
    ledger.set_owner_limit("owner", 100)
    ledger.begin_action(decision())
    attempt = proposal(reserved=10)
    allocated(ledger, attempt)
    with pytest.raises(OperationConflict):
        ledger.claim_action_attempt(
            "owner", "attempt", replace(send_facts(attempt), body_authority_digest="1" * 64),
        )
    ledger.set_owner_limit("owner", 50, expected_revision=1)
    with pytest.raises(OperationConflict, match="owner limit"):
        ledger.claim_action_attempt("owner", "attempt", send_facts(attempt))
    assert ledger.action_attempt("owner", "attempt").operation.state == "allocated"  # type: ignore[union-attr]
    ledger.set_owner_limit("owner", 100, expected_revision=2)
    assert ledger.claim_action_attempt("owner", "attempt", send_facts(attempt)).won


def test_claim_close_race_commits_either_possible_send_or_revocation(tmp_path: Path) -> None:
    path = tmp_path / "usage.sqlite3"
    ledger = ByotUsageLedger(path)
    ledger.begin_action(decision())
    attempt = proposal()
    allocated(ledger, attempt)
    barrier = Barrier(2)

    def claim() -> bool:
        local = ByotUsageLedger(path)
        barrier.wait()
        try:
            return local.claim_action_attempt("owner", "attempt", send_facts(attempt)).won
        except OperationConflict:
            return False

    def close() -> None:
        local = ByotUsageLedger(path)
        barrier.wait()
        local.close_action("owner", "action", expected_epoch=0)

    with ThreadPoolExecutor(max_workers=2) as pool:
        claimed, closing = pool.submit(claim), pool.submit(close)
        won = claimed.result()
        closing.result()
    snapshot = ledger.action_attempt("owner", "attempt")
    assert snapshot is not None
    assert snapshot.operation.state == ("sent" if won else "cancelled")
    assert ledger.owner_usage("owner").held_cents == (30 if won else 0)
    if won:
        assert not ledger.claim_action_attempt("owner", "attempt", send_facts(attempt)).won
    else:
        with pytest.raises(OperationConflict):
            ledger.claim_action_attempt("owner", "attempt", send_facts(attempt))


def test_unknown_survives_restart_and_age_cleanup_without_replay(tmp_path: Path) -> None:
    path = tmp_path / "usage.sqlite3"
    ledger = ByotUsageLedger(path)
    ledger.begin_action(decision())
    attempt = proposal()
    sent(ledger, attempt)
    ledger.mark_action_attempt_unknown("owner", "attempt")
    allocated(ledger, proposal("unclaimed", 20, "record-b"))
    ledger.prepare_operation("legacy", "owner", "legacy", 7, "a" * 64)
    reopened = ByotUsageLedger(path)
    assert reopened.cancel_stale_prepared(owner_user_id="owner", now=datetime(9999, 12, 31, tzinfo=UTC)) == 1
    assert reopened.action_attempt("owner", "unclaimed").operation.state == "allocated"  # type: ignore[union-attr]
    assert reopened.action_attempt("owner", "attempt").operation.state == "unknown"  # type: ignore[union-attr]
    assert not reopened.claim_action_attempt("owner", "attempt", send_facts(attempt)).won
    with pytest.raises(OperationConflict):
        reopened.cancel_action_attempt("owner", "attempt", expected_epoch=0)
    assert reopened.owner_usage("owner").held_cents == 100
    reopened.close_action("owner", "action", expected_epoch=0)
    assert reopened.owner_usage("owner").held_cents == 30
    receipt = reopened.reconcile_action_attempt_usage("owner", "attempt", result(attempt))
    assert receipt.operation.state == "settled"
    assert reopened.reconcile_action_attempt_usage("owner", "attempt", result(attempt)) == receipt


def test_persisted_result_binding_and_outbox_are_idempotent(tmp_path: Path) -> None:
    path = tmp_path / "usage.sqlite3"
    ledger = ByotUsageLedger(path)
    ledger.begin_action(decision())
    attempt = proposal()
    sent(ledger, attempt)
    facts = result(attempt)
    pending = ledger.record_action_attempt_result("owner", "attempt", facts)
    for changed in (replace(facts, cost_micro_usd=90000), replace(facts, evidence_sha256="3" * 64),
                    replace(facts, request_digest="4" * 64), replace(facts, result_text="different")):
        with pytest.raises(SettlementEvidenceError):
            ledger.record_action_attempt_result("owner", "attempt", changed)
    assert ledger.action_attempt("owner", "attempt") == pending
    receipt = ledger.settle_action_attempt("owner", "attempt")
    assert ledger.settle_action_attempt("owner", "attempt") == receipt
    assert ledger.record_action_attempt_result("owner", "attempt", facts) == receipt
    assert ledger.owner_usage("owner").used_cents == 10
    events = ledger.pending_projection_events()
    assert len(events) == 1
    event = events[0]
    assert event.digest == hashlib.sha256(event.canonical_payload().encode()).hexdigest()
    assert (event.actual_cents, event.cost_micro_usd, event.event_kind) == (10, 100000, "settled")
    with pytest.raises(SettlementEvidenceError):
        ledger.acknowledge_projection(event.sequence, "5" * 64)
    assert ledger.pending_projection_events() == events
    ledger.acknowledge_projection(event.sequence, event.digest)
    ByotUsageLedger(path).acknowledge_projection(event.sequence, event.digest)
    assert ledger.pending_projection_events() == ()
    assert ledger.owner_usage("owner").used_cents == 10


def test_one_provider_event_cannot_charge_two_attempts(tmp_path: Path) -> None:
    ledger = ByotUsageLedger(tmp_path / "usage.sqlite3")
    ledger.begin_action(decision())
    first, second = proposal("first"), proposal("second")
    settled(ledger, first)
    sent(ledger, second)
    with pytest.raises(SettlementEvidenceError, match="already recorded"):
        ledger.record_action_attempt_result(
            "owner", "second", replace(result(second), provider_attempt_event_id="event-first"),
        )
    assert ledger.owner_usage("owner").used_cents == 10
    assert ledger.action_attempt("owner", "second").operation.state == "sent"  # type: ignore[union-attr]
    assert len(ledger.pending_projection_events()) == 1


def test_simultaneous_settlement_commits_one_charge_and_event(tmp_path: Path) -> None:
    path = tmp_path / "usage.sqlite3"
    ledger = ByotUsageLedger(path)
    ledger.begin_action(decision())
    attempt = proposal()
    sent(ledger, attempt)
    ledger.record_action_attempt_result("owner", "attempt", result(attempt))
    barrier = Barrier(2)

    def settle(_: int) -> str:
        local = ByotUsageLedger(path)
        barrier.wait()
        return local.settle_action_attempt("owner", "attempt").operation.state

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert list(pool.map(settle, range(2))) == ["settled", "settled"]
    assert ledger.owner_usage("owner").used_cents == 10
    assert len(ledger.pending_projection_events()) == 1


def test_missing_usage_record_cannot_create_phantom_settled_charge(tmp_path: Path) -> None:
    path = tmp_path / "usage.sqlite3"
    ledger = ByotUsageLedger(path)
    ledger.begin_action(decision())
    attempt = proposal()
    sent(ledger, attempt)
    ledger.record_action_attempt_result("owner", "attempt", result(attempt))
    with sqlite3.connect(path) as con:
        con.execute("DELETE FROM byot_key_usage WHERE api_key_id='record-a' AND owner_user_id='owner'")
    with pytest.raises(SettlementEvidenceError, match="usage record"):
        ledger.settle_action_attempt("owner", "attempt")
    assert ledger.action_attempt("owner", "attempt").operation.state == "settlement_pending"  # type: ignore[union-attr]
    assert ledger.pending_projection_events() == ()


@pytest.mark.parametrize("timing", ["BEFORE", "AFTER"])
def test_fault_after_usage_or_outbox_rolls_back_all_accounting(tmp_path: Path, timing: str) -> None:
    path = tmp_path / "usage.sqlite3"
    ledger = ByotUsageLedger(path)
    ledger.begin_action(decision())
    attempt = proposal()
    sent(ledger, attempt)
    ledger.record_action_attempt_result("owner", "attempt", result(attempt))
    pending = ledger.action_attempt("owner", "attempt")
    with sqlite3.connect(path) as con:
        con.execute(f"CREATE TRIGGER fault {timing} INSERT ON byot_action_outbox BEGIN SELECT RAISE(ABORT,'injected'); END")
    with pytest.raises(sqlite3.IntegrityError, match="injected"):
        ledger.settle_action_attempt("owner", "attempt")
    assert ledger.action_attempt("owner", "attempt") == pending
    assert ledger.owner_usage("owner").used_cents == 0
    assert ledger.pending_projection_events() == ()
    with sqlite3.connect(path) as con:
        con.execute("DROP TRIGGER fault")
    ledger.settle_action_attempt("owner", "attempt")
    assert ledger.owner_usage("owner").used_cents == 10
    assert len(ledger.pending_projection_events()) == 1


def test_overrun_accounts_actual_liability_and_quarantines_without_clamping(tmp_path: Path) -> None:
    ledger = ByotUsageLedger(tmp_path / "usage.sqlite3")
    ledger.begin_action(decision())
    attempt = proposal(reserved=5)
    sent(ledger, attempt)
    allocated(ledger, proposal("unclaimed", 40, "record-b"))
    ledger.record_action_attempt_result("owner", "attempt", result(attempt, 120))
    snapshot = ledger.action("owner", "action")
    assert snapshot is not None and snapshot.quarantined and snapshot.state == "quarantined"
    assert snapshot.reserved_cents == 120
    assert ledger.action_attempt("owner", "unclaimed").operation.state == "cancelled"  # type: ignore[union-attr]
    with pytest.raises(OperationConflict):
        allocated(ledger, proposal("after", epoch=snapshot.epoch))
    with pytest.raises(OperationConflict):
        ledger.begin_action(decision("new-action"))
    ledger.settle_action_attempt("owner", "attempt")
    assert ledger.owner_usage("owner").used_cents == 120
    assert ledger.pending_projection_events()[0].actual_cents == 120
    ledger.close_action("owner", "action", expected_epoch=snapshot.epoch)
    assert ledger.owner_usage("owner").held_cents == 0
    assert ledger.action("owner", "action").quarantined  # type: ignore[union-attr]


def test_legacy_limits_and_action_holds_share_one_accounting_transaction(tmp_path: Path) -> None:
    ledger = ByotUsageLedger(tmp_path / "usage.sqlite3")
    ledger.set_limit("record-a", "owner", 35)
    ledger.set_owner_limit("owner", 110)
    ledger.begin_action(decision())
    allocated(ledger, proposal())
    with pytest.raises(OperationConflict):
        ledger.prepare_operation("record-a", "owner", "too-much-record", 6, "a" * 64)
    with pytest.raises(OperationConflict):
        ledger.prepare_operation("record-b", "owner", "too-much-owner", 11, "a" * 64)
    ledger.prepare_operation("record-a", "owner", "legacy", 5, "a" * 64)
    assert ledger.owner_usage("owner").held_cents == 105
    assert ledger.key_usage("record-a", "owner").held_cents == 35  # type: ignore[union-attr]
    ledger.mark_operation_sent("owner", "legacy")
    ledger.record_operation_result("owner", "legacy", actual_cents=2, evidence_sha256="b" * 64,
                                   provider_id="provider", model_id="model", dispatch_event_id="event")
    ledger.settle_operation("owner", "legacy", 2, "b" * 64)
    ledger.record_settlement("unbound", "owner", 3, "c" * 64)
    assert (ledger.owner_usage("owner").used_cents, ledger.owner_usage("owner").held_cents) == (5, 100)
    assert ledger.pending_projection_events() == ()


def test_legacy_mutators_refuse_action_linked_operation_in_all_states(tmp_path: Path) -> None:
    ledger = ByotUsageLedger(tmp_path / "usage.sqlite3")
    ledger.begin_action(decision())
    attempt = proposal()
    allocated(ledger, attempt)
    with pytest.raises(OperationConflict):
        ledger.prepare_operation("record-a", "owner", "attempt", 30, "c" * 64)
    for mutate in (ledger.mark_operation_sent, ledger.cancel_prepared_operation, ledger.reconcile_operation):
        with pytest.raises(OperationConflict):
            mutate("owner", "attempt")
    assert ledger.operation("owner", "attempt").action_id == "action"  # type: ignore[union-attr]
    ledger.claim_action_attempt("owner", "attempt", send_facts(attempt))
    with pytest.raises(OperationConflict):
        ledger.mark_operation_unknown("owner", "attempt")
    with pytest.raises(OperationConflict):
        ledger.record_operation_result("owner", "attempt", actual_cents=10,
                                       evidence_sha256="2" * 64, dispatch_event_id="event",
                                       provider_id="provider", model_id="model")
    ledger.record_action_attempt_result("owner", "attempt", result(attempt))
    with pytest.raises(OperationConflict):
        ledger.settle_operation("owner", "attempt", 10, "2" * 64)
    assert ledger.owner_usage("owner").used_cents == 0


@pytest.mark.parametrize("micro_usd,cents", [(0, 0), (1, 1), (9999, 1), (10000, 1), (10001, 2)])
def test_per_attempt_rounding_is_not_a_parent_charge(tmp_path: Path, micro_usd: int, cents: int) -> None:
    ledger = ByotUsageLedger(tmp_path / "usage.sqlite3")
    ledger.begin_action(decision())
    attempt = proposal()
    sent(ledger, attempt)
    ledger.record_action_attempt_result("owner", "attempt", result(attempt, micro_usd=micro_usd))
    ledger.settle_action_attempt("owner", "attempt")
    assert ledger.owner_usage("owner").used_cents == cents
    assert ledger.pending_projection_events()[0].actual_cents == cents


@pytest.mark.parametrize("value", [True, False, -1, 1.5, MAX_MONEY + 1])
def test_strict_money_and_epoch_validation(tmp_path: Path, value: int) -> None:
    ledger = ByotUsageLedger(tmp_path / "usage.sqlite3")
    with pytest.raises(ValueError):
        replace(decision(), budget_cents=value)
    with pytest.raises(ValueError):
        replace(proposal(), reserved_cents=value)
    with pytest.raises(ValueError):
        replace(proposal(), action_epoch=value)
    with pytest.raises(ValueError):
        replace(result(proposal()), cost_micro_usd=value)
    with pytest.raises(ValueError):
        ledger.set_owner_limit("owner", value)
    with pytest.raises(ValueError):
        ledger.prepare_operation("record", "owner", "legacy", value, "a" * 64)


def test_overflow_refuses_before_usage_or_admission_write(tmp_path: Path) -> None:
    ledger = ByotUsageLedger(tmp_path / "usage.sqlite3")
    ledger.record_settlement("record", "owner", MAX_MONEY, "a" * 64)
    with pytest.raises(ValueError):
        ledger.record_settlement("record", "owner", 1, "a" * 64)
    with pytest.raises(ValueError):
        ledger.begin_action(decision(budget=1))
    with pytest.raises(ValueError):
        ledger.prepare_operation("other", "owner", "overflow", 1, "a" * 64)
    assert ledger.key_usage("record", "owner").used_cents == MAX_MONEY  # type: ignore[union-attr]
    assert ledger.action("owner", "action") is None
    assert ledger.operation("owner", "overflow") is None


def test_policy_revision_and_outbox_bounds(tmp_path: Path) -> None:
    ledger = ByotUsageLedger(tmp_path / "usage.sqlite3")
    assert ledger.set_owner_limit("owner", 100).revision == 1
    with pytest.raises(OperationConflict):
        ledger.set_owner_limit("owner", 200)
    assert ledger.set_owner_limit("owner", None, expected_revision=1).revision == 2
    ledger.begin_action(decision())
    settled(ledger, proposal("first"))
    settled(ledger, proposal("second", record="record-b"))
    events = ledger.pending_projection_events(limit=1)
    assert len(events) == 1
    assert len(ledger.pending_projection_events(after_sequence=events[0].sequence)) == 1
    for invalid in (0, True, 1001):
        with pytest.raises(ValueError):
            ledger.pending_projection_events(limit=invalid)
    with pytest.raises(OperationConflict):
        ledger.acknowledge_projection(999, "a" * 64)
