"""Re-sanitize ``document_reader_html`` rows whose sanitizer stamp is stale.

The reader-HTML sidecar is served AS HTML only when its ``sanitizer_version``
equals ``SANITIZER_VERSION`` exactly (``substrate/reader_html/store.py``,
ring 2). Every sanitizer bump therefore turns every row stamped under the
previous version into ``sanitizer_version_stale``: readable as text, never
rendered, and — since ``GET /documents/{id}/render`` refuses a stale row with
422 — unreachable by the style wheel. ``html_sanitizer.py``'s docstring
promises that an operator re-sanitizes and re-stamps such rows; this is the
tool that does it. Until now the only candidate,
``tools/backfill_book_reader_html.py``, keyed on sidecar ABSENCE
(``r.document_id IS NULL``), so a row sanitized under a buggy version already
had a sidecar and was skipped forever.

WHAT "THE ORIGINAL BODY" IS. The pre-sanitization bytes are not retained
anywhere: ``html_body`` is the sanitizer's OUTPUT, and re-running a body the
1.2.0 ``<embed>`` bug truncated would only restamp the truncation as current.
The closest original the substrate keeps is ``documents.raw_text``, projected
exactly the way the backfill projects it (``raw_text_to_main_html``: an
HTML-shaped or provenanced body passes through, everything else goes through
escape-first markdown). A stale row whose document has no ``raw_text`` is
reported, never rewritten from its own sanitized output. A row an operator has
edited (``edited_at`` set) is reported too and left alone: the edit is not
derivable from ``raw_text`` and ``store_reader_html`` would discard it.

The ``documents.metadata`` stamp (``content_sanitizer_version``, the trust bit
the books serve path reads) is a DIFFERENT contract on a different column and
is inventoried here for completeness only — this tool never writes
``documents``.

DESIGN INVARIANTS (mirroring backfill_book_reader_html.py)
------------------------------------------------------------
* **Dry-run by default.** ``--report`` is the explicit read-only inventory;
  ``--apply`` is required to write.
* **Keyed on the version stamp**, not on sidecar absence.
* **Idempotent.** A re-stamped row is no longer stale; a second ``--apply``
  finds nothing left for it.
* **Single writer.** Mutations go through ``runtime.db_lock.connect_write`` on
  the serialized host funnel (uvicorn runs ``--workers 1``); this tool never
  opens a second writer, and the scan runs on a read-only connection.
* **Rights-neutral.** ``documents.content_class`` / rights are never touched.
* **Sanitize-on-write.** The only write path is ``store_reader_html``.

Usage:
    python tools/resanitize_reader_html.py --report
    python tools/resanitize_reader_html.py --apply --limit 5
    python tools/resanitize_reader_html.py --db-path /tmp/scratch.duckdb --apply
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

from runtime.db_lock import connect_read, connect_write  # noqa: E402
from substrate.books.html_sanitizer import (  # noqa: E402
    SANITIZER_VERSION,
    SANITIZER_VERSION_KEY,
)
from substrate.graph import default_db_path  # noqa: E402
from substrate.reader_html.store import store_reader_html  # noqa: E402
from tools.backfill_book_reader_html import raw_text_to_main_html  # noqa: E402

SKIP_EMPTY_RAW_TEXT = "empty_raw_text"
SKIP_EDITED = "edited"


@dataclass(frozen=True)
class StaleRow:
    document_id: str
    stamped_version: str
    source_kind: str
    source_url: str | None
    title: str | None
    content_class: str | None
    raw_len: int
    skip_reason: str | None = None


@dataclass(frozen=True)
class ResanitizePlan:
    sidecar_rows: int
    current: int
    stale: int
    repairable: int
    skipped_empty: int
    skipped_edited: int
    by_content_class: dict[str, int]
    by_stamped_version: dict[str, int]
    # documents.metadata rows carrying a content_sanitizer_version other than
    # the current one. A different contract (the books serve trust bit); this
    # tool reports it and never repairs it.
    metadata_stamp_stale: int


def _metadata_dict(metadata: Any) -> dict[str, Any]:
    if isinstance(metadata, dict):
        return metadata
    if isinstance(metadata, str) and metadata.strip():
        try:
            loaded = json.loads(metadata)
        except json.JSONDecodeError:
            return {}
        return loaded if isinstance(loaded, dict) else {}
    return {}


def _scan(con) -> tuple[ResanitizePlan, list[StaleRow]]:
    totals = con.execute(
        """
        SELECT
          COUNT(*) AS rows,
          SUM(CASE WHEN sanitizer_version = ? THEN 1 ELSE 0 END) AS current
        FROM document_reader_html
        """,
        [SANITIZER_VERSION],
    ).fetchone()
    sidecar_rows, current = int(totals[0] or 0), int(totals[1] or 0)

    rows = con.execute(
        """
        SELECT
          r.document_id,
          r.sanitizer_version,
          r.source_kind,
          r.source_url,
          r.edited_at,
          d.title,
          d.content_class,
          d.source_uri,
          d.raw_text,
          length(COALESCE(d.raw_text, '')) AS raw_len
        FROM document_reader_html r
        JOIN documents d ON d.document_id = r.document_id
        WHERE r.sanitizer_version <> ?
        ORDER BY r.document_id
        """,
        [SANITIZER_VERSION],
    ).fetchall()

    stale: list[StaleRow] = []
    by_class: dict[str, int] = {}
    by_version: dict[str, int] = {}
    repairable = skipped_empty = skipped_edited = 0
    for (
        document_id,
        version,
        source_kind,
        source_url,
        edited_at,
        title,
        content_class,
        source_uri,
        raw_text,
        raw_len,
    ) in rows:
        ckey = content_class or "(null)"
        by_class[ckey] = by_class.get(ckey, 0) + 1
        vkey = str(version)
        by_version[vkey] = by_version.get(vkey, 0) + 1
        if edited_at is not None:
            skip: str | None = SKIP_EDITED
            skipped_edited += 1
        elif not raw_text or not str(raw_text).strip():
            skip = SKIP_EMPTY_RAW_TEXT
            skipped_empty += 1
        else:
            skip = None
            repairable += 1
        stale.append(
            StaleRow(
                document_id=document_id,
                stamped_version=vkey,
                source_kind=source_kind,
                source_url=source_url or source_uri,
                title=title,
                content_class=content_class,
                raw_len=int(raw_len or 0),
                skip_reason=skip,
            )
        )

    # The metadata stamp is parsed in Python rather than with json_extract so
    # a malformed metadata blob on one row cannot fail the whole inventory.
    meta_rows = con.execute(
        "SELECT metadata FROM documents WHERE CAST(metadata AS VARCHAR) LIKE ?",
        [f"%{SANITIZER_VERSION_KEY}%"],
    ).fetchall()
    metadata_stale = 0
    for (metadata,) in meta_rows:
        stamped = _metadata_dict(metadata).get(SANITIZER_VERSION_KEY)
        if stamped is not None and stamped != SANITIZER_VERSION:
            metadata_stale += 1

    plan = ResanitizePlan(
        sidecar_rows=sidecar_rows,
        current=current,
        stale=len(stale),
        repairable=repairable,
        skipped_empty=skipped_empty,
        skipped_edited=skipped_edited,
        by_content_class=dict(sorted(by_class.items())),
        by_stamped_version=dict(sorted(by_version.items())),
        metadata_stamp_stale=metadata_stale,
    )
    return plan, stale


def _apply(con, stale: Sequence[StaleRow], *, limit: int | None) -> int:
    """Re-stamp up to ``limit`` repairable rows. Reloads each row inside the
    write lock and re-checks it is still stale, so a concurrent re-stamp or
    an operator edit that landed since the scan is left alone."""
    written = 0
    for row in stale:
        if row.skip_reason:
            continue
        if limit is not None and written >= limit:
            break
        fresh = con.execute(
            """
            SELECT r.sanitizer_version, r.edited_at, r.source_kind, r.source_url,
                   d.raw_text, d.metadata, d.source_uri
            FROM document_reader_html r
            JOIN documents d ON d.document_id = r.document_id
            WHERE r.document_id = ?
            """,
            [row.document_id],
        ).fetchone()
        if fresh is None:
            continue
        version, edited_at, source_kind, source_url, raw_text, metadata, source_uri = fresh
        if version == SANITIZER_VERSION or edited_at is not None:
            continue
        if not raw_text or not str(raw_text).strip():
            continue
        main_html, _kind = raw_text_to_main_html(str(raw_text), metadata)
        # The row's own source_kind is its provenance ('url' / 'pdf' / 'book'
        # ...); the backfill's inferred kind is only for rows that never had one.
        store_reader_html(
            con,
            document_id=row.document_id,
            main_html=main_html,
            source_kind=source_kind,
            source_url=source_url or source_uri,
        )
        written += 1
    return written


def _print_report(
    plan: ResanitizePlan,
    stale: Sequence[StaleRow],
    *,
    applied: bool,
    written: int | None = None,
    limit: int | None = None,
) -> None:
    verb = "APPLIED" if applied else "REPORT (nothing written)"
    print(f"document_reader_html re-sanitize — {verb}\n")
    print(f"  current sanitizer        : {SANITIZER_VERSION}")
    print(f"  sidecar rows             : {plan.sidecar_rows}")
    print(f"  stamped current          : {plan.current}")
    print(f"  stale                    : {plan.stale}")
    print(f"  repairable (raw_text)    : {plan.repairable}")
    print(f"  skipped (empty raw_text) : {plan.skipped_empty}")
    print(f"  skipped (operator edit)  : {plan.skipped_edited}")
    print("  stale by content_class:")
    if plan.by_content_class:
        for cclass, n in plan.by_content_class.items():
            print(f"    - {cclass}: {n}")
    else:
        print("    (none)")
    if plan.by_stamped_version:
        print("  stale by stamped version:")
        for version, n in plan.by_stamped_version.items():
            print(f"    - {version}: {n}")
    print(
        f"  documents.metadata stamp stale: {plan.metadata_stamp_stale} "
        "(different contract; not repaired by this tool)"
    )
    if applied and written is not None:
        print(f"  re-stamped               : {written}")
        print(f"  stale remaining          : {plan.stale - written}")
    elif not applied and plan.repairable:
        cap = f" --limit {limit}" if limit is not None else ""
        print(f"\n  re-run with --apply{cap} to re-sanitize from raw_text (rights unchanged).")
    if stale and not applied:
        print("\n  stale sample (up to 12):")
        for row in list(stale)[:12]:
            title = (row.title or "").replace("\n", " ")[:48]
            skip = f" skip={row.skip_reason}" if row.skip_reason else ""
            print(
                f"    - {row.document_id} class={row.content_class} "
                f"stamped={row.stamped_version} kind={row.source_kind} "
                f"raw_len={row.raw_len}{skip} {title!r}"
            )


def run(
    db_path: str, *, apply: bool = False, limit: int | None = None
) -> tuple[ResanitizePlan, int | None]:
    """Scan (and optionally re-stamp) stale sidecar rows.

    Returns the pre-apply plan and the number of rows re-stamped (``None`` on
    a report run). The scan is read-only; only ``apply`` opens the single
    writer, and only for the rows the scan found.
    """
    con = connect_read(db_path)
    try:
        plan, stale = _scan(con)
    finally:
        con.close()
    written = None
    if apply:
        with connect_write(db_path, purpose="tools/resanitize_reader_html") as wcon:
            written = _apply(wcon, stale, limit=limit)
    _print_report(plan, stale, applied=apply, written=written, limit=limit)
    return plan, written


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Inventory document_reader_html rows whose sanitizer stamp is not the "
            "current SANITIZER_VERSION and, with --apply, re-sanitize them from "
            "documents.raw_text through store_reader_html (report-only by default; "
            "never changes content_class)."
        )
    )
    parser.add_argument(
        "--db-path",
        default=None,
        help="DuckDB path (default: the configured graph, ANTIEK_DUCKDB_PATH or ~/.antiek)",
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--report",
        action="store_true",
        help="Print the stale inventory and exit without writing (the default)",
    )
    mode.add_argument(
        "--apply",
        action="store_true",
        help="Re-sanitize stale rows from raw_text via store_reader_html",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Re-stamp at most this many rows per --apply run",
    )
    args = parser.parse_args(list(argv) if argv is not None else None)
    if args.limit is not None and args.limit < 0:
        parser.error("--limit must be a non-negative integer")
    db_path = os.path.expanduser(args.db_path or default_db_path())
    if not os.path.exists(db_path):
        print(f"error: db not found: {db_path}", file=sys.stderr)
        return 2
    run(db_path, apply=bool(args.apply), limit=args.limit)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
