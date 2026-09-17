"""Backfill ``document_reader_html`` for library ``book_assets`` missing a sidecar.

BookReader (``GET /books/{id}/(owner-)full-text``) prefers the trusted reader-HTML
sidecar when rights release the body (PR #3101). Uploads write the sidecar at
ingest; older PDF / corpus books often have markdown ``documents.raw_text`` but
no sidecar, so the reader falls back to text.

This tool:

* Inventories active ``book_assets`` rows lacking ``document_reader_html``
* For rows with non-empty ``raw_text``, projects markdown→safe HTML (or passes
  through already-sanitized HTML bodies) and writes via ``store_reader_html``
* NEVER mutates ``documents.content_class`` / rights / dual structure
  (gated books may still get a sidecar for owner-html serve)

DESIGN INVARIANTS
-----------------
* **Dry-run by default.** ``--apply`` required to write.
* **Idempotent.** Only targets missing sidecars; a second ``--apply`` is a no-op.
* **Single writer.** Mutations use ``runtime.db_lock.connect_write``.
* **Rights-neutral.** No reclassification of gated content as public.
* **Sanitize-on-write.** The only write path is ``store_reader_html``.

Usage:
    python -m tools.backfill_book_reader_html --db-path ~/.antiek/research_graph.duckdb
    python -m tools.backfill_book_reader_html --db-path ~/.antiek/research_graph.duckdb --apply
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

from acquisition.snapshot.reader_html import markdown_to_safe_html  # noqa: E402
from runtime.db_lock import connect_read, connect_write  # noqa: E402
from substrate.books.html_sanitizer import (  # noqa: E402
    CONTENT_SANITIZED_KEY,
    SANITIZER_VERSION_KEY,
)
from substrate.reader_html.store import store_reader_html  # noqa: E402

SOURCE_KIND_BOOK = "book"
SOURCE_KIND_BOOK_IMPORT = "book_import"


@dataclass(frozen=True)
class GapRow:
    document_id: str
    title: str | None
    content_class: str | None
    source_uri: str | None
    raw_len: int
    source_kind: str
    skip_reason: str | None = None


@dataclass(frozen=True)
class BackfillPlan:
    book_assets_active: int
    with_sidecar: int
    missing_sidecar: int
    convertible: int
    skipped_empty: int
    by_content_class: dict[str, int]

    @property
    def html_native_pct(self) -> float:
        if self.book_assets_active <= 0:
            return 100.0
        return 100.0 * self.with_sidecar / self.book_assets_active


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


def _looks_like_html(raw_text: str) -> bool:
    head = raw_text.lstrip()[:64].lower()
    return head.startswith(
        (
            "<!doctype",
            "<html",
            "<section",
            "<article",
            "<p>",
            "<h1",
            "<h2",
            "<div",
            "<body",
        )
    )


def raw_text_to_main_html(raw_text: str, metadata: Any = None) -> tuple[str, str]:
    """Project ``documents.raw_text`` into ``main_html`` + suggested source_kind.

    Returns ``(main_html, source_kind)``. Already-trusted HTML bodies (book
    import provenance or HTML-shaped raw_text) are passed through for
    re-sanitize inside ``store_reader_html``; everything else goes through
    escape-first ``markdown_to_safe_html``.
    """
    meta = _metadata_dict(metadata)
    book_import = meta.get("book_import")
    provenanced = bool(meta.get(CONTENT_SANITIZED_KEY) or meta.get(SANITIZER_VERSION_KEY))
    if provenanced or isinstance(book_import, dict) or _looks_like_html(raw_text):
        kind = SOURCE_KIND_BOOK_IMPORT if isinstance(book_import, dict) else SOURCE_KIND_BOOK
        return raw_text, kind
    return markdown_to_safe_html(raw_text), SOURCE_KIND_BOOK


def _scan(con) -> tuple[BackfillPlan, list[GapRow]]:
    totals = con.execute(
        """
        SELECT
          COUNT(*) AS active,
          SUM(CASE WHEN r.document_id IS NOT NULL THEN 1 ELSE 0 END) AS with_sidecar,
          SUM(CASE WHEN r.document_id IS NULL THEN 1 ELSE 0 END) AS missing
        FROM book_assets ba
        LEFT JOIN document_reader_html r ON r.document_id = ba.document_id
        WHERE COALESCE(ba.taken_down, false) = false
        """
    ).fetchone()
    active, with_sidecar, missing = (int(totals[0] or 0), int(totals[1] or 0), int(totals[2] or 0))

    rows = con.execute(
        """
        SELECT
          ba.document_id,
          d.title,
          d.content_class,
          d.source_uri,
          d.raw_text,
          d.metadata,
          length(COALESCE(d.raw_text, )) AS raw_len
        FROM book_assets ba
        JOIN documents d ON d.document_id = ba.document_id
        LEFT JOIN document_reader_html r ON r.document_id = ba.document_id
        WHERE COALESCE(ba.taken_down, false) = false
          AND r.document_id IS NULL
        ORDER BY ba.document_id
        """
    ).fetchall()

    gaps: list[GapRow] = []
    by_class: dict[str, int] = {}
    convertible = 0
    skipped_empty = 0
    for document_id, title, content_class, source_uri, raw_text, metadata, raw_len in rows:
        ckey = content_class or "(null)"
        by_class[ckey] = by_class.get(ckey, 0) + 1
        if not raw_text or not str(raw_text).strip():
            skipped_empty += 1
            gaps.append(
                GapRow(
                    document_id=document_id,
                    title=title,
                    content_class=content_class,
                    source_uri=source_uri,
                    raw_len=int(raw_len or 0),
                    source_kind=SOURCE_KIND_BOOK,
                    skip_reason="empty_raw_text",
                )
            )
            continue
        _html, kind = raw_text_to_main_html(str(raw_text), metadata)
        convertible += 1
        gaps.append(
            GapRow(
                document_id=document_id,
                title=title,
                content_class=content_class,
                source_uri=source_uri,
                raw_len=int(raw_len or 0),
                source_kind=kind,
            )
        )

    plan = BackfillPlan(
        book_assets_active=active,
        with_sidecar=with_sidecar,
        missing_sidecar=missing,
        convertible=convertible,
        skipped_empty=skipped_empty,
        by_content_class=dict(sorted(by_class.items())),
    )
    return plan, gaps


def _apply(con, gaps: Sequence[GapRow]) -> int:
    """Write missing sidecars. Reloads raw_text inside the write lock."""
    written = 0
    for gap in gaps:
        if gap.skip_reason:
            continue
        row = con.execute(
            "SELECT raw_text, metadata, source_uri FROM documents WHERE document_id = ?",
            [gap.document_id],
        ).fetchone()
        if row is None:
            continue
        raw_text, metadata, source_uri = row
        if not raw_text or not str(raw_text).strip():
            continue
        # Skip if a concurrent writer already filled the sidecar.
        exists = con.execute(
            "SELECT 1 FROM document_reader_html WHERE document_id = ? LIMIT 1",
            [gap.document_id],
        ).fetchone()
        if exists is not None:
            continue
        main_html, kind = raw_text_to_main_html(str(raw_text), metadata)
        store_reader_html(
            con,
            document_id=gap.document_id,
            main_html=main_html,
            source_kind=kind,
            source_url=source_uri or gap.source_uri,
        )
        written += 1
    return written


def _grade(pct: float) -> int:
    """HTML-native coverage grade /100 (rounded library share with sidecar)."""
    return max(0, min(100, int(round(pct))))


def _print_report(
    plan: BackfillPlan,
    gaps: Sequence[GapRow],
    *,
    applied: bool,
    written: int | None = None,
) -> None:
    verb = "APPLIED" if applied else "DRY RUN (nothing written)"
    print(f"book_assets reader-HTML backfill — {verb}\n")
    print(f"  book_assets (active)     : {plan.book_assets_active}")
    print(f"  with document_reader_html: {plan.with_sidecar}")
    print(f"  missing sidecar          : {plan.missing_sidecar}")
    print(f"  convertible (raw_text)   : {plan.convertible}")
    print(f"  skipped (empty raw_text) : {plan.skipped_empty}")
    if plan.by_content_class:
        print("  missing by content_class:")
        for cclass, n in plan.by_content_class.items():
            print(f"    - {cclass}: {n}")
    before_pct = plan.html_native_pct
    print(
        f"  HTML-native before       : {_grade(before_pct)}/100 "
        f"({plan.with_sidecar}/{plan.book_assets_active})"
    )
    if applied and written is not None:
        after_with = plan.with_sidecar + written
        after_pct = (
            100.0 * after_with / plan.book_assets_active
            if plan.book_assets_active
            else 100.0
        )
        print(f"  sidecars written         : {written}")
        print(
            f"  HTML-native after        : {_grade(after_pct)}/100 "
            f"({after_with}/{plan.book_assets_active})"
        )
    elif not applied and plan.convertible:
        projected = plan.with_sidecar + plan.convertible
        proj_pct = (
            100.0 * projected / plan.book_assets_active
            if plan.book_assets_active
            else 100.0
        )
        print(
            f"  HTML-native if applied   : {_grade(proj_pct)}/100 "
            f"({projected}/{plan.book_assets_active})"
        )
        print("\n  re-run with --apply to write sidecars (rights unchanged).")
    if gaps and not applied:
        print("\n  gap sample (up to 12):")
        for gap in list(gaps)[:12]:
            title = (gap.title or "").replace("\n", " ")[:48]
            skip = f" skip={gap.skip_reason}" if gap.skip_reason else ""
            print(
                f"    - {gap.document_id} class={gap.content_class} "
                f"raw_len={gap.raw_len} kind={gap.source_kind}{skip} {title!r}"
            )


def run(db_path: str, *, apply: bool = False) -> BackfillPlan:
    """Scan (and optionally apply) the backfill. Returns the pre-apply plan."""
    with connect_read(db_path) as con:
        plan, gaps = _scan(con)
    written = None
    if apply:
        with connect_write(db_path, purpose="tools/backfill_book_reader_html") as con:
            written = _apply(con, gaps)
    _print_report(plan, gaps, applied=apply, written=written)
    return plan


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Backfill document_reader_html for book_assets missing a sidecar "
            "(dry-run by default; does not change content_class)."
        )
    )
    parser.add_argument(
        "--db-path",
        required=True,
        help="DuckDB path (e.g. ~/.antiek/research_graph.duckdb)",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Write missing sidecars via store_reader_html (default: dry-run)",
    )
    args = parser.parse_args(list(argv) if argv is not None else None)
    db_path = os.path.expanduser(args.db_path)
    if not os.path.exists(db_path):
        print(f"error: db not found: {db_path}", file=sys.stderr)
        return 2
    run(db_path, apply=bool(args.apply))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
