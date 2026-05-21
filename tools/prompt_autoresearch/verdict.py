"""Autoresearch Wedge 1 ratify-or-reject verdict (§15.6, the Lutke-gap test).

Closes Gate G6. Aggregates ``PromptMutationOutcome`` instances from
``runner.PromptAutoresearchRunner`` into a single ratify-or-reject
markdown the operator commits to ``docs/decisions/``.

The test (per ``integration_autoresearch.md`` §5.3 + master-spec
§15.6): the propose-execute-measure-gate loop must produce mutations
that *distinguishably* beat the operator's existing prompts. "Beats"
operationally means:

1. **Acceptance rate** — fraction of mutations whose candidate score
   exceeds baseline + ε is non-trivially above chance (>40%).
2. **Mean improvement** — across all mutations (accepted + rejected),
   mean delta is positive and exceeds ε.
3. **Volume threshold** — at least 20 mutations evaluated. Fewer
   than 20 = insufficient evidence for either outcome.
4. **No-regress floor** — no single accepted mutation produced a
   regression on a sub-metric (sector_vocab_overlap or grounding
   preserved). Catches the case where the composite score improves
   while a critical sub-metric tanks.

If 1+2+3+4 all pass → RATIFY (Wedges 2-4 + Phase 8 enforcing unlock).
Otherwise → REJECT (Phase 8 keeps unconditional patching; Wedges
2-4 fall off the roadmap).

Either outcome is defensible.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from typing import Sequence

from tools.prompt_autoresearch.runner import PromptMutationOutcome


# Verdict thresholds, per §15.6 + the §16 "no consensus hedging" discipline.
# Codified here so a run can't shift the goalposts.
MIN_MUTATIONS = 20
MIN_ACCEPTANCE_RATE = 0.40
MIN_MEAN_DELTA = 0.05  # mirrors the runner's default epsilon


@dataclass(frozen=True)
class Verdict:
    """The verdict the operator commits."""

    role: str
    decision: str  # "ratify" | "reject" | "insufficient_data"
    iteration_count: int
    acceptance_rate: float
    mean_delta: float
    median_delta: float
    best_mutation_id: str | None
    best_mutation_delta: float
    total_cost_usd: float
    rationale: str
    sub_metric_regressions: list[str]


def compute_verdict(
    role: str,
    outcomes: Sequence[PromptMutationOutcome],
    *,
    min_mutations: int = MIN_MUTATIONS,
    min_acceptance_rate: float = MIN_ACCEPTANCE_RATE,
    min_mean_delta: float = MIN_MEAN_DELTA,
) -> Verdict:
    """Aggregate outcomes into a Lutke-gap verdict.

    Pure function over the outcomes; injectable thresholds for tests
    but production should use the constants at module top.
    """
    if not outcomes:
        return Verdict(
            role=role,
            decision="insufficient_data",
            iteration_count=0,
            acceptance_rate=0.0,
            mean_delta=0.0,
            median_delta=0.0,
            best_mutation_id=None,
            best_mutation_delta=0.0,
            total_cost_usd=0.0,
            rationale=(
                "No mutations have been evaluated. Run "
                "`tools.prompt_autoresearch.runner` against the role's "
                "golden traces and re-run this verdict."
            ),
            sub_metric_regressions=[],
        )

    n = len(outcomes)
    accepted = [o for o in outcomes if o.accepted]
    acceptance_rate = len(accepted) / n
    deltas = sorted(o.delta for o in outcomes)
    mean_delta = sum(deltas) / n
    median_delta = (
        deltas[n // 2]
        if n % 2 == 1
        else (deltas[n // 2 - 1] + deltas[n // 2]) / 2
    )
    best = max(outcomes, key=lambda o: o.delta)
    total_cost = sum((float(o.cost_usd) for o in outcomes), 0.0)

    # No-regress floor: any accepted mutation with a negative sub-
    # metric delta poisons the verdict. CompositeScore exposes
    # ``rubric`` (LLM-judged), ``voice_style``, ``sector_vocab``,
    # ``grounding``, ``total``.
    regressions: list[str] = []
    for o in accepted:
        scores = o.composite_breakdown
        if scores.sector_vocab < scores.rubric - 0.10:
            regressions.append(
                f"{o.mutation_id}: sector_vocab underperformed rubric "
                f"({scores.sector_vocab:.2f} vs {scores.rubric:.2f})"
            )
        if scores.grounding < 0.80:
            regressions.append(
                f"{o.mutation_id}: grounding fell below 0.80 floor "
                f"({scores.grounding:.2f})"
            )

    if n < min_mutations:
        decision = "insufficient_data"
        rationale = (
            f"Only {n} mutations evaluated; the verdict requires at "
            f"least {min_mutations} for statistical signal per §15.6. "
            "Continue running mutations against the role's golden traces."
        )
    elif regressions:
        decision = "reject"
        rationale = (
            f"{n} mutations evaluated; acceptance rate "
            f"{acceptance_rate * 100:.1f}%; mean delta {mean_delta:+.3f}. "
            f"BUT {len(regressions)} accepted mutation(s) regressed on a "
            "sub-metric (sector vocabulary or grounding). Composite-score "
            "improvement is masking a quality regression. REJECT per §15.6 "
            "no-regress floor; Phase 8 keeps current unconditional patching."
        )
    elif acceptance_rate >= min_acceptance_rate and mean_delta >= min_mean_delta:
        decision = "ratify"
        rationale = (
            f"{n} mutations evaluated; acceptance rate "
            f"{acceptance_rate * 100:.1f}% (≥{min_acceptance_rate * 100:.0f}%); "
            f"mean delta {mean_delta:+.3f} (≥{min_mean_delta:+.3f}). "
            "No sub-metric regressions on accepted mutations. The "
            "propose-execute-measure-gate loop produces distinguishable "
            "improvement on the role's eval set. RATIFY per §15.6; "
            "Wedges 2-4 unlock; Phase 8 enforcing path opens (Sprint 21)."
        )
    else:
        decision = "reject"
        rationale = (
            f"{n} mutations evaluated; acceptance rate "
            f"{acceptance_rate * 100:.1f}% (need ≥{min_acceptance_rate * 100:.0f}%); "
            f"mean delta {mean_delta:+.3f} (need ≥{min_mean_delta:+.3f}). "
            "The loop did not produce distinguishable improvement. "
            "REJECT per §15.6; Phase 8 enforcing + Wedges 2-4 fall off "
            "the roadmap; Phase 8 keeps unconditional patching."
        )

    return Verdict(
        role=role,
        decision=decision,
        iteration_count=n,
        acceptance_rate=acceptance_rate,
        mean_delta=mean_delta,
        median_delta=median_delta,
        best_mutation_id=best.mutation_id,
        best_mutation_delta=best.delta,
        total_cost_usd=total_cost,
        rationale=rationale,
        sub_metric_regressions=regressions,
    )


def render_verdict_markdown(verdict: Verdict) -> str:
    """Render the verdict as a markdown document the operator commits."""
    lines: list[str] = []
    lines.append(f"# Autoresearch Wedge 1 verdict — `{verdict.role}` (§15.6)")
    lines.append("")
    lines.append(f"**Decision:** `{verdict.decision}`")
    lines.append("")
    lines.append(verdict.rationale)
    lines.append("")
    lines.append("## Summary")
    lines.append("")
    lines.append(f"- Iterations: **{verdict.iteration_count}**")
    lines.append(f"- Acceptance rate: **{verdict.acceptance_rate * 100:.1f}%**")
    lines.append(f"- Mean delta: **{verdict.mean_delta:+.4f}**")
    lines.append(f"- Median delta: **{verdict.median_delta:+.4f}**")
    if verdict.best_mutation_id:
        lines.append(
            f"- Best mutation: `{verdict.best_mutation_id}` "
            f"(Δ = {verdict.best_mutation_delta:+.4f})"
        )
    lines.append(f"- Total cost: ${verdict.total_cost_usd:.4f}")
    lines.append("")
    if verdict.sub_metric_regressions:
        lines.append("## Sub-metric regressions (REJECT triggers)")
        lines.append("")
        for r in verdict.sub_metric_regressions:
            lines.append(f"- {r}")
        lines.append("")
    lines.append("## Next steps")
    lines.append("")
    if verdict.decision == "ratify":
        lines.append("1. Open the Sprint 21 plan; flip Phase 8 gate from shadow → enforcing.")
        lines.append("2. Open Wedge 2 work (Phase 8 skill-patch accept/reject gate at the cohort level).")
        lines.append("3. Open Wedge 3 work (config sweeps once ≥500 graded outcomes accumulate).")
        lines.append("4. Wedge 4 (local SFT loop) stays gated by `loop_3_unlock_criteria.md`.")
        lines.append("5. Close G6 by committing this verdict markdown.")
    elif verdict.decision == "reject":
        lines.append("1. Wedges 2-4 fall off the roadmap. Mark `integration_autoresearch.md` Wedges 2-4 as REJECTED.")
        lines.append("2. Phase 8 stays in unconditional-patching mode (no gate).")
        lines.append("3. Close G6 by committing this verdict markdown.")
        lines.append("4. Optionally re-run with a different role or a wider mutation space.")
    else:
        lines.append("1. Continue running mutations against the role's golden traces.")
        lines.append("2. Re-run this verdict once ≥20 mutations are evaluated.")
    lines.append("")
    lines.append(
        f"_Generated by `tools.prompt_autoresearch.verdict` "
        f"at {datetime.now(timezone.utc).isoformat()}_"
    )
    lines.append("")
    return "\n".join(lines)
