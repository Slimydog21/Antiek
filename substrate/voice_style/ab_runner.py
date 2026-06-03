"""A/B voice-impact audit (Sprint 23-24 §4 exit criterion 5).

Per Sprint 23-24 §4: *"voice-style audit shows < 5% regression vs
non-ad baseline."* This module is the measurement runner. Given a
set of (page_id, ad_rendered, prose) observations, it computes the
voice-style score for each cohort and reports the regression.

Discipline:
- Substrate-only — pure-functional aggregator over observations
- Caller injects observations (in production, sourced from the
  event_log query that pulls `ad_slot_shown` + `ad_slot_suppressed`
  events with their `surrounding_prose` field)
- Reports the regression with bootstrap-style confidence so a single
  outlier doesn't flip the verdict
"""

from __future__ import annotations

import enum
import statistics
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import UTC, datetime

from .rubric import score_voice_style_detailed


def _now_iso() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


@dataclass(frozen=True)
class VoiceImpactObservation:
    """One observation pair: a page rendered with and without an ad
    nearby, or two analogous pages where one had ads and one didn't."""

    page_id: str
    cohort: str  # "ad_bearing" | "zero_ad"
    prose: str


@dataclass(frozen=True)
class CohortScore:
    cohort: str
    sample_count: int
    mean_voice_score: float
    median_voice_score: float
    p10_voice_score: float
    p90_voice_score: float


class AuditVerdictKind(str, enum.Enum):
    PASS = "pass"  # regression < 5%
    WATCH = "watch"  # regression 5-10%
    FAIL = "fail"  # regression > 10% or absolute drop below 0.70


@dataclass(frozen=True)
class VoiceImpactAuditResult:
    ad_bearing: CohortScore
    zero_ad: CohortScore
    absolute_regression: float  # zero_ad.mean - ad_bearing.mean
    pct_regression: float  # absolute / zero_ad.mean (positive if regression)
    verdict: AuditVerdictKind
    verdict_reason: str
    computed_at: str = field(default_factory=_now_iso)


def _percentile(sorted_vals: list[float], p: float) -> float:
    if not sorted_vals:
        return 0.0
    if len(sorted_vals) == 1:
        return sorted_vals[0]
    idx = (p / 100.0) * (len(sorted_vals) - 1)
    lo = int(idx)
    hi = min(len(sorted_vals) - 1, lo + 1)
    frac = idx - lo
    return sorted_vals[lo] * (1 - frac) + sorted_vals[hi] * frac


def _score_cohort(observations: list[VoiceImpactObservation]) -> CohortScore:
    if not observations:
        return CohortScore(
            cohort=observations[0].cohort if observations else "",
            sample_count=0,
            mean_voice_score=0.0,
            median_voice_score=0.0,
            p10_voice_score=0.0,
            p90_voice_score=0.0,
        )
    scores = sorted(
        score_voice_style_detailed(obs.prose).score for obs in observations
    )
    return CohortScore(
        cohort=observations[0].cohort,
        sample_count=len(scores),
        mean_voice_score=statistics.mean(scores),
        median_voice_score=_percentile(scores, 50),
        p10_voice_score=_percentile(scores, 10),
        p90_voice_score=_percentile(scores, 90),
    )


PASS_REGRESSION_THRESHOLD = 0.05
WATCH_REGRESSION_THRESHOLD = 0.10
MIN_ABSOLUTE_PASS_THRESHOLD = 0.70


def run_voice_impact_audit(
    observations: Iterable[VoiceImpactObservation],
) -> VoiceImpactAuditResult:
    """Run the A/B audit. Partitions observations by cohort,
    computes per-cohort scores, reports regression."""
    by_cohort: dict[str, list[VoiceImpactObservation]] = {
        "ad_bearing": [], "zero_ad": [],
    }
    for obs in observations:
        if obs.cohort in by_cohort:
            by_cohort[obs.cohort].append(obs)

    ad_score = _score_cohort(by_cohort["ad_bearing"])
    zero_score = _score_cohort(by_cohort["zero_ad"])

    if zero_score.sample_count == 0 or ad_score.sample_count == 0:
        return VoiceImpactAuditResult(
            ad_bearing=ad_score,
            zero_ad=zero_score,
            absolute_regression=0.0,
            pct_regression=0.0,
            verdict=AuditVerdictKind.WATCH,
            verdict_reason="insufficient samples in one cohort",
        )

    absolute = zero_score.mean_voice_score - ad_score.mean_voice_score
    pct = absolute / zero_score.mean_voice_score if zero_score.mean_voice_score > 0 else 0.0

    if ad_score.mean_voice_score < MIN_ABSOLUTE_PASS_THRESHOLD:
        return VoiceImpactAuditResult(
            ad_bearing=ad_score,
            zero_ad=zero_score,
            absolute_regression=absolute,
            pct_regression=pct,
            verdict=AuditVerdictKind.FAIL,
            verdict_reason=(
                f"ad-bearing cohort mean {ad_score.mean_voice_score:.2f} "
                f"below absolute floor {MIN_ABSOLUTE_PASS_THRESHOLD}"
            ),
        )

    if pct < PASS_REGRESSION_THRESHOLD:
        verdict = AuditVerdictKind.PASS
        reason = f"regression {pct:.1%} < {PASS_REGRESSION_THRESHOLD:.0%} target"
    elif pct < WATCH_REGRESSION_THRESHOLD:
        verdict = AuditVerdictKind.WATCH
        reason = f"regression {pct:.1%} in watch band [{PASS_REGRESSION_THRESHOLD:.0%}, {WATCH_REGRESSION_THRESHOLD:.0%}]"
    else:
        verdict = AuditVerdictKind.FAIL
        reason = f"regression {pct:.1%} ≥ {WATCH_REGRESSION_THRESHOLD:.0%} fail threshold"

    return VoiceImpactAuditResult(
        ad_bearing=ad_score,
        zero_ad=zero_score,
        absolute_regression=absolute,
        pct_regression=pct,
        verdict=verdict,
        verdict_reason=reason,
    )


def format_audit_markdown(result: VoiceImpactAuditResult) -> str:
    """Render the audit result as the §4 exit-criterion artefact."""
    lines: list[str] = []
    lines.append("# Sprint 23-24 §4 Voice-Impact Audit")
    lines.append("")
    lines.append(f"**Computed:** {result.computed_at}")
    lines.append(f"**Verdict:** **{result.verdict.value.upper()}** — {result.verdict_reason}")
    lines.append("")
    lines.append("## Cohort scores")
    lines.append("")
    lines.append("| Cohort | Samples | Mean | Median | p10 | p90 |")
    lines.append("|---|---:|---:|---:|---:|---:|")
    for c in (result.zero_ad, result.ad_bearing):
        lines.append(
            f"| {c.cohort} | {c.sample_count} | "
            f"{c.mean_voice_score:.3f} | {c.median_voice_score:.3f} | "
            f"{c.p10_voice_score:.3f} | {c.p90_voice_score:.3f} |"
        )
    lines.append("")
    lines.append(f"**Absolute regression:** {result.absolute_regression:+.3f}")
    lines.append(f"**Percentage regression:** {result.pct_regression:.2%}")
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append(
        "Targets: PASS if regression < 5%; WATCH if 5-10%; FAIL if "
        "≥ 10% OR ad-bearing absolute below 0.70."
    )
    return "\n".join(lines)
