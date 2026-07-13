r"""Midnight Oil goal interdependence — is the goal set structurally coherent?

Operator vision (ask #13): *"...set a time of work and goals (and the system
provides the user a recommended price ceiling to approve) then the agent goes off
to execute that task."* The operator can set MULTIPLE goals for one autonomous
run. Some goals are INDEPENDENT (pursuable in any order, in parallel); others are
DEPENDENT (one goal's completion is a precondition for another — you cannot answer
"how does X perform at scale?" before you have answered "what is X?"). The
dependency structure among the goals is a structural property of the goal set
itself, assessed BEFORE execution to tell the operator whether their goals are
arranged for efficient autonomous execution or contain structural problems.

**Genuinely distinct (different object):**

* ``goal_delivery`` (#1938): did FINDINGS address the GOALS (forward recall over
  goals — an execution-OUTCOME measure).
* ``scope_adherence`` (#1967): do FINDINGS trace to GOALS (backward precision over
  findings — an execution-outCOME measure).
* ``ceiling_accuracy`` (#1968) / ``budget_safety_margin`` (#1981) /
  ``cost_efficiency`` (#1971): cost/ceiling/economics (execution-outcome).
* ``time_adherence``: execution-time (execution-outcome).

ALL of these measure execution OUTCOMES (did the run, after the fact, deliver).
NONE measures the GOALS-to-GOALS dependency structure of the goal set itself
(before execution: is this goal set even schedulable, and how efficiently?).
THIS is that structural axis: a topological assessment of the goal dependency
graph. It is a planning-readiness signal — it tells the operator (before approving
the ceiling) whether their goal set is well-formed for autonomous execution or
contains a structural problem the planner cannot resolve.

**The measurement (hard to vary).** Given a set of goals and declared dependency
edges among them (the launch brief carries goal dependencies as predecessor
relationships: goal B depends-on goal A means A must complete before B):

* **cycle detection** — a cyclic dependency graph is UNRESOLVABLE: the planner
  cannot topologically sort it, so the goals cannot be scheduled (A waits for B
  waits for A = deadlock). Any cycle is a critical structural failure.
* ``independent_goal_count`` — goals with zero incoming edges (no preconditions;
  can start immediately and run in parallel — the parallelism potential).
* ``dependent_goal_count`` — goals with at least one incoming edge (wait on a
  predecessor; must be scheduled after it).
* ``max_depth`` — the longest dependency chain (the critical path): how many goals
  must execute SEQUENTIALLY in the worst case (a pure chain of N goals has depth N
  and cannot parallelize at all).
* ``edge_count`` — total declared dependency edges.
* ``dependency_density = edges / possible_edges`` — how interconnected the goal
  set is (0.0 = fully independent; approaching 1.0 = dense web). ``possible_edges
  = n * (n - 1) / 2`` for an undirected view of the goal set.

**Verdict (distinct honest states, never collapsed):**

* fewer than two goals -> ``unknown`` (defer — a single goal has no
  inter-dependence to assess; never fabricated).
* a cycle exists -> ``cyclic`` (UNRESOLVABLE — the goal set contains a dependency
  deadlock; the operator MUST see it before approving). The cyclic state is load-
  bearing: it is the one structural failure that makes autonomous execution
  impossible regardless of budget/time.
* no cycle AND ``independent_goal_count == goal_count`` -> ``parallelizable``
  (every goal is independent — full parallelism potential; the run can fan out).
* no cycle AND ``max_depth == goal_count`` -> ``sequential`` (the critical
  path spans every goal: a pure dependency chain — bottlenecked; no two goals can
  run in parallel; the most time-expensive structure; the chain root has no
  predecessor so ``dependent_goal_count == goal_count - 1`` here).
* otherwise -> ``mixed`` (some goals independent, some dependent, acyclic — the
  common healthy shape: a DAG with parallel headroom and a finite critical path).

**Honesty rules (load-bearing):**

* ``unknown`` never fabricates a verdict on fewer than two goals.
* ``max_depth`` / ``dependency_density`` / counts are carried verbatim; None only
  when ``unknown`` (fewer than two goals — a single goal has depth 1, not 0, and
  density is undefined).
* Self-loops (a goal depends on itself) are a trivial cycle and treated as
  ``cyclic`` (never silently dropped).
* Duplicate edges are de-duplicated (A depends-on B twice is one structural edge).
* Deterministic and pure: same inputs -> same report. No LLM, no network, no
  clock, no mutation.
* ``authority`` is always ``"advisory"``.

**Import-free of off-main siblings.** The ``midnight_oil`` package is not on
frozen origin/main (varying ``__init__.py`` would cause add/add collisions). This
module takes plain goal-id and dependency-edge inputs; the route layer adapts 1:1
from the launch brief's goal dependency declarations.
"""

from __future__ import annotations

from collections import defaultdict, deque
from collections.abc import Sequence
from dataclasses import dataclass


class GoalInterdependenceError(ValueError):
    """A goal-interdependence input violates a load-bearing invariant."""


@dataclass(frozen=True)
class GoalDependency:
    """One declared dependency: ``successor`` depends-on ``predecessor``."""

    predecessor_id: str
    successor_id: str


@dataclass(frozen=True)
class GoalInterdependenceReport:
    """The structural coherence verdict for a goal dependency graph. Advisory, pure."""

    goal_count: int
    edge_count: int  # de-duplicated structural edges
    independent_goal_count: int  # zero incoming edges
    dependent_goal_count: int  # at least one incoming edge
    max_depth: int | None  # critical-path length; None when fewer than two goals
    dependency_density: float | None  # edges / possible_edges; None when < 2 goals
    has_cycle: bool | None  # True if a dependency cycle exists; None when < 2 goals
    verdict: str  # cyclic | parallelizable | sequential | mixed | unknown
    notes: tuple[str, ...]
    authority: str = "advisory"


def measure_goal_interdependence(
    goals: Sequence[str],
    dependencies: Sequence[GoalDependency],
) -> GoalInterdependenceReport:
    r"""Assess the structural coherence of a Midnight-Oil goal dependency graph.

    ``goals`` is the set of goal ids for the run. ``dependencies`` is a sequence
    of :class:`GoalDependency` (predecessor_id must finish before successor_id).
    Returns a :class:`GoalInterdependenceReport` with cycle detection, independent/
    dependent counts, critical-path depth, density, and verdict.

    Raises:
        GoalInterdependenceError: if a dependency references a goal id not in the
            ``goals`` set (an undeclared goal — a structural integrity error).
    """
    goal_set = set(goals)

    # Validate: every dependency endpoint must be a declared goal.
    for dep in dependencies:
        if dep.predecessor_id not in goal_set:
            raise GoalInterdependenceError(
                f"predecessor_id {dep.predecessor_id!r} not in declared goals"
            )
        if dep.successor_id not in goal_set:
            raise GoalInterdependenceError(
                f"successor_id {dep.successor_id!r} not in declared goals"
            )

    # De-duplicate edges and build adjacency (a self-loop is a trivial cycle).
    edge_set: set[tuple[str, str]] = set()
    has_self_loop = False
    adj: dict[str, set[str]] = defaultdict(set)
    in_degree: dict[str, int] = {g: 0 for g in goal_set}

    for dep in dependencies:
        edge = (dep.predecessor_id, dep.successor_id)
        if dep.predecessor_id == dep.successor_id:
            has_self_loop = True
        if edge not in edge_set:
            edge_set.add(edge)
            adj[dep.predecessor_id].add(dep.successor_id)
            in_degree[dep.successor_id] += 1

    edge_count = len(edge_set)
    n = len(goal_set)

    if n < 2:
        return GoalInterdependenceReport(
            goal_count=n,
            edge_count=edge_count,
            independent_goal_count=n,
            dependent_goal_count=0,
            max_depth=None,
            dependency_density=None,
            has_cycle=None,
            verdict="unknown",
            notes=("fewer than two goals — no inter-dependence to assess",),
        )

    possible_edges = n * (n - 1) // 2
    density = edge_count / possible_edges if possible_edges > 0 else 0.0

    independent_count = sum(1 for g in goal_set if in_degree[g] == 0)
    dependent_count = n - independent_count

    # Cycle detection via Kahn's algorithm (topological sort).
    # A self-loop is a trivial cycle.
    if has_self_loop:
        return GoalInterdependenceReport(
            goal_count=n,
            edge_count=edge_count,
            independent_goal_count=independent_count,
            dependent_goal_count=dependent_count,
            max_depth=None,
            dependency_density=density,
            has_cycle=True,
            verdict="cyclic",
            notes=("self-loop detected — a goal depends on itself",),
        )

    # Kahn's: repeatedly remove zero-in-degree nodes.
    in_deg = dict(in_degree)
    queue: deque[str] = deque(sorted(g for g in goal_set if in_deg[g] == 0))
    topo_order: list[str] = []
    while queue:
        node = queue.popleft()
        topo_order.append(node)
        for succ in sorted(adj[node]):
            in_deg[succ] -= 1
            if in_deg[succ] == 0:
                queue.append(succ)

    has_cycle = len(topo_order) < n

    if has_cycle:
        cyclic_goals = sorted(goal_set - set(topo_order))
        return GoalInterdependenceReport(
            goal_count=n,
            edge_count=edge_count,
            independent_goal_count=independent_count,
            dependent_goal_count=dependent_count,
            max_depth=None,
            dependency_density=density,
            has_cycle=True,
            verdict="cyclic",
            notes=(
                f"dependency cycle among {len(cyclic_goals)} goal(s); "
                f"unschedulable",
            ),
        )

    # Acyclic: compute critical-path depth (longest chain) via topological DP.
    depth: dict[str, int] = {g: 0 for g in goal_set}
    for node in topo_order:
        for succ in sorted(adj[node]):
            depth[succ] = max(depth[succ], depth[node] + 1)
    max_depth = max(depth.values()) + 1  # depth counts edges; +1 for node count

    if independent_count == n:
        verdict = "parallelizable"
    elif max_depth == n:
        # Critical path spans every goal: a pure dependency chain (the root has
        # no predecessor, so dependent_count == n-1 here, not n). The most
        # time-expensive structure — no two goals can run in parallel.
        verdict = "sequential"
    else:
        verdict = "mixed"

    notes = (
        f"{independent_count} independent, {dependent_count} dependent; "
        f"critical-path depth {max_depth}; density {density:.4f}",
    )

    return GoalInterdependenceReport(
        goal_count=n,
        edge_count=edge_count,
        independent_goal_count=independent_count,
        dependent_goal_count=dependent_count,
        max_depth=max_depth,
        dependency_density=density,
        has_cycle=False,
        verdict=verdict,
        notes=notes,
    )
