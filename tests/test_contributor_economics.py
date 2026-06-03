"""Speak SPR-06 — informant-as-contributor economics tests.

Rigor #3 payout edge cases: zero revenue, an unmapped interviewee
(holding bucket), a slop contribution (no earn), and the mandatory
mechanical gates — slop-doesn't-earn and gate-blocks-disbursement —
plus reconciliation (no double-count). Accrue now, disburse never
(pre-gate).
"""

from __future__ import annotations

import os
import tempfile
from decimal import Decimal

import pytest

from runtime.db_lock import connect_write
from substrate import ip_holders
from substrate.graph.schema import init_database
from substrate.speak import contributor, project, publish_gate
from substrate.speak.contributor import DisbursementBlocked
from substrate.speak.schema import ensure_speak_schema
from substrate.speak.third_party import record_claim


@pytest.fixture
def db(monkeypatch):
    tmpdir = tempfile.mkdtemp(prefix="speak-econ-test-")
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", os.path.join(tmpdir, "events"))
    monkeypatch.delenv("ANTIEK_STRIPE_PROVIDER", raising=False)  # default mock → blocked
    db_path = os.path.join(tmpdir, "t.duckdb")
    with connect_write(db_path, purpose="setup") as con:
        init_database(con)
        ensure_speak_schema(con)
    return db_path


def _con(db):
    return connect_write(db, purpose="econ_test")


def _publishable_claim(con, project_id, text, interview_id):
    c = record_claim(con, project_id=project_id, text=text, interview_id=interview_id,
                    about_subject=True, subject_ref="the-dad")
    publish_gate.operator_attest_claim(con, c.claim_id, project_id=project_id)
    return c


# ── M1 informant → payee mapping ────────────────────────────────────────


def test_map_contributor_creates_payee(db):
    with _con(db) as con:
        p = project.create_project(con, title="Dad's biography")
        m = contributor.map_contributor(con, interview_id="iv-a", project_id=p.project_id,
                                        display_name="Uncle Fawzi")
        assert m.ip_holder_id is not None
        assert m.holding_bucket is False
        # The payee exists in ip_holders escrow.
        assert ip_holders.get(con, m.ip_holder_id) is not None


def test_unmapped_interviewee_goes_to_holding_bucket(db):
    with _con(db) as con:
        p = project.create_project(con, title="Dad's biography")
        m = contributor.map_contributor(con, interview_id="iv-x", project_id=p.project_id)
        assert m.holding_bucket is True
        assert m.ip_holder_id is None


# ── M2 contribution measurement ─────────────────────────────────────────


def test_contribution_shares_sum_to_one(db):
    with _con(db) as con:
        p = project.create_project(con, title="Dad's biography")
        _publishable_claim(con, p.project_id, "He founded the school.", "iv-a")
        _publishable_claim(con, p.project_id, "He ran the bakery.", "iv-a")
        _publishable_claim(con, p.project_id, "He loved jazz.", "iv-b")
        result = contributor.measure_contribution(con, project_id=p.project_id)
        assert set(result.shares) == {"iv-a", "iv-b"}
        assert abs(sum(result.shares.values()) - 1.0) < 1e-9
        assert result.algorithm == "claim_confidence_times_source_tier"


# ── M3 slop gate ────────────────────────────────────────────────────────


def test_slop_contribution_earns_nothing(db):
    with _con(db) as con:
        p = project.create_project(con, title="Dad's biography")
        _publishable_claim(con, p.project_id, "A substantive, cited fact.", "iv-good")
        _publishable_claim(con, p.project_id, "Filler slop.", "iv-slop")
        result = contributor.measure_contribution(
            con, project_id=p.project_id,
            quality_scores={"iv-good": 0.9, "iv-slop": 0.1}, slop_threshold=0.4,
        )
        assert "iv-slop" in result.slop_gated
        assert "iv-slop" not in result.shares
        assert result.shares["iv-good"] == pytest.approx(1.0)


# ── M4 accrual to escrow (zero-buyer safe) ──────────────────────────────


def test_accrual_routes_pool_to_escrow(db):
    with _con(db) as con:
        p = project.create_project(con, title="Dad's biography")
        m_a = contributor.map_contributor(con, interview_id="iv-a", project_id=p.project_id, display_name="A")
        contributor.map_contributor(con, interview_id="iv-b", project_id=p.project_id, display_name="B")
        _publishable_claim(con, p.project_id, "Fact one about him.", "iv-a")
        _publishable_claim(con, p.project_id, "Fact two about him.", "iv-b")
        lines = contributor.accrue_contributions(con, project_id=p.project_id,
                                                 ad_revenue_usd=Decimal("100"))
        # 70% slice of $100 = $70 split across contributors → total accrued ≈ $70.
        total = contributor.accrued_total(con, p.project_id)
        assert abs(total - Decimal("70")) < Decimal("0.01")
        # Escrow of payee A increased.
        a_escrow = ip_holders.get(con, m_a.ip_holder_id).escrow_balance_usd
        assert a_escrow > 0


def test_zero_buyers_tracks_share_but_zero_dollars(db):
    with _con(db) as con:
        p = project.create_project(con, title="Dad's biography")
        contributor.map_contributor(con, interview_id="iv-a", project_id=p.project_id, display_name="A")
        _publishable_claim(con, p.project_id, "A fact about him.", "iv-a")
        lines = contributor.accrue_contributions(con, project_id=p.project_id,
                                                 ad_revenue_usd=Decimal("0"))
        assert lines[0].share_fraction > 0      # share tracked
        assert lines[0].amount_usd == Decimal("0")  # but $0 — no fictional balance
        assert contributor.accrued_total(con, p.project_id) == Decimal("0")


def test_accrual_reconciles_no_double_count(db):
    with _con(db) as con:
        p = project.create_project(con, title="Dad's biography")
        contributor.map_contributor(con, interview_id="iv-a", project_id=p.project_id, display_name="A")
        _publishable_claim(con, p.project_id, "A fact.", "iv-a")
        contributor.accrue_contributions(con, project_id=p.project_id, ad_revenue_usd=Decimal("50"))
        n = con.execute("SELECT count(*) FROM speak_accruals WHERE project_id = ? AND slop_gated = FALSE",
                        [p.project_id]).fetchone()[0]
        assert n == 1  # one earning line, no double-count


# ── M5 disbursement gate (no pre-gate payout) ───────────────────────────


def test_disbursement_blocked_pre_gate(db, monkeypatch):
    monkeypatch.delenv("ANTIEK_STRIPE_PROVIDER", raising=False)  # mock
    with _con(db) as con:
        p = project.create_project(con, title="Dad's biography")
        contributor.map_contributor(con, interview_id="iv-a", project_id=p.project_id, display_name="A")
        with pytest.raises(DisbursementBlocked):
            contributor.attempt_disbursement(con, project_id=p.project_id, interview_id="iv-a")


def test_no_pre_gate_payout_path_even_when_provider_real(db, monkeypatch):
    # Even with the provider flipped, Speak adds no parallel payout path —
    # it routes through the gated Stripe Connect seam (NotImplementedError),
    # never a bespoke pre-gate transfer.
    monkeypatch.setenv("ANTIEK_STRIPE_PROVIDER", "real")
    with _con(db) as con:
        p = project.create_project(con, title="Dad's biography")
        contributor.map_contributor(con, interview_id="iv-a", project_id=p.project_id, display_name="A")
        with pytest.raises(NotImplementedError):
            contributor.attempt_disbursement(con, project_id=p.project_id, interview_id="iv-a")
