"""DRW SPR-07 M1 — unanswered-question detector.

A structural fact: a ``question`` node with no ``resolved_by`` edge (or only
a resolution below ``MIN_RESOLUTION_CONFIDENCE``) is an open question — a
hole the next research can fill. Deterministic from graph state; read-only.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, List

# A resolved_by edge below this extraction_confidence is treated as a weak
# resolution — the question still counts as open. 0.5 = "better than a coin
# flip"; below it, the resolution is not load-bearing.
MIN_RESOLUTION_CONFIDENCE = 0.5


@dataclass(frozen=True)
class OpenQuestion:
    node_id: str
    text: str


def find_unanswered_questions(con: Any) -> List[OpenQuestion]:
    """Return question nodes with no (sufficiently-confident) resolved_by
    edge. Ordered by node_id for determinism."""
    rows = con.execute(
        """
        SELECT q.node_id, q.canonical_label
        FROM nodes q
        WHERE q.node_type = 'question'
          AND NOT EXISTS (
            SELECT 1 FROM edges e
            WHERE e.source_node_id = q.node_id
              AND e.relation = 'resolved_by'
              AND e.extraction_confidence >= ?
          )
        ORDER BY q.node_id
        """,
        [MIN_RESOLUTION_CONFIDENCE],
    ).fetchall()
    return [OpenQuestion(node_id=r[0], text=r[1]) for r in rows]
