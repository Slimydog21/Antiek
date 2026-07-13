r"""Graph diameter — how stretched is the accumulated knowledge graph?

Operator vision (ask #1): *"...the perfect knowledge graph/base and thought
partner/workstation..."* and *"...that substrate of information can be merged,
referenced, and leveraged..."* To navigate and REFERENCE the accumulating graph,
the operator needs to know how FAR APART the two most-separated findings are — how
many hops a traversal costs to get from one corner of the knowledge base to the
opposite corner. A knowledge graph can be fully connected (one component —
``knowledge_graph_fragmentation`` #1995 says ``connected``) and not hub-dominated
(influence spread — ``graph_centrality`` #1996 says ``distributed``) yet still be a
LONG THIN CHAIN: a sequence of findings each linked only to its neighbors, so the
two ends are dozens of hops apart. That shape is technically navigable but
contextually distant — the operator following a thread from one end reaches the
other only after a long unwoven traversal. Diameter — the longest shortest path —
is the graph-theoretic quantity that captures this STRETCH, and neither connectivity
(can I reach it at all?) nor centrality (is the path fragile?) measures it. The
operator's "navigate, reference, and leverage" directive needs all three: a
connected graph that is not hub-fragile AND not stretched into a thread.

**Genuinely distinct from the graph surface (load-bearing):**

* ``knowledge_graph_fragmentation`` (#1995): connected COMPONENTS — how many islands
  (macro connectivity / reachability). Union-Find partition of nodes.
* ``graph_centrality`` (#1996): node INFLUENCE concentration — is the graph
  hub-dominated or distributed? Freeman DEGREE centralization (local neighbor counts).
* **``graph_diameter`` (this):** global STRETCH — the longest shortest-path distance
  between any two mutually-reachable nodes (BFS all-pairs traversal).

They are orthogonal. A graph can be connected (#1995 ``connected``), distributed
(#1996 — every node degree <= 2, no hub), and STILL stretched into a path with
diameter = n-1 (THIS ``stretched``): a long chain that is reachable, robust, yet
contextually long to traverse. The reverse holds too: a connected distributed
CLIQUE has diameter 1 (THIS ``compact``) — everything directly interlinked. Neither
fragmentation nor centrality distinguishes the chain from the clique; only the
shortest-path traversal does. Connectivity asks "can I reach it?", centrality asks
"is the path fragile?", diameter asks "how LONG is the longest path?".

**The measurement (hard to vary).** Given the accumulated node set and undirected
edge set, build the adjacency map (self-loops ignored, duplicate edges merged,
dangling edges to undeclared nodes surfaced not coerced — mirroring #1995/#1996).
Then compute all-pairs shortest paths via BFS from every node (BFS yields the exact
shortest hop count in an unweighted graph):

* ``eccentricity`` of a node = the greatest shortest-path distance from it to any
  other MUTUALLY-REACHABLE node.
* ``diameter`` = the maximum eccentricity = the longest shortest path = the stretch.
* ``radius`` = the minimum eccentricity = the core spread (the best-case traversal
  from the most central node). Always ``radius <= diameter <= 2 * radius``.
* ``mean_eccentricity`` = average eccentricity (how stretched the typical node is).
* ``diameter_path_endpoints`` = the two node ids realizing the diameter (auditable —
  the most-separated findings, so the operator can inspect the thread between them).
* ``component_diameters`` = the diameter of each connected component, sorted
  descending (auditable — the full stretch distribution, mirroring #1995's
  ``component_sizes``).
* ``connected`` = whether the whole graph is one component (so the operator knows
  whether the diameter spans the entire base or is the largest island's reach;
  cross-component pairs have NO path — infinite distance, honestly flagged).

**Disconnected graphs (load-bearing honesty).** When the graph is disconnected,
some node pairs have no path between them. The strict graph-theoretic diameter is
then infinite, which is not actionable. This module reports ``diameter`` as the
longest shortest path among MUTUALLY-REACHABLE pairs (the largest intra-component
stretch) and sets ``connected = False`` so the operator knows unreachable pairs
also exist. The notes carry this verbatim. The module never fabricates a finite
diameter for an unreachable pair.

**Verdict (distinct honest states, never collapsed, DESCRIPTIVE not normative):**

* zero nodes -> ``unknown`` (nothing accumulated — defer, never fabricated).
* exactly one node, zero edges -> ``singleton`` (a lone entry — honest base case).
* >= 2 nodes, zero valid edges -> ``edgeless`` (no paths to measure — diameter
  undefined without edges; deferred honestly, never fabricated ``compact``).
* ``diameter <= compact_threshold`` (default 4) -> ``compact`` (tightly woven — any
  finding reachable in a few hops; the dense-interlinked "infinite information
  platform" that is easy to navigate).
* ``compact_threshold < diameter <= stretch_threshold`` (default 12) -> ``extended``
  (moderate stretch — the base spans several conceptual hops; the common growth shape).
* ``diameter > stretch_threshold`` -> ``stretched`` (long unwoven chain — the two
  most-separated findings are far apart; the base is a thread, not a mesh; suggests
  thin linking even when connected).

DESCRIPTIVE NOT NORMATIVE: ``stretched`` does NOT mean "broken" — a long chain may
be a legitimate sequential argument (a proof, a timeline, a derivation lineage). The
operator judges whether the stretch is load-bearing-by-design (a thread that SHOULD
be linear) or a gap (findings that COULD link more directly but don't). The verdict
describes STRETCH topology; the operator judges value.

**Honesty rules (load-bearing):**

* ``unknown`` never fabricates when the graph is empty.
* ``edgeless`` is its own honest verdict: with zero edges there are no paths —
  diameter is undefined, never fabricated as ``compact`` (a degenerate 0 would be a
  lie; diameter 1 needs a clique, diameter 0 is a single node).
* ``singleton`` is its own base case (one node — distinct from ``unknown`` and from
  ``edgeless`` which needs >= 2 nodes).
* ``diameter`` / ``radius`` / ``mean_eccentricity`` are ``None`` when ``unknown`` /
  ``singleton`` / ``edgeless`` (defer — never ``0``).
* ``diameter_path_endpoints`` is ``()`` when no diameter is realized.
* ``component_diameters`` is ``()`` when no component has a measurable diameter
  (every component a lone node); otherwise one entry per component with >= 2 nodes.
* ``connected`` is ``None`` when ``unknown`` / ``singleton`` (defer — reachability
  undefined for a non-graph); ``False`` only when measured-disconnected.
* absolute hop-count thresholds (not normalized): diameter is the actual traversal
  cost in hops, the navigational quantity the operator cares about — normalizing
  would obscure it (a 4-hop traversal is 4 hops whether the base has 8 or 800 nodes).
* orphan nodes (zero edges) surfaced as ``orphan_node_count`` (mirrors #1995
  accountability — the operator sees the isolated findings).
* self-loops ignored; duplicate edges merged (a repeated link is one relationship);
  edges referencing undeclared nodes surface as ``dangling_edge_count`` (never
  coerced — mirrors #1995/#1996 integrity posture).
* ``authority = "advisory"`` — pure layer proposes; operator consent executes.
* deterministic + immutable (frozen dataclasses; sorted, reproducible output).
* import-free of off-main siblings (own ``GraphEdge`` shape; route layer adapts 1:1).
"""

from __future__ import annotations

from collections import deque
from collections.abc import Sequence
from dataclasses import dataclass

__all__ = [
    "GraphEdge",
    "GraphDiameterReport",
    "measure_graph_diameter",
]

_DEFAULT_COMPACT_THRESHOLD = 4
_DEFAULT_STRETCH_THRESHOLD = 12


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
class GraphDiameterReport:
    """Stretch topology of the accumulated knowledge graph (advisory)."""

    node_count: int
    edge_count: int
    dangling_edge_count: int
    orphan_node_count: int
    component_count: int
    connected: bool | None
    diameter: int | None
    radius: int | None
    mean_eccentricity: float | None
    diameter_path_endpoints: tuple[str, ...]
    component_diameters: tuple[int, ...]
    compact_threshold: int
    stretch_threshold: int
    verdict: str
    notes: tuple[str, ...]
    authority: str = "advisory"


def _bfs_eccentricity(
    start: str, adjacency: dict[str, set[str]]
) -> tuple[int, str]:
    """Breadth-first search from ``start``; return (eccentricity, farthest node).

    Eccentricity is the greatest shortest-path distance from ``start`` to any other
    reachable node. The farthest node is the last-discovered node at that maximum
    distance (deterministic under sorted neighbor traversal).
    """
    dist: dict[str, int] = {start: 0}
    queue: deque[str] = deque([start])
    farthest = start
    farthest_dist = 0
    while queue:
        current = queue.popleft()
        current_dist = dist[current]
        for neighbor in sorted(adjacency[current]):
            if neighbor not in dist:
                reached = current_dist + 1
                dist[neighbor] = reached
                queue.append(neighbor)
                if reached > farthest_dist:
                    farthest_dist = reached
                    farthest = neighbor
    return farthest_dist, farthest


def measure_graph_diameter(
    nodes: Sequence[str],
    edges: Sequence[GraphEdge],
    *,
    compact_threshold: int = _DEFAULT_COMPACT_THRESHOLD,
    stretch_threshold: int = _DEFAULT_STRETCH_THRESHOLD,
) -> GraphDiameterReport:
    r"""Measure the stretch (longest shortest path) of the knowledge graph.

    ``nodes`` are every node id in the accumulated substrate. ``edges`` are every
    undirected link (the route layer supplies all edge types as a flat list).
    Returns a :class:`GraphDiameterReport` with stretch statistics and verdict.

    Raises:
        ValueError: if ``compact_threshold < 1`` or
            ``stretch_threshold < compact_threshold``.
    """
    if compact_threshold < 1:
        raise ValueError(
            f"compact_threshold must be >= 1; got {compact_threshold}"
        )
    if stretch_threshold < compact_threshold:
        raise ValueError(
            f"stretch_threshold ({stretch_threshold}) must be >= "
            f"compact_threshold ({compact_threshold})"
        )

    node_set = set(nodes)
    node_count = len(node_set)

    if node_count == 0:
        return GraphDiameterReport(
            node_count=0,
            edge_count=0,
            dangling_edge_count=0,
            orphan_node_count=0,
            component_count=0,
            connected=None,
            diameter=None,
            radius=None,
            mean_eccentricity=None,
            diameter_path_endpoints=(),
            component_diameters=(),
            compact_threshold=compact_threshold,
            stretch_threshold=stretch_threshold,
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
        return GraphDiameterReport(
            node_count=node_count,
            edge_count=0,
            dangling_edge_count=dangling,
            orphan_node_count=1,
            component_count=1,
            connected=None,
            diameter=None,
            radius=None,
            mean_eccentricity=None,
            diameter_path_endpoints=(),
            component_diameters=(),
            compact_threshold=compact_threshold,
            stretch_threshold=stretch_threshold,
            verdict="singleton",
            notes=("one node, no edges — a lone entry",),
        )

    if valid_edge_count == 0:
        return GraphDiameterReport(
            node_count=node_count,
            edge_count=0,
            dangling_edge_count=dangling,
            orphan_node_count=node_count,
            component_count=node_count,
            connected=False,
            diameter=None,
            radius=None,
            mean_eccentricity=None,
            diameter_path_endpoints=(),
            component_diameters=(),
            compact_threshold=compact_threshold,
            stretch_threshold=stretch_threshold,
            verdict="edgeless",
            notes=(
                f"{node_count} node(s), no edges — diameter undefined "
                "(no paths to measure)",
            ),
        )

    # Connected components via flood-fill BFS.
    component_of: dict[str, int] = {}
    components: list[set[str]] = []
    for seed in sorted(node_set):
        if seed in component_of:
            continue
        idx = len(components)
        comp: set[str] = {seed}
        component_of[seed] = idx
        flood: deque[str] = deque([seed])
        while flood:
            current = flood.popleft()
            for neighbor in adjacency[current]:
                if neighbor not in comp:
                    comp.add(neighbor)
                    component_of[neighbor] = idx
                    flood.append(neighbor)
        components.append(comp)

    component_count = len(components)
    connected = component_count == 1

    # All-pairs shortest paths via per-node BFS. Eccentricity = farthest reachable.
    eccentricity: dict[str, int] = {}
    diameter = 0
    diameter_endpoints: tuple[str, ...] = ()
    for start in sorted(node_set):
        farthest_dist, farthest = _bfs_eccentricity(start, adjacency)
        if farthest != start:
            eccentricity[start] = farthest_dist
            if farthest_dist > diameter:
                diameter = farthest_dist
                diameter_endpoints = (start, farthest)

    ecc_values = list(eccentricity.values())
    radius = min(ecc_values)
    mean_eccentricity = sum(ecc_values) / len(ecc_values)

    comp_diameters: list[int] = []
    for comp in components:
        comp_ecc = [eccentricity[n] for n in comp if n in eccentricity]
        if comp_ecc:
            comp_diameters.append(max(comp_ecc))
    comp_diameters.sort(reverse=True)
    component_diameters = tuple(comp_diameters)

    if diameter <= compact_threshold:
        verdict = "compact"
    elif diameter <= stretch_threshold:
        verdict = "extended"
    else:
        verdict = "stretched"

    note_parts: list[str] = [
        f"{node_count} node(s), {valid_edge_count} edge(s), "
        f"{component_count} component(s); diameter {diameter} hop(s), "
        f"radius {radius}, mean eccentricity {mean_eccentricity:.2f}",
        f"diameter realized by {diameter_endpoints[0]} -> "
        f"{diameter_endpoints[1]} (the most-separated findings)",
        "diameter is the longest shortest-path between MUTUALLY-REACHABLE nodes; "
        "if disconnected, cross-component pairs have no path (infinite distance) — "
        "see the connected flag",
    ]
    if not connected:
        note_parts.append(
            f"disconnected ({component_count} components) — diameter spans only "
            "reachable pairs; unreachable pairs have no finite path"
        )
    if orphan_node_count:
        note_parts.append(f"{orphan_node_count} orphan node(s) with zero edges")
    if dangling:
        note_parts.append(
            f"{dangling} dangling edge(s) to undeclared nodes"
        )
    note_parts.append(
        f"verdict {verdict}: compact_threshold {compact_threshold}, "
        f"stretch_threshold {stretch_threshold} (absolute hop counts — the actual "
        "traversal cost, not normalized)"
    )

    return GraphDiameterReport(
        node_count=node_count,
        edge_count=valid_edge_count,
        dangling_edge_count=dangling,
        orphan_node_count=orphan_node_count,
        component_count=component_count,
        connected=connected,
        diameter=diameter,
        radius=radius,
        mean_eccentricity=mean_eccentricity,
        diameter_path_endpoints=diameter_endpoints,
        component_diameters=component_diameters,
        compact_threshold=compact_threshold,
        stretch_threshold=stretch_threshold,
        verdict=verdict,
        notes=tuple(note_parts),
    )
