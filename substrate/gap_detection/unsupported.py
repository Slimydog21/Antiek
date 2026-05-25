"""DRW SPR-07 M2 — unsupported-claim detector.

A structural fact: a ``claim`` node with no *evidence-bearing* edge is an
unsupported claim — an assertion the graph holds without grounding.

Operational definition (documented so a maintainer can reproduce a verdict):
a claim is **supported** if it is the endpoint of at least
``MIN_SUPPORT_EDGES`` edges that carry evidence — i.e. an edge with a non-null
``chunk_id`` or ``source_document_id`` (the claim traces to a real source), OR
an incoming ``supported_by`` edge from an insight. A claim with fewer than
that is unsupported. The threshold defaults to 1: a single grounding edge is
enough to not be a gap; zero is the hole. Read-only; deterministic.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, List

MIN_SUPPORT_EDGES = 1


@dataclass(frozen=True)
class UnsupportedClaim:
    node_id: str
    text: str
    support_edges: int


def find_unsupported_claims(con: Any, *, min_support: int = MIN_SUPPORT_EDGES) -> List[UnsupportedClaim]:
    """Return claim nodes whose evidence-edge count is below ``min_support``.
    Ordered by node_id for determinism."""
    rows = con.execute(
        """
        WITH support AS (
            SELECT c.node_id, c.canonical_label,
                   (
                     SELECT count(*) FROM edges e
                     WHERE (e.source_node_id = c.node_id OR e.target_node_id = c.node_id)
                       AND (e.chunk_id IS NOT NULL OR e.source_document_id IS NOT NULL)
                   )
                   +
                   (
                     SELECT count(*) FROM edges e2
                     WHERE e2.target_node_id = c.node_id AND e2.relation = 'supported_by'
                   ) AS support_edges
            FROM nodes c
            WHERE c.node_type = 'claim'
        )
        SELECT node_id, canonical_label, support_edges
        FROM support
        WHERE support_edges < ?
        ORDER BY node_id
        """,
        [int(min_support)],
    ).fetchall()
    return [UnsupportedClaim(node_id=r[0], text=r[1], support_edges=int(r[2])) for r in rows]
