"""Re-resolve chunk_id for stale voice_note_anchor rows (SPR-02).

A "stale" row is one whose ``chunker_version`` doesn't match the
current ``substrate.voice.CHUNKER_VERSION``. The worker reads the
row's stored bbox and re-runs ``resolve_chunk_for_bbox`` against
the live chunker geometry, updating ``chunk_id`` and
``chunker_version`` in place.

Idempotent: a second run with no chunker upgrade between runs
finds zero stale rows and writes nothing.

CLI:
    python -m substrate.voice.workers.rechunk_anchors --document-id <id>
    python -m substrate.voice.workers.rechunk_anchors --all

The CLI logs which anchors changed chunk_id and which stayed.

GEOMETRY GAP (carried forward from anchor_api.py):
    Today, ``resolve_chunk_for_bbox`` returns NULL because chunks
    don't expose page+bbox columns. The worker therefore writes
    chunk_id=NULL on every stale anchor and bumps the
    chunker_version. That's the correct behavior — it preserves
    the dual-key (page, bbox) and leaves chunk_id as "no
    resolution available right now" rather than asserting a
    chunk_id that's no longer accurate.
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from dataclasses import dataclass
from typing import Optional

# Repo root for direct-script invocation.
_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(_HERE))
)
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from runtime.db_lock import LockedConnection, connect_write  # noqa: E402
from substrate.voice import CHUNKER_VERSION  # noqa: E402
from substrate.voice.anchor_api import (  # noqa: E402
    BBox,
    resolve_chunk_for_bbox,
)


log = logging.getLogger("substrate.voice.workers.rechunk_anchors")


@dataclass(frozen=True)
class RechunkSummary:
    """Result of one ``rechunk`` invocation.

    Fields:
      scanned: rows considered (matching the document_id filter).
      stale_before: rows whose stored chunker_version != current.
      updated: rows actually rewritten (chunk_id OR chunker_version
        moved). Equals stale_before in the typical case.
      chunk_id_changed: subset of updated where chunk_id actually
        changed (vs only the chunker_version stamp).
    """

    scanned: int
    stale_before: int
    updated: int
    chunk_id_changed: int


def rechunk(
    con: LockedConnection,
    *,
    document_id: Optional[str] = None,
    current_version: str = CHUNKER_VERSION,
) -> RechunkSummary:
    """Re-resolve chunk_id for stale anchors. Idempotent.

    Args:
      con: write-locked connection.
      document_id: if provided, scope to one source document.
        ``None`` scans every document.
      current_version: source-of-truth chunker version (defaults to
        the live constant). Override only in tests.

    Returns:
      RechunkSummary with counts.
    """
    if not isinstance(con, LockedConnection):
        raise TypeError(
            f"rechunk requires a LockedConnection (got "
            f"{type(con).__name__}). Use "
            "runtime.db_lock.connect_write(db_path, purpose=...)."
        )

    # Scan rows in scope.
    if document_id is None:
        scanned_rows = con.execute(
            "SELECT anchor_id, document_id, page, bbox, chunk_id, "
            "chunker_version FROM voice_note_anchor"
        ).fetchall()
    else:
        scanned_rows = con.execute(
            "SELECT anchor_id, document_id, page, bbox, chunk_id, "
            "chunker_version FROM voice_note_anchor "
            "WHERE document_id = ?",
            [document_id],
        ).fetchall()

    scanned = len(scanned_rows)
    stale_before = 0
    updated = 0
    chunk_id_changed = 0

    for row in scanned_rows:
        anchor_id, doc_id, page, bbox_json, old_chunk_id, old_version = row
        if old_version == current_version:
            # Not stale — skip silently (idempotency).
            continue
        stale_before += 1
        try:
            bbox = BBox.from_json(bbox_json)
        except (ValueError, KeyError) as e:
            # Defensive: a malformed bbox is an upstream bug, not
            # our problem to fix. Log and skip.
            log.warning(
                "skipping anchor %s with malformed bbox: %s",
                anchor_id, e,
            )
            continue
        new_chunk_id = resolve_chunk_for_bbox(
            con, document_id=doc_id, page=int(page), bbox=bbox,
        )
        con.execute(
            "UPDATE voice_note_anchor "
            "SET chunk_id = ?, chunker_version = ? "
            "WHERE anchor_id = ?",
            [new_chunk_id, current_version, anchor_id],
        )
        updated += 1
        if new_chunk_id != old_chunk_id:
            chunk_id_changed += 1
            log.info(
                "anchor %s: chunk_id %r → %r (version %s → %s)",
                anchor_id, old_chunk_id, new_chunk_id,
                old_version, current_version,
            )
        else:
            log.info(
                "anchor %s: chunk_id unchanged (%r); "
                "version %s → %s",
                anchor_id, old_chunk_id, old_version, current_version,
            )

    return RechunkSummary(
        scanned=scanned,
        stale_before=stale_before,
        updated=updated,
        chunk_id_changed=chunk_id_changed,
    )


def rechunk_at_path(
    db_path: str, *, document_id: Optional[str] = None,
) -> RechunkSummary:
    """Convenience: acquire a write lock + rechunk."""
    con = connect_write(db_path, purpose="voice_anchor_rechunk")
    try:
        return rechunk(con, document_id=document_id)
    finally:
        con.close()


def _main(argv: Optional[list[str]] = None) -> int:
    p = argparse.ArgumentParser(
        prog="python -m substrate.voice.workers.rechunk_anchors",
        description=(
            "Re-resolve chunk_id for stale voice_note_anchor rows."
        ),
    )
    p.add_argument(
        "--document-id",
        default=None,
        help="Scope to one source document_id (default: all docs).",
    )
    p.add_argument(
        "--all",
        action="store_true",
        help="Scan every document. Required if --document-id is omitted.",
    )
    p.add_argument(
        "--db-path",
        default=None,
        help=(
            "Path to the DuckDB file. Defaults to "
            "ANTIEK_DUCKDB_PATH / substrate.constants.DUCKDB_PATH."
        ),
    )
    args = p.parse_args(argv)
    if args.document_id is None and not args.all:
        p.error("specify --document-id <id> or --all")
        return 2

    if args.db_path:
        db_path = os.path.expanduser(args.db_path)
    else:
        from substrate.graph import default_db_path
        db_path = default_db_path()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    summary = rechunk_at_path(db_path, document_id=args.document_id)
    print(
        f"scanned={summary.scanned} "
        f"stale_before={summary.stale_before} "
        f"updated={summary.updated} "
        f"chunk_id_changed={summary.chunk_id_changed}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
