r"""Research-plan tree — the visible, steerable sub-question decomposition (gap A / P0).

Operator vision (ask #1): *"I want to live in my research workstation and send subagents to
chase questions as I interrogate, assess, and wrestle with the information in front of me in
any given moment."* The deep-research competitive spec (§3 P0) names this as the **one real
trail** where Antiek lags the field: Gemini Deep Research surfaces a *visible, steerable* multi-
step research plan (a tree of sub-questions) that the user sees and redirects before synthesis;
Antiek's cascade runs the decomposition but does not surface a steerable plan tree. This module
is that tree as a pure, decision-independent data structure — the single source of truth for
"what is this research doing" that the workstation renders and the operator steers mid-flight.

**Genuinely distinct from the plan/runner surface (load-bearing):**

* ``runtime/research_runner/protocol.ResearchPlan`` (on main): the per-leaf EXECUTION unit — ONE
  approved ``{investigation_id, sub_question, parent_investigation_id}`` handed to the runner to
  execute. It is a single node's worth of work, not a tree. THIS composes those leaves into a
  *tree* (parent_node_id links), tracks per-node *status* (planned → chasing → done / deprioritized),
  validates tree integrity (acyclic, single root, all parents resolve), and validates steering
  transitions. The runner consumes one ResearchPlan; the workstation reads THIS tree to show the
  whole decomposition and lets the operator steer it.
* ``plan_resolution`` (#1937, off main): a QUALITY axis — *were the plan's questions answered?*
  (content resolution via graph edges). It measures an OUTCOME over an existing plan. THIS is the
  plan-tree MODEL itself — the structure that resolution measures against. You cannot measure
  resolution without a plan tree; this is that tree.
* ``escalation_linkage`` (#1941, off main): the recursion-accountability axis — *were escalated
  questions assigned a chase?* (structural linkage of ArtifactQuestion.escalated →
  reserved_child_investigation_id). THIS is the PLAN level (sub-questions the operator steers),
  not the ARTIFACT level (questions a finding raised). Different object, different layer.

**The model (hard to vary).**

A plan tree is a set of ``PlanNode`` records, each carrying: ``node_id`` (stable), ``sub_question``
(the question this node investigates), ``parent_node_id`` (``None`` for the single root),
``status`` (one of the canonical statuses below), and ``investigation_id`` (``None`` when the node
is planned but not yet assigned a chase — the spawn hasn't happened).

Canonical statuses (the one vocabulary the workstation + cascade key off):

* ``planned`` — decomposed into the tree, not yet started (no investigation assigned).
* ``chasing`` — a subagent chase is in flight (investigation_id assigned, not complete).
* ``done`` — the chase completed and its findings are in the graph.
* ``deprioritized`` — the operator explicitly deferred this node (a steer, not a failure).
* ``branched`` — the operator spawned a child investigation off this node (the spawn-provenance
  substrate; the node is kept in the tree as the branch point, not removed).

``validate_plan_tree`` checks three independent integrity properties and folds them into whether
the tree is ``steerable`` (the operator can safely act on it):

1. **single_root** — exactly one node has ``parent_node_id is None``. Zero roots (a cycle with no
   entry) or multiple roots (a forest, not a tree) both break this.
2. **parents_resolve** — every non-root node's ``parent_node_id`` names a node present in the tree.
   A node whose parent is absent is an orphan (a dangling steer target) — recorded by id.
3. **acyclic** — following parent links from any node reaches the root without revisiting a node.
   A cycle (A→B→A) is a structural defect — the nodes in each cycle are recorded.

A tree with any orphan or cycle is NOT steerable (the operator would steer into a void or a loop).
``steerable`` is the fold: True iff single_root AND no orphans AND no cycles.

**Steering transitions (hard-to-vary).**

``validate_status_transition(from_status, to_status)`` enforces the one defensible transition
table. The operator steers; this validates the steer is coherent before the cascade reads it:

* ``planned → chasing | deprioritized | branched`` (start it, defer it, or branch off it).
* ``chasing → done | deprioritized | branched`` (it finished, the operator defers, or branches).
* ``done → branched`` (a completed node can still spawn a follow-up branch — research continues).
* ``deprioritized → planned | chasing`` (a deferred node can be re-activated; never silently to
  ``done`` — re-activation re-opens the question, it does not fake completion).
* ``branched → chasing`` (a branch point can resume chasing).

A transition NOT in the table is rejected (e.g. ``done → planned`` would erase completed work;
``deprioritized → done`` would fake completion of never-run work). ``authority = "advisory"`` —
this validates the steer; the cascade applies it on its next iteration, never here.

**Completion (the outcome fold).** A plan is ``complete`` when every non-deprioritized LEAF node
(node with no children) is ``done``. A deprioritized leaf is honestly excluded (the operator
chose to defer it — not pending, not failed). A non-leaf node's status is structural (it tracks
the branch, not a deliverable) so only leaves count toward completion. ``complete`` is ``None``
when the tree is not steerable (can't assess outcome over a broken structure).

**Key properties (load-bearing):**

* The tree VERIFIES + MODELS, it does not execute. ``authority = "advisory"`` — no dispatch, no
  spawn, no graph write. The cascade reads the steered tree; the workstation renders it.
* Unknowns surface honestly. ``investigation_id is None`` for a ``planned`` node is the honest
  "not yet started" — never fabricated as chasing. A non-steerable tree yields ``complete = None``,
  never a fabricated True/False.
* ``deprioritized`` is a distinct honest state that never collapses with ``done`` (deferred ≠
  completed) or ``planned`` (the operator explicitly chose to defer; planned is neutral).
* Deterministic + immutable. Frozen dataclasses; re-validating identical nodes reproduces the
  identical report. Orphans + cycles named by id so the failure is actionable.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

__all__ = [
    "STATUSES",
    "STATUS_TRANSITIONS",
    "PlanNode",
    "PlanTreeReport",
    "PlanTreeError",
    "validate_plan_tree",
    "validate_status_transition",
]

# The canonical status vocabulary. One home so the workstation, cascade, and
# tests key off identical strings.
STATUS_PLANNED = "planned"
STATUS_CHASING = "chasing"
STATUS_DONE = "done"
STATUS_DEPRIORITIZED = "deprioritized"
STATUS_BRANCHED = "branched"

STATUSES: frozenset[str] = frozenset(
    {STATUS_PLANNED, STATUS_CHASING, STATUS_DONE, STATUS_DEPRIORITIZED, STATUS_BRANCHED}
)

# The allowed steering transitions. A transition outside this table is rejected.
# Built once; looked up by (from, to) pair. Defensible: each row is a coherent
# operator intent; the rejected pairs erase work (done->planned) or fake it
# (deprioritized->done).
STATUS_TRANSITIONS: frozenset[tuple[str, str]] = frozenset(
    {
        (STATUS_PLANNED, STATUS_CHASING),
        (STATUS_PLANNED, STATUS_DEPRIORITIZED),
        (STATUS_PLANNED, STATUS_BRANCHED),
        (STATUS_CHASING, STATUS_DONE),
        (STATUS_CHASING, STATUS_DEPRIORITIZED),
        (STATUS_CHASING, STATUS_BRANCHED),
        (STATUS_DONE, STATUS_BRANCHED),
        (STATUS_DEPRIORITIZED, STATUS_PLANNED),
        (STATUS_DEPRIORITIZED, STATUS_CHASING),
        (STATUS_BRANCHED, STATUS_CHASING),
    }
)


@dataclass(frozen=True)
class PlanNode:
    """One node in the research-plan tree. ``parent_node_id`` is ``None`` only
    for the single root. ``investigation_id`` is ``None`` when the node is
    planned but no chase has been spawned yet (the honest "not started" state)."""

    node_id: str
    sub_question: str
    status: str
    parent_node_id: str | None
    investigation_id: str | None = None


@dataclass(frozen=True)
class PlanTreeReport:
    """The reproducible integrity + outcome verdict over a research-plan tree.

    ``steerable`` is the structural fold (True iff single_root + no orphans +
    no cycles — the operator can safely act on it). ``complete`` is the outcome
    fold (True iff every non-deprioritized leaf is done; None when not steerable)."""

    root_node_id: str | None
    node_count: int
    leaf_count: int
    single_root: bool
    steerable: bool
    complete: bool | None
    status_counts: dict[str, int]
    orphaned_node_ids: tuple[str, ...]
    cyclic_node_ids: tuple[str, ...]
    leaf_node_ids: tuple[str, ...]
    pending_leaf_ids: tuple[str, ...]
    notes: tuple[str, ...] = ()
    authority: str = "advisory"


class PlanTreeError(ValueError):
    """Raised when a node is malformed (unknown status, empty node_id or
    sub_question) — a programming error in the input, distinct from an integrity
    finding reported in :class:`PlanTreeReport`."""


def _validate_node(node: PlanNode) -> None:
    """Reject malformed nodes before integrity is assessed. An unknown status or
    an empty id/question is a programming error (raises), not an integrity finding
    (reported)."""
    if not node.node_id:
        raise PlanTreeError("PlanNode.node_id must be non-empty")
    if not node.sub_question:
        raise PlanTreeError("PlanNode.sub_question must be non-empty")
    if node.status not in STATUSES:
        raise PlanTreeError(
            f"PlanNode.status {node.status!r} is not canonical (expected one of {sorted(STATUSES)})"
        )


def validate_status_transition(from_status: str, to_status: str) -> bool:
    """Is the steering transition ``from_status -> to_status`` coherent?

    Returns True iff the pair is in :data:`STATUS_TRANSITIONS`. A rejected
    transition is one that erases completed work (``done -> planned``) or fakes
    completion of never-run work (``deprioritized -> done``). This VALIDATES the
    steer; the cascade applies it, never here.
    """
    if from_status not in STATUSES:
        raise PlanTreeError(
            f"from_status {from_status!r} is not canonical (expected one of {sorted(STATUSES)})"
        )
    if to_status not in STATUSES:
        raise PlanTreeError(
            f"to_status {to_status!r} is not canonical (expected one of {sorted(STATUSES)})"
        )
    return (from_status, to_status) in STATUS_TRANSITIONS


def _detect_cycles(nodes_by_id: dict[str, PlanNode]) -> tuple[str, ...]:
    """Return the node_ids that participate in a parent-link cycle. Follows each
    node's parent chain toward the root; if a chain revisits a node before
    reaching a None parent, every node on that loop is cyclic."""
    cyclic: set[str] = set()
    for start_id in nodes_by_id:
        if start_id in cyclic:
            continue
        visited: list[str] = []
        current: str | None = start_id
        while current is not None and current in nodes_by_id:
            if current in visited:
                # the slice from the first occurrence of current onward is the cycle
                cycle_start = visited.index(current)
                cyclic.update(visited[cycle_start:])
                break
            visited.append(current)
            current = nodes_by_id[current].parent_node_id
    return tuple(sorted(cyclic))


def validate_plan_tree(nodes: Sequence[PlanNode]) -> PlanTreeReport:
    """Validate one research-plan tree's integrity + outcome (gap A / P0).

    Returns a :class:`PlanTreeReport` with the structural fold (``steerable``)
    and the outcome fold (``complete``). See the module docstring for the full
    semantics. A malformed node raises :class:`PlanTreeError`. An empty node set
    is a valid (if empty) tree: ``steerable`` False, ``complete`` None.
    """
    for node in nodes:
        _validate_node(node)

    nodes_by_id: dict[str, PlanNode] = {}
    for node in nodes:
        if node.node_id in nodes_by_id:
            raise PlanTreeError(f"duplicate PlanNode.node_id {node.node_id!r}")
        nodes_by_id[node.node_id] = node

    node_count = len(nodes)
    roots = [nid for nid, n in nodes_by_id.items() if n.parent_node_id is None]
    single_root = len(roots) == 1
    root_node_id = roots[0] if len(roots) == 1 else (roots[0] if len(roots) > 0 else None)

    # orphans: non-root nodes whose parent is absent from the tree.
    orphaned = tuple(
        sorted(
            nid
            for nid, n in nodes_by_id.items()
            if n.parent_node_id is not None and n.parent_node_id not in nodes_by_id
        )
    )

    # cycles: parent-link loops.
    cyclic = _detect_cycles(nodes_by_id)

    steerable = bool(single_root and not orphaned and not cyclic and node_count > 0)

    # leaves: nodes that are no other node's parent.
    parent_targets = {n.parent_node_id for n in nodes_by_id.values() if n.parent_node_id is not None}
    leaf_ids = tuple(sorted(nid for nid in nodes_by_id if nid not in parent_targets))

    # status counts (every canonical status present, 0 if absent — auditable shape).
    status_counts = {status: 0 for status in sorted(STATUSES)}
    for n in nodes_by_id.values():
        status_counts[n.status] += 1

    notes: list[str] = []

    if not steerable:
        complete: bool | None = None
        pending_leaf_ids: tuple[str, ...] = ()
        if node_count == 0:
            notes.append("empty plan: no nodes recorded")
        if not single_root:
            notes.append(
                f"not a single-rooted tree: {len(roots)} root node(s) found"
            )
        if orphaned:
            notes.append(
                f"{len(orphaned)} orphaned node(s) (parent not in tree): {list(orphaned)}"
            )
        if cyclic:
            notes.append(
                f"{len(cyclic)} node(s) in a parent-link cycle: {list(cyclic)}"
            )
        notes.append("tree not steerable: completion not assessed over a broken structure")
    else:
        # completion: every non-deprioritized LEAF is done. Deprioritized leaves
        # are honestly excluded (operator chose to defer). Non-leaves are structural.
        pending = tuple(
            nid
            for nid in leaf_ids
            if nodes_by_id[nid].status not in (STATUS_DONE, STATUS_DEPRIORITIZED)
        )
        pending_leaf_ids = pending
        complete = len(pending) == 0
        if complete:
            notes.append(
                "complete: every non-deprioritized leaf is done "
                f"({status_counts.get(STATUS_DEPRIORITIZED, 0)} deprioritized leaf/leaves excluded)"
            )
        else:
            notes.append(
                f"incomplete: {len(pending)} non-deprioritized leaf/leaves not done: {list(pending)}"
            )

    return PlanTreeReport(
        root_node_id=root_node_id,
        node_count=node_count,
        leaf_count=len(leaf_ids),
        single_root=single_root,
        steerable=steerable,
        complete=complete,
        status_counts=status_counts,
        orphaned_node_ids=orphaned,
        cyclic_node_ids=cyclic,
        leaf_node_ids=leaf_ids,
        pending_leaf_ids=pending_leaf_ids,
        notes=tuple(notes),
    )
