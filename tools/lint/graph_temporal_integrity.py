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

Deliberately **not** gated: "more than one live edge per
``(source_node_id, target_node_id, relation)``". That is *not* a violation in
this graph. ``substrate/graph/ops.py:insert_edge`` content-addresses the
``edge_id`` from ``(source, relation, target, chunk_id)`` — "the same triple
from different chunks gets distinct ids … the desired behavior for
evidence-attributed graphs." Two live edges over one triple therefore differ in
grounding: legitimate multi-source corroboration, ranked by tier/confidence at
retrieval, not a contradiction. A same-grounding duplicate is impossible (the
content-addressed id would collide on the PRIMARY KEY). A per-triple live fan-out
count is fine as *observability* (see ``tools/graph_doctor.py``); it is not an
exit-1 gate.

Read-only (the DuckDB single-writer invariant is untouched). ``--graph PATH``
audits a live graph ``read_only=True``; with no graph it is a clean no-op
(deterministic pass), safe to wire into CI before a graph fixture exists. If a
graph IS given but its schema does not resolve (a table or column this gate
queries was renamed/dropped), the gate fails LOUD (exit 2) rather than crashing
with a traceback or silently passing — it cannot certify a schema it no longer
understands. Findings that predate the gate are grandfathered in a shrink-only
baseline.

Output: one ``edge_id|surface: <detail>`` line per NEW finding + a summary count.
Exit ``0`` = clean OR all baselined; ``1`` = a NEW temporal violation; ``2`` =
no graph found / schema drift. Mirrors the exit-code contract of
``tools/lint/serve_guard_check.py``.

The pure core takes plain rows (no clock, no DB), so
``tests/test_graph_temporal_integrity.py`` is deterministic and falsifiable
without a database.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

DEFAULT_BASELINE = Path(__file__).resolve().parent / "baselines" / "graph_temporal.json"


class SchemaDriftError(RuntimeError):
    """A ``--graph`` was given but a table/column this gate SELECTs is missing or
    renamed. The gate cannot certify integrity against a schema it does not
    understand, so it fails loud (exit 2) — never a raw crash, never a silent
    pass that would hide real violations behind a renamed table."""


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

    surface: str   # "inverted_window" | "self_supersession" | "supersession_cycle"
    edge_id: str
    detail: str

    def key(self) -> str:
        return f"{self.surface}\t{self.edge_id}\t{self.detail}"

    def line(self) -> str:
        return f"{self.edge_id}|{self.surface}: {self.detail}"


# --------------------------------------------------------------------------- #
# Pure audit core — no DB, no clock. A function of its inputs only.
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
    is deliberately excluded here so a degenerate case is not double-counted.

    ``seen`` is tracked as both an ordered path (to slice out the cycle) and a
    set for O(1) membership. Total work is bounded by chain length; supersession
    chains are short in practice, so this is not a hot path."""
    nxt = {e.edge_id: e.superseded_by for e in edges}
    on_cycle: set[str] = set()
    for start in nxt:
        path: list[str] = []
        visited: set[str] = set()
        cur: str | None = start
        while cur is not None and cur in nxt and cur not in visited:
            visited.add(cur)
            path.append(cur)
            cur = nxt[cur]
        # ``cur`` closed a loop iff it points back into the path we just walked.
        if cur is not None and cur in visited:
            cycle = path[path.index(cur):]
            if len(cycle) >= 2:
                on_cycle.update(cycle)
    return [
        Finding("supersession_cycle", eid,
                "edge is on a superseded_by cycle (no latest edge)")
        for eid in sorted(on_cycle)
    ]


def audit_edges(edges: list[Edge]) -> list[Finding]:
    return (
        audit_inverted_windows(edges)
        + audit_self_supersession(edges)
        + audit_supersession_cycles(edges)
    )


# --------------------------------------------------------------------------- #
# Baseline (shrink-only by construction)
# --------------------------------------------------------------------------- #
def load_baseline(path: Path) -> set[str]:
    if not path.exists():
        return set()
    return set(json.loads(path.read_text()).get("baselined_keys", []))


def new_findings(findings: list[Finding], baseline: set[str]) -> list[Finding]:
    return [f for f in findings if f.key() not in baseline]


def _write_baseline(path: Path, keys: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"baselined_keys": keys}, indent=2) + "\n")


def shrink_baseline(old: set[str], current_keys: set[str]) -> list[str]:
    """Drop baselined keys that no longer fire; NEVER add a new key. A live
    regression cannot be silenced through this path — that is what makes
    "shrink-only" a mechanical property, not a review-time hope."""
    return sorted(k for k in old if k in current_keys)


# --------------------------------------------------------------------------- #
# DuckDB extraction (read-only, schema-strict)
# --------------------------------------------------------------------------- #
def load_edges_from_duckdb(graph_path: str) -> list[Edge]:
    import duckdb

    try:
        con = duckdb.connect(graph_path, read_only=True)
    except duckdb.Error as exc:
        raise SchemaDriftError(f"cannot open graph: {exc}") from exc
    try:
        try:
            rows = con.execute(
                "SELECT edge_id, source_node_id, target_node_id, relation, "
                "valid_from, valid_until, superseded_by FROM edges"
            ).fetchall()
        except duckdb.Error as exc:
            raise SchemaDriftError(f"edges not resolvable: {exc}") from exc
        edges: list[Edge] = []
        for r in rows:
            valid_from, valid_until = r[4], r[5]
            if not isinstance(valid_from, datetime) or (
                valid_until is not None and not isinstance(valid_until, datetime)
            ):
                raise SchemaDriftError(
                    f"edges temporal columns are not TIMESTAMP (edge {r[0]})"
                )
            edges.append(Edge(*r))
        return edges
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
                        help="Shrink-only re-mint: drop baselined keys that no "
                             "longer fire. NEVER adds a key, so it cannot silence "
                             "a live regression.")
    parser.add_argument("--grandfather", action="store_true",
                        help="Deliberately mint the baseline from ALL current "
                             "findings — the one path that may grow it "
                             "(operator-only, reviewed).")
    args = parser.parse_args(argv)

    if args.graph is None:
        print("graph_temporal_integrity: no --graph given; nothing to audit (clean).")
        return 0
    if not Path(args.graph).exists():
        print(f"::error::graph_temporal_integrity: graph not found: {args.graph}", file=sys.stderr)
        return 2

    try:
        findings = audit_edges(load_edges_from_duckdb(args.graph))
    except SchemaDriftError as exc:
        print(f"::error::graph_temporal_integrity: schema drift — {exc}. Audit "
              f"cannot certify temporal integrity; update the gate for the new "
              f"schema.", file=sys.stderr)
        return 2

    baseline_path = Path(args.baseline)
    current_keys = {f.key() for f in findings}

    if args.grandfather:
        _write_baseline(baseline_path, sorted(current_keys))
        print(f"graph_temporal_integrity: baseline grandfathered with "
              f"{len(current_keys)} finding(s).")
        return 0
    if args.update_baseline:
        old = load_baseline(baseline_path)
        kept = shrink_baseline(old, current_keys)
        _write_baseline(baseline_path, kept)
        print(f"graph_temporal_integrity: baseline shrunk {len(old)} -> "
              f"{len(kept)} ({len(old) - len(kept)} resolved key(s) dropped).")
        # fall through and STILL enforce against the shrunk baseline: a live
        # regression present during maintenance must not exit 0.

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
