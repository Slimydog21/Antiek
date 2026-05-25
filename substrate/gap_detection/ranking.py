"""DRW SPR-07 M4 — computed ranking of gap candidates.

Gaps are ranked by **graph metrics alone** — never by an LLM's opinion of
what's interesting. The impact of a gap is a function of how connected and
how fresh the node(s) it derives from are:

    impact = W_DEGREE  * degree_norm     # a hole on a hub matters more
           + W_RECENCY * recency_norm     # a fresh hole is more actionable
           + W_DEPENDENTS * dependents_norm  # things that build on this node

* W_DEGREE = 0.50 — a gap on a high-degree node (one many edges touch)
  blocks the most downstream reasoning; weight it highest.
* W_RECENCY = 0.20 — a recently-touched area is where the user is working.
* W_DEPENDENTS = 0.30 — explicit in-degree (how many nodes point AT this one)
  is the clearest "others depend on resolving this" signal.

Ranking is reproducible from these metrics; the LLM's only role downstream is
phrasing the question, which does not enter this score. Ties break by node_id
so the order is fully determined by graph state.
"""

from __future__ import annotations

from typing import Any, Dict, Sequence

W_DEGREE = 0.50
W_RECENCY = 0.20
W_DEPENDENTS = 0.30


def node_metrics(con: Any, node_ids: Sequence[str]) -> Dict[str, dict]:
    """Fetch degree + in-degree + created_at for a set of nodes, in one pass.
    Returns ``{node_id: {"degree", "dependents", "created_at"}}``."""
    if not node_ids:
        return {}
    ids = list(dict.fromkeys(node_ids))
    ph = ", ".join("?" for _ in ids)
    rows = con.execute(
        f"""
        SELECT n.node_id, n.created_at,
               (SELECT count(*) FROM edges e
                WHERE e.source_node_id = n.node_id OR e.target_node_id = n.node_id) AS degree,
               (SELECT count(*) FROM edges e2 WHERE e2.target_node_id = n.node_id) AS dependents
        FROM nodes n WHERE n.node_id IN ({ph})
        """,
        ids,
    ).fetchall()
    return {r[0]: {"created_at": r[1], "degree": int(r[2]), "dependents": int(r[3])} for r in rows}


def _norm(value: float, max_value: float) -> float:
    return 0.0 if max_value <= 0 else value / max_value


def impact_score(metrics: dict, *, max_degree: int, max_dependents: int, recency_rank: float) -> float:
    """Compute a node's gap impact. ``recency_rank`` is precomputed in
    [0,1] (1.0 = newest) so the score has no wall-clock dependency."""
    return (
        W_DEGREE * _norm(metrics.get("degree", 0), max_degree)
        + W_RECENCY * recency_rank
        + W_DEPENDENTS * _norm(metrics.get("dependents", 0), max_dependents)
    )


def rank_node_ids(con: Any, node_ids: Sequence[str]) -> Dict[str, float]:
    """Return ``{node_id: impact_score}`` for the given nodes, computed from
    graph metrics. Deterministic."""
    metrics = node_metrics(con, node_ids)
    if not metrics:
        return {nid: 0.0 for nid in node_ids}
    max_degree = max((m["degree"] for m in metrics.values()), default=0)
    max_dependents = max((m["dependents"] for m in metrics.values()), default=0)
    # Rank-based recency: newest created_at → 1.0. Deterministic, no 'now'.
    by_recency = sorted(metrics.items(), key=lambda kv: (str(kv[1]["created_at"]), kv[0]))
    n = len(by_recency)
    recency_rank = {nid: (i / (n - 1) if n > 1 else 1.0) for i, (nid, _) in enumerate(by_recency)}
    return {
        nid: impact_score(m, max_degree=max_degree, max_dependents=max_dependents,
                          recency_rank=recency_rank[nid])
        for nid, m in metrics.items()
    }
