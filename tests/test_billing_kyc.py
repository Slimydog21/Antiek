"""KYC state machine tests (Sprint 23-24 phase 4 — §9.5)."""

from __future__ import annotations

import os
import tempfile

import pytest

from runtime.db_lock import connect_write
from substrate.billing.kyc import (
    KYC_PAYOUT_FLOOR_USD_CENTS,
    KycError,
    KycRegistry,
    KycState,
    begin,
    can_settle,
    complete,
    ensure_table,
    expire,
    invite,
    load_registry,
    reject,
    save_record,
)
from substrate.graph.schema import init_database


@pytest.fixture
def db():
    tmpdir = tempfile.mkdtemp(prefix="antiek-kyc-test-")
    db_path = os.path.join(tmpdir, "test.duckdb")
    con = connect_write(db_path, purpose="kyc_test")
    init_database(con)
    yield con
    con.close()


# ── State machine ──────────────────────────────────────────────────


def test_invite_lands_in_invited_state():
    reg = KycRegistry()
    r = invite(reg, recipient_ref="user-1")
    assert r.state is KycState.INVITED


def test_begin_then_complete_round_trip():
    reg = KycRegistry()
    invite(reg, recipient_ref="user-1")
    begin(reg, recipient_ref="user-1")
    r = complete(
        reg, recipient_ref="user-1", stripe_account_ref="acct_test",
    )
    assert r.state is KycState.COMPLETED
    assert r.stripe_account_ref == "acct_test"


def test_begin_requires_invited():
    reg = KycRegistry()
    # Nothing invited yet.
    with pytest.raises(KycError):
        begin(reg, recipient_ref="user-1")


def test_complete_requires_in_progress():
    reg = KycRegistry()
    invite(reg, recipient_ref="user-1")
    # Skipped IN_PROGRESS → refused.
    with pytest.raises(KycError):
        complete(reg, recipient_ref="user-1")


def test_expire_requires_completed():
    reg = KycRegistry()
    invite(reg, recipient_ref="user-1")
    with pytest.raises(KycError):
        expire(reg, recipient_ref="user-1")


def test_full_cycle_invited_progress_completed_expired_reinvited():
    reg = KycRegistry()
    invite(reg, recipient_ref="user-1")
    begin(reg, recipient_ref="user-1")
    complete(reg, recipient_ref="user-1")
    expire(reg, recipient_ref="user-1")
    # Re-invite from EXPIRED is permitted.
    r = invite(reg, recipient_ref="user-1")
    assert r.state is KycState.INVITED


def test_reject_terminal():
    reg = KycRegistry()
    invite(reg, recipient_ref="user-1")
    reject(reg, recipient_ref="user-1", rejection_reason="sanctions match")
    # Cannot re-reject.
    with pytest.raises(KycError, match="already REJECTED"):
        reject(
            reg, recipient_ref="user-1",
            rejection_reason="another reason",
        )


def test_invite_refused_when_completed():
    reg = KycRegistry()
    invite(reg, recipient_ref="user-1")
    begin(reg, recipient_ref="user-1")
    complete(reg, recipient_ref="user-1")
    with pytest.raises(KycError):
        invite(reg, recipient_ref="user-1")


# ── Settlement gate ────────────────────────────────────────────────


def test_can_settle_below_floor_always_true():
    reg = KycRegistry()
    # No KYC at all, but below-floor amount → True.
    assert can_settle(
        reg, recipient_ref="user-x",
        amount_usd_cents=KYC_PAYOUT_FLOOR_USD_CENTS,
    ) is True
    assert can_settle(
        reg, recipient_ref="user-x", amount_usd_cents=500,
    ) is True


def test_can_settle_above_floor_requires_completed():
    reg = KycRegistry()
    # Not started → above-floor refused.
    assert can_settle(
        reg, recipient_ref="user-x", amount_usd_cents=2000,
    ) is False
    invite(reg, recipient_ref="user-x")
    assert can_settle(
        reg, recipient_ref="user-x", amount_usd_cents=2000,
    ) is False
    begin(reg, recipient_ref="user-x")
    assert can_settle(
        reg, recipient_ref="user-x", amount_usd_cents=2000,
    ) is False
    complete(reg, recipient_ref="user-x")
    # NOW above-floor allowed.
    assert can_settle(
        reg, recipient_ref="user-x", amount_usd_cents=2000,
    ) is True


def test_expired_blocks_settlement():
    reg = KycRegistry()
    invite(reg, recipient_ref="user-x")
    begin(reg, recipient_ref="user-x")
    complete(reg, recipient_ref="user-x")
    expire(reg, recipient_ref="user-x")
    assert can_settle(
        reg, recipient_ref="user-x", amount_usd_cents=2000,
    ) is False


def test_rejected_blocks_settlement_even_above_floor():
    reg = KycRegistry()
    invite(reg, recipient_ref="user-x")
    reject(reg, recipient_ref="user-x", rejection_reason="x")
    assert can_settle(
        reg, recipient_ref="user-x", amount_usd_cents=2000,
    ) is False


# ── Persistence ────────────────────────────────────────────────────


def test_persistence_roundtrips_state_machine(db):
    mem = KycRegistry()
    invite(mem, recipient_ref="user-1")
    save_record(db, mem.records[-1])
    begin(mem, recipient_ref="user-1")
    save_record(db, mem.records[-1])
    complete(
        mem, recipient_ref="user-1", stripe_account_ref="acct_test",
    )
    save_record(db, mem.records[-1])

    loaded = load_registry(db)
    states = [r.state for r in loaded.records]
    assert states == [
        KycState.INVITED,
        KycState.IN_PROGRESS,
        KycState.COMPLETED,
    ]
    assert loaded.latest("user-1").stripe_account_ref == "acct_test"


def test_save_record_idempotent(db):
    mem = KycRegistry()
    rec = invite(mem, recipient_ref="user-1")
    a = save_record(db, rec)
    b = save_record(db, rec)
    assert a == b
    rows = db.execute(
        "SELECT count(*) FROM kyc_status WHERE recipient_ref = ?",
        ["user-1"],
    ).fetchone()
    assert rows[0] == 1


def test_check_constraint_rejects_unknown_state(db):
    ensure_table(db)
    with pytest.raises(Exception):
        db.execute(
            """
            INSERT INTO kyc_status (
                attempt_id, recipient_ref, state, last_state_change_at
            ) VALUES ('bad', 'user-1', 'not_a_state', CURRENT_TIMESTAMP)
            """
        )
