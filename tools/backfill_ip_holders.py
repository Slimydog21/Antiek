"""Backfill ``documents.ip_holder_id`` for rows with a NULL holder (SPR-08 T1).

Until SPR-08 T1 wired ``middleware.ip_holder_resolver.resolve_and_apply`` into
the document persist paths (``substrate.graph.ops.insert_document`` and the
arXiv ``oai_persist`` / ``store`` paths), ``documents.ip_holder_id`` had NO
production writer: every row landed NULL, ``asset_to_ip_holder`` resolved
``None`` for every asset, and the per-second escrow guard in
``frame_attention_accrual`` failed on its first clause for every window. This
one-shot tool walks the rows that pre-date the wiring and applies the SAME
resolver the persist path now runs, so the backlog is attributed by exactly
the rule new rows are.

DESIGN INVARIANTS
-----------------
* **Same resolver, same rule.** No second heuristic: ``resolve_and_apply`` is
  the one function the persist path calls (ISBN -> domain -> author, exact
  matches only). A row the registry cannot match stays NULL, which is the safe
  state (revenue rests in escrow; a false positive would misroute it).
* **Never overwrites.** Only ``ip_holder_id IS NULL`` rows are examined, and
  ``apply_resolved_ip_holder`` refuses to overwrite an existing value, so an
  operator-managed attribution is untouchable here.
* **DuckDB single-writer.** The whole pass runs inside ONE
  ``runtime.db_lock.connect_write`` critical section, ``--workers 1`` only. A
  second parallel connection is rejected at argument parsing: the serialized
  host funnel is the sole graph writer and this tool does not weaken it.
  ``ip_holder_id`` is unindexed by schema design (``idx_documents_ip_holder``
  is dropped at init), so the plain UPDATE is safe on rows that chunks or
  book_assets already reference.
* **Dry-run by default.** Without ``--apply`` the tool resolves in memory and
  writes nothing. ``--apply`` is required to mutate.
* **Never prod.** A prod-DB guard mirrors ``tools.backfill_cc0_remap``: a real
  run requires an explicit ``--db-path`` that does NOT resolve to the substrate
  default. Running against the live store is OPERATOR-GATED.
* **Reports the bar's numbers.** The report prints
  ``SELECT count(*) FROM documents WHERE ip_holder_id IS NOT NULL`` before and
  after the pass, which is what the SPR-08 T1 done-bar reads.

Usage:
    # dry-run report (writes nothing)
    python -m tools.backfill_ip_holders --db-path /tmp/antiek-export.duckdb

    # apply to a LOCAL/TEMP DB
    python -m tools.backfill_ip_holders --db-path /tmp/antiek-export.duckdb --apply
"""

from __future__ import annotations

import argparse
import os
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

from middleware.ip_holder_resolver import (  # noqa: E402
    isbn_from_metadata,
    resolve_and_apply,
    resolve_ip_holder,
)
from runtime.db_lock import connect_write  # noqa: E402

# The only worker count this tool accepts: the pass is one write-lock critical
# section and the DuckDB single-writer invariant is absolute.
_ONLY_WORKER_COUNT = 1


@dataclass(frozen=True)
class BackfillReport:
    """What one pass examined and what it changed (or would change)."""

    attributed_before: int  # count(*) WHERE ip_holder_id IS NOT NULL, pre-pass
    examined: int  # rows with a NULL holder at scan time
    resolved: int  # rows the registry matched (written only with --apply)
    attributed_after: int  # count(*) WHERE ip_holder_id IS NOT NULL, post-pass

    @property
    def unresolved(self) -> int:
        return self.examined - self.resolved


def _count_attributed(con: Any) -> int:
    row = con.execute(
        "SELECT count(*) FROM documents WHERE ip_holder_id IS NOT NULL"
    ).fetchone()
    return int(row[0]) if row is not None else 0


def _pass(con: Any, *, apply: bool) -> BackfillReport:
    """Walk every NULL-holder row and resolve it, writing only when ``apply``.

    Runs on the caller's held write connection. The dry run calls
    ``resolve_ip_holder`` (pure); the apply path calls ``resolve_and_apply``,
    the same function the persist path runs, so the two cannot diverge.
    """
    before = _count_attributed(con)
    rows = con.execute(
        "SELECT document_id, source_uri, author, metadata FROM documents "
        "WHERE ip_holder_id IS NULL ORDER BY document_id"
    ).fetchall()
    resolved = 0
    for document_id, source_uri, author, metadata in rows:
        isbn = isbn_from_metadata(metadata)
        if apply:
            hit = resolve_and_apply(
                con,
                document_id=document_id,
                source_uri=source_uri,
                isbn=isbn,
                author=author,
            )
        else:
            hit = resolve_ip_holder(
                con, source_uri=source_uri, isbn=isbn, author=author
            )
        if hit is not None:
            resolved += 1
    after = _count_attributed(con)
    return BackfillReport(
        attributed_before=before,
        examined=len(rows),
        resolved=resolved,
        attributed_after=after,
    )


def run(db_path: str, *, apply: bool) -> BackfillReport:
    """Scan (and optionally apply) the backfill. Public entry for tests.

    One ``connect_write`` critical section for the whole pass, dry run
    included, so there is exactly one DB-access shape and the count a dry run
    reports cannot diverge from the rows an apply rewrites under a concurrent
    writer.
    """
    purpose = "backfill_ip_holders" if apply else "backfill_ip_holders_dryrun"
    with connect_write(db_path, purpose=purpose) as con:
        return _pass(con, apply=apply)


def _print_report(report: BackfillReport, *, applied: bool) -> None:
    verb = "APPLIED" if applied else "DRY RUN (nothing written)"
    print(f"ip_holder backfill — {verb}\n")
    print(
        "  SELECT count(*) FROM documents WHERE ip_holder_id IS NOT NULL"
        f"  [before] : {report.attributed_before}"
    )
    print(f"  documents examined (ip_holder_id IS NULL) : {report.examined}")
    print(f"  resolved by the registry                  : {report.resolved}")
    print(f"  unresolved (left NULL)                    : {report.unresolved}")
    print(
        "  SELECT count(*) FROM documents WHERE ip_holder_id IS NOT NULL"
        f"  [after]  : {report.attributed_after}"
    )
    if not applied and report.resolved:
        print("\n  re-run with --apply to write the resolved holders.")


def _is_prod_db(db_path: str) -> bool:
    """Reject ever pointing this CLI at the prod DB. Mirrors
    ``tools.backfill_cc0_remap._is_prod_db``: the prod path is the substrate
    default; requiring an explicit --db-path and rejecting that default keeps
    'never write to prod' mechanical."""
    from substrate.graph import default_db_path

    try:
        return os.path.abspath(db_path) == os.path.abspath(default_db_path())
    except Exception:
        return False


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python -m tools.backfill_ip_holders",
        description=(
            "Resolve documents.ip_holder_id for rows with a NULL holder using "
            "the same registry resolver the persist path runs (SPR-08 T1). "
            "Dry-run by default; LOCAL/TEMP DB only."
        ),
    )
    p.add_argument(
        "--db-path",
        required=True,
        help="LOCAL/TEMP DuckDB path (never prod; the prod default is rejected)",
    )
    p.add_argument(
        "--apply",
        action="store_true",
        help="write the resolved holders (default is a dry-run report)",
    )
    p.add_argument(
        "--workers",
        type=int,
        default=_ONLY_WORKER_COUNT,
        choices=[_ONLY_WORKER_COUNT],
        help=(
            "must be 1: the pass is one single-writer critical section; a "
            "parallel connection would violate the DuckDB single-writer invariant"
        ),
    )
    return p


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if _is_prod_db(args.db_path):
        print(
            "error: --db-path resolves to the prod substrate default; this CLI "
            "may only run against a LOCAL/TEMP DB (a prod backfill is "
            "operator-gated)",
            file=sys.stderr,
        )
        return 2

    report = run(args.db_path, apply=args.apply)
    _print_report(report, applied=args.apply)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
