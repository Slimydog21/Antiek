"""Research-artifact insight redundancy — does the artifact repeat itself?

Operator vision (ask #7 "highest quality deep research product in the world"; the
recursive-twin / collective-merge substrate in asks #3/#4): *"...merge various
sub-agent deep researches after they come to completion... collective deep
research where I merge those instances..."* When artifacts are MERGED — the
collective synthesizer (#1835), the twin-substrate merge (#1852), the Midnight-Oil
run-findings promotion (#1899) — the result combines insights from DIFFERENT
sources. Two sources that surfaced the same claim in different wording land as two
insights that say the same thing. Exact-match dedup (the canonical
``content_hash``) misses these because the wording differs; near-duplicate
insights pollute the knowledge graph with redundant nodes and dilute every
downstream measurement that counts insights.

THIS module finds them. For every pair of insights in an artifact it computes the
Jaccard similarity over their DISTINCTIVE terms (non-stop-word, lowercased token
sets): ``|A ∩ B| / |A ∪ B|``. Pairs at/above ``threshold`` (default 0.70 — strict,
catching near-exact duplicates) are flagged. The report is the redundancy surface:
which insight pairs repeat each other, how much, and the share of insights caught
in at least one redundant pair.

**Distinct from the other quality axes.** ``citation_grounding`` (#1848) finds
fabricated citations; ``source_diversity`` (#1921) finds a monoculture of sources;
``problem_question_coverage`` (#1929) finds drift from the stated question;
``plan_resolution`` (#1937) finds unresolved sub-questions; ``goal_delivery``
(#1938 / Midnight Oil) finds unaddressed goals. NONE looks INSIDE one artifact at
whether its own insights repeat each other — the failure mode unique to MERGED
output. This does.

**Honest scope (load-bearing).** This is a LEXICAL floor, not semantic near-dup
detection — the same discipline as the other lexical axes. A paraphrase that
shares no distinctive tokens (``transformer attention`` vs ``self-attention
mechanism``) scores 0 and is NOT flagged; catching those needs an LLM judge and is
declared out of scope. NO stemming (``scale`` != ``scales``): a stemmer would
inflate similarity and flag a false near-dup, masking the real signal behind a
phony match. Stop-words are stripped from BOTH sets so grammatical glue (``the
model is``) does not inflate similarity — only signal words count.

**Honesty rules (load-bearing):**
* An artifact with fewer than two insights has ``max_similarity = None`` (never
  fabricated 0) — redundancy of a single insight is unknown, not zero.
* Two insights with no distinctive terms (empty / stop-words only) score Jaccard
  ``0.0`` — two empty insights share no SIGNAL words, so they are not reported as
  redundant (emptiness is a different quality defect, surfaced elsewhere).
* ``redundancy_ratio`` is ``redundant_insight_ids / insight_count`` (0.0 when there
  are no insights) — the share of the artifact implicated in at least one
  near-duplicate pair.
* ``max_similarity`` is reported even when below threshold (the strongest
  near-dup signal the operator has) — it is never withheld to make a clean report.
* Deterministic and pure: same artifact -> same report. No LLM, no network, no
  clock, no mutation. ``authority`` is always ``"advisory"``.
* Every pair is auditable: the two node_ids, the Jaccard similarity, and the
  shared distinctive terms are carried through.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from substrate.research_artifact.schema import ResearchArtifactBody

_TOKEN_RE = re.compile(r"[a-z0-9]+")

# Stop-words stripped so Jaccard measures signal-word overlap, not grammatical
# glue. Documented mirror of the set in goal_delivery / problem_question_coverage:
# if those change, the drift is visible (all three must agree on signal words).
_STOP_WORDS: frozenset[str] = frozenset(
    {
        "a", "an", "the", "is", "are", "was", "were", "be", "been", "being",
        "of", "to", "in", "on", "for", "with", "and", "or", "but", "not",
        "this", "that", "these", "those", "it", "its", "as", "at", "by",
        "from", "into", "than", "then", "so", "such", "do", "does", "did",
        "will", "would", "can", "could", "should", "may", "might", "must",
        "what", "which", "who", "whom", "how", "when", "where", "why",
        "about", "between", "through", "during", "above", "below", "over",
        "under", "again", "further", "there", "here", "all", "any", "both",
        "each", "few", "more", "most", "other", "some", "no", "nor", "only",
        "own", "same", "very", "just", "if", "because", "while", "until",
    }
)

_DEFAULT_THRESHOLD: float = 0.70


class RedundancyError(ValueError):
    """A redundancy-detection input violates a load-bearing invariant."""


@dataclass(frozen=True)
class RedundantPair:
    """One near-duplicate insight pair. Auditable."""

    node_id_a: str
    node_id_b: str
    similarity: float  # Jaccard in [0,1]
    shared_terms: tuple[str, ...]  # sorted distinctive terms in the intersection


@dataclass(frozen=True)
class RedundancyReport:
    """The artifact's internal-redundancy surface. Advisory, pure."""

    artifact_id: str  # the artifact's investigation_id (traceability)
    insight_count: int
    pair_count: int  # insight pairs compared (n choose 2)
    redundant_pairs: tuple[RedundantPair, ...]  # sim >= threshold, sorted desc
    redundant_insight_ids: tuple[str, ...]  # unique node_ids in ANY redundant pair
    redundancy_ratio: float  # redundant_insight_ids / insight_count; 0.0 if none
    max_similarity: float | None  # highest Jaccard over ALL pairs; None if <2 insights
    threshold: float
    notes: tuple[str, ...]
    authority: str = "advisory"


def _tokenize(text: str) -> list[str]:
    return _TOKEN_RE.findall(text.lower())


def _distinctive_terms(text: str) -> set[str]:
    return {tok for tok in _tokenize(text) if tok not in _STOP_WORDS}


def _jaccard(a: set[str], b: set[str]) -> float:
    """Jaccard over two distinctive-term sets. 0.0 if both empty (no shared signal)."""
    if not a and not b:
        return 0.0
    intersection = len(a & b)
    union = len(a | b)
    return intersection / union


def detect_redundancy(
    artifact: ResearchArtifactBody,
    *,
    threshold: float = _DEFAULT_THRESHOLD,
) -> RedundancyReport:
    """Measure how much an artifact's insights repeat each other.

    ``artifact`` is the canonical knowledge-asset body (insights + open
    questions). ``threshold`` is the Jaccard at/above which a pair is flagged
    (default 0.70 — strict, catching near-exact duplicates; lower to catch more at
    the cost of false positives). Returns a :class:`RedundancyReport`.

    Pure: no DB, no LLM, no clock, no mutation.
    """
    if not 0.0 < threshold <= 1.0:
        raise RedundancyError(
            f"threshold must be in (0.0, 1.0], got {threshold!r}"
        )

    insights = artifact.insights
    n = len(insights)
    pair_count = n * (n - 1) // 2

    term_sets = [_distinctive_terms(ins.text) for ins in insights]

    redundant: list[RedundantPair] = []
    best: float | None = None
    for i in range(n):
        for j in range(i + 1, n):
            sim = _jaccard(term_sets[i], term_sets[j])
            if best is None or sim > best:
                best = sim
            if sim >= threshold:
                shared = tuple(sorted(term_sets[i] & term_sets[j]))
                redundant.append(
                    RedundantPair(
                        node_id_a=insights[i].node_id,
                        node_id_b=insights[j].node_id,
                        similarity=sim,
                        shared_terms=shared,
                    )
                )

    redundant.sort(key=lambda p: (-p.similarity, p.node_id_a, p.node_id_b))
    redundant_pairs = tuple(redundant)

    redundant_ids = sorted(
        {pid for pair in redundant_pairs for pid in (pair.node_id_a, pair.node_id_b)}
    )
    redundancy_ratio = (len(redundant_ids) / n) if n else 0.0

    notes: list[str] = [
        "redundancy detection is a LEXICAL floor (Jaccard over distinctive "
        "terms); paraphrases with no shared tokens score 0 and are not flagged; "
        "semantic near-duplicate detection is an LLM-judge concern, out of scope",
    ]
    if n < 2:
        notes.append(
            f"only {n} insight(s); internal redundancy is not measurable "
            "(needs at least two insights to compare)"
        )
    else:
        notes.append(
            f"compared {pair_count} insight pair(s) at threshold {threshold:.2f}; "
            f"{len(redundant_pairs)} redundant pair(s) implicating "
            f"{len(redundant_ids)} of {n} insight(s) "
            f"(redundancy ratio {redundancy_ratio:.0%})"
        )
        if best is not None:
            tag = " (below threshold)" if best < threshold else " (at/above threshold)"
            notes.append(f"highest pair similarity was {best:.2f}{tag}")

    return RedundancyReport(
        artifact_id=artifact.investigation_id,
        insight_count=n,
        pair_count=pair_count,
        redundant_pairs=redundant_pairs,
        redundant_insight_ids=tuple(redundant_ids),
        redundancy_ratio=redundancy_ratio,
        max_similarity=best,
        threshold=threshold,
        notes=tuple(notes),
    )


__all__ = [
    "RedundancyError",
    "RedundantPair",
    "RedundancyReport",
    "detect_redundancy",
]
