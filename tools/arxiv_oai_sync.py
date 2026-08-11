"""Drive the arXiv OAI-PMH harvest: daily incremental sync (M3) + the full
backfill code path (M5), emitting a reproducible rights-tier census.

This is the orchestrator on top of ``acquisition.arxiv.oai_pmh.OaiPmhHarvester``
(which already owns paging, throttle routing, and the *mid-harvest* resumption
cursor). What lives HERE — and nowhere else — is the SYNC high-water mark: the
``last_successful_datestamp`` of the previous COMPLETED harvest. A daily
incremental run resumes from that datestamp (``from=last_successful_datestamp``)
so it pulls only what changed since the last good run; the backfill run drops
the lower bound (``from=None``) to walk the whole corpus.

Two checkpoints, two distinct jobs — do not conflate them:

  * the harvester's ``HarvestState`` (arxiv_oai_harvest.json) is the WITHIN-run
    resumption token; it is cleared the instant a harvest completes, so it only
    ever protects a crash MID-harvest.
  * this module's ``SyncCheckpoint`` (arxiv_oai_sync.json) is the ACROSS-run
    high-water mark; it advances only on CLEAN completion, so the next day's run
    knows where "yesterday" ended.

Idempotence (M3 acceptance): the checkpoint advances to the max datestamp
actually seen, and arxiv_id is the stable key, so re-ingesting an id UPDATES
rather than duplicates downstream, and a second run with no new papers harvests
an empty window, writes no new high-water mark beyond the (monotonic) datestamp,
and exits clean.

NO live network here. The LIVE backfill (M5) is an OPERATOR step run with a real
``httpx.Client`` against export.arxiv.org — this module only builds and verifies
the code path; ``tests/test_arxiv_oai_sync.py`` drives it through a mocked
multi-page resumption sequence (``httpx.MockTransport``), never a socket.

Usage:

    # daily incremental: harvest from the last successful datestamp forward
    python -m tools.arxiv_oai_sync incremental

    # full backfill code path (LIVE run is operator-only; this is the same path)
    python -m tools.arxiv_oai_sync backfill --until 2024-12-31

The census is emitted to stdout (human) and, with ``--census-json PATH``, as a
machine-readable record stamping the exact reproducing query (metadataPrefix +
from/until window + harvest timestamp), per the reproducibility bar.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

from acquisition.arxiv import ArxivBanned, ArxivThrottle, OaiPmhHarvester  # noqa: E402
from acquisition.arxiv.oai_persist import (  # noqa: E402
    OaiPersistResult,
    persist_oai_record,
)
from acquisition.arxiv.oai_records import build_census  # noqa: E402
from runtime.db_lock import connect_write  # noqa: E402
from substrate.graph import default_db_path, ensure_initialized  # noqa: E402
from substrate.schemas.documents import ArxivOaiRecord, RightsCensus  # noqa: E402

logger = logging.getLogger("tools.arxiv_oai_sync")


def default_sync_state_path() -> str:
    """The across-run high-water-mark file. Honors
    ``ANTIEK_ARXIV_OAI_SYNC_PATH`` for tests / alternate homes; defaults under
    ~/.antiek/ alongside the throttle + mid-harvest cursor. Deliberately a
    DIFFERENT file from the harvester's ``arxiv_oai_harvest.json`` so the
    within-run resume cursor and the across-run high-water mark can never
    clobber each other."""
    env = os.environ.get("ANTIEK_ARXIV_OAI_SYNC_PATH")
    if env:
        return env
    return str(Path.home() / ".antiek" / "arxiv_oai_sync.json")


@dataclass(frozen=True)
class SyncCheckpoint:
    """The across-run sync high-water mark.

    ``last_successful_datestamp`` is the largest OAI datestamp seen in the last
    COMPLETED harvest; the next incremental run passes it as ``from`` so arXiv
    returns only records stamped on/after it. ``last_harvested_at`` is the
    wall-clock of that completion — recorded for defensibility (when did we last
    have a good run), not used as a query bound.

    Both are ``None`` before the first successful run, which is what makes the
    first incremental run behave like a backfill (``from=None``) until a
    high-water mark exists.
    """

    last_successful_datestamp: str | None = None
    last_harvested_at: str | None = None

    def to_dict(self) -> dict:
        return {
            "last_successful_datestamp": self.last_successful_datestamp,
            "last_harvested_at": self.last_harvested_at,
        }

    @classmethod
    def from_dict(cls, d: dict) -> SyncCheckpoint:
        return cls(
            last_successful_datestamp=d.get("last_successful_datestamp"),
            last_harvested_at=d.get("last_harvested_at"),
        )


def read_checkpoint(path: str) -> SyncCheckpoint:
    """Load the high-water mark; a missing or corrupt file reads as the
    pre-first-run empty checkpoint (so a bad file degrades to a backfill rather
    than crashing). Mirrors the throttle's fail-readable-default discipline."""
    try:
        raw = Path(path).read_text(encoding="utf-8")
    except (FileNotFoundError, OSError):
        return SyncCheckpoint()
    try:
        return SyncCheckpoint.from_dict(json.loads(raw))
    except (json.JSONDecodeError, ValueError, TypeError):
        return SyncCheckpoint()


def write_checkpoint(path: str, checkpoint: SyncCheckpoint) -> None:
    """Persist the high-water mark atomically (tmp + os.replace), matching the
    throttle's write discipline so a crash mid-write can't truncate the
    file into a "never synced" state that silently re-backfills the corpus."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(json.dumps(checkpoint.to_dict()), encoding="utf-8")
    os.replace(tmp, p)


def _track_high_water(
    records: Iterator[ArxivOaiRecord], state: dict
) -> Iterator[ArxivOaiRecord]:
    """Pass records through unchanged while recording the max datestamp seen.

    The census fold (``build_census``) is the single owner of the tier counting;
    the sync only needs the high-water datestamp, so it instruments the SAME
    stream rather than iterating twice or re-implementing the fold. Tombstones
    carry a datestamp too — a deletion advances the window legitimately, so they
    count toward the high-water mark even though they're excluded from the tier
    denominator.
    """
    for record in records:
        if record.datestamp and (
            state["max_datestamp"] is None
            or record.datestamp > state["max_datestamp"]
        ):
            state["max_datestamp"] = record.datestamp
        yield record


def _persist_tap(
    records: Iterator[ArxivOaiRecord], con, tally: dict
) -> Iterator[ArxivOaiRecord]:
    """Pass records through unchanged while UPSERTing each LIVE one into the
    documents store on the passed (already write-locked) connection.

    This is the M3/M5 persistence stage: it instruments the SAME single stream
    the census folds, so the corpus lands row-by-row as records flow (never
    holding the whole backfill in memory, never iterating twice). Deleted
    tombstones are passed through to the census/high-water stages but NOT
    persisted (they carry no metadata; a tombstone is not a corpus row).
    ``tally`` accumulates the inserted/updated/skipped counts in place so the
    caller can report them after the harvest completes.
    """
    for record in records:
        if record.deleted:
            tally["skipped_deleted"] += 1
        elif persist_oai_record(con, record):
            tally["inserted"] += 1
        else:
            tally["updated"] += 1
        yield record


@dataclass(frozen=True)
class SyncResult:
    """The outcome of one sync run: the census + how the high-water mark moved
    + how the corpus was persisted.

    ``advanced`` is False when no record carried a datestamp past the prior
    high-water mark — the M3 "second run with no new papers writes nothing"
    case, where the checkpoint datestamp is left untouched.

    ``persist`` is the documents-store upsert tally: it makes the M3 idempotency
    and M5 corpus-present claims checkable (a second pass over the same ids
    reports ``inserted == 0``).
    """

    census: RightsCensus
    from_date: str | None
    until_date: str | None
    previous_datestamp: str | None
    new_datestamp: str | None
    advanced: bool
    persist: OaiPersistResult


def run_sync(
    *,
    harvester: OaiPmhHarvester,
    mode: str,
    sync_state_path: str,
    metadata_prefix: str = "arXiv",
    until_date: str | None = None,
    resume: bool = True,
    harvested_at: datetime | None = None,
    db_path: str | None = None,
) -> SyncResult:
    """Run one harvest, PERSIST it to the documents store, fold it into a census,
    then advance the high-water mark on clean completion.

    ``mode`` is ``"incremental"`` (``from`` = the persisted high-water datestamp)
    or ``"backfill"`` (``from`` = None, the whole corpus — the M5 code path).
    Both are the IDENTICAL harvest call; only the lower bound differs, which is
    exactly why the mocked backfill here verifies the operator's live backfill.

    ``metadata_prefix`` is stamped on the census for reproducibility and must
    match the prefix the ``harvester`` was built with (both default to ``arXiv``,
    the only prefix carrying ``<license>``); it is passed explicitly rather than
    read off the harvester so this orchestrator does not reach into harvester
    internals.

    ``db_path`` resolves the documents store (honoring ``ANTIEK_DUCKDB_PATH``);
    the harvest is upserted into it under ONE write lock for the whole pass —
    each LIVE record landing as a ``doc-arxiv-<id>`` row keyed by arxiv_id (M5
    corpus-present), re-ingesting an id UPDATEing in place rather than
    duplicating (M3). The persist stage taps the SAME stream the census folds, so
    a backfill streams to the DB row-by-row without holding the corpus in memory.

    The high-water mark advances ONLY if some record's datestamp exceeds the
    prior mark and the harvest reached clean completion (the harvester clears its
    own mid-harvest cursor on completion; we key off that same streamed-to-end
    signal). A crash mid-harvest propagates out of the iterator (and out of the
    write lock) BEFORE this function writes the checkpoint, so a partial harvest
    never advances the across-run mark — the next run re-covers the same window
    via the harvester's own resume cursor, and ``arxiv_id`` keys keep the
    re-cover idempotent (the re-covered rows UPDATE, they don't duplicate).
    """
    checkpoint = read_checkpoint(sync_state_path)
    if mode == "incremental":
        from_date = checkpoint.last_successful_datestamp
    elif mode == "backfill":
        from_date = None
    else:
        raise ValueError(f"unknown sync mode {mode!r} (want 'incremental'/'backfill')")

    at = harvested_at or datetime.now(UTC)
    # Seed the high-water tracker from any INTERRUPTED harvest's persisted max
    # datestamp. On a post-crash resume the harvester re-streams only the
    # remaining (often older) pages, so without this seed the mark could be set
    # below the max already consumed pre-crash. A clean prior run cleared the
    # cursor, so this is None then and the seed is a no-op.
    seed_max = harvester.persisted_max_datestamp() if resume else None
    high_water = {"max_datestamp": seed_max}
    persist_tally = {"inserted": 0, "updated": 0, "skipped_deleted": 0}

    resolved_db = ensure_initialized(db_path or default_db_path())

    # One write lock wraps the WHOLE harvest: build_census drives the stream to
    # completion (or propagates a crash) while the instrumented pipeline records
    # the max datestamp (_track_high_water) and upserts each live record into the
    # documents store (_persist_tap), all on the single locked connection. The
    # lock closes — releasing the writer — before the checkpoint is written, and
    # a crash mid-harvest propagates out of the `with` BEFORE write_checkpoint.
    with connect_write(resolved_db, purpose="acquisition/arxiv_oai_sync") as con:
        census = build_census(
            _persist_tap(
                _track_high_water(
                    harvester.harvest(
                        from_date=from_date, until_date=until_date, resume=resume
                    ),
                    high_water,
                ),
                con,
                persist_tally,
            ),
            metadata_prefix=metadata_prefix,
            from_date=from_date,
            until_date=until_date,
            harvested_at=at,
        )

    seen = high_water["max_datestamp"]
    prior = checkpoint.last_successful_datestamp
    # Monotonic: never retreat the mark if this window's max is older than the
    # prior high-water (a backfill of an older slice must not rewind "today").
    advanced = seen is not None and (prior is None or seen > prior)
    new_datestamp = seen if advanced else prior

    write_checkpoint(
        sync_state_path,
        SyncCheckpoint(
            last_successful_datestamp=new_datestamp,
            last_harvested_at=at.isoformat(),
        ),
    )

    return SyncResult(
        census=census,
        from_date=from_date,
        until_date=until_date,
        previous_datestamp=prior,
        new_datestamp=new_datestamp,
        advanced=advanced,
        persist=OaiPersistResult(
            inserted=persist_tally["inserted"],
            updated=persist_tally["updated"],
            skipped_deleted=persist_tally["skipped_deleted"],
        ),
    )


def _print_census(result: SyncResult) -> None:
    c = result.census
    window = f"{result.from_date or '(corpus start)'} .. {result.until_date or '(latest)'}"
    print("\narXiv OAI-PMH census — query reproduces from:")
    print(f"  metadataPrefix = {c.metadata_prefix}")
    print(f"  window         = {window}")
    print(f"  harvested_at   = {c.harvested_at.isoformat()}")
    print(f"\n  total live papers: {c.total}  (+ {c.deleted} deleted tombstones)")
    print(f"  T1 redistributable : {c.t1:>8}  ({c.fraction(c.t1):.4f})")
    print(f"  T2 non-commercial  : {c.t2:>8}  ({c.fraction(c.t2):.4f})")
    print(f"  T3 default/unknown : {c.t3:>8}  ({c.fraction(c.t3):.4f})")
    print(f"     of which ambiguous (no declared license): {c.ambiguous}")
    p = result.persist
    print(f"\n  persisted to documents store: {p.persisted} rows "
          f"({p.inserted} new, {p.updated} updated; "
          f"{p.skipped_deleted} tombstones skipped)")
    if result.advanced:
        print(f"\n  high-water mark advanced {result.previous_datestamp or '(none)'}"
              f" -> {result.new_datestamp}")
    else:
        print(f"\n  no new papers; high-water mark unchanged "
              f"({result.new_datestamp or '(none)'})")


def census_to_dict(result: SyncResult) -> dict:
    """The machine-readable census record: the counts + the EXACT reproducing
    query. ``ambiguous`` is reported as its own number (never folded silently
    into T3) per the intellectual-honesty bar; percentages are recomputed by the
    reader from the integer counts (we never write hand-rounded floats)."""
    c = result.census
    return {
        "metadata_prefix": c.metadata_prefix,
        "from_date": c.from_date,
        "until_date": c.until_date,
        "harvested_at": c.harvested_at.isoformat(),
        "total": c.total,
        "deleted": c.deleted,
        "t1": c.t1,
        "t2": c.t2,
        "t3": c.t3,
        "ambiguous": c.ambiguous,
        "high_water_datestamp": result.new_datestamp,
        "high_water_advanced": result.advanced,
        "persisted_rows": result.persist.persisted,
        "persisted_inserted": result.persist.inserted,
        "persisted_updated": result.persist.updated,
        "persisted_skipped_deleted": result.persist.skipped_deleted,
    }


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python -m tools.arxiv_oai_sync",
        description=(
            "Harvest arXiv OAI-PMH metadata + license, emit a rights-tier "
            "census. Incremental resumes from the last successful datestamp; "
            "backfill walks the whole corpus (LIVE backfill is operator-only)."
        ),
    )
    p.add_argument(
        "mode", choices=("incremental", "backfill"),
        help="incremental: from=last successful datestamp; backfill: from=None",
    )
    p.add_argument(
        "--until", dest="until_date",
        help="upper datestamp bound (YYYY-MM-DD); default: no bound",
    )
    p.add_argument(
        "--metadata-prefix", default="arXiv",
        help="OAI metadataPrefix (default arXiv — the one carrying <license>)",
    )
    p.add_argument(
        "--base-url",
        help="OAI-PMH base URL (default oaipmh.arxiv.org/oai via the harvester)",
    )
    p.add_argument(
        "--no-resume", action="store_true",
        help="ignore any persisted mid-harvest cursor and start the window fresh",
    )
    p.add_argument(
        "--census-json",
        help="write the machine-readable census record to this path",
    )
    p.add_argument(
        "--db-path",
        help="documents store path (default: ANTIEK_DUCKDB_PATH or the resolved "
             "graph DB); the harvested metadata corpus is upserted here",
    )
    return p


def main(argv: Sequence[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    args = build_parser().parse_args(argv)

    harvester = OaiPmhHarvester(
        throttle=ArxivThrottle(),
        metadata_prefix=args.metadata_prefix,
        base_url=args.base_url,
    )
    try:
        result = run_sync(
            harvester=harvester,
            mode=args.mode,
            metadata_prefix=args.metadata_prefix,
            until_date=args.until_date,
            sync_state_path=default_sync_state_path(),
            resume=not args.no_resume,
            db_path=args.db_path,
        )
    except ArxivBanned as exc:
        # The throttle ban sentinel is active — PAUSE, do not re-hit the
        # endpoint (re-hitting is the bug that IP-banned the box). The mid-harvest
        # cursor (if any) is intact, so a later run resumes where this paused.
        print(f"error: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:  # network / HTTP / parse failure
        print(f"error: arxiv OAI-PMH sync failed: {exc}", file=sys.stderr)
        return 1

    _print_census(result)
    if args.census_json:
        Path(args.census_json).write_text(
            json.dumps(census_to_dict(result), indent=2), encoding="utf-8"
        )
        print(f"\ncensus record written to {args.census_json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
