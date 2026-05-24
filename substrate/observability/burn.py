"""Burn telemetry — per-LLM-call cost ledger backed by per-project SQLite."""

from __future__ import annotations

import json
import os
import sqlite3
import threading
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_DISABLE_ENV = "ANTIEK_DISABLE_BURN_TELEMETRY"
_SCHEMA_PATH = Path(__file__).parent / "burn_schema.sql"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class BurnEvent:
    session_id: str
    call_id: str
    model: str
    input_tokens: int
    output_tokens: int
    ts: str = field(default_factory=_now_iso)
    project_id: str | None = None
    tool_id: str | None = None
    cached_tokens: int = 0
    error: str | None = None
    extension_ids_active: tuple[str, ...] = ()


class BurnRecorder:
    _instances: dict[Path, "BurnRecorder"] = {}
    _instances_lock = threading.Lock()

    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._local = threading.local()
        self._ensure_schema()

    @classmethod
    def for_project(cls, project_root: Path) -> "BurnRecorder":
        db = (project_root / ".antiek" / "observability" / "burn.sqlite").resolve()
        with cls._instances_lock:
            inst = cls._instances.get(db)
            if inst is None:
                inst = cls(db)
                cls._instances[db] = inst
            return inst

    @classmethod
    def _reset_instances(cls) -> None:
        with cls._instances_lock:
            cls._instances.clear()

    def _conn(self) -> sqlite3.Connection:
        c = getattr(self._local, "conn", None)
        if c is None:
            c = sqlite3.connect(str(self.db_path), isolation_level=None, check_same_thread=False)
            c.execute("PRAGMA journal_mode=WAL")
            c.execute("PRAGMA synchronous=NORMAL")
            self._local.conn = c
        return c

    def _ensure_schema(self) -> None:
        schema = _SCHEMA_PATH.read_text()
        c = self._conn()
        c.executescript(schema)

    @staticmethod
    def disabled() -> bool:
        return os.environ.get(_DISABLE_ENV) == "1"

    def record(self, event: BurnEvent) -> None:
        if self.disabled():
            return
        d = asdict(event)
        d["extension_ids_active"] = json.dumps(list(event.extension_ids_active))
        c = self._conn()
        c.execute(
            "INSERT INTO burn_events ("
            "ts, session_id, project_id, call_id, model, tool_id, "
            "input_tokens, output_tokens, cached_tokens, error, extension_ids_active"
            ") VALUES ("
            ":ts, :session_id, :project_id, :call_id, :model, :tool_id, "
            ":input_tokens, :output_tokens, :cached_tokens, :error, :extension_ids_active)",
            d,
        )

    def record_many(self, events: list[BurnEvent]) -> None:
        if self.disabled() or not events:
            return
        c = self._conn()
        c.execute("BEGIN")
        try:
            for e in events:
                self.record(e)
            c.execute("COMMIT")
        except Exception:
            c.execute("ROLLBACK")
            raise

    def query(self, sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
        c = self._conn()
        c.row_factory = sqlite3.Row
        rows = [dict(r) for r in c.execute(sql, params)]
        c.row_factory = None
        return rows
