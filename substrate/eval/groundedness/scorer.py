"""Per-claim groundedness (faithfulness) scorer — the TRUTH axis.

The keystone distinction from the style rubric
(``substrate/synthesis_rubric/scorer.py``): that rubric measures FORM —
voice, conviction, citation *density*, constraint compliance. A fluent,
confident, densely-cited LIE scores HIGH on it. This scorer asks the
opposite question and only that question: **does the cited evidence
ENTAIL the claim?** Citation density is irrelevant here — a claim that
cites ten chunks none of which support it is NOT grounded.

Two backends, sharing one verdict shape:

1. ``lexical`` (default) — a deterministic, reproducible,
   no-network, no-cost entailment proxy. It rewards a claim whose
   content tokens are covered by (and consistent with) the union of its
   cited chunk texts, and PENALISES a claim that asserts a relation the
   evidence contradicts (a negation/antonym flip, or a numeric value the
   evidence disagrees with). Deterministic so the harness number in M3
   is reproducible and the unit fixtures are stable.

2. ``llm_judge`` — an OPTIONAL structured LLM-judge over the one
   Hermes-routed dispatch path (temperature 0, structured output). Off
   by default; NEVER exercised in tests/CI (no live paid call). It exists
   so a later sprint can A/B the cheap lexical proxy against a judge
   before any promote-to-gate flip.

A claim with NO cited chunk cannot be grounded: ``score`` floors at 0.0
and ``supported`` is False. That is the exact behaviour citation_density
gets wrong (it would happily score a zero-citation claim's *peers*).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Callable, Optional, Sequence

# Re-use the canonical verdict shape so an emitted event and an in-test
# verdict are the same object — no parallel shape to drift.
from substrate.schemas.events import ClaimGroundednessVerdict

# A claim scoring at/above this is "supported". Tuned on the M3 labeled
# set; documented + made falsifiable in PROMOTE_TO_GATE.md. The value is
# deliberately exported so the harness, the orchestrator wiring, and the
# tests all read ONE threshold (no drift).
DEFAULT_SUPPORTED_THRESHOLD: float = 0.5

DEFAULT_SCORER_ID: str = "groundedness-lexical-v1"

# Tokens that carry no truth content; ignored when measuring coverage so
# a claim isn't rewarded for sharing "the" with its evidence.
_STOPWORDS = frozenset({
    "the", "a", "an", "of", "in", "on", "for", "to", "and", "or", "is",
    "are", "be", "was", "were", "been", "being", "this", "that", "these",
    "those", "it", "its", "as", "at", "by", "with", "from", "into", "but",
    "if", "then", "than", "so", "such", "which", "who", "whom", "whose",
    "has", "have", "had", "will", "would", "can", "could", "may", "might",
    "do", "does", "did", "their", "there", "they", "them", "we", "our",
    "i", "you", "he", "she", "him", "her", "his", "also", "more", "most",
    "some", "any", "all", "both", "each", "about", "over", "under",
})

# Negation / polarity markers. A claim that asserts the OPPOSITE polarity
# of its evidence is a contradiction even when its tokens overlap heavily
# — this is what separates a faithful paraphrase from a confident
# hallucination that flips the sign.
_NEGATIONS = frozenset({
    "not", "no", "never", "none", "cannot", "can't", "won't", "don't",
    "doesn't", "didn't", "isn't", "aren't", "wasn't", "weren't", "nor",
    "without", "fails", "failed", "lacks", "absent", "denies", "denied",
})


@dataclass(frozen=True)
class GroundednessResult:
    """Synthesis-level groundedness over all claims that carry chunk
    citations. ``score`` is the mean per-claim score over
    ``scored_claims`` (claims with at least one cited chunk);
    analogy-only claims (no chunk citation) are counted in
    ``total_claims`` but excluded from the mean. An empty synthesis (no
    claims at all) scores 0.0."""

    score: float
    scored_claims: int
    total_claims: int
    backend: str
    scorer_id: str
    supported_threshold: float
    per_claim: tuple[ClaimGroundednessVerdict, ...]


def _tokens(text: str) -> list[str]:
    return [t.lower() for t in re.findall(r"[A-Za-z0-9][A-Za-z0-9\-.]*", text or "")]


def _content_tokens(text: str) -> set[str]:
    return {t for t in _tokens(text) if t not in _STOPWORDS and len(t) >= 2}


def _numbers(text: str) -> set[str]:
    """Bare numeric literals (e.g. '24', '8.5', '-35'). A claim that
    states a number the evidence never mentions is a classic
    fabricated-precision hallucination."""
    return set(re.findall(r"-?\d+(?:\.\d+)?", text or ""))


def _has_negation(tokens: Sequence[str]) -> bool:
    return any(t in _NEGATIONS for t in tokens)


def lexical_entailment_score(claim: str, chunk_texts: Sequence[str]) -> tuple[float, str]:
    """Deterministic entailment proxy. Returns (score in [0,1], rationale).

    The score is the fraction of the claim's content tokens covered by
    the union of cited-chunk content tokens (lexical entailment), then:

    - **polarity gate**: if the claim and its supporting evidence
      disagree on negation polarity, the score is halved and capped — a
      sign flip is a contradiction even with high token overlap.
    - **fabricated-number gate**: every numeric literal the claim asserts
      that appears in NO cited chunk pulls the score down (fabricated
      precision is the hallucination the truth axis must catch).

    No citations → 0.0 (a claim with no evidence cannot be grounded)."""
    chunk_blob = "\n".join(chunk_texts)
    if not chunk_texts or not chunk_blob.strip():
        return 0.0, "no cited evidence — claim cannot be grounded"

    claim_tokens = _tokens(claim)
    claim_content = _content_tokens(claim)
    if not claim_content:
        # Degenerate claim (all stopwords/empty). Can't be entailed in a
        # meaningful way; treat as ungrounded rather than vacuously 1.0.
        return 0.0, "claim has no content tokens"

    chunk_content = _content_tokens(chunk_blob)
    covered = claim_content & chunk_content
    coverage = len(covered) / len(claim_content)

    rationale_parts = [
        f"coverage={coverage:.2f} ({len(covered)}/{len(claim_content)} content tokens)"
    ]

    score = coverage

    # Polarity gate — sign flips are contradictions.
    claim_neg = _has_negation(claim_tokens)
    chunk_neg = _has_negation(_tokens(chunk_blob))
    if claim_neg != chunk_neg:
        score = min(score, 0.5) * 0.5
        rationale_parts.append(
            "polarity mismatch (negation flip) — contradiction penalty"
        )

    # Fabricated-number gate — numbers the evidence never states.
    claim_nums = _numbers(claim)
    chunk_nums = _numbers(chunk_blob)
    fabricated = claim_nums - chunk_nums
    if claim_nums:
        if fabricated:
            # Penalise proportionally to how many asserted numbers are
            # unsupported. All-fabricated numbers cap hard.
            unsupported_frac = len(fabricated) / len(claim_nums)
            score *= (1.0 - 0.8 * unsupported_frac)
            rationale_parts.append(
                f"fabricated numerals {sorted(fabricated)} not in evidence"
            )
        else:
            rationale_parts.append("all asserted numerals present in evidence")

    score = max(0.0, min(1.0, score))
    return score, "; ".join(rationale_parts)


# An entailment backend is a callable (claim, chunk_texts) -> (score, rationale).
EntailmentBackend = Callable[[str, Sequence[str]], tuple[float, str]]


def _llm_judge_backend(
    *,
    investigation_id: str,
    scorer_id: str,
    config: Any = None,
) -> EntailmentBackend:
    """Build an LLM-judge entailment backend over the ONE Hermes-routed
    dispatch path (``substrate.dispatch.router.dispatch``), temperature 0,
    structured JSON verdict. NOT §16 — it is a per-claim verifier on the
    existing dispatch path, not a second dispatcher.

    This is OFF by default and is never exercised in CI (no live paid
    call). The import is deferred so the deterministic path never pulls
    the dispatch graph."""

    import json

    from substrate.dispatch.router import dispatch  # deferred

    def _judge(claim: str, chunk_texts: Sequence[str]) -> tuple[float, str]:
        if not chunk_texts:
            return 0.0, "no cited evidence — claim cannot be grounded"
        evidence = "\n\n".join(f"[chunk {i}] {t}" for i, t in enumerate(chunk_texts))
        prompt = (
            "You are a strict groundedness judge. Decide ONLY whether the "
            "CLAIM is ENTAILED by the EVIDENCE below. Citation count is "
            "irrelevant; a claim that asserts anything the evidence does "
            "not support — a flipped sign, a fabricated number, an "
            "unstated relation — is NOT entailed.\n\n"
            f"EVIDENCE:\n{evidence}\n\n"
            f"CLAIM:\n{claim}\n\n"
            'Respond with ONLY JSON: {"score": <float 0..1>, '
            '"supported": <true|false>, "rationale": "<one sentence>"}'
        )
        result = dispatch(
            prompt,
            role="verifier",
            investigation_id=investigation_id,
            verification_required=True,
            config=config,
        )
        try:
            obj = json.loads(result.text)
            score = max(0.0, min(1.0, float(obj.get("score", 0.0))))
            rationale = str(obj.get("rationale", ""))[:280]
            return score, rationale or "llm_judge verdict"
        except (ValueError, TypeError, AttributeError) as exc:
            # A judge that returns unparseable output is itself a scorer
            # error — surface it, do not silently treat as grounded.
            raise RuntimeError(
                f"llm_judge returned unparseable verdict: {exc}"
            ) from exc

    return _judge


def score_claim(
    claim: str,
    chunk_texts: Sequence[str],
    *,
    cited_chunk_ids: Optional[Sequence[str]] = None,
    backend: EntailmentBackend = lexical_entailment_score,
    supported_threshold: float = DEFAULT_SUPPORTED_THRESHOLD,
) -> ClaimGroundednessVerdict:
    """Score ONE claim against the text of the chunk(s) it cites.

    ``chunk_texts`` is the resolved text of the EXISTING claim→chunk
    provenance (see ``provenance.resolve_claim_chunks``); this scorer
    never constructs a parallel provenance store. ``supported`` is the
    binary verdict (score ≥ threshold)."""
    score, rationale = backend(claim, chunk_texts)
    return ClaimGroundednessVerdict(
        claim=claim,
        score=score,
        supported=score >= supported_threshold,
        cited_chunk_ids=list(cited_chunk_ids or []),
        rationale=rationale,
    )


def score_synthesis_groundedness(
    claim_chunks: Sequence[tuple[str, Sequence[str], Sequence[str]]],
    *,
    backend: EntailmentBackend = lexical_entailment_score,
    backend_name: str = "lexical",
    scorer_id: str = DEFAULT_SCORER_ID,
    supported_threshold: float = DEFAULT_SUPPORTED_THRESHOLD,
) -> GroundednessResult:
    """Score a whole synthesis.

    ``claim_chunks`` is a sequence of ``(claim, cited_chunk_ids,
    chunk_texts)`` — exactly what ``provenance.resolve_synthesis_claims``
    returns from the EXISTING claim→chunk store. The synthesis score is
    the mean per-claim score over claims that carry at least one cited
    chunk; analogy-only claims (no chunk citation) are counted in
    ``total_claims`` but excluded from the mean (they are grounded
    structurally via paths, a separate axis). An empty synthesis → 0.0."""
    verdicts: list[ClaimGroundednessVerdict] = []
    scored_scores: list[float] = []
    total = 0
    for claim, chunk_ids, chunk_texts in claim_chunks:
        total += 1
        verdict = score_claim(
            claim,
            chunk_texts,
            cited_chunk_ids=chunk_ids,
            backend=backend,
            supported_threshold=supported_threshold,
        )
        verdicts.append(verdict)
        if chunk_ids:
            scored_scores.append(verdict.score)

    mean = sum(scored_scores) / len(scored_scores) if scored_scores else 0.0
    return GroundednessResult(
        score=max(0.0, min(1.0, mean)),
        scored_claims=len(scored_scores),
        total_claims=total,
        backend=backend_name,
        scorer_id=scorer_id,
        supported_threshold=supported_threshold,
        per_claim=tuple(verdicts),
    )


def make_llm_judge_backend(
    *,
    investigation_id: str,
    scorer_id: str = "groundedness-llm-judge-v1",
    config: Any = None,
) -> EntailmentBackend:
    """Public constructor for the optional LLM-judge backend. The caller
    that wants a judged score passes the returned callable as ``backend``
    to ``score_synthesis_groundedness`` (with ``backend_name="llm_judge"``).
    Off the default path; no live call until a caller opts in."""
    return _llm_judge_backend(
        investigation_id=investigation_id,
        scorer_id=scorer_id,
        config=config,
    )
