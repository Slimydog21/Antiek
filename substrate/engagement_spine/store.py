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
            return [
                dict(s)
                for s in self._spawns.values()
                if s.get("parent_asset_id") == asset_id
            ]

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
                dict(note)
                for note in self._twins.get(asset_id, [])
                if note.get("origin") != origin
            ]
            by_id = {str(note["note_id"]): dict(note) for note in retained + notes}
            self._twins[asset_id] = list(by_id.values())

    def put_document(self, document_id: str, doc: dict[str, Any]) -> None:
        with self._lock:
            self._docs[document_id] = dict(doc)

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

    def __post_init__(self) -> None:
        self.root = Path(self.root)
        (self.root / "spawns").mkdir(parents=True, exist_ok=True)
        (self.root / "twins").mkdir(parents=True, exist_ok=True)
        (self.root / "docs").mkdir(parents=True, exist_ok=True)

    def _spawn_path(self, spawn_id: str) -> Path:
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
        if not path.is_file():
            return []
        decoded = json.loads(path.read_text(encoding="utf-8"))
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
        with self._lock, lock_path.open("a+b") as handle:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)

    def put_spawn(self, spawn: dict[str, Any]) -> None:
        path = self._spawn_path(spawn["spawn_id"])
        path.write_text(json.dumps(spawn, sort_keys=True, indent=2), encoding="utf-8")

    def get_spawn(self, spawn_id: str) -> dict[str, Any] | None:
        path = self._spawn_path(spawn_id)
        if not path.is_file():
            return None
        data: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
        return data

    def list_spawns(self, asset_id: str) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for path in sorted((self.root / "spawns").glob("*.json")):
            row = json.loads(path.read_text(encoding="utf-8"))
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
            retained = [
                note
                for note in current
                if note.get("origin") != origin
            ]
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

    def get_document(self, document_id: str) -> dict[str, Any] | None:
        path = self._doc_path(document_id)
        if not path.is_file():
            return None
        data: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
        return data


def spawn_to_dict(obj: Any) -> dict[str, Any]:
    if hasattr(obj, "__dataclass_fields__"):
        return asdict(obj)
    raise TypeError(f"not a dataclass: {type(obj)!r}")
