"""DRW SPR-07 — structural gap detection.

Computes gaps from graph *topology* — unanswered questions, unsupported
claims, contradictions — and ranks them as the next researches. The
compounding flywheel: each completed research enriches the graph, the
enriched graph exposes new structural gaps, those gaps seed the next
researches (via SPR-05's ``plan_from_gap``). Read-only over the graph.

The discipline that keeps this from being "an LLM free-associating things to
research": every ``GapCandidate`` is derived from a structural fact and
*structurally carries* the node ids it came from (``candidates.py`` enforces
non-empty ``backing_node_ids``). The LLM, if used, only phrases — it cannot
invent a gap or change the ranking.
"""

from __future__ import annotations

from typing import Any, Callable, List, Optional

from .candidates import (
    GapCandidate,
    UngroundedGapError,
    dedupe_candidates,
    template_phraser,
)
from .unanswered import find_unanswered_questions
from .unsupported import find_unsupported_claims
from .contradiction import Verifier, find_contradictions
from .ranking import rank_node_ids

__all__ = [
    "GapCandidate", "UngroundedGapError", "template_phraser", "dedupe_candidates",
    "find_unanswered_questions", "find_unsupported_claims", "find_contradictions",
    "Verifier", "rank_node_ids", "detect_gaps",
]


# A phraser turns (kind, primary_text, other_text) into a research question.
Phraser = Callable[..., str]


def detect_gaps(
    con: Any,
    *,
    phraser: Optional[Phraser] = None,
    verifier: Optional[Verifier] = None,
) -> List[GapCandidate]:
    """Run all structural detectors, rank by graph metrics, and emit deduped
    spin-research candidates. Deterministic given a deterministic phraser +
    verifier (defaults are deterministic). Never launches; never writes.

    The order of operations keeps the grounding guarantee intact: each
    candidate is built FROM detector output (which carries node ids), and the
    GapCandidate constructor refuses to exist without them.
    """
    phrase = phraser or template_phraser
    candidates: List[GapCandidate] = []

    # Collect backing node ids first so ranking is one metric pass.
    open_qs = find_unanswered_questions(con)
    unsupported = find_unsupported_claims(con)
    contradictions = find_contradictions(con, verifier=verifier)

    all_node_ids = (
        [q.node_id for q in open_qs]
        + [c.node_id for c in unsupported]
        + [n for c in contradictions for n in (c.node_id_a, c.node_id_b)]
    )
    impact = rank_node_ids(con, all_node_ids)

    for q in open_qs:
        candidates.append(GapCandidate(
            kind="unanswered_question",
            question=phrase("unanswered_question", q.text),
            backing_node_ids=(q.node_id,),
            impact_score=impact.get(q.node_id, 0.0),
            evidence={"question_text": q.text},
        ))
    for c in unsupported:
        candidates.append(GapCandidate(
            kind="unsupported_claim",
            question=phrase("unsupported_claim", c.text),
            backing_node_ids=(c.node_id,),
            impact_score=impact.get(c.node_id, 0.0),
            evidence={"claim_text": c.text, "support_edges": c.support_edges},
        ))
    for c in contradictions:
        # A contradiction's impact is the stronger of its two backing nodes.
        score = max(impact.get(c.node_id_a, 0.0), impact.get(c.node_id_b, 0.0))
        candidates.append(GapCandidate(
            kind="contradiction",
            question=phrase("contradiction", c.text_a, other_text=c.text_b),
            backing_node_ids=(c.node_id_a, c.node_id_b),
            impact_score=score,
            evidence={"similarity": c.similarity},
        ))

    return dedupe_candidates(candidates)
