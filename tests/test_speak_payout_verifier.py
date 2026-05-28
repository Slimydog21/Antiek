"""Speak SPR-10 — AI-graded payout verifier tests.

The done-test for M3 (and the cross-session compounding-interviewer
check for M4). Holds the four payout edge cases (rigor #3), the §9
escrow routing (rigor #5 / not-a-flat-fee), the requester-cannot-deny
moral-hazard guard (rigor #2), and the hard operator-gate boundary:
nothing here disburses money — ``attempt_disbursement`` still refuses.
"""

from __future__ import annotations

import json
import os
import tempfile
from decimal import Decimal

import pytest

from runtime.db_lock import connect_write
from substrate.graph.schema import init_database
from substrate.speak import (
    consent as consent_mod,
    contributor,
    payout_verifier,
    project,
)
from substrate.speak.consent import ConsentScope
from substrate.speak.contributor import DisbursementBlocked, attempt_disbursement
from substrate.speak.payout_verifier import (
    InterviewGoal,
    grade_interview,
    release_payout,
    get_grade,
)
from substrate.speak.schema import ensure_speak_schema
from substrate.speak.third_party import record_claim


@pytest.fixture
def db(monkeypatch):
    tmpdir = tempfile.mkdtemp(prefix="speak-payout-test-")
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", os.path.join(tmpdir, "events"))
    monkeypatch.delenv("ANTIEK_SPEAK_PUBLIC_PUBLISHING", raising=False)
    monkeypatch.delenv("ANTIEK_STRIPE_PROVIDER", raising=False)  # disbursement gated
    db_path = os.path.join(tmpdir, "t.duckdb")
    with connect_write(db_path, purpose="setup") as con:
        init_database(con)
        ensure_speak_schema(con)
    return db_path


def _con(db):
    return connect_write(db, purpose="payout_test")


def _accruals_sum(con, project_id) -> Decimal:
    """The REAL escrow ledger total for a project — the sum of the rows
    actually written to ``speak_accruals`` (what the BLOCKER fix must bind,
    not just the discarded report)."""
    row = con.execute(
        "SELECT COALESCE(SUM(amount_usd), 0) FROM speak_accruals WHERE project_id = ?",
        [project_id],
    ).fetchone()
    return Decimal(str(row[0]))


def _escrow_balance_sum(con, project_id) -> Decimal:
    """The REAL ``ip_holders.escrow_balance_usd`` total for the project's
    contributors — the authoritative 'owed' figure consent_view.py sums.
    The clamp must bind THIS too, or the reconciliation surface over-states."""
    row = con.execute(
        "SELECT COALESCE(SUM(h.escrow_balance_usd), 0) "
        "FROM ip_holders h "
        "JOIN speak_contributors c ON c.ip_holder_id = h.ip_holder_id "
        "WHERE c.project_id = ?",
        [project_id],
    ).fetchone()
    return Decimal(str(row[0]))


# A goal the rubric can score: the requester wants the bakery + the war
# years covered.
GOAL = InterviewGoal(
    information_goal="What was his work and his life during the war?",
    must_cover=("the bakery he ran", "his years during the war"),
    budget_usd=Decimal("100"),
    per_interview_cap_usd=Decimal("40"),
)


def _interview(con, project_id, interview_id, answers, *, consent=True):
    """Create an interview with informant turns + (optionally) record
    consent so it can contribute claims. Returns interview_id."""
    con.execute(
        "INSERT INTO interviews (interview_id, project_id, status, transcript_turns) "
        "VALUES (?, ?, 'completed', ?)",
        [interview_id, project_id,
         json.dumps([{"role": "informant", "text": a, "question_id": f"q{i}"}
                     for i, a in enumerate(answers)])],
    )
    if consent:
        consent_mod.record_consent(
            con, interview_id=interview_id,
            scopes=[ConsentScope.RECORD, ConsentScope.ATTRIBUTE], project_id=project_id,
        )
    return interview_id


# ── M3: the verifier scores a transcript vs the goal (AI, not requester) ──


def test_substantive_interview_passes(db):
    with _con(db) as con:
        p = project.create_project(con, title="Bio", publish_intent="will_be_public")
        iv = _interview(con, p.project_id, "iv-good", [
            "He ran the village bakery for nearly thirty years, baking bread "
            "before dawn every single morning and teaching apprentices the craft.",
            "During the war years he kept the bakery open under rationing, "
            "feeding neighbours when flour was scarce and hiding two families.",
        ])
        grade = grade_interview(con, project_id=p.project_id, interview_id=iv, goal=GOAL)
        assert grade.passed is True
        assert grade.score >= payout_verifier.PASSING_SCORE
        assert grade.graded_by == "deterministic-rubric"  # no dispatch_fn injected
        assert grade.gamed_risk is False


def test_grade_uses_injected_hermes_verifier_not_requester(db):
    """The grade comes from the dispatched verifier (role='verifier',
    Hermes — §16), NOT the requester. A stub dispatch proves the path."""
    seen = {}

    def fake_dispatch(*, prompt, role, investigation_id, system):
        seen["role"] = role
        seen["has_goal"] = "INFORMATION GOAL" in prompt
        return json.dumps({"score": 0.9, "honest": True, "gamed_risk": False,
                           "rationale": "covered both points"})

    with _con(db) as con:
        p = project.create_project(con, title="Bio", publish_intent="will_be_public")
        iv = _interview(con, p.project_id, "iv-x", ["He ran the bakery during the war."])
        grade = grade_interview(con, project_id=p.project_id, interview_id=iv,
                                goal=GOAL, dispatch_fn=fake_dispatch)
    assert seen["role"] == "verifier"          # the Hermes verifier role
    assert seen["has_goal"] is True            # graded against the goal
    assert grade.graded_by == "hermes:verifier"
    assert grade.score == 0.9 and grade.passed is True


# ── rigor #3 edge case (a): bad-but-honest → withheld, KEPT + labeled ──


def test_bad_but_honest_withholds_but_keeps_and_labels(db):
    with _con(db) as con:
        p = project.create_project(con, title="Bio", publish_intent="will_be_public")
        # A sincere but off-goal/thin answer: real words, doesn't cover the goal.
        iv = _interview(con, p.project_id, "iv-honest", [
            "I'm sorry, I really only met him a couple of times at a wedding "
            "and we mostly talked about the weather and the food."
        ])
        grade = grade_interview(con, project_id=p.project_id, interview_id=iv, goal=GOAL)
        assert grade.passed is False         # payout withheld
        assert grade.gamed_risk is False     # NOT gamed — honestly off-goal
        # KEPT, not discarded: the grade + transcript persist + are labeled.
        persisted = get_grade(con, iv)
        assert persisted is not None
        assert persisted.honest is True
        row = con.execute(
            "SELECT transcript_turns FROM interviews WHERE interview_id = ?", [iv]
        ).fetchone()
        assert row[0] and "wedding" in row[0]  # transcript retained


# ── rigor #3 edge case (b): gamed-to-rubric → the OPEN risk is FLAGGED ──


def test_gamed_keyword_padding_is_flagged_not_solved(db):
    """A keyword-padded answer (high coverage, no substance) is FLAGGED
    gamed_risk. We do NOT claim to prevent it — the Goodhart risk stays
    OPEN (ROADMAP:280). This test asserts the FLAG, not a solution."""
    with _con(db) as con:
        p = project.create_project(con, title="Bio", publish_intent="will_be_public")
        iv = _interview(con, p.project_id, "iv-gamed", ["bakery war bakery war"])
        grade = grade_interview(con, project_id=p.project_id, interview_id=iv, goal=GOAL)
        # The honest limitation: the heuristic MIGHT pass it; what we
        # guarantee is the risk is surfaced, not hidden.
        assert grade.gamed_risk is True
        assert grade.honest is False


# ── rigor #3 edge case (c): budget exhausted mid-project ──


def test_budget_exhausted_stops_payout_but_keeps_interviews(db):
    with _con(db) as con:
        p = project.create_project(con, title="Bio", publish_intent="will_be_public")
        long_answer = (
            "He ran the village bakery for thirty years through the war, "
            "feeding the whole street and teaching every apprentice the craft "
            "of sourdough and rye and the patience it takes before dawn."
        )
        for n in ("iv-1", "iv-2", "iv-3"):
            iv = _interview(con, p.project_id, n, [long_answer, long_answer])
            contributor.map_contributor(con, interview_id=iv, project_id=p.project_id,
                                        display_name=n)
            record_claim(con, project_id=p.project_id, interview_id=iv,
                         text="He ran the bakery during the war.", confidence=0.9)
            grade_interview(con, project_id=p.project_id, interview_id=iv, goal=GOAL)
        # Tiny budget, real ad revenue → budget binds before all shares accrue.
        tight = InterviewGoal(information_goal=GOAL.information_goal,
                              budget_usd=Decimal("5"), per_interview_cap_usd=Decimal("0"))
        release = release_payout(con, project_id=p.project_id, goal=tight,
                                 ad_revenue_usd=Decimal("1000"))
        assert release.budget_exhausted is True
        assert release.spent_usd <= Decimal("5")
        # BLOCKER FIX: the clamp binds the REAL escrow ledger, not just the
        # report. Without ad clamping the §9-weighted creator slice would be
        # 0.70 × $1000 = $700; with the budget clamp the actual rows + escrow
        # balances must be ≤ $5.
        assert _accruals_sum(con, p.project_id) <= Decimal("5")
        assert _escrow_balance_sum(con, p.project_id) <= Decimal("5")
        # The interviews are still graded + recorded — budget stops PAYOUT,
        # not the record.
        for n in ("iv-1", "iv-2", "iv-3"):
            assert get_grade(con, n) is not None


def test_per_interview_cap_clamps_one_interview(db):
    with _con(db) as con:
        p = project.create_project(con, title="Bio", publish_intent="will_be_public")
        long_answer = ("He ran the bakery through the war for thirty long years, "
                       "feeding the street and teaching the craft before dawn daily.")
        iv = _interview(con, p.project_id, "iv-solo", [long_answer, long_answer])
        contributor.map_contributor(con, interview_id=iv, project_id=p.project_id, display_name="solo")
        record_claim(con, project_id=p.project_id, interview_id=iv,
                     text="He ran the bakery during the war.", confidence=0.9)
        grade_interview(con, project_id=p.project_id, interview_id=iv, goal=GOAL)
        capped_goal = InterviewGoal(information_goal=GOAL.information_goal,
                                    budget_usd=Decimal("1000"),
                                    per_interview_cap_usd=Decimal("7"))
        release = release_payout(con, project_id=p.project_id, goal=capped_goal,
                                 ad_revenue_usd=Decimal("1000"))
        assert "iv-solo" in release.capped_interview_ids
        assert release.spent_usd <= Decimal("7")
        # BLOCKER FIX: the cap binds the REAL escrow ledger. The single
        # interview's §9 creator slice would be 0.70 × $1000 = $700 (100× the
        # cap); the actual speak_accruals row + escrow balance must be ≤ $7.
        assert _accruals_sum(con, p.project_id) <= Decimal("7")
        assert _escrow_balance_sum(con, p.project_id) <= Decimal("7")


# ── rigor #3 edge case (d): consent withdrawn after capture → takedown ──


def test_takedown_withholds_an_earning_claim(db):
    """rigor #3d: consent withdrawn after capture → takedown applies AND
    payout respects it — on a normally-EARNING (publishable, first-person)
    claim, NOT the vacuous uncorroborated-third-party case the
    publishable_only filter would exclude anyway. The claim earns escrow
    BEFORE the takedown and is withheld ($0, not in shares) AFTER, so the
    takedown is what does the withholding."""
    from substrate.speak import takedown as takedown_mod
    with _con(db) as con:
        p = project.create_project(con, title="Bio", publish_intent="will_be_public")
        iv = _interview(con, p.project_id, "iv-td", [
            "He ran the bakery for thirty years through the war years, daily."])
        contributor.map_contributor(con, interview_id=iv, project_id=p.project_id, display_name="td")
        # A FIRST-PERSON (not third-party) claim — publishable + earning by
        # default, so the takedown is doing the withholding, not the
        # publishable_only filter.
        record_claim(con, project_id=p.project_id, interview_id=iv,
                     text="I ran the bakery for thirty years.", confidence=0.9)
        grade_interview(con, project_id=p.project_id, interview_id=iv, goal=GOAL)

        # BEFORE the takedown: the claim earns a share + accrues escrow.
        before = contributor.measure_contribution(con, project_id=p.project_id)
        assert iv in before.shares and before.shares[iv] > 0
        release_before = release_payout(con, project_id=p.project_id, goal=GOAL,
                                        ad_revenue_usd=Decimal("100"))
        earning_before = {l.interview_id: l for l in release_before.accrual_lines
                          if not l.slop_gated}
        assert iv in earning_before and earning_before[iv].amount_usd > 0
        assert _escrow_balance_sum(con, p.project_id) > 0

        # The interviewee withdraws after capture → takedown reaches the
        # interview. §9 measurement now excludes the taken-down claim.
        takedown_mod.request_takedown(con, project_id=p.project_id,
                                      target_kind="interview", target_id=iv)
        after = contributor.measure_contribution(con, project_id=p.project_id)
        assert iv not in after.shares  # respected — no payout share
        # A fresh release post-takedown accrues $0 for the taken-down
        # interview (its share is withheld, not paid again).
        release_after = release_payout(con, project_id=p.project_id, goal=GOAL,
                                       ad_revenue_usd=Decimal("100"))
        earning_after = {l.interview_id: l for l in release_after.accrual_lines
                         if not l.slop_gated}
        assert iv not in earning_after  # withheld in routing after takedown


# ── rigor #2: requester-cannot-deny a passing interview (moral hazard) ──
#
# The guard is STRUCTURAL, not a function call: there is no production code
# path by which a requester denies a passing interview's payout. An earlier
# draft shipped an ``assert_requester_cannot_deny`` runtime guard + a 403
# endpoint branch; both were DEAD (no caller could reach a deny path), so
# they were removed and the canonical proof is the structural test below —
# economics_mode has no "public but no split" override.


def test_economics_has_no_public_but_no_split_path(db):
    """The STRUCTURAL guard (the canonical requester-cannot-deny proof):
    economics_mode.resolve_policy has no override that yields public
    WITHOUT the split. Public always ⇒ split_applies. ``release_payout``
    takes only the verifier's score as input — the requester supplies the
    goal + money bounds, never a pass/deny verdict — so a passing interview
    cannot be unilaterally denied; the moral hazard is closed by the absence
    of a path, not by an assertion."""
    from substrate.speak import economics_mode
    for invitation in ("private", "public"):
        pol = economics_mode.resolve_policy(invitation, "public")
        assert pol.split_applies is True  # no "public but no split" path exists


# ── rigor #5: a released payout routes via §9, NOT a flat fee ──


def test_release_routes_via_section9_not_flat_fee(db):
    with _con(db) as con:
        p = project.create_project(con, title="Bio", publish_intent="will_be_public")
        big = ("He ran the bakery for thirty years through the war, feeding the "
               "whole street and teaching the craft before dawn every morning.")
        small = ("He ran the bakery during the war and helped where he could "
                 "around the neighbourhood when times were hard.")
        a = _interview(con, p.project_id, "iv-a", [big, big])
        b = _interview(con, p.project_id, "iv-b", [small])
        contributor.map_contributor(con, interview_id=a, project_id=p.project_id, display_name="a")
        contributor.map_contributor(con, interview_id=b, project_id=p.project_id, display_name="b")
        # Different contribution weights via claim confidence (§9.3 Option B).
        record_claim(con, project_id=p.project_id, interview_id=a,
                     text="He ran the bakery for thirty years.", confidence=0.95)
        record_claim(con, project_id=p.project_id, interview_id=b,
                     text="He helped the neighbourhood.", confidence=0.4)
        grade_interview(con, project_id=p.project_id, interview_id=a, goal=GOAL)
        grade_interview(con, project_id=p.project_id, interview_id=b, goal=GOAL)
        release = release_payout(con, project_id=p.project_id, goal=GOAL,
                                 ad_revenue_usd=Decimal("100"))
        earning = {l.interview_id: l for l in release.accrual_lines if not l.slop_gated}
        # NOT a flat fee: the two earning shares differ (§9 weighting), and
        # the heavier contributor earns more.
        assert "iv-a" in earning and "iv-b" in earning
        assert earning["iv-a"].share_fraction != earning["iv-b"].share_fraction
        assert earning["iv-a"].amount_usd > earning["iv-b"].amount_usd
        # The amounts accrued to ESCROW (speak_accruals), the §9 path.
        total = contributor.accrued_total(con, p.project_id)
        assert total > 0


# ── the hard operator-gate boundary: NOTHING here disburses ──


def test_release_never_disburses_money(db):
    """Releasing payout accrues to escrow; disbursement stays gated. The
    structural proof: attempt_disbursement still REFUSES (G2/G3 open)."""
    with _con(db) as con:
        p = project.create_project(con, title="Bio", publish_intent="will_be_public")
        iv = _interview(con, p.project_id, "iv-1", [
            "He ran the bakery for thirty years through the war years daily."])
        contributor.map_contributor(con, interview_id=iv, project_id=p.project_id, display_name="x")
        record_claim(con, project_id=p.project_id, interview_id=iv,
                     text="He ran the bakery.", confidence=0.9)
        grade_interview(con, project_id=p.project_id, interview_id=iv, goal=GOAL)
        release_payout(con, project_id=p.project_id, goal=GOAL, ad_revenue_usd=Decimal("100"))
        # The gate is untouched: money cannot leave escrow pre-G2/G3.
        with pytest.raises(DisbursementBlocked):
            attempt_disbursement(con, project_id=p.project_id, interview_id=iv)
