"""Session chrome store (session descriptors only; spawns live in engagement store)."""

from __future__ import annotations

import json
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from substrate.durable_file_key import contained_legacy_json_path, durable_file_key


@runtime_checkable
class SessionStore(Protocol):
    def put_session(self, session: dict[str, Any]) -> None: ...
    def get_session(self, session_id: str) -> dict[str, Any] | None: ...
    def list_sessions(self, parent_asset_id: str) -> list[dict[str, Any]]: ...


@dataclass
class InMemorySessionStore:
    _sessions: dict[str, dict[str, Any]] = field(default_factory=dict)
    _lock: threading.RLock = field(default_factory=threading.RLock)

    def put_session(self, session: dict[str, Any]) -> None:
        with self._lock:
            self._sessions[session["session_id"]] = dict(session)

    def get_session(self, session_id: str) -> dict[str, Any] | None:
        with self._lock:
            row = self._sessions.get(session_id)
            return dict(row) if row is not None else None

    def list_sessions(self, parent_asset_id: str) -> list[dict[str, Any]]:
        with self._lock:
            return [
                dict(s)
                for s in self._sessions.values()
                if s.get("parent_asset_id") == parent_asset_id
            ]


@dataclass
class FileSessionStore:
    root: Path

    def __post_init__(self) -> None:
        self.root = Path(self.root)
        (self.root / "sessions").mkdir(parents=True, exist_ok=True)

    def _session_path(self, session_id: str) -> Path:
        return self.root / "sessions" / f"{durable_file_key(session_id)}.json"

    def put_session(self, session: dict[str, Any]) -> None:
        path = self._session_path(session["session_id"])
        path.write_text(json.dumps(session, sort_keys=True, indent=2), encoding="utf-8")

    def get_session(self, session_id: str) -> dict[str, Any] | None:
        path = self._session_path(session_id)
        if not path.is_file():
            legacy = contained_legacy_json_path(self.root / "sessions", session_id)
            if legacy is None or not legacy.is_file():
                return None
            path = legacy
        data: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
        if data.get("session_id") != session_id:
            return None
        return data

    def list_sessions(self, parent_asset_id: str) -> list[dict[str, Any]]:
        by_id: dict[str, dict[str, Any]] = {}
        for path in sorted((self.root / "sessions").glob("*.json")):
            row = json.loads(path.read_text(encoding="utf-8"))
            if row.get("parent_asset_id") == parent_asset_id:
                by_id[str(row.get("session_id") or path.name)] = row
        return list(by_id.values())
