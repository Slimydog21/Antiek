"""Research trajectory — the topology of the recursive investigation tree.

Operator vision (ask #1): the workstation lets the operator *"send subagents to
chase questions"* and *"record the valuable data, insights, and questions
recursively."* The schema makes recursion first-class: each ``ArtifactQuestion``
can carry ``reserved_child_investigation_id`` — an escalation edge from a parent
question to a child investigation that chases it deeper. As the operator
researches, this builds a TREE: a root investigation, its escalated questions
spawning children, their escalated questions spawning grandchildren.

No current axis measures the SHAPE of this tree. escalation_linkage (#1941)
checks whether escalated questions got chase reservations (pairwise). plan_
resolution (#1937) checks whether a plan's questions were answered (content).
research_yield (#1944) checks the insight/question balance WITHIN one artifact.
None asks: **what does the overall investigation tree look like?** How deep did
the research go? How broad? Was the recursion productive (children resolved the
parent's questions) or fruitless (children spawned more questions without
resolution)?

THIS module measures the trajectory topology.

**Metrics (hard to vary):**
* ``max_depth`` — the longest root-to-leaf chain (how deep the research went).
  Depth 1 = a flat investigation with no children. Depth 5 = the operator chased
  questions 5 levels deep.
* ``total_investigations`` — all nodes in the tree.
* ``leaf_count`` — investigations with no children (the frontier where research
  stopped — either resolved or abandoned).
* ``avg_branching_factor`` — average children per non-leaf node (how much the
  research expanded at each level).
* ``resolution_rate`` — fraction of leaf investigations that are "resolved"
  (carried insights, not just questions). A high resolution rate means the
  recursion was PRODUCTIVE; a low rate means it was FRUITLESS (spawned
  investigations that never found answers).

**Productive vs fruitless recursion (the operator-facing verdict):**
* ``productive`` — the tree has depth > 1 AND resolution rate is high (children
  resolved the parent's escalated questions).
* ``shallow`` — depth 1 (no recursion happened — the investigation was flat).
* ``fruitless_expansion`` — depth > 1 but low resolution rate (children spawned
  without resolving — the recursion ran but didn't deliver).
* ``unknown`` — empty tree (no investigations).

**Honesty rules (load-bearing):**
* ``max_depth`` is ``None`` when the tree is empty (defer). ``resolution_rate`` is
  ``None`` when there are no leaf investigations with measurable resolution.
* Cycles are detected and rejected (a child pointing back to an ancestor is a
  data integrity error, not a "deep tree"). The module raises
  ``TrajectoryError`` rather than infinite-looping.
* An investigation not reachable from any root is an ORPHAN — counted separately
  (``orphan_count``), not silently merged into the tree.
* ``resolution_rate`` uses the leaf's OWN insight/question balance as the
  resolution signal (a leaf with insights delivered; a leaf with only questions
  did not). This mirrors research_yield #1944 within-leaf.
* Deterministic and pure: same inputs -> same report. No LLM, no network, no
  clock, no mutation.
* ``authority`` is always ``"advisory"``.

**Import-free of off-main siblings (load-bearing).** The module takes the tree
as a frozen :class:`TrajectoryInputs` (root ids + edges + per-investigation
insight/question counts). The route layer extracts these from the graph DB.
Mirrors the #1937/#1949/#1950/#1951 compatible-shape pattern.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass

_DEFAULT_RESOLUTION_THRESHOLD: float = 0.25


class TrajectoryError(ValueError):
    """A trajectory input violates a load-bearing invariant (e.g. a cycle)."""


@dataclass(frozen=True)
class InvestigationNode:
    """One investigation in the trajectory tree.

    ``child_investigation_ids`` are the investigations spawned by THIS node's
    escalated questions (via ``reserved_child_investigation_id``).
    """

    investigation_id: str
    insight_count: int
    question_count: int
    child_investigation_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class TrajectoryInputs:
    """The investigation tree. The route layer fills this from the graph DB."""

    root_investigation_ids: tuple[str, ...]
    nodes: tuple[InvestigationNode, ...]


@dataclass(frozen=True)
class TrajectoryReport:
    """The investigation-tree topology surface. Advisory, pure."""

    root_count: int
    total_investigations: int
    reachable_count: int  # nodes reachable from roots
    orphan_count: int  # nodes NOT reachable from any root
    max_depth: int | None  # longest root-to-leaf chain; None if empty
    leaf_count: int  # reachable nodes with no children
    avg_branching_factor: float | None  # children per non-leaf; None if no non-leaves
    resolution_rate: float | None  # resolved leaves / total leaves; None if no leaves
    verdict: str  # productive | shallow | fruitless_expansion | unknown
    resolution_threshold: float
    notes: tuple[str, ...]
    authority: str = "advisory"


def _has_cycle(
    roots: tuple[str, ...],
    children_of: dict[str, tuple[str, ...]],
) -> str | None:
    """Return a node id involved in a cycle, or None if the tree is acyclic."""
    visited: set[str] = set()
    for root in roots:
        stack: list[tuple[str, frozenset[str]]] = [(root, frozenset())]
        while stack:
            node, ancestors = stack.pop()
            if node in ancestors:
                return node
            if node in visited:
                continue
            visited.add(node)
            new_ancestors = ancestors | {node}
            for child in children_of.get(node, ()):
                stack.append((child, new_ancestors))
    return None


def _resolution_ratio(node: InvestigationNode) -> float:
    """Insight share of informational mass (mirrors research_yield #1944)."""
    mass = node.insight_count + node.question_count
    if mass == 0:
        return 0.0
    return node.insight_count / mass


def analyze_trajectory(
    inputs: TrajectoryInputs,
    *,
    resolution_threshold: float = _DEFAULT_RESOLUTION_THRESHOLD,
) -> TrajectoryReport:
    """Measure the topology of the recursive investigation tree.

    Pure: no DB, no LLM, no clock, no mutation. Detects cycles (raises
    ``TrajectoryError``), counts orphans, and computes depth/breadth/resolution.
    """
    if not 0.0 <= resolution_threshold <= 1.0:
        raise TrajectoryError(
            f"resolution_threshold must be in [0,1], got {resolution_threshold!r}"
        )

    node_map: dict[str, InvestigationNode] = {
        n.investigation_id: n for n in inputs.nodes
    }
    children_of: dict[str, tuple[str, ...]] = {
        n.investigation_id: n.child_investigation_ids for n in inputs.nodes
    }

    # Detect cycles before traversing.
    cycle_node = _has_cycle(inputs.root_investigation_ids, children_of)
    if cycle_node is not None:
        raise TrajectoryError(
            f"cycle detected involving investigation {cycle_node!r} — a child "
            f"points back to an ancestor (data integrity error, not a deep tree)"
        )

    # BFS from roots to find reachable nodes + depths.
    reachable: set[str] = set()
    depth_of: dict[str, int] = {}
    queue: deque[tuple[str, int]] = deque()
    for root in inputs.root_investigation_ids:
        if root in node_map and root not in reachable:
            queue.append((root, 1))
            reachable.add(root)
            depth_of[root] = 1

    while queue:
        node_id, depth = queue.popleft()
        for child_id in children_of.get(node_id, ()):
            if child_id in node_map and child_id not in reachable:
                reachable.add(child_id)
                depth_of[child_id] = depth + 1
                queue.append((child_id, depth + 1))

    total = len(inputs.nodes)
    orphan_count = total - len(reachable)

    if not reachable:
        return TrajectoryReport(
            root_count=len(inputs.root_investigation_ids),
            total_investigations=total,
            reachable_count=0,
            orphan_count=orphan_count,
            max_depth=None,
            leaf_count=0,
            avg_branching_factor=None,
            resolution_rate=None,
            verdict="unknown",
            resolution_threshold=resolution_threshold,
            notes=("empty or unreachable tree; trajectory not measurable (defer)",),
        )

    max_depth = max(depth_of.values())

    # Leaves = reachable nodes with no reachable children.
    leaves = [
        nid
        for nid in reachable
        if not any(c in reachable for c in children_of.get(nid, ()))
    ]
    leaf_count = len(leaves)

    # Branching factor: children per non-leaf reachable node.
    non_leaves = [nid for nid in reachable if nid not in set(leaves)]
    if non_leaves:
        total_children = sum(
            sum(1 for c in children_of.get(nid, ()) if c in reachable)
            for nid in non_leaves
        )
        avg_branching = total_children / len(non_leaves)
    else:
        avg_branching = None

    # Resolution rate: fraction of leaves that delivered insights.
    if leaf_count > 0:
        resolved = sum(
            1
            for nid in leaves
            if _resolution_ratio(node_map[nid]) >= resolution_threshold
        )
        resolution_rate = resolved / leaf_count
    else:
        resolution_rate = None

    notes: list[str] = [
        "trajectory topology is DESCRIPTIVE — 'productive' means the recursion "
        "went deep AND leaves delivered findings, not that the research was "
        "correct (correctness is the content axes' job); 'shallow' is not bad "
        "(a flat investigation may have fully answered its question)",
        "resolution_rate uses each leaf's insight/question balance as the "
        "resolution signal (mirrors research_yield #1944); a leaf with only "
        "questions did not resolve",
    ]

    if max_depth == 1:
        verdict = "shallow"
        notes.append(
            "max depth 1 — no recursion happened; the investigation(s) were flat "
            "(no escalated questions spawned children)"
        )
    elif resolution_rate is not None and resolution_rate < resolution_threshold:
        verdict = "fruitless_expansion"
        notes.append(
            f"max depth {max_depth} but resolution rate {resolution_rate:.0%} "
            f"(threshold {resolution_threshold:.0%}) — the recursion ran deep but "
            f"leaf investigations did not deliver findings; the expansion was "
            f"fruitless"
        )
    else:
        verdict = "productive"
        rate_desc = f"{resolution_rate:.0%}" if resolution_rate is not None else "unknown"
        branch_desc = f"{avg_branching:.1f}" if avg_branching is not None else "N/A"
        notes.append(
            f"max depth {max_depth}, {leaf_count} leaf investigation(s), "
            f"resolution rate {rate_desc}, avg branching "
            f"{branch_desc} — the recursion was productive"
        )

    return TrajectoryReport(
        root_count=len(inputs.root_investigation_ids),
        total_investigations=total,
        reachable_count=len(reachable),
        orphan_count=orphan_count,
        max_depth=max_depth,
        leaf_count=leaf_count,
        avg_branching_factor=avg_branching,
        resolution_rate=resolution_rate,
        verdict=verdict,
        resolution_threshold=resolution_threshold,
        notes=tuple(notes),
        authority="advisory",
    )


__all__ = [
    "InvestigationNode",
    "TrajectoryError",
    "TrajectoryInputs",
    "TrajectoryReport",
    "analyze_trajectory",
]
