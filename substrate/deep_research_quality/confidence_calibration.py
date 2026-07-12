"""Confidence calibration — are confidence labels epistemically honest?

Operator vision (ask #7): *"provide the highest quality deep research product in
the world."* The canonical ``ArtifactInsight`` carries a ``confidence: str | None``
field — the artifact's own assessment of how sure it is about each finding. This
is epistemic METADATA: the artifact is telling the operator "trust this insight a
lot" or "treat this insight cautiously."

No current axis uses this field. citation_grounding (#1848) checks whether
insights trace to sources; provenance_coverage (#1940) checks source provenance.
Neither asks: **are the confidence labels HONEST?** If an artifact labels 10
insights "high confidence" but 8 of them have no source document (ungrounded),
the labels are MISCALIBRED — the artifact is epistemically overconfident, claiming
certainty it cannot support. Conversely, if every insight (grounded or not) is
labeled the same confidence, the labels carry no INFORMATION — they are
meaningless decoration. This axis measures whether confidence labels correlate
with actual grounding (the honest-calibration property).

**The measurement (hard to vary).** For each insight that HAS a confidence label:
* ``grounded`` = has a non-empty ``source_document_id``.
* ``ungrounded`` = no ``source_document_id`` (or empty string).

Confidence labels are bucketed into HIGH / MEDIUM / LOW by lexical mapping (the
field is a free-form string, so a normalized rank is computed). The
``calibration_score`` is the DIFFERENCE between the high-confidence grounding
rate and the low-confidence grounding rate:
``high_grounded_rate - low_grounded_rate`` in ``[-1.0, 1.0]``.
* Positive (high-confidence insights are MORE often grounded than low-confidence)
  = WELL-CALIBRED — the labels are informative and honest.
* Near zero = FLAT — the labels carry no grounding information.
* Negative = INVERTED — high-confidence insights are LESS grounded than
  low-confidence (miscalibrated in the dangerous direction — overconfident).

**Honesty rules (load-bearing):**
* Insights WITHOUT a confidence label (``None``) are EXCLUDED — the calibration is
  about labeled insights only. ``unlabeled_count`` is carried so the operator sees
  how much of the artifact was not self-assessed.
* If ALL insights lack confidence labels -> ``unknown`` (defer; never fabricated).
* If all LABELED insights share the same bucket (e.g. everything is "high") ->
  ``flat`` (the labels carry no discriminating information; ``calibration_score``
  is 0.0, not fabricated).
* ``calibration_score`` is in ``[-1.0, 1.0]`` whenever it is not ``None``.
* Deterministic and pure: same inputs -> same report. No LLM, no network, no
  clock, no mutation.
* ``authority`` is always ``"advisory"``.

**Lexical confidence bucketing (load-bearing).** The ``confidence`` field is a
free-form string. The module maps known lexical patterns to HIGH/MEDIUM/LOW:
* HIGH: "high", "certain", "confident", "strong", "definitive", "verified"
* LOW: "low", "uncertain", "tentative", "weak", "speculative", "unverified"
* Everything else (including unrecognized strings) -> MEDIUM (the neutral default;
  never fabricated as high or low without lexical evidence). This is deliberately
  lexical: an unrecognized confidence string is treated as neutral, not guessed.

**Import-free of off-main siblings.** Uses the canonical
``ArtifactInsight(node_id, text, source_document_id, confidence)`` from
``substrate/research_artifact/schema.py`` (stable on origin/main).
"""

from __future__ import annotations

from dataclasses import dataclass

from substrate.research_artifact.schema import ArtifactInsight, ResearchArtifactBody

_HIGH_MARKERS: frozenset[str] = frozenset(
    {"high", "certain", "confident", "strong", "definitive", "verified", "sure"}
)
_LOW_MARKERS: frozenset[str] = frozenset(
    {"low", "uncertain", "tentative", "weak", "speculative", "unverified", "doubtful"}
)


@dataclass(frozen=True)
class ConfidenceCalibrationReport:
    """The artifact's confidence-label honesty surface. Advisory, pure."""

    artifact_id: str
    labeled_insight_count: int  # insights WITH a confidence label
    unlabeled_insight_count: int  # insights WITHOUT (None)
    high_confidence_count: int
    medium_confidence_count: int
    low_confidence_count: int
    high_grounded_rate: float | None  # fraction of high-confidence with source; None if 0
    low_grounded_rate: float | None
    calibration_score: float | None  # high_grounded - low_grounded in [-1,1]; None if not measurable
    verdict: str  # well_calibrated | flat | miscalibrated | unknown
    notes: tuple[str, ...]
    authority: str = "advisory"


def _confidence_bucket(confidence: str) -> str:
    """Map a confidence string to HIGH / MEDIUM / LOW (word-level, neutral default).

    Uses word-level matching (not substring) so 'uncertain' is NOT caught by the
    'certain' HIGH marker, and 'unverified' is NOT caught by 'verified'.
    """
    import re

    tokens = set(re.findall(r"[a-z]+", confidence.strip().lower()))
    if tokens & _HIGH_MARKERS:
        return "high"
    if tokens & _LOW_MARKERS:
        return "low"
    return "medium"


def _is_grounded(insight: ArtifactInsight) -> bool:
    return bool(insight.source_document_id and insight.source_document_id.strip())


def measure_confidence_calibration(
    artifact: ResearchArtifactBody,
) -> ConfidenceCalibrationReport:
    """Measure whether the artifact's confidence labels correlate with grounding.

    ``artifact`` is the canonical knowledge-asset body. Returns a
    :class:`ConfidenceCalibrationReport`.

    Pure: no DB, no LLM, no clock, no mutation.
    """
    labeled: list[tuple[str, bool]] = []  # (bucket, is_grounded)
    unlabeled = 0

    for ins in artifact.insights:
        if ins.confidence is None:
            unlabeled += 1
            continue
        bucket = _confidence_bucket(ins.confidence)
        labeled.append((bucket, _is_grounded(ins)))

    high = [(b, g) for b, g in labeled if b == "high"]
    low = [(b, g) for b, g in labeled if b == "low"]

    high_count = len(high)
    low_count = len(low)
    medium_count = len(labeled) - high_count - low_count

    high_grounded = sum(1 for _, g in high if g)
    low_grounded = sum(1 for _, g in low if g)

    high_rate: float | None = (high_grounded / high_count) if high_count else None
    low_rate: float | None = (low_grounded / low_count) if low_count else None

    notes: list[str] = [
        "confidence calibration measures whether the artifact's confidence LABELS "
        "are epistemically honest — do high-confidence insights have better source "
        "grounding than low-confidence ones? This is about label HONESTY, not "
        "content quality (the content axes measure that)",
        "unrecognized confidence strings map to MEDIUM (neutral default, never "
        "fabricated as high/low without lexical evidence); insights without a "
        "confidence label are excluded from calibration (the unlabeled_count shows "
        "how much was not self-assessed)",
    ]

    if not labeled:
        calibration_score = None
        verdict = "unknown"
        notes.append(
            f"all {unlabeled} insight(s) lack confidence labels; calibration is not "
            f"measurable (defer — never fabricated)"
        )
    elif high_count == 0 or low_count == 0:
        calibration_score = 0.0 if high_count or low_count else None
        verdict = "flat"
        if calibration_score is not None:
            notes.append(
                f"all labeled insights share a single confidence bucket "
                f"({high_count} high, {medium_count} medium, {low_count} low); "
                f"the labels carry no discriminating grounding information "
                f"(calibration_score 0.0)"
            )
    elif high_rate is not None and low_rate is not None:
        calibration_score = high_rate - low_rate
        if calibration_score > 0.25:
            verdict = "well_calibrated"
            notes.append(
                f"calibration_score {calibration_score:+.2f}: high-confidence "
                f"insights are grounded at {high_rate:.0%} vs low-confidence at "
                f"{low_rate:.0%} — the labels are informative and honest"
            )
        elif calibration_score < -0.25:
            verdict = "miscalibrated"
            notes.append(
                f"calibration_score {calibration_score:+.2f}: high-confidence "
                f"insights are LESS grounded ({high_rate:.0%}) than low-confidence "
                f"({low_rate:.0%}) — the labels are INVERTED (overconfident in "
                f"the dangerous direction)"
            )
        else:
            verdict = "flat"
            notes.append(
                f"calibration_score {calibration_score:+.2f}: high and low "
                f"confidence insights have similar grounding rates ({high_rate:.0%} "
                f"vs {low_rate:.0%}) — the labels carry little grounding information"
            )
    else:
        calibration_score = None
        verdict = "unknown"
        notes.append("calibration not measurable from available data")

    return ConfidenceCalibrationReport(
        artifact_id=artifact.investigation_id,
        labeled_insight_count=len(labeled),
        unlabeled_insight_count=unlabeled,
        high_confidence_count=high_count,
        medium_confidence_count=medium_count,
        low_confidence_count=low_count,
        high_grounded_rate=high_rate,
        low_grounded_rate=low_rate,
        calibration_score=calibration_score,
        verdict=verdict,
        notes=tuple(notes),
        authority="advisory",
    )


__all__ = [
    "ConfidenceCalibrationReport",
    "measure_confidence_calibration",
]
