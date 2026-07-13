r"""Graph transitivity — how locally cliquish is the accumulated knowledge graph?

Operator vision (ask #1): *"...the perfect knowledge graph/base and thought
partner/workstation..."* and *"...that substrate of information can be merged,
referenced, and leveraged..."* The operator's compounding value lives in a
TRANSITIVELY RICH substrate: when finding A relates to B and B relates to C, a
well-woven knowledge base ALSO links A to C — neighborhoods close into triangles,
so navigating locally reveals reinforcement rather than gaps. The graph-theoretic
quantity that captures this LOCAL CLIQUISHNESS is transitivity (the global
clustering coefficient): the fraction of connected length-2 paths (triples) that
CLOSE into triangles. It is bounded ``[0, 1]`` and meaningful at ANY graph size
(unlike raw density, which necessarily falls as a graph grows because the number
of POSSIBLE edges scales quadratically — a 4-hop web is rich whether the base has
40 or 40,000 findings). None of the other topology axes measures local closure.

**Genuinely distinct from the graph surface (load-bearing):**

* ``knowledge_graph_fragmentation`` (#1995): connected COMPONENTS — how many islands
  (macro reachability). Union-Find partition.
* ``graph_centrality`` (#1996): degree CONCENTRATION — hub-dominated or distributed?
  Freeman degree centralization.
* ``graph_diameter`` (#2000): STRETCH — how long is the longest shortest path? BFS
  all-pairs.
* **``graph_transitivity`` (this):** LOCAL CLIQUISHNESS — do a node's neighbors also
  connect to each other (do 2-paths close into triangles)? Triangle counting.

They are orthogonal. A STAR (one hub, many leaves) is connected (#1995 ``connected``),
maximally hub-dominated (#1996 ``hub_dominated``), diameter 2 (#2000 ``compact``), yet
transitivity ``0`` (this ``open_weave`` — the leaves never link to each other, zero
triangles). A CLIQUE is connected, distributed (#1996 — every node the same degree),
diameter 1, and transitivity ``1.0`` (this ``tightly_woven`` — every triple closes).
A graph can share another axis's verdict yet split on transitivity: two connected,
diameter-2, moderately-centralized graphs can differ wholly in local closure (one
where leaves cross-link, one where they don't). Reachability, hub-ness, stretch, and
local closure are four independent views of topology.

**Distinct from single-twin coherence:** ``twin_internal_coherence`` (#1988) measures
whether ONE TWIN's insights connect to each other (within-document, Jaccard
subject-overlap edges). This measures GLOBAL triangle closure across the ENTIRE
accumulated substrate using the full cross-investigation edge set. Different scope,
different machinery.

**The measurement (hard to vary).** Given the accumulated node set and undirected
edge set (self-loops ignored, duplicate edges merged, dangling edges surfaced not
coerced — mirroring #1995/#1996/#2000), build the adjacency map and count:

* For each node ``u`` with degree ``d_u``, the triples CENTERED at ``u`` are the
  ``C(d_u, 2)`` unordered pairs of its neighbors. The CLOSED triples at ``u`` are
  those neighbor-pairs that are themselves connected by an edge.
* ``triangle_count`` — closed triples summed over all centers, divided by 3 (each
  triangle is centered at each of its 3 vertices).
* ``connected_triples`` — ``sum over u of C(d_u, 2)`` (every length-2 path).
* ``transitivity = 3 * triangle_count / connected_triples`` — equivalently
  ``sum(closed_triples_u) / sum(C(d_u, 2))``: the triple-weighted (global) closure
  fraction in ``[0, 1]``; ``1.0`` is a disjoint union of cliques, ``0.0`` is a
  pure open structure (triples exist but none close).
* ``mean_local_clustering`` — the UNWEIGHTED average of per-node local clustering
  coefficients ``closed_triples_u / C(d_u, 2)`` over nodes with ``d_u >= 2`` (the
  complement to transitivity: transitivity weights high-degree nodes more because
  they anchor more triples; mean-local weights every node equally — the two can
  diverge, so both are reported).

**Verdict (distinct honest states, never collapsed, DESCRIPTIVE not normative):**

* zero nodes -> ``unknown`` (nothing accumulated — defer, never fabricated).
* exactly one node, zero edges -> ``singleton`` (a lone entry — honest base case).
* >= 2 nodes, zero valid edges -> ``edgeless`` (no links — clustering undefined;
  deferred honestly, never fabricated ``open_weave``).
* valid edges but ``connected_triples == 0`` (every node degree <= 1 — a disjoint
  union of pairs; no 2-path exists to close) -> ``pairwise`` (clustering undefined;
  distinct from ``edgeless`` which has no edges at all).
* ``connected_triples > 0`` and ``transitivity == 0.0`` -> ``open_weave`` (2-paths
  exist but NONE close — a measured zero; the pure open structure: trees, stars,
  paths, squares. Distinct from ``pairwise`` which has no triples to measure).
* ``0 < transitivity < closure_threshold`` (default ``0.20``) -> ``loosely_woven``
  (some local closure but sparse — neighborhoods rarely reinforce).
* ``transitivity >= closure_threshold`` -> ``tightly_woven`` (neighborhoods close
  into triangles — the substrate is transitively rich and locally navigable; a REAL
  measured verdict, NOT the default).

DESCRIPTIVE NOT NORMATIVE: ``open_weave`` does NOT mean "broken" — a derivation
lineage, a proof, or a timeline is legitimately a LINEAR open structure (each
finding builds on one parent, no cross-links needed). The operator judges whether
low closure is a gap (findings that COULD cross-link but don't) or by-design (a
thread that SHOULD be linear). The verdict describes LOCAL closure topology; the
operator judges value.

**Honesty rules (load-bearing):**

* ``unknown`` / ``singleton`` / ``edgeless`` / ``pairwise`` are DISTINCT defer
  states — ``transitivity`` / ``triangle_count`` / ``connected_triples`` /
  ``mean_local_clustering`` are ``None`` in all of them (defer — never ``0.0``).
* ``open_weave`` is a REAL measured verdict (``transitivity == 0.0`` WITH triples
  present) — never collapsed into ``pairwise`` (no triples, ``None``) or
  ``edgeless`` (no edges).
* ``transitivity`` and ``mean_local_clustering`` are bounded ``[0, 1]`` by
  construction (a fraction of closed triples).
* absolute closure threshold (not normalized to graph size): transitivity is
  already size-stable, so a single ``closure_threshold`` in ``[0, 1]`` is honest at
  any scale.
* orphan nodes (zero edges) surfaced as ``orphan_node_count`` (mirrors #1995/#2000
  accountability).
* self-loops ignored; duplicate edges merged; edges referencing undeclared nodes
  surface as ``dangling_edge_count`` (never coerced — mirrors #1995/#1996/#2000).
* ``authority = "advisory"`` — pure layer proposes; operator consent executes.
* deterministic + immutable (frozen dataclasses; sorted, reproducible output).
* import-free of off-main siblings (own ``GraphEdge`` shape; route layer adapts 1:1).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

__all__ = [
    "GraphEdge",
    "GraphTransitivityReport",
    "measure_graph_transitivity",
]

_DEFAULT_CLOSURE_THRESHOLD = 0.20


@dataclass(frozen=True)
class GraphEdge:
    """An undirected link between two nodes in the accumulated knowledge graph.

    Attributes:
        source: one endpoint node id.
        target: the other endpoint node id.
    """

    source: str
    target: str


@dataclass(frozen=True)
class GraphTransitivityReport:
    """Local-cliquishness topology of the accumulated knowledge graph (advisory)."""

    node_count: int
    edge_count: int
    dangling_edge_count: int
    orphan_node_count: int
    triangle_count: int | None
    connected_triples: int | None
    transitivity: float | None
    mean_local_clustering: float | None
    closure_threshold: float
    verdict: str
    notes: tuple[str, ...]
    authority: str = "advisory"


def measure_graph_transitivity(
    nodes: Sequence[str],
    edges: Sequence[GraphEdge],
    *,
    closure_threshold: float = _DEFAULT_CLOSURE_THRESHOLD,
) -> GraphTransitivityReport:
    r"""Measure the local cliquishness (transitivity) of the knowledge graph.

    ``nodes`` are every node id in the accumulated substrate. ``edges`` are every
    undirected link (the route layer supplies all edge types as a flat list).
    Returns a :class:`GraphTransitivityReport` with closure statistics and verdict.

    Raises:
        ValueError: if ``closure_threshold`` is outside ``(0.0, 1.0]``.
    """
    if not 0.0 < closure_threshold <= 1.0:
        raise ValueError(
            f"closure_threshold must be in (0.0, 1.0]; got {closure_threshold}"
        )

    node_set = set(nodes)
    node_count = len(node_set)

    if node_count == 0:
        return GraphTransitivityReport(
            node_count=0,
            edge_count=0,
            dangling_edge_count=0,
            orphan_node_count=0,
            triangle_count=None,
            connected_triples=None,
            transitivity=None,
            mean_local_clustering=None,
            closure_threshold=closure_threshold,
            verdict="unknown",
            notes=("empty graph — nothing accumulated",),
        )

    adjacency: dict[str, set[str]] = {n: set() for n in node_set}
    seen_edges: set[frozenset[str]] = set()
    valid_edge_count = 0
    dangling = 0

    for edge in edges:
        if edge.source == edge.target:
            continue
        if edge.source not in node_set or edge.target not in node_set:
            dangling += 1
            continue
        canonical = frozenset((edge.source, edge.target))
        if canonical in seen_edges:
            continue
        seen_edges.add(canonical)
        adjacency[edge.source].add(edge.target)
        adjacency[edge.target].add(edge.source)
        valid_edge_count += 1

    orphan_node_count = sum(1 for n in node_set if not adjacency[n])

    if node_count == 1 and valid_edge_count == 0:
        return GraphTransitivityReport(
            node_count=node_count,
            edge_count=0,
            dangling_edge_count=dangling,
            orphan_node_count=1,
            triangle_count=None,
            connected_triples=None,
            transitivity=None,
            mean_local_clustering=None,
            closure_threshold=closure_threshold,
            verdict="singleton",
            notes=("one node, no edges — a lone entry",),
        )

    if valid_edge_count == 0:
        return GraphTransitivityReport(
            node_count=node_count,
            edge_count=0,
            dangling_edge_count=dangling,
            orphan_node_count=node_count,
            triangle_count=None,
            connected_triples=None,
            transitivity=None,
            mean_local_clustering=None,
            closure_threshold=closure_threshold,
            verdict="edgeless",
            notes=(
                f"{node_count} node(s), no edges — clustering undefined "
                "(no links to close)",
            ),
        )

    # Per-node: count triples (C(degree,2)) and closed triples (neighbor-pairs
    # that are themselves connected). Summing closed triples over all centers and
    # dividing by 3 yields the triangle count (each triangle centered 3 times).
    total_triples = 0
    total_closed = 0
    local_coeffs: list[float] = []

    for center in sorted(node_set):
        neighbors = sorted(adjacency[center])
        degree = len(neighbors)
        if degree < 2:
            continue
        pairs = degree * (degree - 1) // 2
        closed = 0
        for idx in range(degree):
            nb_a = neighbors[idx]
            row = adjacency[nb_a]
            for jdx in range(idx + 1, degree):
                if neighbors[jdx] in row:
                    closed += 1
        total_triples += pairs
        total_closed += closed
        local_coeffs.append(closed / pairs)

    if total_triples == 0:
        # Edges exist but every node has degree <= 1 (a disjoint union of pairs).
        return GraphTransitivityReport(
            node_count=node_count,
            edge_count=valid_edge_count,
            dangling_edge_count=dangling,
            orphan_node_count=orphan_node_count,
            triangle_count=0,
            connected_triples=0,
            transitivity=None,
            mean_local_clustering=None,
            closure_threshold=closure_threshold,
            verdict="pairwise",
            notes=(
                f"{node_count} node(s), {valid_edge_count} edge(s) but no node "
                "has >= 2 neighbors — a disjoint union of pairs; clustering "
                "undefined (no 2-path to close)",
            ),
        )

    triangle_count = total_closed // 3
    transitivity = total_closed / total_triples
    mean_local_clustering = sum(local_coeffs) / len(local_coeffs)

    if transitivity == 0.0:
        verdict = "open_weave"
    elif transitivity < closure_threshold:
        verdict = "loosely_woven"
    else:
        verdict = "tightly_woven"

    note_parts: list[str] = [
        f"{node_count} node(s), {valid_edge_count} edge(s); transitivity "
        f"{transitivity:.2f}, {triangle_count} triangle(s) over "
        f"{total_triples} connected triple(s), mean local clustering "
        f"{mean_local_clustering:.2f}",
        "transitivity is the fraction of length-2 paths (triples) that close "
        "into triangles — LOCAL cliquishness, bounded [0,1] and size-stable "
        "(unlike raw density); orthogonal to fragmentation #1995 (components), "
        "centrality #1996 (hub concentration), and diameter #2000 (stretch)",
        "a star has transitivity 0 (leaves never link); a clique has 1.0 "
        "(every triple closes) — neither reachability nor hub-ness nor stretch "
        "distinguishes them; only triangle closure does",
    ]
    if verdict == "open_weave":
        note_parts.append(
            "open_weave: 2-paths exist but NONE close — a measured zero (trees, "
            "stars, paths, squares); distinct from pairwise (no 2-paths) and "
            "edgeless (no edges)"
        )
    if orphan_node_count:
        note_parts.append(f"{orphan_node_count} orphan node(s) with zero edges")
    if dangling:
        note_parts.append(
            f"{dangling} dangling edge(s) to undeclared nodes"
        )
    note_parts.append(
        f"verdict {verdict}: closure_threshold {closure_threshold:.2f}; "
        "DESCRIPTIVE not normative — open_weave may be a legitimate linear "
        "structure (proof, timeline, derivation); the operator judges gap vs "
        "by-design"
    )

    return GraphTransitivityReport(
        node_count=node_count,
        edge_count=valid_edge_count,
        dangling_edge_count=dangling,
        orphan_node_count=orphan_node_count,
        triangle_count=triangle_count,
        connected_triples=total_triples,
        transitivity=transitivity,
        mean_local_clustering=mean_local_clustering,
        closure_threshold=closure_threshold,
        verdict=verdict,
        notes=tuple(note_parts),
    )
