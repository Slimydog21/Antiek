"""Cohort analysis (Researchmaxx spec §E.3 + E.5).

Pure function. Takes pre-loaded cohort + outcomes data; computes the
four evaluation dimensions:

  1. Thesis accuracy by confidence stratum (calibration target check).
  2. Falsification specificity (non-empty ``specific_observable`` rate).
  3. Risk completeness (manifested-risks-anticipated rate).
  4. Decision-outcome alignment (recommendation = actual_decision,
     weighted by ``thesis_outcome_when_proceeded``).

Below ``COHORT_MIN_OBSERVED_INVESTIGATIONS`` the report attaches an
"insufficient power" warning; the numbers are still produced but
flagged as diagnostic, not load-bearing.
"""

from __future__ import annotations

import os
import sys
from collections.abc import Sequence
from typing import Any

try:
    from ...constants import (
        COHORT_MIN_OBSERVED_INVESTIGATIONS,
        CONFIDENCE_CALIBRATION_TARGETS,
    )
except ImportError:  # pragma: no cover — direct-script fallback
    _here = os.path.dirname(os.path.abspath(__file__))
    sys.path.insert(0, os.path.dirname(os.path.dirname(_here)))
    from substrate.constants import (  # type: ignore[no-redef]
        COHORT_MIN_OBSERVED_INVESTIGATIONS,
        CONFIDENCE_CALIBRATION_TARGETS,
    )

from .types import CohortOutcomeRow, CohortSynthesisRow

# Weights for the proceed-confirmation score (spec §E.3). Replaces the
# upstream's keyword-scan of the prose ``decision_outcome_at_observation``
# field with a structured grade.
_PROCEED_OUTCOME_WEIGHTS: dict[str, float] = {
    "confirmed": 1.0,
    "partially_confirmed": 0.5,
    "disconfirmed": 0.0,
    "not_observed": 0.0,
}


def analyze(
    cohort: Sequence[CohortSynthesisRow],
    outcomes_by_synthesis: dict[str, list[CohortOutcomeRow]],
) -> dict[str, Any]:
    """Compute the four cohort dimensions over ``cohort`` + observations.

    ``outcomes_by_synthesis`` maps synthesis_id → list of observation
    rows (a synthesis may be observed multiple times across review
    cycles). Syntheses with no observations are still counted in
    ``cohort_size.total_syntheses`` but excluded from the rate
    numerators / denominators.
    """
    cohort_with_outcomes = [c for c in cohort if c.synthesis_id in outcomes_by_synthesis]

    # ── 1. Thesis accuracy by confidence stratum ──
    by_confidence: dict[str, dict[str, int]] = {
        c: {"total": 0, "confirmed": 0, "partially_confirmed": 0,
            "disconfirmed": 0, "unresolved": 0}
        for c in ("high", "moderate", "low", "unknown")
    }
    for c in cohort_with_outcomes:
        thesis = c.thesis or {}
        components = thesis.get("thesis_components", [])
        claim_to_conf: dict[str, str] = {}
        for comp in components:
            claim_to_conf[comp.get("claim", "")] = comp.get("confidence", "unknown")
        for obs in outcomes_by_synthesis[c.synthesis_id]:
            for to in obs.thesis_outcomes or []:
                claim = to.get("thesis_claim", "")
                conf = claim_to_conf.get(claim, "unknown")
                outcome = to.get("outcome", "unresolved")
                bucket = by_confidence.setdefault(
                    conf,
                    {"total": 0, "confirmed": 0, "partially_confirmed": 0,
                     "disconfirmed": 0, "unresolved": 0},
                )
                bucket["total"] += 1
                bucket[outcome] = bucket.get(outcome, 0) + 1

    calibration: dict[str, dict[str, Any]] = {}
    for conf, stats in by_confidence.items():
        total = stats["total"]
        if total == 0:
            calibration[conf] = {
                **stats,
                "confirmation_rate": None,
                "in_target_band": None,
                "target_band": CONFIDENCE_CALIBRATION_TARGETS.get(conf),
            }
            continue
        rate = stats["confirmed"] / total
        band = CONFIDENCE_CALIBRATION_TARGETS.get(conf)
        in_band = (band is not None and band[0] <= rate <= band[1])
        calibration[conf] = {
            **stats,
            "confirmation_rate": round(rate, 3),
            "target_band": band,
            "in_target_band": in_band,
        }

    # ── 2. Falsification specificity ──
    falsifier_total = 0
    falsifier_specific = 0
    for c in cohort:
        for f in (c.thesis or {}).get("falsification_conditions", []):
            falsifier_total += 1
            if str(f.get("specific_observable", "")).strip():
                falsifier_specific += 1
    falsification_specificity_rate = (
        round(falsifier_specific / falsifier_total, 3) if falsifier_total else None
    )

    # ── 3. Risk completeness ──
    risk_manifested_total = 0
    risk_anticipated = 0
    for c in cohort_with_outcomes:
        thesis_risks = [
            (r.get("risk") or "").strip().lower()
            for r in (c.thesis or {}).get("execution_risks", [])
        ]
        for obs in outcomes_by_synthesis[c.synthesis_id]:
            for er in obs.execution_risk_outcomes or []:
                if er.get("manifested"):
                    risk_manifested_total += 1
                    if (er.get("risk") or "").strip().lower() in thesis_risks:
                        risk_anticipated += 1
    risk_completeness_rate = (
        round(risk_anticipated / risk_manifested_total, 3) if risk_manifested_total else None
    )

    # ── 4. Decision-outcome alignment ──
    aligned_pairs = 0
    aligned_total = 0
    proceed_confirmed = 0
    proceed_total = 0
    proceed_score_sum = 0.0
    for c in cohort_with_outcomes:
        for obs in outcomes_by_synthesis[c.synthesis_id]:
            da = obs.decision_alignment
            if not da:
                continue
            agent_rec = da.get("agent_implicit_recommendation")
            actual = da.get("actual_decision")
            if not agent_rec or not actual:
                continue
            aligned_total += 1
            if agent_rec == actual:
                aligned_pairs += 1
                if agent_rec == "proceed":
                    proceed_total += 1
                    grade = da.get("thesis_outcome_when_proceeded", "not_observed")
                    proceed_score_sum += _PROCEED_OUTCOME_WEIGHTS.get(grade, 0.0)
                    if grade == "confirmed":
                        proceed_confirmed += 1

    decision_alignment = {
        "aligned_pairs": aligned_pairs,
        "aligned_total": aligned_total,
        "alignment_rate": round(aligned_pairs / aligned_total, 3) if aligned_total else None,
        "proceed_confirmed_when_aligned": proceed_confirmed,
        "proceed_aligned_total": proceed_total,
        "proceed_confirmation_score": (
            round(proceed_score_sum / proceed_total, 3) if proceed_total else None
        ),
    }

    # ── Power check ──
    n_observed = len(cohort_with_outcomes)
    insufficient_power = n_observed < COHORT_MIN_OBSERVED_INVESTIGATIONS

    return {
        "cohort_size": {
            "total_syntheses": len(cohort),
            "with_observed_outcomes": n_observed,
            "min_for_power": COHORT_MIN_OBSERVED_INVESTIGATIONS,
        },
        "insufficient_power": insufficient_power,
        "power_warning": (
            f"Cohort has {n_observed} observed investigations; needs "
            f"≥{COHORT_MIN_OBSERVED_INVESTIGATIONS} for meaningful aggregate signal "
            f"(spec §E.5). Numbers below are diagnostic, not load-bearing."
        ) if insufficient_power else None,
        "thesis_accuracy_by_confidence": calibration,
        "falsification_specificity": {
            "rate": falsification_specificity_rate,
            "specific": falsifier_specific,
            "total": falsifier_total,
        },
        "risk_completeness": {
            "rate": risk_completeness_rate,
            "anticipated": risk_anticipated,
            "manifested": risk_manifested_total,
        },
        "decision_alignment": decision_alignment,
    }
