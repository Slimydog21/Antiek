"""Speak ↔ DRW SPR-07 — the gap-detection drop-in (the "later" arrived).

When Speak SPR-04 shipped, ``substrate/gap_detection/`` did not exist, so the
compounding interviewer read gaps from the Speak project graph via
``interviewer_context.SpeakGraphGapSource`` against the ``contracts.GapSource``
Protocol. DRW SPR-07 has since landed (``substrate/gap_detection/detect_gaps``),
so this module supplies the contract's intended real implementation:
``DRWGapSource`` ranks gaps over the **shared** graph by computed centrality
(DRW ``ranking.py`` — degree/dependents/recency), which is exactly the
"degree/centrality from the graph" SPR-04 M4 asked for and ``SpeakGraphGapSource``
could only approximate.

Two honest constraints shape the design (technical taste, not hand-waving):

1. **Scope.** DRW's detector is graph-wide and the ``nodes`` table has no
   project column. Injecting *every* graph gap into one project's interviewer
   would be noise. So ``DRWGapSource`` is **project-scoped**: it only surfaces
   gaps whose backing nodes are tagged with this project
   (``metadata.speak_project_id``). With no Speak content promoted to the
   shared graph yet, it returns ``[]`` and the composite degrades cleanly to
   ``SpeakGraphGapSource`` — today's behavior, unchanged.

2. **Consent, not auto-promotion.** Making Speak content visible in the
   *shared* graph (where Research/Read/Write across projects could read it) is
   broader than "inform another interviewee in this project" and carries the
   same consent/legal weight as public publishing (G2/G3). So this module does
   **not** auto-promote ``speak_claims`` to shared nodes — that is an
   operator-owned decision. It defines the convention a sanctioned promotion
   would follow (``SPEAK_PROJECT_NODE_KEY``) and lights up the moment nodes
   carry it. DRW also reserves the ``corroborate`` kind for Speak's
   consent-aware claim corroboration (``SpeakGraphGapSource``); DRW gaps map to
   ``open_question`` / ``deepen``, which flow through the conditioning context
   without a Speak-claim consent lookup.

The result is a ``CompositeGapSource`` that is the strictly-better SPR-04
default: Speak's consent-aware, project-local corroboration PLUS DRW's
centrality-ranked shared-graph structural gaps for the project.
"""

from __future__ import annotations

import json
from typing import Any, List, Optional, Sequence

from .contracts import GapSource, OpenQuestion

# The node-metadata key a sanctioned Speak→shared-graph promotion stamps so a
# shared node is attributable to a Speak project. DRWGapSource scopes on it.
SPEAK_PROJECT_NODE_KEY = "speak_project_id"

# DRW gap kind → Speak OpenQuestion kind. ``corroborate`` is deliberately NOT a
# target: corroboration is Speak's consent-aware, claim-level concern
# (SpeakGraphGapSource), and a DRW node is not a speak_claim the consent filter
# can resolve. DRW's unsupported/contradiction gaps surface as ``deepen``.
_DRW_KIND_TO_SPEAK = {
    "unanswered_question": "open_question",
    "unsupported_claim": "deepen",
    "contradiction": "deepen",
}


class DRWGapSource:
    """``contracts.GapSource`` backed by DRW SPR-07, scoped to one project's
    promoted shared-graph nodes. Returns DRW gaps ranked by graph centrality."""

    def __init__(self, con: Any):
        self.con = con

    def _project_node_ids(self, project_id: str) -> set:
        """Shared-graph nodes attributable to this Speak project. Empty until a
        sanctioned promotion stamps ``SPEAK_PROJECT_NODE_KEY`` — DRWGapSource
        then returns [] and the composite is exactly SpeakGraphGapSource."""
        try:
            rows = self.con.execute(
                "SELECT node_id FROM nodes WHERE metadata LIKE ?",
                [f'%"{SPEAK_PROJECT_NODE_KEY}": "{project_id}"%'],
            ).fetchall()
        except Exception:
            return set()
        return {r[0] for r in rows}

    def open_questions(self, project_id: str, *, limit: int = 20) -> List[OpenQuestion]:
        project_nodes = self._project_node_ids(project_id)
        if not project_nodes:
            return []  # nothing of this project is in the shared graph (yet)
        try:
            from substrate.gap_detection import detect_gaps
        except ImportError:  # pragma: no cover — DRW not importable
            return []
        out: List[OpenQuestion] = []
        for cand in detect_gaps(self.con):
            # Project scope: every backing node must belong to this project, so
            # an unrelated investigation's gap never leaks into this interviewer.
            if not set(cand.backing_node_ids) <= project_nodes:
                continue
            speak_kind = _DRW_KIND_TO_SPEAK.get(cand.kind)
            if speak_kind is None:
                continue
            out.append(OpenQuestion(
                question_id=cand.gap_id,
                text=cand.question,
                kind=speak_kind,
                salience=cand.impact_score,   # DRW graph-centrality rank
                anchor_id=cand.node_id,
            ))
        out.sort(key=lambda g: g.salience, reverse=True)
        return out[:limit]


class CompositeGapSource:
    """Merges several ``GapSource``s into one ranked list, de-duplicated by
    ``question_id`` (a gap surfaced by more than one source appears once, at
    its highest salience). Deterministic: salience desc, question_id asc."""

    def __init__(self, *sources: GapSource):
        self._sources = [s for s in sources if s is not None]

    def open_questions(self, project_id: str, *, limit: int = 20) -> List[OpenQuestion]:
        best: dict[str, OpenQuestion] = {}
        for src in self._sources:
            for g in src.open_questions(project_id, limit=limit):
                cur = best.get(g.question_id)
                if cur is None or g.salience > cur.salience:
                    best[g.question_id] = g
        merged = sorted(best.values(), key=lambda g: (-g.salience, g.question_id))
        return merged[:limit]


def default_gap_source(con: Any) -> GapSource:
    """The SPR-04 default now that DRW exists: DRW's centrality-ranked
    shared-graph gaps for the project, composed with Speak's consent-aware
    project-local source. Falls back to SpeakGraphGapSource alone if DRW is
    unavailable. Imported lazily by ``interviewer_context`` to avoid a cycle."""
    from .interviewer_context import SpeakGraphGapSource  # lazy: avoids import cycle
    speak_src = SpeakGraphGapSource(con)
    try:
        import substrate.gap_detection  # noqa: F401 — availability probe
    except ImportError:  # pragma: no cover
        return speak_src
    return CompositeGapSource(DRWGapSource(con), speak_src)
