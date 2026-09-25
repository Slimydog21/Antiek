"""DB-authoritative progress for the seekable arXiv JSONL snapshot."""

from __future__ import annotations

import contextlib
import fcntl
import hashlib
import json
import logging
import os
import stat
from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from uuid import uuid4

from acquisition.arxiv.bulk import BulkOaiLine
from acquisition.arxiv.oai_persist import persist_oai_record
from runtime.db_lock import LockedConnection, connect_write
from substrate.graph.schema import (
    ARXIV_BULK_PROGRESS_COLUMNS,
    load_arxiv_bulk_progress,
)
from substrate.schemas.documents import RightsTier

logger = logging.getLogger(__name__)


def _as_int(value: object) -> int:
    if type(value) is not int:
        raise ValueError("malformed arXiv progress integer")
    return value


def _as_date(value: object) -> date | None:
    if value is not None and type(value) is not date:
        raise ValueError("malformed arXiv progress date")
    return value


@dataclass(frozen=True)
class SnapshotIdentity:
    path: str
    sha256: str
    size: int
    device: int
    inode: int
    mtime_ns: int


def verify_snapshot(path: str) -> SnapshotIdentity:
    """Hash the entire plain file and reject a change during verification."""
    source = Path(path).resolve(strict=True)
    if source.suffix.lower() in {".gz", ".tar", ".zip", ".bz2", ".xz"}:
        raise ValueError("byte-offset resume requires a plain JSONL snapshot")
    before = source.stat()
    if not stat.S_ISREG(before.st_mode):
        raise ValueError("bulk snapshot must be a regular file")
    digest = hashlib.sha256()
    with source.open("rb") as fh:
        signature = fh.read(512)
        if (
            signature.startswith((b"\x1f\x8b", b"PK\x03\x04", b"BZh", b"\xfd7zXZ"))
            or signature[257:262] == b"ustar"
        ):
            raise ValueError("byte-offset resume requires a plain JSONL snapshot")
        digest.update(signature)
        for block in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(block)
        opened = os.fstat(fh.fileno())
    after = source.stat()
    if (
        (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)
        != (opened.st_dev, opened.st_ino, opened.st_size, opened.st_mtime_ns)
        or (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)
        != (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns)
    ):
        raise ValueError("bulk snapshot changed during verification")
    return SnapshotIdentity(
        path=str(source), sha256=digest.hexdigest(), size=before.st_size,
        device=before.st_dev, inode=before.st_ino, mtime_ns=before.st_mtime_ns,
    )


def assert_snapshot_unchanged(source: SnapshotIdentity) -> None:
    current = os.stat(source.path)
    if (current.st_dev, current.st_ino, current.st_size, current.st_mtime_ns) != (
        source.device, source.inode, source.size, source.mtime_ns,
    ):
        raise ValueError("bulk snapshot changed during ingestion")


def assert_physical_boundary(source: SnapshotIdentity, offset: int, line_count: int) -> None:
    if offset < 0 or offset > source.size:
        raise ValueError("bulk cursor outside verified snapshot")
    if line_count < 0 or (offset > 0 and line_count == 0):
        raise ValueError("bulk cursor physical line count is inconsistent")
    if offset == 0:
        return
    with open(source.path, "rb") as fh:
        fh.seek(offset - 1)
        previous = fh.read(1)
    if previous != b"\n" and offset != source.size:
        raise ValueError("bulk cursor is not a physical line boundary")
    if previous != b"\n" and offset == source.size:
        # EOF without a final LF is valid after the final line was read.
        # A nonzero byte cursor must have a persisted physical line count.
        return


@contextlib.contextmanager
def whole_run_lock(db_path: str) -> Iterator[None]:
    """Serialize timer, CLI and reset callers without holding DuckDB's flock."""
    lock_path = str(Path(db_path).resolve()) + ".arxiv_bulk_run.lock"
    descriptor = os.open(lock_path, os.O_CREAT | os.O_RDWR, 0o600)
    try:
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            os.lseek(descriptor, 0, os.SEEK_SET)
            holder = os.read(descriptor, 128).decode("ascii", errors="replace").strip()
            raise RuntimeError(f"arXiv bulk run already active ({holder or 'holder unknown'})") from exc
        holder_bytes = f"pid={os.getpid()} started={datetime.now().isoformat()}\n".encode("ascii")
        os.ftruncate(descriptor, 0)
        os.write(descriptor, holder_bytes)
        os.fsync(descriptor)
        yield
    finally:
        with contextlib.suppress(OSError):
            fcntl.flock(descriptor, fcntl.LOCK_UN)
        os.close(descriptor)
    # The lock file is never unlinked; a waiting process must see its inode.


def save_progress(con: LockedConnection, progress: dict[str, object]) -> None:
    columns = tuple(c for c in ARXIV_BULK_PROGRESS_COLUMNS if c != "updated_at")
    names = ", ".join(columns)
    placeholders = ", ".join("?" for _ in columns)
    updates = ", ".join(f"{name} = excluded.{name}" for name in columns if name != "stream_id")
    con.execute(
        f"INSERT INTO arxiv_bulk_progress ({names}) VALUES ({placeholders}) "
        f"ON CONFLICT (stream_id) DO UPDATE SET {updates}, updated_at = now()",
        [progress[name] for name in columns],
    )


def _legacy_high_water(path: str) -> str | None:
    try:
        raw = Path(path).read_text(encoding="utf-8")
    except FileNotFoundError:
        return None
    try:
        value = json.loads(raw)["last_successful_datestamp"]
    except (ValueError, TypeError, KeyError) as exc:
        raise ValueError("legacy arXiv high-water mirror is malformed") from exc
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError("legacy arXiv high-water mirror is malformed")
    if date.fromisoformat(value).isoformat() != value:
        raise ValueError("legacy arXiv high-water mirror is not an ISO date")
    return value


def open_generation(
    db_path: str, source: SnapshotIdentity, *, mode: str,
    until_date: str | None, metadata_prefix: str, sync_state_path: str,
    replay_from_zero: bool, tail_enabled: bool, resume: bool,
) -> dict[str, object]:
    """Create or validate a generation while the whole-run lock is held."""
    if mode not in {"incremental", "backfill"}:
        raise ValueError("unknown arXiv sync mode")
    until = date.fromisoformat(until_date) if until_date is not None else None
    if until is not None and until.isoformat() != until_date:
        raise ValueError("arXiv until bound must use YYYY-MM-DD")
    with connect_write(db_path, purpose="arxiv_bulk_generation", keepalive_s=0) as con:
        current = load_arxiv_bulk_progress(con)
        try:
            legacy = _legacy_high_water(sync_state_path)
        except ValueError:
            if current is None:
                raise
            logger.warning("arXiv JSON mirror malformed; DB progress remains authoritative")
            legacy = None
        if current is None and legacy is not None and not replay_from_zero:
            raise ValueError(
                "legacy JSON high-water exists without a DB cursor; "
                "operator must select --bulk-replay-from-zero"
            )
        if current is not None and replay_from_zero:
            raise ValueError("explicit replay requires a missing DB cursor")
        if current is not None:
            completed = _as_date(current["completed_high_water"])
            completed_text = completed.isoformat() if completed is not None else None
            if legacy != completed_text:
                logger.warning("arXiv JSON mirror disagrees with DB completed high-water")
        if current is not None and current["phase"] in {"bulk", "tail"}:
            if not resume:
                raise ValueError("--no-resume cannot discard an incomplete DB cursor")
            expected = {
                "source_sha256": source.sha256,
                "source_size_bytes": source.size,
                "source_format": "jsonl",
                "source_encoding": "utf-8",
                "mode": mode,
                "tail_enabled": tail_enabled,
                "until_date": until,
                "metadata_prefix": metadata_prefix,
            }
            if any(current[name] != value for name, value in expected.items()):
                raise ValueError("incomplete arXiv cursor source or window mismatch")
            expected_from = (
                current["completed_high_water"] if mode == "incremental" else None
            )
            if current["from_date"] != expected_from:
                raise ValueError("incomplete arXiv cursor lower bound mismatch")
            assert_physical_boundary(
                source, _as_int(current["next_byte_offset"]),
                _as_int(current["physical_line_count"]),
            )
            return current

        completed_high_water = _as_date(current["completed_high_water"]) if current else None
        from_date = completed_high_water if mode == "incremental" else None
        generation: dict[str, object] = {
            "stream_id": "arxiv_bulk", "cursor_schema_version": 1,
            "parser_version": 1, "generation_id": str(uuid4()),
            "source_sha256": source.sha256, "source_size_bytes": source.size,
            "source_format": "jsonl", "source_encoding": "utf-8",
            "source_path": source.path, "mode": mode,
            "tail_enabled": tail_enabled, "from_date": from_date,
            "until_date": until, "metadata_prefix": metadata_prefix,
            "phase": "bulk", "next_byte_offset": 0,
            "physical_line_count": 0, "selected_record_count": 0,
            "bulk_t1_events": 0, "bulk_t2_events": 0, "bulk_t3_events": 0,
            "bulk_ambiguous_events": 0, "bulk_deleted_events": 0,
            "bulk_max_datestamp": None,
            "completed_high_water": completed_high_water,
            "completed_generation_id": current["completed_generation_id"] if current else None,
            "completed_at": current["completed_at"] if current else None,
            "completed_bulk_sha256": current["completed_bulk_sha256"] if current else None,
            "completed_tail_bound": current["completed_tail_bound"] if current else None,
            "completed_census_json": current["completed_census_json"] if current else None,
        }
        if from_date is not None and until is not None and from_date > until:
            raise ValueError("arXiv incremental lower bound exceeds until date")
        with con.transaction():
            save_progress(con, generation)
        return generation


def commit_bulk_slice(
    db_path: str, lines: Sequence[BulkOaiLine], progress: dict[str, object],
    *, max_lock_s: float,
) -> tuple[int, dict[str, object], dict[str, int]]:
    """Commit a bounded prefix of physical lines and its cursor together."""
    if not lines:
        return 0, progress, {"inserted": 0, "updated": 0, "skipped_deleted": 0}
    next_progress = dict(progress)
    tally = {"inserted": 0, "updated": 0, "skipped_deleted": 0}
    consumed = 0
    import time

    with connect_write(db_path, purpose="arxiv_bulk_slice", keepalive_s=0) as con:
        start = time.monotonic()
        with con.transaction():
            for line in lines:
                record = line.record
                if record is not None:
                    next_progress["selected_record_count"] = _as_int(next_progress["selected_record_count"]) + 1
                    try:
                        stamp = date.fromisoformat(record.datestamp) if record.datestamp else None
                    except ValueError:
                        stamp = None  # accepted legacy record; unusable high-water
                    prior_max = _as_date(next_progress["bulk_max_datestamp"])
                    if stamp is not None and (prior_max is None or stamp > prior_max):
                        next_progress["bulk_max_datestamp"] = stamp
                    if record.deleted:
                        next_progress["bulk_deleted_events"] = _as_int(next_progress["bulk_deleted_events"]) + 1
                        tally["skipped_deleted"] += 1
                    else:
                        key = {
                            RightsTier.T1_REDISTRIBUTABLE: "bulk_t1_events",
                            RightsTier.T2_NON_COMMERCIAL: "bulk_t2_events",
                            RightsTier.T3_DEFAULT_UNKNOWN: "bulk_t3_events",
                        }[record.tier]
                        next_progress[key] = _as_int(next_progress[key]) + 1
                        if record.tier == RightsTier.T3_DEFAULT_UNKNOWN and not record.license_uri:
                            next_progress["bulk_ambiguous_events"] = _as_int(next_progress["bulk_ambiguous_events"]) + 1
                        if persist_oai_record(con, record):
                            tally["inserted"] += 1
                        else:
                            tally["updated"] += 1
                next_progress["next_byte_offset"] = line.end_offset
                next_progress["physical_line_count"] = _as_int(next_progress["physical_line_count"]) + 1
                consumed += 1
                if max_lock_s > 0 and time.monotonic() - start >= max_lock_s:
                    break
            save_progress(con, next_progress)
    return consumed, next_progress, tally


def set_phase(db_path: str, progress: dict[str, object], phase: str) -> dict[str, object]:
    next_progress = {**progress, "phase": phase}
    with (
        connect_write(db_path, purpose="arxiv_bulk_phase", keepalive_s=0) as con,
        con.transaction(),
    ):
        save_progress(con, next_progress)
    return next_progress
