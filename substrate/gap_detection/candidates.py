"""DRW SPR-07 M5 + M6 — spin-research candidates + the grounding guard.

A ``GapCandidate`` is a structural hole in the graph phrased as a research
question. The product's named failure mode is "gap detection degenerating
into an LLM that free-associates things you could research." The defense is
**enforced in code, not promised in prose**: a ``GapCandidate`` cannot be
constructed without the node id(s) it derives from. ``__post_init__`` raises
on empty ``backing_node_ids`` — so a graph-ungrounded gap is impossible by
construction, and the guard test proves it.

The LLM (if used at all) is confined to *phrasing* a candidate's question;
it never invents a candidate or changes ranking. The default phraser is a
deterministic template, so removing the LLM changes neither which gaps exist
nor their order.

``GapCandidate`` exposes ``.question`` / ``.gap_id`` / ``.kind`` so it drops
straight into SPR-05's ``plan_from_gap`` seed interface.
"""

from __future__ import annotations

import hashlib
from collections.abc import Sequence
from dataclasses import dataclass, field

GAP_KINDS = ("unanswered_question", "unsupported_claim", "contradiction")


class UngroundedGapError(ValueError):
    """Raised when a GapCandidate is constructed without backing node ids —
    the structural guard against free-associated (graph-ungrounded) gaps."""


@dataclass(frozen=True)
class GapCandidate:
    kind: str
    question: str                       # the phrased research question (SPR-05 seed)
    backing_node_ids: tuple             # REQUIRED, non-empty — the grounding guard
    impact_score: float = 0.0
    evidence: dict[str, object] = field(default_factory=dict)

    def __post_init__(self):
        if self.kind not in GAP_KINDS:
            raise ValueError(f"unknown gap kind {self.kind!r}; allowed: {GAP_KINDS}")
        if not self.backing_node_ids:
            raise UngroundedGapError(
                f"GapCandidate({self.kind!r}) has no backing_node_ids — a gap "
                f"must derive from a graph structural fact. This is the "
                f"anti-free-association invariant (SPR-07 M6)."
            )
        # Normalize to a tuple of non-empty strings.
        object.__setattr__(
            self, "backing_node_ids",
            tuple(str(n) for n in self.backing_node_ids if str(n).strip()),
        )
        if not self.backing_node_ids:
            raise UngroundedGapError("GapCandidate backing_node_ids were all empty.")

    # -- SPR-05 plan_from_gap seed interface --------------------------------

    @property
    def gap_id(self) -> str:
        """Deterministic id from kind + backing nodes — so the same gap on the
        same graph state always has the same id (idempotent re-detection)."""
        h = hashlib.sha256((self.kind + "|" + "|".join(sorted(self.backing_node_ids))).encode()).hexdigest()[:16]
        return f"gap-{h}"

    @property
    def node_id(self) -> str:
        return self.backing_node_ids[0]


# A phraser turns a structural fact into a research question. Default is a
# deterministic template; an LLM phraser may replace it but must not change
# which candidates exist or their order.
def template_phraser(kind: str, primary_text: str, *, other_text: str = "") -> str:
    if kind == "unanswered_question":
        return primary_text.rstrip("?").strip() + "?"
    if kind == "unsupported_claim":
        return f"Find primary-source evidence for or against the claim: {primary_text}"
    if kind == "contradiction":
        return (f"Resolve the apparent contradiction between "
                f"“{primary_text}” and “{other_text}”.")
    return primary_text  # pragma: no cover


def dedupe_candidates(candidates: Sequence[GapCandidate]) -> list[GapCandidate]:
    """Collapse candidates with the same gap_id (same structural fact),
    keeping the highest impact. Deterministic order: impact desc, gap_id asc."""
    by_id: dict[str, GapCandidate] = {}
    for c in candidates:
        existing = by_id.get(c.gap_id)
        if existing is None or c.impact_score > existing.impact_score:
            by_id[c.gap_id] = c
    return sorted(by_id.values(), key=lambda c: (-c.impact_score, c.gap_id))
