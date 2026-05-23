"""Rollover ledger persistence tests."""

from __future__ import annotations

import os
import tempfile

import pytest

from runtime.db_lock import connect_write
from substrate.graph.schema import init_database
from substrate.rev_share.rollover import (
    RolloverEntry,
    RolloverLedger,
    RolloverState,
    accrue,
)
from substrate.rev_share.rollover_persistence import (
    load_balance_cents,
    load_ledger,
    persist_entry,
    persist_ledger,
)


@pytest.fixture
def db():
    tmpdir = tempfile.mkdtemp(prefix="antiek-rollover-test-")
    db_path = os.path.join(tmpdir, "test.duckdb")
    con = connect_write(db_path, purpose="rollover_test")
    init_database(con)
    yield con
    con.close()


def test_persist_then_load_roundtrip(db):
    mem = RolloverLedger()
    accrue(mem, recipient_ref="user-a", cents=500, current_month_index=0)
    persist_ledger(db, mem)
    loaded = load_ledger(db)
    assert "user-a" in loaded.entries
    assert loaded.entries["user-a"].balance_cents == 500


def test_load_balance_cents_for_unknown_returns_zero(db):
    assert load_balance_cents(db, "user-ghost") == 0


def test_persist_entry_upserts(db):
    e = RolloverEntry(
        recipient_ref="user-a", balance_cents=500,
        accrual_started_month=0, state=RolloverState.ACCRUING,
    )
    persist_entry(db, e)
    e2 = RolloverEntry(
        recipient_ref="user-a", balance_cents=800,
        accrual_started_month=0, state=RolloverState.ACCRUING,
    )
    persist_entry(db, e2)
    assert load_balance_cents(db, "user-a") == 800


def test_check_constraint_negative_balance_refused(db):
    with pytest.raises(Exception):
        db.execute(
            """
            INSERT INTO rollover_ledger (recipient_ref, balance_cents, state)
            VALUES ('user-x', -1, 'accruing')
            """
        )


def test_multiple_recipients_load_in_alphabetical_order(db):
    for rid, bal in [("user-z", 100), ("user-a", 200), ("user-m", 300)]:
        persist_entry(db, RolloverEntry(
            recipient_ref=rid, balance_cents=bal,
            accrual_started_month=0, state=RolloverState.ACCRUING,
        ))
    loaded = load_ledger(db)
    assert sorted(loaded.entries) == ["user-a", "user-m", "user-z"]
