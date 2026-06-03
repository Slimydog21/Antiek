"""IP holder escrow tests (Sprint 18, master-spec §9.10)."""

from __future__ import annotations

import os
import tempfile
from decimal import Decimal

import pytest

from runtime.db_lock import connect_write
from substrate.graph.schema import init_database
from substrate.ip_holders import (
    FIRST_COHORT_PUBLISHERS,
    VALID_STATUSES,
    accrue_escrow,
    claim,
    create_pre_onboarded,
    get,
    list_all,
    mark_invited,
    opt_out,
    render_notification_email,
)


@pytest.fixture
def db():
    """Initialized DuckDB at a tempfile with the Sprint 18 schema."""
    tmpdir = tempfile.mkdtemp(prefix="antiek-ip-holders-test-")
    db_path = os.path.join(tmpdir, "test.duckdb")
    con = connect_write(db_path, purpose="ip_holders_test")
    init_database(con)
    yield con
    con.close()


# ── Schema + state-machine tests ─────────────────────────────────────


def test_first_cohort_publishers_match_master_spec():
    """§9.10 first-cohort outreach: MIT Press, Cambridge UP, Princeton UP."""
    assert FIRST_COHORT_PUBLISHERS == (
        "MIT Press",
        "Cambridge University Press",
        "Princeton University Press",
    )


def test_valid_statuses_match_schema_check_constraint():
    """The Python-side VALID_STATUSES must match the SQL CHECK constraint
    in substrate/graph/schema.py. Drift here = silent invariant break."""
    assert frozenset({
        "pre_onboarded", "invited", "claimed", "opted_out",
    }) == VALID_STATUSES


def test_create_pre_onboarded_starts_at_pre_onboarded(db):
    holder_id = create_pre_onboarded(
        db, display_name="MIT Press",
        legal_contact_email="legal@mitpress.mit.edu",
    )
    h = get(db, holder_id)
    assert h is not None
    assert h.display_name == "MIT Press"
    assert h.status == "pre_onboarded"
    assert h.escrow_balance_usd == Decimal("0")
    assert h.notification_sent_at is None
    assert h.claimed_at is None


def test_accrue_escrow_increments(db):
    holder_id = create_pre_onboarded(db, display_name="Test Publisher")
    accrue_escrow(db, holder_id, Decimal("12.50"))
    accrue_escrow(db, holder_id, Decimal("3.25"))
    h = get(db, holder_id)
    assert h is not None
    assert h.escrow_balance_usd == Decimal("15.75")


def test_accrue_escrow_rejects_non_positive(db):
    holder_id = create_pre_onboarded(db, display_name="X")
    with pytest.raises(ValueError):
        accrue_escrow(db, holder_id, Decimal("0"))
    with pytest.raises(ValueError):
        accrue_escrow(db, holder_id, Decimal("-1.00"))


def test_state_machine_pre_onboarded_to_invited_to_claimed(db):
    holder_id = create_pre_onboarded(db, display_name="Cambridge UP")
    mark_invited(db, holder_id)
    h = get(db, holder_id)
    assert h is not None and h.status == "invited"
    assert h.notification_sent_at is not None

    claim(db, holder_id, stripe_connect_account_id="acct_1ABC")
    h = get(db, holder_id)
    assert h is not None and h.status == "claimed"
    assert h.escrow_account_ref == "acct_1ABC"
    assert h.claimed_at is not None


def test_claim_only_works_from_invited(db):
    """Per master-spec §9.10: payouts gate strictly on publisher
    opt-in. The substrate's claim() should reject claiming a holder
    that hasn't been invited yet (no notification = no opt-in
    pathway)."""
    holder_id = create_pre_onboarded(db, display_name="Princeton UP")
    # Skip mark_invited — try to claim directly
    claim(db, holder_id, stripe_connect_account_id="acct_X")
    h = get(db, holder_id)
    assert h is not None
    # Status should remain pre_onboarded because the UPDATE WHERE
    # status='invited' didn't match. The state machine enforces the
    # ordering; the SQL UPDATE is a no-op rather than an error.
    assert h.status == "pre_onboarded"


def test_opt_out_works_from_any_status(db):
    holder_id = create_pre_onboarded(db, display_name="Test")
    opt_out(db, holder_id)
    h = get(db, holder_id)
    assert h is not None
    assert h.status == "opted_out"
    assert h.opted_out_at is not None


def test_list_filtered_by_status(db):
    create_pre_onboarded(db, display_name="A")  # pre_onboarded
    holder_b = create_pre_onboarded(db, display_name="B")
    mark_invited(db, holder_b)
    holder_c = create_pre_onboarded(db, display_name="C")
    mark_invited(db, holder_c)
    claim(db, holder_c, stripe_connect_account_id="acct_C")

    pre = list_all(db, status="pre_onboarded")
    invited = list_all(db, status="invited")
    claimed = list_all(db, status="claimed")

    assert {h.display_name for h in pre} == {"A"}
    assert {h.display_name for h in invited} == {"B"}
    assert {h.display_name for h in claimed} == {"C"}


def test_list_invalid_status_raises(db):
    with pytest.raises(ValueError):
        list_all(db, status="garbage")


# ── Notification template tests ──────────────────────────────────────


def test_notification_email_template_renders_for_pre_onboarded(db):
    holder_id = create_pre_onboarded(
        db, display_name="MIT Press",
        legal_contact_email="legal@mitpress.mit.edu",
    )
    accrue_escrow(db, holder_id, Decimal("42.50"))
    h = get(db, holder_id)
    assert h is not None
    email = render_notification_email(h)
    assert "MIT Press" in email
    assert "42.50" in email
    # Per §9.10 binding framing: email must NOT claim infringement;
    # it must frame the platform as fair-use operator voluntarily
    # sharing revenue. Normalize whitespace before substring match
    # because the template wraps the phrase across lines.
    normalized = " ".join(email.split())
    assert "transformative under fair use" in normalized
    # Must NOT include words that frame the platform as an infringer.
    assert "infringement" not in email.lower()
    assert "stole" not in email.lower()
    # Must surface the opt-out mechanism.
    assert "opt out" in email.lower()
