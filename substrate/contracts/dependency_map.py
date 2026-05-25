"""Cross-spec dependency DAG — proves the integration graph is acyclic with
DRW on the critical path.

A machine-readable graph of the dependencies *between* the five specs (DRW,
Read, Write, Speak, unified). Each edge is ``consumer → provider`` ("consumer
depends on provider"), annotated with the contract that flows across it. This
is what SPR-05's roadmap renders and what SPR-08's conformance gate consumes.

**Scope (an honesty boundary):** this is a *cross-spec* DAG. It encodes the
DRW-internal dependency spine (because DRW is the shared critical path) and
every product → DRW citation at the granularity the spec bodies actually
declare (spec → DRW-sprint), plus the unified spec's own wave order. It does
**not** encode each product's internal sprint-by-sprint DAG — the products own
those. Edges are grounded in the spec bodies (``inventory.md`` citation
audit), never invented.

The two functions the rest of the unified spec relies on:

* ``verify_acyclic()`` — Kahn's algorithm; returns the cycle if one exists.
  A deliberately-injected cycle makes it fail (tested).
* ``critical_path()`` — the longest provider-first chain among DRW's shared
  primitives; returns ``[drw:1, drw:3, drw:10]``, the load-bearing nodes
  Read/Write/Speak all rest on.
"""

from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass


@dataclass(frozen=True)
class Edge:
    """``consumer`` depends on ``provider``, carrying ``contract``. Node ids
    are ``"<spec>:<sprint>"`` (e.g. ``"read:3"``, ``"drw:10"``) or
    ``"<spec>"`` for a whole-spec dependency where the citing sprint is not
    pinned."""

    consumer: str
    provider: str
    contract: str


# DRW-internal spine: the three shared primitives and how they stack. SPR-03
# (note-taker) produces insights that become SPR-01 nodes; SPR-10 (reading
# surface) surfaces SPR-01 nodes + SPR-03 notes. This is the chain everything
# else hangs off.
_DRW_SPINE: tuple[Edge, ...] = (
    Edge("drw:3", "drw:1", "InsightNodeContract"),
    Edge("drw:10", "drw:1", "InsightNodeContract"),
    Edge("drw:10", "drw:3", "NoteTakerOutputContract"),
)

# Product → DRW citations, grounded in the spec-body audit (inventory.md).
_PRODUCT_TO_DRW: tuple[Edge, ...] = (
    # Read cites DRW SPR-01/03/04/05/06/10.
    Edge("read", "drw:1", "InsightNodeContract"),
    Edge("read", "drw:3", "NoteTakerOutputContract"),
    Edge("read", "drw:4", "ContextPackContract"),
    Edge("read", "drw:5", "ResearchPlan"),
    Edge("read", "drw:6", "(orchestration)"),
    Edge("read", "drw:10", "ReaderSurfaceContract"),
    # Write cites DRW SPR-01/03/10.
    Edge("write", "drw:1", "InsightNodeContract"),
    Edge("write", "drw:3", "NoteTakerOutputContract"),
    Edge("write", "drw:10", "ReaderSurfaceContract"),
    # Speak cites DRW SPR-07.
    Edge("speak", "drw:7", "(structural gap detection)"),
)

# Unified spec internal wave order (the eight sprints this spec ships).
# SPR-01 is the keystone; SPR-02 shares Wave 1; SPR-03/04/05 depend on SPR-01;
# SPR-06/07 depend on Wave 2; SPR-08 depends on all.
_UNIFIED_INTERNAL: tuple[Edge, ...] = (
    Edge("unified:2", "unified:1", "ResearchRunner"),     # protocol home
    Edge("unified:3", "unified:1", "(contracts)"),
    Edge("unified:4", "unified:1", "(contracts)"),
    Edge("unified:5", "unified:1", "dependency_map"),
    Edge("unified:6", "unified:3", "(seams)"),
    Edge("unified:6", "unified:4", "(navigation IA)"),
    Edge("unified:7", "unified:3", "(seams)"),
    Edge("unified:8", "unified:1", "conformance"),
    Edge("unified:8", "unified:2", "remote_exec"),
    Edge("unified:8", "unified:3", "(seams)"),
    Edge("unified:8", "unified:5", "(gate ledger)"),
    Edge("unified:8", "unified:6", "(thread nav)"),
    Edge("unified:8", "unified:7", "(cost/consent)"),
)

# unified SPR-02 sits behind DRW SPR-02's protocol (the §16/remote-exec seam).
_UNIFIED_TO_DRW: tuple[Edge, ...] = (
    Edge("unified:2", "drw:2", "ResearchRunner"),
)

EDGES: tuple[Edge, ...] = (
    _DRW_SPINE + _PRODUCT_TO_DRW + _UNIFIED_INTERNAL + _UNIFIED_TO_DRW
)

# The load-bearing nodes the spec asserts are on the critical path.
CRITICAL_PATH_NODES: tuple[str, ...] = ("drw:1", "drw:3", "drw:10")


def nodes() -> set[str]:
    """Every node referenced by an edge."""
    out: set[str] = set()
    for e in EDGES:
        out.add(e.consumer)
        out.add(e.provider)
    return out


def _adjacency(edges: tuple[Edge, ...]) -> dict[str, list[str]]:
    """consumer → [providers]."""
    adj: dict[str, list[str]] = defaultdict(list)
    for e in edges:
        adj[e.consumer].append(e.provider)
    return adj


def verify_acyclic(edges: tuple[Edge, ...] = EDGES) -> list[str]:
    """Return a topological order of the nodes (Kahn's algorithm). Raises
    ``ValueError`` naming a residual cycle if the graph is not acyclic.

    Edges are ``consumer → provider``; we order providers before consumers
    (provider-first), which is the build order. A deliberately-injected cycle
    makes this raise (tested in ``tests/test_contracts_dependency_map.py``)."""
    all_nodes = set()
    for e in edges:
        all_nodes.add(e.consumer)
        all_nodes.add(e.provider)

    # in_degree counts providers each consumer waits on.
    in_degree: dict[str, int] = {n: 0 for n in all_nodes}
    dependents: dict[str, list[str]] = defaultdict(list)
    for e in edges:
        in_degree[e.consumer] += 1
        dependents[e.provider].append(e.consumer)

    ready = deque(sorted(n for n, d in in_degree.items() if d == 0))
    order: list[str] = []
    while ready:
        n = ready.popleft()
        order.append(n)
        for dep in sorted(dependents[n]):
            in_degree[dep] -= 1
            if in_degree[dep] == 0:
                ready.append(dep)

    if len(order) != len(all_nodes):
        residual = sorted(n for n in all_nodes if n not in order)
        raise ValueError(
            f"dependency DAG is not acyclic — cycle among: {residual}"
        )
    return order


def critical_path() -> list[str]:
    """The longest provider-first chain among DRW's shared primitives — the
    load-bearing nodes Read/Write/Speak rest on. Computed as the longest path
    through the DRW-internal subgraph; returns ``['drw:1', 'drw:3', 'drw:10']``
    in build (provider-first) order.

    The acceptance criterion (SPR-01 M4) is that this returns the DRW
    SPR-01 → SPR-03 → SPR-10 spine; the test asserts membership rather than
    trusting the literal."""
    # Provider → consumers, restricted to DRW spine edges.
    drw_edges = tuple(
        e for e in EDGES if e.consumer.startswith("drw:") and e.provider.startswith("drw:")
    )
    # adjacency provider → consumers (we walk deepening dependents).
    succ: dict[str, list[str]] = defaultdict(list)
    for e in drw_edges:
        succ[e.provider].append(e.consumer)

    # Longest path by node count, memoized over the (acyclic) DRW subgraph.
    best: dict[str, list[str]] = {}

    def longest_from(n: str) -> list[str]:
        if n in best:
            return best[n]
        paths = [longest_from(c) for c in succ.get(n, [])]
        tail = max(paths, key=len) if paths else []
        best[n] = [n] + tail
        return best[n]

    drw_nodes = {e.consumer for e in drw_edges} | {e.provider for e in drw_edges}
    if not drw_nodes:
        return list(CRITICAL_PATH_NODES)
    overall = max((longest_from(n) for n in drw_nodes), key=len)
    return overall
