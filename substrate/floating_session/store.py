"""Session chrome store (session descriptors only; spawns live in engagement store)."""

from __future__ import annotations

import json
import re
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

_SESSION_ID = re.compile(r"^fsess_[0-9a-f]{16}$")


def _checked_session_id(value: object) -> str:
    if not isinstance(value, str) or _SESSION_ID.fullmatch(value) is None:
        raise ValueError("session_id is outside the canonical floating-session contract")
    return value


@runtime_checkable
class SessionStore(Protocol):
    def put_session(self, session: dict[str, Any]) -> None: ...
    def get_session(self, session_id: str) -> dict[str, Any] | None: ...
    def list_sessions(self, parent_asset_id: str) -> list[dict[str, Any]]: ...
    def compare_and_set_view(
        self, session_id: str, expected_mode: str | None, target_mode: str
    ) -> tuple[dict[str, Any], bool]: ...
    def update_status(self, session_id: str, status: str) -> dict[str, Any]: ...


@dataclass
class InMemorySessionStore:
    _sessions: dict[str, dict[str, Any]] = field(default_factory=dict)
    _lock: threading.RLock = field(default_factory=threading.RLock)

    def put_session(self, session: dict[str, Any]) -> None:
        session_id = _checked_session_id(session.get("session_id"))
        with self._lock:
            self._sessions[session_id] = dict(session)

    def get_session(self, session_id: str) -> dict[str, Any] | None:
        session_id = _checked_session_id(session_id)
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

    def compare_and_set_view(
        self, session_id: str, expected_mode: str | None, target_mode: str
    ) -> tuple[dict[str, Any], bool]:
        session_id = _checked_session_id(session_id)
        with self._lock:
            row = self._sessions.get(session_id)
            if row is None:
                raise KeyError(session_id)
            current = str(row.get("view_mode") or "floating")
            if current == target_mode:
                return dict(row), True
            if expected_mode is not None and current != expected_mode:
                return dict(row), False
            updated = {**row, "view_mode": target_mode}
            self._sessions[session_id] = updated
            return dict(updated), True

    def update_status(self, session_id: str, status: str) -> dict[str, Any]:
        session_id = _checked_session_id(session_id)
        with self._lock:
            row = self._sessions.get(session_id)
            if row is None:
                raise KeyError(session_id)
            if row.get("status") == status:
                return dict(row)
            updated = {**row, "status": status}
            self._sessions[session_id] = updated
            return dict(updated)


@dataclass
class FileSessionStore:
    root: Path
    _lock: threading.RLock = field(default_factory=threading.RLock, init=False)

    def __post_init__(self) -> None:
        self.root = Path(self.root)
        (self.root / "sessions").mkdir(parents=True, exist_ok=True)

    def put_session(self, session: dict[str, Any]) -> None:
        session_id = _checked_session_id(session.get("session_id"))
        path = self.root / "sessions" / f"{session_id}.json"
        path.write_text(json.dumps(session, sort_keys=True, indent=2), encoding="utf-8")

    def get_session(self, session_id: str) -> dict[str, Any] | None:
        session_id = _checked_session_id(session_id)
        path = self.root / "sessions" / f"{session_id}.json"
        if not path.is_file():
            return None
        decoded = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(decoded, dict) or decoded.get("session_id") != session_id:
            raise ValueError("durable session identity conflicts with its filename")
        data: dict[str, Any] = decoded
        return data

    def list_sessions(self, parent_asset_id: str) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for path in sorted((self.root / "sessions").glob("*.json")):
            session_id = _checked_session_id(path.stem)
            row = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(row, dict) or row.get("session_id") != session_id:
                raise ValueError("durable session identity conflicts with its filename")
            if row.get("parent_asset_id") == parent_asset_id:
                out.append(row)
        return out

    def compare_and_set_view(
        self, session_id: str, expected_mode: str | None, target_mode: str
    ) -> tuple[dict[str, Any], bool]:
        session_id = _checked_session_id(session_id)
        with self._lock:
            row = self.get_session(session_id)
            if row is None:
                raise KeyError(session_id)
            current = str(row.get("view_mode") or "floating")
            if current == target_mode:
                return row, True
            if expected_mode is not None and current != expected_mode:
                return row, False
            updated = {**row, "view_mode": target_mode}
            self.put_session(updated)
            return updated, True

    def update_status(self, session_id: str, status: str) -> dict[str, Any]:
        session_id = _checked_session_id(session_id)
        with self._lock:
            row = self.get_session(session_id)
            if row is None:
                raise KeyError(session_id)
            if row.get("status") == status:
                return row
            updated = {**row, "status": status}
            self.put_session(updated)
            return updated
