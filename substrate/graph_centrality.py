r"""Graph centrality — is the knowledge graph's influence concentrated or spread?

Operator vision (ask #1): *"...the perfect knowledge graph/base and thought
partner/workstation..."* and *"...that substrate of information can be merged,
referenced, and leveraged..."* To REFERENCE and navigate the accumulating graph,
the operator needs to know where the INFLUENTIAL nodes are — which findings are the
load-bearing hubs everything else routes through. A knowledge graph can be fully
connected (one component — ``knowledge_graph_fragmentation`` #1995 says ``connected``)
yet DOMINATED by a single hub: one foundational insight that every other finding
references. That shape is a single-point-of-failure — remove or revise the hub and
the whole structure's navigability degrades. The opposite shape — influence evenly
distributed across many nodes — is robust: no one node is load-bearing. Concentration
of influence is a DIFFERENT graph property from connectivity, and the operator's
"reference and leverage" directive needs both: a connected graph (reachability) that
is ALSO not hub-fragile (robustness).

**Genuinely distinct from the graph surface:**

* ``knowledge_graph_fragmentation`` (#1995): connected COMPONENTS — how many islands
  (macro connectivity / reachability). Union-Find partition.
* **``graph_centrality`` (this):** node INFLUENCE distribution — is the graph
  hub-dominated (concentrated, fragile) or distributed (robust)? Freeman degree
  centralization.

They are orthogonal: a graph can be fully connected (one component — #1995
``connected``) yet hub-dominated (THIS ``hub_dominated`` — a star where one node
connects to all others, every path routes through it), OR connected AND distributed
(THIS ``distributed`` — a mesh where influence spreads evenly, no single point of
failure). Connectivity says "can I reach it?"; centrality says "is the path fragile?"
A connected-but-hub-dominated graph is reachable but brittle; a connected-and-
distributed graph is both reachable and robust. The operator needs both for a
trustworthy navigable knowledge base.

**The measurement (hard to vary).** Given the accumulated node set and undirected
edge set, compute each node's DEGREE (number of distinct neighbors) and DEGREE
CENTRALITY (degree / (node_count - 1) — the fraction of the graph a node directly
connects to). Then FREEMAN DEGREE CENTRALIZATION — the canonical graph-theoretic
statistic for influence concentration:

``C = sum(max_degree - degree_i for all i) / ((node_count - 1) * (node_count - 2))``

The denominator is the maximum possible sum of degree differences (achieved by a STAR
graph — one hub connected to all others, all others connected only to the hub). So
``C`` normalizes to ``[0, 1]``: ``1.0`` is a perfect star (one node dominates —
maximal concentration), ``0.0`` is a regular graph (every node the same degree —
maximal spread). This is genuinely different machinery from Union-Find components
(#1995): centralization measures the SHAPE of the degree distribution, not its
partition into components.

* ``node_count``, ``edge_count`` (distinct valid edges — self-loops/dupes removed).
* ``max_degree``, ``max_degree_centrality`` (the dominant hub's reach).
* ``hub_node_ids`` — nodes whose degree centrality >= ``hub_threshold`` (default
  ``0.50`` — connects to at least half the graph; auditable: the load-bearing nodes).
* ``mean_degree_centrality`` — the average influence.
* ``degree_centralization`` — Freeman's concentration statistic in ``[0, 1]``;
  ``None`` when not measurable (defer — see honesty rules).

**Verdict (distinct honest states, never collapsed, DESCRIPTIVE not normative):**

* zero nodes -> ``unknown`` (nothing accumulated — defer, never fabricated).
* one node, zero edges -> ``singleton`` (a lone entry — honest base case).
* zero edges with >= 2 nodes -> ``edgeless`` (no influence to measure — centralization
  undefined without edges; deferred honestly, never fabricated ``distributed``).
* ``degree_centralization >= high_concentration`` (default ``0.50``) -> ``hub_dominated``
  (a star-like shape — influence concentrated on a hub; the fragile single-point-of-
  failure shape).
* ``degree_centralization <= low_concentration`` (default ``0.15``) -> ``distributed``
  (influence evenly spread — robust, no single point of failure).
* otherwise -> ``concentrated`` (some hub tendency but not extreme — the common
  growth shape as a few key findings gain references).

DESCRIPTIVE NOT NORMATIVE: ``hub_dominated`` does NOT mean "bad" — a hub may be a
legitimate foundational finding everything rightly builds on (a load-bearing theorem,
a canonical source). The operator judges whether the hub is load-bearing-by-design
(healthy) or a fragile dependency (remove it and navigability collapses). The verdict
describes INFLUENCE topology; the operator judges value.

**Honesty rules (load-bearing):**

* ``unknown`` never fabricates when the graph is empty.
* ``edgeless`` is its own honest verdict: with zero edges there is no influence to
  concentrate — centralization is undefined, never fabricated as ``distributed`` (0.0
  centralization on an edgeless graph is a degenerate division, not "even spread").
* ``singleton`` is its own base case (one node — distinct from ``unknown`` and from
  ``edgeless`` which needs >= 2 nodes).
* ``distributed`` is a REAL measured verdict (>= 2 nodes, edges present, low
  centralization), NOT the default — ``edgeless`` and ``unknown`` are the defer
  states; ``distributed`` means measured-and-spread. Never collapsed.
* ``degree_centralization`` / ``max_degree_centrality`` / ``mean_degree_centrality``
  are ``None`` when ``unknown`` / ``singleton`` / ``edgeless`` (defer — never
  ``0.0``).
* hub nodes surfaced as ``hub_node_ids`` (the load-bearing nodes — auditable; the
  operator sees exactly which findings carry the graph's navigability).
* self-loops ignored; duplicate edges deduplicated (a repeated link is one influence
  relationship, not many).
* edges referencing undeclared nodes surface as ``dangling_edge_count`` (never
  coerced — mirrors #1995's integrity posture).
* centralization requires ``node_count >= 3`` (the denominator
  ``(n-1)(n-2)`` is zero for n < 3; n=2 is a trivial symmetric pair — deferred, not
  fabricated).
* ``authority = "advisory"`` — pure layer proposes; operator consent executes.
* deterministic + immutable (frozen dataclasses; sorted, reproducible output).
* import-free of off-main siblings (own ``GraphEdge`` shape; route layer adapts 1:1).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

__all__ = [
    "GraphEdge",
    "GraphCentralityReport",
    "measure_graph_centrality",
]

_DEFAULT_HUB_THRESHOLD = 0.50
_DEFAULT_HIGH_CONCENTRATION = 0.50
_DEFAULT_LOW_CONCENTRATION = 0.15


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
class GraphCentralityReport:
    """The global knowledge-graph influence-concentration verdict. Advisory, pure.

    Attributes:
        node_count: total declared nodes.
        edge_count: distinct valid undirected edges (self-loops/dupes removed).
        dangling_edge_count: edges referencing an undeclared node (surfaced).
        max_degree: the dominant hub's degree.
        max_degree_centrality: hub's degree / (node_count - 1); ``None`` when deferred.
        mean_degree_centrality: average influence; ``None`` when deferred.
        hub_node_ids: nodes with degree centrality >= hub_threshold, sorted.
        degree_centralization: Freeman concentration in [0,1]; ``None`` when deferred.
        hub_threshold: degree-centrality floor for the hub set.
        high_concentration: centralization floor for ``hub_dominated``.
        low_concentration: centralization ceiling for ``distributed``.
        verdict: ``hub_dominated`` / ``concentrated`` / ``distributed`` / ``edgeless``
            / ``singleton`` / ``unknown``.
        notes: human-readable accountability strings.
        authority: always ``"advisory"``.
    """

    node_count: int
    edge_count: int
    dangling_edge_count: int
    max_degree: int
    max_degree_centrality: float | None
    mean_degree_centrality: float | None
    hub_node_ids: tuple[str, ...]
    degree_centralization: float | None
    hub_threshold: float
    high_concentration: float
    low_concentration: float
    verdict: str
    notes: tuple[str, ...]
    authority: str = "advisory"


def measure_graph_centrality(
    nodes: Sequence[str],
    edges: Sequence[GraphEdge],
    *,
    hub_threshold: float = _DEFAULT_HUB_THRESHOLD,
    high_concentration: float = _DEFAULT_HIGH_CONCENTRATION,
    low_concentration: float = _DEFAULT_LOW_CONCENTRATION,
) -> GraphCentralityReport:
    r"""Measure the global influence-concentration structure of the knowledge graph.

    ``nodes`` are every node id in the accumulated substrate. ``edges`` are every
    undirected link. Returns a :class:`GraphCentralityReport` with degree statistics,
    Freeman centralization, and verdict.

    Raises:
        ValueError: if thresholds are outside ``(0.0, 1.0]`` or
            ``low_concentration >= high_concentration``.
    """
    for label, val in (
        ("hub_threshold", hub_threshold),
        ("high_concentration", high_concentration),
        ("low_concentration", low_concentration),
    ):
        if not 0.0 < val <= 1.0:
            raise ValueError(f"{label} must be in (0.0, 1.0]; got {val}")
    if low_concentration >= high_concentration:
        raise ValueError(
            f"low_concentration ({low_concentration}) must be < "
            f"high_concentration ({high_concentration})"
        )

    node_set = set(nodes)
    node_count = len(node_set)

    if node_count == 0:
        return GraphCentralityReport(
            node_count=0,
            edge_count=0,
            dangling_edge_count=0,
            max_degree=0,
            max_degree_centrality=None,
            mean_degree_centrality=None,
            hub_node_ids=(),
            degree_centralization=None,
            hub_threshold=hub_threshold,
            high_concentration=high_concentration,
            low_concentration=low_concentration,
            verdict="unknown",
            notes=("empty graph — nothing accumulated",),
        )

    degree: dict[str, set[str]] = {n: set() for n in node_set}
    seen_edges: set[frozenset[str]] = set()
    dangling = 0
    valid_edge_count = 0

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
        degree[edge.source].add(edge.target)
        degree[edge.target].add(edge.source)
        valid_edge_count += 1

    if node_count == 1 and valid_edge_count == 0:
        return GraphCentralityReport(
            node_count=1,
            edge_count=0,
            dangling_edge_count=dangling,
            max_degree=0,
            max_degree_centrality=None,
            mean_degree_centrality=None,
            hub_node_ids=(),
            degree_centralization=None,
            hub_threshold=hub_threshold,
            high_concentration=high_concentration,
            low_concentration=low_concentration,
            verdict="singleton",
            notes=("one node, no edges — honest base case",),
        )

    if valid_edge_count == 0:
        # >= 2 nodes but zero edges: no influence to concentrate — defer honestly.
        return GraphCentralityReport(
            node_count=node_count,
            edge_count=0,
            dangling_edge_count=dangling,
            max_degree=0,
            max_degree_centrality=None,
            mean_degree_centrality=None,
            hub_node_ids=(),
            degree_centralization=None,
            hub_threshold=hub_threshold,
            high_concentration=high_concentration,
            low_concentration=low_concentration,
            verdict="edgeless",
            notes=("no edges — influence concentration not measurable",),
        )

    degree_counts = {n: len(neigh) for n, neigh in degree.items()}
    max_degree = max(degree_counts.values())

    # Degree centrality per node = degree / (n - 1).
    denom_centrality = node_count - 1
    centralities = {n: d / denom_centrality for n, d in degree_counts.items()}
    max_degree_centrality = max(centralities.values())
    mean_degree_centrality = sum(centralities.values()) / node_count

    hub_node_ids = tuple(
        sorted(n for n, c in centralities.items() if c >= hub_threshold)
    )

    # Freeman degree centralization — requires n >= 3 (denominator (n-1)(n-2) > 0).
    if node_count >= 3:
        centralization = sum(max_degree - d for d in degree_counts.values()) / (
            (node_count - 1) * (node_count - 2)
        )
    else:
        # n == 2: trivial symmetric pair — centralization deferred.
        centralization = None

    note_parts = [
        f"{node_count} node(s), {valid_edge_count} edge(s); "
        f"max degree {max_degree}",
    ]
    if hub_node_ids:
        note_parts.append(
            f"{len(hub_node_ids)} hub node(s) at centrality >= {hub_threshold:.2f}"
        )

    if centralization is None:
        # n == 2 case: with one edge both nodes share equal degree (balanced
        # influence). Concentration is about degree INEQUALITY; a symmetric pair
        # has none -> distributed. Freeman centralization itself is undefined here.
        verdict = "distributed"
        note_parts.append("two-node graph — symmetric, centralization deferred")
    elif centralization >= high_concentration:
        verdict = "hub_dominated"
        note_parts.append(f"centralization {centralization:.4f} — hub-dominated")
    elif centralization <= low_concentration:
        verdict = "distributed"
        note_parts.append(f"centralization {centralization:.4f} — distributed")
    else:
        verdict = "concentrated"
        note_parts.append(f"centralization {centralization:.4f}")

    return GraphCentralityReport(
        node_count=node_count,
        edge_count=valid_edge_count,
        dangling_edge_count=dangling,
        max_degree=max_degree,
        max_degree_centrality=max_degree_centrality,
        mean_degree_centrality=mean_degree_centrality,
        hub_node_ids=hub_node_ids,
        degree_centralization=centralization,
        hub_threshold=hub_threshold,
        high_concentration=high_concentration,
        low_concentration=low_concentration,
        verdict=verdict,
        notes=tuple(note_parts),
    )
