"""Cross-reference polarity — do findings across artifacts conflict or align?

Operator vision (ask #1): the workstation lets the operator *"interrogate, assess,
and wrestle with the information in front of me in any given moment."* The
cross-reference discovery module (#1945) surfaces subject-overlap connections
but DELIBERATELY does not classify the polarity — *"a connection may be
agreement, disagreement, or elaboration; the operator determines the nature."*
That defer was honest for a pure subject-overlap detector. But the operator's
explicit "wrestle" verb demands MORE: when a new finding conflicts with prior
work across investigations, the platform must surface the conflict so the
operator can resolve it. As investigations accumulate, the operator cannot
manually cross-check every new finding against every prior finding for
contradictions — that is the platform's job.

THIS module classifies the polarity of cross-artifact finding connections.

**Two polarities (hard to vary).** For every subject-overlap pair (Jaccard over
distinctive terms >= floor), the module checks for ASYMMETRIC NEGATION on the
shared terms:

* ``cross_contradiction`` — at least one shared distinctive term is negated in
  one finding but asserted in the other (one says "X is not stable"; the other
  says "X is stable"). This is the high-precision conflict signal.
* ``cross_compatible`` — the shared terms have no asymmetric negation (the
  findings are on the same subject without a detectable lexical conflict). This
  does NOT claim agreement — they might corroborate, elaborate, or be neutral;
  it claims only "no conflict detected."

**Asymmetric negation (the proven heuristic).** A shared distinctive term T is
"negated" in an insight when a negation marker (not, no, never, cannot, don't,
lack, fail, …) appears within a small window (default 4 tokens) before T. The
negation is ASYMMETRIC when T is negated in one finding but not the other — that
is the contradiction signature. Symmetric negation (both negate T, or neither
does) is NOT a contradiction. This is the same high-precision low-recall
heuristic the within-artifact contradiction axis (#1943) uses, applied here to
CROSS-artifact pairs. The window is deliberately small so a distant negation
does not spuriously negate an unrelated term.

**Distinct from cross-reference discovery (#1945).** That finds subject-overlap
WITHOUT polarity (just "these connect"). This classifies the RELATIONSHIP
(contradiction vs compatible) for the same overlap pairs. A caller can use #1945
for navigation and this module for the "wrestle" surface.

**Distinct from contradiction (#1943).** That finds WITHIN-artifact conflicts
(insight X contradicts insight Y in the SAME artifact — a self-inconsistency).
This finds CROSS-artifact conflicts (a finding in artifact A contradicts a
finding in artifact B — a knowledge-base inconsistency). Different scope, both
load-bearing: #1943 catches a single investigation that is internally
incoherent; this catches investigations that disagree with each other.

**Lexical floor, not semantic (load-bearing).** Distinctive terms are content
words (grammatical glue stripped). NO stemming, NO synonymy. Negation detection
is lexical (a marker near the term), not semantic intent analysis. A paraphrased
contradiction ("the method fails" vs "the method succeeds") may be missed because
"fails" and "succeeds" are not shared terms — that is the precision/recall
tradeoff: this detector prefers false-negatives over false-positives (crying wolf
erodes trust faster than missing a paraphrase).

**Honesty rules (load-bearing):**
* An artifact never contradicts itself via this module (priors sharing the
  focus's ``investigation_id`` are skipped — within-artifact is #1943's job).
* Empty focus insights OR empty priors -> empty contradictions AND agreements.
* ``overlap_score`` is in ``[0.0, 1.0]``; ``shared_terms`` is non-empty for every
  classified pair.
* For contradictions, ``negated_terms`` lists the shared terms with asymmetric
  negation (the auditable evidence of WHY the conflict was flagged).
* Deterministic and pure: same inputs -> same report, sorted by overlap desc
  then node ids. No LLM, no network, no clock, no mutation.
* ``authority`` is always ``"advisory"``.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass

from substrate.research_artifact.schema import ResearchArtifactBody

_DEFAULT_MIN_OVERLAP: float = 0.30
_DEFAULT_NEGATION_WINDOW: int = 4

_STOP_WORDS: frozenset[str] = frozenset(
    {
        "a", "an", "the", "this", "that", "these", "those",
        "is", "are", "was", "were", "be", "been", "being", "am",
        "of", "to", "in", "on", "at", "by", "for", "with", "from",
        "into", "onto", "upon", "over", "under", "between", "through",
        "during", "before", "after", "above", "below", "up", "down",
        "out", "off", "about", "against", "as", "than", "then",
        "and", "or", "but", "nor", "so", "yet", "if", "because",
        "while", "where", "when", "how", "what", "which", "who", "whom",
        "it", "its", "they", "them", "their", "we", "us", "our",
        "you", "your", "he", "she", "his", "her", "i", "me", "my",
        "have", "has", "had", "having",
        "will", "would", "shall", "should", "can", "could", "may",
        "might", "must", "also", "very", "just",
        "only", "more", "most", "some", "any", "all", "each", "every",
        "such", "there", "here", "now",
    }
)

# Negation markers are deliberately EXCLUDED from the stop-word set so they are
# preserved in the token stream for window-based negation detection. They are
# not "distinctive terms" (they don't carry subject signal), so they are stripped
# from the distinctive-term SET but kept in the ordered token list for the
# proximity check.
_NEGATION_MARKERS: frozenset[str] = frozenset(
    {
        "not", "no", "never", "cannot", "neither", "nor", "without",
        "lack", "absent", "fail", "fails", "failed", "unable",
        "dont", "doesnt", "didnt", "wont", "wouldnt", "cant",
        "couldnt", "shouldnt", "mustnt", "isnt", "arent", "wasnt",
        "werent", "hasnt", "havent", "hadnt",
    }
)

# Terms that are neither stop-words nor negation markers carry subject signal.
_NON_DISTINCTIVE: frozenset[str] = _STOP_WORDS | _NEGATION_MARKERS

# Normalize contractions BEFORE tokenizing so negation markers survive as clean
# tokens (the [a-z0-9]+ regex would split "don't" into "don" + "t").
_CONTRACTIONS: dict[str, str] = {
    "don't": "dont",
    "doesn't": "doesnt",
    "didn't": "didnt",
    "won't": "wont",
    "wouldn't": "wouldnt",
    "can't": "cant",
    "couldn't": "couldnt",
    "shouldn't": "shouldnt",
    "mustn't": "mustnt",
    "isn't": "isnt",
    "aren't": "arent",
    "wasn't": "wasnt",
    "weren't": "werent",
    "hasn't": "hasnt",
    "haven't": "havent",
    "hadn't": "hadnt",
}

_WORD_RE = re.compile(r"[a-z0-9]+")


def _normalize(text: str) -> str:
    """Lowercase and expand contractions so negation markers are clean tokens."""
    lowered = text.lower()
    for contraction, expanded in _CONTRACTIONS.items():
        lowered = lowered.replace(contraction, expanded)
    return lowered


def _tokenize(text: str) -> list[str]:
    """Ordered token list (for proximity-based negation detection)."""
    return _WORD_RE.findall(_normalize(text))


def _distinctive_terms(text: str) -> frozenset[str]:
    """Lowercase content words (glue + negation markers stripped). Lexical floor."""
    return frozenset(
        tok for tok in _tokenize(text) if tok not in _NON_DISTINCTIVE
    )


def _jaccard(a: frozenset[str], b: frozenset[str]) -> float:
    """|A ∩ B| / |A ∪ B| in [0, 1]; 0.0 when the union is empty."""
    union = a | b
    if not union:
        return 0.0
    return len(a & b) / len(union)


def _negated_terms(
    tokens: list[str], terms: frozenset[str], window: int
) -> frozenset[str]:
    """Which of ``terms`` are preceded by a negation marker within ``window``?"""
    if not terms or not tokens:
        return frozenset()
    negated: set[str] = set()
    for i, tok in enumerate(tokens):
        if tok in terms:
            lookback = tokens[max(0, i - window) : i]
            if any(w in _NEGATION_MARKERS for w in lookback):
                negated.add(tok)
    return frozenset(negated)


class CrossPolarityError(ValueError):
    """A cross-reference polarity input violates a load-bearing invariant."""


@dataclass(frozen=True)
class CrossReferencePair:
    """A focus insight connected to a prior insight, with classified polarity."""

    focus_insight_node_id: str
    focus_insight_text: str
    prior_investigation_id: str
    prior_insight_node_id: str
    prior_insight_text: str
    shared_terms: tuple[str, ...]  # distinctive terms both share
    overlap_score: float  # Jaccard over distinctive-term sets, in [0.0, 1.0]
    polarity: str  # "cross_contradiction" | "cross_compatible"
    negated_terms: tuple[str, ...]  # shared terms with asymmetric negation (contradiction evidence)


@dataclass(frozen=True)
class PolarityReport:
    """Cross-artifact finding relationships, classified by polarity. Advisory."""

    focus_investigation_id: str
    contradictions: tuple[CrossReferencePair, ...]  # sorted: overlap desc, then ids
    compatibles: tuple[CrossReferencePair, ...]  # sorted: overlap desc, then ids
    prior_investigation_count: int  # distinct priors examined
    contradiction_prior_count: int  # distinct priors with >= 1 contradiction
    compatible_prior_count: int  # distinct priors with >= 1 compatible pair
    min_overlap: float
    negation_window: int
    authority: str = "advisory"


def classify_cross_reference_polarity(
    focus: ResearchArtifactBody,
    priors: Sequence[ResearchArtifactBody],
    *,
    min_overlap: float = _DEFAULT_MIN_OVERLAP,
    negation_window: int = _DEFAULT_NEGATION_WINDOW,
) -> PolarityReport:
    """Classify cross-artifact finding connections as contradiction or compatible.

    ``focus`` is the artifact the operator is engaging with now; ``priors`` are
    prior investigations to compare against. Returns a :class:`PolarityReport`
    with two lists: ``contradictions`` (pairs with asymmetric negation on a
    shared term) and ``compatibles`` (pairs with no detectable conflict).

    Pure: no DB, no LLM, no clock, no mutation. Priors sharing the focus's
    ``investigation_id`` are skipped; duplicate prior ids are de-duplicated.
    """
    if not 0.0 < min_overlap <= 1.0:
        raise CrossPolarityError(
            f"min_overlap must be in (0.0, 1.0], got {min_overlap!r}"
        )
    if negation_window < 1:
        raise CrossPolarityError(
            f"negation_window must be >= 1, got {negation_window!r}"
        )

    seen_ids: set[str] = set()
    distinct_priors: list[ResearchArtifactBody] = []
    for prior in priors:
        if prior.investigation_id == focus.investigation_id:
            continue
        if prior.investigation_id in seen_ids:
            continue
        seen_ids.add(prior.investigation_id)
        distinct_priors.append(prior)

    # Pre-compute distinctive-term sets AND token lists (for negation proximity).
    focus_data = [
        (ins.node_id, ins.text, _distinctive_terms(ins.text), _tokenize(ins.text))
        for ins in focus.insights
    ]
    prior_data = [
        (p.investigation_id, ins.node_id, ins.text, _distinctive_terms(ins.text), _tokenize(ins.text))
        for p in distinct_priors
        for ins in p.insights
    ]

    contradictions: list[CrossReferencePair] = []
    compatibles: list[CrossReferencePair] = []

    for f_id, f_text, f_set, f_tokens in focus_data:
        if not f_set:
            continue
        for p_inv, p_id, p_text, p_set, p_tokens in prior_data:
            if not p_set:
                continue
            score = _jaccard(f_set, p_set)
            if score < min_overlap:
                continue
            shared = f_set & p_set
            # Asymmetric negation: a shared term negated in one, not the other.
            f_neg = _negated_terms(f_tokens, shared, negation_window)
            p_neg = _negated_terms(p_tokens, shared, negation_window)
            asymmetric = (f_neg | p_neg) - (f_neg & p_neg)

            shared_sorted = tuple(sorted(shared))
            if asymmetric:
                contradictions.append(
                    CrossReferencePair(
                        focus_insight_node_id=f_id,
                        focus_insight_text=f_text,
                        prior_investigation_id=p_inv,
                        prior_insight_node_id=p_id,
                        prior_insight_text=p_text,
                        shared_terms=shared_sorted,
                        overlap_score=score,
                        polarity="cross_contradiction",
                        negated_terms=tuple(sorted(asymmetric)),
                    )
                )
            else:
                compatibles.append(
                    CrossReferencePair(
                        focus_insight_node_id=f_id,
                        focus_insight_text=f_text,
                        prior_investigation_id=p_inv,
                        prior_insight_node_id=p_id,
                        prior_insight_text=p_text,
                        shared_terms=shared_sorted,
                        overlap_score=score,
                        polarity="cross_compatible",
                        negated_terms=(),
                    )
                )

    sort_key = lambda r: (  # noqa: E731 — stable, local
        -r.overlap_score,
        r.focus_insight_node_id,
        r.prior_investigation_id,
        r.prior_insight_node_id,
    )
    contradictions.sort(key=sort_key)
    compatibles.sort(key=sort_key)

    contradiction_priors = {r.prior_investigation_id for r in contradictions}
    compatible_priors = {r.prior_investigation_id for r in compatibles}

    return PolarityReport(
        focus_investigation_id=focus.investigation_id,
        contradictions=tuple(contradictions),
        compatibles=tuple(compatibles),
        prior_investigation_count=len(distinct_priors),
        contradiction_prior_count=len(contradiction_priors),
        compatible_prior_count=len(compatible_priors),
        min_overlap=min_overlap,
        negation_window=negation_window,
    )


__all__ = [
    "CrossPolarityError",
    "CrossReferencePair",
    "PolarityReport",
    "classify_cross_reference_polarity",
]
