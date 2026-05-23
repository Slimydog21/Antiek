"""Deterministic synthesis rubric — §14.4 wire-up via G5 follow-up."""

from __future__ import annotations

from substrate.schemas.events import (
    ConstraintCompliance,
    SynthesizeDeliveredPayload,
    ThesisComponent,
)
from substrate.synthesis_rubric import score_synthesis
from substrate.synthesis_rubric.scorer import (
    INSUFFICIENT_EVIDENCE_FLOOR,
    PASS_THRESHOLD,
)


def _ok_payload(
    *,
    recommendation: str = "proceed",
    conviction: float | None = 0.85,
    n_components: int = 3,
    n_cited: int | None = None,
    constraints_passed: bool = True,
    summary: str = "Substantive analysis. Sharp claim about radar sidelobe suppression.",
) -> SynthesizeDeliveredPayload:
    """Build a SynthesizeDeliveredPayload with realistic shape."""
    if n_cited is None:
        n_cited = n_components
    components: list[ThesisComponent] = []
    for i in range(n_components):
        components.append(
            ThesisComponent(
                claim=f"Claim {i + 1}: a load-bearing finding.",
                confidence="high",
                supporting_chunk_ids=[f"c-{i}-a", f"c-{i}-b"] if i < n_cited else [],
                supporting_path_indices=[],
                confidence_basis=None,
                effective_source_tier=2,
                hedging_required=False,
            )
        )
    return SynthesizeDeliveredPayload(
        thesis_summary=summary,
        implicit_recommendation=recommendation,  # type: ignore[arg-type]
        thesis_components=components,
        falsification_conditions=[],
        execution_risks=[],
        constraint_compliance=ConstraintCompliance(
            hard_constraints_satisfied=constraints_passed,
        ),
        reasoning_paths_used=[],
        conviction_level=conviction,
    )


def test_strong_synthesis_scores_above_threshold():
    payload = _ok_payload()
    s = score_synthesis(payload)
    assert s.composite >= PASS_THRESHOLD, s


def test_insufficient_evidence_floors_at_low_score():
    """Synthesizer explicitly declined; composite floors regardless
    of sub-component scores."""
    payload = _ok_payload(
        recommendation="insufficient_evidence",
        conviction=0.05,
    )
    s = score_synthesis(payload)
    assert s.composite <= INSUFFICIENT_EVIDENCE_FLOOR
    assert "insufficient_evidence" in s.notes


def test_zero_citation_density_drops_score():
    """A synthesis with NO chunk citations on any claim should
    fail the §6 primary-source-connection check via the rubric."""
    strong = score_synthesis(_ok_payload(n_components=3, n_cited=3))
    uncited = score_synthesis(_ok_payload(n_components=3, n_cited=0))
    assert uncited.citation_density == 0.0
    assert strong.composite > uncited.composite


def test_missing_conviction_neutral():
    """No conviction_level → neutral 0.5, neither penalty nor reward."""
    s = score_synthesis(_ok_payload(conviction=None))
    assert s.conviction == 0.5


def test_constraint_failure_subtracts_compliance_weight():
    passed = score_synthesis(_ok_payload(constraints_passed=True))
    failed = score_synthesis(_ok_payload(constraints_passed=False))
    assert passed.constraint_compliance == 1.0
    assert failed.constraint_compliance == 0.0
    assert passed.composite > failed.composite


def test_voice_style_picks_up_slop_patterns():
    """Voice/style score should penalize known LLM-slop patterns
    per §5.1 — em-dashes, padding constructions."""
    clean = score_synthesis(_ok_payload(
        summary="The radar gain is 24 dB. Sidelobe suppression is below -35 dB."
    ))
    sloppy = score_synthesis(_ok_payload(
        summary=(
            "It is important to note that — in this case — the radar "
            "gain is 24 dB — and it should be observed that sidelobe "
            "suppression is — somewhat — below -35 dB."
        )
    ))
    assert clean.voice_style >= sloppy.voice_style


def test_score_clamps_to_unit_interval():
    """Defense-in-depth: Pydantic enforces [0,1] on conviction at the
    payload boundary, but the scorer accepts duck-typed objects (e.g.
    a dict from a deserialized event) and must clamp itself."""

    class _DuckPayload:
        thesis_summary = "ok"
        implicit_recommendation = "proceed"
        thesis_components: list = []
        conviction_level = 2.5  # out-of-range; clamp expected
        constraint_compliance = None

    s = score_synthesis(_DuckPayload())
    assert 0.0 <= s.composite <= 1.0
    assert s.conviction == 1.0  # clamped


def test_empty_components_zero_citation():
    payload = _ok_payload(n_components=0)
    s = score_synthesis(payload)
    assert s.citation_density == 0.0


def test_composite_breakdown_sums_correctly():
    """Sanity: composite = weighted sum of the four sub-components
    when there's no insufficient_evidence floor."""
    from substrate.synthesis_rubric.scorer import (
        W_CITATION_DENSITY,
        W_CONSTRAINT_COMPLIANCE,
        W_CONVICTION,
        W_VOICE_STYLE,
    )

    s = score_synthesis(_ok_payload())
    expected = (
        W_VOICE_STYLE * s.voice_style
        + W_CONVICTION * s.conviction
        + W_CITATION_DENSITY * s.citation_density
        + W_CONSTRAINT_COMPLIANCE * s.constraint_compliance
    )
    assert abs(s.composite - expected) < 1e-9
