#!/usr/bin/env python3
"""Knowledge-graph temporal-integrity audit — the bitemporal invariants the DB can't hold.

The Antiek knowledge graph is bitemporal: ``edges`` (substrate/graph/schema.py)
carry ``valid_from``, ``valid_until`` (NULL = still valid) and ``superseded_by``
(a FK to ``edges.edge_id``). The FK already stops a *dangling* ``superseded_by``,
and a nullable-FK re-check would only duplicate the store. This gate covers the
temporal invariants the schema has **no** way to express as a constraint:

  1. **Inverted window** — ``valid_until`` is non-NULL and ``valid_until <
     valid_from``. A fact that stops being true before it started is impossible;
     no CHECK enforces it.
  2. **Self-supersession** — ``superseded_by == edge_id``. The FK is satisfied
     (it points at a real edge — itself) but the edge supersedes itself, a
     degenerate 1-cycle.
  3. **Supersession cycle** — following ``superseded_by`` loops (A→B→A, or
     longer). A FK cannot forbid a cycle, yet a cyclic supersession chain has no
     "latest" edge — the graph's notion of *which fact replaced which* is broken.
  4. **Current-truth ambiguity** — more than one LIVE edge for the same
     ``(source_node_id, target_node_id, relation)``, where LIVE means
     ``superseded_by IS NULL`` AND (``valid_until IS NULL`` OR ``valid_until`` is
     in the future relative to a passed-in ``now``). A knowledge graph must
     assert at most one *current truth* per (source, target, relation); two live
     edges is an unresolved contradiction the retrieval layer cannot rank.

Read-only (the DuckDB single-writer invariant is untouched). ``--graph PATH``
audits a live graph ``read_only=True``; with no graph it is a clean no-op
(deterministic pass), safe to wire into CI before a graph fixture exists.
Findings that predate the gate are grandfathered in a shrink-only baseline.

Output: one ``edge_id|surface: <detail>`` line per NEW finding + a summary count.
Exit ``0`` = clean OR all baselined; exit ``1`` = a NEW temporal violation.
Mirrors the exit-code contract of ``tools/lint/serve_guard_check.py``.

The pure core takes plain rows and an explicit ``now`` (never ``datetime.now()``)
so ``tests/test_graph_temporal_integrity.py`` is deterministic and falsifiable
without a database.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

DEFAULT_BASELINE = Path(__file__).resolve().parent / "baselines" / "graph_temporal.json"


@dataclass(frozen=True)
class Edge:
    edge_id: str
    source_node_id: str
    target_node_id: str
    relation: str
    valid_from: datetime
    valid_until: datetime | None
    superseded_by: str | None


@dataclass(frozen=True)
class Finding:
    """``key()`` is the stable baseline identity — no volatile data (timestamps,
    iteration order) so the shrink-only baseline does not thrash."""

    surface: str   # "inverted_window" | "self_supersession" | "supersession_cycle" | "duplicate_live"
    edge_id: str
    detail: str

    def key(self) -> str:
        return f"{self.surface}\t{self.edge_id}\t{self.detail}"

    def line(self) -> str:
        return f"{self.edge_id}|{self.surface}: {self.detail}"


# --------------------------------------------------------------------------- #
# Pure audit core — no DB, deterministic (``now`` is always explicit).
# --------------------------------------------------------------------------- #
def audit_inverted_windows(edges: Iterable[Edge]) -> list[Finding]:
    out: list[Finding] = []
    for e in edges:
        if e.valid_until is not None and e.valid_until < e.valid_from:
            out.append(Finding("inverted_window", e.edge_id,
                               f"valid_until {e.valid_until.isoformat()} < "
                               f"valid_from {e.valid_from.isoformat()}"))
    return out


def audit_self_supersession(edges: Iterable[Edge]) -> list[Finding]:
    return [
        Finding("self_supersession", e.edge_id, "edge supersedes itself")
        for e in edges
        if e.superseded_by is not None and e.superseded_by == e.edge_id
    ]


def audit_supersession_cycles(edges: Iterable[Edge]) -> list[Finding]:
    """Report every edge that lies on a ``superseded_by`` cycle (length >= 2).
    Self-supersession (length 1) is reported by ``audit_self_supersession`` and
    is deliberately excluded here so a degenerate case is not double-counted."""
    nxt = {e.edge_id: e.superseded_by for e in edges}
    on_cycle: set[str] = set()
    for start in nxt:
        seen: list[str] = []
        cur: str | None = start
        while cur is not None and cur in nxt and cur not in seen:
            seen.append(cur)
            cur = nxt[cur]
        # ``cur`` closed a loop iff it points back into the path we just walked.
        if cur is not None and cur in seen:
            cycle = seen[seen.index(cur):]
            if len(cycle) >= 2:
                on_cycle.update(cycle)
    return [
        Finding("supersession_cycle", eid,
                "edge is on a superseded_by cycle (no latest edge)")
        for eid in sorted(on_cycle)
    ]


def _is_live(e: Edge, now: datetime) -> bool:
    return e.superseded_by is None and (e.valid_until is None or e.valid_until > now)


def audit_current_truth_uniqueness(edges: Iterable[Edge], now: datetime) -> list[Finding]:
    """At most one LIVE edge per (source, target, relation). Two live edges are a
    contradiction the retrieval layer cannot rank. Every edge in an offending
    group is reported (the whole group is the ambiguity)."""
    groups: dict[tuple[str, str, str], list[Edge]] = defaultdict(list)
    for e in edges:
        if _is_live(e, now):
            groups[(e.source_node_id, e.target_node_id, e.relation)].append(e)
    out: list[Finding] = []
    for (src, tgt, rel), members in groups.items():
        if len(members) > 1:
            ids = ", ".join(sorted(m.edge_id for m in members))
            for m in sorted(members, key=lambda m: m.edge_id):
                out.append(Finding("duplicate_live", m.edge_id,
                                   f"{len(members)} live edges for "
                                   f"({src},{tgt},{rel}): {ids}"))
    return out


def audit_edges(edges: list[Edge], now: datetime) -> list[Finding]:
    return (
        audit_inverted_windows(edges)
        + audit_self_supersession(edges)
        + audit_supersession_cycles(edges)
        + audit_current_truth_uniqueness(edges, now)
    )


# --------------------------------------------------------------------------- #
# Baseline (shrink-only)
# --------------------------------------------------------------------------- #
def load_baseline(path: Path) -> set[str]:
    if not path.exists():
        return set()
    return set(json.loads(path.read_text()).get("baselined_keys", []))


def new_findings(findings: list[Finding], baseline: set[str]) -> list[Finding]:
    return [f for f in findings if f.key() not in baseline]


# --------------------------------------------------------------------------- #
# DuckDB extraction (read-only)
# --------------------------------------------------------------------------- #
def load_edges_from_duckdb(graph_path: str) -> list[Edge]:
    import duckdb

    con = duckdb.connect(graph_path, read_only=True)
    try:
        try:
            rows = con.execute(
                "SELECT edge_id, source_node_id, target_node_id, relation, "
                "valid_from, valid_until, superseded_by FROM edges"
            ).fetchall()
        except duckdb.CatalogException:
            return []
        return [Edge(*r) for r in rows]
    finally:
        con.close()


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--graph", default=None,
                        help="DuckDB graph file. Omit for a clean no-op (exit 0).")
    parser.add_argument("--baseline", default=str(DEFAULT_BASELINE))
    parser.add_argument("--update-baseline", action="store_true",
                        help="Re-mint the baseline from CURRENT findings "
                             "(operator-only; never to silence a live regression).")
    args = parser.parse_args(argv)

    if args.graph is None:
        print("graph_temporal_integrity: no --graph given; nothing to audit (clean).")
        return 0
    if not Path(args.graph).exists():
        print(f"::error::graph_temporal_integrity: graph not found: {args.graph}", file=sys.stderr)
        return 2

    # ``now`` is read once, at the process boundary, and threaded into the pure
    # core — the core itself never calls the clock, so its result is a function
    # of its inputs only.
    now = datetime.now()
    findings = audit_edges(load_edges_from_duckdb(args.graph), now)
    baseline_path = Path(args.baseline)

    if args.update_baseline:
        baseline_path.parent.mkdir(parents=True, exist_ok=True)
        baseline_path.write_text(
            json.dumps({"baselined_keys": sorted(f.key() for f in findings)}, indent=2) + "\n"
        )
        print(f"graph_temporal_integrity: baseline re-minted with {len(findings)} finding(s).")
        return 0

    fresh = new_findings(findings, load_baseline(baseline_path))
    if not fresh:
        print(f"graph_temporal_integrity: OK — no NEW temporal violations "
              f"({len(findings)} baselined).")
        return 0
    for f in fresh:
        print(f.line())
    print(f"\n::error::graph_temporal_integrity: {len(fresh)} NEW temporal "
          f"violation(s) in the knowledge graph.", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
