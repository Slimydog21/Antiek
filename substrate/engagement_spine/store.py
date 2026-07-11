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

from substrate.durable_file_key import contained_legacy_json_path, durable_file_key


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
        return self.root / "spawns" / f"{durable_file_key(spawn_id)}.json"

    def _twin_path(self, asset_id: str) -> Path:
        return self.root / "twins" / f"{durable_file_key(asset_id)}.json"

    def _doc_path(self, document_id: str) -> Path:
        return self.root / "docs" / f"{durable_file_key(document_id)}.json"

    def _legacy_path(self, bucket: str, value: str) -> Path:
        """Address pre-hash slash-flattened files without permitting traversal."""

        path = contained_legacy_json_path(
            self.root / bucket, value, flatten_forward_slashes=True
        )
        if path is None:
            raise ValueError("legacy durable identifier escapes its store")
        return path

    def _legacy_spawn_path(self, spawn_id: str) -> Path | None:
        return contained_legacy_json_path(self.root / "spawns", spawn_id)

    def put_spawn(self, spawn: dict[str, Any]) -> None:
        path = self._spawn_path(spawn["spawn_id"])
        path.write_text(json.dumps(spawn, sort_keys=True, indent=2), encoding="utf-8")

    def get_spawn(self, spawn_id: str) -> dict[str, Any] | None:
        path = self._spawn_path(spawn_id)
        if not path.is_file():
            legacy = self._legacy_spawn_path(spawn_id)
            if legacy is None or not legacy.is_file():
                return None
            path = legacy
        data: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
        if data.get("spawn_id") != spawn_id:
            return None
        return data

    def list_spawns(self, asset_id: str) -> list[dict[str, Any]]:
        by_id: dict[str, dict[str, Any]] = {}
        for path in sorted((self.root / "spawns").glob("*.json")):
            row = json.loads(path.read_text(encoding="utf-8"))
            if row.get("parent_asset_id") == asset_id:
                by_id[str(row.get("spawn_id") or path.name)] = row
        return list(by_id.values())

    def put_twin(self, note: dict[str, Any]) -> None:
        path = self._twin_path(note["asset_id"])
        notes: list[dict[str, Any]] = []
        if path.is_file():
            notes = json.loads(path.read_text(encoding="utf-8"))
        else:
            legacy = self._legacy_path("twins", note["asset_id"])
            if legacy != path and legacy.is_file():
                legacy_notes = json.loads(legacy.read_text(encoding="utf-8"))
                notes = [
                    row
                    for row in legacy_notes
                    if row.get("asset_id") == note["asset_id"]
                ]
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
            path = self._legacy_path("twins", asset_id)
            if not path.is_file():
                return []
        rows: list[dict[str, Any]] = json.loads(path.read_text(encoding="utf-8"))
        return [row for row in rows if row.get("asset_id") == asset_id]

    def put_document(self, document_id: str, doc: dict[str, Any]) -> None:
        path = self._doc_path(document_id)
        path.write_text(json.dumps(doc, sort_keys=True, indent=2), encoding="utf-8")

    def get_document(self, document_id: str) -> dict[str, Any] | None:
        path = self._doc_path(document_id)
        used_legacy_path = False
        if not path.is_file():
            path = self._legacy_path("docs", document_id)
            if not path.is_file():
                return None
            used_legacy_path = True
        data: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
        embedded_id = data.get("document_id")
        if (used_legacy_path and embedded_id != document_id) or (
            embedded_id is not None and embedded_id != document_id
        ):
            return None
        return data


def spawn_to_dict(obj: Any) -> dict[str, Any]:
    if hasattr(obj, "__dataclass_fields__"):
        return asdict(obj)
    raise TypeError(f"not a dataclass: {type(obj)!r}")
