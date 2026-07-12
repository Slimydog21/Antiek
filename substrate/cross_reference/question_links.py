"""Question cross-links — clustering related open questions across investigations.

Operator vision (ask #4): the workstation records *"valuable data, insights, and
questions recursively that informs all prompts."* Open questions are the
RECURSION engine — each one seeds the next investigation. As investigations
accumulate, the operator accumulates a growing set of open questions across the
knowledge base. Two high-value signals emerge from that set:

1. **Recurring unknowns** — the same question phrased differently across multiple
   investigations signals a hard, persistent problem worth prioritizing.
2. **Question clusters** — groups of related open questions that, taken together,
   define a research THEME the operator should tackle as a unit.

Without cross-linking, open questions are a flat list. With it, the operator sees
*"you've asked about model hallucination in 3 investigations — this is a
recurring unknown"* and *"these 4 questions all cluster around retrieval
latency — that's a theme."* This is the question↔question edge that completes the
reference graph (insight↔insight #1945, insight→question #1946, question↔question
THIS).

**Distinct from resolution-candidate discovery (#1946).** That connects insights
to questions (a finding may RESOLVE a question). This connects questions to
questions (two questions are ABOUT the same thing). Different endpoints, different
value — #1946 is the resolution signal; this is the clustering/recurring signal.

**Distinct from cross-reference discovery (#1945).** That finds insight↔insight
subject similarity (findings connect to findings). This finds question↔question
subject similarity (questions connect to questions).

**The link (hard to vary).** Two open questions cross-link when they share
DISTINCTIVE subject terms above a floor. ``overlap_score`` is the Jaccard index
over the two questions' distinctive-term sets. ``1.0`` = identical subject
vocabulary (likely the same question re-asked); ``0.0`` = no shared distinctive
terms. A link requires ``overlap_score >= min_overlap`` (default ``0.30``).

**Cluster detection.** Beyond pairwise links, the module identifies CLUSTERS —
sets of questions connected by links (transitive closure over the link graph).
A cluster of 3+ questions defines a research theme. A pair (cluster of 2) is a
recurring unknown. Isolated questions are singletons.

**Lexical floor, not semantic (load-bearing).** Distinctive terms are content
words (grammatical glue + interrogatives stripped). NO stemming, NO synonymy.
Interrogative words (what, how, why, when, where, which, who) are stop-words so
they never inflate question-question similarity — two questions starting with
"how does…" do NOT link unless they share CONTENT terms.

**Honest scope (load-bearing).** This is a STRUCTURAL subject-overlap detector.
It does NOT assert that linked questions are semantically identical (paraphrases
may be missed) or that a cluster is a coherent research theme (the operator
confirms). It surfaces the CONNECTION and the CLUSTERING with auditable evidence.

**Honesty rules (load-bearing):**
* A question never links to itself (same node_id skipped).
* Questions within the SAME artifact ARE eligible (an artifact can have related
  open questions — e.g., three sub-questions about the same topic). This is
  distinct from insight↔insight (#1945) which skips self-artifact; questions are
  inherently cross-cutting.
* Empty question sets -> empty links and no clusters.
* ``overlap_score`` is in ``[0.0, 1.0]``; ``shared_terms`` is non-empty for every
  link.
* Deterministic and pure: same inputs -> same report. No LLM, no network, no
  clock, no mutation.
* ``authority`` is always ``"advisory"``.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass

from substrate.research_artifact.schema import ResearchArtifactBody

_DEFAULT_MIN_OVERLAP: float = 0.30

_STOP_WORDS: frozenset[str] = frozenset(
    {
        "a", "an", "the", "this", "that", "these", "those",
        "is", "are", "was", "were", "be", "been", "being", "am",
        "of", "to", "in", "on", "at", "by", "for", "with", "from",
        "into", "onto", "upon", "over", "under", "between", "through",
        "during", "before", "after", "above", "below", "up", "down",
        "out", "off", "about", "against", "as", "than", "then",
        "and", "or", "but", "nor", "so", "yet", "if", "because",
        # Interrogatives — stripped so "how does…" never inflates question overlap.
        "while", "where", "when", "how", "what", "which", "who", "whom",
        "why", "whose",
        "it", "its", "they", "them", "their", "we", "us", "our",
        "you", "your", "he", "she", "his", "her", "i", "me", "my",
        "do", "does", "did", "doing", "have", "has", "had", "having",
        "will", "would", "shall", "should", "can", "could", "may",
        "might", "must", "not", "no", "yes", "also", "very", "just",
        "only", "more", "most", "some", "any", "all", "each", "every",
        "such", "there", "here", "now",
    }
)

_WORD_RE = re.compile(r"[a-z0-9]+")


def _distinctive_terms(text: str) -> frozenset[str]:
    """Lowercase content words (glue + interrogatives stripped). Lexical floor."""
    return frozenset(
        tok for tok in _WORD_RE.findall(text.lower()) if tok not in _STOP_WORDS
    )


def _jaccard(a: frozenset[str], b: frozenset[str]) -> float:
    """|A ∩ B| / |A ∪ B| in [0, 1]; 0.0 when the union is empty."""
    union = a | b
    if not union:
        return 0.0
    return len(a & b) / len(union)


class QuestionLinkError(ValueError):
    """A question-link input violates a load-bearing invariant."""


@dataclass(frozen=True)
class QuestionLink:
    """Two open questions connected by shared subject matter."""

    question_a_investigation_id: str
    question_a_node_id: str
    question_a_text: str
    question_b_investigation_id: str
    question_b_node_id: str
    question_b_text: str
    shared_terms: tuple[str, ...]  # distinctive terms both share (auditable)
    overlap_score: float  # Jaccard over distinctive-term sets, in [0.0, 1.0]


@dataclass(frozen=True)
class QuestionCluster:
    """A set of questions linked by shared subject (a research theme or recurring
    unknown). Built via transitive closure over the link graph."""

    question_node_ids: tuple[str, ...]  # sorted for determinism
    size: int  # len(question_node_ids)
    investigation_ids: tuple[str, ...]  # distinct investigations in the cluster


@dataclass(frozen=True)
class QuestionLinkReport:
    """Cross-artifact question links and clusters. Advisory, pure."""

    links: tuple[QuestionLink, ...]  # sorted: overlap desc, then node ids
    clusters: tuple[QuestionCluster, ...]  # sorted: size desc, then node ids
    total_questions: int  # total questions across all artifacts
    linked_question_count: int  # questions that appear in >= 1 link
    singleton_count: int  # questions not in any link
    min_overlap: float
    authority: str = "advisory"


def discover_question_links(
    artifacts: Sequence[ResearchArtifactBody],
    *,
    min_overlap: float = _DEFAULT_MIN_OVERLAP,
) -> QuestionLinkReport:
    """Discover subject-overlap links between open questions across artifacts.

    ``artifacts`` are the investigations whose open questions to cross-link.
    Returns a :class:`QuestionLinkReport` with pairwise links and transitive-
    closure clusters. A cluster of 1 is a singleton (isolated question); 2 is a
    recurring pair; 3+ is a research theme.

    Pure: no DB, no LLM, no clock, no mutation. Questions are eligible across
    artifacts AND within the same artifact (questions are inherently cross-
    cutting).
    """
    if not 0.0 < min_overlap <= 1.0:
        raise QuestionLinkError(
            f"min_overlap must be in (0.0, 1.0], got {min_overlap!r}"
        )

    # Flatten all questions with provenance + pre-computed term sets.
    questions: list[tuple[str, str, str, frozenset[str]]] = [
        (art.investigation_id, q.node_id, q.text, _distinctive_terms(q.text))
        for art in artifacts
        for q in art.open_questions
    ]

    links: list[QuestionLink] = []
    for i, (inv_a, id_a, text_a, terms_a) in enumerate(questions):
        if not terms_a:
            continue
        for j in range(i + 1, len(questions)):
            inv_b, id_b, text_b, terms_b = questions[j]
            if not terms_b:
                continue
            if id_a == id_b:
                continue  # never link a question to itself
            score = _jaccard(terms_a, terms_b)
            if score >= min_overlap:
                shared = tuple(sorted(terms_a & terms_b))
                links.append(
                    QuestionLink(
                        question_a_investigation_id=inv_a,
                        question_a_node_id=id_a,
                        question_a_text=text_a,
                        question_b_investigation_id=inv_b,
                        question_b_node_id=id_b,
                        question_b_text=text_b,
                        shared_terms=shared,
                        overlap_score=score,
                    )
                )

    links.sort(
        key=lambda lk: (
            -lk.overlap_score,
            lk.question_a_node_id,
            lk.question_b_node_id,
        )
    )

    # Transitive closure over the link graph -> clusters (union-find).
    parent: dict[str, str] = {}

    def find(node: str) -> str:
        while parent[node] != node:
            parent[node] = parent[parent[node]]
            node = parent[node]
        return node

    def union(a_node: str, b_node: str) -> None:
        ra, rb = find(a_node), find(b_node)
        if ra != rb:
            parent[ra] = rb

    node_to_inv: dict[str, str] = {}
    for _, q_id, _, _ in questions:
        parent[q_id] = q_id

    for inv, q_id, _, _ in questions:
        node_to_inv[q_id] = inv

    for lk in links:
        union(lk.question_a_node_id, lk.question_b_node_id)

    cluster_map: dict[str, set[str]] = {}
    for _, q_id, _, _ in questions:
        root = find(q_id)
        cluster_map.setdefault(root, set()).add(q_id)

    clusters: list[QuestionCluster] = []
    for members in cluster_map.values():
        sorted_members = tuple(sorted(members))
        invs = tuple(sorted({node_to_inv[m] for m in members}))
        clusters.append(
            QuestionCluster(
                question_node_ids=sorted_members,
                size=len(sorted_members),
                investigation_ids=invs,
            )
        )
    clusters.sort(key=lambda c: (-c.size, c.question_node_ids))

    linked_nodes = {lk.question_a_node_id for lk in links} | {
        lk.question_b_node_id for lk in links
    }
    total = len(questions)
    singleton = sum(1 for members in cluster_map.values() if len(members) == 1)

    return QuestionLinkReport(
        links=tuple(links),
        clusters=tuple(clusters),
        total_questions=total,
        linked_question_count=len(linked_nodes),
        singleton_count=singleton,
        min_overlap=min_overlap,
    )


__all__ = [
    "QuestionCluster",
    "QuestionLink",
    "QuestionLinkError",
    "QuestionLinkReport",
    "discover_question_links",
]
