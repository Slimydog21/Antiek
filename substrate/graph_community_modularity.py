r"""Graph community-modularity axis — does the knowledge graph self-organize into sub-topics?

Operator vision (ask #1): *"...the perfect knowledge graph/base... navigate, reference, and
leverage."* A knowledge graph that has accreted hundreds of findings can take two shapes: one
undifferentiated blob where every finding links weakly to every other, or a genuinely MODULAR
substrate — dense clusters of related findings connected by sparse bridges. Modular structure is
what makes a knowledge base NAVIGABLE (the operator can hop cluster-to-cluster) and REFERENCEABLE
(a cluster is a citable sub-topic). No existing graph axis detects emergent community structure.

**Genuinely distinct from the graph surface (load-bearing):**

* ``graph_fragmentation`` (#1995): Union-Find COMPONENT partitioning — splits by REACHABILITY
  (zero-path vs one-path). A connected graph is ONE component regardless of how it is internally
  clustered. Community structure splits a SINGLE component into sub-groups by LINK DENSITY — a
  graph can be fully connected (one component) yet sharply modular (many communities).
* ``graph_transitivity`` (#2001): triangle-counting CLIQUISHNESS — a local, per-node property
  averaged globally. A graph of two dense cliques joined by a bridge has high transitivity AND
  strong community structure, but transitivity alone cannot tell you there are TWO communities
  (it averages away the partition). Community structure is a GLOBAL partition, not a local average.
* ``graph_strongly_connected`` (#2023): partitions by DIRECTED mutual reachability (feedback
  loops). Community structure partitions by LINK DENSITY (topical clustering) on an UNDIRECTED
  graph. A DAG (zero SCCs) can still have strong community structure (dense topical clusters).
* Every distance/centrality/influence axis (``diameter``, ``centrality``, ``pagerank``,
  ``betweenness``, ``k_core``, ``assortativity``, ``global_efficiency``, ``reciprocity``,
  ``directed_reachability``, ``structural_fragility``, ``staleness_cascade``): all measure
  connectivity, distance, importance, symmetry, or feedback. NONE asks "how many natural
  sub-topics does this graph fall into, and how sharply?"

**The binding distinctness:** community-modularity is the only axis that EMERGENTLY PARTITIONS
the graph into dense sub-groups (greedy agglomerative modularity maximization) and SCORES that
partition (Newman's modularity ``Q``). It reveals the topical grain of the accumulated knowledge.

**The measurement (hard to vary).** Two-stage, both standard, deterministic, and convergent:

1. **Greedy agglomerative modularity maximization** (Newman 2004 fast-greedy). Start with every
   node as its own community. Each step, compute the modularity GAIN ``ΔQ`` for merging every
   pair of ADJACENT communities and merge the pair with the MAXIMUM gain (ties broken
   lexicographically by the sorted community-label pair — fully deterministic). Stop when no
   merge yields a positive gain. This is CASCADE-FREE (unlike label propagation) and CONVERGENT
   (at most ``n−1`` merges; each merge strictly reduces the community count).

   The gain formula for merging communities ``a`` and ``b`` (``L`` = total edges, ``L_ab`` =
   edges between them, ``D_a``/``D_b`` = degree sums):

       ΔQ = L_ab / L − (D_a · D_b) / (2L)²

   A positive ``ΔQ`` means the within-community density increases more than chance would predict;
   a negative ``ΔQ`` means the merge would dilute modularity.

2. **Modularity** ``Q``. For the discovered partition, ``Q = Σ_c [ L_c / L − (D_c / 2L)² ]``
   where ``L_c`` is edges WITHIN community ``c`` and ``D_c`` is ``c``'s degree sum. ``Q ≈ 0``
   means community-less (no better than random); ``Q > 0.3`` is the conventional threshold for
   significant modular structure. ``Q ∈ [−0.5, 1]`` in practice.

**Why this diverges from transitivity (the worked example):** Two triangles (A-B-C and D-E-F)
joined by a single bridge (C-D). Transitivity is HIGH (every node is in triangles) and reports
ONE global cliquishness number. But greedy modularity finds TWO communities (the two triangles)
with high ``Q`` (the bridge is too sparse to make merging them worthwhile — ``ΔQ < 0``). Only
the partition reveals the two sub-topics.

**Measured fields:**

* ``node_count`` — distinct nodes in the edge set.
* ``edge_count`` — distinct non-self-loop undirected edges.
* ``self_loop_count`` — excluded self-loops (auditable; never silently dropped).
* ``community_count`` — communities after greedy merging.
* ``largest_community_fraction`` — the biggest community's share of nodes in ``[0, 1]`` (``None``
  for ``unknown``; ``1.0`` when every node merged into one).
* ``modularity`` — ``Q`` (``None`` only for ``unknown`` / ``atomized`` where there are no edges
  to score the partition against).
* ``merges_performed`` — how many agglomerative merges ran (auditable; ``n − community_count``).
* ``community_sizes`` — every community's size sorted desc (auditable: the full grain).

**Verdict (distinct honest states, never collapsed, DESCRIPTIVE not normative):**

* zero nodes -> ``unknown`` (defer, never fabricated).
* exactly one node -> ``singleton`` (trivially one community of one).
* ``>= 2`` nodes, zero edges -> ``atomized`` (every node its own community — ``community_count
  == node_count`` — but this is the absence of structure, not modular grain; ``modularity`` is
  ``None`` because there are no edges to score).
* ``>= 2`` nodes, edges exist, ``community_count == 1`` -> ``single_community`` (greedy merging
  collapsed everyone into one blob — a clique or uniformly dense graph; the honest measured
  ``Q`` is ``0.0``, distinct from ``atomized``'s ``None``).
* ``community_count >= 2``, ``modularity >= modular_threshold`` (default ``0.30``) -> ``modular``
  (sharp, statistically-significant community structure — the knowledge graph has organized into
  citable sub-topics).
* ``community_count >= 2``, ``modularity < modular_threshold`` -> ``weakly_modular`` (multiple
  communities found but below significance — the grain is faint).

**DESCRIPTIVE NOT NORMATIVE:** ``modular`` does NOT mean "good" — an overly-clustered graph may
signal echo chambers or disconnected sub-fields that never cross-reference. ``single_community``
does NOT mean "bad" — a tightly-integrated, cross-referential knowledge base may legitimately
form one cohesive whole. The operator judges whether the grain reflects healthy sub-topic
organization or Balkanized isolation.

**Honesty rules (load-bearing):**

* ``unknown`` never fabricates when zero nodes are supplied.
* ``atomized`` is its own honest state (no edges -> trivially N communities, but no structure to
  score) — ``modularity`` is ``None``, NEVER a fabricated ``0.0``.
* ``single_community`` carries an honest measured ``modularity`` of ``0.0`` (one group -> ``Q``
  is exactly 0 by the formula) — distinct from ``atomized``'s ``None``.
* ``modularity`` is ``None`` ONLY for ``unknown`` / ``atomized``; any graph with edges yields a
  measured ``Q``.
* the greedy merge loop is deterministic (lexicographic tie-break on sorted label pairs) and
  convergent (bounded by ``n−1`` merges, stops at first non-positive max gain).
* self-loops excluded but counted; parallel edges deduped to a simple graph.
* ``authority = "advisory"`` — pure layer proposes; operator consent executes.
* deterministic + immutable (frozen dataclass; sorted, reproducible output).
* import-free of off-main siblings (plain ``(node, node)`` edge pairs; route layer adapts 1:1
  from the knowledge-graph edge set).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

__all__ = [
    "GraphCommunityModularityReport",
    "measure_graph_community_modularity",
]

_DEFAULT_MODULAR_THRESHOLD = 0.30


@dataclass(frozen=True)
class GraphCommunityModularityReport:
    """The community-modularity surface for one knowledge graph. Advisory, pure."""

    node_count: int
    edge_count: int
    self_loop_count: int
    community_count: int
    largest_community_fraction: float | None
    modularity: float | None
    merges_performed: int
    community_sizes: tuple[int, ...]
    modular_threshold: float
    verdict: str
    notes: tuple[str, ...]
    authority: str = "advisory"


def _greedy_communities(
    nodes: list[str],
    adj: dict[str, set[str]],
    edge_count: int,
) -> tuple[list[set[str]], int]:
    """Greedy agglomerative modularity maximization (Newman fast-greedy).

    Start: each node its own community. Each step: merge the adjacent community pair with the
    maximum positive modularity gain (ties broken lexicographically by sorted label pair). Stop
    at first non-positive max gain. Deterministic + convergent (at most n-1 merges).
    """
    if edge_count == 0:
        return [{n} for n in nodes], 0

    two_l = 2.0 * edge_count
    degree: dict[str, int] = {n: len(adj[n]) for n in nodes}

    # Each node starts as its own community (labeled by the node id).
    communities: dict[str, set[str]] = {n: {n} for n in nodes}
    comm_degree: dict[str, float] = {n: float(degree[n]) for n in nodes}

    # Inter-community edge counts stored symmetrically: cross[a][b] = cross[b][a] = edge count.
    # Iterate each undirected edge ONCE (source is the lex-smaller endpoint).
    cross: dict[str, dict[str, int]] = {n: {} for n in nodes}
    for n in nodes:
        for nb in adj[n]:
            if n < nb:
                cross[n][nb] = cross[n].get(nb, 0) + 1
                cross[nb][n] = cross[nb].get(n, 0) + 1

    merges = 0
    while len(communities) > 1:
        # Find the adjacent pair with the maximum strictly-positive gain.
        best_gain = 0.0
        best_pair: tuple[str, str] | None = None
        for a in sorted(communities):
            for b in sorted(communities):
                if a >= b:
                    continue
                lab = cross.get(a, {}).get(b, 0)
                if lab == 0:
                    continue
                gain = lab / edge_count - (comm_degree[a] * comm_degree[b]) / (two_l * two_l)
                pair = (a, b) if a <= b else (b, a)
                if gain > best_gain or (
                    gain > 0.0 and gain == best_gain and best_pair is not None and pair < best_pair
                ):
                    best_gain = gain
                    best_pair = pair

        if best_pair is None:
            break

        # Merge hi into lo (lo is the lex-smaller surviving label).
        lo, hi = best_pair
        communities[lo] = communities[lo] | communities[hi]
        comm_degree[lo] = comm_degree[lo] + comm_degree[hi]

        # Redirect all of hi's cross-edges to lo (symmetric update).
        for other, cnt in list(cross.get(hi, {}).items()):
            if other == lo:
                continue  # internal edge now; drop
            if other == hi:
                continue
            cross[lo][other] = cross[lo].get(other, 0) + cnt
            cross[other][lo] = cross[other].get(lo, 0) + cnt
            cross[other].pop(hi, None)
        # Drop lo->hi and hi entirely.
        cross[lo].pop(hi, None)
        cross.pop(hi, None)

        del communities[hi]
        del comm_degree[hi]
        merges += 1

    return list(communities.values()), merges


def _compute_modularity(
    nodes: list[str],
    adj: dict[str, set[str]],
    communities: list[set[str]],
    edge_count: int,
) -> float:
    """Newman modularity Q for the given partition over a simple undirected graph."""
    two_l = 2.0 * edge_count
    degree: dict[str, int] = {n: len(adj[n]) for n in nodes}
    node_comm: dict[str, int] = {}
    for ci, comm in enumerate(communities):
        for n in comm:
            node_comm[n] = ci
    degree_by_comm: dict[int, float] = {}
    within_edges: dict[int, float] = {}
    for ci in range(len(communities)):
        degree_by_comm[ci] = 0.0
        within_edges[ci] = 0.0
    for n in nodes:
        ci = node_comm[n]
        degree_by_comm[ci] += degree[n]
    for n in nodes:
        ci = node_comm[n]
        for nb in adj[n]:
            if node_comm[nb] == ci:
                within_edges[ci] += 1.0
    q = 0.0
    for ci in range(len(communities)):
        lc = within_edges[ci] / 2.0
        dc = degree_by_comm[ci]
        q += lc / edge_count - (dc / two_l) ** 2
    return q


def measure_graph_community_modularity(
    nodes: Sequence[str],
    edges: Sequence[tuple[str, str]],
    *,
    modular_threshold: float = _DEFAULT_MODULAR_THRESHOLD,
) -> GraphCommunityModularityReport:
    r"""Measure the community structure (greedy modularity partition + Q) of a graph.

    Args:
        nodes: distinct node identifiers.
        edges: ``(from, to)`` pairs (treated as undirected; self-loops excluded).
        modular_threshold: ``Q`` at/above which structure is ``modular`` (default ``0.30``).

    Returns:
        A :class:`GraphCommunityModularityReport` with the partition and modularity.

    Raises:
        ValueError: if ``modular_threshold`` is outside its valid range.
    """
    if not 0.0 <= modular_threshold <= 1.0:
        raise ValueError(
            f"modular_threshold must be in [0.0, 1.0]; got {modular_threshold}"
        )

    node_list: list[str] = sorted(set(nodes))
    node_count = len(node_list)

    if node_count == 0:
        return GraphCommunityModularityReport(
            node_count=0,
            edge_count=0,
            self_loop_count=0,
            community_count=0,
            largest_community_fraction=None,
            modularity=None,
            merges_performed=0,
            community_sizes=(),
            modular_threshold=modular_threshold,
            verdict="unknown",
            notes=("no nodes — community structure unmeasurable",),
        )

    # Simple undirected graph: dedup edges (order-insensitive), drop self-loops.
    self_loop_count = 0
    distinct: set[tuple[str, str]] = set()
    for a, b in edges:
        if a == b:
            self_loop_count += 1
            continue
        distinct.add((a, b) if a <= b else (b, a))

    edge_count = len(distinct)
    adj: dict[str, set[str]] = {n: set() for n in node_list}
    for a, b in distinct:
        adj[a].add(b)
        adj[b].add(a)

    communities, merges_performed = _greedy_communities(node_list, adj, edge_count)
    sizes = sorted((len(c) for c in communities), reverse=True)
    community_count = len(communities)
    largest_community_fraction = sizes[0] / node_count

    # Singleton: one node is trivially one community of one.
    if node_count == 1:
        return GraphCommunityModularityReport(
            node_count=node_count,
            edge_count=edge_count,
            self_loop_count=self_loop_count,
            community_count=1,
            largest_community_fraction=1.0,
            modularity=None,
            merges_performed=0,
            community_sizes=tuple(sizes),
            modular_threshold=modular_threshold,
            verdict="singleton",
            notes=("one node — trivially one community of one",),
        )

    # Atomized: >= 2 nodes, no edges -> each node its own community, no structure to score.
    if edge_count == 0:
        return GraphCommunityModularityReport(
            node_count=node_count,
            edge_count=0,
            self_loop_count=self_loop_count,
            community_count=community_count,
            largest_community_fraction=largest_community_fraction,
            modularity=None,
            merges_performed=0,
            community_sizes=tuple(sizes),
            modular_threshold=modular_threshold,
            verdict="atomized",
            notes=(
                f"{community_count} isolated nodes, zero edges — no structure to score "
                "(distinct from a measured modularity of 0.0)",
            ),
        )

    modularity = _compute_modularity(node_list, adj, communities, edge_count)

    if community_count == 1:
        verdict = "single_community"
        notes = (
            "greedy merging collapsed all nodes into one community — a uniformly "
            f"dense or clique-like graph (measured modularity {modularity:.4f})",
        )
    elif modularity >= modular_threshold:
        verdict = "modular"
        notes = (
            f"{community_count} communities, modularity {modularity:.4f} >= "
            f"modular_threshold {modular_threshold:.2f} — sharp, significant structure "
            "(the knowledge graph has organized into citable sub-topics)",
        )
    else:
        verdict = "weakly_modular"
        notes = (
            f"{community_count} communities, modularity {modularity:.4f} < "
            f"modular_threshold {modular_threshold:.2f} — the grain is faint "
            "(communities detected but below statistical significance)",
        )

    return GraphCommunityModularityReport(
        node_count=node_count,
        edge_count=edge_count,
        self_loop_count=self_loop_count,
        community_count=community_count,
        largest_community_fraction=largest_community_fraction,
        modularity=modularity,
        merges_performed=merges_performed,
        community_sizes=tuple(sizes),
        modular_threshold=modular_threshold,
        verdict=verdict,
        notes=notes,
    )
