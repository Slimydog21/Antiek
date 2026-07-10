"""Account library + host store (pure, offline)."""

from __future__ import annotations

import json
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class HostStore(Protocol):
    def put_document(self, document_id: str, doc: dict[str, Any]) -> None: ...
    def get_document(self, document_id: str) -> dict[str, Any] | None: ...
    def put_membership(self, owner_id: str, document_id: str) -> None: ...
    def list_membership(self, owner_id: str) -> list[str]: ...
    def put_receipt(self, receipt_id: str, receipt: dict[str, Any]) -> None: ...
    def get_receipt(self, receipt_id: str) -> dict[str, Any] | None: ...


@dataclass
class InMemoryHostStore:
    """Thread-safe in-process store for tests and single-process runners."""

    _docs: dict[str, dict[str, Any]] = field(default_factory=dict)
    _lib: dict[str, list[str]] = field(default_factory=dict)
    _receipts: dict[str, dict[str, Any]] = field(default_factory=dict)
    _lock: threading.RLock = field(default_factory=threading.RLock)

    def put_document(self, document_id: str, doc: dict[str, Any]) -> None:
        with self._lock:
            self._docs[document_id] = dict(doc)

    def get_document(self, document_id: str) -> dict[str, Any] | None:
        with self._lock:
            row = self._docs.get(document_id)
            return dict(row) if row is not None else None

    def put_membership(self, owner_id: str, document_id: str) -> None:
        with self._lock:
            bucket = self._lib.setdefault(owner_id, [])
            if document_id not in bucket:
                bucket.append(document_id)

    def list_membership(self, owner_id: str) -> list[str]:
        with self._lock:
            return list(self._lib.get(owner_id, []))

    def put_receipt(self, receipt_id: str, receipt: dict[str, Any]) -> None:
        with self._lock:
            self._receipts[receipt_id] = dict(receipt)

    def get_receipt(self, receipt_id: str) -> dict[str, Any] | None:
        with self._lock:
            row = self._receipts.get(receipt_id)
            return dict(row) if row is not None else None


@dataclass
class FileHostStore:
    """JSON-file durable store under a root directory."""

    root: Path

    def __post_init__(self) -> None:
        self.root = Path(self.root)
        for sub in ("docs", "lib", "receipts"):
            (self.root / sub).mkdir(parents=True, exist_ok=True)

    def put_document(self, document_id: str, doc: dict[str, Any]) -> None:
        safe = document_id.replace("/", "_")
        (self.root / "docs" / f"{safe}.json").write_text(
            json.dumps(doc, sort_keys=True, indent=2), encoding="utf-8"
        )

    def get_document(self, document_id: str) -> dict[str, Any] | None:
        safe = document_id.replace("/", "_")
        path = self.root / "docs" / f"{safe}.json"
        if not path.is_file():
            return None
        data: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
        return data

    def put_membership(self, owner_id: str, document_id: str) -> None:
        path = self.root / "lib" / f"{owner_id.replace('/', '_')}.json"
        ids: list[str] = []
        if path.is_file():
            ids = list(json.loads(path.read_text(encoding="utf-8")))
        if document_id not in ids:
            ids.append(document_id)
        path.write_text(json.dumps(ids, indent=2), encoding="utf-8")

    def list_membership(self, owner_id: str) -> list[str]:
        path = self.root / "lib" / f"{owner_id.replace('/', '_')}.json"
        if not path.is_file():
            return []
        return list(json.loads(path.read_text(encoding="utf-8")))

    def put_receipt(self, receipt_id: str, receipt: dict[str, Any]) -> None:
        safe = receipt_id.replace("/", "_")
        (self.root / "receipts" / f"{safe}.json").write_text(
            json.dumps(receipt, sort_keys=True, indent=2), encoding="utf-8"
        )

    def get_receipt(self, receipt_id: str) -> dict[str, Any] | None:
        safe = receipt_id.replace("/", "_")
        path = self.root / "receipts" / f"{safe}.json"
        if not path.is_file():
            return None
        data: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
        return data


@dataclass(frozen=True)
class AccountLibrary:
    """Read model over membership for one owner."""

    owner_id: str
    document_ids: tuple[str, ...]

    @classmethod
    def load(cls, owner_id: str, *, store: HostStore) -> AccountLibrary:
        if not owner_id.strip():
            raise ValueError("owner_id is required")
        ids = store.list_membership(owner_id.strip())
        return cls(owner_id=owner_id.strip(), document_ids=tuple(ids))
