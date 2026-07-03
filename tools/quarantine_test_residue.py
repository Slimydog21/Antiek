#!/usr/bin/env python3
"""quarantine_test_residue — move test residue OUT of the real store, reversibly.

DOGFOOD SPR-04 M3. The real ``~/.antiek/research_graph.duckdb`` carries test
residue that leaked in before the SPR-04 isolation guard existed. This tool
MOVES that residue into ``_quarantine_edges`` / ``_quarantine_nodes`` archive
tables (original ids + a ``moved_at`` timestamp + a ``quarantine_reason``
preserved) so a maintainer can audit or restore. It never DELETEs silently —
honest remediation is reversible, evidence-preserving, and operator-confirmed.

Provenance-honest identification (verify, don't guess):

* **Edges** — ``investigation_id = 'inv-1'`` (the lone test investigation; the
  only edge in the store, extracted 2026-05-26, referencing placeholder test
  nodes). Unambiguous.
* **Nodes** — non-entity nodes (``insight`` / ``question`` / ``claim``) whose
  source document (``metadata->>source_document_id`` or ``->>document_id``) is
  NOT present in ``documents``. These are test fixtures orphaned to placeholder
  doc ids like ``doc-1`` / ``d`` (e.g. canonical labels ``'source?'``, ``'t'``,
  ``'Acme is mid-sized.'``). A node whose provenance is ambiguous (NULL doc id,
  or a doc id that resolves to a real document) is LEFT and flagged.

SPEC CORRECTION (intellectual honesty): the SPR-04 brief's M1 premise named
"1147 page-heading-stub nodes" as test residue. That is wrong — those are the
``## Page N`` entity nodes created by the production books reader
(``acquisition/books/reader.py``) for the operator's REAL libgen books; 100% of
them resolve to real ``doc-book-*`` documents. Quarantining them would destroy
operator data. This tool's entity-excluding criterion enforces that correction
mechanically: only non-entity nodes orphaned to non-existent docs are moved.

Single-writer discipline throughout (``runtime.db_lock.connect_write``).
``--dry-run`` is the default; ``--apply`` requires
``--confirm-i-understand-this-mutates-prod``; ``--restore`` moves rows back.
"""

from __future__ import annotations

import argparse
import os
import sys
from dataclasses import dataclass

# Resolve the worktree's own modules (the editable-install .pth in the shared
# venv points at ~/Antiek/platform and shadows a worktree's namespace; CI's
# clean env is unaffected).
_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(_HERE)))

from runtime.db_lock import connect_write  # noqa: E402
from substrate.graph import default_db_path  # noqa: E402

# The lone test investigation whose edge is unambiguous residue.
_TEST_INVESTIGATION_ID = "inv-1"


@dataclass
class ResidueReport:
    """What the tool found (pure — no DB writes). Populated by a read pass."""

    candidate_edges: int = 0
    candidate_nodes: int = 0
    edges_total: int = 0
    nodes_total: int = 0
    entity_nodes_total: int = 0
    # Sample labels so the operator can eyeball that only fixtures matched.
    node_label_samples: tuple[str, ...] = ()


def _identify_residue(con) -> ResidueReport:
    """Read-only scan returning the candidate residue counts. The IDENTIFICATION
    contract lives here so dry-run and apply agree exactly."""
    rep = ResidueReport()
    rep.edges_total = con.execute("SELECT count(*) FROM edges").fetchone()[0]
    rep.nodes_total = con.execute("SELECT count(*) FROM nodes").fetchone()[0]
    rep.entity_nodes_total = con.execute(
        "SELECT count(*) FROM nodes WHERE node_type = 'entity'"
    ).fetchone()[0]
    rep.candidate_edges = con.execute(
        "SELECT count(*) FROM edges WHERE investigation_id = ?",
        [_TEST_INVESTIGATION_ID],
    ).fetchone()[0]
    # Non-entity nodes orphaned to a source doc that is NOT a real document.
    # metadata may be NULL or non-JSON; treat unreadable/absent doc ids as
    # ambiguous → NOT matched (left + flagged, never guessed).
    rep.candidate_nodes = con.execute(
        """
        SELECT count(*)
        FROM nodes n
        WHERE n.node_type IN ('insight', 'question', 'claim')
          AND COALESCE(
                n.metadata::JSON->>'source_document_id',
                n.metadata::JSON->>'document_id'
              ) IS NOT NULL
          AND COALESCE(
                n.metadata::JSON->>'source_document_id',
                n.metadata::JSON->>'document_id'
              ) NOT IN (SELECT document_id FROM documents)
        """
    ).fetchone()[0]
    rep.node_label_samples = tuple(
        r[0]
        for r in con.execute(
            """
            SELECT n.canonical_label
            FROM nodes n
            WHERE n.node_type IN ('insight', 'question', 'claim')
              AND COALESCE(
                    n.metadata::JSON->>'source_document_id',
                    n.metadata::JSON->>'document_id'
                  ) IS NOT NULL
              AND COALESCE(
                    n.metadata::JSON->>'source_document_id',
                    n.metadata::JSON->>'document_id'
                  ) NOT IN (SELECT document_id FROM documents)
            ORDER BY n.node_type, n.created_at
            """
        ).fetchall()
    )
    return rep


def _ensure_quarantine_tables(con) -> None:
    """Create the archive tables if absent (clone source schema, no FKs,
    + moved_at + quarantine_reason). Idempotent."""
    con.execute(
        "CREATE TABLE IF NOT EXISTS _quarantine_edges AS "
        "SELECT *, CAST(NULL AS TIMESTAMP) AS moved_at, "
        "CAST(NULL AS VARCHAR) AS quarantine_reason FROM edges WHERE 1=0"
    )
    con.execute(
        "CREATE TABLE IF NOT EXISTS _quarantine_nodes AS "
        "SELECT *, CAST(NULL AS TIMESTAMP) AS moved_at, "
        "CAST(NULL AS VARCHAR) AS quarantine_reason FROM nodes WHERE 1=0"
    )


def _apply(con, reason: str, rep: ResidueReport) -> tuple[int, int]:
    """MOVE candidate residue into the archive (insert + delete). Returns
    (edges_moved, nodes_moved)."""
    _ensure_quarantine_tables(con)
    con.execute(
        "INSERT INTO _quarantine_edges "
        "SELECT *, CURRENT_TIMESTAMP, ? FROM edges "
        "WHERE investigation_id = ?",
        [reason, _TEST_INVESTIGATION_ID],
    )
    con.execute(
        "DELETE FROM edges WHERE investigation_id = ?", [_TEST_INVESTIGATION_ID]
    )
    con.execute(
        """
        INSERT INTO _quarantine_nodes
        SELECT *, CURRENT_TIMESTAMP, ?
        FROM nodes n
        WHERE n.node_type IN ('insight', 'question', 'claim')
          AND COALESCE(
                n.metadata::JSON->>'source_document_id',
                n.metadata::JSON->>'document_id'
              ) IS NOT NULL
          AND COALESCE(
                n.metadata::JSON->>'source_document_id',
                n.metadata::JSON->>'document_id'
              ) NOT IN (SELECT document_id FROM documents)
        """,
        [reason],
    )
    con.execute(
        """
        DELETE FROM nodes
        WHERE node_type IN ('insight', 'question', 'claim')
          AND COALESCE(
                metadata::JSON->>'source_document_id',
                metadata::JSON->>'document_id'
              ) IS NOT NULL
          AND COALESCE(
                metadata::JSON->>'source_document_id',
                metadata::JSON->>'document_id'
              ) NOT IN (SELECT document_id FROM documents)
        """
    )
    return rep.candidate_edges, rep.candidate_nodes


def _restore(con) -> tuple[int, int]:
    """MOVE archived rows back to their source tables. Returns
    (edges_restored, nodes_restored). Nodes first (edges reference them)."""
    nodes_n = con.execute("SELECT count(*) FROM _quarantine_nodes").fetchone()[0]
    if nodes_n:
        con.execute(
            "INSERT INTO nodes "
            "SELECT * EXCLUDE (moved_at, quarantine_reason) FROM _quarantine_nodes"
        )
        con.execute("DELETE FROM _quarantine_nodes")
    edges_n = con.execute("SELECT count(*) FROM _quarantine_edges").fetchone()[0]
    if edges_n:
        con.execute(
            "INSERT INTO edges "
            "SELECT * EXCLUDE (moved_at, quarantine_reason) FROM _quarantine_edges"
        )
        con.execute("DELETE FROM _quarantine_edges")
    return edges_n, nodes_n


def _print_report(rep: ResidueReport, *, verb: str) -> None:
    print(f"\n=== residue {verb} ===")
    print(f"  candidate edges (investigation_id={_TEST_INVESTIGATION_ID}): "
          f"{rep.candidate_edges} of {rep.edges_total} total")
    print(f"  candidate nodes (non-entity, orphaned to a non-existent doc): "
          f"{rep.candidate_nodes} of {rep.nodes_total} total "
          f"({rep.entity_nodes_total} entity nodes PROTECTED — real operator data)")
    if rep.node_label_samples:
        samples = ", ".join(repr(s) for s in rep.node_label_samples[:8])
        print(f"  node label samples: {samples}")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--db-path", default=None, help="graph DB path "
                     "(default: substrate.graph.default_db_path())")
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument("--apply", action="store_true",
                      help="MOVE residue into the quarantine archive")
    mode.add_argument("--restore", action="store_true",
                      help="MOVE quarantined rows back to their source tables")
    ap.add_argument("--dry-run", action="store_true", default=True,
                    help="report only; default unless --apply/--restore")
    ap.add_argument("--confirm-i-understand-this-mutates-prod", action="store_true",
                    help="required gate for --apply / --restore against the real store")
    ap.add_argument("--reason", default="DOGFOOD SPR-04 test-residue quarantine",
                    help="quarantine_reason stamped on moved rows")
    args = ap.parse_args(argv)

    db_path = args.db_path or default_db_path()
    real = os.path.realpath(os.path.expanduser("~/.antiek/research_graph.duckdb"))
    is_prod = os.path.realpath(db_path) == real
    mutating = args.apply or args.restore

    if mutating:
        if not args.confirm_i_understand_this_mutates_prod:
            print("REFUSING: --apply/--require requires "
                  "--confirm-i-understand-this-mutates-prod.", file=sys.stderr)
            return 2
        if is_prod:
            print(f"NOTICE: mutating the REAL store at {db_path}", file=sys.stderr)

    if args.restore:
        with connect_write(db_path, purpose="quarantine-restore") as con:
            n = con.execute("SELECT count(*) FROM _quarantine_nodes").fetchone()[0]
            e = con.execute("SELECT count(*) FROM _quarantine_edges").fetchone()[0]
            if not (n or e) and not is_prod:
                # nothing archived; still create tables for a clean restore path
                _ensure_quarantine_tables(con)
            edges_n, nodes_n = _restore(con)
        print("\n=== restore complete ===")
        print(f"  edges restored: {edges_n}; nodes restored: {nodes_n}")
        return 0

    with connect_write(db_path, purpose="quarantine-test-residue") as con:
        # dry-run/apply share one read so the reported plan == the moved set.
        rep = _identify_residue(con)
        _print_report(rep, verb=("to move" if not args.apply else "moved"))
        if not args.apply:
            print("\n(dry-run — no rows moved; pass --apply "
                  "--confirm-i-understand-this-mutates-prod to move)")
            after_edges = rep.edges_total
            after_nodes = rep.nodes_total
        else:
            em, nm = _apply(con, args.reason, rep)
            after_edges = con.execute("SELECT count(*) FROM edges").fetchone()[0]
            after_nodes = con.execute("SELECT count(*) FROM nodes").fetchone()[0]
            print("\n=== apply complete ===")
            print(f"  moved: {em} edges, {nm} nodes → _quarantine_*")

    print("\n=== store counts (before → after) ===")
    print(f"  edges: {rep.edges_total} → {after_edges}")
    print(f"  nodes: {rep.nodes_total} → {after_nodes} "
          f"(entity nodes unchanged at {rep.entity_nodes_total})")
    if not args.apply and not args.restore:
        print("\nReversibility: --restore moves archived rows back to their "
              "source tables (ids + schema preserved).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
