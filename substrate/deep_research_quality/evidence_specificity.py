"""Evidence specificity — does the research surface checkable, quantitative evidence?

Operator vision: *"the highest quality deep research product in the world."*
A deep-research artifact that traffics in vague qualitative claims — *"the model
performs well," "performance improved significantly"* — is low quality: nothing in
it can be checked, falsified, or acted on. The operator, a professional technology
researcher, lives or dies on CONCRETE evidence — numbers, versions, percentages,
dates, magnitudes. A research workstation that cannot distinguish a concrete finding
("GPT-4 scores 86.4% on MMLU") from hand-waving ("strong results") cannot enforce
the quality bar the vision demands.

No current axis measures this. citation_grounding (#1848) checks structural
``source_document_id``. provenance_coverage (#1940) checks source metadata.
confidence_calibration (#1953) checks whether confidence labels are honest.
twin_fidelity (#1954) checks whether the twin hallucinates vocabulary. None measure
whether the insight's CONTENT is concrete and quantitative. THIS is that axis: what
fraction of an insight's tokens are numeric evidence markers?

**The measurement (hard to vary).** For each insight:

* Tokenize on whitespace (``text.split()``) — every token is one unit.
* A token is a **numeric marker** iff it contains a digit (``re.search(r"\\d", tok)``).
  This captures integers, decimals, percentages, version strings, ranges, years,
  magnitudes — anything checkable — WITHOUT heuristic NER, stemming, or synonymy.
* ``specificity_ratio = numeric_marker_count / total_token_count`` — the density of
  concrete evidence in the insight, always in ``[0.0, 1.0]``.
* An insight with ``specificity_ratio >= concreteness_threshold`` (default 0.10) is
  ``concrete``; below is ``vague`` (a hand-wave). An insight with zero tokens is
  ``unmeasurable`` (empty text — excluded from the mean, never fabricated).

The module reports:

* ``concrete_count`` / ``vague_count`` / ``unmeasurable_count``.
* ``mean_specificity_ratio`` over measurable insights (``None`` when zero measurable).
* ``total_markers`` — raw numeric-marker count across all insights.
* per-insight ``InsightSpecificity`` (``node_id``, ``specificity_ratio``, ``verdict``,
  ``markers`` — the auditable evidence: exactly which tokens carry digits).
* ``synthesis_marker_count`` / ``synthesis_specificity_ratio`` — the synthesis
  excerpt's own concreteness (``None`` when ``synthesis_withheld`` or no excerpt —
  never fabricated).

**Whitespace tokenization (load-bearing).** A token is numeric iff it contains a
digit, period. This is deliberately COARSE: ``GPT-4`` is one numeric token, ``86.4%``
is one, ``alpha`` is not. No stemming, no synonymy, no entity recognition — the
detector flags CONCRETE, CHECKABLE evidence and nothing else. A metaphor that
*feels* specific but carries no digits ("a sea change in capability") scores low;
that is the precision/recall tradeoff: this detector prefers flagging a metaphor
(false positive) over certifying a hand-wave as concrete (false negative). A
semantic specificity check can confirm downstream.

**Honesty rules (load-bearing):**

* An insight with no tokens (empty string) is ``unmeasurable`` — excluded from the
  mean, carried through as a count (never fabricated as 0.0 or 1.0).
* ``mean_specificity_ratio`` is ``None`` when zero measurable insights (defer).
* The synthesis excerpt's specificity is ``None`` when ``synthesis_withheld`` or the
  excerpt is absent (the operator deliberately withheld it — never fabricated).
* ``specificity_ratio`` is in ``[0.0, 1.0]``; ``markers`` is the auditable evidence.
* Deterministic and pure: same inputs -> same report. No LLM, no network, no clock,
  no mutation.
* ``authority`` is always ``"advisory"``.

**Import-free of off-main siblings.** Uses the canonical ``ResearchArtifactBody``
from ``substrate/research_artifact/schema.py`` (stable on origin/main).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from substrate.research_artifact.schema import ResearchArtifactBody

_DEFAULT_CONCRETENESS_THRESHOLD: float = 0.10


class EvidenceSpecificityError(ValueError):
    """An evidence-specificity input violates a load-bearing invariant."""


@dataclass(frozen=True)
class InsightSpecificity:
    """One insight's density of numeric (concrete) evidence."""

    node_id: str
    specificity_ratio: float | None  # None if unmeasurable (no tokens)
    verdict: str  # concrete | vague | unmeasurable
    markers: tuple[str, ...]  # numeric tokens found (auditable evidence)
    token_count: int


@dataclass(frozen=True)
class EvidenceSpecificityReport:
    """The artifact's concreteness. Advisory, pure."""

    artifact_id: str
    concrete_count: int
    vague_count: int
    unmeasurable_count: int
    total_markers: int
    mean_specificity_ratio: float | None  # over measurable; None if zero measurable
    insight_specificities: tuple[InsightSpecificity, ...]
    synthesis_marker_count: int | None  # None if withheld/no excerpt
    synthesis_specificity_ratio: float | None
    concreteness_threshold: float
    verdict: str  # evidence_rich | mixed | qualitative | unknown
    notes: tuple[str, ...]
    authority: str = "advisory"


def _numeric_markers(text: str) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Return (all_tokens, numeric_tokens) for a text (numeric = tokens with a digit)."""
    tokens = text.split()
    numeric = tuple(tok for tok in tokens if re.search(r"\d", tok))
    return tuple(tokens), numeric


def _ratio(numeric: int, total: int) -> float | None:
    """Density of numeric markers; None when there are no tokens to measure."""
    if total == 0:
        return None
    return numeric / total


def measure_evidence_specificity(
    artifact: ResearchArtifactBody,
    *,
    concreteness_threshold: float = _DEFAULT_CONCRETENESS_THRESHOLD,
) -> EvidenceSpecificityReport:
    """Measure whether the artifact's insights surface quantitative, checkable evidence.

    ``artifact`` is a completed deep-research artifact. Returns an
    :class:`EvidenceSpecificityReport` with per-insight concreteness + the overall
    density of numeric evidence.

    Pure: no DB, no LLM, no clock, no mutation.
    """
    if not 0.0 <= concreteness_threshold <= 1.0:
        raise EvidenceSpecificityError(
            f"concreteness_threshold must be in [0,1], got {concreteness_threshold!r}"
        )

    per_insight: list[InsightSpecificity] = []
    concrete = 0
    vague = 0
    unmeasurable = 0
    total_markers = 0
    measurable_ratios: list[float] = []

    for ins in artifact.insights:
        all_tokens, markers = _numeric_markers(ins.text)
        ratio = _ratio(len(markers), len(all_tokens))
        total_markers += len(markers)

        if ratio is None:
            verdict = "unmeasurable"
            unmeasurable += 1
        elif ratio >= concreteness_threshold:
            verdict = "concrete"
            concrete += 1
            measurable_ratios.append(ratio)
        else:
            verdict = "vague"
            vague += 1
            measurable_ratios.append(ratio)

        per_insight.append(
            InsightSpecificity(
                node_id=ins.node_id,
                specificity_ratio=ratio,
                verdict=verdict,
                markers=markers,
                token_count=len(all_tokens),
            )
        )

    mean_ratio = (
        sum(measurable_ratios) / len(measurable_ratios) if measurable_ratios else None
    )

    # synthesis excerpt specificity (None when withheld or absent — never fabricated)
    if artifact.synthesis_withheld or artifact.synthesis_excerpt is None:
        synthesis_marker_count: int | None = None
        synthesis_ratio: float | None = None
    else:
        synth_tokens, synth_markers = _numeric_markers(artifact.synthesis_excerpt)
        synthesis_marker_count = len(synth_markers)
        synthesis_ratio = _ratio(len(synth_markers), len(synth_tokens))

    if mean_ratio is None:
        artifact_verdict = "unknown"
    elif mean_ratio >= concreteness_threshold:
        artifact_verdict = "evidence_rich"
    elif mean_ratio >= concreteness_threshold / 2:
        artifact_verdict = "mixed"
    else:
        artifact_verdict = "qualitative"

    notes: list[str] = [
        "evidence specificity measures whether insights surface QUANTITATIVE, checkable "
        "evidence (numeric markers) or traffic in vague qualitative claims — a hand-wave "
        "('strong results') scores low; a concrete finding ('86.4% on MMLU') scores high; "
        "the operator's 'highest quality deep research' bar demands checkable evidence",
        "numeric marker = any whitespace token containing a digit (no stemming/synonymy/NER): "
        "a metaphor that feels specific but carries no digits scores low — this detector "
        "prefers flagging a metaphor (false positive) over certifying a hand-wave (false "
        "negative); a semantic specificity check can confirm downstream",
        "insights with no tokens are unmeasurable (excluded from the mean, never fabricated); "
        "the markers tuple shows exactly which tokens carry the concrete evidence",
    ]
    if mean_ratio is None:
        notes.append(
            "no measurable insights (empty artifact or all-empty text); concreteness is "
            "not measurable (defer — never fabricated)"
        )
    else:
        notes.append(
            f"mean specificity {mean_ratio:.0%}: {concrete} concrete, {vague} vague, "
            f"{unmeasurable} unmeasurable of {len(artifact.insights)} insight(s) at "
            f"threshold {concreteness_threshold:.0%} -> verdict {artifact_verdict}"
        )

    return EvidenceSpecificityReport(
        artifact_id=artifact.investigation_id,
        concrete_count=concrete,
        vague_count=vague,
        unmeasurable_count=unmeasurable,
        total_markers=total_markers,
        mean_specificity_ratio=mean_ratio,
        insight_specificities=tuple(per_insight),
        synthesis_marker_count=synthesis_marker_count,
        synthesis_specificity_ratio=synthesis_ratio,
        concreteness_threshold=concreteness_threshold,
        verdict=artifact_verdict,
        notes=tuple(notes),
        authority="advisory",
    )


__all__ = [
    "EvidenceSpecificityError",
    "EvidenceSpecificityReport",
    "InsightSpecificity",
    "measure_evidence_specificity",
]
