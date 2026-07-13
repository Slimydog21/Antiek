"""Graph assortativity axis — do high-degree nodes connect to other high-degree nodes?

The knowledge-graph topology quartet (fragmentation, centrality, diameter, transitivity) covers
connectivity, node-importance, stretch, and cliquishness. THIS axis is the **degree-mixing
pattern** — the 5th orthogonal topology view: are hubs wired to hubs (assortative) or to leaves
(disassortative)? Measured as **Newman's assortativity coefficient** ``r`` — the Pearson
correlation of the degrees at the two ends of every edge.

* ``r > 0`` — **assortative**: high-degree nodes preferentially attach to high-degree nodes
  (a "rich club"; common in social graphs).
* ``r < 0`` — **disassortative**: high-degree nodes attach to low-degree nodes (hubs serve
  leaves; common in technological/biological networks — a star is maximally disassortative).
* ``r ~= 0`` — **neutral mixing**: no systematic degree-degree correlation.

This is genuinely distinct from the quartet: a graph can be highly clustered (high transitivity)
yet disassortative, or well-connected (low fragmentation) yet assortative. Mixing pattern is
orthogonal to connectivity / importance / stretch / cliquishness. It is also scale-robust: ``r``
is a normalized correlation in ``[-1, 1]``, not a raw count that drifts with graph size.

**Measured fields:**

* ``node_count`` — distinct nodes appearing in the edge set (isolated degree-0 nodes carry no
  mixing signal and are out of scope).
* ``edge_count`` — distinct non-self-loop undirected edges (the mixing sample).
* ``self_loop_count`` — edges excluded because they were self-loops (auditable: an edge ``(u,u)``
  is not inter-node mixing; never silently dropped).
* ``degree_pairs_observed`` = ``2 * edge_count`` — the Pearson sample size (each undirected edge
  contributes two symmetric ordered endpoint-pairs).
* ``min_degree`` / ``max_degree`` — the degree range over edge-participating nodes (auditable:
  the operator sees whether degree variation exists).
* ``mean_degree`` = ``2 * edge_count / node_count``.
* ``assortativity`` — Newman's ``r`` in ``[-1, 1]``. ``None`` when undefined (no edges, or all
  endpoints share one degree — a regular graph has no mixing pattern to measure).

**Verdict (distinct honest states, never collapsed, DESCRIPTIVE not normative):**

* zero edges -> ``unknown`` (no mixing to measure — defer, never fabricated).
* all endpoints one degree (regular graph / single edge) -> ``unmeasurable`` (variance is zero —
  there is no degree variation to correlate; defer, never fabricated ``0.0``).
* ``r >= assortative_threshold`` (default ``0.30``) -> ``assortative`` (rich-club wiring).
* ``r <= disassortative_threshold`` (default ``-0.30``) -> ``disassortative`` (hub-to-leaf wiring).
* otherwise -> ``neutral_mixing`` (no systematic degree correlation).

**DESCRIPTIVE NOT NORMATIVE:** ``assortative`` does NOT mean "good" — a rich club can be an
exclusive echo chamber resistant to new information. ``disassortative`` does NOT mean "bad" — a
hub-and-spoke knowledge structure efficiently routes diverse leaf sources to central syntheses.
The operator judges whether the mixing pattern serves the graph's purpose. This axis surfaces the
FACT of degree-mixing; it does not prescribe the right structure.

**Honesty rules (load-bearing):**

* ``unknown`` never fabricates when zero edges are supplied.
* ``unmeasurable`` is its own honest state when variance is zero (a regular graph) — it is NOT
  collapsed into ``neutral_mixing`` (a real measured near-zero ``r``).
* ``assortativity`` is ``None`` only for ``unknown`` / ``unmeasurable``; a real near-zero ``r``
  is carried as a measured value, never deferred.
* ``r`` is scale-robust (normalized correlation: a 0.3 threshold means the same mixing strength at
  10 or 10 000 nodes).
* self-loops surfaced via ``self_loop_count`` (never silently dropped); parallel edges deduped to a
  simple graph (the mixing question is about distinct connections).
* ``authority = "advisory"`` — pure layer proposes; operator consent executes.
* deterministic + immutable (frozen dataclasses; sorted, reproducible output).
* import-free of off-main siblings (plain ``(node, node)`` edge pairs; route layer adapts 1:1 from
  the knowledge-graph edge set).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

__all__ = [
    "GraphAssortativityReport",
    "measure_graph_assortativity",
]

_DEFAULT_ASSORTATIVE_THRESHOLD = 0.30
_DEFAULT_DISASSORTATIVE_THRESHOLD = -0.30


@dataclass(frozen=True)
class GraphAssortativityReport:
    """The degree-mixing (assortativity) surface for one knowledge graph. Advisory, pure."""

    node_count: int
    edge_count: int
    self_loop_count: int
    degree_pairs_observed: int
    min_degree: int | None
    max_degree: int | None
    mean_degree: float | None
    assortativity: float | None
    assortative_threshold: float
    disassortative_threshold: float
    verdict: str
    notes: tuple[str, ...]
    authority: str = "advisory"


def measure_graph_assortativity(
    edges: Sequence[tuple[str, str]],
    *,
    assortative_threshold: float = _DEFAULT_ASSORTATIVE_THRESHOLD,
    disassortative_threshold: float = _DEFAULT_DISASSORTATIVE_THRESHOLD,
) -> GraphAssortativityReport:
    r"""Measure the degree-mixing (assortativity) of a knowledge graph.

    ``edges`` are undirected ``(node_a, node_b)`` pairs (the route layer supplies these from the
    knowledge-graph edge set). Returns a :class:`GraphAssortativityReport` with Newman's
    assortativity coefficient and verdict.

    Raises:
        ValueError: if a threshold is outside its valid range.
    """
    if not 0.0 < assortative_threshold <= 1.0:
        raise ValueError(
            f"assortative_threshold must be in (0.0, 1.0]; got {assortative_threshold}"
        )
    if not -1.0 <= disassortative_threshold < 0.0:
        raise ValueError(
            f"disassortative_threshold must be in [-1.0, 0.0); got {disassortative_threshold}"
        )

    # Simple undirected graph: dedup edges (order-insensitive), drop self-loops.
    self_loop_count = 0
    distinct: set[tuple[str, str]] = set()
    for a, b in edges:
        if a == b:
            self_loop_count += 1
            continue
        distinct.add((a, b) if a <= b else (b, a))

    edge_count = len(distinct)
    nodes: set[str] = {n for e in distinct for n in e}
    node_count = len(nodes)

    if edge_count == 0:
        return GraphAssortativityReport(
            node_count=node_count,
            edge_count=0,
            self_loop_count=self_loop_count,
            degree_pairs_observed=0,
            min_degree=None,
            max_degree=None,
            mean_degree=None,
            assortativity=None,
            assortative_threshold=assortative_threshold,
            disassortative_threshold=disassortative_threshold,
            verdict="unknown",
            notes=("no edges — degree mixing unmeasurable",),
        )

    degree: dict[str, int] = {n: 0 for n in nodes}
    for a, b in distinct:
        degree[a] += 1
        degree[b] += 1

    # Symmetric ordered endpoint-pairs (each undirected edge -> two observations).
    ends_a: list[int] = []
    ends_b: list[int] = []
    for a, b in distinct:
        ends_a.append(degree[a])
        ends_b.append(degree[b])
        ends_a.append(degree[b])
        ends_b.append(degree[a])

    n_pairs = len(ends_a)
    mean = sum(ends_a) / n_pairs
    cov = sum((ends_a[i] - mean) * (ends_b[i] - mean) for i in range(n_pairs)) / n_pairs
    var = sum((ends_a[i] - mean) ** 2 for i in range(n_pairs)) / n_pairs
    min_degree = min(degree.values())
    max_degree = max(degree.values())
    mean_degree = 2 * edge_count / node_count

    if var == 0.0:
        return GraphAssortativityReport(
            node_count=node_count,
            edge_count=edge_count,
            self_loop_count=self_loop_count,
            degree_pairs_observed=n_pairs,
            min_degree=min_degree,
            max_degree=max_degree,
            mean_degree=mean_degree,
            assortativity=None,
            assortative_threshold=assortative_threshold,
            disassortative_threshold=disassortative_threshold,
            verdict="unmeasurable",
            notes=("all endpoints share one degree (regular graph) — no mixing pattern",),
        )

    r = cov / var

    if r >= assortative_threshold:
        verdict = "assortative"
        notes = (
            f"assortativity {r:.4f} >= assortative_threshold {assortative_threshold:.2f} — "
            "hubs preferentially attach to hubs (rich-club wiring)",
        )
    elif r <= disassortative_threshold:
        verdict = "disassortative"
        notes = (
            f"assortativity {r:.4f} <= disassortative_threshold {disassortative_threshold:.2f} "
            "— hubs attach to leaves (hub-and-spoke wiring)",
        )
    else:
        verdict = "neutral_mixing"
        notes = (
            f"assortativity {r:.4f} between thresholds — no systematic degree correlation",
        )

    return GraphAssortativityReport(
        node_count=node_count,
        edge_count=edge_count,
        self_loop_count=self_loop_count,
        degree_pairs_observed=n_pairs,
        min_degree=min_degree,
        max_degree=max_degree,
        mean_degree=mean_degree,
        assortativity=r,
        assortative_threshold=assortative_threshold,
        disassortative_threshold=disassortative_threshold,
        verdict=verdict,
        notes=tuple(notes),
    )
