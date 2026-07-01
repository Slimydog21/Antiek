#!/usr/bin/env python3
"""graph doctor — a read-only health report over the Antiek knowledge graph.

The workstation instrument for "what is actually in my graph, and is its shape
healthy?" It is *observability*, not a gate: it opens the DuckDB graph
``read_only=True`` and reports the graph's SHAPE. It mints no rights, dedup, or
integrity logic — those live in ``substrate/corpus_audit.py`` (rights) and the
``tools/lint/*_integrity`` gates (correctness). This composes with them: run the
doctor to *see* the graph, run the gates to *enforce* it.

Reported:

* **Counts** — documents, chunks, nodes, edges, syntheses, ip_holders.
* **Shape / orphans** the schema permits but that usually signal a broken
  pipeline stage:
    - ``documents_without_chunks``  — ingested but never chunked (chunking stalled).
    - ``isolated_nodes``            — a node on neither end of any edge (extracted
                                      but never connected — "shipped into purgatory").
    - ``syntheses_without_manifest``— a synthesis that pinned NO substrate (no
                                      provenance basis for "what the model saw").
* **Edge temporal breakdown** (vs a passed-in ``now``): ``live`` /
  ``superseded`` / ``expired`` — the bitemporal population at a glance.

By default the doctor always exits ``0`` (a report never fails a build). Pass
``--fail-on-orphans`` to make it a soft CI signal: exit ``1`` if ANY orphan
bucket is non-empty (useful once a graph fixture exists). Read-only throughout —
the DuckDB single-writer invariant is untouched. ``--json`` emits the metrics as
one machine-readable object.

The metric math is split into a pure ``derive`` step (no DB) so it is unit
tested deterministically; ``collect`` does the read-only SQL.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime


@dataclass
class GraphMetrics:
    counts: dict[str, int] = field(default_factory=dict)
    documents_without_chunks: int = 0
    isolated_nodes: int = 0
    syntheses_without_manifest: int = 0
    edges_live: int = 0
    edges_superseded: int = 0
    edges_expired: int = 0

    @property
    def total_orphans(self) -> int:
        return (self.documents_without_chunks
                + self.isolated_nodes
                + self.syntheses_without_manifest)


# --------------------------------------------------------------------------- #
# Pure derivation — the edge temporal split from plain rows (no DB). Unit tested.
# --------------------------------------------------------------------------- #
def derive_edge_temporal(
    rows: list[tuple[str | None, datetime | None]], now: datetime
) -> tuple[int, int, int]:
    """``rows`` are ``(superseded_by, valid_until)`` per edge. Returns
    ``(live, superseded, expired)``. Precedence: a superseded edge counts as
    superseded even if also expired (supersession is the stronger statement);
    a non-superseded edge is live while ``valid_until`` is NULL or in the
    future, else expired."""
    live = superseded = expired = 0
    for superseded_by, valid_until in rows:
        if superseded_by is not None:
            superseded += 1
        elif valid_until is None or valid_until > now:
            live += 1
        else:
            expired += 1
    return live, superseded, expired


# --------------------------------------------------------------------------- #
# Read-only collection
# --------------------------------------------------------------------------- #
def collect(graph_path: str, now: datetime) -> GraphMetrics:
    import duckdb

    con = duckdb.connect(graph_path, read_only=True)
    m = GraphMetrics()
    try:
        def scalar(sql: str) -> int:
            try:
                r = con.execute(sql).fetchone()
                return int(r[0]) if r and r[0] is not None else 0
            except duckdb.CatalogException:
                return 0

        for t in ("documents", "chunks", "nodes", "edges", "syntheses", "ip_holders"):
            m.counts[t] = scalar(f"SELECT count(*) FROM {t}")

        m.documents_without_chunks = scalar(
            "SELECT count(*) FROM documents d "
            "WHERE NOT EXISTS (SELECT 1 FROM chunks c WHERE c.document_id = d.document_id)"
        )
        m.isolated_nodes = scalar(
            "SELECT count(*) FROM nodes n WHERE NOT EXISTS ("
            "  SELECT 1 FROM edges e WHERE e.source_node_id = n.node_id "
            "     OR e.target_node_id = n.node_id)"
        )
        m.syntheses_without_manifest = scalar(
            "SELECT count(*) FROM syntheses s WHERE NOT EXISTS ("
            "  SELECT 1 FROM synthesis_substrate_manifest m "
            "  WHERE m.synthesis_id = s.synthesis_id)"
        )
        try:
            edge_rows = con.execute(
                "SELECT superseded_by, valid_until FROM edges"
            ).fetchall()
        except duckdb.CatalogException:
            edge_rows = []
        m.edges_live, m.edges_superseded, m.edges_expired = derive_edge_temporal(
            edge_rows, now
        )
        return m
    finally:
        con.close()


# --------------------------------------------------------------------------- #
# Pure rendering
# --------------------------------------------------------------------------- #
def render(m: GraphMetrics) -> str:
    lines = ["knowledge-graph health report", "=" * 30, "", "counts:"]
    lines += [f"  {t:<12} {n:>10,}" for t, n in m.counts.items()]
    lines += [
        "",
        "shape / orphans:",
        f"  documents_without_chunks    {m.documents_without_chunks:>10,}",
        f"  isolated_nodes              {m.isolated_nodes:>10,}",
        f"  syntheses_without_manifest  {m.syntheses_without_manifest:>10,}",
        "",
        "edges (temporal):",
        f"  live        {m.edges_live:>10,}",
        f"  superseded  {m.edges_superseded:>10,}",
        f"  expired     {m.edges_expired:>10,}",
        "",
        f"total orphan-shape rows: {m.total_orphans:,}",
    ]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--graph", default=None,
                   help="DuckDB graph file. Omit for a clean no-op (exit 0).")
    p.add_argument("--json", action="store_true", help="Emit metrics as JSON.")
    p.add_argument("--fail-on-orphans", action="store_true",
                   help="Exit 1 if any orphan-shape bucket is non-empty.")
    args = p.parse_args(argv)

    if args.graph is None:
        print("graph_doctor: no --graph given; nothing to report (clean).")
        return 0

    from pathlib import Path
    if not Path(args.graph).exists():
        print(f"::error::graph_doctor: graph not found: {args.graph}", file=sys.stderr)
        return 2

    m = collect(args.graph, datetime.now())
    if args.json:
        print(json.dumps(asdict(m) | {"total_orphans": m.total_orphans}, indent=2))
    else:
        print(render(m))

    if args.fail_on_orphans and m.total_orphans > 0:
        print(f"\n::error::graph_doctor: {m.total_orphans} orphan-shape row(s) "
              f"(un-chunked docs / isolated nodes / unpinned syntheses).",
              file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
