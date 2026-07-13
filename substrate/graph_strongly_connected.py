r"""Graph strongly-connected-components axis — where does the citation graph feed back on itself?

Operator vision (ask #1): *"...the perfect knowledge graph/base."* A citation graph is a
hierarchy when it is acyclic — findings point at prior work and never circle back. But real
knowledge bases accumulate FEEDBACK: finding A cites B, B cites C, and C cites A (transitively
mutually reachable). That feedback is neither good nor bad — but the operator must SEE it, because
a cyclic cluster is a self-reinforcing echo (every member reachable from every other) that looks
like deep cross-referencing but may be circular reasoning. The unit of feedback structure is the
**strongly connected component** (SCC): a maximal set of nodes where each can reach each other
along DIRECTED edges. No existing graph axis computes SCCs.

**Genuinely distinct from the graph surface (load-bearing):**

* ``graph_fragmentation`` (#1995): Union-Find components over UNDIRECTED reachability — A and B
  are in the same component if a path exists in EITHER direction. SCCs use DIRECTED mutual
  reachability — A and B are in the same SCC only if A can reach B AND B can reach A. A→B without
  B→A: one component (fragmentation) but TWO SCCs (this axis). Fragmentation sees connectivity;
  SCCs see feedback.
* ``graph_reciprocity`` (#2022): DIRECT mutual edges (A↔B both present). SCCs capture TRANSITIVE
  mutual reachability (A→B→C→A, no direct back-edge needed). Reciprocity counts returned links;
  SCCs count returned REACHABILITY — a 5-node directed cycle has zero reciprocity (each edge
  one-way) yet is ONE SCC (every node reachable from every other). Reciprocity sees direct
  exchange; SCCs see cyclic closure at any length.
* ``graph_pagerank`` (#2021): stationary random-walk influence (where rank pools). SCCs are a
  STRUCTURAL partition (which nodes are mutually locked). A node can hold maximal PageRank while
  sitting in a trivial (size-1) SCC — influential but not part of any feedback loop.
* ``structural_fragility`` (#2017): Tarjan LOW-LINK for CUT VERTICES and BRIDGES on an UNDIRECTED
  graph (which node's removal disconnects). SCCs use Tarjan/Kosaraju for COMPONENT partitioning on
  a DIRECTED graph (which nodes are mutually reachable). Different application of related theory;
  different graph model; different question.

**The binding distinctness:** SCCs are the only axis measuring DIRECTED FEEDBACK STRUCTURE —
which findings form mutually-reinforcing cyclic clusters. They distinguish a clean acyclic
hierarchy (a DAG) from a graph with echo loops, a distinction no connectivity, symmetry,
distance, or influence measure can surface.

**The measurement (hard to vary).** Kosaraju's two-pass algorithm, implemented iteratively
(no recursion-limit risk) and deterministically (sorted node/neighbor iteration throughout):

1. **Pass 1** — iterative DFS over the forward graph, recording nodes in finishing-time order.
2. **Pass 2** — process nodes in REVERSE finishing order, running BFS on the REVERSED graph;
   each BFS tree is one SCC.

Every node lands in exactly one SCC (the partition is complete and disjoint). An SCC of size
``1`` is TRIVIAL (no cycle through it — a node that cannot return to itself); size ``>= 2`` is
NONTRIVIAL (a genuine feedback cluster). The graph is a DAG (directed acyclic graph) iff every
SCC is trivial.

**Why SCCs diverge from reciprocity (the worked example):** A→B→C→A (a 3-cycle, each edge one-way).
Reciprocity is ``0.0`` (no edge is directly returned). But the graph is ONE SCC of size 3 — every
node reaches every other (A→B→C→A, B→C→A→B, …). Reciprocity says "no direct exchange"; SCCs say
"total cyclic closure." Only the transitive reachability sees the loop.

**Measured fields:**

* ``node_count`` — distinct nodes in the edge set.
* ``directed_edge_count`` — distinct non-self-loop directed edges.
* ``self_loop_count`` — excluded self-loops (auditable; never silently dropped).
* ``scc_count`` — number of strongly connected components.
* ``largest_scc_size`` / ``largest_scc_fraction`` — the biggest SCC's node count and its share
  in ``[0, 1]`` (``None`` for ``unknown``; ``1.0`` when the whole graph is one SCC).
* ``trivial_scc_count`` — SCCs of size 1 (nodes in no feedback cycle).
* ``nontrivial_scc_count`` — SCCs of size ``>= 2`` (genuine feedback clusters).
* ``is_dag`` — ``True`` iff every SCC is trivial (the graph has zero directed cycles).
* ``scc_sizes`` — every SCC's size sorted desc (auditable: the full feedback grain).

**Verdict (distinct honest states, never collapsed, DESCRIPTIVE not normative):**

* zero nodes -> ``unknown`` (defer, never fabricated).
* exactly one node -> ``singleton`` (trivially one SCC of one).
* ``>= 2`` nodes, zero directed edges -> ``no_directed_edges`` (each node its own trivial SCC,
  but there is no structure — ``is_dag`` is ``True`` vacuously; honest base case).
* ``directed_edge_count >= 1``, ``is_dag`` is ``True`` -> ``acyclic`` (a clean citation
  hierarchy — no feedback loops; every SCC trivial).
* ``scc_count == 1`` (and ``>= 2`` nodes) -> ``strongly_connected`` (the entire graph is one
  mutual-reachability cluster — total feedback closure).
* otherwise (``nontrivial_scc_count >= 1`` but ``scc_count > 1``) -> ``partially_cyclic``
  (feedback clusters embedded in a larger structure).

**DESCRIPTIVE NOT NORMATIVE:** ``strongly_connected`` does NOT mean "good" — total feedback can
be a closed echo chamber where findings only justify each other. ``acyclic`` does NOT mean "bad" —
a clean hierarchy of findings pointing at foundational sources is a healthy DAG. The operator
judges whether the feedback reflects genuine convergence or circular reasoning. This axis surfaces
the FACT of feedback structure; it does not prescribe the right shape.

**Honesty rules (load-bearing):**

* ``unknown`` never fabricates when zero nodes are supplied.
* ``largest_scc_fraction`` is ``None`` ONLY for ``unknown``; for any ``>= 1`` node it is a measured
  value in ``(0, 1]`` (``1/node_count`` when every node is its own SCC; ``1.0`` when all share one).
* ``is_dag`` is an honest boolean computed from the partition — never fabricated.
* SCC sizes are surfaced verbatim and sorted (auditable: the operator sees the feedback grain, no
  black-box).
* self-loops excluded + counted; parallel edges deduped.
* ``authority = "advisory"`` — pure layer proposes; operator consent executes.
* deterministic + immutable (frozen dataclass; sorted iteration throughout Kosaraju; reproducible
  output).
* import-free of off-main siblings (plain ``(node, node)`` directed edge pairs; route layer adapts
  1:1 from the knowledge-graph directed-edge set).
"""

from __future__ import annotations

from collections import deque
from collections.abc import Sequence
from dataclasses import dataclass

__all__ = [
    "GraphStronglyConnectedReport",
    "measure_graph_strongly_connected",
]


@dataclass(frozen=True)
class GraphStronglyConnectedReport:
    """The strongly-connected-components surface for one directed graph. Advisory, pure."""

    node_count: int
    directed_edge_count: int
    self_loop_count: int
    scc_count: int
    largest_scc_size: int
    largest_scc_fraction: float | None
    trivial_scc_count: int
    nontrivial_scc_count: int
    is_dag: bool
    scc_sizes: tuple[int, ...]
    verdict: str
    notes: tuple[str, ...]
    authority: str = "advisory"


def _kosaraju(
    nodes: list[str],
    adj: dict[str, set[str]],
    radj: dict[str, set[str]],
) -> list[list[str]]:
    """Deterministic Kosaraju SCC. Returns a list of SCCs (each a sorted node list)."""
    # Pass 1: iterative DFS over forward graph, recording finishing order.
    visited: set[str] = set()
    finish_order: list[str] = []
    for start in nodes:
        if start in visited:
            continue
        stack: list[tuple[str, list[str]]] = [(start, sorted(adj[start]))]
        visited.add(start)
        while stack:
            node, neighbors = stack[-1]
            progressed = False
            while neighbors:
                nb = neighbors.pop()
                if nb not in visited:
                    visited.add(nb)
                    stack.append((nb, sorted(adj[nb])))
                    progressed = True
                    break
            if not progressed:
                finish_order.append(node)
                stack.pop()

    # Pass 2: reverse finishing order, BFS on reversed graph -> each tree is an SCC.
    visited2: set[str] = set()
    sccs: list[list[str]] = []
    for node in reversed(finish_order):
        if node in visited2:
            continue
        comp: list[str] = []
        dq: deque[str] = deque([node])
        visited2.add(node)
        while dq:
            cur = dq.popleft()
            comp.append(cur)
            for v in sorted(radj[cur]):
                if v not in visited2:
                    visited2.add(v)
                    dq.append(v)
        sccs.append(sorted(comp))
    return sccs


def measure_graph_strongly_connected(
    nodes: Sequence[str],
    edges: Sequence[tuple[str, str]],
) -> GraphStronglyConnectedReport:
    r"""Measure the strongly-connected-components (feedback) structure of a directed graph.

    Args:
        nodes: distinct node identifiers.
        edges: ``(from, to)`` DIRECTED pairs (self-loops excluded; parallel edges merged).

    Returns:
        A :class:`GraphStronglyConnectedReport` with the SCC partition and DAG verdict.
    """
    node_list: list[str] = sorted(set(nodes))
    node_count = len(node_list)

    if node_count == 0:
        return GraphStronglyConnectedReport(
            node_count=0,
            directed_edge_count=0,
            self_loop_count=0,
            scc_count=0,
            largest_scc_size=0,
            largest_scc_fraction=None,
            trivial_scc_count=0,
            nontrivial_scc_count=0,
            is_dag=True,
            scc_sizes=(),
            verdict="unknown",
            notes=("no nodes — feedback structure unmeasurable",),
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
    radj: dict[str, set[str]] = {n: set() for n in node_list}
    for src, dst in directed:
        adj[src].add(dst)
        radj[dst].add(src)

    sccs = _kosaraju(node_list, adj, radj)
    sizes = sorted((len(scc) for scc in sccs), reverse=True)
    scc_count = len(sccs)
    largest_scc_size = sizes[0]
    largest_scc_fraction = largest_scc_size / node_count
    trivial_scc_count = sum(1 for s in sizes if s == 1)
    nontrivial_scc_count = scc_count - trivial_scc_count
    is_dag = nontrivial_scc_count == 0

    if node_count == 1:
        return GraphStronglyConnectedReport(
            node_count=node_count,
            directed_edge_count=directed_edge_count,
            self_loop_count=self_loop_count,
            scc_count=1,
            largest_scc_size=1,
            largest_scc_fraction=1.0,
            trivial_scc_count=1,
            nontrivial_scc_count=0,
            is_dag=True,
            scc_sizes=(1,),
            verdict="singleton",
            notes=("one node — trivially one SCC of one",),
        )

    if directed_edge_count == 0:
        return GraphStronglyConnectedReport(
            node_count=node_count,
            directed_edge_count=0,
            self_loop_count=self_loop_count,
            scc_count=scc_count,
            largest_scc_size=largest_scc_size,
            largest_scc_fraction=largest_scc_fraction,
            trivial_scc_count=trivial_scc_count,
            nontrivial_scc_count=0,
            is_dag=True,
            scc_sizes=tuple(sizes),
            verdict="no_directed_edges",
            notes=(
                f"{scc_count} trivial SCCs, zero edges — no structure (vacuously a DAG)",
            ),
        )

    if is_dag:
        verdict = "acyclic"
        notes = (
            f"all {scc_count} SCCs are trivial — a clean acyclic citation hierarchy "
            f"(zero directed cycles, is_dag True)",
        )
    elif scc_count == 1:
        verdict = "strongly_connected"
        notes = (
            f"all {node_count} nodes form one SCC — total mutual-reachability closure "
            "(a single feedback cluster)",
        )
    else:
        verdict = "partially_cyclic"
        notes = (
            f"{nontrivial_scc_count} nontrivial SCC(s) among {scc_count} total — "
            "feedback clusters embedded in a larger structure",
        )

    return GraphStronglyConnectedReport(
        node_count=node_count,
        directed_edge_count=directed_edge_count,
        self_loop_count=self_loop_count,
        scc_count=scc_count,
        largest_scc_size=largest_scc_size,
        largest_scc_fraction=largest_scc_fraction,
        trivial_scc_count=trivial_scc_count,
        nontrivial_scc_count=nontrivial_scc_count,
        is_dag=is_dag,
        scc_sizes=tuple(sizes),
        verdict=verdict,
        notes=notes,
    )
