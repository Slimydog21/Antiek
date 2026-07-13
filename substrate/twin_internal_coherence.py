r"""Twin internal coherence — do a twin's insights connect to each other?

Operator vision (ask #4): *"...the recursive note taker where every information
asset created on my platform has a twin document with all the insights and
questions proposed by that information document written by an LLM..."* The twin
is the distilled note-taking layer. Four twin axes already exist:
``twin_fidelity`` (#1954, does the twin HALLUCINATE — external truth grounding),
``twin_coverage`` (#1964, does the twin CAPTURE the source — external recall),
``twin_question_support`` (#1959, are the twin's questions GROUNDED — external
grounding), and ``twin_staleness`` (#1975, is the twin OUT OF DATE — temporal
grounding). ALL FOUR measure the twin against an EXTERNAL reference (the source,
the truth, the time). NONE measures the twin's INTERNAL structural coherence —
do its insights CONNECT to each other (a coherent narrative) or are they a
DISCONNECTED list of islands (the note-taker jotted unrelated facts)?

**Genuinely distinct (external vs internal):**

* ``twin_fidelity`` (#1954): twin vs TRUTH (every insight traceable/grounded — no
  fabrication). EXTERNAL.
* ``twin_coverage`` (#1954): twin vs SOURCE (did the twin capture the source's
  content — recall). EXTERNAL.
* ``twin_question_support`` (#1959): twin's questions vs SOURCE (are the questions
  grounded in source content). EXTERNAL.
* ``twin_staleness`` (#1975): twin vs SOURCE VERSION (temporal — out of date).
  EXTERNAL/TEMPORAL.
* THIS (``twin_internal_coherence``): twin vs ITSELF (do the insights share a
  subject thread — is there a connective tissue among them?). INTERNAL.

They are independent. A twin can be perfectly faithful (every insight grounded in
the source, #1954 high), fully cover the source (#1964 high), ask grounded
questions (#1959 high), and be temporally fresh (#1975 high) — yet be INTERNALLY
incoherent: ten insights that are each individually correct but share no subject
thread (a list of unrelated facts: "the GPU has 80GB", "the CEO was appointed in
2019", "the dataset has 2M rows" — each grounded, collectively an archipelago of
islands with no narrative). Internal coherence is the connective-tissue signal
that makes a twin a coherent *document* rather than a bullet list. The recursive
note-taker's value proposition is a distilled, navigable narrative; incoherence
defeats that.

**The measurement (hard to vary).** Given a twin's insights (each a short text):
build the pairwise subject-overlap graph. Two insights CONNECT when they share at
least ``min_overlap`` distinctive terms (stop-word-stripped, NO stemming/
synonymy — the lexical floor pinned across all text axes; ``min_overlap`` default
``1``). A twin is coherent when its insights form a connected graph (any insight
reachable from any other through a chain of subject-sharing edges), not when every
pair directly overlaps (that would be redundancy #1939, the opposite failure).

* ``insight_count`` — measurable insights (after all-glue exclusion).
* ``connected_pairs`` — insight pairs sharing >= min_overlap distinctive terms
  (auditable: both node_ids + sorted shared terms).
* ``edge_count`` — len(connected_pairs).
* ``connected_component_count`` — the number of disconnected subject-islands
  (computed via union-find on the overlap graph).
* ``coherence_ratio = connected_pairs / possible_pairs`` — the density of the
  overlap graph (0.0 = no two insights share a subject; approaching 1.0 = every
  pair overlaps — high coherence but trending toward redundancy).
* ``max_component_size`` — the largest subject-island (how many insights are in
  the single biggest connected thread).

**Verdict (distinct honest states, never collapsed):**

* ``insight_count < 2`` -> ``unknown`` (defer — a single insight cannot be
  internally coherent or incoherent; never fabricated).
* ``connected_component_count == 1`` -> ``coherent`` (the insights form ONE
  connected subject graph — any insight reachable from any other through shared
  threads; a navigable narrative).
* ``connected_component_count == insight_count`` -> ``fragmented`` (every insight
  is its own island — zero shared threads; a pure list of unrelated facts; the
  archipelago failure mode).
* otherwise -> ``partially_connected`` (multiple islands but at least some
  insights connect — the common middle ground).

**Honesty rules (load-bearing):**

* ``unknown`` never fabricates on fewer than two insights.
* ``coherence_ratio`` / ``max_component_size`` / counts are ``None`` when
  ``unknown`` (defer — never ``0.0``).
* ``coherent`` is a REAL measured verdict (the graph is connected), NOT the
  default: ``unknown`` means too-few-to-measure; ``coherent`` means
  measured-and-connected. Never collapsed.
* ``fragmented`` never collapses with ``unknown``: too-few = unknown; enough-but-
  disconnected = fragmented.
* all-glue insights (only stop-words) are EXCLUDED (carried as
  ``unmeasurable_count``) — they share nothing distinctive, so they cannot connect
  by this measure; fabricating a connection would be dishonest.
* Distinct from insight_redundancy #1939 (near-duplicate AGREEMENT — too MUCH
  overlap): THIS measures connectivity (enough overlap to form a narrative thread),
  the opposite concern. A coherent twin is NOT a redundant one — coherence needs a
  CHAIN of partial overlaps, not full duplication.
* Deterministic and pure: same inputs -> same report. No LLM, no network, no
  clock, no mutation.
* ``authority`` is always ``"advisory"``.

**Import-free of off-main siblings.** Defines its own ``TwinInsightText`` input
shape (the route layer adapts 1:1 from the twin's insight list). Pure-Python:
stdlib only.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass

_DEFAULT_MIN_OVERLAP: int = 1

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
class TwinInsightText:
    """One twin insight's text. Pure input."""

    insight_id: str
    text: str | None


@dataclass(frozen=True)
class ConnectedInsightPair:
    """One subject-sharing insight pair. Auditable."""

    insight_a_id: str
    insight_b_id: str
    shared_terms: tuple[str, ...]  # sorted distinctive terms in both


@dataclass(frozen=True)
class TwinInternalCoherenceReport:
    """The twin's internal structural coherence verdict. Advisory, pure."""

    insight_count: int
    unmeasurable_count: int
    connected_pairs: tuple[ConnectedInsightPair, ...]
    edge_count: int
    connected_component_count: int | None  # subject-islands; None when unknown
    coherence_ratio: float | None  # edges / possible_pairs; None when unknown
    max_component_size: int | None  # largest island; None when unknown
    min_overlap: int
    verdict: str  # coherent | partially_connected | fragmented | unknown
    notes: tuple[str, ...]
    authority: str = "advisory"


def _distinctive_terms(text: str | None) -> frozenset[str]:
    if text is None:
        return frozenset()
    tokens = _TOKEN_RE.findall(text.lower())
    return frozenset(t for t in tokens if t not in _STOP_WORDS)


def measure_twin_internal_coherence(
    insights: Sequence[TwinInsightText],
    *,
    min_overlap: int = _DEFAULT_MIN_OVERLAP,
) -> TwinInternalCoherenceReport:
    r"""Measure the internal structural coherence of a twin's insights.

    ``insights`` is a sequence of :class:`TwinInsightText`. Two insights connect
    when they share at least ``min_overlap`` distinctive terms (stop-word-stripped).
    Returns a :class:`TwinInternalCoherenceReport` with the connectivity graph,
    component count, and verdict.

    Raises:
        ValueError: if ``min_overlap`` is not positive.
    """
    if min_overlap < 1:
        raise ValueError(f"min_overlap must be positive; got {min_overlap}")

    # Compute distinctive term sets; exclude all-glue insights.
    term_sets: dict[str, frozenset[str]] = {}
    unmeasurable = 0
    for ins in insights:
        terms = _distinctive_terms(ins.text)
        if not terms:
            unmeasurable += 1
        else:
            term_sets[ins.insight_id] = terms

    ids = sorted(term_sets)
    n = len(ids)

    if n < 2:
        return TwinInternalCoherenceReport(
            insight_count=n,
            unmeasurable_count=unmeasurable,
            connected_pairs=(),
            edge_count=0,
            connected_component_count=None,
            coherence_ratio=None,
            max_component_size=None,
            min_overlap=min_overlap,
            verdict="unknown",
            notes=("fewer than two measurable insights",),
        )

    connected_pairs: list[ConnectedInsightPair] = []
    # Union-find for connected components.
    parent: dict[str, str] = {i: i for i in ids}

    def find(x: str) -> str:
        root = x
        while parent[root] != root:
            root = parent[root]
        while parent[x] != root:
            parent[x], x = root, parent[x]
        return root

    def union(a: str, b: str) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb

    for i in range(n):
        for j in range(i + 1, n):
            a_id, b_id = ids[i], ids[j]
            shared = term_sets[a_id] & term_sets[b_id]
            if len(shared) >= min_overlap:
                connected_pairs.append(
                    ConnectedInsightPair(
                        insight_a_id=a_id,
                        insight_b_id=b_id,
                        shared_terms=tuple(sorted(shared)),
                    )
                )
                union(a_id, b_id)

    # Count connected components and their sizes.
    comp_sizes: dict[str, int] = {}
    for node_id in ids:
        root = find(node_id)
        comp_sizes[root] = comp_sizes.get(root, 0) + 1

    component_count = len(comp_sizes)
    max_component_size = max(comp_sizes.values())
    possible_pairs = n * (n - 1) // 2
    coherence_ratio = len(connected_pairs) / possible_pairs

    connected_pairs.sort(key=lambda p: (p.insight_a_id, p.insight_b_id))

    if component_count == 1:
        verdict = "coherent"
    elif component_count == n:
        verdict = "fragmented"
    else:
        verdict = "partially_connected"

    notes = (
        f"{component_count} connected component(s) over {n} insight(s); "
        f"{len(connected_pairs)} edge(s), max component {max_component_size}",
    )

    return TwinInternalCoherenceReport(
        insight_count=n,
        unmeasurable_count=unmeasurable,
        connected_pairs=tuple(connected_pairs),
        edge_count=len(connected_pairs),
        connected_component_count=component_count,
        coherence_ratio=coherence_ratio,
        max_component_size=max_component_size,
        min_overlap=min_overlap,
        verdict=verdict,
        notes=notes,
    )
