"""Engagement-spine store protocol and in-memory / JSON-file backends.

The spine never opens DuckDB directly — callers that want graph promotion
call ``insight_question.promote_*`` separately with the twin note text.
This keeps the engagement spine testable offline and composable with the
existing single-writer graph path.
"""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
import tempfile
import threading
from collections.abc import Iterator
from contextlib import AbstractContextManager, contextmanager
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from .authority import ENGAGEMENT_AUTHORITY_VERSION, EngagementAuthority

_IMMUTABLE_DOCUMENT_KINDS = frozenset(
    {"claim_challenge_acceptance", "claim_challenge_reversal"}
)


@runtime_checkable
class EngagementStore(Protocol):
    def put_spawn(self, spawn: dict[str, Any]) -> None: ...
    def get_spawn(self, spawn_id: str) -> dict[str, Any] | None: ...
    def list_spawns(self, asset_id: str) -> list[dict[str, Any]]: ...
    def put_twin(self, note: dict[str, Any]) -> None: ...
    def list_twins(self, asset_id: str) -> list[dict[str, Any]]: ...
    def replace_twins_for_origin(
        self, asset_id: str, origin: str, notes: list[dict[str, Any]]
    ) -> None: ...
    def put_document(self, document_id: str, doc: dict[str, Any]) -> None: ...
    def claim_document(self, document_id: str, doc: dict[str, Any]) -> bool: ...
    def get_document(self, document_id: str) -> dict[str, Any] | None: ...
    def lock_document(self, document_id: str) -> AbstractContextManager[None]: ...


@dataclass
class InMemoryEngagementStore:
    """Thread-safe in-process store for tests and single-process runners."""

    _spawns: dict[str, dict[str, Any]] = field(default_factory=dict)
    _twins: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    _docs: dict[str, dict[str, Any]] = field(default_factory=dict)
    _lock: threading.RLock = field(default_factory=threading.RLock)

    def put_spawn(self, spawn: dict[str, Any]) -> None:
        with self._lock:
            self._spawns[spawn["spawn_id"]] = dict(spawn)

    def get_spawn(self, spawn_id: str) -> dict[str, Any] | None:
        with self._lock:
            row = self._spawns.get(spawn_id)
            return dict(row) if row is not None else None

    def list_spawns(self, asset_id: str) -> list[dict[str, Any]]:
        with self._lock:
            return [dict(s) for s in self._spawns.values() if s.get("parent_asset_id") == asset_id]

    def put_twin(self, note: dict[str, Any]) -> None:
        with self._lock:
            bucket = self._twins.setdefault(note["asset_id"], [])
            # Idempotent on note_id
            for i, existing in enumerate(bucket):
                if existing.get("note_id") == note["note_id"]:
                    bucket[i] = dict(note)
                    return
            bucket.append(dict(note))

    def list_twins(self, asset_id: str) -> list[dict[str, Any]]:
        with self._lock:
            return [dict(n) for n in self._twins.get(asset_id, [])]

    def replace_twins_for_origin(
        self, asset_id: str, origin: str, notes: list[dict[str, Any]]
    ) -> None:
        with self._lock:
            retained = [
                dict(note) for note in self._twins.get(asset_id, []) if note.get("origin") != origin
            ]
            by_id = {str(note["note_id"]): dict(note) for note in retained + notes}
            self._twins[asset_id] = list(by_id.values())

    def put_document(self, document_id: str, doc: dict[str, Any]) -> None:
        with self._lock:
            self._docs[document_id] = dict(doc)

    def claim_document(self, document_id: str, doc: dict[str, Any]) -> bool:
        with self._lock:
            if document_id in self._docs:
                return False
            self._docs[document_id] = dict(doc)
            return True

    def get_document(self, document_id: str) -> dict[str, Any] | None:
        with self._lock:
            row = self._docs.get(document_id)
            return dict(row) if row is not None else None

    @contextmanager
    def lock_document(self, document_id: str) -> Iterator[None]:
        del document_id
        with self._lock:
            yield


@dataclass
class FileEngagementStore:
    """JSON-file durable store (one directory tree). Offline-safe."""

    root: Path
    _lock: threading.RLock = field(default_factory=threading.RLock, init=False, repr=False)
    _document_lock_state: threading.local = field(
        default_factory=threading.local, init=False, repr=False
    )

    def __post_init__(self) -> None:
        self.root = Path(self.root)
        (self.root / "spawns").mkdir(parents=True, exist_ok=True)
        (self.root / "twins").mkdir(parents=True, exist_ok=True)
        (self.root / "docs").mkdir(parents=True, exist_ok=True)

    def _spawn_path(self, spawn_id: str) -> Path:
        digest = hashlib.sha256(spawn_id.encode("utf-8")).hexdigest()
        return self.root / "spawns" / f"spawn-{digest}.json"

    def _legacy_spawn_path(self, spawn_id: str) -> Path | None:
        if (
            not spawn_id
            or spawn_id in {".", ".."}
            or "/" in spawn_id
            or "\\" in spawn_id
            or "\x00" in spawn_id
            or len(spawn_id.encode("utf-8")) > 200
        ):
            return None
        return self.root / "spawns" / f"{spawn_id}.json"

    def _twin_path(self, asset_id: str) -> Path:
        digest = hashlib.sha256(asset_id.encode("utf-8")).hexdigest()
        return self.root / "twins" / f"asset-{digest}.json"

    def _legacy_twin_path(self, asset_id: str) -> Path | None:
        filename = f"{asset_id.replace('/', '_')}.json"
        if "\x00" in filename or len(filename.encode("utf-8")) > 240:
            return None
        return self.root / "twins" / filename

    @contextmanager
    def _twin_file_lock(self, asset_id: str) -> Iterator[None]:
        lock_path = self._twin_path(asset_id).with_suffix(".lock")
        with lock_path.open("a+b") as handle:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)

    @staticmethod
    def _read_exact_twins(path: Path, asset_id: str) -> list[dict[str, Any]]:
        if not path.is_file() or path.is_symlink():
            return []
        try:
            decoded = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return []
        if not isinstance(decoded, list):
            return []
        return [
            dict(note)
            for note in decoded
            if isinstance(note, dict) and note.get("asset_id") == asset_id
        ]

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

    def _doc_path(self, document_id: str) -> Path:
        safe = document_id.replace("/", "_")
        return self.root / "docs" / f"{safe}.json"

    @contextmanager
    def lock_document(self, document_id: str) -> Iterator[None]:
        lock_path = self._doc_path(document_id).with_suffix(".lock")
        key = str(lock_path)
        with self._lock:
            depths = getattr(self._document_lock_state, "depths", None)
            if depths is None:
                depths = {}
                self._document_lock_state.depths = depths
            if depths.get(key, 0):
                depths[key] += 1
                try:
                    yield
                finally:
                    depths[key] -= 1
                return
            with lock_path.open("a+b") as handle:
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
                depths[key] = 1
                try:
                    yield
                finally:
                    depths.pop(key, None)
                    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)

    def put_spawn(self, spawn: dict[str, Any]) -> None:
        path = self._spawn_path(spawn["spawn_id"])
        with self._lock:
            self._atomic_write_json(path, spawn)

    def get_spawn(self, spawn_id: str) -> dict[str, Any] | None:
        try:
            return self.get_spawn_strict(spawn_id)
        except RuntimeError:
            return None

    def get_spawn_strict(self, spawn_id: str) -> dict[str, Any] | None:
        """Read one spawn while preserving corrupt/unavailable storage as an error."""

        path = self._spawn_path(spawn_id)
        if path.is_symlink() or (path.exists() and not path.is_file()):
            raise RuntimeError("stored engagement spawn is unsafe")
        if not path.is_file():
            legacy = self._legacy_spawn_path(spawn_id)
            if legacy is None:
                return None
            if legacy.is_symlink() or (legacy.exists() and not legacy.is_file()):
                raise RuntimeError("stored engagement spawn is unsafe")
            if not legacy.is_file():
                return None
            path = legacy
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise RuntimeError("stored engagement spawn is unavailable or corrupt") from exc
        if not isinstance(data, dict):
            raise RuntimeError("stored engagement spawn is corrupt")
        return data if data.get("spawn_id") == spawn_id else None

    def list_spawns(self, asset_id: str) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for path in sorted((self.root / "spawns").glob("*.json")):
            if path.is_symlink():
                continue
            try:
                row = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if not isinstance(row, dict):
                continue
            if row.get("parent_asset_id") == asset_id:
                out.append(row)
        return out

    def put_twin(self, note: dict[str, Any]) -> None:
        asset_id = str(note["asset_id"])
        path = self._twin_path(asset_id)
        with self._lock, self._twin_file_lock(asset_id):
            notes = self._load_twins_for_write(asset_id, path)
            for index, existing in enumerate(notes):
                if existing.get("note_id") == note["note_id"]:
                    notes[index] = dict(note)
                    break
            else:
                notes.append(dict(note))
            self._atomic_write_json(path, notes)

    def _load_twins_for_write(self, asset_id: str, path: Path) -> list[dict[str, Any]]:
        notes = self._read_exact_twins(path, asset_id)
        legacy = self._legacy_twin_path(asset_id)
        if not path.is_file() and legacy is not None:
            notes = self._read_exact_twins(legacy, asset_id)
        return notes

    def replace_twins_for_origin(
        self, asset_id: str, origin: str, notes: list[dict[str, Any]]
    ) -> None:
        path = self._twin_path(asset_id)
        with self._lock, self._twin_file_lock(asset_id):
            current = self._load_twins_for_write(asset_id, path)
            retained = [note for note in current if note.get("origin") != origin]
            by_id = {str(note["note_id"]): dict(note) for note in retained + notes}
            self._atomic_write_json(path, list(by_id.values()))

    def list_twins(self, asset_id: str) -> list[dict[str, Any]]:
        with self._lock:
            path = self._twin_path(asset_id)
            if path.is_file():
                return self._read_exact_twins(path, asset_id)
            legacy = self._legacy_twin_path(asset_id)
            return self._read_exact_twins(legacy, asset_id) if legacy is not None else []

    def put_document(self, document_id: str, doc: dict[str, Any]) -> None:
        path = self._doc_path(document_id)
        with self.lock_document(document_id):
            self._atomic_write_json(path, doc)

    def claim_document(self, document_id: str, doc: dict[str, Any]) -> bool:
        path = self._doc_path(document_id)
        with self._lock, self.lock_document(document_id):
            if path.exists():
                return False
            self._atomic_write_json(path, doc)
            return True

    def get_document(self, document_id: str) -> dict[str, Any] | None:
        try:
            return self.get_document_strict(document_id)
        except RuntimeError:
            return None

    def get_document_strict(self, document_id: str) -> dict[str, Any] | None:
        """Read one document while preserving corrupt/unavailable storage as an error."""

        path = self._doc_path(document_id)
        if path.is_symlink() or (path.exists() and not path.is_file()):
            raise RuntimeError("stored engagement document is unsafe")
        if not path.is_file():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise RuntimeError("stored engagement document is unavailable or corrupt") from exc
        if not isinstance(data, dict):
            raise RuntimeError("stored engagement document is corrupt")
        return data


def spawn_to_dict(obj: Any) -> dict[str, Any]:
    if hasattr(obj, "__dataclass_fields__"):
        return asdict(obj)
    raise TypeError(f"not a dataclass: {type(obj)!r}")


@dataclass(frozen=True)
class AuthorizedEngagementStore:
    """Authority-enforcing facade over legacy storage primitives.

    Composite opaque storage keys prevent same-display collisions. Embedded
    authority fields are validated on every read so path names are not the
    security boundary.
    """

    base: EngagementStore
    authority: EngagementAuthority

    def _asset_storage_id(self, display_id: str) -> str:
        return self.authority.storage_id("asset", display_id)

    def _document_storage_id(self, display_id: str) -> str:
        return self.authority.storage_id("document", display_id)

    def _spawn_storage_id(self, display_id: str) -> str:
        return self.authority.storage_id("spawn", display_id)

    def _stamp(self, row: dict[str, Any]) -> dict[str, Any]:
        stamped = dict(row)
        stamped["engagement_authority_version"] = ENGAGEMENT_AUTHORITY_VERSION
        stamped["owner_account_digest"] = self.authority.account_digest
        stamped["engagement_key_id"] = self.authority.key_id
        return stamped

    def _valid_row(self, row: dict[str, Any] | None) -> bool:
        return bool(
            row
            and row.get("engagement_authority_version") == ENGAGEMENT_AUTHORITY_VERSION
            and self.authority.owns_digest(row.get("owner_account_digest"))
            and row.get("engagement_key_id") == self.authority.key_id
        )

    def put_spawn(self, spawn: dict[str, Any]) -> None:
        row = self._stamp(spawn)
        display_spawn = str(row["spawn_id"])
        display_asset = str(row["parent_asset_id"])
        row["display_spawn_id"] = display_spawn
        row["spawn_id"] = self._spawn_storage_id(display_spawn)
        row["display_parent_asset_id"] = display_asset
        row["parent_asset_id"] = self._asset_storage_id(display_asset)
        self.base.put_spawn(row)

    def get_spawn(self, spawn_id: str) -> dict[str, Any] | None:
        storage_id = self._spawn_storage_id(spawn_id)
        row = self.base.get_spawn(storage_id)
        if not self._valid_row(row):
            return None
        assert row is not None
        if row.get("spawn_id") != storage_id or row.get("display_spawn_id") != spawn_id:
            return None
        display_asset = row.get("display_parent_asset_id")
        if not isinstance(display_asset, str) or row.get(
            "parent_asset_id"
        ) != self._asset_storage_id(display_asset):
            return None
        out = dict(row)
        out["spawn_id"] = spawn_id
        out["parent_asset_id"] = display_asset
        return out

    def get_spawn_strict(self, spawn_id: str) -> dict[str, Any] | None:
        storage_id = self._spawn_storage_id(spawn_id)
        strict = getattr(self.base, "get_spawn_strict", None)
        row = strict(storage_id) if callable(strict) else self.base.get_spawn(storage_id)
        if row is None:
            return None
        if not self._valid_row(row):
            raise RuntimeError("stored engagement spawn authority is corrupt")
        assert row is not None
        if row.get("spawn_id") != storage_id or row.get("display_spawn_id") != spawn_id:
            raise RuntimeError("stored engagement spawn identity is corrupt")
        display_asset = row.get("display_parent_asset_id")
        if not isinstance(display_asset, str) or row.get(
            "parent_asset_id"
        ) != self._asset_storage_id(display_asset):
            raise RuntimeError("stored engagement spawn parent identity is corrupt")
        out = dict(row)
        out["spawn_id"] = spawn_id
        out["parent_asset_id"] = display_asset
        return out

    def list_spawns(self, asset_id: str) -> list[dict[str, Any]]:
        rows = self.base.list_spawns(self._asset_storage_id(asset_id))
        return [
            row
            for row in (self.get_spawn(str(item.get("display_spawn_id") or "")) for item in rows)
            if row
        ]

    def put_twin(self, note: dict[str, Any]) -> None:
        row = self._stamp(note)
        display_asset = str(row["asset_id"])
        row["display_asset_id"] = display_asset
        row["asset_id"] = self._asset_storage_id(display_asset)
        self.base.put_twin(row)

    def list_twins(self, asset_id: str) -> list[dict[str, Any]]:
        storage_id = self._asset_storage_id(asset_id)
        out: list[dict[str, Any]] = []
        for row in self.base.list_twins(storage_id):
            if not self._valid_row(row) or row.get("display_asset_id") != asset_id:
                continue
            restored = dict(row)
            restored["asset_id"] = asset_id
            out.append(restored)
        return out

    def replace_twins_for_origin(
        self, asset_id: str, origin: str, notes: list[dict[str, Any]]
    ) -> None:
        storage_id = self._asset_storage_id(asset_id)
        stamped: list[dict[str, Any]] = []
        for note in notes:
            row = self._stamp(note)
            if row.get("asset_id") != asset_id:
                raise ValueError("twin asset identity is invalid")
            row["display_asset_id"] = asset_id
            row["asset_id"] = storage_id
            stamped.append(row)
        self.base.replace_twins_for_origin(storage_id, origin, stamped)

    def put_document(self, document_id: str, doc: dict[str, Any]) -> None:
        with self.lock_document(document_id):
            existing = self.get_document(document_id)
            if existing is not None and existing.get("kind") in _IMMUTABLE_DOCUMENT_KINDS:
                raise ValueError("immutable engagement document cannot be overwritten")
            row = self._stamp(doc)
            row["display_document_id"] = document_id
            self.base.put_document(self._document_storage_id(document_id), row)

    def claim_document(self, document_id: str, doc: dict[str, Any]) -> bool:
        row = self._stamp(doc)
        row["display_document_id"] = document_id
        return self.base.claim_document(self._document_storage_id(document_id), row)

    def get_document(self, document_id: str) -> dict[str, Any] | None:
        row = self.base.get_document(self._document_storage_id(document_id))
        if not self._valid_row(row) or row.get("display_document_id") != document_id:
            return None
        return dict(row)

    def get_document_strict(self, document_id: str) -> dict[str, Any] | None:
        storage_id = self._document_storage_id(document_id)
        strict = getattr(self.base, "get_document_strict", None)
        row = strict(storage_id) if callable(strict) else self.base.get_document(storage_id)
        if row is None:
            return None
        if not self._valid_row(row) or row.get("display_document_id") != document_id:
            raise RuntimeError("stored engagement document authority is corrupt")
        return dict(row)

    def lock_document(self, document_id: str) -> AbstractContextManager[None]:
        return self.base.lock_document(self._document_storage_id(document_id))


def authorized_store(
    store: EngagementStore, authority: EngagementAuthority
) -> AuthorizedEngagementStore:
    if isinstance(store, AuthorizedEngagementStore):
        if store.authority != authority:
            raise PermissionError("engagement store authority mismatch")
        return store
    return AuthorizedEngagementStore(store, authority)
