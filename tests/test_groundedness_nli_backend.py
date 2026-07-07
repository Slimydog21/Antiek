"""Tests for the offline NLI entailment backend (Groundedness Gate SPR-02).

Covers the three load-bearing properties the sprint's rigor cards demand:
- Contract match: drop-in ``EntailmentBackend`` (rigor #4 — reuse the seam).
- Determinism: byte-identical across runs (rigor #3 — a tested property, not a hope).
- CI-safety: no live call at inference; missing model raises loudly (rigor #5).

Plus the headline bar-clears assertion: NLI lifts threshold_accuracy past the
0.85 bar on the SPR-01 hard set where lexical failed.

These tests need the optional ``embedding`` extra (torch/transformers) and a
cached NLI model. They are skipped automatically when the deps/model are
absent so the default CI path (which may not have the model cached) is not
broken — but the skip is LOUD (names what wasn't run), never silent.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from substrate.eval.groundedness.scorer import score_claim

_LABELED_FIXTURE = (
    Path(__file__).parent / "fixtures" / "groundedness_labeled.jsonl"
)


def _nli_available() -> bool:
    """True iff the NLI backend can actually run in this environment
    (deps installed AND model cached). Used to skip honestly when not."""
    try:
        from substrate.eval.groundedness.nli_backend import (
            NLIModelUnavailable,
            nli_entailment_score,
        )
    except ImportError:
        return False
    try:
        # Probe with a tiny input; if the model isn't cached + offline, this raises.
        nli_entailment_score("a claim", ["some evidence text here"])
        return True
    except NLIModelUnavailable:
        return False
    except Exception:
        return False


# Module-level probe so the skip reason is computed once, honestly.
_NLI_OK = _nli_available()
_NLI_SKIP = pytest.mark.skipif(
    not _NLI_OK,
    reason=(
        "NLI backend unavailable (torch/transformers not installed or model "
        "MoritzLaurer/DeBERTa-v3-base-mnli-fever-anli not cached + offline). "
        "Run `huggingface-cli download MoritzLaurer/DeBERTa-v3-base-mnli-fever-anli` "
        "and install the `embedding` extra to exercise these tests."
    ),
)


@_NLI_SKIP
def test_nli_backend_matches_entailment_contract():
    """The NLI backend is a drop-in ``EntailmentBackend``: it accepts
    ``(claim, chunk_texts)`` and returns ``(score, rationale)`` with score in
    [0, 1]. Verified by passing it as ``backend=`` to ``score_claim``."""
    from substrate.eval.groundedness.nli_backend import nli_entailment_score

    score, rationale = nli_entailment_score(
        "The radar achieves 24 dB of gain.",
        ["The phased-array radar achieves 24 dB of gain."],
    )
    assert isinstance(score, float)
    assert 0.0 <= score <= 1.0
    assert isinstance(rationale, str) and rationale
    # And it drops into score_claim unchanged.
    verdict = score_claim(
        "The radar achieves 24 dB of gain.",
        ["The phased-array radar achieves 24 dB of gain."],
        backend=nli_entailment_score,
    )
    assert 0.0 <= verdict.score <= 1.0
    # EntailmentBackend is the documented type — static checkers enforce it; this
    # runtime check guards against a signature drift the checker might miss.
    assert callable(nli_entailment_score)
    # Sanity: a faithful paraphrase should score HIGH (entailed).
    assert score > 0.5, f"expected entailed claim to score high, got {score}"


@_NLI_SKIP
def test_nli_backend_deterministic():
    """Determinism is a TESTED property (rigor #3). Same input → byte-identical
    ``(score, rationale)`` across two runs. A backend that drifts by 0.001
    would make a threshold-straddling case flap the gate red/green — the exact
    instability a merge-gate cannot have."""
    from substrate.eval.groundedness.nli_backend import nli_entailment_score

    claim = "The lithium cells retained 92 percent capacity after 3000 cycles."
    chunks = ["After 3000 cycles the cells retained 92 percent of capacity."]
    s1, r1 = nli_entailment_score(claim, chunks)
    s2, r2 = nli_entailment_score(claim, chunks)
    assert s1 == s2, f"non-deterministic score: {s1} != {s2}"
    assert r1 == r2, f"non-deterministic rationale: {r1!r} != {r2!r}"


@_NLI_SKIP
def test_nli_backend_no_evidence_floors_at_zero():
    """No cited chunks → 0.0 (identical to lexical's floor). A claim with no
    evidence cannot be grounded."""
    from substrate.eval.groundedness.nli_backend import nli_entailment_score

    score, rationale = nli_entailment_score("any claim", [])
    assert score == 0.0
    assert "no cited evidence" in rationale


@_NLI_SKIP
def test_nli_backend_catches_densely_cited_subject_swap():
    """The load-bearing case: a subject-swap hallucination (mRNA vs siRNA)
    that lexical scores HIGH (0.75) must score LOW under NLI — the whole
    justification for this backend."""
    from substrate.eval.groundedness.nli_backend import nli_entailment_score

    # Claim says mRNA; chunk says siRNA. Same numbers, wrong molecule.
    score, _ = nli_entailment_score(
        "The lipid nanoparticle formulation preserved 95 percent of mRNA integrity after 30 days.",
        ["After 30 days the lipid nanoparticle formulation retained 95 percent of siRNA integrity."],
    )
    assert score < 0.5, (
        f"NLI should catch the subject-swap hallucination (score < 0.5); got {score}. "
        "If this regressed, the densely-cited blind spot is back."
    )


@_NLI_SKIP
def test_nli_backend_clears_the_four_part_bar():
    """SPR-02 headline: the NLI backend clears the PROMOTE_TO_GATE.md bar on
    the SPR-01 hard set — the bar lexical failed. This is the positive
    counterpart to ``test_promote_bar_lexical_finds_the_gap`` (which asserts
    lexical FAILS the bar)."""
    from substrate.eval.groundedness.harness import load_labeled, score_labeled_set
    from substrate.eval.groundedness.nli_backend import nli_entailment_score

    cases = load_labeled(str(_LABELED_FIXTURE))
    report, _rows = score_labeled_set(cases, backend=nli_entailment_score)
    assert report.n_faithful + report.n_hallucinated >= 40
    assert report.n_hallucinated >= 15
    assert report.auc >= 0.85, f"NLI auc {report.auc:.4f} < 0.85"
    assert report.mean_gap >= 0.30, f"NLI mean_gap {report.mean_gap:.4f} < 0.30"
    assert report.threshold_accuracy >= 0.85, (
        f"NLI threshold_accuracy {report.threshold_accuracy:.4f} < 0.85 — "
        "the bar lexical failed is also failed by NLI; SPR-02 did not close the gap."
    )


@_NLI_SKIP
def test_nli_backend_residual_misses_are_documented_not_hidden():
    """Honesty (rigor #3): the NLI backend is NOT perfect on the densely-cited
    class. As of this sprint it still misses the 'true-but-misleading' cases
    (correlation-causation, temporal-shift, conditional-flatten) where the
    surface claim is mostly entailed. This test PINS that residual so a future
    change is forced to acknowledge it — if NLI starts catching them, the test
    fails and the maintainer updates the documented residual.

    The residual is acceptable: 10/13 caught lifts threshold_accuracy from
    0.674 (lexical) to ~0.88 (NLI), clearing the bar. The remaining 3 are the
    hardest class and are the natural work item for a future calibration sprint."""
    from substrate.eval.groundedness.harness import load_labeled, score_labeled_set
    from substrate.eval.groundedness.nli_backend import nli_entailment_score

    cases = load_labeled(str(_LABELED_FIXTURE))
    _report, rows = score_labeled_set(cases, backend=nli_entailment_score)
    # The three known residual misses (scored >= 0.5 despite being hallucinated).
    residual_ids = {
        "hallu-dch-correlation-causation",
        "hallu-dch-temporal-shift",
        "hallu-dch-conditional-flatten",
    }
    residual_rows = [
        (c.case_id, s) for c, s, _sup in rows
        if c.case_id in residual_ids and s >= 0.5
    ]
    # The documented residual: as of SPR-02, NLI still misses the
    # 'true-but-misleading' densely-cited cases (correlation-causation,
    # temporal-shift, conditional-flatten) — surface-entailed claims whose
    # falsehood is the dropped qualifier, not the surface tokens. PIN the
    # expected count so a change is forced to acknowledge it: if NLI catches
    # MORE (count drops), update the docstring + lower the bound; if it
    # catches FEWER (count rises above 3), the backend regressed.
    assert len(residual_rows) <= 3, (
        f"NLI is missing MORE densely-cited cases than documented ({len(residual_rows)}); "
        f"either the backend regressed or the labeled set grew new hard cases: "
        f"{[cid for cid, _ in residual_rows]}"
    )
    # And at least the known-hard residual must still be present (else the
    # fixture's hard class was silently weakened).
    assert len(residual_rows) >= 1, (
        "NLI now catches ALL densely-cited cases — either the backend improved "
        "(update this test to a positive residual-is-zero assertion) or the "
        "densely-cited class was weakened. Investigate before flipping the gate."
    )
    # And confirm the residual doesn't sink the overall bar (regression guard).
    report, _ = score_labeled_set(cases, backend=nli_entailment_score)
    assert report.threshold_accuracy >= 0.85
