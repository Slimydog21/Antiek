"""Durable detail/checkpoint store for the Midnight Oil worker projection."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import replace
from pathlib import Path
from typing import Any

from .job import (
    MidnightOilJob,
    _graph_checkpoint,
    _graph_source_checkpoint,
    _job_from_row,
    _job_to_row,
)


class DurableJobStore:
    """SQLite job projection plus a stable sibling DuckDB budget ledger path."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._budget_path = self.path.with_suffix(".budget.duckdb")
        with self._connect() as connection:
            connection.execute(
                "CREATE TABLE IF NOT EXISTS midnight_oil_job_details ("
                "job_id TEXT PRIMARY KEY, row_json TEXT NOT NULL)"
            )

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=30, isolation_level=None)
        connection.execute("PRAGMA busy_timeout = 30000")
        return connection

    def put_job(self, job: dict[str, Any]) -> None:
        canonical = _job_to_row(_job_from_row(dict(job)))
        encoded = json.dumps(canonical, sort_keys=True, separators=(",", ":"))
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                existing = connection.execute(
                    "SELECT row_json FROM midnight_oil_job_details WHERE job_id = ?",
                    (canonical["job_id"],),
                ).fetchone()
                if existing is not None:
                    current_raw = json.loads(str(existing[0]))
                    if not isinstance(current_raw, dict):
                        raise ValueError("stored Midnight Oil job is invalid")
                    current = _job_from_row(current_raw)
                    updated = _job_from_row(canonical)
                    if (
                        current.graph_projection_source_sha256 is not None
                        and _graph_source_checkpoint(current) != _graph_source_checkpoint(updated)
                    ):
                        raise ValueError("sealed graph projection source is immutable")
                connection.execute(
                    "INSERT INTO midnight_oil_job_details(job_id, row_json) VALUES (?, ?) "
                    "ON CONFLICT(job_id) DO UPDATE SET row_json = excluded.row_json",
                    (canonical["job_id"], encoded),
                )
                connection.execute("COMMIT")
            except BaseException:
                connection.execute("ROLLBACK")
                raise

    def get_job(self, job_id: str) -> dict[str, Any] | None:
        if type(job_id) is not str or not job_id.strip() or len(job_id) > 256:
            raise ValueError("job_id must be a bounded non-empty string")
        with self._connect() as connection:
            row = connection.execute(
                "SELECT row_json FROM midnight_oil_job_details WHERE job_id = ?",
                (job_id.strip(),),
            ).fetchone()
        if row is None:
            return None
        value = json.loads(str(row[0]))
        if not isinstance(value, dict):
            raise ValueError("stored Midnight Oil job is invalid")
        return _job_to_row(_job_from_row(value))

    def compare_and_put_graph(self, expected: MidnightOilJob, updated: MidnightOilJob) -> bool:
        if expected.job_id != updated.job_id:
            raise ValueError("graph checkpoint jobs must match")
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                row = connection.execute(
                    "SELECT row_json FROM midnight_oil_job_details WHERE job_id = ?",
                    (expected.job_id,),
                ).fetchone()
                if row is None:
                    connection.execute("COMMIT")
                    return False
                current_raw = json.loads(str(row[0]))
                if not isinstance(current_raw, dict):
                    raise ValueError("stored Midnight Oil job is invalid")
                current = _job_from_row(current_raw)
                if _graph_checkpoint(current) != _graph_checkpoint(
                    expected
                ) or _graph_source_checkpoint(current) != _graph_source_checkpoint(expected):
                    connection.execute("COMMIT")
                    return False
                merged = replace(
                    current,
                    graph_projection_state=updated.graph_projection_state,
                    graph_projection_reason=updated.graph_projection_reason,
                    graph_effect_receipt=updated.graph_effect_receipt,
                    graph_projection_source_sha256=updated.graph_projection_source_sha256,
                )
                encoded = json.dumps(_job_to_row(merged), sort_keys=True, separators=(",", ":"))
                connection.execute(
                    "UPDATE midnight_oil_job_details SET row_json = ? WHERE job_id = ?",
                    (encoded, expected.job_id),
                )
                connection.execute("COMMIT")
                return True
            except BaseException:
                connection.execute("ROLLBACK")
                raise

    def budget_db_path(self) -> str:
        return str(self._budget_path)


__all__ = ["DurableJobStore"]
