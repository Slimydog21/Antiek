"""No-op variance calibration for prompt-autoresearch acceptance epsilon."""

from __future__ import annotations

from dataclasses import dataclass
from statistics import pstdev

from tools.prompt_autoresearch.runner import PromptMutationOutcome
from tools.prompt_autoresearch.verdict import MIN_MEAN_DELTA


@dataclass(frozen=True)
class CalibrationReport:
    """Recommended epsilon from no-op mutation variance."""

    role: str
    iteration_count: int
    mean_delta: float
    sigma: float
    two_sigma: float
    floor_epsilon: float
    recommended_epsilon: float
    rationale: str


def calibrate_epsilon(
    role: str,
    outcomes: list[PromptMutationOutcome],
    *,
    floor_epsilon: float = MIN_MEAN_DELTA,
) -> CalibrationReport:
    """Compute the minimum acceptance epsilon from no-op outcome deltas.

    Per ``integration_autoresearch.md`` §5.3, accepted prompt mutations
    must clear no-op variance. This helper is deliberately pure: the
    operator runs the no-op cohort locally, then passes the resulting
    outcomes here.
    """
    if not role:
        raise ValueError("role must be a non-empty string")
    if not outcomes:
        raise ValueError("at least one no-op outcome is required")
    deltas = [outcome.delta for outcome in outcomes]
    mean_delta = sum(deltas) / len(deltas)
    sigma = pstdev(deltas) if len(deltas) > 1 else 0.0
    two_sigma = 2.0 * sigma
    recommended = max(floor_epsilon, two_sigma)
    return CalibrationReport(
        role=role,
        iteration_count=len(outcomes),
        mean_delta=mean_delta,
        sigma=sigma,
        two_sigma=two_sigma,
        floor_epsilon=floor_epsilon,
        recommended_epsilon=recommended,
        rationale=(
            f"{len(outcomes)} no-op mutation(s) evaluated for {role}; "
            f"observed σ={sigma:.4f}, so 2σ={two_sigma:.4f}. "
            f"Use ε≥{recommended:.4f} for prompt-autoresearch acceptance."
        ),
    )


def render_calibration_markdown(report: CalibrationReport) -> str:
    """Render an operator-reviewable calibration note."""
    return "\n".join([
        f"# Prompt autoresearch calibration — `{report.role}`",
        "",
        report.rationale,
        "",
        "## Summary",
        "",
        f"- Iterations: **{report.iteration_count}**",
        f"- Mean no-op delta: **{report.mean_delta:+.4f}**",
        f"- σ: **{report.sigma:.4f}**",
        f"- 2σ: **{report.two_sigma:.4f}**",
        f"- Floor epsilon: **{report.floor_epsilon:.4f}**",
        f"- Recommended epsilon: **{report.recommended_epsilon:.4f}**",
        "",
        "## Use",
        "",
        "Use the recommended epsilon for the mutation cohort that feeds the Wedge 1 verdict.",
        "",
    ])
