"""Graph global-efficiency axis — how well does information flow on average across the graph?

The topology surface has fragmentation (connectivity), centrality (importance), diameter (worst-
case stretch — the MAX shortest path), transitivity (cliquishness), and assortativity (degree
mixing). THIS axis is the **average-case flow quality**: the Latora-Marchiori **global
efficiency** ``E`` — the mean of ``1 / shortest_path_length`` over all node pairs. It answers:
*on average, how many hops separate two nodes — and how badly do disconnected pairs hurt flow?*

``E`` is genuinely distinct from diameter: diameter is the PESSIMISTIC view (the single longest
shortest path, which is **infinite** for any disconnected graph — diameter cannot see past the
first break). Global efficiency is the AVERAGE view, and it **gracefully absorbs disconnection**:
a disconnected pair contributes ``1/infinity = 0``, so ``E`` stays finite and meaningful even for
a fragmented graph. A graph can have small diameter (within a component) yet low global efficiency
(many disconnected pairs drag the average down) — they measure different things.

**Measured fields:**

* ``node_count`` — distinct nodes in the edge set (isolated degree-0 nodes are out of scope, as in
  the sibling graph axes).
* ``edge_count`` — distinct non-self-loop undirected edges.
* ``self_loop_count`` — excluded self-loops (auditable; never silently dropped).
* ``reachable_pair_count`` — unordered node pairs that ARE connected (auditable: the operator sees
  how much of the graph is actually wired).
* ``total_pair_count`` = ``node_count * (node_count - 1) / 2`` — all unordered pairs.
* ``connected_fraction`` = ``reachable / total`` (the share of the graph that is wired; complements
  fragmentation but carried here as audit context for the efficiency number).
* ``global_efficiency`` — ``E`` in ``[0, 1]`` (``1`` = complete graph, every pair one hop apart;
  ``0`` = no flow). ``None`` only for ``unknown``.
* ``mean_shortest_path`` — average shortest-path length over REACHABLE pairs only (the typical
  separation when connected; ``None`` when no pair is reachable or ``unknown``). Distinct object
  from diameter's MAX.

**Verdict (distinct honest states, never collapsed, DESCRIPTIVE not normative):**

* zero edges -> ``unknown`` (no active graph to measure — defer, never fabricated).
* ``global_efficiency >= high_threshold`` (default ``0.60``) -> ``high_efficiency`` (most pairs are
  close — short paths dominate, few or no breaks).
* ``global_efficiency <= low_threshold`` (default ``0.30``) -> ``low_efficiency`` (most pairs are
  far or disconnected — long paths and fragmentation drag flow down).
* otherwise -> ``moderate_efficiency`` (a middle blend).

**DESCRIPTIVE NOT NORMATIVE:** ``high_efficiency`` does NOT mean "good" — an over-connected graph
can be noisy and redundant (every node one hop from every other is a clique, not a useful
hierarchy). ``low_efficiency`` does NOT mean "bad" — a modular, deliberately-compartmentalized
structure (clusters with sparse bridges) is often the right shape for a knowledge graph. The
operator judges whether the flow quality serves the graph's purpose. This axis surfaces the FACT of
average flow efficiency; it does not prescribe the right structure.

**Honesty rules (load-bearing):**

* ``unknown`` never fabricates when zero edges are supplied (an edges-only input cannot surface
  isolated degree-0 nodes — consistent with the sibling graph axes).
* ``global_efficiency`` is ``None`` only for ``unknown``; for any ``>= 1`` edge it is a measured
  value in ``(0, 1]`` (a single edge is the complete graph ``K2`` -> ``E = 1.0``).
* disconnection is absorbed honestly (disconnected pairs contribute ``0``, never fabricated) —
  ``E`` stays finite where diameter would be infinite.
* ``reachable_pair_count`` / ``connected_fraction`` surface the wiring verbatim so the efficiency
  number is never a black box.
* ``mean_shortest_path`` excludes infinite (disconnected) distances — the average separation AMONG
  connected pairs, distinct from diameter's max.
* self-loops excluded but counted; parallel edges deduped to a simple graph.
* ``authority = "advisory"`` — pure layer proposes; operator consent executes.
* deterministic + immutable (frozen dataclasses; sorted, reproducible output).
* import-free of off-main siblings (plain ``(node, node)`` edge pairs; route layer adapts 1:1 from
  the knowledge-graph edge set).
"""

from __future__ import annotations

from collections import deque
from collections.abc import Sequence
from dataclasses import dataclass

__all__ = [
    "GraphGlobalEfficiencyReport",
    "measure_graph_global_efficiency",
]

_DEFAULT_HIGH_THRESHOLD = 0.60
_DEFAULT_LOW_THRESHOLD = 0.30


@dataclass(frozen=True)
class GraphGlobalEfficiencyReport:
    """The average flow-efficiency surface for one knowledge graph. Advisory, pure."""

    node_count: int
    edge_count: int
    self_loop_count: int
    reachable_pair_count: int
    total_pair_count: int
    connected_fraction: float | None
    global_efficiency: float | None
    mean_shortest_path: float | None
    high_threshold: float
    low_threshold: float
    verdict: str
    notes: tuple[str, ...]
    authority: str = "advisory"


def measure_graph_global_efficiency(
    edges: Sequence[tuple[str, str]],
    *,
    high_threshold: float = _DEFAULT_HIGH_THRESHOLD,
    low_threshold: float = _DEFAULT_LOW_THRESHOLD,
) -> GraphGlobalEfficiencyReport:
    r"""Measure the global (average flow) efficiency of a knowledge graph.

    ``edges`` are undirected ``(node_a, node_b)`` pairs (the route layer supplies these from the
    knowledge-graph edge set). Returns a :class:`GraphGlobalEfficiencyReport` with the
    Latora-Marchiori global efficiency and verdict.

    Raises:
        ValueError: if thresholds are out of their valid ranges.
    """
    if not 0.0 < high_threshold <= 1.0:
        raise ValueError(
            f"high_threshold must be in (0.0, 1.0]; got {high_threshold}"
        )
    if not 0.0 <= low_threshold < 1.0:
        raise ValueError(
            f"low_threshold must be in [0.0, 1.0); got {low_threshold}"
        )
    if not low_threshold < high_threshold:
        raise ValueError(
            f"low_threshold ({low_threshold}) must be < high_threshold ({high_threshold})"
        )

    self_loop_count = 0
    distinct: set[tuple[str, str]] = set()
    for a, b in edges:
        if a == b:
            self_loop_count += 1
            continue
        distinct.add((a, b) if a <= b else (b, a))

    edge_count = len(distinct)
    nodes = sorted({n for e in distinct for n in e})
    node_count = len(nodes)

    if edge_count == 0:
        return GraphGlobalEfficiencyReport(
            node_count=node_count,
            edge_count=0,
            self_loop_count=self_loop_count,
            reachable_pair_count=0,
            total_pair_count=0,
            connected_fraction=None,
            global_efficiency=None,
            mean_shortest_path=None,
            high_threshold=high_threshold,
            low_threshold=low_threshold,
            verdict="unknown",
            notes=("no edges — flow efficiency unmeasurable",),
        )

    adj: dict[str, set[str]] = {n: set() for n in nodes}
    for a, b in distinct:
        adj[a].add(b)
        adj[b].add(a)

    def bfs_distances(src: str) -> dict[str, int]:
        dist = {src: 0}
        dq: deque[str] = deque([src])
        while dq:
            u = dq.popleft()
            for v in adj[u]:
                if v not in dist:
                    dist[v] = dist[u] + 1
                    dq.append(v)
        return dist

    dist_from = {n: bfs_distances(n) for n in nodes}

    reachable_pair_count = 0
    reach_dist_sum = 0
    inv_dist_sum = 0.0  # sum over unordered reachable pairs of 1/d
    for i in range(node_count):
        for j in range(i + 1, node_count):
            a, b = nodes[i], nodes[j]
            d = dist_from[a].get(b)
            if d is not None:
                reachable_pair_count += 1
                reach_dist_sum += d
                inv_dist_sum += 1.0 / d

    total_pair_count = node_count * (node_count - 1) // 2
    connected_fraction = reachable_pair_count / total_pair_count
    # global efficiency = (sum over ORDERED pairs of 1/d) / (n*(n-1))
    #                   = (2 * unordered inv_dist_sum) / (n*(n-1))
    global_efficiency = (2.0 * inv_dist_sum) / (node_count * (node_count - 1))
    mean_shortest_path = (
        reach_dist_sum / reachable_pair_count if reachable_pair_count > 0 else None
    )

    if global_efficiency >= high_threshold:
        verdict = "high_efficiency"
        notes = (
            f"global_efficiency {global_efficiency:.4f} >= high_threshold "
            f"{high_threshold:.2f} — most pairs are close (short paths dominate)",
        )
    elif global_efficiency <= low_threshold:
        verdict = "low_efficiency"
        notes = (
            f"global_efficiency {global_efficiency:.4f} <= low_threshold "
            f"{low_threshold:.2f} — long paths and/or disconnection drag flow down",
        )
    else:
        verdict = "moderate_efficiency"
        notes = (
            f"global_efficiency {global_efficiency:.4f} between thresholds — "
            "a middle blend of close and far pairs",
        )

    return GraphGlobalEfficiencyReport(
        node_count=node_count,
        edge_count=edge_count,
        self_loop_count=self_loop_count,
        reachable_pair_count=reachable_pair_count,
        total_pair_count=total_pair_count,
        connected_fraction=connected_fraction,
        global_efficiency=global_efficiency,
        mean_shortest_path=mean_shortest_path,
        high_threshold=high_threshold,
        low_threshold=low_threshold,
        verdict=verdict,
        notes=tuple(notes),
    )
