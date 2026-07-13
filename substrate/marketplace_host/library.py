"""Account library + host store (pure, offline)."""

from __future__ import annotations

import json
import os
import sqlite3
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
class SQLiteHostStore:
    """Transactional durable store for composed API and worker processes."""

    path: Path

    def __post_init__(self) -> None:
        path = Path(self.path)
        if path.exists() and not path.is_file():
            raise ValueError("marketplace host database path must be a file")
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists():
            try:
                descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            except FileExistsError:
                pass
            else:
                os.close(descriptor)
        os.chmod(path, 0o600)
        object.__setattr__(self, "path", path)
        with self._connect() as con:
            schema_version = int(con.execute("PRAGMA user_version").fetchone()[0])
            if schema_version not in {0, 1}:
                raise RuntimeError("unsupported marketplace host schema version")
            con.executescript(
                """
                CREATE TABLE IF NOT EXISTS hosted_documents (
                    document_id TEXT PRIMARY KEY,
                    payload_json TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS host_memberships (
                    sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                    owner_id TEXT NOT NULL,
                    document_id TEXT NOT NULL,
                    FOREIGN KEY(document_id) REFERENCES hosted_documents(document_id),
                    UNIQUE(owner_id, document_id)
                );
                CREATE INDEX IF NOT EXISTS host_memberships_owner_sequence
                    ON host_memberships(owner_id, sequence);
                CREATE TABLE IF NOT EXISTS purchase_receipts (
                    receipt_id TEXT PRIMARY KEY,
                    payload_json TEXT NOT NULL
                );
                """
            )
            expected_columns = {
                "hosted_documents": ("document_id", "payload_json"),
                "host_memberships": ("sequence", "owner_id", "document_id"),
                "purchase_receipts": ("receipt_id", "payload_json"),
            }
            for table, expected in expected_columns.items():
                columns = tuple(
                    str(row[1]) for row in con.execute(f"PRAGMA table_info({table})")
                )
                if columns != expected:
                    raise RuntimeError(f"marketplace host table {table} has an invalid schema")
            if schema_version == 0:
                con.execute("PRAGMA user_version=1")

    def _connect(self) -> sqlite3.Connection:
        con = sqlite3.connect(self.path, timeout=30)
        con.execute("PRAGMA journal_mode=DELETE")
        con.execute("PRAGMA synchronous=FULL")
        con.execute("PRAGMA busy_timeout=30000")
        con.execute("PRAGMA foreign_keys=ON")
        return con

    @staticmethod
    def _key(value: str, *, label: str) -> str:
        if not isinstance(value, str) or not value.strip() or value != value.strip():
            raise ValueError(f"{label} must be a canonical non-empty string")
        if len(value) > 512:
            raise ValueError(f"{label} is too long")
        return value

    @staticmethod
    def _payload(value: dict[str, Any], *, label: str) -> str:
        if not isinstance(value, dict):
            raise TypeError(f"{label} must be an object")
        try:
            return json.dumps(
                value, sort_keys=True, separators=(",", ":"), allow_nan=False
            )
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{label} must be JSON serializable") from exc

    @staticmethod
    def _decode(value: object, *, label: str) -> dict[str, Any]:
        try:
            decoded = json.loads(str(value))
        except (TypeError, ValueError) as exc:
            raise RuntimeError(f"stored {label} is not valid JSON") from exc
        if not isinstance(decoded, dict):
            raise RuntimeError(f"stored {label} is not an object")
        return decoded

    def put_document(self, document_id: str, doc: dict[str, Any]) -> None:
        key = self._key(document_id, label="document_id")
        payload = self._payload(doc, label="document")
        with self._connect() as con:
            con.execute(
                """
                INSERT INTO hosted_documents(document_id, payload_json)
                VALUES (?, ?)
                ON CONFLICT(document_id) DO UPDATE SET payload_json=excluded.payload_json
                """,
                (key, payload),
            )

    def get_document(self, document_id: str) -> dict[str, Any] | None:
        key = self._key(document_id, label="document_id")
        with self._connect() as con:
            row = con.execute(
                "SELECT payload_json FROM hosted_documents WHERE document_id=?", (key,)
            ).fetchone()
        return None if row is None else self._decode(row[0], label="document")

    def put_membership(self, owner_id: str, document_id: str) -> None:
        owner = self._key(owner_id, label="owner_id")
        document = self._key(document_id, label="document_id")
        with self._connect() as con:
            con.execute(
                """
                INSERT OR IGNORE INTO host_memberships(owner_id, document_id)
                VALUES (?, ?)
                """,
                (owner, document),
            )

    def list_membership(self, owner_id: str) -> list[str]:
        owner = self._key(owner_id, label="owner_id")
        with self._connect() as con:
            rows = con.execute(
                """
                SELECT document_id FROM host_memberships
                WHERE owner_id=? ORDER BY sequence
                """,
                (owner,),
            ).fetchall()
        return [str(row[0]) for row in rows]

    def put_receipt(self, receipt_id: str, receipt: dict[str, Any]) -> None:
        key = self._key(receipt_id, label="receipt_id")
        payload = self._payload(receipt, label="receipt")
        with self._connect() as con:
            con.execute(
                """
                INSERT INTO purchase_receipts(receipt_id, payload_json)
                VALUES (?, ?)
                ON CONFLICT(receipt_id) DO NOTHING
                """,
                (key, payload),
            )
            stored = con.execute(
                "SELECT payload_json FROM purchase_receipts WHERE receipt_id=?", (key,)
            ).fetchone()
            if stored is None or stored[0] != payload:
                raise ValueError("receipt_id conflicts with immutable receipt evidence")

    def get_receipt(self, receipt_id: str) -> dict[str, Any] | None:
        key = self._key(receipt_id, label="receipt_id")
        with self._connect() as con:
            row = con.execute(
                "SELECT payload_json FROM purchase_receipts WHERE receipt_id=?", (key,)
            ).fetchone()
        return None if row is None else self._decode(row[0], label="receipt")

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
