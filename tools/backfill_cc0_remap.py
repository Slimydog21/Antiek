"""Re-classify mis-stamped CC0 / CC-BY / CC-BY-SA documents (2026-05-29 remap).

Until 2026-05-29 the license-resolution layer routed CC0 and source-declared
CC-BY / CC-BY-SA works into ``content_class='opt_in_licensed'``. That stamped a
FALSE provenance: ``opt_in_licensed`` means EXACTLY "a publisher claimed this
work via the §9.10 opt-in flow", which a CC0 arXiv paper or a CC-BY OpenAlex
work never did — the open license was declared AT THE SOURCE. This tool
re-derives the corrected class for the rows that lie:

  * CC0           -> ``public_domain``        (public-domain dedication)
  * CC-BY/CC-BY-SA -> ``source_declared_open`` (servable, attribution owed,
                                                NOT a §9.10 opt-in)

It reads the license BASIS (the human-readable provenance string stored on
``book_assets.license_basis``, joined to ``documents`` by ``document_id``) to
decide which rows are CC and which are genuine §9.10 publisher claims. A row
whose basis carries NO CC marker is left as ``opt_in_licensed`` — that is a
real publisher opt-in and must not be touched.

DESIGN INVARIANTS
-----------------
* **Read-the-basis, not the URI guess.** The decision keys off the stored
  ``license_basis`` provenance, the same string a reviewer would read to defend
  the original classification. No re-fetch, no re-resolve.
* **Idempotent.** A second ``--apply`` is a no-op: once a row is moved off
  ``opt_in_licensed`` it no longer matches the WHERE clause.
* **Dry-run by default.** Without ``--apply`` the tool prints per-bucket counts
  and writes nothing. ``--apply`` is required to mutate.
* **DuckDB single-writer.** The mutation runs inside a single
  ``runtime.db_lock.connect_write`` critical section — the same serialized host
  funnel every other substrate writer uses. No second concurrent writer.
* **Never prod.** A prod-DB guard mirrors ``tools.ingest_open_access._is_prod_db``:
  a real run requires an explicit ``--db-path`` that does NOT resolve to the
  substrate default. Real prod execution is OPERATOR-GATED and out of scope for
  this tool; it builds + tests against synthetic DBs only.

Usage:
    # dry-run report (writes nothing)
    python -m tools.backfill_cc0_remap --db-path /tmp/antiek.duckdb

    # apply the remap to a LOCAL/TEMP DB
    python -m tools.backfill_cc0_remap --db-path /tmp/antiek.duckdb --apply
"""

from __future__ import annotations

import argparse
import os
import sys
from dataclasses import dataclass
from typing import Optional, Sequence

_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

from runtime.db_lock import connect_write  # noqa: E402
from substrate.constants import (  # noqa: E402
    SERVABLE_CONTENT_CLASSES,
    SOURCE_DECLARED_OPEN_CONTENT_CLASS,
)
from substrate.graph.ops import update_document_gate_columns  # noqa: E402

# The corrected target classes. ``source_declared_open`` comes from the
# substrate constant so a rename is a single edit; "public_domain" and
# "opt_in_licensed" are stable vocabulary literals (no constant exists for them
# as bare names — they live inside SERVABLE_CONTENT_CLASSES, asserted below).
_PUBLIC_DOMAIN = "public_domain"
_SOURCE_DECLARED_OPEN = SOURCE_DECLARED_OPEN_CONTENT_CLASS
_MISCLASSIFIED = "opt_in_licensed"

# Defensive coupling: the two corrected targets MUST be servable classes (a
# remap that moved a row to a gated class would silently un-serve content).
assert _PUBLIC_DOMAIN in SERVABLE_CONTENT_CLASSES
assert _SOURCE_DECLARED_OPEN in SERVABLE_CONTENT_CLASSES
assert _MISCLASSIFIED in SERVABLE_CONTENT_CLASSES

# Substring markers (case-insensitive) found in a license_basis provenance
# string. These mirror the license_name values the resolver stamps
# (acquisition.licenses_core / acquisition.openaccess.licenses):
#   "CC0 1.0 (public-domain dedication)" and the publicdomain/zero URI;
#   "CC BY" / "CC BY-SA" and the creativecommons.org/licenses/by(-sa) URIs /
#   short codes.
# A genuine §9.10 publisher claim carries NONE of these.
#
# The URI markers are DOMAIN-QUALIFIED (``creativecommons.org/licenses/by``,
# not the bare ``licenses/by``) on purpose: a publisher's own provenance string
# is free to read "licensed by permission" or carry a path like
# ``acme.com/licenses/by-special-deal`` — a bare ``licenses/by`` substring would
# false-positive that genuine §9.10 claim into source_declared_open and falsely
# un-claim the publisher. We only key off the *Creative Commons* license URL
# (or the explicit "CC BY" / "CC0" name/short-code the resolver stamps), never a
# stray "licenses/by" that any other domain might use.
_CC0_MARKERS = ("creativecommons.org/publicdomain/zero", "cc0")
# CC-BY-SA markers are checked BEFORE bare CC-BY so a BY-SA basis is bucketed
# as BY-SA (it would also contain the "cc by" / "/licenses/by" substring
# otherwise).
_CC_BY_SA_MARKERS = ("creativecommons.org/licenses/by-sa", "cc by-sa", "cc-by-sa")
_CC_BY_MARKERS = ("creativecommons.org/licenses/by", "cc by", "cc-by")


@dataclass(frozen=True)
class RemapPlan:
    """The counts that a dry-run reports and an --apply effects."""

    to_public_domain: int       # CC0 rows -> public_domain
    to_source_declared_open: int  # CC-BY / CC-BY-SA rows -> source_declared_open
    left_opt_in: int            # genuine §9.10 publisher claims left untouched
    total_opt_in: int           # all opt_in_licensed docs examined

    @property
    def total_remapped(self) -> int:
        return self.to_public_domain + self.to_source_declared_open


def _classify_basis(basis: Optional[str]) -> Optional[str]:
    """Map a license_basis provenance string to the corrected content_class,
    or ``None`` if the basis carries no CC marker (a genuine §9.10 claim).

    CC0 is checked first (a publicdomain/zero basis never names "cc by"), then
    CC-BY-SA before bare CC-BY (a BY-SA string also contains the BY substring).
    """
    if not basis:
        return None
    b = basis.lower()
    if any(m in b for m in _CC0_MARKERS):
        return _PUBLIC_DOMAIN
    if any(m in b for m in _CC_BY_SA_MARKERS):
        return _SOURCE_DECLARED_OPEN
    if any(m in b for m in _CC_BY_MARKERS):
        return _SOURCE_DECLARED_OPEN
    return None


def _scan(con) -> tuple[RemapPlan, list[tuple[str, str]]]:
    """Examine every ``opt_in_licensed`` document, join its ``book_assets``
    license_basis, and bucket it. Returns the plan + the list of
    ``(document_id, target_class)`` rows that need rewriting.

    LEFT JOIN so a document with no book_assets row (no stored basis) is still
    examined — with a NULL basis it has no CC marker and is therefore treated
    as a genuine claim and left alone (deny-by-default on the *remap*: we never
    move a row we can't affirmatively prove is CC)."""
    rows = con.execute(
        """
        SELECT d.document_id, ba.license_basis
        FROM documents d
        LEFT JOIN book_assets ba ON ba.document_id = d.document_id
        WHERE d.content_class = ?
        """,
        [_MISCLASSIFIED],
    ).fetchall()

    to_pd = 0
    to_sdo = 0
    left = 0
    updates: list[tuple[str, str]] = []
    for document_id, basis in rows:
        target = _classify_basis(basis)
        if target == _PUBLIC_DOMAIN:
            to_pd += 1
            updates.append((document_id, _PUBLIC_DOMAIN))
        elif target == _SOURCE_DECLARED_OPEN:
            to_sdo += 1
            updates.append((document_id, _SOURCE_DECLARED_OPEN))
        else:
            left += 1
    plan = RemapPlan(
        to_public_domain=to_pd,
        to_source_declared_open=to_sdo,
        left_opt_in=left,
        total_opt_in=len(rows),
    )
    return plan, updates


def _apply(con, updates: Sequence[tuple[str, str]]) -> None:
    """Rewrite content_class for the planned rows inside the held write lock.

    Routes every mutation through ``substrate.graph.ops.update_document_gate_columns``
    — the ONLY sanctioned way to change ``documents.content_class`` on a row
    that is the target of a foreign key (book_assets / chunks reference it). A
    raw ``UPDATE documents SET content_class=…`` trips DuckDB's
    "key still referenced by a foreign key" rejection on a secondary-indexed
    column; the helper does the index drop/recreate dance atomically under the
    same write lock."""
    for document_id, target in updates:
        update_document_gate_columns(
            con,
            document_id,
            content_class=target,
            set_content_class=True,
        )


def _print_report(plan: RemapPlan, *, applied: bool) -> None:
    verb = "APPLIED" if applied else "DRY RUN (nothing written)"
    print(f"CC0/CC-BY/CC-BY-SA remap — {verb}\n")
    print(f"  opt_in_licensed documents examined : {plan.total_opt_in}")
    print(f"  -> public_domain        (CC0)      : {plan.to_public_domain}")
    print(f"  -> source_declared_open (CC-BY/SA) : {plan.to_source_declared_open}")
    print(f"  left as opt_in_licensed (genuine §9.10): {plan.left_opt_in}")
    print(f"  total remapped                     : {plan.total_remapped}")
    if not applied and plan.total_remapped:
        print("\n  re-run with --apply to effect the remap.")


def _is_prod_db(db_path: str) -> bool:
    """Reject ever pointing this CLI at the prod DB. Mirrors
    tools.ingest_open_access._is_prod_db: the prod path is the substrate
    default; requiring an explicit --db-path and rejecting that default keeps
    'never write to prod' mechanical."""
    from substrate.graph import default_db_path

    try:
        return os.path.abspath(db_path) == os.path.abspath(default_db_path())
    except Exception:
        return False


def run(db_path: str, *, apply: bool) -> RemapPlan:
    """Scan (and optionally apply) the remap. Public entry for tests.

    The scan + (optional) apply share ONE write-lock critical section so the
    count a dry-run-equivalent sees and the rows it rewrites cannot diverge
    under a concurrent writer. (We acquire the write lock even for the scan
    when applying; a pure dry-run could read-only, but acquiring the same lock
    keeps the path identical and respects the single-writer funnel.)"""
    if apply:
        with connect_write(db_path, purpose="backfill_cc0_remap") as con:
            plan, updates = _scan(con)
            _apply(con, updates)
        return plan
    # Dry run: still funnel through the write coordinator so there is exactly
    # one DB-access shape, but write nothing.
    with connect_write(db_path, purpose="backfill_cc0_remap_dryrun") as con:
        plan, _ = _scan(con)
    return plan


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python -m tools.backfill_cc0_remap",
        description=(
            "Re-classify CC0 -> public_domain and CC-BY/CC-BY-SA -> "
            "source_declared_open for documents mis-stamped opt_in_licensed "
            "(2026-05-29 remap). Dry-run by default; LOCAL/TEMP DB only."
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
        help="effect the remap (default is a dry-run report that writes nothing)",
    )
    return p


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)

    if _is_prod_db(args.db_path):
        print(
            "error: --db-path resolves to the prod substrate default; this CLI "
            "may only run against a LOCAL/TEMP DB (prod remap is operator-gated)",
            file=sys.stderr,
        )
        return 2

    plan = run(args.db_path, apply=args.apply)
    _print_report(plan, applied=args.apply)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
