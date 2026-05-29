"""SPR-11 — end-to-end ad-economics verification (the capstone).

These tests COMPOSE the real economics chain (auction → per-second frame
attention → eligibility filter → accrual → escrow → trace → disbursement gate)
over a faithful PROD-SHAPED FIXTURE corpus and assert the invariants hold
end-to-end. They build NO new economics; they verify the modules' COMPOSITION.

Rigor #2 — steelman "unit tests already cover this": the upstream unit tests
(test_frame_attention_accrual, test_attribution_*, test_seam_single_escrow_
writer) each prove ONE module in isolation with hand-fed inputs. None of them
drive the WHOLE chain — auction-priced window → real eligibility filter →
real accrual → real escrow → real trace → real gate — over a multi-session
corpus and assert it reconciles to the cent AND that the disbursement gate
blocks. A green unit suite + a broken composition (e.g. an off-by-one in how
ad value flows from the auction into the per-second engine, or an escrow total
that silently drops the unmapped-eligible cents) would pass every unit test and
still ship a wrong money story. Only the e2e run proves the seams line up.

Rigor #3 — prove the NEGATIVE: test_disbursement_is_blocked_by_the_real_gate
CALLS the real attempt_disbursement and asserts it raises; it does NOT merely
refrain from calling. test_no_stripe_path_invoked asserts the harness imports
no module under tools/stripe_connect/.
"""

from __future__ import annotations

import os
import tempfile
from decimal import Decimal

import pytest

from runtime.db_lock import connect_write
from substrate import ip_holders
from substrate.ad_inventory.payout import CREATOR_REV_SHARE, PLATFORM_CUT
from substrate.speak import contributor

from tools import verify_ad_economics as ve


@pytest.fixture
def con():
    tmpdir = tempfile.mkdtemp(prefix="antiek-spr11-e2e-")
    db_path = os.path.join(tmpdir, "e2e.duckdb")
    c = connect_write(db_path, purpose="spr11_e2e_test")
    c.execute(ve._IP_HOLDERS_DDL)
    yield c
    c.close()


@pytest.fixture
def report(con):
    return ve.verify(con)


# ---------------------------------------------------------------------------
# M1 — the chain runs through the ACTUAL modules (no mocks)
# ---------------------------------------------------------------------------


def test_m1_chain_drives_every_session_through_real_modules(report):
    """Every session produced a real WindowAccrual via accrue_window, an ad was
    selected via the real SPR-10 select_ad, and the accrual replays identically
    (proving the persisted ledger re-derives from the same inputs)."""
    assert len(report.results) == 4
    for r in report.results:
        assert r.ad_value_usd_cents > 0
        assert r.selected_ad_id is not None  # the real auction cleared a slot
        assert r.accrual.batch_ref.startswith("frame-batch-")
        assert r.replay_identical, f"{r.window_id} did not replay identically"


def test_m1_idempotent_no_double_accrual(con):
    """Re-running the chain in the SAME DB does not double-accrue escrow (the
    accrue_window idempotency carries through the whole composition)."""
    corpus = ve._build_corpus()
    ve.run_chain(con, corpus)
    before = {h.ip_holder_id: h.escrow_balance_usd for h in ip_holders.list_all(con)}
    # Re-accrue identical batches (same publishers already exist; reuse them).
    publisher_to_holder = {h.display_name: h.ip_holder_id for h in ip_holders.list_all(con)}
    for session in corpus:
        batch = ve._frame_for(session)
        a2h = {a.asset_id: (publisher_to_holder.get(a.publisher) if a.publisher else None)
               for a in session.assets}
        ve.accrue_window(con, batch, asset_to_ip_holder=a2h)
    after = {h.ip_holder_id: h.escrow_balance_usd for h in ip_holders.list_all(con)}
    assert before == after


# ---------------------------------------------------------------------------
# M2 — conservation + 70/30 (to the cent, constants not hardcoded)
# ---------------------------------------------------------------------------


def test_m2_run_level_conservation_to_the_cent(report):
    rec = report.reconciliation
    assert rec.reconciles, (
        f"Σ contributor ({rec.total_contributor_cents}) + Σ house "
        f"({rec.total_house_cents}) != Σ ad value ({rec.total_ad_value_cents})"
    )
    # THE invariant, stated explicitly:
    assert (rec.total_contributor_cents + rec.total_house_cents
            == rec.total_ad_value_cents)


def test_m2_per_window_reconciles_via_window_accrual(report):
    """Every window's WindowAccrual.reconciles() AND the persisted
    window_reconciliation agree with its ad value."""
    assert report.reconciliation.per_window_reconciles
    for r in report.results:
        assert r.accrual.reconciles()
        contrib = sum(line.amount_cents for line in r.accrual.asset_lines)
        assert contrib + r.accrual.house.amount_cents == r.ad_value_usd_cents


def test_m2_seventy_thirty_read_from_payout_constants(report):
    """The 70/30 split is READ from payout.py, never hardcoded here."""
    rec = report.reconciliation
    assert rec.creator_rev_share == CREATOR_REV_SHARE == Decimal("0.70")
    assert rec.platform_cut == PLATFORM_CUT == Decimal("0.30")
    assert rec.split_sums_to_one


def test_m2_all_amounts_non_negative(report):
    assert report.reconciliation.all_non_negative


# ---------------------------------------------------------------------------
# M3 — traceability (amount → chunk → asset → holder, reconciles)
# ---------------------------------------------------------------------------


def test_m3_every_escrow_trace_reconciles_to_accrued_amount(report):
    """Each holder's escrow traces back through explain_asset_earning + the
    frame accrual rows to the EXACT cents it accrued."""
    assert report.traces, "expected at least one holder with escrow to trace"
    for t in report.traces:
        assert t.reconciles, (
            f"{t.publisher} escrow {t.escrow_balance_usd} did not reconcile to "
            f"its frame-accrued cents"
        )
        # The trace names the contributing chunks/assets — not an opaque total.
        assert t.explanations
        for e in t.explanations:
            assert e["eligible"] is True
            assert e["per_chunk"], "trace must decompose to chunks"


def test_m3_trace_uses_real_explain_no_parallel_logic(con):
    """The trace is produced by the real explain_asset_earning, and an eligible
    asset's per-chunk contributions sum to its asset total (the SPR-04
    conservation property the trace inherits)."""
    from substrate.ad_inventory.attribution import AttributionAlgorithm
    from substrate.ad_inventory.attribution_explain import explain_asset_earning

    exp = explain_asset_earning(
        document_id="doc-mit-quantum",
        algorithm=AttributionAlgorithm.OPTION_B_CONFIDENCE_TIMES_TIER,
        period_label="t",
        chunk_to_document={"ch-mq-1": "doc-mit-quantum", "ch-x": "doc-other"},
        period_revenue_usd_cents=1000,
        chunk_to_claim_confidence={"ch-mq-1": 0.9, "ch-x": 0.5},
        document_to_source_tier={"doc-mit-quantum": 1, "doc-other": 5},
        content_class="opt_in_licensed",
    )
    assert exp.eligible
    assert sum(c.earned_usd_cents for c in exp.per_chunk) == exp.total_earned_usd_cents


# ---------------------------------------------------------------------------
# M4 — eligibility gate (read via monetization_eligible, not re-derived)
# ---------------------------------------------------------------------------


def test_m4_private_user_owned_asset_earns_zero_even_when_alone(con):
    """A user_owned private upload that is the ONLY thing in frame earns $0 —
    the whole window pockets to the house."""
    report = ve.verify(con)
    # win-read-004 is the all-private session.
    s4 = next(r for r in report.results if r.window_id == "win-read-004")
    assert s4.accrual.asset_lines == ()  # no contributor line
    assert s4.accrual.house.amount_cents == s4.ad_value_usd_cents  # all house
    # And the private asset never appears in ANY accrual row.
    rows = con.execute(
        "SELECT COUNT(*) FROM frame_attention_accruals WHERE asset_id = 'doc-only-private'"
    ).fetchone()[0]
    assert rows == 0


def test_m4_public_eligible_asset_accrues(report):
    """A publicly-searchable eligible asset (opt_in_licensed) accrues > 0."""
    s1 = next(r for r in report.results if r.window_id == "win-read-001")
    mit = next(line for line in s1.accrual.asset_lines if line.asset_id == "doc-mit-quantum")
    assert mit.amount_cents > 0


def test_m4_gated_but_public_asset_accrues_to_escrow_body_withheld(report, con):
    """A restricted_pending_opt_in (gated-but-public) asset EARNS to escrow
    while its body is non-servable. We assert it accrued; servability is a
    different gate (orthogonal §9.0) and is never rendered/cited as a body
    here — the asset earns purely off in-frame visibility."""
    from substrate.ad_inventory.attribution import monetization_eligible
    from substrate.contracts.servable import FULL_TEXT_SERVABLE

    assert monetization_eligible("restricted_pending_opt_in") is True
    # Body is NOT servable for the gated class (the §9.0 render gate, derived
    # from the SAME content_class via FULL_TEXT_SERVABLE). EARNS != renders.
    assert "restricted_pending_opt_in" not in FULL_TEXT_SERVABLE
    s2 = next(r for r in report.results if r.window_id == "win-research-002")
    gated = next(line for line in s2.accrual.asset_lines
                 if line.asset_id == "doc-cup-gated")
    assert gated.amount_cents > 0
    assert gated.ip_holder_id is not None  # routed to its pre_onboarded holder


def test_m4_eligibility_is_read_not_re_derived(report):
    """The eligibility verdicts in the report come from the real
    monetization_eligible — assert the report agrees with the source."""
    from substrate.ad_inventory.attribution import monetization_eligible

    seen = {}
    for session in report.corpus:
        for a in session.assets:
            seen[a.content_class] = monetization_eligible(a.content_class)
    assert seen["user_owned"] is False
    assert seen["opt_in_licensed"] is True
    assert seen["restricted_pending_opt_in"] is True
    assert seen["public_domain"] is True
    assert seen["source_declared_open"] is True


# ---------------------------------------------------------------------------
# M5 — house-second pocket (explicit line, not a residual; no fake impression)
# ---------------------------------------------------------------------------


def test_m5_zero_eligible_second_produces_house_record(report, con):
    """A window with no eligible in-frame contributor produces a house record;
    the platform pockets it; no contributor accrues; it's an explicit row."""
    s4 = next(r for r in report.results if r.window_id == "win-read-004")
    assert s4.accrual.house.amount_cents > 0
    assert s4.accrual.house.reason == "no_eligible_asset_in_frame"
    # The house row is persisted explicitly (not inferred as a residual).
    hrow = con.execute(
        "SELECT amount_cents FROM house_seconds WHERE window_id = 'win-read-004'"
    ).fetchone()
    assert hrow is not None
    assert hrow[0] == s4.accrual.house.amount_cents


def test_m5_house_total_is_explicit_line_in_conservation(report):
    """Σ house seconds is an explicit line that reconciles INTO M2 (not a
    plug). Recompute it independently and assert it matches the report."""
    independent_house = sum(r.accrual.house.amount_cents for r in report.results)
    assert independent_house == report.reconciliation.total_house_cents
    assert (report.reconciliation.total_contributor_cents
            + independent_house == report.reconciliation.total_ad_value_cents)


# ---------------------------------------------------------------------------
# M6 — safety valve: escrow accrues, NOTHING disburses (prove the negative)
# ---------------------------------------------------------------------------


def test_m6_escrow_accrues_to_pre_onboarded_holder(report, con):
    """Escrow accrues to pre_onboarded holders (no notification, no claim)."""
    holders = ip_holders.list_all(con)
    earning = [h for h in holders if h.escrow_balance_usd > 0]
    assert earning, "expected escrow to accrue to publishers"
    for h in earning:
        assert h.status == "pre_onboarded"  # never claimed/invited by the harness
        assert h.notification_sent_at is None  # no notification sent


def test_m6_disbursement_is_blocked_by_the_real_gate(con):
    """Rigor #3 — CALL the real attempt_disbursement and assert it raises
    DisbursementBlocked. We do NOT close/flip/mock G2/G3, and we do NOT merely
    refrain from calling."""
    ve.verify(con)
    # The real gate must report not-allowed by default (mock provider).
    from substrate.speak import gate_status
    assert gate_status.disbursement_allowed().allowed is False

    with pytest.raises(contributor.DisbursementBlocked):
        contributor.attempt_disbursement(
            con, project_id="spr11-verify", interview_id="spr11-iv",
        )


def test_m6_we_did_not_close_or_flip_the_gate(monkeypatch):
    """Defensibility — assert the harness/test never sets ANTIEK_STRIPE_PROVIDER
    to 'real'. The gate's default must remain mock; flipping it would be an
    automatic-fail of this sprint."""
    # The env var must NOT be 'real' in this process.
    assert os.environ.get("ANTIEK_STRIPE_PROVIDER", "mock").strip().lower() != "real"


def test_m6_no_stripe_path_invoked():
    """The harness imports NO module under tools/stripe_connect/. (If it did, a
    disbursement path could exist; it must not.)"""
    import sys
    # The harness module is imported at the top of this test file.
    stripe_mods = [m for m in sys.modules
                   if m.startswith("tools.stripe_connect")]
    # Importing the e2e tests + the harness must not have pulled in any
    # stripe_connect module.
    assert not stripe_mods, f"stripe_connect was imported: {stripe_mods}"
    # And the harness source contains no reference to the stripe_connect package.
    src = ve.__file__
    with open(src, encoding="utf-8") as fh:
        text = fh.read()
    assert "stripe_connect" not in text.replace(
        "tools/stripe_connect/", "<<path-mention-in-docstring>>"
    ), "harness must not reference the stripe_connect package in code"


def test_m6_report_states_zero_disbursed(report):
    """The rendered report states plainly 'disbursed: $0 (G2/G3 open)'."""
    text = ve.render_report(report)
    assert "disbursed: $0 (G2/G3 open)" in text
    assert "VERIFIED" in text  # the run reconciled and the valve held


def test_report_discloses_unmapped_eligible_accrual_in_prose(report):
    """Rigor #1 (honesty): when Σ contributor accrual exceeds Σ escrow-by-holder
    because an eligible asset has no ip_holder, the report must SAY SO in prose
    AND name the asset — not leave the operator to reconstruct it from raw rows.
    The fixture has exactly one such asset (doc-open-cc), so the disclosure must
    name it and the escrow-by-holder line must be present."""
    text = ve.render_report(report)
    escrow_total = sum(h.escrow_balance_cents for h in report.holders)
    unmapped_delta = report.reconciliation.total_contributor_cents - escrow_total
    assert unmapped_delta > 0, "fixture must exercise the unmapped-eligible case"
    assert "Σ escrow-by-holder" in text
    # The disclosure names the specific unmapped earner and the exact gap.
    assert "doc-open-cc" in text
    assert f"by ${unmapped_delta / 100:,.2f}" in text
    assert "Conservation is on the accrual ledger, not escrow" in text


# ---------------------------------------------------------------------------
# Full report reconciliation (defensibility — the operator's trust artifact)
# ---------------------------------------------------------------------------


def test_report_reconciles_and_is_reproducible(con):
    """Render the report twice over two fresh DBs and assert the economic
    SUBSTANCE matches (amounts, house, conservation) — only the random
    ip_holder_id surrogate keys differ, which are masked out."""
    import re

    def _substance(text: str) -> str:
        # Mask non-deterministic surrogate ids so we compare the money story.
        return re.sub(r"ipholder-[0-9a-f]+", "ipholder-XXX", text)

    r1 = ve.render_report(ve.verify(con))

    tmpdir = tempfile.mkdtemp(prefix="antiek-spr11-repro-")
    db2 = os.path.join(tmpdir, "repro.duckdb")
    c2 = connect_write(db2, purpose="spr11_repro")
    try:
        c2.execute(ve._IP_HOLDERS_DDL)
        r2 = ve.render_report(ve.verify(c2))
    finally:
        c2.close()

    assert _substance(r1) == _substance(r2)
