#!/usr/bin/env python3
"""Provenance-edge integrity audit — the knowledge graph's dangling-reference gate.

Antiek's provenance chain (``CLAUDE.md`` invariant #3, master-spec §2.5)::

    claim -> chunk -> document -> ip_holder

must never dangle. The *structural* edges of that chain are already FOREIGN KEYs
in ``substrate/graph/schema.py`` — ``chunks.document_id``,
``edges.source_node_id``, ``edges.target_node_id`` all carry ``REFERENCES``
clauses, so the store itself refuses a dangling insert there. Re-checking those
would only duplicate the DB.

This gate covers the provenance references the schema **cannot** express as a
foreign key — the places a dangling edge can appear that the DB will *not*
catch:

  1. ``synthesis_substrate_manifest.entity_id`` — a POLYMORPHIC reference: one
     column pinned by ``entity_kind IN ('document','chunk','node','edge')`` plus
     a free-text ``entity_id``. A single FK cannot span four target tables, so
     nothing stops a synthesis from pinning substrate that was later deleted.
     The result is a synthesis whose provenance manifest cites evidence that no
     longer exists — a broken "what did the model actually see" guarantee.
  2. ``edges.chunk_id`` / ``edges.source_document_id`` — NULLABLE grounding
     columns. ``NULL`` is legitimate (a structural edge with no single grounding
     chunk/document); a NON-null value that does not resolve to a live row is a
     dangling grounding edge. DuckDB does not enforce a FK on a nullable column
     across all write paths, so this is a real, uncaught drift surface.

The audit is READ-ONLY (never writes to the graph; the DuckDB single-writer
invariant is untouched). Given ``--graph PATH`` it opens the graph
``read_only=True`` and queries the live tables; with no graph it is a clean
no-op — a deterministic pass — so it is safe to wire into CI before a graph
fixture exists. If a graph IS given, every expected table/column must resolve;
a renamed/dropped one is reported as schema drift (exit 2), never crashed on and
never silently passed. Findings that predate this gate are grandfathered in a
shrink-only baseline: ``--update-baseline`` may only DROP resolved keys (it can
never silence a new regression); growing the baseline needs an explicit,
reviewed ``--grandfather``.

Output: one ``kind|ref_id: <what dangles>`` line per NEW (non-baselined) finding
plus a summary count. Exit ``0`` = clean OR every finding is baselined; exit
``1`` = at least one NEW dangling reference. This mirrors the exit-code contract
of ``tools/lint/serve_guard_check.py`` (0 = clean, 1 = violations).

Pure core (``audit_manifest`` / ``audit_edge_grounding``) operates on plain
in-memory rows and takes no DB — it is exercised directly by
``tests/test_provenance_edge_audit.py`` with a seeded dangling edge, so the gate
is falsifiable without a live database.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

# The four kinds a synthesis manifest may pin, each mapped to its owning table's
# primary-key column. Mirrors the CHECK constraint on
# synthesis_substrate_manifest.entity_kind in substrate/graph/schema.py.
MANIFEST_KIND_TABLE: dict[str, tuple[str, str]] = {
    "document": ("documents", "document_id"),
    "chunk": ("chunks", "chunk_id"),
    "node": ("nodes", "node_id"),
    "edge": ("edges", "edge_id"),
}

DEFAULT_BASELINE = Path(__file__).resolve().parent / "baselines" / "provenance_edges.json"


@dataclass(frozen=True)
class Finding:
    """One dangling provenance reference. ``key()`` is the stable identity used
    for baseline membership — it must not embed anything volatile (timestamps,
    row order) or the shrink-only baseline would thrash."""

    surface: str          # "manifest" | "edge.chunk_id" | "edge.source_document_id"
    ref_id: str           # the dangling entity_id / edge_id
    detail: str           # human-readable "<owner> -> <missing kind> <id>"

    def key(self) -> str:
        return f"{self.surface}\t{self.ref_id}\t{self.detail}"

    def line(self) -> str:
        return f"{self.surface}|{self.ref_id}: {self.detail}"


# --------------------------------------------------------------------------- #
# Pure audit core — no database, no I/O. Falsifiable in a unit test.
# --------------------------------------------------------------------------- #
def audit_manifest(
    manifest_rows: Iterable[tuple[str, str, str]],
    live_ids: Mapping[str, set[str]],
) -> list[Finding]:
    """Every ``(synthesis_id, entity_kind, entity_id)`` must resolve to a live
    row in the table named by ``entity_kind``.

    ``manifest_rows``: rows of ``synthesis_substrate_manifest``.
    ``live_ids``: kind -> set of live primary keys, e.g.
        ``{"document": {...}, "chunk": {...}, "node": {...}, "edge": {...}}``.

    An unknown ``entity_kind`` is itself a finding (the CHECK constraint should
    make it impossible, but a schema drift or a raw insert could smuggle one in,
    and we must not silently pass a reference we cannot resolve).
    """
    findings: list[Finding] = []
    for synthesis_id, kind, entity_id in manifest_rows:
        known = live_ids.get(kind)
        if known is None:
            findings.append(
                Finding("manifest", entity_id,
                        f"synthesis {synthesis_id} pins unknown entity_kind {kind!r}")
            )
            continue
        if entity_id not in known:
            findings.append(
                Finding("manifest", entity_id,
                        f"synthesis {synthesis_id} pins missing {kind} {entity_id}")
            )
    return findings


def audit_edge_grounding(
    edges: Iterable[tuple[str, str | None, str | None]],
    chunk_ids: set[str],
    document_ids: set[str],
) -> list[Finding]:
    """A non-null ``edges.chunk_id`` / ``edges.source_document_id`` must resolve.
    ``NULL`` is allowed (a structural edge with no single grounding source) and
    is never a finding.

    ``edges``: rows of ``(edge_id, chunk_id, source_document_id)``.
    """
    findings: list[Finding] = []
    for edge_id, chunk_id, source_document_id in edges:
        if chunk_id is not None and chunk_id not in chunk_ids:
            findings.append(
                Finding("edge.chunk_id", edge_id,
                        f"edge {edge_id} grounds on missing chunk {chunk_id}")
            )
        if source_document_id is not None and source_document_id not in document_ids:
            findings.append(
                Finding("edge.source_document_id", edge_id,
                        f"edge {edge_id} grounds on missing document {source_document_id}")
            )
    return findings


# --------------------------------------------------------------------------- #
# Baseline (shrink-only)
# --------------------------------------------------------------------------- #
def load_baseline(path: Path) -> set[str]:
    if not path.exists():
        return set()
    data = json.loads(path.read_text())
    return set(data.get("baselined_keys", []))


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
# DuckDB extraction (read-only, schema-strict). Isolated so the pure core
# stays DB-free.
# --------------------------------------------------------------------------- #
class SchemaDriftError(RuntimeError):
    """A ``--graph`` was given but a table/column this gate SELECTs is missing or
    renamed. The gate cannot certify provenance against a schema it does not
    understand, so it fails loud (exit 2) — never a raw crash on a renamed
    column, never a silent pass that would hide real dangling references behind a
    renamed table."""


def load_from_duckdb(
    graph_path: str,
) -> tuple[list[tuple[str, str, str]], dict[str, set[str]], list[tuple[str, str | None, str | None]]]:
    """Return ``(manifest_rows, live_ids, edges)`` extracted read-only. Every
    expected table and column must resolve; a missing/renamed one raises
    ``SchemaDriftError``. A graph passed via ``--graph`` is an assertion that a
    real, migrated graph is present — the gate refuses to certify a schema it no
    longer understands rather than silently passing."""
    import duckdb  # already a substrate dependency

    try:
        con = duckdb.connect(graph_path, read_only=True)
    except duckdb.Error as exc:
        raise SchemaDriftError(f"cannot open graph: {exc}") from exc
    try:
        def q(sql: str, what: str) -> list[Any]:
            try:
                return con.execute(sql).fetchall()
            except duckdb.Error as exc:
                raise SchemaDriftError(f"{what} not resolvable: {exc}") from exc

        live_ids: dict[str, set[str]] = {
            kind: {r[0] for r in q(f"SELECT {col} FROM {table}", f"{table}.{col}")}
            for kind, (table, col) in MANIFEST_KIND_TABLE.items()
        }
        manifest_rows = q(
            "SELECT synthesis_id, entity_kind, entity_id FROM synthesis_substrate_manifest",
            "synthesis_substrate_manifest",
        )
        edges = q("SELECT edge_id, chunk_id, source_document_id FROM edges", "edges")
        return manifest_rows, live_ids, edges
    finally:
        con.close()


def audit_graph(graph_path: str) -> list[Finding]:
    manifest_rows, live_ids, edges = load_from_duckdb(graph_path)
    findings = audit_manifest(manifest_rows, live_ids)
    findings += audit_edge_grounding(
        edges, live_ids.get("chunk", set()), live_ids.get("document", set())
    )
    return findings


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--graph", default=None,
        help="Path to a DuckDB knowledge-graph file. Omit for a clean no-op "
             "(no graph = nothing to audit = exit 0).",
    )
    parser.add_argument("--baseline", default=str(DEFAULT_BASELINE),
                        help="Shrink-only baseline of grandfathered findings.")
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
        print("provenance_edge_audit: no --graph given; nothing to audit (clean).")
        return 0

    if not Path(args.graph).exists():
        print(f"::error::provenance_edge_audit: graph not found: {args.graph}", file=sys.stderr)
        return 2

    try:
        findings = audit_graph(args.graph)
    except SchemaDriftError as exc:
        print(f"::error::provenance_edge_audit: schema drift — {exc}. Audit cannot "
              f"certify provenance; update the gate for the new schema.",
              file=sys.stderr)
        return 2

    baseline_path = Path(args.baseline)
    current_keys = {f.key() for f in findings}

    if args.grandfather:
        _write_baseline(baseline_path, sorted(current_keys))
        print(f"provenance_edge_audit: baseline grandfathered with "
              f"{len(current_keys)} finding(s).")
        return 0
    if args.update_baseline:
        old = load_baseline(baseline_path)
        kept = shrink_baseline(old, current_keys)
        _write_baseline(baseline_path, kept)
        print(f"provenance_edge_audit: baseline shrunk {len(old)} -> {len(kept)} "
              f"({len(old) - len(kept)} resolved key(s) dropped).")
        # fall through and STILL enforce against the shrunk baseline: a live
        # regression present during maintenance must not exit 0.

    fresh = new_findings(findings, load_baseline(baseline_path))
    if not fresh:
        print(
            f"provenance_edge_audit: OK — no NEW dangling provenance references "
            f"({len(findings)} baselined)."
        )
        return 0

    for f in fresh:
        print(f.line())
    print(f"\n::error::provenance_edge_audit: {len(fresh)} NEW dangling provenance "
          f"reference(s). A synthesis or edge cites substrate that does not exist.",
          file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
