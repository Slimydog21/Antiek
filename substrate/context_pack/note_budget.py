"""DRW SPR-04 M2 + M4 — context-window budgeting + coverage for notes.

"Always in context" is a slogan; the window is finite. The honest framing
is **the most valuable notes that fit, with visible truncation.** This
module ranks retrieved notes by a documented function and selects the
deterministic, fitting top set, returning coverage so the UI can show the
user when they are near the window edge.

Ranking function (each term justified):

    score = W_RELEVANCE * similarity        # the task at hand dominates
          + W_RECENCY   * recency_norm      # fresher distilled state first
          + W_CONFIDENCE* confidence_norm    # trust higher-confidence notes

* W_RELEVANCE = 0.60 — relevance to the *current task* is the primary
  signal; a maximally-recent but irrelevant note should not crowd out a
  directly-relevant one.
* W_RECENCY = 0.20 — when relevance ties, the project's *latest* understanding
  wins (living notes evolve; the newest text is the current truth).
* W_CONFIDENCE = 0.20 — a high-confidence insight outranks a low-confidence
  one at equal relevance/recency.

Ties (identical score) break by ``node_id`` ascending — a stable, content-
independent ordering, so the same inputs always yield the same selection
(the determinism gate). The highest-scored notes are filled first, so the
most valuable note is never the one dropped.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Sequence

from .note_retrieval import RetrievedNote


W_RELEVANCE = 0.60
W_RECENCY = 0.20
W_CONFIDENCE = 0.20

_CONFIDENCE_NORM = {"high": 1.0, "moderate": 0.66, "low": 0.33, "unknown": 0.5}


@dataclass(frozen=True)
class NoteCoverage:
    """How much of the relevant note set made it into the window."""

    relevant: int      # candidates considered
    included: int      # selected within budget
    truncated: int     # relevant - included (made visible to the user)

    @property
    def fully_covered(self) -> bool:
        return self.truncated == 0


class _Counter:
    def count(self, text: str) -> int:
        return max(1, (len(text) + 3) // 4)


def _recency_norm(notes: Sequence[RetrievedNote]) -> dict:
    """Rank-based recency in [0,1]: newest → 1.0, oldest → 0.0. Rank-based
    (not wall-clock decay) keeps the selection deterministic and free of a
    'now' dependency for the test, while still preferring the latest state."""
    order = sorted(range(len(notes)), key=lambda i: (str(notes[i].created_at), notes[i].node_id))
    n = len(notes)
    rn = {}
    for rank, idx in enumerate(order):
        rn[notes[idx].node_id] = 0.0 if n <= 1 else rank / (n - 1)
    return rn


def score_note(note: RetrievedNote, recency_norm: float) -> float:
    conf = _CONFIDENCE_NORM.get(note.confidence, 0.5)
    return W_RELEVANCE * note.similarity + W_RECENCY * recency_norm + W_CONFIDENCE * conf


def render_note(note: RetrievedNote) -> str:
    """One note's line in the injected section. Stable format."""
    tag = "INSIGHT" if note.node_type == "insight" else "QUESTION"
    return f"- [{tag}] ({note.confidence}) {note.text}"


def select_within_budget(
    notes: Sequence[RetrievedNote],
    *,
    token_budget: int,
    counter: Optional[object] = None,
    header_text: str = "",
) -> tuple[List[RetrievedNote], NoteCoverage]:
    """Select the highest-scored notes that fit ``token_budget`` tokens.
    Deterministic; highest-ranked are never the ones dropped."""
    counter = counter or _Counter()
    rn = _recency_norm(notes)
    ranked = sorted(
        notes,
        key=lambda nt: (-score_note(nt, rn[nt.node_id]), nt.node_id),  # score desc, id asc
    )
    used = counter.count(header_text) if header_text else 0
    selected: List[RetrievedNote] = []
    for nt in ranked:
        cost = counter.count(render_note(nt) + "\n")
        if used + cost > token_budget:
            # Stop at the first note that doesn't fit. The selection is then a
            # PREFIX of the ranked order, so the highest-ranked notes are never
            # the ones dropped (M2). Matches the assembler's smart-truncate
            # break semantics; a pathological single oversized note blocking
            # the rest is acceptable for line-sized notes.
            break
        selected.append(nt)
        used += cost
    coverage = NoteCoverage(
        relevant=len(notes), included=len(selected),
        truncated=len(notes) - len(selected),
    )
    return selected, coverage
