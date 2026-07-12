"""Session chrome store (session descriptors only; spawns live in engagement store)."""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
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
    def list_sessions(
        self, parent_asset_id: str, owner_id: str = "__operator__"
    ) -> list[dict[str, Any]]: ...
    def list_owner_sessions(
        self, owner_id: str, *, after_session_id: str | None, limit: int
    ) -> list[dict[str, Any]]: ...
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

    def list_sessions(
        self, parent_asset_id: str, owner_id: str = "__operator__"
    ) -> list[dict[str, Any]]:
        with self._lock:
            return [
                dict(s)
                for s in self._sessions.values()
                if s.get("parent_asset_id") == parent_asset_id
                and s.get("owner_id") == owner_id
            ]

    def list_owner_sessions(
        self, owner_id: str, *, after_session_id: str | None, limit: int
    ) -> list[dict[str, Any]]:
        if not owner_id or limit < 1:
            raise ValueError("owner_id is required")
        with self._lock:
            rows = sorted(
                (
                dict(session)
                for session in self._sessions.values()
                if session.get("owner_id") == owner_id
                ),
                key=lambda session: str(session["session_id"]),
            )
            if after_session_id is not None:
                try:
                    index = next(
                        index
                        for index, row in enumerate(rows)
                        if row["session_id"] == after_session_id
                    )
                except StopIteration as exc:
                    raise ValueError("session cursor is not available") from exc
                rows = rows[index + 1 :]
            return rows[:limit]

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
        (self.root / "owner_index").mkdir(parents=True, exist_ok=True)
        self._backfill_owner_index()

    def _backfill_owner_index(self) -> None:
        """Reconcile row-first writes into both indexes on every startup.

        Session row + indexes are deliberately a recoverable multi-file write:
        a crash can leave the canonical row ahead of either index.  Scanning on
        startup is therefore correctness work, not only a one-time migration.
        """

        for path in sorted((self.root / "sessions").glob("fsess_*.json")):
            session_id = _checked_session_id(path.stem)
            row = self._read_unlocked(session_id, path)
            if row is not None:
                self._index_session(row)

    def _index_path(self, owner_id: str, parent_asset_id: str) -> Path:
        digest = hashlib.sha256(
            f"antiek.session-index.v1\0{owner_id}\0{parent_asset_id}".encode()
        ).hexdigest()
        return self.root / "owner_index" / f"{digest}.json"

    def _owner_index_path(self, owner_id: str) -> Path:
        digest = hashlib.sha256(
            f"antiek.session-owner-index.v1\0{owner_id}".encode()
        ).hexdigest()
        return self.root / "owner_index" / f"owner-{digest}.json"

    def _append_index(self, path: Path, session_id: str) -> None:
        lock_path = path.with_suffix(".lock")
        with self._lock, lock_path.open("a+b") as lock_file:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
            ids: list[str] = []
            if path.is_file():
                decoded = json.loads(path.read_text(encoding="utf-8"))
                if not isinstance(decoded, list) or not all(
                    isinstance(item, str) for item in decoded
                ):
                    raise ValueError("durable owner session index is malformed")
                ids = decoded
            if session_id in ids:
                return
            ids.append(session_id)
            temp = path.with_suffix(f".{os.getpid()}.{threading.get_ident()}.tmp")
            try:
                with temp.open("w", encoding="utf-8") as handle:
                    json.dump(sorted(ids), handle)
                    handle.flush()
                    os.fsync(handle.fileno())
                os.replace(temp, path)
                directory_fd = os.open(path.parent, os.O_RDONLY)
                try:
                    os.fsync(directory_fd)
                finally:
                    os.close(directory_fd)
            finally:
                temp.unlink(missing_ok=True)

    def _index_session(self, session: dict[str, Any]) -> None:
        owner = str(session.get("owner_id") or "")
        parent = str(session.get("parent_asset_id") or "")
        if not owner or not parent:
            return  # ownerless legacy rows are deliberately not indexed
        session_id = str(session["session_id"])
        self._append_index(self._index_path(owner, parent), session_id)
        self._append_index(self._owner_index_path(owner), session_id)

    def put_session(self, session: dict[str, Any]) -> None:
        session_id = _checked_session_id(session.get("session_id"))
        path = self.root / "sessions" / f"{session_id}.json"
        lock_path = path.with_suffix(".lock")
        with self._lock, lock_path.open("a+b") as lock_file:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
            self._write_unlocked(path, session)
        self._index_session(session)

    def _write_unlocked(self, path: Path, session: dict[str, Any]) -> None:
        temp = path.with_suffix(f".{os.getpid()}.{threading.get_ident()}.tmp")
        try:
            with temp.open("w", encoding="utf-8") as handle:
                json.dump(session, handle, sort_keys=True, indent=2)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp, path)
            directory_fd = os.open(path.parent, os.O_RDONLY)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
        finally:
            temp.unlink(missing_ok=True)

    def _read_unlocked(self, session_id: str, path: Path) -> dict[str, Any] | None:
        if not path.is_file():
            return None
        decoded = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(decoded, dict) or decoded.get("session_id") != session_id:
            raise ValueError("durable session identity conflicts with its filename")
        data: dict[str, Any] = decoded
        return data

    def get_session(self, session_id: str) -> dict[str, Any] | None:
        session_id = _checked_session_id(session_id)
        path = self.root / "sessions" / f"{session_id}.json"
        return self._read_unlocked(session_id, path)

    def list_sessions(
        self, parent_asset_id: str, owner_id: str = "__operator__"
    ) -> list[dict[str, Any]]:
        index_path = self._index_path(owner_id, parent_asset_id)
        if not index_path.is_file():
            return []
        decoded = json.loads(index_path.read_text(encoding="utf-8"))
        if not isinstance(decoded, list) or not all(
            isinstance(item, str) for item in decoded
        ):
            raise ValueError("durable owner session index is malformed")
        out: list[dict[str, Any]] = []
        for raw_session_id in decoded:
            session_id = _checked_session_id(raw_session_id)
            row = self.get_session(session_id)
            if row is None or row.get("owner_id") != owner_id:
                raise ValueError("durable owner session index requires reconciliation")
            if row.get("parent_asset_id") != parent_asset_id:
                raise ValueError("durable owner session index requires reconciliation")
            out.append(row)
        return out

    def list_owner_sessions(
        self, owner_id: str, *, after_session_id: str | None, limit: int
    ) -> list[dict[str, Any]]:
        if not owner_id or limit < 1:
            raise ValueError("owner_id is required")
        index_path = self._owner_index_path(owner_id)
        if not index_path.is_file():
            return []
        decoded = json.loads(index_path.read_text(encoding="utf-8"))
        if not isinstance(decoded, list) or not all(
            isinstance(item, str) for item in decoded
        ):
            raise ValueError("durable owner session index is malformed")
        session_ids = sorted(decoded)
        if after_session_id is not None:
            try:
                cursor_index = session_ids.index(after_session_id)
            except ValueError as exc:
                raise ValueError("session cursor is not available") from exc
            session_ids = session_ids[cursor_index + 1 :]
        out: list[dict[str, Any]] = []
        for raw_session_id in session_ids[:limit]:
            session_id = _checked_session_id(raw_session_id)
            row = self.get_session(session_id)
            if row is None or row.get("owner_id") != owner_id:
                raise ValueError("durable owner session index requires reconciliation")
            out.append(row)
        return out

    def compare_and_set_view(
        self, session_id: str, expected_mode: str | None, target_mode: str
    ) -> tuple[dict[str, Any], bool]:
        session_id = _checked_session_id(session_id)
        path = self.root / "sessions" / f"{session_id}.json"
        lock_path = path.with_suffix(".lock")
        with self._lock, lock_path.open("a+b") as lock_file:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
            row = self._read_unlocked(session_id, path)
            if row is None:
                raise KeyError(session_id)
            current = str(row.get("view_mode") or "floating")
            if current == target_mode:
                return row, True
            if expected_mode is not None and current != expected_mode:
                return row, False
            updated = {**row, "view_mode": target_mode}
            self._write_unlocked(path, updated)
            return updated, True

    def update_status(self, session_id: str, status: str) -> dict[str, Any]:
        session_id = _checked_session_id(session_id)
        path = self.root / "sessions" / f"{session_id}.json"
        lock_path = path.with_suffix(".lock")
        with self._lock, lock_path.open("a+b") as lock_file:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
            row = self._read_unlocked(session_id, path)
            if row is None:
                raise KeyError(session_id)
            if row.get("status") == status:
                return row
            updated = {**row, "status": status}
            self._write_unlocked(path, updated)
            return updated
