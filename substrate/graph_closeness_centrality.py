r"""Graph closeness centrality — which findings are close to everything else?

Operator vision (ask #1): *"...the perfect knowledge graph/base and thought partner/
workstation... navigate, reference, and leverage."* To know which findings are at the
REACH CENTER of the graph — the ones from which every other finding is, on average, the
fewest hops away — the operator needs CLOSENESS CENTRALITY. A high-closeness node can
reach (or be reached from) the whole graph quickly: it is the natural entry point for a
survey, the anchor for a reading order, and the seed from which a subagent's breadth-first
chase spreads fastest. A low-closeness node is on the periphery — far from the mass of the
graph, reached only through long chains. None of the existing graph axes computes this,
because none asks: *"from which finding is the rest of the graph nearest?"*

**Genuinely distinct from the graph surface (load-bearing):**

* ``graph_centrality`` (#1996): Freeman DEGREE centralization — the raw local neighbor
  COUNT. A node can have HIGH degree (many immediate neighbors) but LOW closeness if those
  neighbors are themselves peripheral. Degree counts neighbors; closeness sums DISTANCES to
  everyone. Degree ≠ reach.
* ``graph_betweenness`` (#2019): Brandes' PATH-PARTICIPATION — on how many shortest paths does
  the node GATEKEEP. Closeness is PATH-DISTANCE-SUM — how SHORT are the node's OWN shortest
  paths. A dead-end leaf has zero betweenness (nothing routes through it) yet may have moderate
  closeness (it is one hop from its neighbor); a deep-chain middle node has high betweenness
  but low closeness (everything is far). Gateway role ≠ reach efficiency.
* ``graph_pagerank`` (#2021): random-walk ARRIVAL PROBABILITY with teleport — where does a
  surfer end up. Closeness is GEODESIC REACH — how few hops to everywhere, deterministically
  (no randomness, no damping). PageRank rewards being linked-to by the influential; closeness
  rewards being structurally near the whole.
* ``k_core_decomposition`` (#2020): iterative degree-PEELING — deep mutually-reinforcing
  embedding. Closeness is GEODESIC DISTANCE — a deeply-embedded node (high core) in a large
  sparse cluster can still be far from nodes in other parts. Embedding depth ≠ reach.
* ``graph_global_efficiency`` (#2013): a GRAPH-LEVEL scalar — the mean of ``1/d(u,v)`` over
  ALL pairs (harmonic aggregation), one number for the whole graph. Closeness is PER-NODE — a
  value for EACH finding (reciprocal of the SUM of its distances, Sabidussi aggregation).
  Global efficiency answers *"how efficient is flow across the whole graph on average"*;
  closeness answers *"WHICH node reaches the rest fastest, and how strong is that center."*
  Different granularity (scalar vs ranking) AND different aggregation (harmonic-of-reciprocals
  vs reciprocal-of-sum).

**The measurement (hard to vary).** For each node, BFS computes the shortest-path distance
to every reachable node. Standard Sabidussi closeness for a CONNECTED graph is
``C(u) = (n-1) / Σ d(u,v)``. For DISCONNECTED graphs this is ill-defined (unreachable nodes
have infinite distance), so we use the **Wasserman–Faust (1994) reformulation**, which is
honest and comparable across components:

    C_WF(u) = (k / (n-1)) × (k / Σ d(u,v))

where ``k`` is the number of nodes reachable from ``u`` (excluding ``u``) and the sum is over
those reachable nodes. The first factor ``(k/(n-1))`` penalizes nodes that can only reach a
fraction of the graph; the second is standard closeness within the reachable set. For a
connected graph ``k = n-1`` and this reduces exactly to Sabidussi. ``C_WF ∈ [0.0, 1.0]``;
``1.0`` means the node is one hop from every other node (the center of a star / a node in a
complete graph).

**Key property (the binding distinctness):** closeness depends on the SHAPE of the distance
distribution from a node, not on link counts or routing load. Two nodes with identical degree
can have very different closeness (one sits near the graph's center, the other on a long
tentacle). This is the unique classic centrality that captures GEODESIC REACH — it cannot be
derived from degree, betweenness, or PageRank.

**Measured fields:**

* ``total_node_count`` / ``component_count``.
* ``max_closeness`` / ``mean_closeness`` — peak and average reach efficiency.
* ``closest_node`` — the highest-closeness node (auditable — the reach center).
* ``per_node`` — every node's ``(node_id, closeness, reachable_count, total_distance)``
  sorted by closeness desc then id asc (auditable: the full reach ranking + the raw distance
  sums that produced it — no black-box).

**Verdict (distinct honest states, never collapsed, DESCRIPTIVE not normative):**

* zero nodes -> ``unknown`` (defer, never fabricated).
* exactly one node -> ``singleton`` (no other nodes to be close to — closeness undefined).
* ``>= 2`` nodes, zero edges -> ``edgeless`` (every node reaches nothing — honest ``0.0``).
* ``max_closeness >= focal_threshold`` (default ``0.50``) -> ``focal`` (a strong reach center
  exists — at least one finding reaches the bulk of the graph in few hops; a natural survey
  anchor / chase seed).
* ``max_closeness < focal_threshold`` -> ``diffuse`` (no node is close to the whole graph —
  the structure is spread out or fragmented with no reach center).

The verdict is driven by ``max_closeness`` (not a Gini) because closeness values are bounded
in ``[0, 1]`` and cluster tightly (the most-central node is rarely orders of magnitude above
the rest), so the meaningful question is not *inequality* but *does a strong center exist at
all* — exactly what ``max_closeness`` answers and global efficiency (#2013) does not.

**DESCRIPTIVE NOT NORMATIVE:** ``focal`` does NOT mean "good" — a strong reach center can be a
single-point funnel (a fragility). ``diffuse`` does NOT mean "bad" — it can mean a
well-mixed graph with no bottleneck. The operator judges whether the reach structure reflects
a healthy survey anchor or an accidental funnel.

**Honesty rules (load-bearing):**

* ``unknown`` / ``singleton`` never fabricate — closeness fields are ``None``.
* ``edgeless`` carries honest ``0.0`` everywhere (no node reaches anything — distinct from the
  deferred ``None`` of unknown/singleton).
* ``reachable_count`` and ``total_distance`` are carried per node (auditable: the operator sees
  exactly how many nodes each finding reaches and the raw hop-sum, not just the normalized
  score). An isolated node has ``reachable_count == 0`` and ``closeness == 0.0`` (honest).
* Wasserman–Faust normalization makes cross-component comparison honest: a node reaching only
  one peer is never scored ``1.0``; it is scaled by ``k/(n-1)``.
* self-loops ``(a, a)`` dropped (a self-loop does not reduce distance to anyone); duplicate
  edges merged.
* disconnected graphs analyzed globally (each node's closeness is computed against the whole
  node set via WF; ``component_count`` carried so the operator sees the fragmentation that
  drives small-component penalties).
* every node auditable via ``per_node``; ``authority = "advisory"``; deterministic + immutable.
* import-free of off-main siblings (plain ``(str, str)`` edge pairs; route layer adapts 1:1
  from the knowledge-graph edge set). Pure-Python (stdlib only).
"""

from __future__ import annotations

from collections import deque
from collections.abc import Sequence
from dataclasses import dataclass

__all__ = [
    "NodeCloseness",
    "GraphClosenessReport",
    "measure_graph_closeness_centrality",
]

_DEFAULT_FOCAL_THRESHOLD: float = 0.50


@dataclass(frozen=True)
class NodeCloseness:
    """One node's closeness (geodesic reach efficiency)."""

    node_id: str
    closeness: float  # Wasserman-Faust closeness in [0.0, 1.0]
    reachable_count: int  # k: nodes reachable from this node (excluding self)
    total_distance: int  # S: sum of shortest-path distances to reachable nodes


@dataclass(frozen=True)
class GraphClosenessReport:
    """The per-node closeness (reach) surface for one knowledge graph. Advisory, pure."""

    total_node_count: int
    component_count: int
    max_closeness: float | None
    mean_closeness: float | None
    closest_node: str | None
    per_node: tuple[NodeCloseness, ...]
    focal_threshold: float
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


def _bfs_distances(start: str, adjacency: dict[str, set[str]]) -> tuple[int, int]:
    """BFS from ``start``: returns (reachable_count, total_distance).

    ``reachable_count`` excludes ``start`` itself; ``total_distance`` is the sum of
    shortest-path distances to every reachable node.
    """
    distances: dict[str, int] = {start: 0}
    queue: deque[str] = deque([start])
    reachable = 0
    total = 0
    while queue:
        u = queue.popleft()
        for w in adjacency.get(u, ()):
            if w not in distances:
                du = distances[u] + 1
                distances[w] = du
                reachable += 1
                total += du
                queue.append(w)
    return reachable, total


def _count_components(nodes: list[str], adjacency: dict[str, set[str]]) -> int:
    """Count connected components via flood fill."""
    seen: set[str] = set()
    components = 0
    for start in nodes:
        if start in seen:
            continue
        components += 1
        stack = [start]
        seen.add(start)
        while stack:
            u = stack.pop()
            for v in adjacency.get(u, ()):
                if v not in seen:
                    seen.add(v)
                    stack.append(v)
    return components


def measure_graph_closeness_centrality(
    nodes: Sequence[str],
    edges: Sequence[tuple[str, str]],
    *,
    focal_threshold: float = _DEFAULT_FOCAL_THRESHOLD,
) -> GraphClosenessReport:
    r"""Measure the per-node closeness (geodesic reach) surface of a knowledge graph.

    ``nodes`` are every node id in the accumulated substrate (including zero-degree nodes —
    the route layer supplies the full set). ``edges`` are ``(source_id, target_id)``
    undirected pairs. Self-loops are dropped; duplicates are merged.

    Returns:
        A :class:`GraphClosenessReport` with per-node Wasserman-Faust closeness and the
        reach-center verdict.

    Raises:
        ValueError: if ``focal_threshold`` is outside ``[0.0, 1.0]``.
    """
    if not 0.0 <= focal_threshold <= 1.0:
        raise ValueError(
            f"focal_threshold must be in [0.0, 1.0]; got {focal_threshold}"
        )

    node_set: set[str] = {n.strip() for n in nodes if n.strip()}
    for src, dst in edges:
        node_set.add(src)
        node_set.add(dst)
    sorted_nodes = sorted(node_set)
    total_node_count = len(sorted_nodes)

    if total_node_count == 0:
        return GraphClosenessReport(
            total_node_count=0,
            component_count=0,
            max_closeness=None,
            mean_closeness=None,
            closest_node=None,
            per_node=(),
            focal_threshold=focal_threshold,
            verdict="unknown",
            notes=(),
        )

    adjacency = _build_adjacency(edges)
    component_count = _count_components(sorted_nodes, adjacency)

    if total_node_count == 1:
        return GraphClosenessReport(
            total_node_count=1,
            component_count=1,
            max_closeness=None,
            mean_closeness=None,
            closest_node=None,
            per_node=(
                NodeCloseness(
                    node_id=sorted_nodes[0],
                    closeness=0.0,
                    reachable_count=0,
                    total_distance=0,
                ),
            ),
            focal_threshold=focal_threshold,
            verdict="singleton",
            notes=("one node — no other nodes to be close to (closeness undefined)",),
        )

    if not adjacency:
        return GraphClosenessReport(
            total_node_count=total_node_count,
            component_count=total_node_count,
            max_closeness=0.0,
            mean_closeness=0.0,
            closest_node=sorted_nodes[0],
            per_node=tuple(
                NodeCloseness(
                    node_id=n, closeness=0.0, reachable_count=0, total_distance=0
                )
                for n in sorted_nodes
            ),
            focal_threshold=focal_threshold,
            verdict="edgeless",
            notes=(
                "nodes exist but zero edges — every node reaches nothing "
                "(closeness 0.0 everywhere, not a center signal)",
            ),
        )

    denominator = total_node_count - 1
    per_node_list: list[NodeCloseness] = []
    for n in sorted_nodes:
        reachable, total_dist = _bfs_distances(n, adjacency)
        # Wasserman-Faust: (k/(n-1)) * (k/S) = k^2 / ((n-1) * S); isolated -> 0.0
        closeness = 0.0 if reachable == 0 else (reachable * reachable) / (denominator * total_dist)
        per_node_list.append(
            NodeCloseness(
                node_id=n,
                closeness=closeness,
                reachable_count=reachable,
                total_distance=total_dist,
            )
        )

    per_node_list.sort(key=lambda nc: (-nc.closeness, nc.node_id))
    per_node = tuple(per_node_list)

    closeness_values = [nc.closeness for nc in per_node]
    max_c = closeness_values[0]
    mean_c = sum(closeness_values) / total_node_count
    closest = per_node[0].node_id

    notes_list: list[str] = []
    if max_c >= focal_threshold:
        verdict = "focal"
        notes_list.append(
            f"a strong reach center exists — node '{closest}' has closeness {max_c:.3f} "
            f"(>= {focal_threshold:.0%}); it reaches the bulk of the graph in few hops"
        )
    else:
        verdict = "diffuse"
        notes_list.append(
            f"no strong reach center — peak closeness {max_c:.3f} (< {focal_threshold:.0%}) "
            f"at '{closest}'; the graph is spread out or fragmented"
        )

    if component_count > 1:
        notes_list.append(
            f"graph is fragmented into {component_count} components — Wasserman-Faust "
            f"normalization scales each node by its reachable fraction k/(n-1), so "
            f"small-component nodes are honestly penalized, never scored 1.0"
        )

    return GraphClosenessReport(
        total_node_count=total_node_count,
        component_count=component_count,
        max_closeness=max_c,
        mean_closeness=mean_c,
        closest_node=closest,
        per_node=per_node,
        focal_threshold=focal_threshold,
        verdict=verdict,
        notes=tuple(notes_list),
    )
