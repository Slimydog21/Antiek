#!/usr/bin/env python3
"""arXiv takedown CLI — erase a paper's body by arxiv_id + audit it (SPR-09 M4).

A ToS removal demand for an arXiv paper arrives keyed by the paper's arXiv id
(e.g. ``2401.00001``), not by Antiek's internal document_id. This CLI bridges
that gap: it resolves ``arxiv_doc_id(arxiv_id) -> document_id``, opens a
single-writer ``connect_write`` lock, delegates the actual erasure to the
EXISTING ``substrate.books.takedown.take_down`` handler (which atomically nulls
``raw_text`` + restricts ``content_class`` to the takedown gate + flips
``taken_down`` + emits its own typed events under one lock), AND records an
``arxiv.takedown`` event into the M4 ``arxiv_audit`` trace so the removal shows
up in ``trace(con, arxiv_id)`` alongside the paper's fetch/serve/accrue history.

What ``take_down`` removes — HONEST about chunk erasure
------------------------------------------------------
``take_down`` purges the materialized body (``documents.raw_text`` → NULL) and
moves ``content_class`` to the takedown gate, so the paper VANISHES from both the
full-text serve allowlist AND the chunk-search G1 denylist — it is unservable and
unsearchable immediately. BUT it does NOT delete the ``chunks`` rows: retrieval
is GATE-SUPPRESSED, not row-deleted. If a removal demand requires the chunk rows
physically gone too, that is a NOTED FOLLOW-UP — a ``substrate/deletion_worker/``
exists in the tree and is the likely home for full chunk deletion. This tool does
NOT silently claim chunks are deleted; the audit ``detail`` records
``chunks_deleted: false`` so the trace is honest about exactly what was erased.
"""

from __future__ import annotations

import argparse
import sys

from acquisition.arxiv import arxiv_doc_id
from runtime.db_lock import connect_write
from substrate.audit.arxiv_audit import ARXIV_TAKEDOWN, record_event
from substrate.books.takedown import BookNotRegistered, take_down


def take_down_arxiv(
    db_path: str, arxiv_id: str, *, reason: str
) -> tuple[bool, str]:
    """Resolve ``arxiv_id`` → document_id, take the paper down, and record an
    ``arxiv.takedown`` audit event. Returns ``(performed, document_id)`` where
    ``performed`` is ``take_down``'s result (``False`` if already taken down).

    The takedown + the audit write happen under the SAME write lock so the trace
    and the erasure are consistent — there is no window where the body is gone
    but the audit is missing (or vice versa).
    """
    document_id = arxiv_doc_id(arxiv_id)
    con = connect_write(db_path, purpose="arxiv_takedown")
    try:
        performed = take_down(con, document_id, reason=reason)
        # Audit the takedown into the arXiv compliance trace. §9.0: refs + reason
        # only — never the purged body. ``chunks_deleted: false`` is the honest
        # record that take_down gate-suppresses chunks rather than deleting rows.
        #
        # The audit detail is INDEPENDENT of ``performed`` on purpose: a takedown
        # for a given (arxiv_id, reason) is ONE compliance event whether or not
        # THIS call was the one that did the purge — so re-running the CLI on an
        # already-down paper UNDER THE SAME REASON is an idempotent no-op on BOTH
        # the body (take_down returns False) AND the audit (same deterministic
        # event_id → no second row). A re-takedown under a DIFFERENT ``reason`` is
        # a DISTINCT compliance event (round-2: ``reason`` is now part of the
        # event_id identity), so the new reason is recorded as its own leg rather
        # than silently collapsing onto the first. Adding ``performed`` to detail
        # would mint a distinct id on the second same-reason run and proliferate
        # rows, so it stays out of detail.
        record_event(
            con,
            arxiv_id=arxiv_id,
            document_id=document_id,
            kind=ARXIV_TAKEDOWN,
            reason=reason,
            detail={
                "raw_text_purged": True,
                "chunks_deleted": False,
                "chunk_erasure_followup": "substrate/deletion_worker/",
            },
        )
    finally:
        con.close()
    return performed, document_id


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Take down an arXiv paper by arxiv_id: null its body + restrict it "
            "from serve/search, and record an arxiv.takedown audit event."
        )
    )
    parser.add_argument("arxiv_id", help="The arXiv id, e.g. 2401.00001")
    parser.add_argument(
        "--reason", required=True, help="The takedown reason (recorded in the audit)."
    )
    parser.add_argument(
        "--db-path",
        default=None,
        help="DuckDB path (defaults to the substrate default_db_path()).",
    )
    args = parser.parse_args(argv)

    db_path = args.db_path
    if db_path is None:
        from substrate.graph import default_db_path, ensure_initialized

        db_path = default_db_path()
        ensure_initialized(db_path)

    try:
        performed, document_id = take_down_arxiv(
            db_path, args.arxiv_id, reason=args.reason
        )
    except BookNotRegistered as exc:
        print(
            f"ERROR: {args.arxiv_id} (document_id resolved) is not a registered "
            f"book — nothing to take down. {exc}",
            file=sys.stderr,
        )
        return 2

    if performed:
        print(
            f"OK: took down {args.arxiv_id} (document_id={document_id}); "
            "raw_text purged + content restricted from serve/search. "
            "Chunk ROWS are gate-suppressed (not deleted) — see "
            "substrate/deletion_worker/ if physical chunk erasure is required. "
            "Recorded arxiv.takedown in the audit trace."
        )
    else:
        print(
            f"OK: {args.arxiv_id} (document_id={document_id}) was ALREADY taken "
            "down — no second purge. arxiv.takedown audit event recorded "
            "(idempotent)."
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
