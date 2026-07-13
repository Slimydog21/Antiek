r"""Structural-fragility axis — is the knowledge graph's connectivity robust or hinging on load-bearing nodes?

Operator vision (ask #1): *"...the perfect knowledge graph/base and thought partner/
workstation... that substrate of information can be merged, referenced, and leveraged."*
A knowledge graph that is connected (``knowledge_graph_fragmentation`` #1995 says
``connected``), not hub-dominated (``graph_centrality`` #1996 says ``distributed``),
compact (``graph_diameter`` #2000), and efficient (``graph_global_efficiency`` #2013)
can STILL be structurally FRAGILE: a single finding whose removal splits the graph into
islands. That finding is an ARTICULATION POINT (cut vertex) — a node that is the only
bridge between two sub-graphs. None of the existing graph axes detects it, because none
asks: *"which nodes, if removed, fragment the graph?"*

**Genuinely distinct from the graph surface (load-bearing):**

* ``knowledge_graph_fragmentation`` (#1995): how many components exist NOW (static
  partition — Union-Find). THIS asks what WOULD happen if a node were removed.
* ``graph_centrality`` (#1996): Freeman DEGREE centralization — is influence
  concentrated on a high-degree hub? An articulation point can have degree 2 (a node
  linking two cliques) — LOW degree, so centrality rates it as non-critical, yet its
  removal splits the graph. Degree ≠ structural-criticality.
* ``graph_diameter`` (#2000): longest shortest-path (stretch). A compact graph can
  still have an articulation point.
* ``graph_transitivity`` (#2001): local triangle density (cliquishness).
* ``graph_assortativity`` (#2010): degree-mixing (do hubs connect to hubs?).
* ``graph_global_efficiency`` (#2013): mean inverse shortest-path (average flow).
* ``staleness_cascade`` (#2016): reachability of a node ATTRIBUTE (staleness). THIS
  is pure-structure resilience — no attribute needed.

ALL six measure either static structure or attribute propagation. NONE identifies
single-points-of-failure via Tarjan's cut-vertex / bridge DFS. The orthogonality: a
graph can be connected, distributed, compact, efficient, AND internally biconnected
(zero articulation points — robust) — or connected, distributed, compact, efficient,
AND fragile (one degree-2 node linking two dense clusters, whose removal creates two
islands). Only the low-link DFS distinguishes them.

**The measurement (hard to vary).** Tarjan's articulation-point and bridge algorithm:
a single DFS assigns each node a discovery time (``disc``) and a low-link value
(``low`` = the earliest discovery time reachable from the node's subtree via at most
one back edge). A non-root node ``u`` is an ARTICULATION POINT iff it has a DFS-tree
child ``v`` with ``low[v] >= disc[u]`` (``v``'s subtree cannot reach above ``u`` —
``u`` is the sole gateway). The DFS root is an articulation point iff it has ``>= 2``
DFS-tree children. An edge ``(u, v)`` is a BRIDGE iff ``low[v] > disc[u]`` (``v``'s
subtree has no back edge to ``u`` or above — the edge is the sole link). These are
EXACT graph-theoretic quantities, not approximations.

**Measured fields:**

* ``total_node_count`` — distinct nodes in the accumulated graph.
* ``component_count`` — connected components (so the operator knows the baseline).
* ``articulation_point_count`` — nodes whose removal increases the component count.
* ``articulation_point_ids`` — every cut vertex sorted ascending (auditable — the
  operator sees exactly which findings are load-bearing, no black-box count).
* ``bridge_count`` — edges whose removal increases the component count.
* ``bridge_edges`` — every bridge as ``(min_id, max_id)`` sorted (auditable).
* ``fragility_ratio`` — ``articulation_point_count / total_node_count`` in ``[0, 1]``
  (what fraction of the graph is load-bearing). ``None`` only for ``unknown`` /
  ``singleton`` / ``edgeless``.
* ``max_fragmentation`` — the largest number of components any single articulation
  point's removal would produce (the worst-case blast radius of one removal). ``None``
  when no articulation points exist; a real ``int`` otherwise.

**Verdict (distinct honest states, never collapsed, DESCRIPTIVE not normative):**

* zero nodes -> ``unknown`` (no graph — defer, never fabricated).
* exactly one node -> ``singleton`` (a lone entry — honest base case).
* ``>= 2`` nodes, zero edges -> ``edgeless`` (already maximally fragmented — no
  connections to break; honest state distinct from ``robust`` which needs edges).
* edges exist, zero articulation points AND zero bridges -> ``robust`` (biconnected —
  no single removal fragments; a REAL measured verdict, NOT the default).
* zero articulation points but ``>= 1`` bridge -> ``bridge_fragile`` (edge-removal
  sensitive — a bridge's deletion fragments, but no single node does).
* ``>= 1`` articulation point -> ``fragile`` (node-removal sensitive — the strongest
  fragility signal).

**DESCRIPTIVE NOT NORMATIVE:** ``fragile`` does NOT mean "bad" — a deliberately linear
chain of findings (a proof, a derivation lineage) SHOULD be fragile (removing a step
breaks the thread — that is the argument's structure). ``robust`` does NOT mean "good"
— over-connected noise where every finding links to every other is robust but useless.
The operator judges whether the fragility reflects deliberate structure (a sequential
argument) or an accidental gap (findings that COULD have alternate paths but don't).

**Honesty rules (load-bearing):**

* ``unknown`` never fabricates when the graph is empty.
* ``singleton`` is its own base case (one node — distinct from ``unknown`` and from
  ``edgeless`` which needs ``>= 2`` nodes).
* ``edgeless`` is its own honest state (nodes exist but no connections — already
  maximally fragmented, so fragility is vacuous, NOT ``robust``).
* ``fragility_ratio`` is ``None`` for ``unknown`` / ``singleton`` / ``edgeless``;
  for ``robust`` / ``bridge_fragile`` with zero APs it is an honest ``0.0`` (zero
  load-bearing nodes over a real graph — literal truth; the verdict carries the state).
* ``max_fragmentation`` is ``None`` when no articulation points exist (defer — never
  fabricated ``0``); a real ``int`` (``>= 2``) otherwise.
* ``articulation_point_ids`` / ``bridge_edges`` carried verbatim (auditable — the
  operator sees every load-bearing node and edge, not just a count).
* self-loops ``(a, a)`` dropped (a node cannot be its own articulation point);
  duplicate edges merged harmlessly (set-based adjacency).
* disconnected graphs analyzed per-component (each component's articulation points
  detected independently — a disconnected graph can have APs within each island).
* iterative DFS (no recursion-depth limit — robust for large graphs).
* ``authority = "advisory"`` — pure layer proposes; operator consent executes.
* deterministic + immutable (frozen dataclasses; sorted, reproducible output).
* import-free of off-main siblings (plain ``(str, str)`` edge pairs; route layer
  adapts 1:1 from the knowledge-graph edge set).
"""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from dataclasses import dataclass

__all__ = [
    "StructuralFragilityReport",
    "measure_structural_fragility",
]


@dataclass(frozen=True)
class StructuralFragilityReport:
    """The single-point-of-failure surface for one knowledge graph. Advisory, pure."""

    total_node_count: int
    component_count: int
    articulation_point_count: int
    articulation_point_ids: tuple[str, ...]
    bridge_count: int
    bridge_edges: tuple[tuple[str, str], ...]
    fragility_ratio: float | None
    max_fragmentation: int | None
    verdict: str
    notes: tuple[str, ...]
    authority: str = "advisory"


def _build_adjacency(
    edges: Sequence[tuple[str, str]],
) -> dict[str, set[str]]:
    """Build undirected adjacency from edge pairs.

    Self-loops (``a, a``) are dropped — a node cannot be its own articulation point.
    Duplicate edges collapse naturally (set-based adjacency).
    """
    adjacency: dict[str, set[str]] = {}
    for src, dst in edges:
        if src == dst:
            continue
        adjacency.setdefault(src, set()).add(dst)
        adjacency.setdefault(dst, set()).add(src)
    return adjacency


def _count_components(
    nodes: set[str], adjacency: dict[str, set[str]]
) -> int:
    """Count connected components via flood fill."""
    visited: set[str] = set()
    components = 0
    for start in sorted(nodes):
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


def _find_cuts(
    nodes: set[str], adjacency: dict[str, set[str]]
) -> tuple[set[str], set[tuple[str, str]]]:
    """Tarjan's articulation-point and bridge detection (iterative DFS).

    Returns ``(articulation_points, bridges)``. Bridges are normalized as
    ``(min_id, max_id)`` for uniqueness.
    """
    disc: dict[str, int] = {}
    low: dict[str, int] = {}
    parent: dict[str, str | None] = {}
    children_count: dict[str, int] = {}
    aps: set[str] = set()
    bridges: set[tuple[str, str]] = set()
    time = 0

    for root in sorted(nodes):
        if root in disc:
            continue

        disc[root] = low[root] = time
        time += 1
        parent[root] = None
        children_count[root] = 0
        stack: list[tuple[str, Iterator[str]]] = [
            (root, iter(sorted(adjacency.get(root, set()))))
        ]

        while stack:
            u, it = stack[-1]
            advanced = False
            for v in it:
                if v == parent[u]:
                    continue
                if v in disc:
                    if disc[v] < low[u]:
                        low[u] = disc[v]
                else:
                    parent[v] = u
                    children_count[v] = 0
                    disc[v] = low[v] = time
                    time += 1
                    children_count[u] += 1
                    stack.append(
                        (v, iter(sorted(adjacency.get(v, set()))))
                    )
                    advanced = True
                    break
            if not advanced:
                stack.pop()
                if stack:
                    p = stack[-1][0]
                    if low[u] < low[p]:
                        low[p] = low[u]
                    if parent[p] is not None and low[u] >= disc[p]:
                        aps.add(p)
                    if low[u] > disc[p]:
                        bridges.add((min(p, u), max(p, u)))

        if children_count[root] >= 2:
            aps.add(root)

    return aps, bridges


def measure_structural_fragility(
    nodes: Sequence[str],
    edges: Sequence[tuple[str, str]],
) -> StructuralFragilityReport:
    r"""Measure the single-point-of-failure surface of a knowledge graph.

    ``nodes`` are every node id in the accumulated substrate (findings/assets,
    including those with zero references — the route layer supplies the full node
    set, not just edge endpoints). ``edges`` are ``(source_id, target_id)`` pairs
    (undirected — both directions are inferred internally). Self-loops are dropped;
    duplicate edges are merged. Nodes in edges but not in ``nodes`` are included
    (defensive — the route layer should supply all, but edge endpoints are never
    lost).

    Returns:
        A :class:`StructuralFragilityReport` with articulation points, bridges, and
        the fragility verdict.
    """
    adjacency = _build_adjacency(edges)
    all_nodes: set[str] = {n.strip() for n in nodes if n.strip()}
    for src, dst in edges:
        all_nodes.add(src)
        all_nodes.add(dst)
    total_node_count = len(all_nodes)

    if total_node_count == 0:
        return StructuralFragilityReport(
            total_node_count=0,
            component_count=0,
            articulation_point_count=0,
            articulation_point_ids=(),
            bridge_count=0,
            bridge_edges=(),
            fragility_ratio=None,
            max_fragmentation=None,
            verdict="unknown",
            notes=(),
        )

    component_count = _count_components(all_nodes, adjacency)

    if total_node_count == 1:
        return StructuralFragilityReport(
            total_node_count=1,
            component_count=1,
            articulation_point_count=0,
            articulation_point_ids=(),
            bridge_count=0,
            bridge_edges=(),
            fragility_ratio=None,
            max_fragmentation=None,
            verdict="singleton",
            notes=("one node — no connections to break (honest base case)",),
        )

    has_edges = bool(adjacency)
    if not has_edges:
        return StructuralFragilityReport(
            total_node_count=total_node_count,
            component_count=total_node_count,
            articulation_point_count=0,
            articulation_point_ids=(),
            bridge_count=0,
            bridge_edges=(),
            fragility_ratio=None,
            max_fragmentation=None,
            verdict="edgeless",
            notes=(
                "nodes exist but zero edges — already maximally fragmented "
                "(fragility vacuous, not robust)",
            ),
        )

    aps, bridges = _find_cuts(all_nodes, adjacency)
    ap_count = len(aps)
    bridge_count = len(bridges)

    fragility_ratio = ap_count / total_node_count

    max_frag: int | None = None
    if ap_count > 0:
        max_frag = 0
        for ap in aps:
            remaining = all_nodes - {ap}
            remaining_adj: dict[str, set[str]] = {}
            for n in remaining:
                remaining_adj[n] = adjacency.get(n, set()) - {ap}
            comps = _count_components(remaining, remaining_adj)
            if comps > max_frag:
                max_frag = comps

    notes_list: list[str] = []
    if ap_count > 0:
        verdict = "fragile"
        notes_list.append(
            f"{ap_count} articulation point(s) — node removal fragments the graph "
            f"(worst single removal -> {max_frag} components)"
        )
    elif bridge_count > 0:
        verdict = "bridge_fragile"
        notes_list.append(
            f"zero articulation points but {bridge_count} bridge(s) — edge removal "
            f"fragments, but no single node does"
        )
    else:
        verdict = "robust"
        notes_list.append(
            "zero articulation points and zero bridges — biconnected "
            "(no single node or edge removal fragments)"
        )
    notes = tuple(notes_list)

    return StructuralFragilityReport(
        total_node_count=total_node_count,
        component_count=component_count,
        articulation_point_count=ap_count,
        articulation_point_ids=tuple(sorted(aps)),
        bridge_count=bridge_count,
        bridge_edges=tuple(sorted(bridges)),
        fragility_ratio=fragility_ratio,
        max_fragmentation=max_frag,
        verdict=verdict,
        notes=notes,
    )
