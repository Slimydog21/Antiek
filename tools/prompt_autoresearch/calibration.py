"""No-op variance calibration for prompt-autoresearch acceptance epsilon."""

from __future__ import annotations

import math
from dataclasses import dataclass
from statistics import pstdev

from tools.prompt_autoresearch.runner import PromptMutationOutcome
from tools.prompt_autoresearch.verdict import MIN_MEAN_DELTA

_FLOAT_TOLERANCE = 1e-9


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
    if (
        isinstance(floor_epsilon, bool)
        or not isinstance(floor_epsilon, int | float)
        or not math.isfinite(float(floor_epsilon))
        or floor_epsilon < 0.0
    ):
        raise ValueError("floor_epsilon must be a non-negative finite number")
    accepted = [
        outcome.mutation_id
        for outcome in outcomes
        if outcome.accepted
    ]
    if accepted:
        offenders = ", ".join(accepted[:5])
        suffix = "" if len(accepted) <= 5 else f", ... (+{len(accepted) - 5} more)"
        raise ValueError(
            "no-op calibration outcomes must all be rejected; accepted "
            f"outcome(s): {offenders}{suffix}"
        )
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
    _validate_report(report)
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


def _validate_report(report: CalibrationReport) -> None:
    if not isinstance(report.role, str) or not report.role.strip():
        raise ValueError("calibration report role must be a non-empty string")
    if (
        isinstance(report.iteration_count, bool)
        or not isinstance(report.iteration_count, int)
        or report.iteration_count <= 0
    ):
        raise ValueError("calibration report iteration_count must be positive")
    for field in (
        "mean_delta",
        "sigma",
        "two_sigma",
        "floor_epsilon",
        "recommended_epsilon",
    ):
        value = getattr(report, field)
        if isinstance(value, bool) or not isinstance(value, int | float):
            raise ValueError(f"calibration report {field} must be finite")
        if not math.isfinite(float(value)):
            raise ValueError(f"calibration report {field} must be finite")
    for field in ("sigma", "two_sigma", "floor_epsilon", "recommended_epsilon"):
        if getattr(report, field) < 0.0:
            raise ValueError(f"calibration report {field} must be non-negative")
    if abs(report.two_sigma - (2.0 * report.sigma)) > _FLOAT_TOLERANCE:
        raise ValueError("calibration report two_sigma must equal 2 * sigma")
    expected_epsilon = max(report.floor_epsilon, report.two_sigma)
    if abs(report.recommended_epsilon - expected_epsilon) > _FLOAT_TOLERANCE:
        raise ValueError(
            "calibration report recommended_epsilon must equal "
            "max(floor_epsilon, two_sigma)"
        )
    if report.recommended_epsilon < report.floor_epsilon:
        raise ValueError("calibration report recommended_epsilon must be at least floor_epsilon")
    if not isinstance(report.rationale, str) or not report.rationale.strip():
        raise ValueError("calibration report rationale must be a non-empty string")
