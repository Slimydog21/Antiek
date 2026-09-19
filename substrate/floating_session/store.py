"""Session chrome store (session descriptors only; spawns live in engagement store)."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from substrate.engagement_spine.authority import (
    ENGAGEMENT_AUTHORITY_VERSION,
    EngagementAuthority,
)


@runtime_checkable
class SessionStore(Protocol):
    def put_session(self, session: dict[str, Any]) -> None: ...
    def get_session(self, session_id: str) -> dict[str, Any] | None: ...
    def list_sessions(self, parent_asset_id: str) -> list[dict[str, Any]]: ...


class SessionStoreUnavailable(RuntimeError):
    """A selected canonical session row exists but cannot be trusted or read."""


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
    _lock: threading.RLock = field(default_factory=threading.RLock, init=False, repr=False)

    def __post_init__(self) -> None:
        self.root = Path(self.root)
        (self.root / "sessions").mkdir(parents=True, exist_ok=True)

    def _session_path(self, session_id: str) -> Path:
        digest = hashlib.sha256(session_id.encode("utf-8")).hexdigest()
        return self.root / "sessions" / f"session-{digest}.json"

    def _legacy_session_path(self, session_id: str) -> Path | None:
        if (
            not session_id
            or session_id in {".", ".."}
            or "/" in session_id
            or "\\" in session_id
            or "\x00" in session_id
            or len(session_id.encode("utf-8")) > 200
        ):
            return None
        return self.root / "sessions" / f"{session_id}.json"

    @staticmethod
    def _atomic_write_json(path: Path, value: object) -> None:
        encoded = json.dumps(value, sort_keys=True, indent=2)
        fd, raw_temp = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
        temp = Path(raw_temp)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(encoded)
                handle.flush()
                os.fsync(handle.fileno())
            temp.replace(path)
        finally:
            temp.unlink(missing_ok=True)

    def put_session(self, session: dict[str, Any]) -> None:
        path = self._session_path(str(session["session_id"]))
        with self._lock:
            self._atomic_write_json(path, session)

    def get_session(self, session_id: str) -> dict[str, Any] | None:
        try:
            return self.get_session_strict(session_id)
        except SessionStoreUnavailable:
            return None

    def get_session_strict(self, session_id: str) -> dict[str, Any] | None:
        path = self._session_path(session_id)
        if path.is_symlink() or (path.exists() and not path.is_file()):
            raise SessionStoreUnavailable("stored session is unsafe")
        if not path.is_file():
            legacy = self._legacy_session_path(session_id)
            if legacy is None:
                return None
            if legacy.is_symlink() or (legacy.exists() and not legacy.is_file()):
                raise SessionStoreUnavailable("stored session is unsafe")
            if not legacy.is_file():
                return None
            path = legacy
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise SessionStoreUnavailable("stored session is unavailable or corrupt") from exc
        if not isinstance(data, dict) or data.get("session_id") != session_id:
            raise SessionStoreUnavailable("stored session identity is corrupt")
        return data

    def list_sessions(self, parent_asset_id: str) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for path in sorted((self.root / "sessions").glob("*.json")):
            if path.is_symlink():
                continue
            try:
                row = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if not isinstance(row, dict):
                continue
            if row.get("parent_asset_id") == parent_asset_id:
                out.append(row)
        return out


@dataclass(frozen=True)
class AuthorizedSessionStore:
    base: SessionStore
    authority: EngagementAuthority

    def _asset_storage_id(self, display_id: str) -> str:
        return self.authority.storage_id("asset", display_id)

    def _session_storage_id(self, display_id: str) -> str:
        return self.authority.storage_id("session", display_id)

    def _valid(self, row: dict[str, Any] | None) -> bool:
        return bool(
            row
            and row.get("engagement_authority_version") == ENGAGEMENT_AUTHORITY_VERSION
            and self.authority.owns_digest(row.get("owner_account_digest"))
            and row.get("engagement_key_id") == self.authority.key_id
        )

    def put_session(self, session: dict[str, Any]) -> None:
        row = dict(session)
        display_session = str(row["session_id"])
        display_asset = str(row["parent_asset_id"])
        row.update(
            {
                "engagement_authority_version": ENGAGEMENT_AUTHORITY_VERSION,
                "owner_account_digest": self.authority.account_digest,
                "engagement_key_id": self.authority.key_id,
                "display_session_id": display_session,
                "session_id": self._session_storage_id(display_session),
                "display_parent_asset_id": display_asset,
                "parent_asset_id": self._asset_storage_id(display_asset),
            }
        )
        self.base.put_session(row)

    def get_session(self, session_id: str) -> dict[str, Any] | None:
        try:
            return self.get_session_strict(session_id)
        except SessionStoreUnavailable:
            return None

    def get_session_strict(self, session_id: str) -> dict[str, Any] | None:
        storage_id = self._session_storage_id(session_id)
        strict = getattr(self.base, "get_session_strict", None)
        row = strict(storage_id) if callable(strict) else self.base.get_session(storage_id)
        if row is None:
            return None
        if not self._valid(row):
            raise SessionStoreUnavailable("stored session authority envelope is corrupt")
        assert row is not None
        display_asset = row.get("display_parent_asset_id")
        if (
            row.get("session_id") != storage_id
            or row.get("display_session_id") != session_id
            or not isinstance(display_asset, str)
            or row.get("parent_asset_id") != self._asset_storage_id(display_asset)
        ):
            raise SessionStoreUnavailable("stored session identity envelope is corrupt")
        out = dict(row)
        out["session_id"] = session_id
        out["parent_asset_id"] = display_asset
        return out

    def list_sessions(self, parent_asset_id: str) -> list[dict[str, Any]]:
        rows = self.base.list_sessions(self._asset_storage_id(parent_asset_id))
        return [
            row
            for row in (
                self.get_session(str(item.get("display_session_id") or "")) for item in rows
            )
            if row
        ]


def authorized_session_store(
    store: SessionStore, authority: EngagementAuthority
) -> AuthorizedSessionStore:
    if isinstance(store, AuthorizedSessionStore):
        if store.authority != authority:
            raise PermissionError("session store authority mismatch")
        return store
    return AuthorizedSessionStore(store, authority)
