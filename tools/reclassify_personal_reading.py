"""Backward-remediation sweep: move already-ingested third-party documents off a
servable class onto ``personal_reading`` (Personal-Reading Lane SPR-03).

WHAT THIS DOES
--------------
Before the Personal-Reading Lane existed, the web family of connectors
(``acquisition/urls`` -> ``web_article``, ``acquisition/youtube`` ->
``video_transcript``, ``acquisition/twitter`` -> ``social_thread``, and the
reserved Substack ``newsletter_post``) inserted documents with NO explicit
``content_class``. A NULL content_class resolved as servable on the public
chunk-search / ad-attribution path, and a row hand-stamped ``user_owned``
(the schema's servable default for genuine operator content) inherited a
servable class it has no rights basis for — third-party copyrighted text the
public/collective graph and the per-second ad border would treat as fair game.
SPR-02 fixed the FORWARD path (connectors now stamp ``personal_reading`` at
ingest). This tool fixes the BACKWARD path: the rows already in the corpus.

It selects every document where::

    document_type IN (THIRD_PARTY_DOCUMENT_TYPES)
      AND content_class IN (SERVABLE_CONTENT_CLASSES)   -- the offending set

and moves each to ``personal_reading`` (the owner-readable / public-non-servable
lane: NOT in SERVABLE_CONTENT_CLASSES, a member of NON_ATTRIBUTABLE_CONTENT_CLASSES,
absent from PUBLIC_GRAPH_CONTENT_CLASSES, never trained, never ad-attributed).

WHY ``document_type`` IS THE DISCRIMINATOR (not ``content_class`` alone)
-----------------------------------------------------------------------
``user_owned`` is ALSO the schema default for GENUINE operator content (the
Write workflow, a real ``book`` / ``voice_note`` / ``academic_paper`` upload,
a notebook row). Sweeping on ``content_class = 'user_owned'`` alone would
mislabel real operator ownership as non-servable. ``document_type`` is the
discriminator that distinguishes third-party leakage (one of the four
THIRD_PARTY_DOCUMENT_TYPES) from real ownership. A genuine ``user_owned``
upload is STRUCTURALLY excluded because its ``document_type`` is not in the
THIRD_PARTY set — never by its class.

REVERSIBILITY (durable contract — read this to reverse the migration)
---------------------------------------------------------------------
Before mutating a row, the prior ``content_class`` is written into that row's
existing ``metadata`` JSON under key ``reclassify_prior_content_class``, with a
``reclassify_swept_at`` ISO-8601-``Z`` timestamp. No new table, no schema
migration — reversibility is row-local. ``--rollback`` restores each row's
``content_class`` from ``metadata.reclassify_prior_content_class`` and deletes
the ``reclassify_*`` keys. The prior-class key is written ONLY if absent, so a
partial-crash re-run never re-stamps (which would corrupt the reversibility
record). The rollback CANNOT un-emit the sweep event; it appends a rollback
event instead.

  metadata key  ``reclassify_prior_content_class``  -> the class before the sweep
  metadata key  ``reclassify_swept_at``             -> ISO-8601-Z stamp of the sweep
  event action  ``corpus.reclassify_personal_reading`` (untyped log_event; the
                only audit trail of "when and how many" if an operator applies
                this to a real DB — payload fields are load-bearing, see _emit)

IDEMPOTENCY
-----------
A second ``--apply`` selects zero rows: a swept row's ``content_class =
personal_reading`` is not in SERVABLE_CONTENT_CLASSES, so it no longer matches
the offending WHERE clause; ``reclassify_swept_at`` is therefore stable across
re-runs (no re-stamp).

SAFETY
------
* **Dry-run by default.** Without ``--apply`` (or ``--rollback``) the tool
  prints the SweepPlan and writes nothing — the read goes through
  ``runtime.db_lock.connect_read`` (no write connection is even opened).
* **DuckDB single-writer.** Every mutation rides ONE
  ``runtime.db_lock.connect_write`` critical section — the serialized host
  funnel every other substrate writer uses. No second concurrent writer.
* **All content_class writes go through ``update_document_gate_columns``** —
  never a raw ``UPDATE documents SET content_class=…`` (that path fails on
  DuckDB 1.5.2 because content_class is secondary-indexed and the row is a
  foreign-key target; the helper does the index drop/recreate dance atomically).
* **Never prod.** A prod-DB guard mirrors ``tools.backfill_cc0_remap._is_prod_db``:
  a real run requires an explicit ``--db-path`` that does NOT resolve to the
  substrate default. Real prod execution is OPERATOR-GATED and out of scope; this
  tool builds + tests against synthetic in-memory / temp DBs only.

USAGE
-----
    # dry-run report (writes nothing) — the count is your contract
    python -m tools.reclassify_personal_reading --db-path /tmp/antiek.duckdb

    # effect the sweep on a LOCAL/TEMP DB
    python -m tools.reclassify_personal_reading --db-path /tmp/antiek.duckdb --apply

    # reverse it: restore each swept row's prior content_class + drop reclassify_* keys
    python -m tools.reclassify_personal_reading --db-path /tmp/antiek.duckdb --rollback
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional, Sequence

_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

from runtime.db_lock import connect_read, connect_write  # noqa: E402
from substrate.constants import (  # noqa: E402
    PERSONAL_READING_CONTENT_CLASS,
    SERVABLE_CONTENT_CLASSES,
    THIRD_PARTY_DOCUMENT_TYPES,
)
from substrate.event_log.events import log_event  # noqa: E402
from substrate.graph.ops import update_document_gate_columns  # noqa: E402

# The metadata JSON keys that carry the reversibility record. These names are a
# DURABLE CONTRACT — a future maintainer reads them to reverse the migration
# without this file; do not rename without a rollback migration.
PRIOR_CLASS_KEY = "reclassify_prior_content_class"
SWEPT_AT_KEY = "reclassify_swept_at"
_RECLASSIFY_KEYS = (PRIOR_CLASS_KEY, SWEPT_AT_KEY)

# The untyped action_type for the sweep / rollback events. Untyped (raw string
# through log_event, the cascade.launched / un-schemaed-vocabulary convention) —
# no payload schema / codegen bump for a one-shot migration's audit trail.
SWEEP_ACTION_TYPE = "corpus.reclassify_personal_reading"

# The personal_reading target MUST NOT be servable (a sweep that moved a row to a
# servable class would not cure the leak). Asserted at import so a future taxonomy
# edit that put personal_reading back in the servable set fails loudly here too.
assert PERSONAL_READING_CONTENT_CLASS not in SERVABLE_CONTENT_CLASSES, (
    "personal_reading must NOT be servable — the sweep target would not cure the "
    "leak otherwise."
)


@dataclass(frozen=True)
class SweepPlan:
    """What a dry-run reports and an --apply effects. ``total_offending`` is the
    contract: if --apply sweeps a different number on the same DB, a row changed
    class between read and write, or two WHERE clauses diverged — surface it,
    don't paper over it (rigor #1)."""

    total_offending: int
    by_document_type: tuple[tuple[str, int], ...]
    by_source_domain: tuple[tuple[str, int], ...]


def _now_iso_z() -> str:
    """ISO-8601 UTC with a trailing ``Z`` (matches the event-log emitted_at
    convention)."""
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _source_domain(source_uri: Optional[str]) -> str:
    """Best-effort domain extraction from a source_uri for the dry-run breakdown.
    Falls back to ``(none)`` / ``(unparsed)`` rather than raising — the breakdown
    is a report aid, never a gate."""
    if not source_uri:
        return "(none)"
    try:
        from urllib.parse import urlparse

        netloc = urlparse(source_uri).netloc
        return netloc or "(unparsed)"
    except Exception:
        return "(unparsed)"


# The offending-set predicate. document_type AND content_class are BOTH bound
# (never f-string-interpolated values) so a taxonomy literal can't sneak in, and
# the report and the mutation read the SAME clause — one source of truth, two
# filters can't diverge (M4 acceptance criterion).
def _offending_where_and_params() -> tuple[str, list[str]]:
    dt_ph = ", ".join("?" for _ in THIRD_PARTY_DOCUMENT_TYPES)
    cc_ph = ", ".join("?" for _ in SERVABLE_CONTENT_CLASSES)
    where = (
        f"document_type IN ({dt_ph}) AND content_class IN ({cc_ph})"
    )
    # Sort the frozensets to a stable param order (frozenset iteration order is
    # not guaranteed stable across processes; bound params don't care, but a
    # stable order keeps logs/debugging reproducible).
    params = sorted(THIRD_PARTY_DOCUMENT_TYPES) + sorted(SERVABLE_CONTENT_CLASSES)
    return where, params


def _scan(con) -> tuple[SweepPlan, list[tuple[str, str, Optional[str]]]]:
    """Read the offending set. Returns the SweepPlan + the list of
    ``(document_id, prior_content_class, metadata_json)`` rows to sweep.

    Read-only: takes whatever connection it is handed (a read conn for the
    dry-run, the held write conn for an --apply scan-then-mutate)."""
    where, params = _offending_where_and_params()
    rows = con.execute(
        f"""
        SELECT document_id, document_type, content_class, source_uri, metadata
          FROM documents
         WHERE {where}
         ORDER BY document_id
        """,
        params,
    ).fetchall()

    by_type: dict[str, int] = {}
    by_domain: dict[str, int] = {}
    sweep: list[tuple[str, str, Optional[str]]] = []
    for document_id, document_type, content_class, source_uri, metadata in rows:
        by_type[document_type] = by_type.get(document_type, 0) + 1
        dom = _source_domain(source_uri)
        by_domain[dom] = by_domain.get(dom, 0) + 1
        sweep.append((document_id, content_class, metadata))

    plan = SweepPlan(
        total_offending=len(rows),
        by_document_type=tuple(sorted(by_type.items())),
        by_source_domain=tuple(sorted(by_domain.items())),
    )
    return plan, sweep


def _load_metadata(metadata_json: Optional[str]) -> dict:
    """Parse a row's metadata TEXT JSON into a dict (``{}`` for NULL / unparsable
    — a non-dict metadata blob is treated as absent rather than crashing the
    sweep)."""
    if not metadata_json:
        return {}
    try:
        obj = json.loads(metadata_json)
        return obj if isinstance(obj, dict) else {}
    except (ValueError, TypeError):
        return {}


def _write_metadata(con, document_id: str, meta: dict) -> None:
    """Persist a row's metadata dict. metadata is NOT a gate column (not
    secondary-indexed, not the FK-rejection path), so a plain UPDATE is correct
    here — only content_class must route through update_document_gate_columns."""
    con.execute(
        "UPDATE documents SET metadata = ? WHERE document_id = ?",
        [json.dumps(meta, default=str), document_id],
    )


def _apply(con, sweep: Sequence[tuple[str, str, Optional[str]]]) -> int:
    """Sweep the offending rows on the held write connection. For each row:

      1. stamp the prior class into metadata under PRIOR_CLASS_KEY (ONLY if
         absent — never re-stamp a partial-rerun row), plus SWEPT_AT_KEY;
      2. move content_class to personal_reading via update_document_gate_columns.

    Both the metadata write and the gate-column update ride the SAME write
    connection. Returns the number of rows swept."""
    swept = 0
    for document_id, prior_class, metadata_json in sweep:
        meta = _load_metadata(metadata_json)
        # Key-absence guard: a partial crash could leave a row already on
        # personal_reading (off the offending set — it wouldn't be scanned) or a
        # row stamped but not yet moved. Within the offending set a row should
        # NOT already carry the key; if it does, leave the original stamp intact
        # so the reversibility record is never corrupted.
        if PRIOR_CLASS_KEY not in meta:
            meta[PRIOR_CLASS_KEY] = prior_class
            meta[SWEPT_AT_KEY] = _now_iso_z()
            _write_metadata(con, document_id, meta)
        update_document_gate_columns(
            con,
            document_id,
            content_class=PERSONAL_READING_CONTENT_CLASS,
            set_content_class=True,
        )
        swept += 1
    return swept


def _scan_rollback(con) -> list[tuple[str, str, Optional[str]]]:
    """Find every row carrying a PRIOR_CLASS_KEY stamp — the rows a prior sweep
    moved. Returns ``(document_id, prior_class, metadata_json)``. JSON-extracts
    in SQL via the ``->>`` operator so we only touch stamped rows."""
    rows = con.execute(
        f"""
        SELECT document_id,
               json_extract_string(metadata, '$.{PRIOR_CLASS_KEY}') AS prior_class,
               metadata
          FROM documents
         WHERE metadata IS NOT NULL
           AND json_extract_string(metadata, '$.{PRIOR_CLASS_KEY}') IS NOT NULL
         ORDER BY document_id
        """
    ).fetchall()
    return [(r[0], r[1], r[2]) for r in rows]


def _rollback(con, rows: Sequence[tuple[str, str, Optional[str]]]) -> int:
    """Restore each stamped row's content_class from
    metadata.reclassify_prior_content_class, then delete the reclassify_* keys.
    Returns the number of rows rolled back."""
    rolled = 0
    for document_id, prior_class, metadata_json in rows:
        if prior_class is None:
            continue
        update_document_gate_columns(
            con,
            document_id,
            content_class=prior_class,
            set_content_class=True,
        )
        meta = _load_metadata(metadata_json)
        for k in _RECLASSIFY_KEYS:
            meta.pop(k, None)
        _write_metadata(con, document_id, meta)
        rolled += 1
    return rolled


def _emit(plan_or_count, *, operation: str, by_document_type) -> None:
    """Append the audit-trail event for a sweep / rollback. Untyped log_event —
    the only record of "when and how many" if an operator applies this to a real
    DB. Payload fields are load-bearing:
        operation        : 'apply' | 'rollback'
        rows             : count swept / rolled back
        by_document_type : per-type breakdown (apply only; [] on rollback)
    investigation_id is a stable corpus-scoped id so the event is discoverable
    (the envelope requires a non-null investigation_id). NEVER carries raw_text."""
    log_event(
        "corpus-reclassify-personal-reading",
        SWEEP_ACTION_TYPE,
        payload={
            "operation": operation,
            "rows": plan_or_count,
            "by_document_type": [list(t) for t in by_document_type],
        },
        role="migration",
    )


def _print_report(plan: SweepPlan, *, applied: bool) -> None:
    verb = "APPLIED" if applied else "DRY RUN (nothing written)"
    print(f"reclassify third-party -> personal_reading — {verb}\n")
    print(f"  total offending (third-party on a servable class): {plan.total_offending}")
    print("  by document_type:")
    for dt, n in plan.by_document_type:
        print(f"    {dt}: {n}")
    if not plan.by_document_type:
        print("    (none)")
    print("  by source domain:")
    for dom, n in plan.by_source_domain:
        print(f"    {dom}: {n}")
    if not plan.by_source_domain:
        print("    (none)")
    if not applied and plan.total_offending:
        print("\n  re-run with --apply to effect the sweep.")


def _is_prod_db(db_path: str) -> bool:
    """Reject ever pointing this CLI at the prod DB. Mirrors
    tools.backfill_cc0_remap._is_prod_db / tools.ingest_open_access._is_prod_db:
    the prod path is the substrate default; requiring an explicit --db-path and
    rejecting that default keeps 'never write to prod' mechanical."""
    from substrate.graph import default_db_path

    try:
        return os.path.abspath(db_path) == os.path.abspath(default_db_path())
    except Exception:
        return False


def run(db_path: str, *, apply: bool = False, rollback: bool = False) -> SweepPlan:
    """Scan (and optionally apply / rollback) the sweep. Public entry for tests.

    apply and rollback are mutually exclusive; pass at most one. Default (both
    False) is a pure dry-run that opens a READ-ONLY connection and writes
    nothing. Returns the SweepPlan describing the offending set as scanned.
    """
    if apply and rollback:
        raise ValueError("apply and rollback are mutually exclusive")

    if rollback:
        with connect_write(db_path, purpose="reclassify_personal_reading_rollback") as con:
            rows = _scan_rollback(con)
            rolled = _rollback(con, rows)
        _emit(rolled, operation="rollback", by_document_type=())
        # Report what the corpus looks like AFTER rollback (offending set is
        # whatever rolled back into a servable class — the inverse signal).
        with connect_read(db_path) as con:
            plan, _ = _scan(con)
        return plan

    if apply:
        with connect_write(db_path, purpose="reclassify_personal_reading") as con:
            plan, sweep = _scan(con)
            _apply(con, sweep)
        _emit(plan.total_offending, operation="apply",
              by_document_type=plan.by_document_type)
        return plan

    # Dry run: read-only, write nothing, no write lock acquired.
    with connect_read(db_path) as con:
        plan, _ = _scan(con)
    return plan


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python -m tools.reclassify_personal_reading",
        description=(
            "Move already-ingested third-party documents (web_article / "
            "video_transcript / social_thread / newsletter_post) off a servable "
            "class onto personal_reading. Dry-run by default; LOCAL/TEMP DB only."
        ),
    )
    p.add_argument(
        "--db-path",
        required=True,
        help="LOCAL/TEMP DuckDB path (never prod; the prod default is rejected)",
    )
    mode = p.add_mutually_exclusive_group()
    mode.add_argument(
        "--apply",
        action="store_true",
        help="effect the sweep (default is a dry-run report that writes nothing)",
    )
    mode.add_argument(
        "--rollback",
        action="store_true",
        help=(
            "reverse a prior sweep: restore each swept row's content_class from "
            "metadata.reclassify_prior_content_class and drop the reclassify_* keys"
        ),
    )
    return p


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)

    if _is_prod_db(args.db_path):
        print(
            "error: --db-path resolves to the prod substrate default; this CLI "
            "may only run against a LOCAL/TEMP DB (prod sweep is operator-gated)",
            file=sys.stderr,
        )
        return 2

    plan = run(args.db_path, apply=args.apply, rollback=args.rollback)
    if args.rollback:
        print("reclassify rollback — APPLIED (restored prior content_class)\n")
        print(
            "  offending rows now on a servable class "
            f"(post-rollback inverse signal): {plan.total_offending}"
        )
    else:
        _print_report(plan, applied=args.apply)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
