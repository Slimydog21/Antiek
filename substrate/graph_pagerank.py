r"""Graph PageRank — which findings hold the most long-run random-walk influence?

Operator vision (ask #1): *"...the perfect knowledge graph/base... navigate, reference,
and leverage."* To know which findings are most INFLUENTIAL in the long-run sense — not
just locally popular, but recursively authoritative (cited by other authoritative findings)
— the operator needs PageRank. A finding with high PageRank is one a reader following
citation links at random would most likely arrive at: it is the convergent target of the
citation structure. None of the existing graph axes computes this, because none simulates
a random walk or measures the stationary distribution of recursive influence.

**Genuinely distinct from the graph surface (load-bearing):**

* ``graph_centrality`` (#1996): Freeman DEGREE centralization — the raw local neighbor
  COUNT. A node can have HIGH degree (many peripheral citations) but LOW PageRank (its
  citers are themselves uncited). PageRank is RECURSIVE: rank flows through chains.
  Degree is one-hop; PageRank is infinite-hop. A node cited by one highly-cited finding
  has higher PageRank than a node cited by ten uncited findings.
* ``graph_betweenness`` (#2019): Brandes' PATH-PARTICIPATION — which nodes are ON shortest
  paths. PageRank is LINK-TARGET weight — which nodes are ARRIVED AT by a random walk.
  A node can have high betweenness (bridging two clusters) but low PageRank (neither
  cluster links TO it), and vice versa.
* ``k_core_decomposition`` (#2020): iterative DEGREE-PEELING — structural embedding depth.
  PageRank is random-walk STATIONARY PROBABILITY — flow-convergent influence. A node can
  be deeply embedded (high core number) but have low PageRank (its cluster is internally
  dense but nobody outside cites into it), and vice versa.
* ``structural_fragility`` / ``staleness_cascade`` / ``diameter`` / ``transitivity`` /
  ``assortativity`` / ``global_efficiency`` / ``fragmentation``: all use undirected or
  static machinery. PageRank is the FIRST DIRECTED-graph axis — citations are directional
  (A cites B ≠ B cites A), and PageRank exploits that directionality. Rank flows FROM the
  citer TO the cited; the cited accumulates authority. Undirected axes cannot see this
  asymmetry.

**The binding distinctness:** PageRank is the only axis measuring RECURSIVE, DIRECTIONAL
influence via random-walk convergence. It is the graph-theoretic quantity that captures
"which findings are the deep attractors of the citation structure" — no local count, path
count, peeling depth, or structural property can substitute.

**The measurement (hard to vary).** The classic PageRank power-iteration algorithm:

    PR(p) = (1 - d) / N + d * [ dangling_redistribution + Σ_{q→p} PR(q) / outdeg(q) ]

where ``d`` is the damping factor (default ``0.85``: with 85 % probability follow a link,
with 15 % probability jump to a random node), ``N`` is the node count, and the sum is over
all nodes ``q`` that link TO ``p``. Dangling nodes (zero out-degree) redistribute their
rank uniformly to all nodes (their ``d * PR`` is spread evenly, preventing rank leakage).
Iteration continues until the maximum change in any node's PageRank falls below
``tolerance`` (default ``1e-6``) or ``max_iterations`` (default ``100``) is reached. The
final values are normalized to sum ``1.0``.

**Why PageRank diverges from degree (the worked example):** Consider a chain A→B→C→D
(each cites the next). Degree of each is 1 (one in-link). But PageRank concentrates
DOWNSTREAM: D (cited by C, which is cited by B, which is cited by A) accumulates the most
recursive influence. Degree says "all equal"; PageRank says "D is the attractor." Only the
random walk sees the recursive flow.

**Measured fields:**

* ``total_node_count`` — distinct nodes.
* ``damping_factor`` — the d parameter (auditable).
* ``convergence_iterations`` — how many iterations ran before convergence (auditable —
  tells the operator whether the graph is well-behaved or oscillating).
* ``converged`` — whether the iteration reached the tolerance (``False`` if it hit
  ``max_iterations`` without converging — honest, never fabricated).
* ``dangling_node_count`` — nodes with zero out-degree (rank-sinks that get redistributed).
* ``max_pagerank`` / ``influential_node`` — the peak and its node (auditable).
* ``pagerank_gini`` — Gini coefficient of the rank distribution in ``[0, 1]`` (``0`` =
  uniform, ``1`` = all rank on one node — the concentration of influence).
* ``per_node`` — every node's ``(node_id, pagerank)`` sorted by pagerank desc then id asc
  (auditable: the full influence ranking, no black-box).

**Verdict (distinct honest states, never collapsed, DESCRIPTIVE not normative):**

* zero nodes -> ``unknown`` (defer, never fabricated).
* exactly one node -> ``singleton`` (rank is 1.0 — the only destination).
* ``>= 2`` nodes, zero edges -> ``uniform_rank`` (every node has rank ``1/N`` — no links
  to concentrate flow; honest state distinct from ``concentrated`` which needs edges).
* edges exist, ``pagerank_gini >= concentration_threshold`` (default ``0.50``) ->
  ``concentrated`` (influence is focused on a few attractor findings — the citation
  structure has clear authority hubs).
* edges exist, ``pagerank_gini < concentration_threshold`` -> ``diffuse_rank`` (influence
  is spread — no finding dominates the random walk).

**DESCRIPTIVE NOT NORMATIVE:** ``concentrated`` does NOT mean "good" — a citation structure
where one finding monopolizes influence may signal a monoculture (everything cites one
source, no diversity). ``diffuse_rank`` does NOT mean "bad" — a web of equally-influential
findings may signal a healthy, non-hierarchical knowledge base. The operator judges whether
the concentration reflects genuine authority or a citation monoculture.

**Honesty rules (load-bearing):**

* ``unknown`` never fabricates.
* ``singleton`` / ``uniform_rank`` are honest base cases (distinct states, never collapsed).
* ``converged`` is ``False`` when ``max_iterations`` is reached without the tolerance being
  met — honestly disclosed, never fabricated as converged.
* ``pagerank_gini`` is ``None`` for ``unknown`` / ``singleton``; for ``uniform_rank`` it is
  an honest ``0.0`` (perfectly uniform — literal truth; the verdict carries the state).
* ``dangling_node_count`` carried verbatim (the operator sees how many rank-sinks exist).
* self-loops ``(a, a)`` dropped (a self-citation does not contribute to PageRank flow — you
  cannot amplify your own authority by citing yourself); duplicate edges merged.
* every node auditable via ``per_node`` (id + pagerank — no black-box score).
* deterministic + immutable (frozen dataclasses; sorted output is reproducible;
  power-iteration with fixed damping/tolerance/max_iterations is deterministic).
* ``authority = "advisory"``; import-free of off-main siblings (plain ``(str, str)``
  directed edge pairs; route layer adapts 1:1 from the knowledge-graph citation edge set).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

__all__ = [
    "NodePageRank",
    "GraphPageRankReport",
    "measure_graph_pagerank",
]

_DEFAULT_DAMPING = 0.85
_DEFAULT_TOLERANCE = 1e-6
_DEFAULT_MAX_ITERATIONS = 100
_DEFAULT_CONCENTRATION_THRESHOLD = 0.50


@dataclass(frozen=True)
class NodePageRank:
    """One node's PageRank (long-run random-walk arrival probability)."""

    node_id: str
    pagerank: float  # in [0.0, 1.0]; all node pageranks sum to 1.0


@dataclass(frozen=True)
class GraphPageRankReport:
    """The recursive influence surface for one directed knowledge graph. Advisory, pure."""

    total_node_count: int
    damping_factor: float
    tolerance: float
    max_iterations: int
    convergence_iterations: int
    converged: bool
    dangling_node_count: int
    max_pagerank: float | None
    influential_node: str | None
    pagerank_gini: float | None
    per_node: tuple[NodePageRank, ...]
    concentration_threshold: float
    verdict: str
    notes: tuple[str, ...]
    authority: str = "advisory"


def _build_directed_adjacency(
    edges: Sequence[tuple[str, str]],
) -> tuple[dict[str, list[str]], dict[str, int]]:
    """Build directed out-adjacency and out-degree map.

    Self-loops (``a -> a``) are dropped (a self-citation does not amplify own authority).
    Duplicate edges merged (a repeated citation is one relationship). Returns
    (out_adjacency, out_degree) where out_adjacency[node] = list of nodes it links to.
    """
    out_adj: dict[str, list[str]] = {}
    out_degree: dict[str, int] = {}
    for src, dst in edges:
        if src == dst:
            continue
        out_adj.setdefault(src, []).append(dst)
        out_degree[src] = out_degree.get(src, 0) + 1
    return out_adj, out_degree


def _gini(values: Sequence[float]) -> float:
    """Gini coefficient in [0, 1]. 0 = uniform, 1 = all mass on one unit."""
    if not values:
        return 0.0
    sorted_vals = sorted(values)
    n = len(sorted_vals)
    total = sum(sorted_vals)
    if total == 0:
        return 0.0
    cumulative = sum((2 * i - n + 1) * v for i, v in enumerate(sorted_vals))
    return cumulative / (n * total)


def _compute_pagerank(
    nodes: list[str],
    out_adj: dict[str, list[str]],
    out_degree: dict[str, int],
    damping: float,
    tolerance: float,
    max_iterations: int,
) -> tuple[dict[str, float], int, bool]:
    """Power-iteration PageRank. Returns (pagerank dict, iterations, converged)."""
    n = len(nodes)
    pr = {node: 1.0 / n for node in nodes}

    dangling = [node for node in nodes if out_degree.get(node, 0) == 0]
    dangling_count = len(dangling)

    # Build in-link map: in_links[p] = list of (q, outdeg(q)) for each q linking to p.
    in_links: dict[str, list[tuple[str, float]]] = {node: [] for node in nodes}
    for src, targets in out_adj.items():
        deg = out_degree[src]
        for dst in targets:
            if dst in in_links:
                in_links[dst].append((src, float(deg)))

    iterations = 0
    converged = False
    for iteration in range(max_iterations):
        iterations = iteration + 1
        new_pr: dict[str, float] = {}

        # Dangling redistribution: d * sum(PR[dangling]) / N spread to all.
        dangling_sum = sum(pr[d] for d in dangling) if dangling_count > 0 else 0.0
        dangling_share = damping * dangling_sum / n

        for node in nodes:
            rank = (1.0 - damping) / n + dangling_share
            in_rank = 0.0
            for source, src_outdeg in in_links[node]:
                in_rank += pr[source] / src_outdeg
            rank += damping * in_rank
            new_pr[node] = rank

        # Check convergence.
        max_change = max(abs(new_pr[node] - pr[node]) for node in nodes)
        pr = new_pr
        if max_change < tolerance:
            converged = True
            break

    # Normalize to sum 1.0.
    total = sum(pr.values())
    if total > 0:
        pr = {node: v / total for node, v in pr.items()}

    return pr, iterations, converged


def measure_graph_pagerank(
    nodes: Sequence[str],
    edges: Sequence[tuple[str, str]],
    *,
    damping: float = _DEFAULT_DAMPING,
    tolerance: float = _DEFAULT_TOLERANCE,
    max_iterations: int = _DEFAULT_MAX_ITERATIONS,
    concentration_threshold: float = _DEFAULT_CONCENTRATION_THRESHOLD,
) -> GraphPageRankReport:
    r"""Measure the PageRank (recursive random-walk influence) of a directed knowledge graph.

    ``nodes`` are every node id in the accumulated substrate. ``edges`` are
    ``(source_id, target_id)`` DIRECTED pairs where source links to (cites) target.
    Self-loops are dropped; duplicates are merged.

    Returns:
        A :class:`GraphPageRankReport` with per-node PageRank and the influence verdict.

    Raises:
        ValueError: if ``damping`` is outside ``[0.0, 1.0]``, ``tolerance <= 0``,
            ``max_iterations < 1``, or ``concentration_threshold`` outside ``[0.0, 1.0]``.
    """
    if not 0.0 <= damping <= 1.0:
        raise ValueError(f"damping must be in [0.0, 1.0]; got {damping}")
    if tolerance <= 0:
        raise ValueError(f"tolerance must be > 0; got {tolerance}")
    if max_iterations < 1:
        raise ValueError(f"max_iterations must be >= 1; got {max_iterations}")
    if not 0.0 <= concentration_threshold <= 1.0:
        raise ValueError(
            f"concentration_threshold must be in [0.0, 1.0]; got {concentration_threshold}"
        )

    node_set: set[str] = {n.strip() for n in nodes if n.strip()}
    for src, dst in edges:
        node_set.add(src)
        node_set.add(dst)
    sorted_nodes = sorted(node_set)
    total_node_count = len(sorted_nodes)

    if total_node_count == 0:
        return GraphPageRankReport(
            total_node_count=0,
            damping_factor=damping,
            tolerance=tolerance,
            max_iterations=max_iterations,
            convergence_iterations=0,
            converged=False,
            dangling_node_count=0,
            max_pagerank=None,
            influential_node=None,
            pagerank_gini=None,
            per_node=(),
            concentration_threshold=concentration_threshold,
            verdict="unknown",
            notes=(),
        )

    if total_node_count == 1:
        return GraphPageRankReport(
            total_node_count=1,
            damping_factor=damping,
            tolerance=tolerance,
            max_iterations=max_iterations,
            convergence_iterations=0,
            converged=True,
            dangling_node_count=1,
            max_pagerank=1.0,
            influential_node=sorted_nodes[0],
            pagerank_gini=None,
            per_node=(NodePageRank(sorted_nodes[0], 1.0),),
            concentration_threshold=concentration_threshold,
            verdict="singleton",
            notes=("one node — rank is 1.0 (the only destination)",),
        )

    out_adj, out_degree = _build_directed_adjacency(edges)

    if not out_adj:
        uniform = 1.0 / total_node_count
        return GraphPageRankReport(
            total_node_count=total_node_count,
            damping_factor=damping,
            tolerance=tolerance,
            max_iterations=max_iterations,
            convergence_iterations=0,
            converged=True,
            dangling_node_count=total_node_count,
            max_pagerank=uniform,
            influential_node=sorted_nodes[0],
            pagerank_gini=0.0,
            per_node=tuple(NodePageRank(n, uniform) for n in sorted_nodes),
            concentration_threshold=concentration_threshold,
            verdict="uniform_rank",
            notes=("zero edges — every node has rank 1/N (no links to concentrate flow)",),
        )

    dangling_node_count = sum(
        1 for node in sorted_nodes if out_degree.get(node, 0) == 0
    )

    pr, iterations, converged = _compute_pagerank(
        sorted_nodes, out_adj, out_degree, damping, tolerance, max_iterations
    )

    per_node_list = sorted(pr.items(), key=lambda kv: (-kv[1], kv[0]))
    per_node = tuple(NodePageRank(n, p) for n, p in per_node_list)

    max_pr = per_node[0].pagerank
    influential = per_node[0].node_id
    gini = _gini([pr[n] for n in sorted_nodes])

    notes_list: list[str] = []
    if gini >= concentration_threshold:
        verdict = "concentrated"
        notes_list.append(
            f"influence concentrated (Gini {gini:.3f}) — node '{influential}' "
            f"holds {max_pr:.1%} of the random-walk mass"
        )
    else:
        verdict = "diffuse_rank"
        notes_list.append(
            f"influence diffuse (Gini {gini:.3f}) — no finding dominates "
            f"the random walk"
        )
    if not converged:
        notes_list.append(
            f"did NOT converge within {max_iterations} iterations — the rank "
            f"estimates are approximate (consider raising max_iterations)"
        )
    if dangling_node_count > 0:
        notes_list.append(
            f"{dangling_node_count} dangling node(s) (zero out-degree — rank "
            f"redistributed uniformly)"
        )

    return GraphPageRankReport(
        total_node_count=total_node_count,
        damping_factor=damping,
        tolerance=tolerance,
        max_iterations=max_iterations,
        convergence_iterations=iterations,
        converged=converged,
        dangling_node_count=dangling_node_count,
        max_pagerank=max_pr,
        influential_node=influential,
        pagerank_gini=gini,
        per_node=per_node,
        concentration_threshold=concentration_threshold,
        verdict=verdict,
        notes=tuple(notes_list),
    )
