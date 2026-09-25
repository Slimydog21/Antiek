"""Run arXiv metadata sync through the governed OAI harvester.

The bulk path reads a verified plain JSONL snapshot and commits document rows
with their physical byte cursor in the same DuckDB transaction. A restarted
run resumes at the last committed line. Its OAI tail replays from the recorded
bulk/prior high-water date, and the DB completion row is authoritative after
backup restore. The JSON checkpoint is a mirror written after completion.

The legacy pure-OAI path retains its JSON checkpoint while no DB bulk cursor
exists. Once a DB bulk cursor exists, pure-OAI and legacy reset are refused so
two independent progress authorities cannot diverge.
"""

from __future__ import annotations

import argparse
import contextlib
import json
import logging
import os
import sys
import time
from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import cast

_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

from runtime.ssl_bootstrap import bootstrap as _ssl_bootstrap  # noqa: E402

# A python.org interpreter ships no CA bundle (arxiv-missing-ssl-env); point at
# certifi unless SSL_CERT_FILE is already set (systemd / ca-certificates win).
_ssl_bootstrap()

from acquisition.arxiv import ArxivBanned, ArxivThrottle, OaiPmhHarvester  # noqa: E402
from acquisition.arxiv.bulk import (  # noqa: E402
    default_bulk_snapshot_path,
    ensure_bulk_snapshot,
    iter_bulk_oai_lines,
)
from acquisition.arxiv.oai_persist import (  # noqa: E402
    OaiPersistResult,
    persist_oai_record,
)
from acquisition.arxiv.oai_pmh import default_harvest_state_path  # noqa: E402
from acquisition.arxiv.oai_records import build_census  # noqa: E402
from runtime.db_lock import LockedConnection, connect_write  # noqa: E402
from substrate.graph import default_db_path, ensure_initialized  # noqa: E402
from substrate.graph.schema import load_arxiv_bulk_progress  # noqa: E402
from substrate.schemas.documents import ArxivOaiRecord, RightsCensus  # noqa: E402
from tools.arxiv_bulk_resume import (  # noqa: E402
    assert_snapshot_unchanged,
    commit_bulk_slice,
    open_generation,
    save_progress,
    set_phase,
    verify_snapshot,
    whole_run_lock,
)

logger = logging.getLogger("tools.arxiv_oai_sync")

# Short-lived write-lock defaults (prod nightly). Override via CLI or env.
# Incident 2026-09-18: one connect_write wrapped the entire --bulk stream and
# held antiek.duckdb.write.lock for ~5.5h, starving api.antiek.ai /health.
DEFAULT_PERSIST_BATCH_SIZE = 200
DEFAULT_MAX_LOCK_SECONDS = 15.0
DEFAULT_LOCK_YIELD_SECONDS = 0.5


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    return int(raw)


def _env_float(name: str, default: float) -> float:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    return float(raw)


def resolve_persist_batch_size(cli_value: int | None = None) -> int:
    if cli_value is not None:
        return cli_value
    return _env_int("ANTIEK_ARXIV_PERSIST_BATCH_SIZE", DEFAULT_PERSIST_BATCH_SIZE)


def resolve_max_lock_seconds(cli_value: float | None = None) -> float:
    if cli_value is not None:
        return cli_value
    return _env_float("ANTIEK_ARXIV_MAX_LOCK_SECONDS", DEFAULT_MAX_LOCK_SECONDS)


def resolve_lock_yield_seconds(cli_value: float | None = None) -> float:
    if cli_value is not None:
        return cli_value
    return _env_float("ANTIEK_ARXIV_LOCK_YIELD_SECONDS", DEFAULT_LOCK_YIELD_SECONDS)


def _persist_one(con: LockedConnection, record: ArxivOaiRecord, tally: dict[str, int]) -> None:
    if record.deleted:
        tally["skipped_deleted"] += 1
    elif persist_oai_record(con, record):
        tally["inserted"] += 1
    else:
        tally["updated"] += 1


def _flush_persist_batch(
    db_path: str,
    batch: list[ArxivOaiRecord],
    tally: dict[str, int],
    *,
    max_lock_s: float,
    yield_s: float,
) -> None:
    """Persist ``batch`` under one or more short-lived write locks.

    Releases the lock every ``max_lock_s`` wall-clock seconds (or sooner when
    the batch ends), sleeping ``yield_s`` between sessions so other writers
    (uvicorn / agent-work lease) can acquire the flock.
    """
    if not batch:
        return
    idx = 0
    n = len(batch)
    while idx < n:
        with connect_write(
            db_path, purpose="acquisition/arxiv_oai_sync", keepalive_s=0
        ) as con:
            t0 = time.monotonic()
            while idx < n:
                _persist_one(con, batch[idx], tally)
                idx += 1
                if max_lock_s > 0 and (time.monotonic() - t0) >= max_lock_s:
                    break
        if idx < n and yield_s > 0:
            time.sleep(yield_s)


def _chunked_persist_tap(
    records: Iterator[ArxivOaiRecord],
    db_path: str,
    tally: dict[str, int],
    *,
    batch_size: int = DEFAULT_PERSIST_BATCH_SIZE,
    max_lock_s: float = DEFAULT_MAX_LOCK_SECONDS,
    yield_s: float = DEFAULT_LOCK_YIELD_SECONDS,
) -> Iterator[ArxivOaiRecord]:
    """Pass records through while UPSERTing under short-lived write locks.

    Same census/high-water stream contract as ``_persist_tap``, but never holds
    the DuckDB write lock across an entire multi-hour harvest. Crash safety is
    unchanged: the across-run high-water checkpoint still advances only after
    the full stream completes; mid-run crashes leave upserts idempotent by
    ``arxiv_id``.
    """
    if batch_size < 1:
        raise ValueError("batch_size must be >= 1")
    if max_lock_s < 0:
        raise ValueError("max_lock_s must be >= 0")
    if yield_s < 0:
        raise ValueError("yield_s must be >= 0")

    pending: list[ArxivOaiRecord] = []
    for record in records:
        pending.append(record)
        if len(pending) >= batch_size:
            _flush_persist_batch(
                db_path, pending, tally, max_lock_s=max_lock_s, yield_s=yield_s
            )
            yield from pending
            pending = []
            if yield_s > 0:
                time.sleep(yield_s)
    if pending:
        _flush_persist_batch(
            db_path, pending, tally, max_lock_s=max_lock_s, yield_s=yield_s
        )
        yield from pending



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

    def to_dict(self) -> dict[str, str | None]:
        return {
            "last_successful_datestamp": self.last_successful_datestamp,
            "last_harvested_at": self.last_harvested_at,
        }

    @classmethod
    def from_dict(cls, d: dict[str, str | None]) -> SyncCheckpoint:
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


def reset_state_files(
    *,
    harvest_state_path: str | None = None,
    sync_state_path: str | None = None,
) -> tuple[Path, ...]:
    """Operator recovery: delete the mid-harvest cursor AND the across-run
    high-water mark so the next run starts as a fresh first-run backfill (an
    ``incremental`` run with no mark behaves like a backfill until a new mark
    exists).

    The THROTTLE state (``~/.antiek/arxiv_throttle.json``) is deliberately NOT
    touched: a live ``banned_until`` sentinel must survive a reset, because
    clearing it re-opens the re-hit-a-banned-endpoint bug that IP-banned the
    box. If only one of the two files exists (e.g. a crash between the harvest
    completing and the sync checkpoint writing), the other is removed
    independently.

    Paths honor the same env overrides as the defaults
    (``ANTIEK_ARXIV_OAI_STATE_PATH`` / ``ANTIEK_ARXIV_OAI_SYNC_PATH``).
    Returns the paths actually removed (empty when neither file existed)."""
    removed: list[Path] = []
    for p in (
        Path(harvest_state_path or default_harvest_state_path()),
        Path(sync_state_path or default_sync_state_path()),
    ):
        with contextlib.suppress(FileNotFoundError):
            p.unlink()
            removed.append(p)
    return tuple(removed)


def _track_high_water(
    records: Iterator[ArxivOaiRecord], state: dict[str, str | None]
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
    records: Iterator[ArxivOaiRecord], con: LockedConnection, tally: dict[str, int]
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
    persist_batch_size: int | None = None,
    max_lock_seconds: float | None = None,
    lock_yield_seconds: float | None = None,
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
    the harvest is upserted in SHORT-LIVED write-lock batches (see
    ``persist_batch_size`` / ``max_lock_seconds``) — each LIVE record landing as a
    ``doc-arxiv-<id>`` row keyed by arxiv_id (M5 corpus-present), re-ingesting an
    id UPDATEing in place rather than duplicating (M3). The persist stage taps the
    SAME stream the census folds, so a backfill streams to the DB row-by-row
    without holding the corpus in memory or monopolizing the write lock.

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
    with whole_run_lock(resolved_db):
        with connect_write(resolved_db, purpose="arxiv_pure_oai_authority_check", keepalive_s=0) as con:
            if load_arxiv_bulk_progress(con) is not None:
                raise ValueError("pure OAI cannot run while DB-authoritative bulk progress is active")

        batch_size = resolve_persist_batch_size(persist_batch_size)
        max_lock_s = resolve_max_lock_seconds(max_lock_seconds)
        yield_s = resolve_lock_yield_seconds(lock_yield_seconds)

        # Chunked write locks: build_census drives the stream to completion while
        # _chunked_persist_tap upserts in short sessions (batch_size / max_lock_s)
        # and yields the lock between flushes. Checkpoint still writes ONLY after
        # the stream ends cleanly — crash mid-harvest never advances high-water.
        census = build_census(
            _chunked_persist_tap(
                _track_high_water(
                    harvester.harvest(
                        from_date=from_date, until_date=until_date, resume=resume
                    ),
                    high_water,
                ),
                resolved_db,
                persist_tally,
                batch_size=batch_size,
                max_lock_s=max_lock_s,
                yield_s=yield_s,
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


def run_bulk_sync(
    *,
    harvester: OaiPmhHarvester,
    mode: str,
    sync_state_path: str,
    bulk_snapshot_path: str,
    metadata_prefix: str = "arXiv",
    until_date: str | None = None,
    resume: bool = True,
    harvested_at: datetime | None = None,
    db_path: str | None = None,
    oai_tail: bool = True,
    persist_batch_size: int | None = None,
    max_lock_seconds: float | None = None,
    lock_yield_seconds: float | None = None,
    replay_from_zero: bool = False,
) -> SyncResult:
    """Resume a verified plain JSONL snapshot, then replay the OAI tail.

    The whole-run flock serializes timer/CLI callers. Each bounded DuckDB
    transaction commits selected document rows with the next physical line
    offset, cumulative event counts and bulk maximum date. On interruption,
    the DB cursor resumes the suffix; a tail failure leaves phase ``tail`` and
    replays its inclusive date window. Only complete success advances the DB
    high-water and writes the observational JSON mirror.

    An absent DB cursor plus a legacy JSON high-water requires an explicit
    ``replay_from_zero`` operator choice. Changed source bytes, window, parser
    contract or tail mode during an incomplete generation fail closed.
    """
    if mode not in {"incremental", "backfill"}:
        raise ValueError("unknown arXiv sync mode")
    batch_size = resolve_persist_batch_size(persist_batch_size)
    max_lock_s = resolve_max_lock_seconds(max_lock_seconds)
    yield_s = resolve_lock_yield_seconds(lock_yield_seconds)
    if batch_size < 1 or max_lock_s < 0 or yield_s < 0:
        raise ValueError("invalid arXiv batch or lock interval")
    at = harvested_at or datetime.now(UTC)
    resolved_db = ensure_initialized(db_path or default_db_path())
    persist_tally = {"inserted": 0, "updated": 0, "skipped_deleted": 0}

    with whole_run_lock(resolved_db):
        source = verify_snapshot(bulk_snapshot_path)
        progress = open_generation(
            resolved_db, source, mode=mode, until_date=until_date,
            metadata_prefix=metadata_prefix, sync_state_path=sync_state_path,
            replay_from_zero=replay_from_zero, tail_enabled=oai_tail,
            resume=resume,
        )
        from_date = cast(date | None, progress["from_date"])
        prior = cast(date | None, progress["completed_high_water"])
        from_text = from_date.isoformat() if from_date is not None else None
        prior_text = prior.isoformat() if prior is not None else None
        if progress["phase"] == "bulk":
            with open(source.path, "rb") as fh:
                opened = os.fstat(fh.fileno())
                if (opened.st_dev, opened.st_ino, opened.st_size, opened.st_mtime_ns) != (
                    source.device, source.inode, source.size, source.mtime_ns,
                ):
                    raise ValueError("bulk snapshot changed before scanning")
                pending = []
                selected = 0
                committed_slices = 0
                for line in iter_bulk_oai_lines(
                    fh, start_offset=cast(int, progress["next_byte_offset"]),
                    since=from_text, until=until_date,
                ):
                    if line.is_eof:
                        break
                    pending.append(line)
                    selected += line.record is not None
                    if selected < batch_size and len(pending) < max(1000, batch_size):
                        continue
                    while pending:
                        assert_snapshot_unchanged(source)
                        consumed, progress, delta = commit_bulk_slice(
                            resolved_db, pending, progress, max_lock_s=max_lock_s,
                        )
                        for key, count in delta.items():
                            persist_tally[key] += count
                        committed_slices += 1
                        if committed_slices % 25 == 0:
                            logger.info(
                                "arXiv bulk progress bytes=%d/%d lines=%d selected=%d",
                                cast(int, progress["next_byte_offset"]), source.size,
                                cast(int, progress["physical_line_count"]),
                                cast(int, progress["selected_record_count"]),
                            )
                        del pending[:consumed]
                        if yield_s > 0:
                            time.sleep(yield_s)
                    selected = 0
                while pending:
                    assert_snapshot_unchanged(source)
                    consumed, progress, delta = commit_bulk_slice(
                        resolved_db, pending, progress, max_lock_s=max_lock_s,
                    )
                    for key, count in delta.items():
                        persist_tally[key] += count
                    committed_slices += 1
                    if committed_slices % 25 == 0:
                        logger.info(
                            "arXiv bulk progress bytes=%d/%d lines=%d selected=%d",
                            cast(int, progress["next_byte_offset"]), source.size,
                            cast(int, progress["physical_line_count"]),
                            cast(int, progress["selected_record_count"]),
                        )
                    del pending[:consumed]
                    if yield_s > 0:
                        time.sleep(yield_s)
            assert_snapshot_unchanged(source)
            if verify_snapshot(source.path).sha256 != source.sha256:
                raise ValueError("bulk snapshot digest changed during scanning")
            if progress["next_byte_offset"] != source.size:
                raise RuntimeError("bulk stream stopped before verified EOF")
            logger.info(
                "arXiv bulk reached verified EOF bytes=%d lines=%d selected=%d",
                source.size, cast(int, progress["physical_line_count"]),
                cast(int, progress["selected_record_count"]),
            )
            progress = set_phase(resolved_db, progress, "tail")

        # A failed OAI tail keeps phase=tail. Retry replays from the same
        # inclusive date, regardless of an older saved OAI page token.
        bulk_max = cast(date | None, progress["bulk_max_datestamp"])
        bounds = [bound for bound in (prior, bulk_max) if bound is not None]
        tail_bound = max(bounds) if bounds else None
        tail_from = tail_bound.isoformat() if tail_bound is not None else None
        high_water: dict[str, str | None] = {"max_datestamp": None}
        tail_attempted = oai_tail and not (
            until_date is not None and tail_from is not None and tail_from >= until_date
        )
        if tail_attempted:
            tail_census = build_census(
                _chunked_persist_tap(
                    _track_high_water(
                        harvester.harvest(
                            from_date=tail_from, until_date=until_date, resume=False,
                        ), high_water,
                    ),
                    resolved_db, persist_tally, batch_size=batch_size,
                    max_lock_s=max_lock_s, yield_s=yield_s,
                ),
                metadata_prefix=metadata_prefix, from_date=tail_from,
                until_date=until_date, harvested_at=at,
            )
        else:
            tail_census = RightsCensus(
                t1=0, t2=0, t3=0, total=0, ambiguous=0,
                metadata_prefix=metadata_prefix, from_date=tail_from,
                until_date=until_date, harvested_at=at,
            )
        census = RightsCensus(
            t1=cast(int, progress["bulk_t1_events"]) + tail_census.t1,
            t2=cast(int, progress["bulk_t2_events"]) + tail_census.t2,
            t3=cast(int, progress["bulk_t3_events"]) + tail_census.t3,
            total=(cast(int, progress["bulk_t1_events"]) + cast(int, progress["bulk_t2_events"])
                   + cast(int, progress["bulk_t3_events"]) + tail_census.total),
            ambiguous=cast(int, progress["bulk_ambiguous_events"]) + tail_census.ambiguous,
            deleted=cast(int, progress["bulk_deleted_events"]) + tail_census.deleted,
            metadata_prefix=metadata_prefix, from_date=from_text,
            until_date=until_date, harvested_at=at,
        )
        candidates = [stamp for stamp in (prior_text, high_water["max_datestamp"],
                      bulk_max.isoformat() if bulk_max is not None else None) if stamp]
        new_datestamp = max(candidates) if candidates else None
        advanced = new_datestamp is not None and (
            prior_text is None or new_datestamp > prior_text
        )
        # Complete only after the entire tail succeeds and the source still
        # hashes to the generation's digest. This is one DB transaction.
        assert_snapshot_unchanged(source)
        if verify_snapshot(source.path).sha256 != source.sha256:
            raise ValueError("bulk snapshot digest changed before completion")
        provenance = {
            "kind": "event_counts", "generation_id": progress["generation_id"],
            "source_sha256": source.sha256,
            "tail_bound": tail_from if tail_attempted else None,
            "t1": census.t1, "t2": census.t2, "t3": census.t3,
            "ambiguous": census.ambiguous, "deleted": census.deleted,
        }
        completed = {
            **progress, "phase": "complete",
            "completed_high_water": (
                datetime.fromisoformat(new_datestamp).date()
                if new_datestamp is not None else None
            ),
            "completed_generation_id": progress["generation_id"],
            "completed_at": at.replace(tzinfo=None),
            "completed_bulk_sha256": source.sha256,
            "completed_tail_bound": tail_bound if tail_attempted else None,
            "completed_census_json": json.dumps(provenance, separators=(",", ":")),
        }
        with connect_write(
            resolved_db, purpose="arxiv_bulk_complete", keepalive_s=0
        ) as con, con.transaction():
            save_progress(con, completed)
        # JSON is an observational mirror. The DB row is the authority after a
        # crash or restore, and any mismatch is reported on the next run.
        write_checkpoint(
            sync_state_path,
            SyncCheckpoint(
                last_successful_datestamp=new_datestamp,
                last_harvested_at=at.isoformat(),
            ),
        )

    return SyncResult(
        census=census, from_date=from_text, until_date=until_date,
        previous_datestamp=prior_text, new_datestamp=new_datestamp,
        advanced=advanced,
        persist=OaiPersistResult(**persist_tally),
    )


def _print_census(result: SyncResult) -> None:
    c = result.census
    window = f"{result.from_date or '(corpus start)'} .. {result.until_date or '(latest)'}"
    print("\narXiv OAI-PMH census — query reproduces from:")
    print(f"  metadataPrefix = {c.metadata_prefix}")
    print(f"  window         = {window}")
    print(f"  harvested_at   = {c.harvested_at.isoformat()}")
    print(f"\n  live record events: {c.total}  (+ {c.deleted} deleted tombstone events)")
    print(f"  T1 redistributable : {c.t1:>8}  ({c.fraction(c.t1):.4f})")
    print(f"  T2 non-commercial  : {c.t2:>8}  ({c.fraction(c.t2):.4f})")
    print(f"  T3 default/unknown : {c.t3:>8}  ({c.fraction(c.t3):.4f})")
    print(f"     of which ambiguous (no declared license): {c.ambiguous}")
    p = result.persist
    print(f"\n  persisted during this attempt: {p.persisted} rows "
          f"({p.inserted} new, {p.updated} updated; "
          f"{p.skipped_deleted} tombstones skipped)")
    if result.advanced:
        print(f"\n  high-water mark advanced {result.previous_datestamp or '(none)'}"
              f" -> {result.new_datestamp}")
    else:
        print(f"\n  no new papers; high-water mark unchanged "
              f"({result.new_datestamp or '(none)'})")


def census_to_dict(result: SyncResult) -> dict[str, object]:
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
            "Harvest arXiv metadata + license, emit a rights-tier census. "
            "Incremental resumes from the last successful datestamp; backfill "
            "walks the whole corpus. Pass --bulk for the free metadata "
            "snapshot path (mass throughput) + OAI tail (records newer than "
            "the snapshot)."
        ),
    )
    p.add_argument(
        "mode", choices=("incremental", "backfill"),
        help="incremental: from=last successful datestamp; backfill: from=None",
    )
    p.add_argument(
        "--bulk", action="store_true",
        help="bulk-dump-aware mode: stream the free arXiv metadata snapshot "
             "for mass throughput, then OAI-PMH only for records newer than "
             "the snapshot (recommended for nightly; pure OAI is ~22h for a "
             "26K-doc window under the 1-req/3s rate rule)",
    )
    p.add_argument(
        "--bulk-snapshot",
        help="path to a local plain, seekable arxiv-metadata-oai-snapshot.json "
             "(compressed wrappers cannot use byte-offset resume). When omitted, downloads "
             "the free GCS mirror to ~/.antiek/ (or ANTIEK_ARXIV_BULK_SNAPSHOT)",
    )
    p.add_argument(
        "--bulk-only", action="store_true",
        help="with --bulk: skip the OAI tail (snapshot only). Useful for an "
             "offline backfill when the snapshot is known-current",
    )
    p.add_argument(
        "--bulk-force-download", action="store_true",
        help="with --bulk: re-download the snapshot even if a local file exists",
    )
    p.add_argument(
        "--bulk-replay-from-zero", action="store_true",
        help="explicit operator full replay when legacy JSON high-water exists but DB progress is absent",
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
        help="OAI-PMH base URL (default export.arxiv.org/oai2 via the harvester)",
    )
    p.add_argument(
        "--no-resume", action="store_true",
        help="ignore any persisted mid-harvest cursor and start the window fresh",
    )
    p.add_argument(
        "--reset-state", action="store_true",
        help="legacy pure-OAI recovery: remove its JSON state files only when "
             "the DB has no authoritative bulk progress row",
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
    p.add_argument(
        "--persist-batch-size",
        type=int,
        default=None,
        help=(
            f"records per write-lock flush (default {DEFAULT_PERSIST_BATCH_SIZE} "
            "or ANTIEK_ARXIV_PERSIST_BATCH_SIZE). Smaller → more lock yields."
        ),
    )
    p.add_argument(
        "--max-lock-seconds",
        type=float,
        default=None,
        help=(
            f"attempted wall-clock cap holding DuckDB write.lock per session "
            f"(default {DEFAULT_MAX_LOCK_SECONDS} or ANTIEK_ARXIV_MAX_LOCK_SECONDS). "
            "A single slow record can exceed it; 0 disables the attempt."
        ),
    )
    p.add_argument(
        "--lock-yield-seconds",
        type=float,
        default=None,
        help=(
            f"sleep between write-lock sessions so uvicorn can acquire the flock "
            f"(default {DEFAULT_LOCK_YIELD_SECONDS} or ANTIEK_ARXIV_LOCK_YIELD_SECONDS)."
        ),
    )
    return p


def main(argv: Sequence[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    args = build_parser().parse_args(argv)
    if args.bulk_replay_from_zero and not args.bulk:
        print("error: --bulk-replay-from-zero requires --bulk", file=sys.stderr)
        return 2

    if args.reset_state:
        # Operator recovery: clear both checkpoint files BEFORE this run so the
        # same invocation then starts as a fresh backfill. Distinct from
        # --no-resume, which ignores only the mid-harvest cursor and keeps the
        # high-water mark.
        resolved_db = ensure_initialized(args.db_path or default_db_path())
        with whole_run_lock(resolved_db):
            with connect_write(
                resolved_db, purpose="arxiv_reset_authority_check", keepalive_s=0
            ) as con:
                if load_arxiv_bulk_progress(con) is not None:
                    print(
                        "error: --reset-state cannot reset DB-authoritative bulk progress",
                        file=sys.stderr,
                    )
                    return 2
            removed = reset_state_files()
        for p in removed:
            print(f"reset: removed {p}")
        if not removed:
            print("reset: no state files present (nothing to reset)")

    harvester = OaiPmhHarvester(
        throttle=ArxivThrottle(),
        metadata_prefix=args.metadata_prefix,
        base_url=args.base_url,
    )
    try:
        if args.bulk:
            # Resolve the snapshot (local path or free GCS download) BEFORE
            # opening the write lock / starting the harvest. A download
            # failure here leaves the high-water mark untouched.
            snapshot = args.bulk_snapshot or default_bulk_snapshot_path()
            try:
                snapshot = ensure_bulk_snapshot(
                    snapshot_path=snapshot,
                    force=args.bulk_force_download,
                )
            except FileNotFoundError as exc:
                print(
                    f"error: bulk snapshot unavailable ({exc}); "
                    "pass --bulk-snapshot PATH or drop --bulk to use pure OAI",
                    file=sys.stderr,
                )
                return 1
            print(f"bulk: streaming snapshot {snapshot}")
            result = run_bulk_sync(
                harvester=harvester,
                mode=args.mode,
                metadata_prefix=args.metadata_prefix,
                until_date=args.until_date,
                sync_state_path=default_sync_state_path(),
                bulk_snapshot_path=snapshot,
                resume=not args.no_resume,
                db_path=args.db_path,
                oai_tail=not args.bulk_only,
                persist_batch_size=args.persist_batch_size,
                max_lock_seconds=args.max_lock_seconds,
                lock_yield_seconds=args.lock_yield_seconds,
                replay_from_zero=args.bulk_replay_from_zero,
            )
        else:
            result = run_sync(
                harvester=harvester,
                mode=args.mode,
                metadata_prefix=args.metadata_prefix,
                until_date=args.until_date,
                sync_state_path=default_sync_state_path(),
                resume=not args.no_resume,
                db_path=args.db_path,
                persist_batch_size=args.persist_batch_size,
                max_lock_seconds=args.max_lock_seconds,
                lock_yield_seconds=args.lock_yield_seconds,
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
