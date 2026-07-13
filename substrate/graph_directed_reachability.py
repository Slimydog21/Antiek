r"""Graph directed-reachability axis — how much of the citation graph is navigable by directed paths?

Operator vision (ask #1): *"...the perfect knowledge graph/base... navigate, reference, and
leverage."* Navigation is the core reading/research verb: can the operator trace from finding A
to finding B along the DIRECTED citation structure? A knowledge graph where almost every node is
reachable from almost every other is HIGHLY NAVIGABLE — the operator can follow the citation
chain anywhere. A graph fragmented into many one-way branches is SPARSELY NAVIGABLE — large
regions are mutually invisible along directed paths. No existing axis measures DIRECTED
REACHABILITY breadth, because only PageRank (#2021), reciprocity (#2022), and SCCs (#2023) treat
edges as directed — and none counts the transitive closure.

**Genuinely distinct from the graph surface (load-bearing):**

* ``graph_global_efficiency`` (#2013): the mean of ``1/shortest_path_length`` — a DISTANCE-
  WEIGHTED average over reachable pairs, plus an undirected ``connected_fraction``. Reachability
  is a pure BINARY count (is ``j`` reachable from ``i`` AT ALL, regardless of how many hops) over
  DIRECTED pairs. The two diverge sharply: a chain ``A→B→…→Z`` has reachability ``~1.0``
  (everything reachable) but LOW efficiency (the long paths drag the average down). Efficiency
  asks "how CLOSE on average"; reachability asks "can I even GET there." Different machinery
  (distance-weighted mean vs boolean closure), different question.
* ``graph_strongly_connected`` (#2023): partitions nodes by MUTUAL reachability (``i→j`` AND
  ``j→i``). Reachability counts ONE-WAY reachability (``i→j`` OR ``j→i``). A DAG has ``n(n-1)/2``
  one-way-reachable directed pairs (half of all ordered pairs) yet ``n`` trivial SCCs (zero
  mutual reachability). SCCs measure feedback loops; reachability measures navigability breadth.
* ``graph_fragmentation`` (#1995): Union-Find components over UNDIRECTED reachability. Reachability
  uses DIRECTED paths — ``A→B`` without ``B→A`` is reachable one-way (counts here) but fragments
  into one undirected component (same node-set). Fragmentation sees connectivity;
  reachability sees directional traceability.
* ``graph_diameter`` (#2000): the MAX shortest path — a single pessimistic stretch (``∞`` once
  disconnected). Reachability is the full COUNT of reachable pairs — the average navigability, not
  the worst-case stretch.

**The binding distinctness:** directed reachability is the only axis measuring the BREADTH of
directed navigability via transitive closure — what fraction of ordered node-pairs have a
directed path between them. It tells the operator "how much of my knowledge base can I traverse
by following citations," a question no distance, feedback, or connectivity measure answers.

**The measurement (hard to vary).** For each node, compute its directed reachability SET (all
nodes reachable along directed paths, excluding itself) via iterative BFS. Then:

* ``reachable_directed_pair_count`` = Σ over nodes of ``|reach(node)|`` (ordered pairs ``i→j``).
* ``total_possible_directed_pairs`` = ``n·(n−1)`` (all ordered pairs ``i≠j``).
* ``reachability_ratio`` = ``reachable_directed_pair_count / total_possible_directed_pairs`` in
  ``[0, 1]``. ``0`` = no node reaches any other; ``1`` = every node reaches every other.

Because direction matters, an UNORDERED pair ``{i, j}`` falls into exactly one of three states:

* ``mutual`` — both ``i→j`` and ``j→i`` reachable (``i`` and ``j`` are in the same SCC).
* ``one_way`` — exactly one direction reachable.
* ``unreachable`` — neither direction reachable.

These three partition the ``n(n−1)/2`` unordered pairs exactly (auditable: the breakdown never
over- or under-counts).

**Why reachability diverges from efficiency (the worked example):** a 10-node directed chain
``A→B→…→J``. Every node reaches every later node: ``reachable_directed_pair_count = 45`` (45+36+…+1
= 45), ``total = 90`` → ``reachability_ratio = 0.5`` (one-way: every pair has exactly one
direction reachable, zero mutual). Global efficiency is dragged LOW by the long paths, yet
reachability is a clean ``0.5``. Efficiency says "far apart"; reachability says "half is
one-way-traceable." Only the closure count sees navigability independent of distance.

**Measured fields:**

* ``node_count`` — distinct nodes in the edge set.
* ``directed_edge_count`` — distinct non-self-loop directed edges.
* ``self_loop_count`` — excluded self-loops (auditable; never silently dropped).
* ``reachable_directed_pair_count`` — ordered pairs with a directed path.
* ``total_possible_directed_pairs`` = ``n·(n−1)``.
* ``reachability_ratio`` — the ratio in ``[0, 1]`` (``None`` only for ``unknown``).
* ``mutual_pair_count`` / ``one_way_pair_count`` / ``unreachable_pair_count`` — the unordered-pair
  breakdown (auditable; partition-complete).
* ``max_reach_set_size`` — the largest reach set (the most "followable" node; ``None`` for
  ``unknown`` / ``singleton``).

**Verdict (distinct honest states, never collapsed, DESCRIPTIVE not normative):**

* zero nodes -> ``unknown`` (defer, never fabricated).
* exactly one node -> ``singleton`` (no other node to reach).
* ``>= 2`` nodes, zero directed edges -> ``no_directed_edges`` (``reachability_ratio`` is an
  honest ``0.0`` — nothing is reachable; distinct from ``unknown``'s ``None``).
* ``reachability_ratio == 1.0`` -> ``fully_navigable`` (every node reaches every other — total
  directed navigability; equivalent to strong connectivity measured via the closure).
* ``reachability_ratio >= navigable_threshold`` (default ``0.70``) -> ``highly_navigable`` (most
  of the graph is one-followable from most of the graph).
* ``reachability_ratio <= sparse_threshold`` (default ``0.30``) -> ``sparsely_navigable`` (most
  pairs are mutually invisible along directed paths — fragmented navigation).
* otherwise -> ``moderately_navigable`` (a middle blend).

**DESCRIPTIVE NOT NORMATIVE:** ``fully_navigable`` does NOT mean "good" — total reachability can
be a tangle where everything cites everything (noise, not structure). ``sparsely_navigable`` does
NOT mean "bad" — a clean hierarchy of independent branches may be exactly the right shape. The
operator judges whether the navigability reflects a traceable structure or a citation tangle.

**Honesty rules (load-bearing):**

* ``unknown`` never fabricates when zero nodes are supplied.
* ``no_directed_edges`` is its own honest state — ``reachability_ratio`` is a measured ``0.0``,
  NEVER ``None`` (zero edges is a real measurement: nothing reachable). The ``None`` vs ``0.0``
  states never collapse.
* ``reachability_ratio`` is ``None`` ONLY for ``unknown`` / ``singleton``.
* the unordered-pair breakdown is a verifiable partition (``mutual + one_way + unreachable ==
  n(n-1)/2``).
* self-loops excluded + counted; parallel edges deduped.
* ``authority = "advisory"`` — pure layer proposes; operator consent executes.
* deterministic + immutable (frozen dataclass; BFS in sorted-neighbor order; reproducible output).
* import-free of off-main siblings (plain ``(node, node)`` directed edge pairs; route layer adapts
  1:1 from the knowledge-graph directed-edge set).
"""

from __future__ import annotations

from collections import deque
from collections.abc import Sequence
from dataclasses import dataclass

__all__ = [
    "GraphDirectedReachabilityReport",
    "measure_graph_directed_reachability",
]

_DEFAULT_NAVIGABLE_THRESHOLD = 0.70
_DEFAULT_SPARSE_THRESHOLD = 0.30


@dataclass(frozen=True)
class GraphDirectedReachabilityReport:
    """The directed-reachability (navigability) surface for one directed graph. Advisory, pure."""

    node_count: int
    directed_edge_count: int
    self_loop_count: int
    reachable_directed_pair_count: int
    total_possible_directed_pairs: int
    reachability_ratio: float | None
    mutual_pair_count: int
    one_way_pair_count: int
    unreachable_pair_count: int
    max_reach_set_size: int | None
    navigable_threshold: float
    sparse_threshold: float
    verdict: str
    notes: tuple[str, ...]
    authority: str = "advisory"


def measure_graph_directed_reachability(
    nodes: Sequence[str],
    edges: Sequence[tuple[str, str]],
    *,
    navigable_threshold: float = _DEFAULT_NAVIGABLE_THRESHOLD,
    sparse_threshold: float = _DEFAULT_SPARSE_THRESHOLD,
) -> GraphDirectedReachabilityReport:
    r"""Measure the directed reachability (navigability breadth) of a directed graph.

    Args:
        nodes: distinct node identifiers.
        edges: ``(from, to)`` DIRECTED pairs (self-loops excluded; parallel edges merged).
        navigable_threshold: ratio at/above which the graph is ``highly_navigable``
            (default ``0.70``).
        sparse_threshold: ratio at/below which the graph is ``sparsely_navigable``
            (default ``0.30``).

    Returns:
        A :class:`GraphDirectedReachabilityReport` with the reachability ratio and verdict.

    Raises:
        ValueError: if thresholds are outside their valid ranges.
    """
    if not 0.0 <= sparse_threshold <= 1.0:
        raise ValueError(
            f"sparse_threshold must be in [0.0, 1.0]; got {sparse_threshold}"
        )
    if not 0.0 <= navigable_threshold <= 1.0:
        raise ValueError(
            f"navigable_threshold must be in [0.0, 1.0]; got {navigable_threshold}"
        )
    if not sparse_threshold <= navigable_threshold <= 1.0:
        raise ValueError(
            f"navigable_threshold ({navigable_threshold}) must be in "
            f"[sparse_threshold ({sparse_threshold}), 1.0]"
        )

    node_list: list[str] = sorted(set(nodes))
    node_count = len(node_list)

    if node_count == 0:
        return GraphDirectedReachabilityReport(
            node_count=0,
            directed_edge_count=0,
            self_loop_count=0,
            reachable_directed_pair_count=0,
            total_possible_directed_pairs=0,
            reachability_ratio=None,
            mutual_pair_count=0,
            one_way_pair_count=0,
            unreachable_pair_count=0,
            max_reach_set_size=None,
            navigable_threshold=navigable_threshold,
            sparse_threshold=sparse_threshold,
            verdict="unknown",
            notes=("no nodes — directed reachability unmeasurable",),
        )

    # Distinct directed edges; exclude self-loops (count them).
    self_loop_count = 0
    directed: set[tuple[str, str]] = set()
    for src, dst in edges:
        if src == dst:
            self_loop_count += 1
            continue
        directed.add((src, dst))

    directed_edge_count = len(directed)
    adj: dict[str, set[str]] = {n: set() for n in node_list}
    for src, dst in directed:
        adj[src].add(dst)

    # Directed reachability set per node via iterative BFS (sorted neighbors for determinism).
    reach_sets: dict[str, set[str]] = {}
    for start in node_list:
        seen: set[str] = set()
        dq: deque[str] = deque([start])
        seen.add(start)
        while dq:
            cur = dq.popleft()
            for nb in sorted(adj[cur]):
                if nb not in seen:
                    seen.add(nb)
                    dq.append(nb)
        seen.discard(start)  # exclude self
        reach_sets[start] = seen

    max_reach_set_size = max((len(rs) for rs in reach_sets.values()), default=0)

    if node_count == 1:
        return GraphDirectedReachabilityReport(
            node_count=node_count,
            directed_edge_count=directed_edge_count,
            self_loop_count=self_loop_count,
            reachable_directed_pair_count=0,
            total_possible_directed_pairs=0,
            reachability_ratio=None,
            mutual_pair_count=0,
            one_way_pair_count=0,
            unreachable_pair_count=0,
            max_reach_set_size=max_reach_set_size,
            navigable_threshold=navigable_threshold,
            sparse_threshold=sparse_threshold,
            verdict="singleton",
            notes=("one node — no other node to reach",),
        )

    reachable_directed_pair_count = sum(len(rs) for rs in reach_sets.values())
    total_possible_directed_pairs = node_count * (node_count - 1)
    reachability_ratio = reachable_directed_pair_count / total_possible_directed_pairs

    # Unordered-pair breakdown: mutual / one_way / unreachable.
    mutual_pair_count = 0
    one_way_pair_count = 0
    unreachable_pair_count = 0
    for i in range(node_count):
        for j in range(i + 1, node_count):
            a, b = node_list[i], node_list[j]
            a_reaches_b = b in reach_sets[a]
            b_reaches_a = a in reach_sets[b]
            if a_reaches_b and b_reaches_a:
                mutual_pair_count += 1
            elif a_reaches_b or b_reaches_a:
                one_way_pair_count += 1
            else:
                unreachable_pair_count += 1

    if directed_edge_count == 0:
        verdict = "no_directed_edges"
        notes = (
            "reachability_ratio 0.0 — zero directed edges, nothing reachable "
            "(distinct from unknown's None)",
        )
    elif reachability_ratio == 1.0:
        verdict = "fully_navigable"
        notes = (
            "reachability_ratio 1.0 — every node reaches every other along directed "
            "paths (total navigability, equivalent to strong connectivity)",
        )
    elif reachability_ratio >= navigable_threshold:
        verdict = "highly_navigable"
        notes = (
            f"reachability_ratio {reachability_ratio:.4f} >= navigable_threshold "
            f"{navigable_threshold:.2f} — most of the graph is directed-reachable "
            "from most of the graph",
        )
    elif reachability_ratio <= sparse_threshold:
        verdict = "sparsely_navigable"
        notes = (
            f"reachability_ratio {reachability_ratio:.4f} <= sparse_threshold "
            f"{sparse_threshold:.2f} — most pairs are mutually invisible along "
            "directed paths",
        )
    else:
        verdict = "moderately_navigable"
        notes = (
            f"reachability_ratio {reachability_ratio:.4f} between thresholds — "
            "a middle blend of reachable and unreachable pairs",
        )

    return GraphDirectedReachabilityReport(
        node_count=node_count,
        directed_edge_count=directed_edge_count,
        self_loop_count=self_loop_count,
        reachable_directed_pair_count=reachable_directed_pair_count,
        total_possible_directed_pairs=total_possible_directed_pairs,
        reachability_ratio=reachability_ratio,
        mutual_pair_count=mutual_pair_count,
        one_way_pair_count=one_way_pair_count,
        unreachable_pair_count=unreachable_pair_count,
        max_reach_set_size=max_reach_set_size,
        navigable_threshold=navigable_threshold,
        sparse_threshold=sparse_threshold,
        verdict=verdict,
        notes=notes,
    )
