"""Deterministic synthesis rubric — runs after every Phase 6 exit.

Pure function over a ``SynthesizeDeliveredPayload``. No LLM calls,
no network, no I/O. The orchestrator calls this on the synthesis
that just landed and emits a ``rubric.scored`` event with the
result.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

# Substrate-wide pass threshold; documented in
# architecture_notes §3.2 and matched by
# tools/dispatch_tier_verdict/analyzer.py PASS_THRESHOLD.
PASS_THRESHOLD = 0.5

# Floor score when the synthesizer explicitly declined to produce
# a thesis (implicit_recommendation == "insufficient_evidence").
# The synthesizer correctly refusing to fabricate is a small
# positive signal — but not enough to clear PASS_THRESHOLD.
INSUFFICIENT_EVIDENCE_FLOOR = 0.10

# Weights for the composite. Sum to 1.0 by construction. Voice/style
# is weighted slightly heavier because the §5 quality bar is
# load-bearing for the product proposition (the slop test).
W_VOICE_STYLE = 0.30
W_CONVICTION = 0.25
W_CITATION_DENSITY = 0.25
W_CONSTRAINT_COMPLIANCE = 0.20


@dataclass(frozen=True)
class CompositeRubricScore:
    """The four-component breakdown the rubric emits."""

    voice_style: float
    conviction: float
    citation_density: float
    constraint_compliance: float
    composite: float
    notes: str = ""


def _voice_style_score(payload: Any) -> float:
    """Cheap deterministic voice/style score. Re-uses the existing
    heuristic from tools.prompt_autoresearch.score to avoid drift —
    both this scorer and the prompt-autoresearch runner should
    agree on what "voice/style" means."""
    # Defer the import so this module doesn't pull
    # tools.prompt_autoresearch into the orchestrator's import graph
    # at startup.
    from tools.prompt_autoresearch.score import deterministic_voice_style_score

    # Concatenate the prose fields the synthesizer produces; that's
    # the text the §5 discipline applies to.
    pieces: list[str] = []
    summary = getattr(payload, "thesis_summary", None)
    if isinstance(summary, str):
        pieces.append(summary)
    for c in getattr(payload, "thesis_components", []) or []:
        claim = getattr(c, "claim", None)
        if isinstance(claim, str):
            pieces.append(claim)
        basis = getattr(c, "confidence_basis", None)
        if isinstance(basis, str):
            pieces.append(basis)
    text = "\n".join(pieces)
    if not text:
        return 0.0
    return float(deterministic_voice_style_score(text))


def _conviction_score(payload: Any) -> float:
    """The synthesizer's own conviction_level, clamped to [0, 1].

    Returns 0.5 (neutral) when conviction is unset — the
    synthesizer hasn't committed a self-confidence number, so we
    don't penalize but also don't reward.
    """
    raw = getattr(payload, "conviction_level", None)
    if raw is None:
        return 0.5
    try:
        return max(0.0, min(1.0, float(raw)))
    except (TypeError, ValueError):
        return 0.5


def _citation_density_score(payload: Any) -> float:
    """Fraction of thesis_components that have at least one
    supporting_chunk_id. The §6 primary-source-connection
    requirement: every load-bearing claim cites chunks (or paths,
    but for the rubric we count chunks specifically — paths are
    secondary provenance per §6.1).
    """
    components = getattr(payload, "thesis_components", []) or []
    if not components:
        return 0.0
    cited = sum(
        1
        for c in components
        if (getattr(c, "supporting_chunk_ids", None) or [])
    )
    return cited / len(components)


def _constraint_compliance_score(payload: Any) -> float:
    """1.0 when the synthesizer's own constraint-compliance check
    passed; 0.0 when it failed. The synthesizer self-reports this
    via ConstraintCompliance.hard_constraints_satisfied.
    """
    compliance = getattr(payload, "constraint_compliance", None)
    if compliance is None:
        return 0.0
    satisfied = getattr(compliance, "hard_constraints_satisfied", False)
    return 1.0 if bool(satisfied) else 0.0


def score_synthesis(payload: Any) -> CompositeRubricScore:
    """Score a SynthesizeDeliveredPayload deterministically.

    Returns a CompositeRubricScore. The ``composite`` field is the
    weighted sum the orchestrator emits as the rubric's
    final_score. Sub-component scores ride along for diagnostic
    inspection.

    Special case: when ``implicit_recommendation ==
    "insufficient_evidence"``, the composite floors at
    INSUFFICIENT_EVIDENCE_FLOOR (0.10) regardless of the sub-
    component scores. The synthesizer correctly declining to
    fabricate is a positive signal, but not enough to pass the
    §14.4 0.5 gate.
    """
    voice = _voice_style_score(payload)
    conviction = _conviction_score(payload)
    citation_density = _citation_density_score(payload)
    constraint = _constraint_compliance_score(payload)

    composite = (
        W_VOICE_STYLE * voice
        + W_CONVICTION * conviction
        + W_CITATION_DENSITY * citation_density
        + W_CONSTRAINT_COMPLIANCE * constraint
    )

    notes = ""
    recommendation = getattr(payload, "implicit_recommendation", None)
    if recommendation == "insufficient_evidence":
        notes = (
            "synthesizer declined to produce a thesis "
            "(insufficient_evidence); composite floored at "
            f"{INSUFFICIENT_EVIDENCE_FLOOR}"
        )
        composite = min(composite, INSUFFICIENT_EVIDENCE_FLOOR)

    return CompositeRubricScore(
        voice_style=voice,
        conviction=conviction,
        citation_density=citation_density,
        constraint_compliance=constraint,
        composite=max(0.0, min(1.0, composite)),
        notes=notes,
    )
