r"""Knowledge-graph fragmentation — is the accumulated substrate one graph or islands?

Operator vision (ask #1): *"...build my comprehensive reading, research, and writing
platform to be the perfect knowledge graph/base..."* The platform's compounding
value lives in its accumulated GRAPH — insights, questions, investigations, and
artifacts connected by derivation, cross-reference, provenance, and merge edges. The
operator's "infinite information platform" is only infinite if it is a CONNECTED
substrate: each new finding should link into the existing graph, growing ONE
navigable structure. A knowledge base that fragments into disconnected islands never
compounds — it is a pile of isolated notes, not a graph. Fragmentation is the
structural failure mode that defeats the "knowledge graph/base" vision at the
FOUNDATIONAL level.

**Genuinely distinct from every existing connectivity/coherence axis:**

* ``twin_internal_coherence`` (#1988): do ONE TWIN's insights connect to each other
  (within-document, edges = that twin's insight subject-overlap). Single-twin scope.
* ``connectedness`` (#1949): how does ONE ARTIFACT relate to priors via the 4
  cross-reference edge types (single-artifact edge count to prior work).
* ``trajectory`` (#1952): ONE investigation's recursion-TREE topology (depth,
  branching, resolution rate).
* ``collective_coherence`` (#1976): do the N INPUT instances of ONE merge share a
  subject (within-one-merge).

ALL operate on a SINGLE artifact, twin, or investigation. NONE measures the GLOBAL
accumulated graph's connected-component structure across the ENTIRE substrate. This
is the only axis that takes the WHOLE edge set (every derivation / cross-reference /
provenance / merge link across all investigations and artifacts) and partitions it
into connected components via Union-Find — revealing whether the knowledge base is
ONE growing structure or N disconnected islands.

**The load-bearing distinction (why global != aggregation of single axes):** a
knowledge base where every individual artifact is ``well_integrated`` (#1949 — each
has edges to priors) and every twin is ``coherent`` (#1988 — internally connected)
can STILL be globally fragmented: two clusters A-B-C and D-E-F where everything
connects WITHIN each cluster but the clusters never cross-reference. No single-artifact
axis sees the cross-cluster gap; only the GLOBAL component partition does. And the
reverse: global cohesion does not guarantee per-artifact integration. They are
independent — both must hold for the substrate to truly compound.

**The measurement (hard to vary).** Given the accumulated node set (every insight /
question / artifact id that exists) and the edge set (every undirected link between
two nodes — derivation, cross-reference, provenance, merge — the route layer supplies
all edge types as a flat id-pair list), partition the nodes into connected components
via Union-Find:

* ``node_count`` — total nodes in the graph.
* ``edge_count`` — total undirected edges.
* ``component_count`` — connected components (islands).
* ``orphan_node_count`` — nodes with degree zero (no edges — pure islands, the
  worst-case fragmentation; surfaced separately for accountability).
* ``orphan_fraction`` — orphan_node_count / node_count.
* ``largest_component_fraction`` — the size of the biggest component / node_count
  (does ONE dominant structure span most of the base, or is mass spread evenly across
  many small islands?).
* ``mean_component_size`` — node_count / component_count (the typical island size).
* ``component_sizes`` — every component's size, sorted descending (auditable: the
  operator sees the full island-size distribution, no black-box fragmentation).

**Verdict (distinct honest states, never collapsed, DESCRIPTIVE not normative):**

* zero nodes -> ``unknown`` (nothing accumulated — defer, never fabricated).
* exactly one node, zero edges -> ``singleton`` (a lone entry — not fragmented, not
  connected; an honest base case distinct from ``unknown``).
* ``component_count == 1`` AND ``node_count >= 2`` -> ``connected`` (the whole base
  is ONE spanning component — every finding reachable from every other; the
  compounding ideal). A REAL measured verdict, NOT the default.
* ``largest_component_fraction`` < ``dominance_floor`` (default ``0.50``) -> ``fragmented``
  (no component dominates — mass spread across many islands; the structure never
  consolidated). This is the failure mode: research threads that never cross-pollinate.
* otherwise (one dominant component but with outliers) -> ``cohesive`` (a large core
  connected structure plus some outlying islands — the common healthy shape as the
  base grows; new threads link in over time).

DESCRIPTIVE NOT NORMATIVE: ``fragmented`` does NOT mean "broken" — the islands may
be genuinely unrelated research threads (legitimate separation). The operator judges
whether the fragmentation is a missed cross-connection (a failure to engage prior
work) or legitimate scope separation. The verdict describes GLOBAL topology; the
operator judges value (mirrors #1949's honesty posture).

**Honesty rules (load-bearing):**

* ``unknown`` never fabricates when the graph is empty (nothing accumulated).
* ``connected`` is a REAL measured verdict (Union-Find confirmed one spanning
  component with >= 2 nodes), NOT the default — ``unknown`` means nothing-to-measure;
  ``connected`` means measured-and-spanning. Never collapsed. ``singleton`` (one node,
  no edges) is its own honest base case, distinct from both.
* ``orphan_fraction`` / ``largest_component_fraction`` / ``mean_component_size`` are
  ``None`` when ``unknown`` (defer — never ``0.0``).
* orphan nodes (degree zero) are surfaced as ``orphan_node_count`` (the worst-case
  island — a finding connected to nothing); never silently dropped.
* every component size carried verbatim in ``component_sizes`` (auditable — the full
  island distribution, no black-box "fragmented" verdict).
* self-loops (a node linked to itself) are ignored (a self-loop does not connect two
  distinct nodes — never counted as an edge that reduces fragmentation).
* duplicate edges de-duplicated (a repeated link is one connection, not many).
* edges referencing undeclared nodes are NOT coerced — they surface as a
  ``dangling_edge_count`` (a link to a node outside the declared set; an integrity
  oddity surfaced for review, never silently invented).
* ``authority = "advisory"`` — pure layer proposes; operator consent executes.
* deterministic + immutable (frozen dataclasses; sorted, reproducible output).
* import-free of off-main siblings (own ``GraphEdge`` shape; the route layer adapts
  1:1 from the accumulated cross-reference / derivation / provenance / merge edges).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

__all__ = [
    "GraphEdge",
    "GraphFragmentationReport",
    "measure_graph_fragmentation",
]

_DEFAULT_DOMINANCE_FLOOR = 0.50


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
class GraphFragmentationReport:
    """The global knowledge-graph fragmentation verdict. Advisory, pure.

    Attributes:
        node_count: total declared nodes.
        edge_count: distinct valid undirected edges (self-loops/dupes removed).
        dangling_edge_count: edges referencing an undeclared node (surfaced).
        component_count: connected components (islands).
        orphan_node_count: nodes with degree zero.
        orphan_fraction: orphan_node_count / node_count; ``None`` when ``unknown``.
        largest_component_fraction: biggest component / node_count; ``None`` when
            ``unknown``.
        mean_component_size: node_count / component_count; ``None`` when ``unknown``.
        component_sizes: every component's size, sorted descending (auditable).
        dominance_floor: largest-fraction floor for the ``fragmented`` verdict.
        verdict: ``connected`` / ``cohesive`` / ``fragmented`` / ``singleton`` /
            ``unknown``.
        notes: human-readable accountability strings.
        authority: always ``"advisory"``.
    """

    node_count: int
    edge_count: int
    dangling_edge_count: int
    component_count: int
    orphan_node_count: int
    orphan_fraction: float | None
    largest_component_fraction: float | None
    mean_component_size: float | None
    component_sizes: tuple[int, ...]
    dominance_floor: float
    verdict: str
    notes: tuple[str, ...]
    authority: str = "advisory"


class _UnionFind:
    """Minimal Union-Find for connected-component partitioning."""

    __slots__ = ("_parent", "_rank")

    def __init__(self, nodes: Sequence[str]) -> None:
        self._parent: dict[str, str] = {n: n for n in nodes}
        self._rank: dict[str, int] = {n: 0 for n in nodes}

    def find(self, x: str) -> str:
        root = x
        while self._parent[root] != root:
            root = self._parent[root]
        # Path compression.
        while self._parent[x] != root:
            self._parent[x], x = root, self._parent[x]
        return root

    def union(self, a: str, b: str) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra == rb:
            return
        if self._rank[ra] < self._rank[rb]:
            ra, rb = rb, ra
        self._parent[rb] = ra
        if self._rank[ra] == self._rank[rb]:
            self._rank[ra] += 1


def measure_graph_fragmentation(
    nodes: Sequence[str],
    edges: Sequence[GraphEdge],
    *,
    dominance_floor: float = _DEFAULT_DOMINANCE_FLOOR,
) -> GraphFragmentationReport:
    r"""Measure the global connected-component structure of the knowledge graph.

    ``nodes`` are every node id in the accumulated substrate. ``edges`` are every
    undirected link (the route layer supplies all edge types as a flat list).
    Returns a :class:`GraphFragmentationReport` with component statistics and verdict.

    Raises:
        ValueError: if ``dominance_floor`` is outside ``(0.0, 1.0]``.
    """
    if not 0.0 < dominance_floor <= 1.0:
        raise ValueError(
            f"dominance_floor must be in (0.0, 1.0]; got {dominance_floor}"
        )

    node_set = set(nodes)
    node_count = len(node_set)

    if node_count == 0:
        return GraphFragmentationReport(
            node_count=0,
            edge_count=0,
            dangling_edge_count=0,
            component_count=0,
            orphan_node_count=0,
            orphan_fraction=None,
            largest_component_fraction=None,
            mean_component_size=None,
            component_sizes=(),
            dominance_floor=dominance_floor,
            verdict="unknown",
            notes=("empty graph — nothing accumulated",),
        )

    uf = _UnionFind(sorted(node_set))
    degree: dict[str, int] = {n: 0 for n in node_set}

    seen_edges: set[frozenset[str]] = set()
    valid_edge_count = 0
    dangling = 0

    for edge in edges:
        # Self-loops do not connect two distinct nodes — ignore.
        if edge.source == edge.target:
            continue
        # Edges referencing undeclared nodes are surfaced, not coerced.
        if edge.source not in node_set or edge.target not in node_set:
            dangling += 1
            continue
        canonical = frozenset((edge.source, edge.target))
        if canonical in seen_edges:
            continue
        seen_edges.add(canonical)
        uf.union(edge.source, edge.target)
        degree[edge.source] += 1
        degree[edge.target] += 1
        valid_edge_count += 1

    # Component sizes via root grouping.
    comp_buckets: dict[str, int] = {}
    for n in node_set:
        root = uf.find(n)
        comp_buckets[root] = comp_buckets.get(root, 0) + 1

    component_sizes = tuple(sorted(comp_buckets.values(), reverse=True))
    component_count = len(component_sizes)
    orphan_node_count = sum(1 for n in node_set if degree[n] == 0)
    largest_component = component_sizes[0]

    orphan_fraction = orphan_node_count / node_count
    largest_component_fraction = largest_component / node_count
    mean_component_size = node_count / component_count

    # Verdict.
    if node_count == 1 and valid_edge_count == 0:
        verdict = "singleton"
    elif component_count == 1:
        verdict = "connected"
    elif largest_component_fraction < dominance_floor:
        verdict = "fragmented"
    else:
        verdict = "cohesive"

    note_parts = [
        f"{node_count} node(s), {component_count} component(s); "
        f"largest covers {largest_component_fraction:.2f} of the base",
    ]
    if orphan_node_count:
        note_parts.append(
            f"{orphan_node_count} orphan node(s) with zero edges"
        )
    if dangling:
        note_parts.append(
            f"{dangling} dangling edge(s) to undeclared nodes"
        )

    return GraphFragmentationReport(
        node_count=node_count,
        edge_count=valid_edge_count,
        dangling_edge_count=dangling,
        component_count=component_count,
        orphan_node_count=orphan_node_count,
        orphan_fraction=orphan_fraction,
        largest_component_fraction=largest_component_fraction,
        mean_component_size=mean_component_size,
        component_sizes=component_sizes,
        dominance_floor=dominance_floor,
        verdict=verdict,
        notes=tuple(note_parts),
    )
