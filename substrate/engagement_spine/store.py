"""Engagement-spine store protocol and in-memory / JSON-file backends.

The spine never opens DuckDB directly — callers that want graph promotion
call ``insight_question.promote_*`` separately with the twin note text.
This keeps the engagement spine testable offline and composable with the
existing single-writer graph path.
"""

from __future__ import annotations

import fcntl
import hashlib
import hmac
import json
import os
import re
import threading
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

_DOCUMENT_REVISION_DOMAIN = b"antiek.engagement.parent-revision.v1\0"
_LOGICAL_PREFIX = re.compile(r"^[a-z][a-z0-9_]{1,63}$")
_OWNED_LISTING_BYTE_CAP = 32_000_000


def document_revision_sha256(doc: dict[str, Any] | None) -> str:
    """Content revision used by every canonical document CAS writer."""
    payload = json.dumps(doc or {}, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(_DOCUMENT_REVISION_DOMAIN + payload).hexdigest()


def owned_document_id(owner_id: str, logical_document_id: str) -> str:
    """Map a logical document into an account namespace without leaking identity."""
    owner = (owner_id or "").strip()
    if not owner:
        raise ValueError("owner_id is required")
    if owner == "__operator__":
        return logical_document_id
    digest = hashlib.sha256(f"antiek-owner:v1:{owner}".encode()).hexdigest()[:16]
    return f"owner_{digest}_{logical_document_id}"


def _document_owner_matches(row: dict[str, Any], owner_id: str) -> bool:
    """Fail closed on embedded-owner drift; operator alone may adopt legacy rows."""
    embedded = row.get("owner_id")
    if owner_id == "__operator__" and embedded in (None, "__operator__"):
        return True
    return embedded == owner_id


def _validate_owned_listing(owner_id: str, logical_prefix: str, limit: int) -> None:
    if not owner_id.strip():
        raise ValueError("owner_id is required")
    if _LOGICAL_PREFIX.fullmatch(logical_prefix) is None:
        raise ValueError("logical document prefix is outside the listing contract")
    if not 1 <= limit <= 101:
        raise ValueError("owned document listing limit is outside the contract")


@runtime_checkable
class EngagementStore(Protocol):
    def put_spawn(self, spawn: dict[str, Any]) -> None: ...
    def get_spawn(self, spawn_id: str) -> dict[str, Any] | None: ...
    def list_spawns(self, asset_id: str) -> list[dict[str, Any]]: ...
    def put_twin(self, note: dict[str, Any]) -> None: ...
    def list_twins(self, asset_id: str, owner_id: str = "__operator__") -> list[dict[str, Any]]: ...
    def put_document(self, document_id: str, doc: dict[str, Any]) -> None: ...
    def get_document(self, document_id: str) -> dict[str, Any] | None: ...
    def compare_and_set_document(
        self, document_id: str, expected_sha256: str, doc: dict[str, Any]
    ) -> bool: ...
    def get_owned_spawn(self, spawn_id: str, owner_id: str) -> dict[str, Any] | None: ...
    def mutate_owned_spawn(
        self,
        spawn_id: str,
        owner_id: str,
        mutation: Callable[[dict[str, Any]], dict[str, Any]],
    ) -> dict[str, Any]: ...
    def get_owned_document(
        self, logical_document_id: str, owner_id: str
    ) -> dict[str, Any] | None: ...
    def mutate_owned_document(
        self,
        logical_document_id: str,
        owner_id: str,
        mutation: Callable[[dict[str, Any] | None], dict[str, Any]],
    ) -> dict[str, Any]: ...
    def list_owned_documents(
        self,
        owner_id: str,
        *,
        logical_prefix: str,
        after_logical_id: str | None,
        limit: int,
    ) -> list[tuple[str, dict[str, Any]]]: ...


@dataclass
class InMemoryEngagementStore:
    """Thread-safe in-process store for tests and single-process runners."""

    _spawns: dict[str, dict[str, Any]] = field(default_factory=dict)
    _twins: dict[tuple[str, str], list[dict[str, Any]]] = field(default_factory=dict)
    _docs: dict[str, dict[str, Any]] = field(default_factory=dict)
    _lock: threading.RLock = field(default_factory=threading.RLock)

    def put_spawn(self, spawn: dict[str, Any]) -> None:
        with self._lock:
            self._spawns[spawn["spawn_id"]] = dict(spawn)

    def get_spawn(self, spawn_id: str) -> dict[str, Any] | None:
        with self._lock:
            row = self._spawns.get(spawn_id)
            return dict(row) if row is not None else None

    def get_owned_spawn(self, spawn_id: str, owner_id: str) -> dict[str, Any] | None:
        with self._lock:
            row = self._spawns.get(spawn_id)
            if row is None or row.get("owner_id") != owner_id:
                return None
            return dict(row)

    def mutate_owned_spawn(
        self,
        spawn_id: str,
        owner_id: str,
        mutation: Callable[[dict[str, Any]], dict[str, Any]],
    ) -> dict[str, Any]:
        with self._lock:
            current = self._spawns.get(spawn_id)
            if current is None or current.get("owner_id") != owner_id:
                raise KeyError(spawn_id)
            updated = mutation(dict(current))
            if updated.get("spawn_id") != spawn_id or updated.get("owner_id") != owner_id:
                raise ValueError("owned spawn mutation cannot change identity or owner")
            self._spawns[spawn_id] = dict(updated)
            return dict(updated)

    def list_spawns(self, asset_id: str) -> list[dict[str, Any]]:
        with self._lock:
            return [dict(s) for s in self._spawns.values() if s.get("parent_asset_id") == asset_id]

    def put_twin(self, note: dict[str, Any]) -> None:
        with self._lock:
            owner = str(note.get("owner_id") or "__operator__")
            bucket = self._twins.setdefault((owner, note["asset_id"]), [])
            # Idempotent on note_id
            for i, existing in enumerate(bucket):
                if existing.get("note_id") == note["note_id"]:
                    bucket[i] = dict(note)
                    return
            bucket.append(dict(note))

    def list_twins(self, asset_id: str, owner_id: str = "__operator__") -> list[dict[str, Any]]:
        with self._lock:
            return [dict(n) for n in self._twins.get((owner_id, asset_id), [])]

    def put_document(self, document_id: str, doc: dict[str, Any]) -> None:
        with self._lock:
            self._docs[document_id] = dict(doc)

    def get_document(self, document_id: str) -> dict[str, Any] | None:
        with self._lock:
            row = self._docs.get(document_id)
            return dict(row) if row is not None else None

    def get_owned_document(self, logical_document_id: str, owner_id: str) -> dict[str, Any] | None:
        row = self.get_document(owned_document_id(owner_id, logical_document_id))
        if row is None or not _document_owner_matches(row, owner_id):
            return None
        return row

    def mutate_owned_document(
        self,
        logical_document_id: str,
        owner_id: str,
        mutation: Callable[[dict[str, Any] | None], dict[str, Any]],
    ) -> dict[str, Any]:
        document_id = owned_document_id(owner_id, logical_document_id)
        with self._lock:
            current = self._docs.get(document_id)
            if current is not None and not _document_owner_matches(current, owner_id):
                raise ValueError("owned document has conflicting embedded owner")
            updated = mutation(dict(current) if current is not None else None)
            if updated.get("owner_id") not in (None, owner_id):
                raise ValueError("owned document mutation cannot change owner")
            updated = {**updated, "owner_id": owner_id}
            self._docs[document_id] = dict(updated)
            return dict(updated)

    def list_owned_documents(
        self,
        owner_id: str,
        *,
        logical_prefix: str,
        after_logical_id: str | None,
        limit: int,
    ) -> list[tuple[str, dict[str, Any]]]:
        _validate_owned_listing(owner_id, logical_prefix, limit)
        physical_prefix = owned_document_id(owner_id, logical_prefix)
        physical_after = (
            owned_document_id(owner_id, after_logical_id) if after_logical_id is not None else None
        )
        with self._lock:
            identities = sorted(
                identity for identity in self._docs if identity.startswith(physical_prefix)
            )
            if physical_after is not None:
                try:
                    cursor_index = identities.index(physical_after)
                except ValueError as exc:
                    raise ValueError("owned document cursor is not available") from exc
                identities = identities[cursor_index + 1 :]
            rows: list[tuple[str, dict[str, Any]]] = []
            encoded_bytes = 0
            for identity in identities[:limit]:
                row = self._docs[identity]
                encoded_bytes += len(
                    json.dumps(row, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
                )
                if encoded_bytes > _OWNED_LISTING_BYTE_CAP:
                    raise ValueError("owned document listing exceeds byte cap")
                if not _document_owner_matches(row, owner_id):
                    raise ValueError("owned document listing requires reconciliation")
                logical_id = (
                    identity
                    if owner_id == "__operator__"
                    else identity.removeprefix(physical_prefix.removesuffix(logical_prefix))
                )
                rows.append((logical_id, dict(row)))
            return rows

    def compare_and_set_document(
        self, document_id: str, expected_sha256: str, doc: dict[str, Any]
    ) -> bool:
        with self._lock:
            current = self._docs.get(document_id)
            if not hmac.compare_digest(document_revision_sha256(current), expected_sha256):
                return False
            self._docs[document_id] = dict(doc)
            return True


@dataclass
class FileEngagementStore:
    """JSON-file durable store (one directory tree). Offline-safe."""

    root: Path
    _lock: threading.RLock = field(default_factory=threading.RLock, init=False)

    def __post_init__(self) -> None:
        self.root = Path(self.root)
        (self.root / "spawns").mkdir(parents=True, exist_ok=True)
        (self.root / "twins").mkdir(parents=True, exist_ok=True)
        (self.root / "docs").mkdir(parents=True, exist_ok=True)

    def _spawn_path(self, spawn_id: str) -> Path:
        return self.root / "spawns" / f"{spawn_id}.json"

    def _twin_path(self, asset_id: str, owner_id: str = "__operator__") -> Path:
        logical = owned_document_id(owner_id, asset_id)
        safe = logical.replace("/", "_")
        return self.root / "twins" / f"{safe}.json"

    def _doc_path(self, document_id: str) -> Path:
        safe = document_id.replace("/", "_")
        return self.root / "docs" / f"{safe}.json"

    def _write_document_unlocked(self, path: Path, doc: Any) -> None:
        temp = path.with_suffix(f".{os.getpid()}.{threading.get_ident()}.tmp")
        try:
            with temp.open("w", encoding="utf-8") as handle:
                json.dump(doc, handle, sort_keys=True, indent=2)
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

    def put_spawn(self, spawn: dict[str, Any]) -> None:
        path = self._spawn_path(spawn["spawn_id"])
        lock_path = path.with_suffix(".lock")
        with self._lock, lock_path.open("a+b") as lock_file:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
            self._write_document_unlocked(path, spawn)

    def get_spawn(self, spawn_id: str) -> dict[str, Any] | None:
        path = self._spawn_path(spawn_id)
        if not path.is_file():
            return None
        data: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
        return data

    def get_owned_document(self, logical_document_id: str, owner_id: str) -> dict[str, Any] | None:
        row = self.get_document(owned_document_id(owner_id, logical_document_id))
        if row is None or not _document_owner_matches(row, owner_id):
            return None
        return row

    def mutate_owned_document(
        self,
        logical_document_id: str,
        owner_id: str,
        mutation: Callable[[dict[str, Any] | None], dict[str, Any]],
    ) -> dict[str, Any]:
        document_id = owned_document_id(owner_id, logical_document_id)
        path = self._doc_path(document_id)
        lock_path = path.with_suffix(".lock")
        with self._lock, lock_path.open("a+b") as lock_file:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
            current: dict[str, Any] | None = None
            if path.is_file():
                decoded = json.loads(path.read_text(encoding="utf-8"))
                if not isinstance(decoded, dict):
                    raise ValueError("durable document must be a JSON object")
                current = decoded
            if current is not None and not _document_owner_matches(current, owner_id):
                raise ValueError("owned document has conflicting embedded owner")
            updated = mutation(dict(current) if current is not None else None)
            if updated.get("owner_id") not in (None, owner_id):
                raise ValueError("owned document mutation cannot change owner")
            updated = {**updated, "owner_id": owner_id}
            self._write_document_unlocked(path, updated)
            return dict(updated)

    def list_owned_documents(
        self,
        owner_id: str,
        *,
        logical_prefix: str,
        after_logical_id: str | None,
        limit: int,
    ) -> list[tuple[str, dict[str, Any]]]:
        """Keyset-page owner rows by safe logical filename prefix.

        Directory enumeration may inspect matching names, but only the requested
        ``limit`` rows are deserialized. Canonical rows are discovery authority,
        so a crash after row replacement needs no second index repair.
        """
        _validate_owned_listing(owner_id, logical_prefix, limit)
        physical_prefix = owned_document_id(owner_id, logical_prefix)
        physical_after = (
            owned_document_id(owner_id, after_logical_id) if after_logical_id is not None else None
        )
        paths = sorted((self.root / "docs").glob(f"{physical_prefix}*.json"))
        identities = [path.stem for path in paths]
        if physical_after is not None:
            try:
                cursor_index = identities.index(physical_after)
            except ValueError as exc:
                raise ValueError("owned document cursor is not available") from exc
            paths = paths[cursor_index + 1 :]
        rows: list[tuple[str, dict[str, Any]]] = []
        encoded_bytes = 0
        for path in paths[:limit]:
            encoded_bytes += path.stat().st_size
            if encoded_bytes > _OWNED_LISTING_BYTE_CAP:
                raise ValueError("owned document listing exceeds byte cap")
            decoded = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(decoded, dict) or not _document_owner_matches(decoded, owner_id):
                raise ValueError("owned document listing requires reconciliation")
            logical_id = (
                path.stem
                if owner_id == "__operator__"
                else path.stem.removeprefix(physical_prefix.removesuffix(logical_prefix))
            )
            rows.append((logical_id, decoded))
        return rows

    def get_owned_spawn(self, spawn_id: str, owner_id: str) -> dict[str, Any] | None:
        row = self.get_spawn(spawn_id)
        if row is None or row.get("owner_id") != owner_id:
            return None
        return row

    def mutate_owned_spawn(
        self,
        spawn_id: str,
        owner_id: str,
        mutation: Callable[[dict[str, Any]], dict[str, Any]],
    ) -> dict[str, Any]:
        path = self._spawn_path(spawn_id)
        lock_path = path.with_suffix(".lock")
        with self._lock, lock_path.open("a+b") as lock_file:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
            if not path.is_file():
                raise KeyError(spawn_id)
            current = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(current, dict) or current.get("owner_id") != owner_id:
                raise KeyError(spawn_id)
            updated = mutation(dict(current))
            if updated.get("spawn_id") != spawn_id or updated.get("owner_id") != owner_id:
                raise ValueError("owned spawn mutation cannot change identity or owner")
            self._write_document_unlocked(path, updated)
            return dict(updated)

    def list_spawns(self, asset_id: str) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for path in sorted((self.root / "spawns").glob("*.json")):
            row = json.loads(path.read_text(encoding="utf-8"))
            if row.get("parent_asset_id") == asset_id:
                out.append(row)
        return out

    def put_twin(self, note: dict[str, Any]) -> None:
        owner = str(note.get("owner_id") or "__operator__")
        path = self._twin_path(note["asset_id"], owner)
        lock_path = path.with_suffix(".lock")
        with self._lock, lock_path.open("a+b") as lock_file:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
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
            self._write_document_unlocked(path, notes)

    def list_twins(self, asset_id: str, owner_id: str = "__operator__") -> list[dict[str, Any]]:
        path = self._twin_path(asset_id, owner_id)
        if not path.is_file():
            return []
        return list(json.loads(path.read_text(encoding="utf-8")))

    def put_document(self, document_id: str, doc: dict[str, Any]) -> None:
        path = self._doc_path(document_id)
        lock_path = path.with_suffix(".lock")
        with self._lock, lock_path.open("a+b") as lock_file:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
            self._write_document_unlocked(path, doc)
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)

    def get_document(self, document_id: str) -> dict[str, Any] | None:
        path = self._doc_path(document_id)
        if not path.is_file():
            return None
        data: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
        return data

    def compare_and_set_document(
        self, document_id: str, expected_sha256: str, doc: dict[str, Any]
    ) -> bool:
        path = self._doc_path(document_id)
        lock_path = path.with_suffix(".lock")
        with self._lock, lock_path.open("a+b") as lock_file:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
            current: dict[str, Any] | None = None
            if path.is_file():
                decoded = json.loads(path.read_text(encoding="utf-8"))
                if not isinstance(decoded, dict):
                    raise ValueError("durable document must be a JSON object")
                current = decoded
            if not hmac.compare_digest(document_revision_sha256(current), expected_sha256):
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
                return False
            self._write_document_unlocked(path, doc)
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
            return True


def spawn_to_dict(obj: Any) -> dict[str, Any]:
    if hasattr(obj, "__dataclass_fields__"):
        return asdict(obj)
    raise TypeError(f"not a dataclass: {type(obj)!r}")
