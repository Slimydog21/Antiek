r"""Collective-coherence — do N merged instances cohere into one unit, or pile?

Operator vision (ask #3): *"maybe I want to click on multiple of these sub agents
to engage in a collective deep research where I merge those instances and prompt
them as a cohesive unit; maybe even I want to merge various sub-agent deep
researches after they come to completion to create a written analysis."* The
collective merge PROMISES a cohesive unit — the operator treats the merged set as
ONE thing and prompts it as such. ``collective_coherence`` answers whether that
promise holds: do the merged instances share a common SUBJECT ANCHOR (a shared
term/thread tying them together), or are they a disjoint pile of unrelated
researches that will scatter when prompted as a unit?

**Genuinely distinct (different object + different question):**

* ``contradiction`` (#1943): do an artifact's INSIGHTS conflict? (within-artifact
  negation pairs — about CONFLICT)
* ``insight_redundancy`` (#1939): does the artifact repeat itself? (near-duplicate
  AGREEMENT within one artifact)
* ``connectedness`` (#1949): how does an artifact relate to the KNOWLEDGE BASE?
  (external cross-artifact reference-graph edges — about EXTERNAL integration)
* ``merge_integrity`` (#1962): did the RESULT preserve its PARENTS? (parent
  survival in the committed merge — about FIDELITY)
* ``draft_divergence`` (#1974): how far has the DRAFT drifted from parents?
  (pre-merge novelty — about DRIFT)
* THIS (``collective_coherence``): do the MERGED INSTANCES share a common
  subject anchor? (about COHESION — do N separate researches actually belong
  together?)

None of the above asks *"do these merged instances share a common subject?"*
Contradiction/redundancy operate WITHIN one artifact's insights;
connectedness is EXTERNAL (artifact-to-knowledge-base); merge_integrity is about
PRESERVATION; draft_divergence is about DRIFT. A merge can have ZERO
contradictions, ZERO redundancy, full parent survival, and perfect draft fidelity
— yet be INCOHERENT: three researches on unrelated topics merged into one
"cohesive unit" that has no shared subject to prompt. That gap is this axis.

**The measurement (hard to vary):**

Each instance is tokenized to its distinctive-term SET (lexical floor: stop-word +
interrogative stripped, NO stemming/synonymy — pinned). Across the N instances:

* ``total_distinct_terms`` = size of the UNION of all instance term sets (the
  collective vocabulary)
* ``shared_terms`` = the terms present in EVERY instance (the ∩-intersection
  across all N — the common subject anchor). A term shared by all instances is a
  strong cohesion signal; a term shared by some-but-not-all is weaker.
* ``core_share = |shared_terms| / |total_distinct_terms|`` in ``[0,1]`` — the
  share of the collective vocabulary that is COMMON to all instances (1.0 = every
  instance uses only shared terms — maximal cohesion; 0.0 = no term is shared by
  all — the instances share no common subject)
* ``pairwise_mean`` = the mean pairwise Jaccard similarity across all instance
  pairs (a complementary cohesion lens: the average overlap between two randomly
  chosen instances)

**Verdict:**

* ``unknown`` — fewer than two measurable instances (defer — coherence across one
  or zero instances is vacuous; never fabricated as perfectly coherent)
* ``incoherent`` — ``core_share <= incoherent_threshold`` (default ``0.05`` —
  almost no common vocabulary; the instances share no subject anchor; boundary
  inclusive)
* ``coherent`` — ``core_share >= coherent_threshold`` (default ``0.25`` — a
  strong common vocabulary; boundary inclusive)
* ``weakly_cohesive`` — between the two thresholds (partial overlap — the
  instances are related but not tightly bound)

**Honesty rules (load-bearing):**

* ``unknown`` never fabricates coherence when there are fewer than two measurable
  instances — a single instance cannot be "coherent with itself" (defer).
* ``core_share`` and ``pairwise_mean`` are ``None`` when ``unknown`` (defer, never
  ``0.0``).
* ``core_share == 0.0`` is a REAL verdict (``incoherent``): N instances with NO
  term shared by all is measured incoherence, NOT ``unknown`` (the instances were
  measured; they share nothing).
* all-glue instances (only stop-words) are excluded from the measurement (they
  contribute no distinctive terms; carried as ``unmeasurable_instance_count``).
* If ALL instances are all-glue, the measurable set is empty -> ``unknown`` (a
  collective of empty notes cannot be assessed for cohesion).
* ``total_distinct_terms == 0`` -> ``unknown`` (defer — cannot divide; never
  fabricate).
* Deterministic and pure: same inputs -> same report. No LLM, no network, no
  clock, no mutation. ``authority`` is always ``"advisory"``.

**Import-free of off-main siblings.** No merge/collective substrate is on frozen
``origin/main``; this defines its own ``CollectiveInstance`` input shape (the
route layer adapts 1:1 from the collective_graph / merge records). Pure-Python:
stdlib only.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from itertools import combinations

_DEFAULT_INCOHERENT_THRESHOLD: float = 0.05
_DEFAULT_COHERENT_THRESHOLD: float = 0.25

# Stop-words stripped before measuring (lexical floor — no stemming/synonymy).
_STOP_WORDS: frozenset[str] = frozenset(
    {
        "the", "a", "an", "and", "or", "but", "if", "then", "else", "when",
        "at", "by", "for", "with", "about", "against", "between", "into",
        "through", "during", "before", "after", "above", "below", "to", "from",
        "up", "down", "in", "out", "on", "off", "over", "under", "again",
        "further", "is", "are", "was", "were", "be", "been", "being", "am",
        "have", "has", "had", "do", "does", "did", "will", "would", "shall",
        "should", "may", "might", "must", "can", "could", "of", "as", "this",
        "that", "these", "those", "it", "its", "they", "them", "their", "we",
        "us", "our", "you", "your", "he", "she", "him", "her", "his", "hers",
        "i", "me", "my", "mine", "which", "who", "whom", "what", "where", "why",
        "how", "all", "each", "every", "both", "few", "more", "most", "other",
        "some", "such", "no", "not", "only", "own", "same", "so", "than", "too",
        "very", "just", "also", "there", "here", "now", "any", "because", "while",
    }
)

_TOKEN_RE = re.compile(r"[a-z0-9]+(?:\.[0-9]+)?%?")


@dataclass(frozen=True)
class CollectiveInstance:
    """One merged research instance's text. Pure input."""

    instance_id: str
    text: str | None


@dataclass(frozen=True)
class CollectiveCoherenceReport:
    """The collective-coherence verdict. Advisory, pure."""

    measurable_instance_count: int  # instances with >=1 distinctive term
    unmeasurable_instance_count: int  # all-glue instances excluded
    total_distinct_terms: int  # union across measurable instances
    shared_term_count: int  # terms in ALL instances (the common anchor)
    core_share: float | None  # shared/total; None when unknown
    pairwise_mean: float | None  # mean pairwise Jaccard; None when unknown
    incoherent_threshold: float
    coherent_threshold: float
    verdict: str  # unknown | incoherent | weakly_cohesive | coherent
    notes: tuple[str, ...]
    authority: str = "advisory"


class CollectiveCoherenceError(ValueError):
    """A collective-coherence input violates a load-bearing invariant."""


def measure_collective_coherence(
    instances: Sequence[CollectiveInstance],
    *,
    incoherent_threshold: float = _DEFAULT_INCOHERENT_THRESHOLD,
    coherent_threshold: float = _DEFAULT_COHERENT_THRESHOLD,
) -> CollectiveCoherenceReport:
    """Measure whether N merged instances cohere into one unit.

    ``instances`` are the merged research instances.
    ``incoherent_threshold`` is the core_share at/below which the set is
    incoherent (default 0.05).
    ``coherent_threshold`` is the core_share at/above which the set is coherent
    (default 0.25).

    Pure: no DB, no LLM, no clock, no mutation.
    """
    if not 0.0 <= incoherent_threshold <= 1.0:
        raise CollectiveCoherenceError(
            f"incoherent_threshold must be in [0,1], got {incoherent_threshold!r}"
        )
    if not 0.0 <= coherent_threshold <= 1.0:
        raise CollectiveCoherenceError(
            f"coherent_threshold must be in [0,1], got {coherent_threshold!r}"
        )
    if incoherent_threshold > coherent_threshold:
        raise CollectiveCoherenceError(
            f"incoherent_threshold ({incoherent_threshold}) cannot exceed "
            f"coherent_threshold ({coherent_threshold})"
        )

    # Validate instance ids (non-empty; duplicates ambiguous).
    seen_ids: set[str] = set()
    for inst in instances:
        if not inst.instance_id.strip():
            raise CollectiveCoherenceError(
                f"instance_id must be non-empty, got {inst.instance_id!r}"
            )
        if inst.instance_id in seen_ids:
            raise CollectiveCoherenceError(
                f"duplicate instance_id {inst.instance_id!r}"
            )
        seen_ids.add(inst.instance_id)

    # Tokenize each instance to its distinctive-term set; separate all-glue ones.
    term_sets: list[set[str]] = []
    unmeasurable = 0
    for inst in instances:
        terms = _distinctive_terms(inst.text)
        if not terms:
            unmeasurable += 1
        else:
            term_sets.append(terms)

    measurable = len(term_sets)

    # Fewer than two measurable instances -> unknown (defer — cohesion across
    # one/zero instances is vacuous; never fabricated as perfectly coherent).
    if measurable < 2:
        return _report(
            measurable, unmeasurable, 0, 0, None, None,
            incoherent_threshold, coherent_threshold, "unknown",
            [
                "collective-coherence measures whether N merged instances share a "
                "common SUBJECT anchor (do they cohere into one unit, or pile?) — "
                "distinct from contradiction #1943 (conflict), redundancy #1939 "
                "(repetition), connectedness #1949 (external reference-graph), "
                "merge_integrity #1962 (parent survival), draft_divergence #1974 "
                "(drift); THIS is about COHESION across instances",
                "verdict unknown — fewer than two measurable instances (defer; a "
                "single instance cannot be 'coherent with itself' — core_share and "
                "pairwise_mean are None, never fabricated)",
            ],
        )

    total_union: set[str] = set()
    for terms in term_sets:
        total_union |= terms
    total_distinct = len(total_union)

    # Cannot divide by zero — but measurable>=2 with non-empty sets guarantees
    # total_distinct>=1, so the guard is belt-and-suspenders honesty.
    if total_distinct == 0:
        return _report(
            measurable, unmeasurable, 0, 0, None, None,
            incoherent_threshold, coherent_threshold, "unknown",
            [
                "collective-coherence measures whether N merged instances share a "
                "common SUBJECT anchor; distinct from contradiction/redundancy/"
                "connectedness/merge_integrity/draft_divergence",
                "verdict unknown — total distinct vocabulary is 0 (defer; "
                "core_share and pairwise_mean are None, never fabricated)",
            ],
        )

    shared = set.intersection(*term_sets) if term_sets else set()
    shared_count = len(shared)
    core_share = shared_count / total_distinct

    pairwise_mean = _mean_pairwise_jaccard(term_sets)

    if core_share <= incoherent_threshold:
        verdict = "incoherent"
    elif core_share >= coherent_threshold:
        verdict = "coherent"
    else:
        verdict = "weakly_cohesive"

    notes: list[str] = [
        "collective-coherence measures whether N merged instances share a common "
        "SUBJECT anchor (do they cohere into one unit, or pile?) — distinct from "
        "contradiction #1943 (conflict), redundancy #1939 (repetition), "
        "connectedness #1949 (external reference-graph), merge_integrity #1962 "
        "(parent survival), draft_divergence #1974 (drift); THIS is about COHESION",
        "core_share = shared_terms / total_distinct_terms in [0,1] (the share of "
        "the collective vocabulary COMMON to all instances; 1.0 = every instance "
        "uses only shared terms); pairwise_mean = mean pairwise Jaccard (average "
        "overlap between two instances)",
        "verdict: incoherent (core_share <= incoherent_threshold, boundary "
        "inclusive — no common subject), coherent (>= coherent_threshold), "
        "weakly_cohesive (partial overlap)",
        "unknown when fewer than two measurable instances (defer — a single "
        "instance cannot be coherent with itself); incoherent at core_share 0.0 "
        "is a REAL measured verdict (N instances sharing no term), NOT unknown",
    ]
    notes.append(
        f"verdict {verdict}: {measurable} measurable instances, "
        f"{total_distinct} total distinct terms, {shared_count} shared across "
        f"all, core_share {core_share:.0%}, pairwise_mean {pairwise_mean:.0%}; "
        f"incoherent_threshold {incoherent_threshold:.0%}, coherent_threshold "
        f"{coherent_threshold:.0%}"
    )

    return _report(
        measurable, unmeasurable, total_distinct, shared_count,
        core_share, pairwise_mean, incoherent_threshold, coherent_threshold,
        verdict, notes,
    )


def _distinctive_terms(text: str | None) -> set[str]:
    """Lexical distinctive-term set for one instance (stop-words stripped).

    All-glue text contributes nothing (empty set). Lowercased.
    """
    if not text:
        return set()
    tokens = _TOKEN_RE.findall(text.lower())
    return {t for t in tokens if t not in _STOP_WORDS}


def _mean_pairwise_jaccard(term_sets: list[set[str]]) -> float:
    """Mean pairwise Jaccard similarity across all instance pairs.

    Jaccard(a,b) = |a ∩ b| / |a ∪ b|. Averages over all C(n,2) pairs.
    """
    if len(term_sets) < 2:
        return 0.0
    total = 0.0
    pair_count = 0
    for set_a, set_b in combinations(term_sets, 2):
        union = set_a | set_b
        if not union:
            continue  # both empty — skip (shouldn't happen post-filter)
        total += len(set_a & set_b) / len(union)
        pair_count += 1
    return total / pair_count if pair_count else 0.0


def _report(
    measurable: int,
    unmeasurable: int,
    total_distinct: int,
    shared_count: int,
    core_share: float | None,
    pairwise_mean: float | None,
    incoherent_threshold: float,
    coherent_threshold: float,
    verdict: str,
    notes: list[str],
) -> CollectiveCoherenceReport:
    return CollectiveCoherenceReport(
        measurable_instance_count=measurable,
        unmeasurable_instance_count=unmeasurable,
        total_distinct_terms=total_distinct,
        shared_term_count=shared_count,
        core_share=core_share,
        pairwise_mean=pairwise_mean,
        incoherent_threshold=incoherent_threshold,
        coherent_threshold=coherent_threshold,
        verdict=verdict,
        notes=tuple(notes),
    )
