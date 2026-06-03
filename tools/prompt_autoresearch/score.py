"""Composite score for prompt-autoresearch (integration_autoresearch.md §5.3).

Three of four components are deterministic. The LLM-judged rubric
carries 40% — large enough to matter, small enough that gaming it
alone can't move composite by more than 40%. Reward hacking against
deterministic components is structurally bounded.

The Lutke-gap question (§15.6): does this composite survive the
deterministic → LLM-judged transition? Wedge 1 ratification IS the
test.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# Weights per integration_autoresearch.md §5.3.
WEIGHT_RUBRIC = 0.40      # LLM-judged (the only non-deterministic component)
WEIGHT_VOICE_STYLE = 0.30  # deterministic (em-dash count, padding patterns)
WEIGHT_SECTOR_VOCAB = 0.20  # deterministic (corpus-term overlap)
WEIGHT_GROUNDING = 0.10   # deterministic (grounding preservation rate)


# Voice-style discipline patterns to suppress (master-spec §5.1).
#
# DELIBERATELY NOT unified with substrate.voice_style.constructions
# (the canonical prompt-side §5 source). The two share the §5.1 origin but
# serve different masters: that source instructs the *model* (prompt addendum
# text); this list is a *deterministic scorer* whose per-pattern -0.05 weight
# and exact membership were tuned for the §5.3 composite (em-dash + padding +
# transition penalties). The two lists already differ on purpose — this scorer
# penalizes generic transitions ("Furthermore,", "Additionally,", "In
# conclusion,") that the prompt source does not enumerate, and the prompt
# source carries enumeration tics + the "context indicates" preamble that this
# scorer intentionally does not weight. Sourcing this from the canonical list
# would change the deterministic score (start penalizing "Firstly,"/"The
# context indicates that", stop penalizing "Furthermore,") and shift the
# tuned composite — a behavior change, not a de-duplication. Left inline by
# design; see SPR-11 handoff for the steelman of both choices.
FORBIDDEN_PADDING_PATTERNS: tuple[re.Pattern, ...] = (
    re.compile(r"It is important to note that", re.IGNORECASE),
    re.compile(r"It should be observed", re.IGNORECASE),
    re.compile(r"It can be argued that", re.IGNORECASE),
    re.compile(r"It is worth noting", re.IGNORECASE),
    re.compile(r"Furthermore,", re.IGNORECASE),
    re.compile(r"Additionally,", re.IGNORECASE),
    re.compile(r"In conclusion,", re.IGNORECASE),
)

# Em-dash cap per master-spec §5.4: ≤2 per thesis. We measure
# total em-dash count and normalize per 1000 chars.
EM_DASH_RE = re.compile(r"—")


@dataclass(frozen=True)
class CompositeScore:
    rubric: float
    voice_style: float
    sector_vocab: float
    grounding: float
    total: float


def deterministic_voice_style_score(text: str) -> float:
    """Score voice/style adherence. Returns [0, 1].

    Deductions:
    - Each padding pattern occurrence: -0.05
    - Em-dashes above 2 per 1000 chars: -0.10 per excess
    """
    if not text:
        return 0.0
    score = 1.0
    for pat in FORBIDDEN_PADDING_PATTERNS:
        for _ in pat.finditer(text):
            score -= 0.05
    em_dashes = len(EM_DASH_RE.findall(text))
    chars = max(1, len(text))
    em_dash_per_1k = (em_dashes / chars) * 1000
    if em_dash_per_1k > 2.0:
        excess = em_dash_per_1k - 2.0
        score -= 0.10 * excess
    return max(0.0, score)


def sector_vocab_overlap(
    synthesis_text: str,
    corpus_terms: list[str],
) -> float:
    """Master-spec §5.4 verification: synthesis uses ≥40% of
    identifiable sector terms from corpus chunks. Returns [0, 1]
    representing the fraction of corpus_terms that appear in
    synthesis_text (case-insensitive)."""
    if not corpus_terms:
        return 1.0
    text_lower = synthesis_text.lower()
    matched = sum(1 for t in corpus_terms if t.lower() in text_lower)
    return matched / len(corpus_terms)


def grounding_preserved_rate(
    synthesis_text: str,
    expected_claim_ids: list[str],
) -> float:
    """Returns the fraction of expected claim_ids that the synthesis
    text cites inline. The substrate's synthesizer prompt explicitly
    asks for chunk-id citations; this metric verifies they survive
    a candidate prompt mutation."""
    if not expected_claim_ids:
        return 1.0
    cited = sum(1 for cid in expected_claim_ids if cid in synthesis_text)
    return cited / len(expected_claim_ids)


def composite_score(
    synthesis_text: str,
    *,
    rubric_score: float,
    corpus_terms: list[str],
    expected_claim_ids: list[str],
) -> CompositeScore:
    """Combine the four components into a single weighted score.

    Per integration_autoresearch.md §5.3: 40% LLM-judged + 60%
    deterministic (voice/style + sector-vocab + grounding). The
    deterministic floor bounds the reward-hacking surface."""
    vs = deterministic_voice_style_score(synthesis_text)
    sv = sector_vocab_overlap(synthesis_text, corpus_terms)
    gr = grounding_preserved_rate(synthesis_text, expected_claim_ids)
    total = (
        WEIGHT_RUBRIC * rubric_score
        + WEIGHT_VOICE_STYLE * vs
        + WEIGHT_SECTOR_VOCAB * sv
        + WEIGHT_GROUNDING * gr
    )
    return CompositeScore(
        rubric=rubric_score,
        voice_style=vs,
        sector_vocab=sv,
        grounding=gr,
        total=total,
    )
