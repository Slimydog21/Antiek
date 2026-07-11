"""Durable owner-scoped Midnight Oil job authority with atomic CAS.

SQLite is used here deliberately, not as a convenience default. This adapter's
hard requirement is one durable compare-and-set transition proven across
independent connections after restart. SQLite gives that with a real
transactional file, serialized write transactions, and a single atomic UPDATE
predicate over version/state/operation. A process-local mutex would not survive
restart and would not serialize separate processes, so it would not satisfy the
authority contract.
"""

from __future__ import annotations

import json
import os
import sqlite3
from collections.abc import Mapping
from contextlib import closing
from dataclasses import replace
from decimal import ROUND_FLOOR, Decimal, InvalidOperation
from typing import Any, Final, cast

from .job import (
    MidnightOilJob,
    MidnightOilJobAuthority,
    OperationState,
    _job_from_row,
    _job_to_row,
    _validate_authority,
    _validate_authority_transition,
    _validate_cents,
    _validate_identifier,
    _validate_integer,
    _validate_job_status,
    _validate_operation_state,
    _validate_timestamp,
)

_TABLE_NAME: Final = "midnight_oil_jobs"
_SCHEMA_VERSION: Final = 2
_LEGACY_OWNER_USER_ID: Final = "__operator__"
_CREATE_TABLE_SQL: Final = f"""
CREATE TABLE IF NOT EXISTS {_TABLE_NAME} (
    owner_user_id TEXT NOT NULL,
    job_id TEXT NOT NULL,
    goals_json TEXT NOT NULL,
    duration_minutes INTEGER NOT NULL,
    model_id TEXT,
    recommended_price_ceiling_usd REAL NOT NULL,
    status TEXT NOT NULL,
    approved_ceiling_usd REAL,
    spent_usd REAL NOT NULL DEFAULT 0,
    asset_id TEXT,
    spawn_ids_json TEXT NOT NULL,
    completed_step_keys_json TEXT NOT NULL DEFAULT '[]',
    returned_step_keys_json TEXT NOT NULL DEFAULT '[]',
    started_at_ms INTEGER,
    elapsed_ms INTEGER NOT NULL DEFAULT 0,
    force_below_recommended INTEGER NOT NULL DEFAULT 0,
    notes TEXT NOT NULL DEFAULT '',
    research_tier TEXT NOT NULL,
    fanout_depth INTEGER NOT NULL DEFAULT 3,
    state_version INTEGER NOT NULL DEFAULT 0,
    approved_ceiling_cents INTEGER,
    consent_granted_by_user_id TEXT,
    consent_recorded_at_ms INTEGER,
    consent_note TEXT NOT NULL DEFAULT '',
    operation_state TEXT NOT NULL DEFAULT 'awaiting_approval',
    operation_id TEXT,
    dispatch_claimed_at_ms INTEGER,
    dispatch_started_at_ms INTEGER,
    dispatch_completed_at_ms INTEGER,
    PRIMARY KEY (owner_user_id, job_id)
)
"""
_ALL_COLUMNS: Final[tuple[str, ...]] = (
    "owner_user_id",
    "job_id",
    "goals_json",
    "duration_minutes",
    "model_id",
    "recommended_price_ceiling_usd",
    "status",
    "approved_ceiling_usd",
    "spent_usd",
    "asset_id",
    "spawn_ids_json",
    "completed_step_keys_json",
    "returned_step_keys_json",
    "started_at_ms",
    "elapsed_ms",
    "force_below_recommended",
    "notes",
    "research_tier",
    "fanout_depth",
    "state_version",
    "approved_ceiling_cents",
    "consent_granted_by_user_id",
    "consent_recorded_at_ms",
    "consent_note",
    "operation_state",
    "operation_id",
    "dispatch_claimed_at_ms",
    "dispatch_started_at_ms",
    "dispatch_completed_at_ms",
)
_ADD_COLUMN_SQL: Final[dict[str, str]] = {
    "owner_user_id": (
        "ALTER TABLE midnight_oil_jobs "
        "ADD COLUMN owner_user_id TEXT NOT NULL DEFAULT '__operator__'"
    ),
    "goals_json": (
        "ALTER TABLE midnight_oil_jobs ADD COLUMN goals_json TEXT NOT NULL DEFAULT '[]'"
    ),
    "spawn_ids_json": (
        "ALTER TABLE midnight_oil_jobs ADD COLUMN spawn_ids_json TEXT NOT NULL DEFAULT '[]'"
    ),
    "completed_step_keys_json": (
        "ALTER TABLE midnight_oil_jobs "
        "ADD COLUMN completed_step_keys_json TEXT NOT NULL DEFAULT '[]'"
    ),
    "returned_step_keys_json": (
        "ALTER TABLE midnight_oil_jobs "
        "ADD COLUMN returned_step_keys_json TEXT NOT NULL DEFAULT '[]'"
    ),
    "research_tier": (
        "ALTER TABLE midnight_oil_jobs ADD COLUMN research_tier TEXT NOT NULL DEFAULT 'deep'"
    ),
    "fanout_depth": (
        "ALTER TABLE midnight_oil_jobs ADD COLUMN fanout_depth INTEGER NOT NULL DEFAULT 3"
    ),
    "state_version": (
        "ALTER TABLE midnight_oil_jobs ADD COLUMN state_version INTEGER NOT NULL DEFAULT 0"
    ),
    "approved_ceiling_cents": (
        "ALTER TABLE midnight_oil_jobs ADD COLUMN approved_ceiling_cents INTEGER"
    ),
    "consent_granted_by_user_id": (
        "ALTER TABLE midnight_oil_jobs ADD COLUMN consent_granted_by_user_id TEXT"
    ),
    "consent_recorded_at_ms": (
        "ALTER TABLE midnight_oil_jobs ADD COLUMN consent_recorded_at_ms INTEGER"
    ),
    "consent_note": (
        "ALTER TABLE midnight_oil_jobs ADD COLUMN consent_note TEXT NOT NULL DEFAULT ''"
    ),
    "operation_state": (
        "ALTER TABLE midnight_oil_jobs "
        "ADD COLUMN operation_state TEXT NOT NULL DEFAULT 'awaiting_approval'"
    ),
    "operation_id": "ALTER TABLE midnight_oil_jobs ADD COLUMN operation_id TEXT",
    "dispatch_claimed_at_ms": (
        "ALTER TABLE midnight_oil_jobs ADD COLUMN dispatch_claimed_at_ms INTEGER"
    ),
    "dispatch_started_at_ms": (
        "ALTER TABLE midnight_oil_jobs ADD COLUMN dispatch_started_at_ms INTEGER"
    ),
    "dispatch_completed_at_ms": (
        "ALTER TABLE midnight_oil_jobs ADD COLUMN dispatch_completed_at_ms INTEGER"
    ),
}
_UNSET: Final = object()


def _legacy_usd_to_cents_floor(value: object | None) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (float, int, str)):
        raise ValueError("approved_ceiling_usd must be a legacy numeric display value")
    try:
        cents = (Decimal(str(value)) * 100).to_integral_value(rounding=ROUND_FLOOR)
    except InvalidOperation as exc:
        raise ValueError("approved_ceiling_usd must be a finite USD amount") from exc
    return cast(
        int | None,
        _validate_cents(int(cents), field_name="approved_ceiling_cents", allow_none=True),
    )


def _operation_state_from_status(status: object) -> OperationState:
    status_text = str(status or "awaiting_approval")
    mapping: dict[str, OperationState] = {
        "draft": "awaiting_approval",
        "awaiting_approval": "awaiting_approval",
        "approved": "approved",
        "running": "dispatch_started",
        "complete": "dispatch_finished",
        "timed_out": "dispatch_finished",
        "budget_halted": "failed_closed",
        "failed": "failed_closed",
    }
    return mapping.get(status_text, "failed_closed")


def _json_dump(items: list[str]) -> str:
    return json.dumps(items, separators=(",", ":"), ensure_ascii=True)


def _decode_string_array(value: object, *, field_name: str) -> list[str]:
    if not isinstance(value, str):
        raise ValueError(f"{field_name} must be JSON text")
    try:
        decoded = json.loads(value)
    except json.JSONDecodeError as exc:
        raise ValueError(f"{field_name} must contain valid JSON") from exc
    if not isinstance(decoded, list) or any(not isinstance(item, str) for item in decoded):
        raise ValueError(f"{field_name} must be an array of strings")
    return decoded


def _row_to_job(row: Mapping[str, Any]) -> MidnightOilJob:
    _validate_identifier(row["owner_user_id"], field_name="owner_user_id")
    _validate_identifier(row["job_id"], field_name="job_id")
    row_dict: dict[str, Any] = {
        "job_id": row["job_id"],
        "goals": _decode_string_array(row["goals_json"], field_name="goals_json"),
        "duration_minutes": row["duration_minutes"],
        "model_id": row["model_id"],
        "recommended_price_ceiling_usd": row["recommended_price_ceiling_usd"],
        "status": _validate_job_status(row["status"]),
        "approved_ceiling_usd": row["approved_ceiling_usd"],
        "spent_usd": row["spent_usd"],
        "asset_id": row["asset_id"],
        "spawn_ids": _decode_string_array(row["spawn_ids_json"], field_name="spawn_ids_json"),
        "completed_step_keys": _decode_string_array(
            row["completed_step_keys_json"], field_name="completed_step_keys_json"
        ),
        "returned_step_keys": _decode_string_array(
            row["returned_step_keys_json"], field_name="returned_step_keys_json"
        ),
        "started_at_ms": row["started_at_ms"],
        "elapsed_ms": row["elapsed_ms"],
        "force_below_recommended": bool(row["force_below_recommended"]),
        "notes": row["notes"],
        "research_tier": row["research_tier"],
        "fanout_depth": row["fanout_depth"],
        "owner_user_id": row["owner_user_id"],
        "state_version": row["state_version"],
        "approved_ceiling_cents": row["approved_ceiling_cents"],
        "consent_granted_by_user_id": row["consent_granted_by_user_id"],
        "consent_recorded_at_ms": row["consent_recorded_at_ms"],
        "consent_note": row["consent_note"],
        "operation_state": row["operation_state"],
        "operation_id": row["operation_id"],
        "dispatch_claimed_at_ms": row["dispatch_claimed_at_ms"],
        "dispatch_started_at_ms": row["dispatch_started_at_ms"],
        "dispatch_completed_at_ms": row["dispatch_completed_at_ms"],
    }
    return _job_from_row(row_dict)


def _job_to_sql_row(owner_user_id: str, job: MidnightOilJob) -> dict[str, Any]:
    authority = job.authority
    if authority is None:
        raise ValueError("job.authority is required for durable owner-scoped storage")
    if authority.owner_user_id != owner_user_id:
        raise ValueError("job.authority.owner_user_id must match the owner scope")
    _validate_identifier(owner_user_id, field_name="owner_user_id")
    _validate_identifier(job.job_id, field_name="job_id")
    _validate_authority(authority)
    status = _validate_job_status(job.status)
    approved_ceiling_cents = _validate_cents(
        authority.approved_ceiling_cents,
        field_name="approved_ceiling_cents",
        allow_none=True,
    )
    state_version = cast(
        int,
        _validate_integer(authority.state_version, field_name="state_version", allow_none=False),
    )
    operation_state = _validate_operation_state(authority.operation_state)
    dispatch_claimed_at_ms = _validate_timestamp(
        authority.dispatch_claimed_at_ms,
        field_name="dispatch_claimed_at_ms",
    )
    dispatch_started_at_ms = _validate_timestamp(
        authority.dispatch_started_at_ms,
        field_name="dispatch_started_at_ms",
    )
    dispatch_completed_at_ms = _validate_timestamp(
        authority.dispatch_completed_at_ms,
        field_name="dispatch_completed_at_ms",
    )
    row = _job_to_row(job)
    approved_ceiling_usd = row.get("approved_ceiling_usd")
    if approved_ceiling_usd is None and approved_ceiling_cents is not None:
        approved_ceiling_usd = approved_ceiling_cents / 100
    return {
        "owner_user_id": owner_user_id,
        "job_id": row["job_id"],
        "goals_json": _json_dump(cast(list[str], row["goals"])),
        "duration_minutes": int(row["duration_minutes"]),
        "model_id": row["model_id"],
        "recommended_price_ceiling_usd": float(row["recommended_price_ceiling_usd"]),
        "status": status,
        "approved_ceiling_usd": approved_ceiling_usd,
        "spent_usd": float(row.get("spent_usd") or 0.0),
        "asset_id": row.get("asset_id"),
        "spawn_ids_json": _json_dump(cast(list[str], row["spawn_ids"])),
        "completed_step_keys_json": _json_dump(cast(list[str], row["completed_step_keys"])),
        "returned_step_keys_json": _json_dump(cast(list[str], row["returned_step_keys"])),
        "started_at_ms": row.get("started_at_ms"),
        "elapsed_ms": int(row.get("elapsed_ms") or 0),
        "force_below_recommended": 1 if row.get("force_below_recommended") else 0,
        "notes": str(row.get("notes") or ""),
        "research_tier": str(row.get("research_tier") or "deep"),
        "fanout_depth": int(row.get("fanout_depth") or 3),
        "state_version": state_version,
        "approved_ceiling_cents": approved_ceiling_cents,
        "consent_granted_by_user_id": authority.consent_granted_by_user_id,
        "consent_recorded_at_ms": authority.consent_recorded_at_ms,
        "consent_note": authority.consent_note,
        "operation_state": operation_state,
        "operation_id": authority.operation_id,
        "dispatch_claimed_at_ms": dispatch_claimed_at_ms,
        "dispatch_started_at_ms": dispatch_started_at_ms,
        "dispatch_completed_at_ms": dispatch_completed_at_ms,
    }


class SqliteDurableJobStore:
    def __init__(self, db_path: str) -> None:
        self.db_path = _validate_identifier(db_path, field_name="db_path")

    def ensure_schema(self) -> None:
        directory = os.path.dirname(self.db_path)
        if directory:
            os.makedirs(directory, exist_ok=True)
        with closing(self._connect()) as conn:
            conn.execute("BEGIN EXCLUSIVE")
            try:
                version = int(conn.execute("PRAGMA user_version").fetchone()[0])
                if version > _SCHEMA_VERSION:
                    raise RuntimeError(f"unsupported Midnight Oil schema version {version}")
                columns = self._table_columns(conn, _TABLE_NAME)
                if not columns:
                    conn.execute(_CREATE_TABLE_SQL)
                elif "owner_user_id" not in columns or not self._has_composite_primary_key(columns):
                    self._rebuild_legacy_table(conn)
                else:
                    self._add_missing_columns(conn)
                self._backfill_legacy_approved_ceiling_cents(conn)
                conn.execute(f"PRAGMA user_version = {_SCHEMA_VERSION}")
                conn.commit()
            except BaseException:
                conn.rollback()
                raise

    def put_job_for_owner(self, owner_user_id: str, job: MidnightOilJob) -> MidnightOilJob:
        self.ensure_schema()
        _validate_identifier(owner_user_id, field_name="owner_user_id")
        _validate_identifier(job.job_id, field_name="job_id")
        sql_row = _job_to_sql_row(owner_user_id, job)
        placeholders = ", ".join("?" for _ in _ALL_COLUMNS)
        values = [sql_row[column] for column in _ALL_COLUMNS]
        with closing(self._connect()) as conn:
            try:
                conn.execute(
                    f"INSERT INTO {_TABLE_NAME} ({', '.join(_ALL_COLUMNS)}) VALUES ({placeholders})",
                    values,
                )
            except sqlite3.IntegrityError as exc:
                raise ValueError(
                    "durable job already exists; authority changes require CAS"
                ) from exc
        stored = self.get_job_for_owner(job.job_id, owner_user_id)
        if stored is None:
            raise RuntimeError("durable job vanished immediately after creation")
        return stored

    def get_job_for_owner(
        self,
        job_id: str,
        owner_user_id: str,
    ) -> MidnightOilJob | None:
        self.ensure_schema()
        _validate_identifier(job_id, field_name="job_id")
        _validate_identifier(owner_user_id, field_name="owner_user_id")
        with closing(self._connect()) as conn:
            row = conn.execute(
                f"""
                SELECT {", ".join(_ALL_COLUMNS)}
                FROM {_TABLE_NAME}
                WHERE owner_user_id = ? AND job_id = ?
                """,
                (owner_user_id, job_id),
            ).fetchone()
        if row is None:
            return None
        return _row_to_job(row)

    def update_execution_for_owner(
        self, owner_user_id: str, job: MidnightOilJob
    ) -> MidnightOilJob:
        """Persist worker-owned fields without changing durable authority."""
        self.ensure_schema()
        current = self.get_job_for_owner(job.job_id, owner_user_id)
        if current is None or current.authority is None:
            raise KeyError(job.job_id)
        def immutable(value: MidnightOilJob) -> tuple[object, ...]:
            return (
                value.job_id,
                value.goals,
                value.duration_minutes,
                value.model_id,
                value.recommended_price_ceiling_usd,
                value.asset_id,
                value.research_tier,
                value.fanout_depth,
                value.force_below_recommended,
            )
        if immutable(job) != immutable(current):
            raise ValueError("worker cannot change immutable durable job configuration")
        if job.authority not in {None, current.authority}:
            raise ValueError("worker cannot change durable operation authority")
        proposed = replace(job, authority=current.authority)
        row = _job_to_sql_row(owner_user_id, proposed)
        execution_columns = (
            "status",
            "approved_ceiling_usd",
            "spent_usd",
            "spawn_ids_json",
            "completed_step_keys_json",
            "returned_step_keys_json",
            "started_at_ms",
            "elapsed_ms",
            "notes",
        )
        with closing(self._connect()) as conn:
            conn.execute("BEGIN IMMEDIATE")
            cursor = conn.execute(
                f"UPDATE {_TABLE_NAME} SET "
                + ", ".join(f"{column} = ?" for column in execution_columns)
                + " WHERE owner_user_id = ? AND job_id = ? AND state_version = ?",
                [
                    *(row[column] for column in execution_columns),
                    owner_user_id,
                    job.job_id,
                    current.authority.state_version,
                ],
            )
            if cursor.rowcount != 1:
                conn.rollback()
                raise RuntimeError("durable operation authority changed during worker checkpoint")
            conn.commit()
        stored = self.get_job_for_owner(job.job_id, owner_user_id)
        if stored is None:
            raise RuntimeError("durable worker checkpoint vanished")
        return stored

    def compare_and_set_authority(
        self,
        job_id: str,
        owner_user_id: str,
        *,
        expected_version: int,
        expected_state: OperationState,
        expected_operation_id: str | None,
        operation_id: str | None,
        next_state: OperationState,
        approved_ceiling_cents: object = _UNSET,
        consent_granted_by_user_id: object = _UNSET,
        consent_recorded_at_ms: object = _UNSET,
        consent_note: object = _UNSET,
        force_below_recommended: object = _UNSET,
        dispatch_claimed_at_ms: object = _UNSET,
        dispatch_started_at_ms: object = _UNSET,
        dispatch_completed_at_ms: object = _UNSET,
    ) -> MidnightOilJob | None:
        self.ensure_schema()
        _validate_identifier(job_id, field_name="job_id")
        _validate_identifier(owner_user_id, field_name="owner_user_id")
        _validate_integer(expected_version, field_name="expected_version", allow_none=False)
        _validate_operation_state(expected_state)
        _validate_operation_state(next_state)
        if expected_operation_id is not None:
            _validate_identifier(expected_operation_id, field_name="expected_operation_id")
        if operation_id is not None:
            _validate_identifier(operation_id, field_name="operation_id")
        approved_cents_value: object = _UNSET
        consent_recorded_value: object = _UNSET
        dispatch_claimed_value: object = _UNSET
        dispatch_started_value: object = _UNSET
        dispatch_completed_value: object = _UNSET
        force_below_value: object = _UNSET
        approved_cents_value = (
            _validate_cents(
                approved_ceiling_cents,
                field_name="approved_ceiling_cents",
                allow_none=True,
            )
            if approved_ceiling_cents is not _UNSET
            else _UNSET
        )
        consent_recorded_value = (
            _validate_timestamp(
                consent_recorded_at_ms,
                field_name="consent_recorded_at_ms",
            )
            if consent_recorded_at_ms is not _UNSET
            else _UNSET
        )
        dispatch_claimed_value = (
            _validate_timestamp(
                dispatch_claimed_at_ms,
                field_name="dispatch_claimed_at_ms",
            )
            if dispatch_claimed_at_ms is not _UNSET
            else _UNSET
        )
        dispatch_started_value = (
            _validate_timestamp(
                dispatch_started_at_ms,
                field_name="dispatch_started_at_ms",
            )
            if dispatch_started_at_ms is not _UNSET
            else _UNSET
        )
        dispatch_completed_value = (
            _validate_timestamp(
                dispatch_completed_at_ms,
                field_name="dispatch_completed_at_ms",
            )
            if dispatch_completed_at_ms is not _UNSET
            else _UNSET
        )
        if force_below_recommended is not _UNSET:
            if type(force_below_recommended) is not bool:
                raise ValueError("force_below_recommended must be a boolean")
            if expected_state != "awaiting_approval" or next_state != "approved":
                raise ValueError("force_below_recommended is set only during approval")
            force_below_value = force_below_recommended
        set_clauses = [
            "state_version = state_version + 1",
            "operation_state = ?",
            "operation_id = ?",
        ]
        params: list[Any] = [next_state, operation_id]
        if next_state == "approved":
            set_clauses.append("status = 'approved'")
        if approved_cents_value is not _UNSET:
            approved_cents = cast(int | None, approved_cents_value)
            set_clauses.append("approved_ceiling_cents = ?")
            params.append(approved_cents)
            set_clauses.append("approved_ceiling_usd = ?")
            params.append(None if approved_cents is None else float(approved_cents) / 100.0)
        if consent_granted_by_user_id is not _UNSET:
            set_clauses.append("consent_granted_by_user_id = ?")
            params.append(consent_granted_by_user_id)
        if consent_recorded_value is not _UNSET:
            set_clauses.append("consent_recorded_at_ms = ?")
            params.append(consent_recorded_value)
        if consent_note is not _UNSET:
            set_clauses.append("consent_note = ?")
            params.append("" if consent_note is None else str(consent_note))
        if force_below_value is not _UNSET:
            set_clauses.append("force_below_recommended = ?")
            params.append(1 if force_below_value else 0)
        if dispatch_claimed_value is not _UNSET:
            set_clauses.append("dispatch_claimed_at_ms = ?")
            params.append(dispatch_claimed_value)
        if dispatch_started_value is not _UNSET:
            set_clauses.append("dispatch_started_at_ms = ?")
            params.append(dispatch_started_value)
        if dispatch_completed_value is not _UNSET:
            set_clauses.append("dispatch_completed_at_ms = ?")
            params.append(dispatch_completed_value)
        params.extend(
            [
                owner_user_id,
                job_id,
                expected_version,
                expected_state,
                expected_operation_id,
                expected_operation_id,
            ]
        )
        with closing(self._connect()) as conn:
            conn.execute("BEGIN IMMEDIATE")
            current_row = conn.execute(
                f"SELECT {', '.join(_ALL_COLUMNS)} FROM {_TABLE_NAME} "
                "WHERE owner_user_id = ? AND job_id = ?",
                (owner_user_id, job_id),
            ).fetchone()
            if current_row is None:
                conn.rollback()
                return None
            current_job = _row_to_job(current_row)
            current = cast(MidnightOilJobAuthority, current_job.authority)
            if (
                current.state_version != expected_version
                or current.operation_state != expected_state
                or current.operation_id != expected_operation_id
            ):
                conn.rollback()
                return None
            proposed = replace(
                current,
                state_version=current.state_version + 1,
                operation_state=next_state,
                operation_id=operation_id,
                approved_ceiling_cents=(
                    current.approved_ceiling_cents
                    if approved_cents_value is _UNSET
                    else cast(int | None, approved_cents_value)
                ),
                consent_granted_by_user_id=(
                    current.consent_granted_by_user_id
                    if consent_granted_by_user_id is _UNSET
                    else cast(str | None, consent_granted_by_user_id)
                ),
                consent_recorded_at_ms=(
                    current.consent_recorded_at_ms
                    if consent_recorded_value is _UNSET
                    else cast(int | None, consent_recorded_value)
                ),
                consent_note=(
                    current.consent_note
                    if consent_note is _UNSET
                    else ""
                    if consent_note is None
                    else str(consent_note)
                ),
                dispatch_claimed_at_ms=(
                    current.dispatch_claimed_at_ms
                    if dispatch_claimed_value is _UNSET
                    else cast(int | None, dispatch_claimed_value)
                ),
                dispatch_started_at_ms=(
                    current.dispatch_started_at_ms
                    if dispatch_started_value is _UNSET
                    else cast(int | None, dispatch_started_value)
                ),
                dispatch_completed_at_ms=(
                    current.dispatch_completed_at_ms
                    if dispatch_completed_value is _UNSET
                    else cast(int | None, dispatch_completed_value)
                ),
            )
            try:
                _validate_authority_transition(current, proposed)
            except ValueError:
                conn.rollback()
                raise
            cur = conn.execute(
                f"""
                UPDATE {_TABLE_NAME}
                SET {", ".join(set_clauses)}
                WHERE owner_user_id = ?
                  AND job_id = ?
                  AND state_version = ?
                  AND operation_state = ?
                  AND (
                    (operation_id IS NULL AND ? IS NULL)
                    OR operation_id = ?
                  )
                """,
                params,
            )
            if cur.rowcount != 1:
                conn.rollback()
                return None
            row = conn.execute(
                f"""
                SELECT {", ".join(_ALL_COLUMNS)}
                FROM {_TABLE_NAME}
                WHERE owner_user_id = ? AND job_id = ?
                """,
                (owner_user_id, job_id),
            ).fetchone()
            conn.commit()
        if row is None:
            raise RuntimeError("durable authority row missing after successful CAS")
        return _row_to_job(row)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(
            self.db_path,
            isolation_level=None,
            timeout=10.0,
            check_same_thread=False,
        )
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA busy_timeout = 10000")
        return conn

    @staticmethod
    def _table_columns(
        conn: sqlite3.Connection,
        table_name: str,
    ) -> dict[str, sqlite3.Row]:
        rows = conn.execute(f"PRAGMA table_info({table_name})").fetchall()
        return {str(row["name"]): row for row in rows}

    @staticmethod
    def _has_composite_primary_key(columns: Mapping[str, sqlite3.Row]) -> bool:
        owner_pk = (
            int(columns.get("owner_user_id", {"pk": 0})["pk"]) if "owner_user_id" in columns else 0
        )
        job_pk = int(columns.get("job_id", {"pk": 0})["pk"]) if "job_id" in columns else 0
        return owner_pk == 1 and job_pk == 2

    def _add_missing_columns(self, conn: sqlite3.Connection) -> None:
        columns = self._table_columns(conn, _TABLE_NAME)
        for column_name, sql in _ADD_COLUMN_SQL.items():
            if column_name not in columns:
                conn.execute(sql)

    def _rebuild_legacy_table(self, conn: sqlite3.Connection) -> None:
        old_columns = self._table_columns(conn, _TABLE_NAME)
        conn.execute(f"DROP TABLE IF EXISTS {_TABLE_NAME}_migrated")
        conn.execute(_CREATE_TABLE_SQL.replace(_TABLE_NAME, f"{_TABLE_NAME}_migrated"))
        select_columns = ", ".join(old_columns)
        rows = conn.execute(f"SELECT {select_columns} FROM {_TABLE_NAME}").fetchall()
        for old_row in rows:
            migrated = self._migrate_legacy_row(old_row, old_columns)
            conn.execute(
                f"""
                INSERT INTO {_TABLE_NAME}_migrated ({", ".join(_ALL_COLUMNS)})
                VALUES ({", ".join("?" for _ in _ALL_COLUMNS)})
                """,
                [migrated[column] for column in _ALL_COLUMNS],
            )
        conn.execute(f"DROP TABLE {_TABLE_NAME}")
        conn.execute(f"ALTER TABLE {_TABLE_NAME}_migrated RENAME TO {_TABLE_NAME}")

    def _migrate_legacy_row(
        self,
        old_row: sqlite3.Row,
        old_columns: Mapping[str, sqlite3.Row],
    ) -> dict[str, Any]:
        row_map = {name: old_row[name] for name in old_columns}
        goals_json = row_map.get("goals_json")
        if goals_json is not None:
            goals_json = _json_dump(_decode_string_array(goals_json, field_name="goals_json"))
        else:
            goals = row_map.get("goals")
            if isinstance(goals, str):
                try:
                    parsed_goals = json.loads(goals)
                except json.JSONDecodeError:
                    parsed_goals = [goals]
            else:
                parsed_goals = list(goals or [])
            goals_json = _json_dump([str(item) for item in parsed_goals])
        spawn_ids_json = row_map.get("spawn_ids_json")
        if spawn_ids_json is not None:
            spawn_ids_json = _json_dump(
                _decode_string_array(spawn_ids_json, field_name="spawn_ids_json")
            )
        else:
            spawn_ids = row_map.get("spawn_ids")
            if isinstance(spawn_ids, str):
                try:
                    parsed_spawn_ids = json.loads(spawn_ids)
                except json.JSONDecodeError:
                    parsed_spawn_ids = [spawn_ids]
            else:
                parsed_spawn_ids = list(spawn_ids or [])
            spawn_ids_json = _json_dump([str(item) for item in parsed_spawn_ids])
        completed_step_keys_json = _json_dump(
            _decode_string_array(
                row_map.get("completed_step_keys_json", "[]"),
                field_name="completed_step_keys_json",
            )
        )
        returned_step_keys_json = _json_dump(
            _decode_string_array(
                row_map.get("returned_step_keys_json", "[]"),
                field_name="returned_step_keys_json",
            )
        )
        status = _validate_job_status(row_map.get("status"))
        operation_state = row_map.get("operation_state") or _operation_state_from_status(status)
        operation_state = _validate_operation_state(operation_state)
        approved_ceiling_usd = row_map.get("approved_ceiling_usd")
        approved_ceiling_cents = row_map.get("approved_ceiling_cents")
        if approved_ceiling_cents is None:
            approved_ceiling_cents = _legacy_usd_to_cents_floor(approved_ceiling_usd)
        approved_ceiling_cents = _validate_cents(
            approved_ceiling_cents,
            field_name="approved_ceiling_cents",
            allow_none=True,
        )
        consent_granted_by_user_id = row_map.get("consent_granted_by_user_id")
        consent_recorded_at_ms = row_map.get("consent_recorded_at_ms")
        consent_note = str(row_map.get("consent_note") or "")
        operation_id = row_map.get("operation_id")
        dispatch_claimed_at_ms = row_map.get("dispatch_claimed_at_ms")
        dispatch_started_at_ms = row_map.get("dispatch_started_at_ms")
        dispatch_completed_at_ms = row_map.get("dispatch_completed_at_ms")
        requires_approval = operation_state in {
            "approved",
            "dispatch_claimed",
            "dispatch_started",
            "dispatch_finished",
        }
        has_durable_consent = (
            approved_ceiling_cents is not None
            and approved_ceiling_cents > 0
            and consent_granted_by_user_id is not None
            and consent_recorded_at_ms is not None
        )
        if requires_approval and not has_durable_consent:
            status = "failed"
            operation_state = "failed_closed"
            approved_ceiling_cents = None
            consent_granted_by_user_id = None
            consent_recorded_at_ms = None
            consent_note = ""
            operation_id = None
            dispatch_claimed_at_ms = None
            dispatch_started_at_ms = None
            dispatch_completed_at_ms = None
        owner_user_id = _validate_identifier(
            str(row_map.get("owner_user_id") or _LEGACY_OWNER_USER_ID),
            field_name="owner_user_id",
        )
        job_id = _validate_identifier(str(row_map["job_id"]), field_name="job_id")
        authority = MidnightOilJobAuthority(
            owner_user_id=owner_user_id,
            state_version=cast(
                int,
                _validate_integer(
                    row_map.get("state_version") or 0, field_name="state_version", allow_none=False
                ),
            ),
            approved_ceiling_cents=approved_ceiling_cents,
            consent_granted_by_user_id=consent_granted_by_user_id,
            consent_recorded_at_ms=consent_recorded_at_ms,
            consent_note=consent_note,
            operation_state=operation_state,
            operation_id=operation_id,
            dispatch_claimed_at_ms=dispatch_claimed_at_ms,
            dispatch_started_at_ms=dispatch_started_at_ms,
            dispatch_completed_at_ms=dispatch_completed_at_ms,
        )
        _validate_authority(authority)
        return {
            "owner_user_id": owner_user_id,
            "job_id": job_id,
            "goals_json": goals_json,
            "duration_minutes": int(row_map["duration_minutes"]),
            "model_id": row_map.get("model_id"),
            "recommended_price_ceiling_usd": float(row_map["recommended_price_ceiling_usd"]),
            "status": status,
            "approved_ceiling_usd": approved_ceiling_usd,
            "spent_usd": float(row_map.get("spent_usd") or 0.0),
            "asset_id": row_map.get("asset_id"),
            "spawn_ids_json": spawn_ids_json,
            "completed_step_keys_json": completed_step_keys_json,
            "returned_step_keys_json": returned_step_keys_json,
            "started_at_ms": row_map.get("started_at_ms"),
            "elapsed_ms": int(row_map.get("elapsed_ms") or 0),
            "force_below_recommended": 1 if row_map.get("force_below_recommended") else 0,
            "notes": str(row_map.get("notes") or ""),
            "research_tier": str(row_map.get("research_tier") or "deep"),
            "fanout_depth": int(row_map.get("fanout_depth") or 3),
            "state_version": authority.state_version,
            "approved_ceiling_cents": approved_ceiling_cents,
            "consent_granted_by_user_id": authority.consent_granted_by_user_id,
            "consent_recorded_at_ms": authority.consent_recorded_at_ms,
            "consent_note": authority.consent_note,
            "operation_state": str(operation_state),
            "operation_id": authority.operation_id,
            "dispatch_claimed_at_ms": authority.dispatch_claimed_at_ms,
            "dispatch_started_at_ms": authority.dispatch_started_at_ms,
            "dispatch_completed_at_ms": authority.dispatch_completed_at_ms,
        }

    def _backfill_legacy_approved_ceiling_cents(self, conn: sqlite3.Connection) -> None:
        rows = conn.execute(
            f"""
            SELECT owner_user_id, job_id, approved_ceiling_usd
            FROM {_TABLE_NAME}
            WHERE approved_ceiling_cents IS NULL
              AND approved_ceiling_usd IS NOT NULL
              AND operation_state IN (
                'approved', 'dispatch_claimed', 'dispatch_started', 'dispatch_finished'
              )
            """
        ).fetchall()
        for row in rows:
            cents = _legacy_usd_to_cents_floor(row["approved_ceiling_usd"])
            conn.execute(
                f"""
                UPDATE {_TABLE_NAME}
                SET approved_ceiling_cents = ?
                WHERE owner_user_id = ? AND job_id = ?
                """,
                (cents, row["owner_user_id"], row["job_id"]),
            )


class OwnerBoundDurableJobStore:
    """Bind the legacy worker store protocol to one durable owner scope."""

    def __init__(self, store: SqliteDurableJobStore, owner_user_id: str) -> None:
        self.store = store
        self.owner_user_id = _validate_identifier(owner_user_id, field_name="owner_user_id")

    def get_job(self, job_id: str) -> dict[str, Any] | None:
        job = self.store.get_job_for_owner(job_id, self.owner_user_id)
        return None if job is None else _job_to_row(job)

    def put_job(self, row: dict[str, Any]) -> None:
        job = _job_from_row(row)
        self.store.update_execution_for_owner(self.owner_user_id, job)

    def budget_db_path(self) -> str:
        return f"{self.store.db_path}.budget.duckdb"


def create_production_job_store(db_path: str | None) -> SqliteDurableJobStore:
    if db_path is None or not db_path.strip():
        raise RuntimeError("a non-empty durable Midnight Oil database path is required")
    store = SqliteDurableJobStore(db_path)
    store.ensure_schema()
    return store
