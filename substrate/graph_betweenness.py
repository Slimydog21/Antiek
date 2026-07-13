r"""Graph betweenness — which findings are the gateway nodes of information flow?

Operator vision (ask #1): *"...the perfect knowledge graph/base... navigate, reference,
and leverage."* To navigate the accumulating graph efficiently, the operator needs to know
which findings sit on the critical path of information flow — the GATEWAY nodes through
which many cross-topic traversals must pass. A high-betweenness node is an information
bottleneck: removing it does not necessarily disconnect the graph, but it lengthens many
shortest-path traversals. None of the existing graph axes identifies these nodes, because
none asks: *"which nodes are on the most shortest paths between other pairs?"*

**Genuinely distinct from the graph surface (load-bearing):**

* ``knowledge_graph_fragmentation`` (#1995): connected COMPONENTS (Union-Find). This measures
  per-node PATH-PARTICIPATION (Brandes' BFS dependency accumulation).
* ``graph_centrality`` (#1996): Freeman DEGREE centralization — local neighbor COUNT. A
  high-degree hub is NOT necessarily a high-betweenness gateway (a star center has high
  degree AND high betweenness, but a node bridging two dense clusters has degree 2 and
  MAXIMAL betweenness). Degree ≠ path-bridge role.
* ``graph_diameter`` (#2000): longest shortest-path (global stretch, not per-node
  attribution).
* ``graph_transitivity`` (#2001): triangle density (local cliquishness).
* ``graph_assortativity`` (#2010): degree-mixing (Newman r).
* ``graph_global_efficiency`` (#2013): MEAN inverse shortest-path (an aggregate average-case
  flow score, not per-node path attribution).
* ``staleness_cascade`` (#2016): reachability of a node attribute.
* ``structural_fragility`` (#2017): DISCRETE removal-criticality — does removing a node
  DISCONNECT? Betweenness is CONTINUOUS — how many shortest paths PASS THROUGH, whether or
  not removal disconnects. A non-articulation-point node can have high betweenness (it is on
  many shortest paths but has alternates); an articulation point can have low betweenness
  (if it connects two tiny components with few pairs). Discrete-criticality ≠
  continuous-flow-attribution.

The orthogonality: a connected, distributed, compact, efficient, biconnected graph can
STILL have a single high-betweenness gateway through which most cross-cluster traversals
must route. Removing it does not fragment (biconnected — #2017 says ``robust``) but every
cross-cluster path now costs 2 extra hops. Only betweenness surfaces that bottleneck.

**The measurement (hard to vary).** Brandes' (2001) algorithm for unweighted graphs: for
each source node, a BFS computes the number of shortest paths ``σ[v]`` from the source to
every node and the predecessor lists; then nodes are processed in REVERSE BFS order,
accumulating dependencies ``δ[v] = Σ_w (σ[v] / σ[w]) × (1 + δ[w])``. The betweenness of
``v`` is the sum of ``δ[v]`` over all sources (divided by 2 for undirected graphs, since
each path is counted from both endpoints). Normalized to ``[0, 1]`` by dividing by
``(n-1)(n-2) / 2`` (the max possible pairs for undirected graphs): ``C_B(v) = betweenness(v)
/ ((n-1)(n-2)/2)``. ``1.0`` = the node is on EVERY shortest path (a star center).

**Measured fields:**

* ``total_node_count`` — distinct nodes.
* ``component_count`` — connected components.
* ``max_normalized_betweenness`` — the peak normalized betweenness (the biggest bottleneck).
* ``mean_betweenness`` — average normalized betweenness (the overall flow-concentration
  level).
* ``gateway_node`` — the highest-betweenness node (auditable — the single biggest gateway).
* ``gateway_concentration`` — ``max_normalized_betweenness / mean_betweenness`` (how much
  the peak dominates the average; ``None`` when mean is 0).
* ``per_node`` — every node's ``(node_id, normalized_betweenness)`` sorted by betweenness
  desc then id asc (auditable: the operator sees the full gateway ranking, not a black-box
  score).

**Verdict (distinct honest states, never collapsed, DESCRIPTIVE not normative):**

* zero nodes -> ``unknown`` (defer, never fabricated).
* exactly one node -> ``singleton`` (no pairs to be on a path between).
* ``>= 2`` nodes, zero edges -> ``edgeless`` (no paths exist — betweenness undefined).
* edges exist, all components size ``<= 2`` (no node is on any shortest path — pairs are
  directly connected or in different components) -> ``pairwise_only`` (betweenness 0
  everywhere — honest measured zero, NOT undefined).
* ``max_normalized_betweenness >= gateway_threshold`` (default ``0.40``) -> ``gateway_dominated``
  (one node is on >= 40 % of all shortest paths — a severe bottleneck).
* ``max_normalized_betweenness < gateway_threshold`` AND ``>= some`` threshold (default
  ``0.10``) -> ``multi_gateway`` (several moderate gateways — distributed flow routing).
* ``max_normalized_betweenness < moderate_threshold`` -> ``diffuse_flow`` (no node
  dominates — information flows through many equally-short routes).

**DESCRIPTIVE NOT NORMATIVE:** ``gateway_dominated`` does NOT mean "bad" — a star-shaped
knowledge base with one central index finding SHOULD route through the hub (that is its
purpose). ``diffuse_flow`` does NOT mean "good" — a clique where every node is on every
path is diffuse but informationally redundant. The operator judges whether the bottleneck
reflects deliberate architecture or an accidental single-point-of-traversal.

**Honesty rules (load-bearing):**

* ``unknown`` never fabricates.
* ``singleton`` / ``edgeless`` are honest base cases (distinct states, never collapsed).
* ``pairwise_only`` is its own honest state (betweenness is an honest ``0.0`` everywhere —
  real measured zero, NOT undefined; distinct from ``edgeless`` which has no paths).
* ``max_normalized_betweenness`` / ``mean_betweenness`` are ``None`` for ``unknown`` /
  ``singleton`` / ``edgeless``; for ``pairwise_only`` they are honest ``0.0``.
* ``gateway_concentration`` is ``None`` when ``mean_betweenness`` is 0 (never fabricated).
* self-loops dropped; duplicate edges merged; disconnected graphs analyzed globally (a node
  in one component has zero betweenness from pairs in other components — honest).
* per-component analysis: betweenness is correctly computed across the WHOLE graph (Brandes
  runs from every source; cross-component pairs contribute zero, which is correct — a node
  cannot be on a path between unreachable nodes).
* every node auditable via ``per_node`` (id + betweenness — no black-box).
* ``authority = "advisory"``; deterministic + immutable.
* import-free of off-main siblings (plain ``(str, str)`` edge pairs; route layer adapts 1:1).
"""

from __future__ import annotations

from collections import deque
from collections.abc import Sequence
from dataclasses import dataclass

__all__ = [
    "NodeBetweenness",
    "GraphBetweennessReport",
    "measure_graph_betweenness",
]

_DEFAULT_GATEWAY_THRESHOLD = 0.40
_DEFAULT_MODERATE_THRESHOLD = 0.10


@dataclass(frozen=True)
class NodeBetweenness:
    """One node's normalized betweenness centrality."""

    node_id: str
    normalized_betweenness: float  # in [0.0, 1.0]


@dataclass(frozen=True)
class GraphBetweennessReport:
    """The per-node path-gateway surface for one knowledge graph. Advisory, pure."""

    total_node_count: int
    component_count: int
    max_normalized_betweenness: float | None
    mean_betweenness: float | None
    gateway_node: str | None
    gateway_concentration: float | None
    per_node: tuple[NodeBetweenness, ...]
    gateway_threshold: float
    moderate_threshold: float
    verdict: str
    notes: tuple[str, ...]
    authority: str = "advisory"


def _build_adjacency(
    edges: Sequence[tuple[str, str]],
) -> dict[str, set[str]]:
    """Build undirected adjacency. Self-loops dropped; duplicates merged."""
    adjacency: dict[str, set[str]] = {}
    for src, dst in edges:
        if src == dst:
            continue
        adjacency.setdefault(src, set()).add(dst)
        adjacency.setdefault(dst, set()).add(src)
    return adjacency


def _count_components(
    nodes: list[str], adjacency: dict[str, set[str]]
) -> int:
    """Count connected components via flood fill."""
    visited: set[str] = set()
    components = 0
    for start in nodes:
        if start in visited:
            continue
        components += 1
        stack = [start]
        visited.add(start)
        while stack:
            u = stack.pop()
            for v in adjacency.get(u, set()):
                if v not in visited:
                    visited.add(v)
                    stack.append(v)
    return components


def _brandes_betweenness(
    nodes: list[str], adjacency: dict[str, set[str]]
) -> dict[str, float]:
    """Brandes' (2001) algorithm: compute raw betweenness for all nodes.

    For each source, BFS tracks the number of shortest paths (sigma) and predecessors.
    Then nodes are processed in reverse BFS order, accumulating dependencies.
    Undirected graphs: final values divided by 2 (each path counted from both ends).
    """
    betweenness: dict[str, float] = {n: 0.0 for n in nodes}

    for s in nodes:
        stack: list[str] = []
        predecessors: dict[str, list[str]] = {n: [] for n in nodes}
        sigma: dict[str, float] = {n: 0.0 for n in nodes}
        sigma[s] = 1.0
        dist: dict[str, int] = {n: -1 for n in nodes}
        dist[s] = 0
        queue: deque[str] = deque([s])

        while queue:
            v = queue.popleft()
            stack.append(v)
            for w in adjacency.get(v, set()):
                if dist[w] < 0:
                    queue.append(w)
                    dist[w] = dist[v] + 1
                if dist[w] == dist[v] + 1:
                    sigma[w] += sigma[v]
                    predecessors[w].append(v)

        delta: dict[str, float] = {n: 0.0 for n in nodes}
        while stack:
            w = stack.pop()
            for v in predecessors[w]:
                delta[v] += (sigma[v] / sigma[w]) * (1.0 + delta[w])
            if w != s:
                betweenness[w] += delta[w]

    # Undirected: each path counted from both endpoints — divide by 2.
    for n in nodes:
        betweenness[n] /= 2.0

    return betweenness


def measure_graph_betweenness(
    nodes: Sequence[str],
    edges: Sequence[tuple[str, str]],
    *,
    gateway_threshold: float = _DEFAULT_GATEWAY_THRESHOLD,
    moderate_threshold: float = _DEFAULT_MODERATE_THRESHOLD,
) -> GraphBetweennessReport:
    r"""Measure the per-node betweenness (gateway) surface of a knowledge graph.

    ``nodes`` are every node id in the accumulated substrate. ``edges`` are
    ``(source_id, target_id)`` undirected pairs. Returns a
    :class:`GraphBetweennessReport` with per-node betweenness rankings and verdict.

    Raises:
        ValueError: if ``gateway_threshold`` or ``moderate_threshold`` is outside
            ``[0.0, 1.0]``, or ``moderate_threshold > gateway_threshold``.
    """
    if not 0.0 <= gateway_threshold <= 1.0:
        raise ValueError(
            f"gateway_threshold must be in [0.0, 1.0]; got {gateway_threshold}"
        )
    if not 0.0 <= moderate_threshold <= 1.0:
        raise ValueError(
            f"moderate_threshold must be in [0.0, 1.0]; got {moderate_threshold}"
        )
    if moderate_threshold > gateway_threshold:
        raise ValueError(
            f"moderate_threshold ({moderate_threshold}) must be <= "
            f"gateway_threshold ({gateway_threshold})"
        )

    node_set: set[str] = {n.strip() for n in nodes if n.strip()}
    for src, dst in edges:
        node_set.add(src)
        node_set.add(dst)
    sorted_nodes = sorted(node_set)
    total_node_count = len(sorted_nodes)

    if total_node_count == 0:
        return GraphBetweennessReport(
            total_node_count=0,
            component_count=0,
            max_normalized_betweenness=None,
            mean_betweenness=None,
            gateway_node=None,
            gateway_concentration=None,
            per_node=(),
            gateway_threshold=gateway_threshold,
            moderate_threshold=moderate_threshold,
            verdict="unknown",
            notes=(),
        )

    adjacency = _build_adjacency(edges)
    component_count = _count_components(sorted_nodes, adjacency)

    if total_node_count == 1:
        return GraphBetweennessReport(
            total_node_count=1,
            component_count=1,
            max_normalized_betweenness=None,
            mean_betweenness=None,
            gateway_node=None,
            gateway_concentration=None,
            per_node=(),
            gateway_threshold=gateway_threshold,
            moderate_threshold=moderate_threshold,
            verdict="singleton",
            notes=("one node — no pairs to be on a path between",),
        )

    has_edges = bool(adjacency)
    if not has_edges:
        return GraphBetweennessReport(
            total_node_count=total_node_count,
            component_count=total_node_count,
            max_normalized_betweenness=None,
            mean_betweenness=None,
            gateway_node=None,
            gateway_concentration=None,
            per_node=(),
            gateway_threshold=gateway_threshold,
            moderate_threshold=moderate_threshold,
            verdict="edgeless",
            notes=("nodes exist but zero edges — no paths to measure",),
        )

    raw = _brandes_betweenness(sorted_nodes, adjacency)

    # Normalize: divide by (n-1)(n-2)/2 — the number of ordered pairs excluding the node.
    normalizer = (total_node_count - 1) * (total_node_count - 2) / 2.0
    normalized: dict[str, float] = {}
    for n in sorted_nodes:
        normalized[n] = raw[n] / normalizer if normalizer > 0 else 0.0

    per_node_list = sorted(
        normalized.items(), key=lambda kv: (-kv[1], kv[0])
    )
    per_node = tuple(
        NodeBetweenness(node_id=n, normalized_betweenness=b) for n, b in per_node_list
    )

    max_b = per_node[0].normalized_betweenness
    mean_b = sum(normalized[n] for n in sorted_nodes) / total_node_count
    gateway = per_node[0].node_id
    concentration = max_b / mean_b if mean_b > 0 else None

    notes_list: list[str] = []

    if max_b == 0.0:
        verdict = "pairwise_only"
        notes_list.append(
            "zero betweenness everywhere — no node is on any shortest path "
            "(every pair is directly connected)"
        )
    elif max_b >= gateway_threshold:
        verdict = "gateway_dominated"
        notes_list.append(
            f"node '{gateway}' is on {max_b:.1%} of all shortest paths — "
            f"a severe bottleneck"
        )
    elif max_b >= moderate_threshold:
        verdict = "multi_gateway"
        notes_list.append(
            f"peak betweenness {max_b:.1%} — several moderate gateways, "
            f"flow routing is distributed"
        )
    else:
        verdict = "diffuse_flow"
        notes_list.append(
            f"peak betweenness {max_b:.1%} — no node dominates, information "
            f"flows through many equally-short routes"
        )

    return GraphBetweennessReport(
        total_node_count=total_node_count,
        component_count=component_count,
        max_normalized_betweenness=max_b,
        mean_betweenness=mean_b,
        gateway_node=gateway,
        gateway_concentration=concentration,
        per_node=per_node,
        gateway_threshold=gateway_threshold,
        moderate_threshold=moderate_threshold,
        verdict=verdict,
        notes=tuple(notes_list),
    )
