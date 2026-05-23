"""§9.4 programmatic-display gate re-evaluation runner.

Per Sprint 25+ §4 exit criterion 6: *"The §9.4 programmatic-display
gate has been re-evaluated; decision (still no / now yes) is
documented."*

Per Sprint 30+ Thread 3 §1 callout: *"if not triggered: the
rejection is renewed in writing with current-quarter numbers."*

This runner reads the current marketplace snapshot + emits the
quarterly DEFER renewal (or GO decision) per the doc's discipline.
The runner does NOT activate programmatic; it only writes the
decision artefact.

Usage:
    python -m tools.marketplace.programmatic_gate \
        --output docs/decisions/programmatic_gate_2026_Q3.md
"""

from __future__ import annotations

import argparse
import enum
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from substrate.marketplace_metrics import (
    MarketplaceSnapshot,
    build_snapshot_from_inputs,
)


# §9.4 + §9.6 thresholds.
SELF_SERVICE_THRESHOLD_CENTS = 5_000_000  # $50K/mo per §9.6
PROGRAMMATIC_DEMAND_CAPACITY_CENTS = 25_000_000  # $250K/mo per Sprint 30+ §1 callout
MANUAL_CURATION_HOURS_PER_WEEK_THRESHOLD = 20  # operator's manual cost ceiling


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


class ProgrammaticVerdictKind(str, enum.Enum):
    GO = "go"
    DEFER = "defer"


@dataclass(frozen=True)
class ProgrammaticGateVerdict:
    verdict: ProgrammaticVerdictKind
    current_monthly_spend_cents: int
    crosses_self_service_threshold: bool
    crosses_programmatic_capacity: bool
    operator_manual_hours_per_week: Optional[int]
    reasoning: str
    computed_at: str


def evaluate_programmatic_gate(
    snapshot: MarketplaceSnapshot,
    *,
    operator_manual_hours_per_week: Optional[int] = None,
) -> ProgrammaticGateVerdict:
    """Decide GO/DEFER from the marketplace snapshot."""
    spend = snapshot.advertisers.total_spend_current_cents
    crosses_ss = snapshot.advertisers.crosses_self_service_threshold
    crosses_prog = spend >= PROGRAMMATIC_DEMAND_CAPACITY_CENTS

    # The §9.4 gate is GO iff (a) aggregate demand exceeds manual-
    # curation capacity AND (b) the operator's hours-per-week on
    # manual curation crosses the threshold. Either alone is not
    # enough — demand without operator-cost-pain is a feature, not
    # a programmatic-needed signal.
    if crosses_prog and operator_manual_hours_per_week is not None and operator_manual_hours_per_week > MANUAL_CURATION_HOURS_PER_WEEK_THRESHOLD:
        verdict = ProgrammaticVerdictKind.GO
        reasoning = (
            f"aggregate spend ${spend / 100:,.0f}/mo exceeds programmatic "
            f"capacity ${PROGRAMMATIC_DEMAND_CAPACITY_CENTS / 100:,.0f}/mo AND "
            f"operator manual-curation hours ({operator_manual_hours_per_week}/week) "
            f"exceed threshold ({MANUAL_CURATION_HOURS_PER_WEEK_THRESHOLD}/week)"
        )
    else:
        reasons: list[str] = []
        if not crosses_prog:
            reasons.append(
                f"aggregate spend ${spend / 100:,.0f}/mo < programmatic "
                f"capacity ${PROGRAMMATIC_DEMAND_CAPACITY_CENTS / 100:,.0f}/mo"
            )
        if operator_manual_hours_per_week is None:
            reasons.append("operator manual-curation hours not measured this quarter")
        elif operator_manual_hours_per_week <= MANUAL_CURATION_HOURS_PER_WEEK_THRESHOLD:
            reasons.append(
                f"operator manual-curation hours ({operator_manual_hours_per_week}/week) "
                f"below threshold ({MANUAL_CURATION_HOURS_PER_WEEK_THRESHOLD}/week)"
            )
        verdict = ProgrammaticVerdictKind.DEFER
        reasoning = "; ".join(reasons)

    return ProgrammaticGateVerdict(
        verdict=verdict,
        current_monthly_spend_cents=spend,
        crosses_self_service_threshold=crosses_ss,
        crosses_programmatic_capacity=crosses_prog,
        operator_manual_hours_per_week=operator_manual_hours_per_week,
        reasoning=reasoning,
        computed_at=_now_iso(),
    )


def format_verdict_markdown(
    verdict: ProgrammaticGateVerdict,
    *,
    quarter_label: str = "2026-Q2",
) -> str:
    """Render the verdict as the quarterly artefact."""
    lines: list[str] = []
    lines.append(f"# §9.4 Programmatic-Display Gate — {quarter_label} Re-evaluation")
    lines.append("")
    lines.append(f"**Computed:** {verdict.computed_at}")
    lines.append(f"**Verdict:** **{verdict.verdict.value.upper()}**")
    lines.append("")
    lines.append("## Reasoning")
    lines.append("")
    lines.append(verdict.reasoning)
    lines.append("")
    lines.append("## Numbers cited")
    lines.append("")
    spend = verdict.current_monthly_spend_cents
    lines.append(f"- Current advertiser monthly spend: ${spend / 100:,.0f}")
    lines.append(
        f"- Self-service threshold (§9.6, $50K/mo) crossed: "
        f"{verdict.crosses_self_service_threshold}"
    )
    lines.append(
        f"- Programmatic capacity threshold ($250K/mo) crossed: "
        f"{verdict.crosses_programmatic_capacity}"
    )
    if verdict.operator_manual_hours_per_week is not None:
        lines.append(
            f"- Operator manual-curation hours: "
            f"{verdict.operator_manual_hours_per_week}/week"
        )
    else:
        lines.append("- Operator manual-curation hours: not measured this quarter")
    lines.append("")
    if verdict.verdict == ProgrammaticVerdictKind.DEFER:
        lines.append("## Discipline note")
        lines.append("")
        lines.append(
            "Per Sprint 30+ Thread 3 §1 callout: *\"if not triggered: the "
            "rejection is renewed in writing with current-quarter numbers.\"* "
            "This file IS that renewal."
        )
    else:
        lines.append("## Next steps")
        lines.append("")
        lines.append(
            "Per `docs/sprint-breakdown.html` Sprint 30+ Thread 3, GO means:"
        )
        lines.append("1. SSP onboarding (Google Ad Manager OR Magnite)")
        lines.append("2. Brand-safety classifier wired against §5.5 voice rubric")
        lines.append("3. Manual fallback for inventory below brand-safety threshold")
    return "\n".join(lines)


def _main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        description="§9.4 programmatic-display gate quarterly re-evaluation",
    )
    parser.add_argument("--quarter", default="2026-Q2",
                        help="Quarter label for the artefact title")
    parser.add_argument("--current-spend-cents", type=int, default=0,
                        help="Current month advertiser total spend (override)")
    parser.add_argument("--prior-spend-cents", type=int, default=0,
                        help="Prior month advertiser total spend (override)")
    parser.add_argument("--operator-hours-per-week", type=int, default=None,
                        help="Operator manual-curation hours/week this quarter")
    parser.add_argument("--output", default="",
                        help="Optional path to write the verdict markdown")
    args = parser.parse_args(argv)

    # Build a snapshot from the operator-supplied numbers. In
    # production this comes from the /marketplace/snapshot endpoint
    # output.
    snapshot = build_snapshot_from_inputs(
        creator_paid_cents={},
        publisher_status_rows=[],
        publisher_accrual_cents={},
        publisher_paid_cents={},
        current_advertiser_spend={"_aggregate": args.current_spend_cents} if args.current_spend_cents else {},
        prior_advertiser_spend={"_aggregate": args.prior_spend_cents} if args.prior_spend_cents else {},
    )
    verdict = evaluate_programmatic_gate(
        snapshot,
        operator_manual_hours_per_week=args.operator_hours_per_week,
    )
    md = format_verdict_markdown(verdict, quarter_label=args.quarter)
    print(md)
    if args.output:
        with open(args.output, "w") as f:
            f.write(md)
    return 0


if __name__ == "__main__":
    sys.exit(_main(sys.argv[1:]))
