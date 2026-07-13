r"""Staleness-cascade axis — how far does a stale source's rot propagate through citations?

Operator vision (ask #1 + ask #6): the research workstation is a **knowledge graph** where every
asset references others. When a source goes STALE (superseded, retracted, or its evidence base
moved), the rot does not stay local — every work that cites it inherits a foundation built on
outdated material. No prior axis measures this **transitive propagation**:

* ``twin_staleness`` (#1975): is ONE twin stale relative to ITS source (1:1, single instant, no
  graph edges)? That is local temporal drift; THIS is graph-wide propagation.
* ``source_recency`` (#1951): how CURRENT is the evidence base (per-source freshness at a point)?
  That is a freshness distribution; THIS is reachability over a citation DAG.
* ``temporal_spread`` (#2002): do sources triangulate across TIME (spread of publish dates)?
  That is a date-range statistic; THIS is a directed-reachability traversal.
* the graph quintet+1 (fragmentation #1995, centrality #1996, diameter #2000, transitivity #2001,
  assortativity #2010, global-efficiency #2013): all measure pure STRUCTURE (no node attribute).
  THIS carries a node attribute (stale/fresh) and measures how that attribute REACHES dependents —
  reachability over an attributed DAG, machinery none of them use.

The binding distinctness: a knowledge graph can be perfectly connected (global-efficiency 1.0),
centrally healthy (no hub rot), and fully triangulated (temporal-spread high) — yet have ONE stale
foundational paper whose rot silently propagates to 80 % of the graph through citation edges.
Only a reachability traversal over the stale-attribute set surfaces that. Structure axes are blind
to attribute propagation; the single-twin staleness axis is blind to the graph.

**The measurement (hard to vary).** Given:

* a citation DAG as directed edges ``(source_id, dependent_id)`` where ``dependent`` cites ``source``
  (staleness propagates FROM source TO dependent — the dependent's foundation is the source), and
* a set of ``stale_node_ids`` (nodes flagged stale by #1975 / source-recency / operator override),

compute, for each stale root, the set of dependents reachable along forward edges (BFS over the
``source -> dependent`` direction). A dependent reachable from ANY stale root is TRANSITIVELY
STALE. The cascade is the union of all reachable dependents (roots themselves are stale-by-flag,
not stale-by-propagation — two distinct concepts carried separately).

**Measured fields:**

* ``total_node_count`` — distinct nodes in the citation DAG.
* ``stale_root_count`` — nodes flagged stale directly (the ignition set).
* ``transitively_stale_count`` — non-root dependents reachable from at least one stale root (the
  propagation footprint, EXCLUDING the roots — honest distinction from the ignition set).
* ``total_stale_footprint`` — ``stale_root_count + transitively_stale_count`` (the full rot scope).
* ``cascade_ratio`` — ``total_stale_footprint / total_node_count`` in ``[0, 1]`` (the fraction of
  the graph affected by rot — ignition + propagation). ``None`` only for ``unknown``.
* ``max_cascade_depth`` — the longest root-to-reachable-leaf chain (how DEEP the rot penetrates).
  ``0`` when stale roots have no outgoing edges (isolated); ``None`` for ``unknown``.
* ``affected_root_count`` — stale roots that reach AT LEAST one dependent (roots with non-empty
  cascades — the roots actually driving propagation).
* ``per_root_cascade`` — every stale root as ``(root_id, reachable_count, local_depth)`` sorted by
  reachable_count desc then root_id asc (auditable: the operator sees each root's blast radius).

**Verdict (distinct honest states, never collapsed, DESCRIPTIVE not normative):**

* zero nodes -> ``unknown`` (no graph to propagate through — defer, never fabricated).
* nodes exist but zero stale roots -> ``no_staleness`` (the graph is rot-free NOW — a REAL measured
  verdict distinct from ``unknown`` which has no graph).
* stale roots exist but reach zero dependents -> ``isolated_staleness`` (each stale node is a
  terminal/uncited node — the rot is contained, it does not propagate).
* stale roots reach >= 1 dependent -> ``cascade`` (rot propagates). Sub-classified by
  ``cascade_ratio``: ``contained_cascade`` (< 0.30), ``spreading_cascade`` ([0.30, 0.70)),
  ``pervasive_cascade`` (>= 0.70).

**DESCRIPTIVE NOT NORMATIVE:** ``pervasive_cascade`` does NOT mean "bad" — a foundational paper
going stale SHOULD flag its whole subtree (that is the system surfacing a real foundation problem).
``isolated_staleness`` does NOT mean "good" — a stale node with no citers may be unreferenced
garbage, not a contained problem. ``no_staleness`` does NOT mean "good" — everything fresh NOW
does not mean it will not rot tomorrow (this axis is a snapshot, not a predictor). The operator
judges whether the cascade reflects a genuine foundation risk or noise. This axis surfaces the
FACT of transitive rot; it does not prescribe remediation.

**Honesty rules (load-bearing):**

* ``unknown`` never fabricates when the graph is empty (zero nodes).
* ``no_staleness`` is its own honest base case (graph exists, zero stale roots — distinct from
  ``unknown`` which has no graph, and from ``isolated_staleness`` which HAS stale roots).
* ``cascade_ratio`` is ``None`` only for ``unknown``; for ``no_staleness`` it is an honest ``0.0``
  (zero stale footprint over a real graph — literal truth; the verdict carries the state).
* ``max_cascade_depth`` is ``None`` for ``unknown``; ``0`` when no cascade exists (stale roots with
  no outgoing edges — three distinct states: ``None``/``0``/a real depth, never collapsed).
* ``transitively_stale_count`` EXCLUDES the stale roots (propagation is distinct from ignition —
  a root is stale by flag, a reachable dependent is stale by inheritance).
* cycle-safe: the citation graph may contain cycles (A cites B cites A — live data); BFS uses a
  visited set, so cycles never infinite-loop and a node reachable via multiple paths is counted once.
* self-loops ``(a, a)`` and duplicate edges are deduped harmlessly (a node cannot propagate rot to
  itself meaningfully; the visited set bounds it).
* a node flagged stale that is NOT in the DAG's node set is counted in ``stale_root_count`` but
  contributes zero cascade (it has no edges to propagate through — carried in
  ``detached_root_count``, never silently dropped).
* every stale root's blast radius auditable via ``per_root_cascade`` (id + count + depth — no
  black-box ratio).
* ``authority = "advisory"`` — pure layer proposes; operator consent (or a refresh worker) executes.
* deterministic + immutable (frozen dataclasses; sorted, reproducible output).
* import-free of off-main siblings (plain ``(str, str)`` edge pairs + ``str`` stale ids; route
  layer adapts 1:1 from the knowledge-graph edge set + the staleness-flag store).
"""

from __future__ import annotations

from collections import deque
from collections.abc import Sequence
from dataclasses import dataclass

__all__ = [
    "RootCascade",
    "StalenessCascadeReport",
    "measure_staleness_cascade",
]

_DEFAULT_CONTAINED_THRESHOLD = 0.30
_DEFAULT_PERVASIVE_THRESHOLD = 0.70


@dataclass(frozen=True)
class RootCascade:
    """One stale root's blast radius."""

    root_id: str
    reachable_count: int  # distinct dependents reachable from this root (>= 0)
    local_depth: int  # longest root-to-leaf chain for this root (0 if no outgoing edges)


@dataclass(frozen=True)
class StalenessCascadeReport:
    """The transitive staleness-propagation surface for one knowledge graph. Advisory, pure."""

    total_node_count: int
    stale_root_count: int
    transitively_stale_count: int
    total_stale_footprint: int
    cascade_ratio: float | None
    max_cascade_depth: int | None
    affected_root_count: int
    detached_root_count: int
    per_root_cascade: tuple[RootCascade, ...]
    contained_threshold: float
    pervasive_threshold: float
    verdict: str
    notes: tuple[str, ...]
    authority: str = "advisory"


def _build_adjacency(
    edges: Sequence[tuple[str, str]],
) -> tuple[dict[str, list[str]], set[str]]:
    """Build forward adjacency (source -> [dependents]) and the full node set.

    Self-loops (``a -> a``) are dropped: a node cannot propagate staleness to itself meaningfully.
    Duplicate edges collapse naturally (list append + the later visited-set dedupes at traversal).
    """
    adjacency: dict[str, list[str]] = {}
    nodes: set[str] = set()
    for src, dep in edges:
        nodes.add(src)
        nodes.add(dep)
        if src == dep:
            continue  # self-loop: cannot propagate to self
        adjacency.setdefault(src, []).append(dep)
    return adjacency, nodes


def _bfs_cascade(
    root: str,
    adjacency: dict[str, list[str]],
    stale_roots: set[str],
) -> tuple[set[str], int]:
    """BFS from one stale root, returning (reachable dependents, local depth).

    The root itself is excluded from ``reachable`` (it is stale-by-flag, not by propagation).
    Other stale roots encountered during traversal ARE counted as reachable (a stale root can be
    transitively downstream of another stale root — inherited rot compounds with its own).
    Depth is the longest root-to-reachable-leaf chain (0 if the root has no outgoing edges).
    """
    reachable: set[str] = set()
    depth = 0
    queue: deque[tuple[str, int]] = deque()
    visited: set[str] = {root}
    for neighbor in adjacency.get(root, []):
        if neighbor not in visited:
            visited.add(neighbor)
            reachable.add(neighbor)
            queue.append((neighbor, 1))
            depth = max(depth, 1)
    while queue:
        node, d = queue.popleft()
        for neighbor in adjacency.get(node, []):
            if neighbor not in visited:
                visited.add(neighbor)
                reachable.add(neighbor)
                queue.append((neighbor, d + 1))
                depth = max(depth, d + 1)
    return reachable, depth


def measure_staleness_cascade(
    edges: Sequence[tuple[str, str]],
    stale_node_ids: Sequence[str],
    *,
    contained_threshold: float = _DEFAULT_CONTAINED_THRESHOLD,
    pervasive_threshold: float = _DEFAULT_PERVASIVE_THRESHOLD,
) -> StalenessCascadeReport:
    r"""Measure how far staleness propagates through a citation knowledge graph.

    ``edges`` are ``(source_id, dependent_id)`` pairs where ``dependent`` cites ``source``
    (staleness flows source -> dependent). ``stale_node_ids`` are nodes flagged stale directly.

    Returns:
        A :class:`StalenessCascadeReport` quantifying transitive staleness propagation.

    Raises:
        ValueError: if ``contained_threshold`` or ``pervasive_threshold`` is outside ``[0, 1]``,
            or ``contained_threshold > pervasive_threshold``.
    """
    if not 0.0 <= contained_threshold <= 1.0:
        raise ValueError(
            f"contained_threshold must be in [0.0, 1.0]; got {contained_threshold}"
        )
    if not 0.0 <= pervasive_threshold <= 1.0:
        raise ValueError(
            f"pervasive_threshold must be in [0.0, 1.0]; got {pervasive_threshold}"
        )
    if contained_threshold > pervasive_threshold:
        raise ValueError(
            f"contained_threshold ({contained_threshold}) must be <= "
            f"pervasive_threshold ({pervasive_threshold})"
        )

    adjacency, nodes = _build_adjacency(edges)
    total_node_count = len(nodes)
    stale_roots = {sid.strip() for sid in stale_node_ids if sid.strip()}
    stale_root_count = len(stale_roots)

    if total_node_count == 0 and stale_root_count == 0:
        return StalenessCascadeReport(
            total_node_count=0,
            stale_root_count=0,
            transitively_stale_count=0,
            total_stale_footprint=0,
            cascade_ratio=None,
            max_cascade_depth=None,
            affected_root_count=0,
            detached_root_count=0,
            per_root_cascade=(),
            contained_threshold=contained_threshold,
            pervasive_threshold=pervasive_threshold,
            verdict="unknown",
            notes=(),
        )

    if stale_root_count == 0:
        return StalenessCascadeReport(
            total_node_count=total_node_count,
            stale_root_count=0,
            transitively_stale_count=0,
            total_stale_footprint=0,
            cascade_ratio=0.0,
            max_cascade_depth=0,
            affected_root_count=0,
            detached_root_count=0,
            per_root_cascade=(),
            contained_threshold=contained_threshold,
            pervasive_threshold=pervasive_threshold,
            verdict="no_staleness",
            notes=("graph has no flagged stale roots — rot-free at this snapshot",),
        )

    # Compute each stale root's cascade.
    per_root: list[RootCascade] = []
    all_transitively_stale: set[str] = set()
    max_depth = 0
    affected = 0
    detached = 0
    for root in stale_roots:
        reachable, local_depth = _bfs_cascade(root, adjacency, stale_roots)
        per_root.append(
            RootCascade(
                root_id=root,
                reachable_count=len(reachable),
                local_depth=local_depth,
            )
        )
        if reachable:
            all_transitively_stale |= reachable
            affected += 1
            max_depth = max(max_depth, local_depth)
        else:
            if root not in nodes:
                detached += 1

    transitively_stale_count = len(all_transitively_stale)
    total_stale_footprint = stale_root_count + transitively_stale_count
    cascade_ratio = total_stale_footprint / total_node_count if total_node_count else 0.0

    per_root_tuple = tuple(
        sorted(per_root, key=lambda rc: (-rc.reachable_count, rc.root_id))
    )

    notes_list: list[str] = []
    if transitively_stale_count == 0:
        verdict = "isolated_staleness"
        notes_list.append(
            "stale roots exist but none reach a dependent — rot is contained (each stale "
            "node is terminal/uncited)"
        )
    else:
        if cascade_ratio >= pervasive_threshold:
            verdict = "pervasive_cascade"
        elif cascade_ratio >= contained_threshold:
            verdict = "spreading_cascade"
        else:
            verdict = "contained_cascade"
        notes_list.append(
            f"{affected} of {stale_root_count} stale root(s) propagate rot to "
            f"{transitively_stale_count} dependent(s)"
        )
    if detached > 0:
        notes_list.append(
            f"{detached} stale root(s) are detached (not in the graph's node set — no "
            f"edges to propagate through)"
        )

    return StalenessCascadeReport(
        total_node_count=total_node_count,
        stale_root_count=stale_root_count,
        transitively_stale_count=transitively_stale_count,
        total_stale_footprint=total_stale_footprint,
        cascade_ratio=cascade_ratio,
        max_cascade_depth=max_depth if transitively_stale_count > 0 else 0,
        affected_root_count=affected,
        detached_root_count=detached,
        per_root_cascade=per_root_tuple,
        contained_threshold=contained_threshold,
        pervasive_threshold=pervasive_threshold,
        verdict=verdict,
        notes=tuple(notes_list),
    )
