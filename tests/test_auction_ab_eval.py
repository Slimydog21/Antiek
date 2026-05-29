"""A/B harness tests (SPR-10 M4).

The harness must run offline, report an honest lift number (even zero/negative),
and keep rule-based the leader unless learned measurably beats it."""

from __future__ import annotations

from decimal import Decimal

from substrate.ad_inventory.ad_bidding import AdInventoryItem
from substrate.ad_inventory.intent_targeting import (
    InventoryTargeting,
    PageContext,
    TargetedInventoryItem,
)
from tools.auction_ab_eval import (
    ABReport,
    EvalSession,
    RankerResult,
    evaluate,
    format_report,
    load_sessions,
    main,
)


def _ti(inv_id: str, cpm: str, *, sector: str, intent: str) -> TargetedInventoryItem:
    return TargetedInventoryItem(
        item=AdInventoryItem(
            inventory_id=inv_id,
            advertiser_display_name=inv_id,
            target_topics=(sector,),
            cpm_usd=Decimal(cpm),
            creative_url=f"https://example.com/{inv_id}.png",
            landing_url=f"https://example.com/{inv_id}/lp",
        ),
        targeting=InventoryTargeting(
            target_sectors=(sector,), target_audience_intents=(intent,),
        ),
    )


def test_runs_on_synthetic_fixture_and_reports_lift() -> None:
    sessions, source = load_sessions(None)
    assert "synthetic" in source
    report = evaluate(sessions, data_source=source)
    # The headline is evaluated on a HELD-OUT partition — a non-empty PROPER
    # subset of the sessions (the model never trained on it).
    assert 0 < report.rule.n_sessions < len(sessions)
    assert report.rule.n_sessions == report.learned.n_sessions
    # The in-sample contrast partition is the rest and is disjoint in size.
    assert report.in_sample_rule is not None
    assert (
        report.in_sample_rule.n_sessions + report.rule.n_sessions == len(sessions)
    )
    assert report.learned.n_filled > 0
    # Lift is a finite number (may be +/-); the report names a leader honestly.
    assert isinstance(report.lift, float)
    assert report.leader in ("learned", "rule-based")


def test_synthetic_fixture_is_deterministic() -> None:
    s1, _ = load_sessions(None)
    s2, _ = load_sessions(None)
    r1 = evaluate(s1, data_source="synthetic")
    r2 = evaluate(s2, data_source="synthetic")
    assert r1.lift == r2.lift
    assert r1.rule.total_value == r2.rule.total_value
    assert r1.learned.total_value == r2.learned.total_value


def test_leader_rule_honors_measurably_better() -> None:
    """A non-positive lift keeps rule-based the leader; a positive lift makes
    learned the leader. The threshold is strict (>1e-9)."""
    rule = RankerResult("rule-based", 10, 10, 5.0)       # value/imp = 0.5
    # Tie → rule-based leads.
    learned_tie = RankerResult("learned", 10, 10, 5.0)
    rpt = ABReport(rule=rule, learned=learned_tie, data_source="x")
    assert rpt.lift == 0.0
    assert rpt.leader == "rule-based"
    # Learned worse → rule-based leads.
    learned_worse = RankerResult("learned", 10, 10, 4.0)
    assert ABReport(rule, learned_worse, "x").leader == "rule-based"
    # Learned better → learned leads.
    learned_better = RankerResult("learned", 10, 10, 6.0)
    assert ABReport(rule, learned_better, "x").leader == "learned"


def test_empty_corpus_falls_back_with_honest_label(tmp_path) -> None:
    """A db-path to an empty/nonexistent DB falls back to synthetic and SAYS so
    — the number is never mislabeled as a production result."""
    sessions, source = load_sessions(str(tmp_path / "nonexistent.duckdb"))
    assert "synthetic" in source
    assert "rule-based leads until real feedback accrues" in source
    assert len(sessions) > 0


def test_learned_finds_lift_when_value_diverges_from_cpm() -> None:
    """Construct sessions where the highest-CPM eligible candidate is NOT the
    highest-realized-value one: a learned ranker should earn >= rule-based and
    the harness should report it honestly (no fabricated lift)."""
    sessions: list[EvalSession] = []
    for i in range(60):
        ctx = PageContext(
            sector="defense", sub_sector=None,
            audience_intents=("researcher",), flat_topics=("defense",),
        )
        # High-CPM candidate has the WRONG intent (low value); low-CPM candidate
        # matches intent (high value). Rule-by-CPM picks the high-CPM low-value
        # one; learned can prefer the intent-matching high-value one.
        c_hi = _ti(f"hi{i}", "9.0", sector="defense", intent="procurement")
        c_lo = _ti(f"lo{i}", "3.0", sector="defense", intent="researcher")
        realized = {f"hi{i}": 0.2, f"lo{i}": 0.9}
        sessions.append(EvalSession(
            session_id=f"d{i}", context=ctx,
            candidates=(c_hi, c_lo), realized_value=realized,
        ))
    report = evaluate(sessions, data_source="test-divergent")
    # Rule-based picks the high-CPM low-value candidate every time → ~0.2/imp.
    assert report.rule.value_per_impression < 0.5
    # Learned should do at least as well, and the report is honest either way.
    assert report.learned.value_per_impression >= report.rule.value_per_impression - 1e-9
    assert isinstance(report.lift, float)


def test_main_runs_and_exits_zero(capsys) -> None:
    rc = main([])
    assert rc == 0
    out = capsys.readouterr().out
    assert "A/B Eval" in out
    assert "lift" in out
    assert "LEADER" in out


def test_format_report_is_honest_about_non_positive_lift() -> None:
    rule = RankerResult("rule-based", 5, 5, 3.0)
    learned = RankerResult("learned", 5, 5, 2.5)  # worse
    text = format_report(ABReport(rule, learned, "synthetic"))
    assert "RULE-BASED" in text
    assert "did NOT measurably beat" in text
