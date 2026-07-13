r"""Graph reciprocity axis — how much of the citation structure is mutual exchange?

Operator vision (ask #1): *"...the perfect knowledge graph/base... navigate, reference,
and leverage."* Citations are DIRECTIONAL: finding A may cite B without B citing back. The
shape of that directionality matters. A graph where nearly every citation is reciprocated
(A↔B) describes a substrate of MUTUAL intellectual exchange — findings that reference each
other, a dialogue. A graph where citations are almost all one-way (A→B) describes a
hierarchical, acyclic influence flow — findings point at authorities that do not point back.
No existing graph axis measures this SYMMETRY, because only PageRank (#2021) even treats
edges as directed — and PageRank measures WHERE influence accumulates, not whether it flows
both ways.

**Genuinely distinct from the graph surface (load-bearing):**

* ``graph_pagerank`` (#2021): the only other DIRECTED axis, but it measures the STATIONARY
  random-walk distribution — which nodes accumulate rank. Reciprocity measures the
  DIRECTIONAL SYMMETRY of the edges themselves — how often a link is returned. A node can
  hold maximal PageRank (everyone cites into it) while the graph is perfectly acyclic
  (zero reciprocity): the influencer is cited but never cites back. Reciprocity sees the
  exchange pattern PageRank's stationary distribution averages away.
* Every UNDIRECTED axis (``fragmentation``, ``centrality``, ``diameter``, ``transitivity``,
  ``assortativity``, ``global_efficiency``, ``structural_fragility``, ``staleness_cascade``,
  ``betweenness``, ``k_core``): collapse A→B and B→A into a single undirected edge and
  CANNOT see directionality at all. Reciprocity is the second axis (with PageRank) to
  exploit directedness, and the only one to measure its SYMMETRY.

**The binding distinctness:** reciprocity is the only axis measuring MUTUAL citation — the
fraction of directed edges whose reverse also exists. It distinguishes a dialogic substrate
(reciprocated) from a hierarchical one (acyclic), a distinction invisible to every
influence, distance, or topology measure.

**The measurement (hard to vary).** The standard arc-reciprocity ratio:

    reciprocity = reciprocated_edge_count / directed_edge_count

where ``directed_edge_count`` is the number of distinct directed edges ``m`` (self-loops
excluded, parallel duplicates merged), and ``reciprocated_edge_count = 2 × mutual_pair_count``
— each mutual unordered pair ``{u, v}`` (both ``u→v`` and ``v→u`` present) contributes two
reciprocated edges. The ratio is in ``[0, 1]``: ``0`` means every citation is one-way
(a strict acyclic/hierarchical flow), ``1`` means every citation is returned (a fully
dialogic graph). It is undefined (``None``) when there are no directed edges at all.

**Why reciprocity diverges from PageRank (the worked example):** A→B, B→A (mutual),
B→C (one-way). PageRank concentrates DOWNSTREAM at C (the sink of the chain). Reciprocity
sees ``2/3 ≈ 0.667`` — two of three edges are returned. PageRank answers "who is the
attractor"; reciprocity answers "is the graph a dialogue or a hierarchy." Only the symmetry
ratio sees the exchange.

**Measured fields:**

* ``node_count`` — distinct nodes in the edge set.
* ``directed_edge_count`` — distinct non-self-loop directed edges (the ``m`` denominator).
* ``self_loop_count`` — excluded self-loops (auditable; never silently dropped).
* ``mutual_pair_count`` — unordered pairs ``{u, v}`` with BOTH directions present.
* ``reciprocated_edge_count`` — ``2 × mutual_pair_count`` (the numerator).
* ``asymmetric_edge_count`` — edges with NO reverse (``m − reciprocated``).
* ``reciprocity_ratio`` — the ratio in ``[0, 1]`` (``None`` only for ``unknown`` /
  ``no_directed_edges``).
* ``mutual_pairs`` — every reciprocated pair ``(min(u,v), max(u,v))`` sorted asc (auditable:
  the exact exchange pairs, no black-box).

**Verdict (distinct honest states, never collapsed, DESCRIPTIVE not normative):**

* zero nodes -> ``unknown`` (defer, never fabricated).
* exactly one node -> ``singleton`` (self-loops excluded — no directed edge possible).
* ``>= 2`` nodes, zero directed edges -> ``no_directed_edges`` (``reciprocity_ratio`` is
  ``None`` — no edges to measure symmetry over; honest base case, never fabricated ``0.0``).
* ``directed_edge_count >= 1``, ``reciprocity_ratio == 0`` -> ``acyclic`` (fully one-way —
  a strict hierarchical flow; the honest measured ``0.0``, distinct from ``None``).
* ``0 < reciprocity_ratio < reciprocal_threshold`` -> ``partially_reciprocal`` (some
  exchange, some one-way flow).
* ``reciprocity_ratio >= reciprocal_threshold`` (default ``0.50``) -> ``highly_reciprocal``
  (most citations are returned — a dialogic substrate).

**DESCRIPTIVE NOT NORMATIVE:** ``highly_reciprocal`` does NOT mean "good" — a graph of mutual
back-scratching (A cites B, B cites A, neither contributes novelty) is reciprocated but
empty. ``acyclic`` does NOT mean "bad" — a clean hierarchy where many findings cite a few
foundational authorities (who need not cite back) is a healthy, acyclic citation structure.
The operator judges whether the symmetry reflects genuine dialogue or circular citation.

**Honesty rules (load-bearing):**

* ``unknown`` never fabricates when zero nodes are supplied.
* ``no_directed_edges`` is its own honest state — ``reciprocity_ratio`` is ``None``, NEVER a
  fabricated ``0.0`` (zero edges is the absence of a denominator, not measured asymmetry).
* ``acyclic`` carries an honest measured ``0.0`` — there ARE edges, none reciprocated. The
  two states (``None`` vs ``0.0``) never collapse.
* ``reciprocity_ratio`` is ``None`` ONLY for ``unknown`` / ``no_directed_edges``.
* ``authority = "advisory"`` — pure layer proposes; operator consent executes.
* deterministic + immutable (frozen dataclass; sorted, reproducible output).
* import-free of off-main siblings (plain ``(node, node)`` directed edge pairs; route layer
  adapts 1:1 from the knowledge-graph directed-edge set).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

__all__ = [
    "GraphReciprocityReport",
    "measure_graph_reciprocity",
]

_DEFAULT_RECIPROCAL_THRESHOLD = 0.50


@dataclass(frozen=True)
class GraphReciprocityReport:
    """The reciprocity (mutual-citation) surface for one directed graph. Advisory, pure."""

    node_count: int
    directed_edge_count: int
    self_loop_count: int
    mutual_pair_count: int
    reciprocated_edge_count: int
    asymmetric_edge_count: int
    reciprocity_ratio: float | None
    mutual_pairs: tuple[tuple[str, str], ...]
    reciprocal_threshold: float
    verdict: str
    notes: tuple[str, ...]
    authority: str = "advisory"


def measure_graph_reciprocity(
    nodes: Sequence[str],
    edges: Sequence[tuple[str, str]],
    *,
    reciprocal_threshold: float = _DEFAULT_RECIPROCAL_THRESHOLD,
) -> GraphReciprocityReport:
    r"""Measure the reciprocity (mutual-citation symmetry) of a directed graph.

    Args:
        nodes: distinct node identifiers.
        edges: ``(from, to)`` DIRECTED pairs (self-loops excluded; parallel edges merged).
        reciprocal_threshold: ratio at/above which the graph is ``highly_reciprocal``
            (default ``0.50``).

    Returns:
        A :class:`GraphReciprocityReport` with the reciprocity ratio and verdict.

    Raises:
        ValueError: if ``reciprocal_threshold`` is outside its valid range.
    """
    if not 0.0 < reciprocal_threshold <= 1.0:
        raise ValueError(
            f"reciprocal_threshold must be in (0.0, 1.0]; got {reciprocal_threshold}"
        )

    node_set = set(nodes)
    node_count = len(node_set)

    if node_count == 0:
        return GraphReciprocityReport(
            node_count=0,
            directed_edge_count=0,
            self_loop_count=0,
            mutual_pair_count=0,
            reciprocated_edge_count=0,
            asymmetric_edge_count=0,
            reciprocity_ratio=None,
            mutual_pairs=(),
            reciprocal_threshold=reciprocal_threshold,
            verdict="unknown",
            notes=("no nodes — reciprocity unmeasurable",),
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

    if node_count == 1:
        # One node: only possible edges are self-loops (already excluded).
        return GraphReciprocityReport(
            node_count=node_count,
            directed_edge_count=0,
            self_loop_count=self_loop_count,
            mutual_pair_count=0,
            reciprocated_edge_count=0,
            asymmetric_edge_count=0,
            reciprocity_ratio=None,
            mutual_pairs=(),
            reciprocal_threshold=reciprocal_threshold,
            verdict="singleton",
            notes=("one node — no inter-node directed edge possible",),
        )

    if directed_edge_count == 0:
        return GraphReciprocityReport(
            node_count=node_count,
            directed_edge_count=0,
            self_loop_count=self_loop_count,
            mutual_pair_count=0,
            reciprocated_edge_count=0,
            asymmetric_edge_count=0,
            reciprocity_ratio=None,
            mutual_pairs=(),
            reciprocal_threshold=reciprocal_threshold,
            verdict="no_directed_edges",
            notes=("no directed edges — reciprocity unmeasurable (no denominator)",),
        )

    # Find mutual pairs: unordered {u,v} where both (u,v) and (v,u) present.
    mutual_pairs: list[tuple[str, str]] = []
    for src, dst in directed:
        if src < dst and (dst, src) in directed:
            mutual_pairs.append((src, dst))
    mutual_pairs.sort()
    mutual_pair_count = len(mutual_pairs)
    reciprocated_edge_count = 2 * mutual_pair_count
    asymmetric_edge_count = directed_edge_count - reciprocated_edge_count
    reciprocity_ratio = reciprocated_edge_count / directed_edge_count

    if reciprocity_ratio == 0.0:
        verdict = "acyclic"
        notes = (
            f"reciprocity_ratio 0.0 — all {directed_edge_count} directed edges are "
            "one-way (a strict hierarchical flow, no mutual exchange)",
        )
    elif reciprocity_ratio >= reciprocal_threshold:
        verdict = "highly_reciprocal"
        notes = (
            f"reciprocity_ratio {reciprocity_ratio:.4f} >= reciprocal_threshold "
            f"{reciprocal_threshold:.2f} — {reciprocated_edge_count} of "
            f"{directed_edge_count} edges are returned (a dialogic substrate)",
        )
    else:
        verdict = "partially_reciprocal"
        notes = (
            f"reciprocity_ratio {reciprocity_ratio:.4f} between 0 and "
            f"reciprocal_threshold {reciprocal_threshold:.2f} — a mix of mutual "
            "exchange and one-way flow",
        )

    return GraphReciprocityReport(
        node_count=node_count,
        directed_edge_count=directed_edge_count,
        self_loop_count=self_loop_count,
        mutual_pair_count=mutual_pair_count,
        reciprocated_edge_count=reciprocated_edge_count,
        asymmetric_edge_count=asymmetric_edge_count,
        reciprocity_ratio=reciprocity_ratio,
        mutual_pairs=tuple(mutual_pairs),
        reciprocal_threshold=reciprocal_threshold,
        verdict=verdict,
        notes=notes,
    )
