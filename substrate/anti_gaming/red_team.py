"""Executable attack-class simulators for the Sprint 23-24 red-team gate.

The `docs/sprint23_red_team.md` template documents four attack classes
that an external red-team must catch before Sprints 23-24 ship. This
module provides the in-process simulators + a report generator that
converts the template's '[to be filled in]' slots into concrete
pass/fail evidence.

The simulators are deterministic — no real network — and exercise the
substrate detectors directly. An external red-team firm can:
1. Run this harness to baseline the substrate's current calibration.
2. Mutate the substrate (e.g., to introduce a regression) and re-run
   to verify their attack still gets caught.
3. Cite the harness output as the §2 evidence in the report.

Attack classes covered (all four from sprint23_red_team.md §2):
- A: Botnet view inflation (homogeneous UA + IP /24 + short dwell)
- B: Attribution-graph injection (deep chain depth)
- C: Multi-account self-attribution (single-consumer dominance)
- D: Creator-cluster collusion (mutual boosting ring)
"""

from __future__ import annotations

import enum
from dataclasses import dataclass

from .attribution_fraud import (
    detect_creator_cluster_collusion,
    score_attribution_payout,
)
from .detector import AntiGamingDetector, run_full_check
from .verdict import FraudVerdictKind


class AttackClass(str, enum.Enum):
    A_BOTNET_VIEW_INFLATION = "A_botnet_view_inflation"
    B_ATTRIBUTION_GRAPH_INJECTION = "B_attribution_graph_injection"
    C_MULTI_ACCOUNT_SELF_ATTRIBUTION = "C_multi_account_self_attribution"
    D_CREATOR_CLUSTER_COLLUSION = "D_creator_cluster_collusion"


@dataclass(frozen=True)
class AttackResult:
    """The outcome of one simulated attack."""

    attack_class: AttackClass
    expected_verdict: FraudVerdictKind  # what the doc says should happen
    observed_verdict: FraudVerdictKind  # what the substrate actually returned
    signals_fired: tuple[str, ...]  # which named signals triggered
    samples_scored: int
    samples_blocked_or_reviewed: int

    @property
    def passed(self) -> bool:
        """The attack was caught iff observed verdict is at least as
        strong as expected (PASS < REVIEW < BLOCK)."""
        order = {
            FraudVerdictKind.PASS: 0,
            FraudVerdictKind.REVIEW: 1,
            FraudVerdictKind.BLOCK: 2,
        }
        return order[self.observed_verdict] >= order[self.expected_verdict]


@dataclass(frozen=True)
class FalsePositiveResult:
    """Calibration test: legitimate sessions should mostly PASS."""

    samples_scored: int
    samples_review: int
    samples_block: int

    @property
    def review_rate(self) -> float:
        if self.samples_scored == 0:
            return 0.0
        return self.samples_review / self.samples_scored

    @property
    def block_rate(self) -> float:
        if self.samples_scored == 0:
            return 0.0
        return self.samples_block / self.samples_scored


@dataclass(frozen=True)
class RedTeamReport:
    """The full executable evidence for the sprint23 red-team artefact."""

    substrate_version: str
    attack_results: tuple[AttackResult, ...]
    false_positive_result: FalsePositiveResult
    fp_rate_target_review: float = 0.01  # ≤ 1% FP on REVIEW
    fp_rate_target_block: float = 0.001  # ≤ 0.1% FP on BLOCK

    @property
    def all_attacks_caught(self) -> bool:
        return all(r.passed for r in self.attack_results)

    @property
    def fp_rate_acceptable(self) -> bool:
        return (
            self.false_positive_result.review_rate <= self.fp_rate_target_review
            and self.false_positive_result.block_rate <= self.fp_rate_target_block
        )

    @property
    def overall_verdict(self) -> str:
        if self.all_attacks_caught and self.fp_rate_acceptable:
            return "GO"
        return "NO-GO"


# ---------------------------------------------------------------------------
# Attack-class simulators
# ---------------------------------------------------------------------------


def simulate_attack_a_botnet_view_inflation(
    *,
    botnet_size: int = 50,
    user_agent: str = "Mozilla/5.0 (BotFrame/9.0)",
    ip_prefix: str = "203.0.113.",
    dwell_seconds: float = 0.05,
) -> AttackResult:
    """Botnet of N bots, all sharing UA + /24 + short dwell."""
    detector = AntiGamingDetector()
    blocked_or_reviewed = 0

    for i in range(botnet_size):
        verdict = run_full_check(
            detector,
            session_id=f"botnet-s-{i}",
            user_agent=user_agent,
            ip=f"{ip_prefix}{i % 250}",
            dwell_seconds=dwell_seconds,
            view_dwell_ms=10.0,
            ad_id="ad-target",
            ts_seconds=100.0 + i,
            creator_id=None,
            chain_depth=2,
        )
        if verdict.kind != FraudVerdictKind.PASS:
            blocked_or_reviewed += 1

    # The final verdict is the last bot's; pull its signals.
    final = run_full_check(
        detector,
        session_id="botnet-s-final",
        user_agent=user_agent,
        ip=f"{ip_prefix}99",
        dwell_seconds=dwell_seconds,
        view_dwell_ms=10.0,
        ad_id="ad-target",
        ts_seconds=200.0,
    )
    return AttackResult(
        attack_class=AttackClass.A_BOTNET_VIEW_INFLATION,
        expected_verdict=FraudVerdictKind.BLOCK,
        observed_verdict=final.kind,
        signals_fired=tuple(s.name for s in final.signals),
        samples_scored=botnet_size,
        samples_blocked_or_reviewed=blocked_or_reviewed,
    )


def simulate_attack_b_attribution_chain_injection(
    *,
    chain_depth: int = 12,
) -> AttackResult:
    """Inflate one creator's share via deep synthetic citation chain."""
    verdict = score_attribution_payout(
        creator_id="target-creator",
        consumer_share={"u-1": 0.3, "u-2": 0.3, "u-3": 0.4},
        chain_depth=chain_depth,
    )
    return AttackResult(
        attack_class=AttackClass.B_ATTRIBUTION_GRAPH_INJECTION,
        expected_verdict=FraudVerdictKind.REVIEW,
        observed_verdict=verdict.kind,
        signals_fired=tuple(s.name for s in verdict.signals),
        samples_scored=1,
        samples_blocked_or_reviewed=1 if verdict.kind != FraudVerdictKind.PASS else 0,
    )


def simulate_attack_c_multi_account_self_attribution(
    *,
    dominant_share: float = 0.85,
) -> AttackResult:
    """One attacker-controlled consumer dominates creator's accrual."""
    verdict = score_attribution_payout(
        creator_id="target-creator",
        consumer_share={"attacker": dominant_share, "other": 1.0 - dominant_share},
        chain_depth=3,
    )
    return AttackResult(
        attack_class=AttackClass.C_MULTI_ACCOUNT_SELF_ATTRIBUTION,
        expected_verdict=FraudVerdictKind.REVIEW,
        observed_verdict=verdict.kind,
        signals_fired=tuple(s.name for s in verdict.signals),
        samples_scored=1,
        samples_blocked_or_reviewed=1 if verdict.kind != FraudVerdictKind.PASS else 0,
    )


def simulate_attack_d_creator_cluster_collusion(
    *,
    ring_size: int = 3,
    intra_ring_share: float = 0.85,
) -> AttackResult:
    """M creators mutually citing each other to boost accrual."""
    creators = [f"c-{i}" for i in range(ring_size)]
    pairwise: dict[tuple[str, str], int] = {}
    for a in creators:
        ring_each_other = sum(1 for o in creators if o != a)
        for b in creators:
            if a == b:
                continue
            # Heavy intra-ring weight.
            pairwise[(a, b)] = int(100 * intra_ring_share / ring_each_other)
        # Token outbound to non-ring.
        pairwise[(a, "outside")] = int(100 * (1.0 - intra_ring_share))

    verdicts = detect_creator_cluster_collusion(
        creator_pairwise_attribution=pairwise,
        creators=creators,
    )
    if verdicts:
        # Use the strongest verdict for the report.
        observed = max(verdicts, key=lambda v: v.total_score)
    else:
        # No verdicts means the ring was not flagged.
        from .verdict import FraudVerdict as _FV
        observed = _FV(kind=FraudVerdictKind.PASS, signals=())

    return AttackResult(
        attack_class=AttackClass.D_CREATOR_CLUSTER_COLLUSION,
        expected_verdict=FraudVerdictKind.REVIEW,
        observed_verdict=observed.kind,
        signals_fired=tuple(s.name for s in observed.signals),
        samples_scored=ring_size,
        samples_blocked_or_reviewed=len(verdicts),
    )


# ---------------------------------------------------------------------------
# False-positive calibration
# ---------------------------------------------------------------------------


def measure_false_positive_rate(
    *,
    legitimate_sessions: int = 1000,
    seed: int = 42,
) -> FalsePositiveResult:
    """Simulate `legitimate_sessions` non-attacker users + score each.

    Realistic-ish diversity: unique UA per session, IP across many /24s,
    healthy dwell times, bursts at human pace. Substrate should
    overwhelmingly PASS these.
    """
    detector = AntiGamingDetector()
    review = 0
    block = 0

    for i in range(legitimate_sessions):
        # Each session gets unique UA + IP + healthy dwell.
        verdict = run_full_check(
            detector,
            session_id=f"legit-{i}",
            user_agent=f"Mozilla/5.0 (Browser/{i % 47}) Build/{(i * 13) % 91}",
            ip=f"10.{i % 200}.{(i * 7) % 256}.{(i * 11) % 256}",
            dwell_seconds=3.0 + (i % 10) * 0.5,
            view_dwell_ms=1500.0 + (i % 20) * 100.0,
            ad_id=f"ad-{i % 8}",
            ts_seconds=float(i * 5),  # one impression per 5s — well under burst threshold
            creator_id=f"creator-{i % 30}",  # spread across creators
            chain_depth=2 + (i % 4),
        )
        if verdict.kind == FraudVerdictKind.BLOCK:
            block += 1
        elif verdict.kind == FraudVerdictKind.REVIEW:
            review += 1

    return FalsePositiveResult(
        samples_scored=legitimate_sessions,
        samples_review=review,
        samples_block=block,
    )


# ---------------------------------------------------------------------------
# Full red-team report
# ---------------------------------------------------------------------------


def run_red_team_report(
    *,
    substrate_version: str = "unknown",
    fp_sample_size: int = 1000,
) -> RedTeamReport:
    """Run all four attack-class simulators + FP calibration."""
    return RedTeamReport(
        substrate_version=substrate_version,
        attack_results=(
            simulate_attack_a_botnet_view_inflation(),
            simulate_attack_b_attribution_chain_injection(),
            simulate_attack_c_multi_account_self_attribution(),
            simulate_attack_d_creator_cluster_collusion(),
        ),
        false_positive_result=measure_false_positive_rate(
            legitimate_sessions=fp_sample_size,
        ),
    )


def format_report_markdown(report: RedTeamReport) -> str:
    """Render the report in the §2 evidence format used by the
    sprint23_red_team.md template."""
    lines: list[str] = []
    lines.append("# Sprint 23-24 — Red-Team Report (Executable Evidence)")
    lines.append("")
    lines.append(f"**Substrate version:** `{report.substrate_version}`")
    lines.append(f"**Overall verdict:** **{report.overall_verdict}**")
    lines.append("")
    lines.append("## §2 Attack-class results")
    lines.append("")
    for r in report.attack_results:
        lines.append(f"### {r.attack_class.value}")
        lines.append(f"- Expected verdict: `{r.expected_verdict.value}`")
        lines.append(f"- Observed verdict: `{r.observed_verdict.value}`")
        lines.append(f"- Signals fired: {list(r.signals_fired)}")
        lines.append(
            f"- Samples scored: {r.samples_scored} / "
            f"blocked-or-reviewed: {r.samples_blocked_or_reviewed}"
        )
        lines.append(f"- Verdict: **{'PASS' if r.passed else 'FAIL'}**")
        lines.append("")
    lines.append("## §3 False-positive calibration")
    fp = report.false_positive_result
    lines.append(f"- Samples: {fp.samples_scored}")
    lines.append(
        f"- REVIEW rate: {fp.review_rate:.4f} "
        f"(target ≤ {report.fp_rate_target_review:.4f})"
    )
    lines.append(
        f"- BLOCK rate: {fp.block_rate:.4f} "
        f"(target ≤ {report.fp_rate_target_block:.4f})"
    )
    lines.append(f"- FP rate acceptable: **{report.fp_rate_acceptable}**")
    return "\n".join(lines)
