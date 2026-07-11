"""Durable detail/checkpoint store for the Midnight Oil worker projection."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from .job import _job_from_row, _job_to_row


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

    def budget_db_path(self) -> str:
        return str(self._budget_path)


__all__ = ["DurableJobStore"]
