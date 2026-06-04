"""Reader SPR-02 (M5) — backfill ``documents.structured_blocks`` for pre-SPR-02 docs.

Walks the ``documents`` table, finds every row that has ``raw_text`` but no
``structured_blocks`` (i.e. a document ingested BEFORE this sprint, stored as the
flat cleaned-text body), and UPGRADES it to the SPR-01 typed-block model by
running the M1 markdown/text extractor (``processing.extraction.to_document_model
.text_to_document``) over its STORED text — WITHOUT re-fetching the source.

Idempotent by construction (the M5 gate):

* A row that already has ``structured_blocks`` is SKIPPED — the WHERE clause
  filters it out, so a second run promotes zero rows and is a no-op.
* The model is derived deterministically from the stored ``raw_text`` (no model
  call, no provider key, no network), so the same row produces the same model on
  every run.

No data loss (the M5 gate): the upgrade only WRITES ``structured_blocks``; it
NEVER touches ``raw_text`` (the "view original" source is preserved) and NEVER
re-stamps ``content_class`` / ``ip_holder_id`` (the rights state set at ingest is
left exactly as-is — a backfill upgrades the BODY representation, never the
rights). It does not re-fetch, so it cannot lose or change the source.

Operational shape (mirrors ``backfill_insight_question.py``):

* ``--dry-run`` reports counts (rows scanned, candidates, already-upgraded,
  would-upgrade) WITHOUT opening a write connection.
* a real run holds ONE write lock for the whole backfill so a large corpus does
  not thrash the single-writer lock (acquired once, not once-per-row).
* the run is LOGGED via a report (JSON to stdout) — the count of upgraded rows
  and any per-row extraction failures (a row whose stored text the parser could
  not handle is recorded and SKIPPED, never written half-formed).

Back up ``~/.antiek/research_graph.duckdb`` before a real run.
"""

from __future__ import annotations

import json
import logging
import os
import sys
from dataclasses import asdict, dataclass, field

try:
    from ...runtime.db_lock import connect_read, connect_write
    from ..contracts.document_model import DocumentAttribution
    from .ops import set_structured_blocks
except ImportError:  # pragma: no cover — direct-script fallback
    _here = os.path.dirname(os.path.abspath(__file__))
    sys.path.insert(0, os.path.dirname(os.path.dirname(_here)))
    from runtime.db_lock import (  # type: ignore[no-redef]
        connect_read,
        connect_write,
    )
    from substrate.contracts.document_model import (  # type: ignore[no-redef]
        DocumentAttribution,
    )
    from substrate.graph.ops import set_structured_blocks  # type: ignore[no-redef]

logger = logging.getLogger(__name__)


@dataclass
class BackfillReport:
    """What a backfill run did — logged to stdout as JSON (the M5 "logged"
    requirement). ``failures`` records (document_id, error) for rows the parser
    could not handle; those are SKIPPED (never written half-formed), so the run
    is safe to re-run after a code fix.

    ``upgraded`` vs ``would_upgrade`` (D4 — no surprising log reader): ``upgraded``
    is ALWAYS the count of rows ACTUALLY written (0 on ``--dry-run``, which writes
    nothing); ``would_upgrade`` is the count a real run WOULD upgrade, populated
    on the dry-run path so a planner can size the batch without a write. On a real
    run ``would_upgrade == upgraded`` (everything projected was written, modulo
    per-row ``failures``); on a dry run ``upgraded == 0`` and ``would_upgrade`` is
    the projection. A log reader never has to guess which meaning ``upgraded``
    carries — it is unambiguously "rows written"."""

    rows_scanned: int = 0
    candidates: int = 0  # had raw_text, no structured_blocks
    already_upgraded: int = 0  # had structured_blocks already (skipped)
    upgraded: int = 0  # rows ACTUALLY written (always 0 on --dry-run)
    would_upgrade: int = 0  # rows a real run WOULD write (the dry-run projection)
    skipped_empty_text: int = 0  # no raw_text to upgrade from
    failures: list[tuple[str, str]] = field(default_factory=list)
    dry_run: bool = False

    def as_dict(self) -> dict:
        d = asdict(self)
        d["failures"] = [{"document_id": i, "error": e} for i, e in self.failures]
        return d


def _candidate_rows(con) -> list[tuple[str, str, str | None]]:
    """``(document_id, raw_text, title)`` for every row needing an upgrade:
    raw_text present AND structured_blocks NULL. The NULL filter is what makes
    the backfill idempotent — an already-upgraded row is not a candidate."""
    return con.execute(
        "SELECT document_id, raw_text, title FROM documents "
        "WHERE raw_text IS NOT NULL AND structured_blocks IS NULL"
    ).fetchall()


def _count_already_upgraded(con) -> int:
    (n,) = con.execute(
        "SELECT COUNT(*) FROM documents WHERE structured_blocks IS NOT NULL"
    ).fetchone()
    return int(n)


def _total_rows(con) -> int:
    (n,) = con.execute("SELECT COUNT(*) FROM documents").fetchone()
    return int(n)


def backfill_structured_blocks(
    db_path: str,
    *,
    dry_run: bool = False,
) -> BackfillReport:
    """Upgrade every pre-SPR-02 document to the typed-block model.

    On ``dry_run=True`` only reads (no write connection, no mutation). On a real
    run, holds ONE write lock and upgrades all candidates under it.
    """
    from processing.extraction.to_document_model import text_to_document

    report = BackfillReport(dry_run=dry_run)

    # Read phase (no lock needed for the scan).
    rcon = connect_read(db_path)
    try:
        report.rows_scanned = _total_rows(rcon)
        report.already_upgraded = _count_already_upgraded(rcon)
        candidates = _candidate_rows(rcon)
    finally:
        rcon.close()
    report.candidates = len(candidates)

    if dry_run:
        # Report what WOULD happen without writing. ``upgraded`` STAYS 0 (a dry
        # run writes nothing); the projection lands in ``would_upgrade`` so a log
        # reader is never misled into thinking rows were upgraded.
        report.would_upgrade = sum(1 for _, raw, _ in candidates if (raw or "").strip())
        report.skipped_empty_text = report.candidates - report.would_upgrade
        return report

    if not candidates:
        return report

    # Write phase — ONE lock for the whole batch (no per-row lock thrash).
    wcon = connect_write(db_path, purpose="reader_spr02.backfill_structured_blocks")
    try:
        for document_id, raw_text, title in candidates:
            if not (raw_text or "").strip():
                report.skipped_empty_text += 1
                continue
            try:
                doc = text_to_document(
                    raw_text,
                    document_id=document_id,
                    title=title,
                    # Attribution is left default here: the backfill upgrades the
                    # BODY representation only. The authoritative rights/provenance
                    # already live on the documents ROW (content_class /
                    # ip_holder_id / source_uri) and are NOT re-derived or touched
                    # (no data loss, no re-stamp).
                    attribution=DocumentAttribution(),
                )
                set_structured_blocks(wcon, document_id, doc.model_dump_json())
                report.upgraded += 1
            except Exception as e:  # noqa: BLE001 — one bad row must not abort the batch
                # Record + SKIP — never write a half-formed model. Re-runnable
                # after a fix (the row stays NULL, still a candidate).
                report.failures.append((document_id, repr(e)))
                logger.warning(
                    "backfill: extraction failed for %s; skipped", document_id,
                    exc_info=True,
                )
    finally:
        wcon.close()

    # On a real run, the rows we WOULD upgrade are exactly the rows we DID upgrade
    # (every non-empty candidate written, minus per-row failures). Mirror the two
    # so a downstream reader sees the same invariant on either path.
    report.would_upgrade = report.upgraded
    return report


def _main(argv: list[str] | None = None) -> int:
    import argparse

    p = argparse.ArgumentParser(
        description="Reader SPR-02 M5 — backfill documents.structured_blocks "
        "for pre-SPR-02 documents (idempotent; no re-fetch; no data loss)."
    )
    p.add_argument("--db-path", required=True, help="Path to the DuckDB graph file")
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Report counts without writing (no write lock acquired).",
    )
    args = p.parse_args(argv)

    report = backfill_structured_blocks(args.db_path, dry_run=args.dry_run)
    # The "logged" M5 requirement: emit the run report as JSON to stdout.
    print(json.dumps(report.as_dict(), indent=2))
    return 0


if __name__ == "__main__":  # pragma: no cover — CLI entry
    raise SystemExit(_main())


__all__ = [
    "BackfillReport",
    "backfill_structured_blocks",
]
