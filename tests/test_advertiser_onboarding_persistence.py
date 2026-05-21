"""Advertiser onboarding persistence tests (Sprint 23-24 phase 5)."""

from __future__ import annotations

import os
import tempfile

import pytest

from runtime.db_lock import connect_write
from substrate.ad_inventory.advertiser_onboarding import (
    AdvertiserRegistry,
    AdvertiserStatus,
    activate_advertiser,
    approve_advertiser,
    ensure_table,
    load_registry,
    reject_advertiser,
    save_record,
    submit_application,
    suspend_advertiser,
)
from substrate.graph.schema import init_database


@pytest.fixture
def db():
    tmpdir = tempfile.mkdtemp(prefix="antiek-adv-persistence-test-")
    db_path = os.path.join(tmpdir, "test.duckdb")
    con = connect_write(db_path, purpose="advertiser_persistence_test")
    init_database(con)
    yield con
    con.close()


def test_ensure_table_idempotent(db):
    ensure_table(db)
    ensure_table(db)
    rows = db.execute("SELECT count(*) FROM advertisers").fetchone()
    assert rows[0] == 0


def test_submit_through_active_round_trips(db):
    mem = AdvertiserRegistry()
    rec = submit_application(
        mem,
        display_name="Acme Recruiting",
        contact_email="ops@acme.example",
        verticals=("recruiting", "saas"),
        audience_intents=("hiring_manager",),
        monthly_budget_usd_cents=500_00,
        advertiser_id="adv-acme",
    )
    save_record(db, rec)
    approved = approve_advertiser(
        mem, advertiser_id="adv-acme", operator_notes="vetted",
    )
    save_record(db, approved)
    active = activate_advertiser(
        mem, advertiser_id="adv-acme", legal_gate_passed=True,
    )
    save_record(db, active)

    loaded = load_registry(db)
    states = [
        r.status for r in loaded.records if r.advertiser_id == "adv-acme"
    ]
    assert states == [
        AdvertiserStatus.PENDING_REVIEW,
        AdvertiserStatus.APPROVED,
        AdvertiserStatus.ACTIVE,
    ]
    latest = loaded.latest("adv-acme")
    assert latest is not None
    assert latest.status is AdvertiserStatus.ACTIVE
    assert latest.verticals == ("recruiting", "saas")
    assert latest.audience_intents == ("hiring_manager",)
    assert latest.monthly_budget_usd_cents == 500_00
    assert "vetted" in latest.operator_notes


def test_reject_and_rejection_reason_preserved(db):
    mem = AdvertiserRegistry()
    rec = submit_application(
        mem, display_name="X", contact_email="x@y", verticals=(),
        advertiser_id="adv-x",
    )
    save_record(db, rec)
    rejected = reject_advertiser(
        mem, advertiser_id="adv-x", rejection_reason="off-brand",
    )
    save_record(db, rejected)

    loaded = load_registry(db)
    latest = loaded.latest("adv-x")
    assert latest.status is AdvertiserStatus.REJECTED
    assert latest.rejection_reason == "off-brand"


def test_suspend_notes_concatenation_persists(db):
    mem = AdvertiserRegistry()
    rec = submit_application(
        mem, display_name="X", contact_email="x@y", verticals=(),
        advertiser_id="adv-x",
    )
    save_record(db, rec)
    approved = approve_advertiser(mem, advertiser_id="adv-x")
    save_record(db, approved)
    active = activate_advertiser(
        mem, advertiser_id="adv-x", legal_gate_passed=True,
    )
    save_record(db, active)
    suspended = suspend_advertiser(
        mem, advertiser_id="adv-x", reason="brand-safety review",
    )
    save_record(db, suspended)

    loaded = load_registry(db)
    latest = loaded.latest("adv-x")
    assert latest.status is AdvertiserStatus.SUSPENDED
    assert "brand-safety review" in latest.operator_notes


def test_save_record_idempotent(db):
    mem = AdvertiserRegistry()
    rec = submit_application(
        mem, display_name="X", contact_email="x@y", verticals=(),
        advertiser_id="adv-x",
    )
    a = save_record(db, rec)
    b = save_record(db, rec)
    assert a == b
    cnt = db.execute(
        "SELECT count(*) FROM advertisers WHERE advertiser_id = ?",
        ["adv-x"],
    ).fetchone()[0]
    assert cnt == 1


def test_all_serving_round_trips_through_persistence(db):
    mem = AdvertiserRegistry()
    for aid in ("adv-a", "adv-b"):
        rec = submit_application(
            mem, display_name=aid, contact_email=f"{aid}@x", verticals=(),
            advertiser_id=aid,
        )
        save_record(db, rec)
        approved = approve_advertiser(mem, advertiser_id=aid)
        save_record(db, approved)
        active = activate_advertiser(
            mem, advertiser_id=aid, legal_gate_passed=True,
        )
        save_record(db, active)

    # A pending one that is never activated.
    rec = submit_application(
        mem, display_name="adv-p", contact_email="p@x", verticals=(),
        advertiser_id="adv-p",
    )
    save_record(db, rec)

    loaded = load_registry(db)
    serving = [r.advertiser_id for r in loaded.all_serving()]
    assert serving == ["adv-a", "adv-b"]


def test_check_constraint_rejects_unknown_status(db):
    ensure_table(db)
    with pytest.raises(Exception):
        db.execute(
            """
            INSERT INTO advertisers (
                attempt_id, advertiser_id, display_name, contact_email,
                status, submitted_at, last_status_change_at
            ) VALUES (
                'bogus', 'adv-x', 'X', 'x@y',
                'not_a_real_status', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
            )
            """
        )
