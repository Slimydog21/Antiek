"""Engagement-spine store protocol and in-memory / JSON-file backends.

The spine never opens DuckDB directly — callers that want graph promotion
call ``insight_question.promote_*`` separately with the twin note text.
This keeps the engagement spine testable offline and composable with the
existing single-writer graph path.
"""

from __future__ import annotations

import json
import threading
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
    def put_document(self, document_id: str, doc: dict[str, Any]) -> None: ...
    def get_document(self, document_id: str) -> dict[str, Any] | None: ...


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

    def put_document(self, document_id: str, doc: dict[str, Any]) -> None:
        with self._lock:
            self._docs[document_id] = dict(doc)

    def get_document(self, document_id: str) -> dict[str, Any] | None:
        with self._lock:
            row = self._docs.get(document_id)
            return dict(row) if row is not None else None


@dataclass
class FileEngagementStore:
    """JSON-file durable store (one directory tree). Offline-safe."""

    root: Path

    def __post_init__(self) -> None:
        self.root = Path(self.root)
        (self.root / "spawns").mkdir(parents=True, exist_ok=True)
        (self.root / "twins").mkdir(parents=True, exist_ok=True)
        (self.root / "docs").mkdir(parents=True, exist_ok=True)

    def _spawn_path(self, spawn_id: str) -> Path:
        return self.root / "spawns" / f"{spawn_id}.json"

    def _twin_path(self, asset_id: str) -> Path:
        safe = asset_id.replace("/", "_")
        return self.root / "twins" / f"{safe}.json"

    def _doc_path(self, document_id: str) -> Path:
        safe = document_id.replace("/", "_")
        return self.root / "docs" / f"{safe}.json"

    def put_spawn(self, spawn: dict[str, Any]) -> None:
        path = self._spawn_path(spawn["spawn_id"])
        path.write_text(json.dumps(spawn, sort_keys=True, indent=2), encoding="utf-8")

    def get_spawn(self, spawn_id: str) -> dict[str, Any] | None:
        path = self._spawn_path(spawn_id)
        if not path.is_file():
            return None
        row = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(row, dict):
            raise ValueError(f"spawn file is not an object: {path}")
        return row

    def list_spawns(self, asset_id: str) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for path in sorted((self.root / "spawns").glob("*.json")):
            row = json.loads(path.read_text(encoding="utf-8"))
            if row.get("parent_asset_id") == asset_id:
                out.append(row)
        return out

    def put_twin(self, note: dict[str, Any]) -> None:
        path = self._twin_path(note["asset_id"])
        notes: list[dict[str, Any]] = []
        if path.is_file():
            notes = json.loads(path.read_text(encoding="utf-8"))
        replaced = False
        for i, existing in enumerate(notes):
            if existing.get("note_id") == note["note_id"]:
                notes[i] = note
                replaced = True
                break
        if not replaced:
            notes.append(note)
        path.write_text(json.dumps(notes, sort_keys=True, indent=2), encoding="utf-8")

    def list_twins(self, asset_id: str) -> list[dict[str, Any]]:
        path = self._twin_path(asset_id)
        if not path.is_file():
            return []
        return list(json.loads(path.read_text(encoding="utf-8")))

    def put_document(self, document_id: str, doc: dict[str, Any]) -> None:
        path = self._doc_path(document_id)
        path.write_text(json.dumps(doc, sort_keys=True, indent=2), encoding="utf-8")

    def get_document(self, document_id: str) -> dict[str, Any] | None:
        path = self._doc_path(document_id)
        if not path.is_file():
            return None
        row = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(row, dict):
            raise ValueError(f"document file is not an object: {path}")
        return row


def spawn_to_dict(obj: Any) -> dict[str, Any]:
    if hasattr(obj, "__dataclass_fields__"):
        return asdict(obj)
    raise TypeError(f"not a dataclass: {type(obj)!r}")
