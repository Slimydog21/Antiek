r"""K-core decomposition — what is the deep mutually-reinforcing core of the knowledge graph?

Operator vision (ask #1): *"...the perfect knowledge graph/base and thought partner/
workstation... navigate, reference, and leverage."* To know which findings are DEEPLY
EMBEDDED in a mutually-reinforcing structure (vs peripheral loners that hang off the
edge), the operator needs the CORE NUMBER of each node — the highest ``k`` such that the
node survives the iterative ``k``-core peeling process. A node with core number ``3`` is
in a subgraph where EVERY node has at least 3 neighbors also in that subgraph — it is
deeply embedded. A node with core number ``1`` hangs off the edge (it would be removed
in the first peeling round if not for one surviving neighbor). None of the existing
graph axes computes this, because none asks: *"what is the maximal mutually-reinforcing
subgraph each finding belongs to?"*

**Genuinely distinct from the graph surface (load-bearing):**

* ``graph_centrality`` (#1996): Freeman DEGREE centralization — the raw local neighbor
  COUNT. A node can have HIGH degree (connected to many peripheral nodes) but a LOW core
  number (all its neighbors get peeled away in round 1). Degree counts immediate
  neighbors; core number measures ITERATIVE REINFORCEMENT. A star center has degree n-1
  but core number 1 (all its leaves peel off, leaving it alone). Degree ≠ embedding depth.
* ``structural_fragility`` (#2017): DISCRETE articulation-point detection — does removing
  ONE node disconnect? Core decomposition is ITERATIVE CASCADING removal — how deep does
  the mutually-connected subgraph go? A biconnected graph (zero APs) can have a shallow
  core (max core number 1 — a cycle, robust but not dense).
* ``graph_betweenness`` (#2019): Brandes' PATH-PARTICIPATION — which nodes are on shortest
  paths. Core number is LOCAL-DEGREE-PEELING — which nodes survive iterative thinning.
  A low-betweenness node can have a high core number (deeply embedded in a dense cluster
  that nothing routes THROUGH because there are shorter paths elsewhere).
* ``graph_transitivity`` (#2001): triangle density — LOCAL cliquishness. Core number is
  GLOBAL iterative thinning — a graph can be triangle-rich (high transitivity) yet have a
  shallow max core (small tight clusters that don't connect densely).
* ``graph_diameter`` / ``global_efficiency`` / ``assortativity`` / ``fragmentation`` /
  ``staleness_cascade``: all measure stretch, flow, mixing, components, or attribute
  propagation — none performs iterative degree-peeling.

**The measurement (hard to vary).** The Batagelj–Zaversnik (2003) linear-time algorithm:
maintain a working ``degree`` for each node. Repeatedly extract the minimum-degree
unremoved node ``v``; its core number is its current degree ``d``. For each unremoved
neighbor ``w``, if ``degree[w] > d``, decrement it (but never below ``d`` — ``w`` was a
neighbor of ``v``, so any ``k``-core with ``k > d`` containing ``w`` would need ``v``,
which has core ``d``). This produces the EXACT core number for every node — the maximal
``k`` such that the node belongs to a subgraph of minimum degree ``>= k``.

**Key property (the binding distinctness):** a node's core number can be FAR below its
degree. A star center (degree ``n-1``) has core number ``1``. A hub connected to 100
leaves has core number ``1``. Only MUTUALLY-REINFORCING structures (cliques, dense
clusters where every member has many OTHER deep members) achieve high core numbers.
This is the unique graph-theoretic quantity that captures DEEP EMBEDDING — no single
edge or node attribute can fake it.

**Measured fields:**

* ``total_node_count`` — distinct nodes.
* ``max_core_number`` — the highest core number (the deepest layer).
* ``deep_core_size`` — number of nodes in the max-core (the deep-core set).
* ``mean_core_number`` — average core number (the overall embedding depth).
* ``peripheral_fraction`` — fraction of nodes with core number ``<= 1`` (the periphery).
* ``core_distribution`` — every ``(core_number, count)`` pair sorted by core_number desc
  (auditable: the operator sees the full onion-layer structure, no black-box).
* ``deep_core_ids`` — every node in the max-core sorted ascending (auditable — the
  operator sees exactly which findings are deeply embedded).
* ``per_node`` — every node's ``(node_id, core_number)`` sorted by core desc then id asc
  (auditable: the full per-node embedding ranking).

**Verdict (distinct honest states, never collapsed, DESCRIPTIVE not normative):**

* zero nodes -> ``unknown`` (defer, never fabricated).
* exactly one node -> ``singleton`` (no peers to reinforce with).
* ``>= 2`` nodes, zero edges -> ``edgeless`` (every core number is ``0`` — already peeled
  to nothing; honest state distinct from ``shallow_core`` which needs edges).
* ``max_core_number <= 1`` -> ``shallow_core`` (the graph is a forest of trees/stars —
  no node has two mutually-connected neighbors; every finding hangs off at most one
  structural support).
* ``max_core_number == 2`` -> ``cyclic_core`` (there are cycles but no dense clusters —
  the 2-core exists, meaning some findings mutually reinforce in rings, but nothing
  denser).
* ``max_core_number >= 3`` -> ``deep_core`` (there is a subgraph where every node has
  >= 3 mutually-connected neighbors — a genuinely dense, deeply-embedded core).

**DESCRIPTIVE NOT NORMATIVE:** ``deep_core`` does NOT mean "good" — a dense clique of
redundant findings is deeply embedded but informationally useless. ``shallow_core`` does
NOT mean "bad" — a deliberately linear derivation is a tree (core 1) and that is its
correct structure. The operator judges whether the embedding reflects genuine structural
reinforcement or accidental redundancy.

**Honesty rules (load-bearing):**

* ``unknown`` never fabricates when the graph is empty.
* ``singleton`` / ``edgeless`` are honest base cases (never collapsed).
* ``max_core_number`` / ``mean_core_number`` are ``None`` for ``unknown`` / ``singleton``;
  for ``edgeless`` they are honest ``0`` (every node has core number 0 — literal truth).
* ``deep_core_size`` is ``0`` when ``max_core_number`` is ``0`` (no deep core exists);
  never fabricated.
* ``peripheral_fraction`` carries the real periphery share (nodes with core ``<= 1``).
* self-loops ``(a, a)`` dropped (a self-loop does not contribute to a node's k-core
  membership — you cannot be your own structural support); duplicate edges merged.
* disconnected graphs analyzed globally (each component's nodes get their own core
  numbers independently — the peeling runs across the whole node set).
* every layer auditable via ``core_distribution``; every node via ``per_node``.
* ``authority = "advisory"``; deterministic + immutable.
* import-free of off-main siblings (plain ``(str, str)`` edge pairs; route layer adapts
  1:1 from the knowledge-graph edge set).
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass

__all__ = [
    "CoreLayer",
    "NodeCore",
    "KCoreReport",
    "measure_k_core_decomposition",
]


@dataclass(frozen=True)
class CoreLayer:
    """One onion-layer of the k-core decomposition."""

    core_number: int  # the k value
    node_count: int  # how many nodes have this exact core number


@dataclass(frozen=True)
class NodeCore:
    """One node's core number (embedding depth)."""

    node_id: str
    core_number: int  # >= 0


@dataclass(frozen=True)
class KCoreReport:
    """The k-core decomposition surface for one knowledge graph. Advisory, pure."""

    total_node_count: int
    max_core_number: int | None
    deep_core_size: int | None
    mean_core_number: float | None
    peripheral_fraction: float | None
    core_distribution: tuple[CoreLayer, ...]
    deep_core_ids: tuple[str, ...]
    per_node: tuple[NodeCore, ...]
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


def _compute_core_numbers(
    nodes: list[str], adjacency: dict[str, set[str]]
) -> dict[str, int]:
    """Batagelj–Zaversnik (2003) k-core decomposition.

    Repeatedly extract the minimum-degree unremoved node; its core number is its
    current degree. Decrement unremoved neighbors but never below the extracted node's
    core value. Produces the EXACT core number for every node.
    """
    degree: dict[str, int] = {n: len(adjacency.get(n, set())) for n in nodes}
    core: dict[str, int] = {}
    removed: set[str] = set()

    while len(removed) < len(nodes):
        min_node: str | None = None
        min_deg = -1
        for n in nodes:
            if n not in removed:
                d = degree[n]
                if min_node is None or d < min_deg:
                    min_node = n
                    min_deg = d

        assert min_node is not None
        core[min_node] = degree[min_node]
        removed.add(min_node)
        for w in adjacency.get(min_node, set()):
            if w not in removed and degree[w] > core[min_node]:
                degree[w] -= 1

    return core


def measure_k_core_decomposition(
    nodes: Sequence[str],
    edges: Sequence[tuple[str, str]],
) -> KCoreReport:
    r"""Measure the k-core decomposition of a knowledge graph.

    ``nodes`` are every node id in the accumulated substrate (including zero-degree
    nodes — the route layer supplies the full set). ``edges`` are ``(source, target)``
    undirected pairs. Self-loops are dropped; duplicates are merged.

    Returns:
        A :class:`KCoreReport` with per-node core numbers and the embedding verdict.
    """
    node_set: set[str] = {n.strip() for n in nodes if n.strip()}
    for src, dst in edges:
        node_set.add(src)
        node_set.add(dst)
    sorted_nodes = sorted(node_set)
    total_node_count = len(sorted_nodes)

    if total_node_count == 0:
        return KCoreReport(
            total_node_count=0,
            max_core_number=None,
            deep_core_size=None,
            mean_core_number=None,
            peripheral_fraction=None,
            core_distribution=(),
            deep_core_ids=(),
            per_node=(),
            verdict="unknown",
            notes=(),
        )

    if total_node_count == 1:
        return KCoreReport(
            total_node_count=1,
            max_core_number=0,
            deep_core_size=0,
            mean_core_number=0.0,
            peripheral_fraction=1.0,
            core_distribution=(CoreLayer(core_number=0, node_count=1),),
            deep_core_ids=(),
            per_node=(NodeCore(sorted_nodes[0], 0),),
            verdict="singleton",
            notes=("one node — no peers to reinforce with (core number 0)",),
        )

    adjacency = _build_adjacency(edges)

    if not adjacency:
        return KCoreReport(
            total_node_count=total_node_count,
            max_core_number=0,
            deep_core_size=0,
            mean_core_number=0.0,
            peripheral_fraction=1.0,
            core_distribution=(CoreLayer(core_number=0, node_count=total_node_count),),
            deep_core_ids=(),
            per_node=tuple(NodeCore(n, 0) for n in sorted_nodes),
            verdict="edgeless",
            notes=(
                "nodes exist but zero edges — every core number is 0 "
                "(already peeled to nothing, not shallow)",
            ),
        )

    core = _compute_core_numbers(sorted_nodes, adjacency)

    max_core = max(core.values())

    core_counter: Counter[int] = Counter(core.values())
    core_distribution = tuple(
        sorted(
            (CoreLayer(core_number=k, node_count=c) for k, c in core_counter.items()),
            key=lambda cl: cl.core_number,
            reverse=True,
        )
    )

    deep_core_ids = tuple(sorted(n for n, c in core.items() if c == max_core and c > 0))

    mean_core = sum(core.values()) / total_node_count
    peripheral = sum(1 for c in core.values() if c <= 1) / total_node_count

    per_node_list = sorted(core.items(), key=lambda kv: (-kv[1], kv[0]))
    per_node = tuple(NodeCore(n, c) for n, c in per_node_list)

    notes_list: list[str] = []
    if max_core <= 1:
        verdict = "shallow_core"
        notes_list.append(
            f"max core number {max_core} — the graph is a forest of trees/stars; "
            f"no node has two mutually-connected neighbors"
        )
    elif max_core == 2:
        verdict = "cyclic_core"
        notes_list.append(
            "max core number 2 — cycles exist but no dense clusters (2-core only)"
        )
    else:
        verdict = "deep_core"
        notes_list.append(
            f"max core number {max_core} — a subgraph of {len(deep_core_ids)} node(s) "
            f"where every member has >= {max_core} mutually-connected neighbors"
        )

    return KCoreReport(
        total_node_count=total_node_count,
        max_core_number=max_core,
        deep_core_size=len(deep_core_ids),
        mean_core_number=mean_core,
        peripheral_fraction=peripheral,
        core_distribution=core_distribution,
        deep_core_ids=deep_core_ids,
        per_node=per_node,
        verdict=verdict,
        notes=tuple(notes_list),
    )
