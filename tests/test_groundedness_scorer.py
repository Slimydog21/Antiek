"""Groundedness scorer — the TRUTH axis (Foundation v2 SPR-02, M2).

Gates G3 (faithful → high) and G4 (hallucinated → low, with the
fail-before/pass-after non-vacuity check: the SAME densely-cited
hallucination scores HIGH on the style rubric's citation_density and LOW
on the entailment scorer)."""

from __future__ import annotations

from substrate.eval.groundedness import (
    DEFAULT_SUPPORTED_THRESHOLD,
    lexical_entailment_score,
    score_claim,
    score_synthesis_groundedness,
)
from substrate.eval.groundedness.scorer import GroundednessResult
from substrate.schemas.events import (
    ConstraintCompliance,
    SynthesizeDeliveredPayload,
    ThesisComponent,
)

# A chunk that genuinely supports a claim, and the faithful claim.
_CHUNK = (
    "The QuEra neutral-atom platform demonstrated single-qubit gate error "
    "rates of 8.5e-4 at the 100-qubit scale, measured via randomized "
    "benchmarking on 12 March 2025."
)
_FAITHFUL_CLAIM = (
    "The QuEra neutral-atom platform showed single-qubit gate error rates "
    "of 8.5e-4 at the 100-qubit scale."
)
# A hallucination that cites the chunk THREE times (high density) but
# flips the sign and fabricates a number — fails entailment.
_HALLUCINATED_CLAIM = (
    "The QuEra neutral-atom platform did not achieve single-qubit gate "
    "error rates, failing at 999 qubits."
)


def test_groundedness_faithful_claim_scores_high():
    """G3: a claim entailed by its cited chunk scores above threshold."""
    verdict = score_claim(_FAITHFUL_CLAIM, [_CHUNK], cited_chunk_ids=["c1"])
    assert verdict.score >= DEFAULT_SUPPORTED_THRESHOLD, verdict
    assert verdict.supported is True
    assert verdict.cited_chunk_ids == ["c1"]


def test_groundedness_hallucinated_claim_scores_low():
    """G4: a known-hallucinated, DENSELY-cited claim scores below
    threshold on the entailment scorer."""
    verdict = score_claim(
        _HALLUCINATED_CLAIM, [_CHUNK, _CHUNK, _CHUNK],
        cited_chunk_ids=["c1", "c1", "c1"],
    )
    assert verdict.score < DEFAULT_SUPPORTED_THRESHOLD, verdict
    assert verdict.supported is False


def test_groundedness_hallucinated_fail_before_pass_after():
    """G4 non-vacuity (fail-before / pass-after on the SAME fixture):

    - FAIL-BEFORE: the style rubric's citation_density proxy scores the
      densely-cited hallucination HIGH (it cites three chunks → density
      1.0). Gating density would let the lie through.
    - PASS-AFTER: the entailment scorer scores the SAME claim LOW.

    The two numbers on one fixture is the whole point of the truth axis."""
    chunk_ids = ["c1", "c1", "c1"]

    # FAIL-BEFORE — a citation_density proxy (the style rubric's axis):
    # fraction of claims with >=1 citation. The hallucination IS cited, so
    # density says 1.0 (high) — it would pass a density gate.
    density_proxy = 1.0 if chunk_ids else 0.0
    assert density_proxy >= DEFAULT_SUPPORTED_THRESHOLD  # the lie passes density

    # PASS-AFTER — the entailment scorer on the SAME densely-cited claim:
    verdict = score_claim(
        _HALLUCINATED_CLAIM, [_CHUNK, _CHUNK, _CHUNK], cited_chunk_ids=chunk_ids,
    )
    assert verdict.score < DEFAULT_SUPPORTED_THRESHOLD  # entailment catches it
    # The discriminating gap: density passes it, entailment fails it.
    assert density_proxy - verdict.score > 0.4


def test_groundedness_no_citation_floors_at_zero():
    """A claim with NO cited chunk cannot be grounded — score 0.0,
    unsupported. This is the exact behaviour citation_density gets wrong."""
    verdict = score_claim(_FAITHFUL_CLAIM, [], cited_chunk_ids=[])
    assert verdict.score == 0.0
    assert verdict.supported is False


def test_groundedness_lexical_is_deterministic():
    """Deterministic backend: same inputs → byte-identical score (the M3
    harness number must be reproducible)."""
    a = lexical_entailment_score(_FAITHFUL_CLAIM, [_CHUNK])
    b = lexical_entailment_score(_FAITHFUL_CLAIM, [_CHUNK])
    assert a == b


def _payload(components: list[ThesisComponent]) -> SynthesizeDeliveredPayload:
    return SynthesizeDeliveredPayload(
        thesis_summary="s",
        implicit_recommendation="proceed",  # type: ignore[arg-type]
        thesis_components=components,
        constraint_compliance=ConstraintCompliance(hard_constraints_satisfied=True),
        conviction_level=0.8,
    )


def test_groundedness_synthesis_level_mean_excludes_uncited():
    """Synthesis score is the mean over claims WITH chunk citations;
    analogy-only claims are counted in total but excluded from the mean."""
    comps = [
        ThesisComponent(claim=_FAITHFUL_CLAIM, confidence="high",
                        supporting_chunk_ids=["c1"]),
        # analogy-only — no chunk citation, has a path index instead
        ThesisComponent(claim="An analogy-grounded claim.", confidence="moderate",
                        supporting_path_indices=[0]),
    ]
    result: GroundednessResult = score_synthesis_groundedness(
        [
            (_FAITHFUL_CLAIM, ["c1"], [_CHUNK]),
            ("An analogy-grounded claim.", [], []),
        ],
    )
    assert result.total_claims == 2
    assert result.scored_claims == 1  # only the cited one counts in the mean
    assert result.score >= DEFAULT_SUPPORTED_THRESHOLD
    assert result.backend == "lexical"
    # sanity: the payload carries the same two-claim shape
    assert len(_payload(comps).thesis_components) == 2


def test_groundedness_empty_synthesis_scores_zero():
    result = score_synthesis_groundedness([])
    assert result.score == 0.0
    assert result.total_claims == 0
    assert result.scored_claims == 0
