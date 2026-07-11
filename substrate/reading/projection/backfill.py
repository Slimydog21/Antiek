"""Deterministic, resumable PDF-to-HTML projection backfill."""

from __future__ import annotations

import hashlib
import json
import math
import os
import time
from collections.abc import Callable
from contextlib import suppress
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Literal

from runtime.db_lock import connect_read, connect_write
from substrate.contracts.html_projection import HtmlProjectionContract, derive_projection_id
from substrate.reading.projection.pipeline import (
    PreparedProjection,
    finalize_projection,
    persist_prepared_projection,
    prepare_projection,
)
from substrate.reading.projection.source_catalog import (
    ProjectionSourceCandidate,
    ProjectionSourceCatalog,
    UnresolvedProjectionSource,
)
from substrate.reading.projection.store import ProjectionStore

CONVERTER_ID = "pypdf"
CONVERTER_VERSION = "1"
SANITIZER_POLICY = "born-antiek"
SANITIZER_VERSION = "1"
SCHEMA_VERSION = "1"
DEFAULT_LEASE_SECONDS = 300.0

ItemStatus = Literal["pending", "processing", "ready", "ocr_required", "failed"]
ErrorCode = Literal[
    "conversion_failed",
    "identity_conflict",
    "object_hash_conflict",
    "source_read_failed",
    "persistence_failed",
]


@dataclass(frozen=True)
class BackfillItemRecord:
    document_id: str
    projection_id: str
    source_asset_id: str
    source_bytes: int
    outcome: str
    expected_html_bytes: int = 0
    error_code: str | None = None
    object_key: str | None = None


@dataclass(frozen=True)
class Lease:
    owner: str
    expires_at: float


@dataclass(frozen=True)
class UnresolvedReasonRecord:
    document_id: str
    reason_code: str


@dataclass(frozen=True)
class RollbackScope:
    run_id: str
    item_rows: tuple[str, ...]
    object_keys: tuple[str, ...]
    automatic: bool = False


@dataclass(frozen=True)
class BackfillReport:
    schema_version: str
    dry_run: bool
    plan_id: str
    items: tuple[BackfillItemRecord, ...]
    candidates: int
    already_ready: int
    would_convert: int
    ocr_required: int
    conversion_failed: int
    unresolved: int
    source_bytes: int
    expected_html_bytes: int
    unresolved_reasons: tuple[UnresolvedReasonRecord, ...]
    rollback_scope: RollbackScope

    def canonical_json(self) -> str:
        return json.dumps(asdict(self), sort_keys=True, separators=(",", ":"))

    def canonical_json_bytes(self) -> bytes:
        return self.canonical_json().encode("utf-8")


def queued_contract(candidate: ProjectionSourceCandidate) -> HtmlProjectionContract:
    identity = {
        "source_asset_id": candidate.source_asset_id,
        "source_document_id": candidate.document_id,
        "source_sha256": candidate.sha256,
        "converter_id": CONVERTER_ID,
        "converter_version": CONVERTER_VERSION,
        "sanitizer_policy": SANITIZER_POLICY,
        "sanitizer_version": SANITIZER_VERSION,
    }
    return HtmlProjectionContract(
        **identity, projection_id=derive_projection_id(**identity), status="queued"
    )


def backfill_projections(
    *,
    db_path: str | Path,
    source_object_root: str | Path,
    html_object_root: str | Path,
    apply: bool = False,
    worker_id: str = "html-projection-backfill",
    clock: Callable[[], float] = time.time,
    lease_seconds: float = DEFAULT_LEASE_SECONDS,
    prepare: Callable[[HtmlProjectionContract, bytes], PreparedProjection] = prepare_projection,
) -> BackfillReport:
    """Plan or apply the backfill. Without ``apply=True`` this is strictly read-only."""
    if not worker_id.strip():
        raise ValueError("worker_id must be nonempty")
    if not math.isfinite(lease_seconds) or lease_seconds <= 0:
        raise ValueError("lease_seconds must be finite and greater than zero")
    db = str(db_path)
    with connect_read(db) as con:
        records = ProjectionSourceCatalog(con, source_object_root).list()
        existing = _existing_projections(con)

    unresolved = tuple(
        UnresolvedReasonRecord(record.document_id, record.reason_code)
        for record in records
        if isinstance(record, UnresolvedProjectionSource)
    )
    candidates = tuple(
        record for record in records if isinstance(record, ProjectionSourceCandidate)
    )
    contracts = tuple((candidate, queued_contract(candidate)) for candidate in candidates)
    plan_id = _plan_id(contracts, unresolved)
    if apply:
        _ensure_and_seed(db, plan_id, contracts)

    items: list[BackfillItemRecord] = []
    for candidate, queued in contracts:
        stored = existing.get(queued.projection_id)
        if stored is not None:
            if stored.identity() != queued.identity():
                items.append(_item(candidate, queued, "failed", error="identity_conflict"))
                if apply:
                    _reconcile(
                        db, plan_id, queued.projection_id, "failed", "identity_conflict", None
                    )
                continue
            if stored.status == "ready":
                items.append(_item(candidate, queued, "already_ready", stored.hosted_html_locator))
                if apply:
                    _reconcile(
                        db, plan_id, queued.projection_id, "ready", None, stored.hosted_html_locator
                    )
                continue

        lease: Lease | None = None
        if apply:
            now = float(clock())
            if not math.isfinite(now):
                raise ValueError("clock must return a finite value")
            lease = _claim(db, plan_id, queued.projection_id, worker_id, now, lease_seconds)
        if apply and lease is None:
            row = _item_state(db, plan_id, queued.projection_id)
            outcome = "already_ready" if row[0] == "ready" else row[0]
            items.append(_item(candidate, queued, outcome, row[2], error=row[1]))
            continue
        try:
            source = candidate.source_path.read_bytes()
        except OSError:
            items.append(_item(candidate, queued, "failed", error="source_read_failed"))
            if apply:
                assert lease is not None
                if not _terminal(
                    db, plan_id, queued.projection_id, lease, "failed", "source_read_failed", None
                ):
                    items[-1] = _checkpoint_item(candidate, queued, db, plan_id)
            continue
        try:
            prepared = prepare(queued, source)
        except Exception:
            items.append(_item(candidate, queued, "failed", error="conversion_failed"))
            if apply:
                assert lease is not None
                if not _terminal(
                    db, plan_id, queued.projection_id, lease, "failed", "conversion_failed", None
                ):
                    items[-1] = _checkpoint_item(candidate, queued, db, plan_id)
            continue
        if prepared.terminal_status != "ready":
            outcome = prepared.terminal_status
            error = "conversion_failed" if outcome == "failed" else None
            items.append(_item(candidate, queued, outcome, error=error))
            if apply:
                assert lease is not None
                try:
                    persisted = _persist_terminal(
                        db, plan_id, queued, prepared, lease, outcome, error
                    )
                except Exception:
                    persisted = _terminal(
                        db,
                        plan_id,
                        queued.projection_id,
                        lease,
                        "failed",
                        "persistence_failed",
                        None,
                    )
                    items[-1] = (
                        _item(candidate, queued, "failed", error="persistence_failed")
                        if persisted
                        else _checkpoint_item(candidate, queued, db, plan_id)
                    )
                else:
                    if not persisted:
                        items[-1] = _checkpoint_item(candidate, queued, db, plan_id)
            continue
        assert prepared.html_bytes is not None
        key = f"html-projections/{queued.projection_id}.html"
        item = _item(
            candidate,
            queued,
            "would_convert" if not apply else "ready",
            key,
            html_bytes=len(prepared.html_bytes),
        )
        if not apply:
            items.append(item)
            continue
        finalized = finalize_projection(prepared, key)
        assert lease is not None
        # Object publication is deliberately outside the DuckDB writer lock.
        # A stale worker can at worst publish the same deterministic bytes;
        # the fenced transaction below decides whether it may publish state.
        publish_error = _publish(Path(html_object_root), key, prepared.html_bytes)
        if publish_error:
            persisted = _terminal(
                db, plan_id, queued.projection_id, lease, "failed", publish_error, None
            )
            items.append(
                _item(candidate, queued, "failed", error=publish_error)
                if persisted
                else _checkpoint_item(candidate, queued, db, plan_id)
            )
            continue
        try:
            persisted = _persist_terminal(db, plan_id, queued, finalized, lease, "ready", None, key)
        except Exception:
            persisted = _terminal(
                db,
                plan_id,
                queued.projection_id,
                lease,
                "failed",
                "persistence_failed",
                None,
            )
            items.append(
                _item(candidate, queued, "failed", error="persistence_failed")
                if persisted
                else _checkpoint_item(candidate, queued, db, plan_id)
            )
        else:
            items.append(item if persisted else _checkpoint_item(candidate, queued, db, plan_id))

    return _report(plan_id, not apply, items, unresolved)


def plan_backfill(**kwargs: Any) -> BackfillReport:
    return backfill_projections(**kwargs, apply=False)


def apply_backfill(**kwargs: Any) -> BackfillReport:
    return backfill_projections(**kwargs, apply=True)


run_projection_backfill = backfill_projections
dry_run_backfill = plan_backfill


def _existing_projections(con: Any) -> dict[str, HtmlProjectionContract]:
    tables = {str(row[0]) for row in con.execute("SHOW TABLES").fetchall()}
    if "html_projections" not in tables:
        return {}
    return {p.projection_id: p for p in ProjectionStore(con).list()}


def _plan_id(
    contracts: tuple[tuple[ProjectionSourceCandidate, HtmlProjectionContract], ...],
    unresolved: tuple[UnresolvedReasonRecord, ...],
) -> str:
    payload = {
        "schema_version": SCHEMA_VERSION,
        "projection_ids": sorted(contract.projection_id for _, contract in contracts),
        "unresolved": [asdict(item) for item in sorted(unresolved, key=lambda x: x.document_id)],
    }
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return f"hpb-{hashlib.sha256(raw).hexdigest()}"


def _ensure_and_seed(
    db: str,
    run_id: str,
    contracts: tuple[tuple[ProjectionSourceCandidate, HtmlProjectionContract], ...],
) -> None:
    with connect_write(db, purpose="html_projection_backfill.seed") as con:
        con.execute("""
            CREATE TABLE IF NOT EXISTS html_projection_backfill_runs (
                run_id TEXT PRIMARY KEY, schema_version TEXT NOT NULL, plan_json JSON NOT NULL
            )
        """)
        con.execute("""
            CREATE TABLE IF NOT EXISTS html_projection_backfill_items (
                run_id TEXT NOT NULL, projection_id TEXT NOT NULL, document_id TEXT NOT NULL,
                status TEXT NOT NULL CHECK(status IN ('pending','processing','ready','ocr_required','failed')),
                attempt_count INTEGER NOT NULL DEFAULT 0, lease_owner TEXT,
                lease_expires_at DOUBLE, error_code TEXT, object_key TEXT,
                CHECK(attempt_count >= 0),
                CHECK((status = 'processing' AND lease_owner IS NOT NULL AND lease_expires_at IS NOT NULL)
                      OR (status <> 'processing' AND lease_owner IS NULL AND lease_expires_at IS NULL)),
                CHECK(error_code IS NULL OR error_code IN ('conversion_failed','identity_conflict',
                      'object_hash_conflict','source_read_failed','persistence_failed')),
                PRIMARY KEY(run_id, projection_id)
            )
        """)
        plan_json = json.dumps(
            [contract.projection_id for _, contract in contracts], separators=(",", ":")
        )
        con.execute(
            "INSERT OR IGNORE INTO html_projection_backfill_runs VALUES (?, ?, ?)",
            [run_id, SCHEMA_VERSION, plan_json],
        )
        for candidate, contract in contracts:
            con.execute(
                "INSERT OR IGNORE INTO html_projection_backfill_items "
                "(run_id, projection_id, document_id, status) VALUES (?, ?, ?, 'pending')",
                [run_id, contract.projection_id, candidate.document_id],
            )


def _claim(
    db: str, run_id: str, projection_id: str, owner: str, now: float, lease_seconds: float
) -> Lease | None:
    with connect_write(db, purpose="html_projection_backfill.claim") as con:
        lease = Lease(owner, now + lease_seconds)
        claimed = con.execute(
            "UPDATE html_projection_backfill_items SET status='processing', attempt_count=attempt_count+1, "
            "lease_owner=?, lease_expires_at=?, error_code=NULL "
            "WHERE run_id=? AND projection_id=? "
            "AND (status IN ('pending','failed') "
            "OR (status='processing' AND lease_expires_at<=?)) RETURNING projection_id",
            [lease.owner, lease.expires_at, run_id, projection_id, now],
        ).fetchone()
        return lease if claimed is not None else None


def _persist_terminal(
    db: str,
    run_id: str,
    queued: HtmlProjectionContract,
    prepared: PreparedProjection,
    lease: Lease,
    status: str,
    error: str | None,
    key: str | None = None,
) -> bool:
    with connect_write(db, purpose="html_projection_backfill.persist") as con:
        con.execute("BEGIN TRANSACTION")
        try:
            if not _owns_lease(con, run_id, queued.projection_id, lease):
                con.execute("ROLLBACK")
                return False
            store = ProjectionStore(con)
            store.ensure_tables()
            try:
                current = store.load(queued.projection_id)
            except KeyError:
                current = None
            if current is not None and current.status == "failed":
                store.transition(queued)
            persist_prepared_projection(store, queued, prepared)
            _terminal_sql(con, run_id, queued.projection_id, lease, status, error, key)
            con.execute("COMMIT")
            return True
        except Exception:
            con.execute("ROLLBACK")
            raise


def _terminal(
    db: str,
    run_id: str,
    projection_id: str,
    lease: Lease,
    status: str,
    error: str | None,
    key: str | None,
) -> bool:
    with connect_write(db, purpose="html_projection_backfill.terminal") as con:
        if not _owns_lease(con, run_id, projection_id, lease):
            return False
        _terminal_sql(con, run_id, projection_id, lease, status, error, key)
        return True


def _reconcile(
    db: str, run_id: str, projection_id: str, status: str, error: str | None, key: str | None
) -> bool:
    with connect_write(db, purpose="html_projection_backfill.reconcile") as con:
        con.execute(
            "UPDATE html_projection_backfill_items SET status=?, lease_owner=NULL, "
            "lease_expires_at=NULL, error_code=?, object_key=? WHERE run_id=? AND projection_id=? "
            "AND status IN ('pending','failed')",
            [status, error, key, run_id, projection_id],
        )
        row = con.execute(
            "SELECT status,error_code,object_key FROM html_projection_backfill_items "
            "WHERE run_id=? AND projection_id=?",
            [run_id, projection_id],
        ).fetchone()
        return row == (status, error, key)


def _terminal_sql(
    con: Any,
    run_id: str,
    projection_id: str,
    lease: Lease,
    status: str,
    error: str | None,
    key: str | None,
) -> None:
    # Kept as a second CAS even though callers verify under the same transaction.
    con.execute(
        "UPDATE html_projection_backfill_items SET status=?, lease_owner=NULL, "
        "lease_expires_at=NULL, error_code=?, object_key=? WHERE run_id=? AND projection_id=? "
        "AND status='processing' AND lease_owner=? AND lease_expires_at=?",
        [status, error, key, run_id, projection_id, lease.owner, lease.expires_at],
    )


def _owns_lease(con: Any, run_id: str, projection_id: str, lease: Lease) -> bool:
    row = con.execute(
        "SELECT count(*) FROM html_projection_backfill_items WHERE run_id=? AND projection_id=? "
        "AND status='processing' AND lease_owner=? AND lease_expires_at=?",
        [run_id, projection_id, lease.owner, lease.expires_at],
    ).fetchone()
    return row is not None and row[0] == 1


def _item_state(db: str, run_id: str, projection_id: str) -> tuple[str, str | None, str | None]:
    with connect_read(db) as con:
        row = con.execute(
            "SELECT status,error_code,object_key FROM html_projection_backfill_items "
            "WHERE run_id=? AND projection_id=?",
            [run_id, projection_id],
        ).fetchone()
    assert row is not None
    return str(row[0]), row[1], row[2]


def _checkpoint_item(
    candidate: ProjectionSourceCandidate, queued: HtmlProjectionContract, db: str, run_id: str
) -> BackfillItemRecord:
    status, error, key = _item_state(db, run_id, queued.projection_id)
    return _item(
        candidate, queued, "already_ready" if status == "ready" else status, key, error=error
    )


def _publish(root: Path, key: str, data: bytes) -> ErrorCode | None:
    final = root.joinpath(*key.split("/"))
    final.parent.mkdir(parents=True, exist_ok=True)
    expected = hashlib.sha256(data).hexdigest()
    if final.exists():
        return None if _hash_file(final) == expected else "object_hash_conflict"
    temp = final.with_name(f".{final.name}.{expected}.tmp")
    try:
        with temp.open("xb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp, final)
        try:
            descriptor = os.open(final.parent, os.O_RDONLY)
            try:
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
        except OSError:
            pass
    except FileExistsError:
        if final.exists() and _hash_file(final) == expected:
            return None
        return "object_hash_conflict"
    except OSError:
        return "persistence_failed"
    finally:
        with suppress(FileNotFoundError):
            temp.unlink()
    return None


def _hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _item(
    candidate: ProjectionSourceCandidate,
    queued: HtmlProjectionContract,
    outcome: str,
    object_key: str | None = None,
    *,
    error: str | None = None,
    html_bytes: int = 0,
) -> BackfillItemRecord:
    return BackfillItemRecord(
        candidate.document_id,
        queued.projection_id,
        candidate.source_asset_id,
        candidate.byte_size,
        outcome,
        html_bytes,
        error,
        object_key,
    )


def _report(
    plan_id: str,
    dry_run: bool,
    items: list[BackfillItemRecord],
    unresolved: tuple[UnresolvedReasonRecord, ...],
) -> BackfillReport:
    ordered = tuple(sorted(items, key=lambda item: (item.projection_id, item.document_id)))
    outcomes = [item.outcome for item in ordered]
    owned = tuple(item.projection_id for item in ordered if item.outcome != "already_ready")
    keys = tuple(
        sorted(
            item.object_key
            for item in ordered
            if item.object_key and item.outcome != "already_ready"
        )
    )
    return BackfillReport(
        SCHEMA_VERSION,
        dry_run,
        plan_id,
        ordered,
        len(ordered),
        outcomes.count("already_ready"),
        outcomes.count("would_convert") if dry_run else outcomes.count("ready"),
        outcomes.count("ocr_required"),
        outcomes.count("failed"),
        len(unresolved),
        sum(item.source_bytes for item in ordered),
        sum(item.expected_html_bytes for item in ordered),
        tuple(sorted(unresolved, key=lambda item: (item.document_id, item.reason_code))),
        RollbackScope(plan_id, owned, keys),
    )


__all__ = [
    "BackfillItemRecord",
    "BackfillReport",
    "RollbackScope",
    "UnresolvedReasonRecord",
    "apply_backfill",
    "backfill_projections",
    "dry_run_backfill",
    "plan_backfill",
    "queued_contract",
    "run_projection_backfill",
]
