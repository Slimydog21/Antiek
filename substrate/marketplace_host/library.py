"""Account library + host store (pure, offline)."""

from __future__ import annotations

import json
import os
import re
import sqlite3
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

_SQLITE_HOST_COLUMNS = {
    "hosted_documents": (
        ("document_id", "TEXT", 0, 1, 0),
        ("payload_json", "TEXT", 1, 0, 0),
    ),
    "host_memberships": (
        ("sequence", "INTEGER", 0, 1, 0),
        ("owner_id", "TEXT", 1, 0, 0),
        ("document_id", "TEXT", 1, 0, 0),
    ),
    "purchase_receipts": (
        ("receipt_id", "TEXT", 0, 1, 0),
        ("payload_json", "TEXT", 1, 0, 0),
    ),
}
_SQLITE_HOST_DDL = {
    "hosted_documents": """
        CREATE TABLE hosted_documents (
            document_id TEXT PRIMARY KEY,
            payload_json TEXT NOT NULL
        )
    """,
    "host_memberships": """
        CREATE TABLE host_memberships (
            sequence INTEGER PRIMARY KEY AUTOINCREMENT,
            owner_id TEXT NOT NULL,
            document_id TEXT NOT NULL,
            FOREIGN KEY(document_id) REFERENCES hosted_documents(document_id),
            UNIQUE(owner_id, document_id)
        )
    """,
    "host_memberships_owner_sequence": """
        CREATE INDEX host_memberships_owner_sequence
            ON host_memberships(owner_id, sequence)
    """,
    "purchase_receipts": """
        CREATE TABLE purchase_receipts (
            receipt_id TEXT PRIMARY KEY,
            payload_json TEXT NOT NULL
        )
    """,
}


def _normalize_sql(value: object) -> str:
    return re.sub(r"\s+", " ", str(value).strip()).upper()


def _decode_json_object(value: object, *, label: str) -> dict[str, Any]:
    try:
        decoded = json.loads(str(value))
    except (TypeError, ValueError) as exc:
        raise RuntimeError(f"stored {label} is not valid JSON") from exc
    if not isinstance(decoded, dict):
        raise RuntimeError(f"stored {label} is not an object")
    return decoded


def _validate_sqlite_host_schema(
    con: sqlite3.Connection,
    *,
    allowed_versions: frozenset[int],
) -> int:
    """Validate the durable schema without modifying the connection."""

    schema_version = int(con.execute("PRAGMA user_version").fetchone()[0])
    if schema_version not in allowed_versions:
        raise RuntimeError("unsupported marketplace host schema version")
    tables = {
        str(row[0])
        for row in con.execute(
            "SELECT name FROM sqlite_master "
            "WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        )
    }
    if tables != set(_SQLITE_HOST_COLUMNS):
        raise RuntimeError("marketplace host database has an invalid table set")
    schema_objects = {
        str(row[0]): _normalize_sql(row[1])
        for row in con.execute(
            "SELECT name, sql FROM sqlite_master "
            "WHERE type IN ('table', 'index', 'view', 'trigger') "
            "AND name NOT LIKE 'sqlite_%' AND sql IS NOT NULL"
        )
    }
    expected_objects = {
        name: _normalize_sql(sql) for name, sql in _SQLITE_HOST_DDL.items()
    }
    if schema_objects != expected_objects:
        raise RuntimeError("marketplace host database has invalid schema objects")
    for table, expected in _SQLITE_HOST_COLUMNS.items():
        columns = tuple(
            (
                str(row[1]),
                str(row[2]).upper(),
                int(row[3]),
                int(row[5]),
                int(row[6]),
            )
            for row in con.execute(f"PRAGMA table_xinfo({table})")
        )
        if columns != expected:
            raise RuntimeError(f"marketplace host table {table} has an invalid schema")

    foreign_keys = tuple(
        (
            int(row[0]),
            int(row[1]),
            str(row[2]),
            str(row[3]),
            str(row[4]),
            str(row[5]),
            str(row[6]),
            str(row[7]),
        )
        for row in con.execute("PRAGMA foreign_key_list(host_memberships)")
    )
    if foreign_keys != (
        (
            0,
            0,
            "hosted_documents",
            "document_id",
            "document_id",
            "NO ACTION",
            "NO ACTION",
            "NONE",
        ),
    ):
        raise RuntimeError("marketplace host membership foreign key is invalid")
    membership_sql_row = con.execute(
        "SELECT sql FROM sqlite_master "
        "WHERE type='table' AND name='host_memberships'"
    ).fetchone()
    if membership_sql_row is None or "DEFERRABLE" in str(membership_sql_row[0]).upper():
        raise RuntimeError("marketplace host membership foreign key is invalid")

    membership_indexes: dict[
        str,
        tuple[bool, str, bool, tuple[tuple[str, int, str], ...]],
    ] = {}
    for row in con.execute("PRAGMA index_list(host_memberships)"):
        index_name = str(row[1])
        index_columns = tuple(
            (str(column[2]), int(column[3]), str(column[4]))
            for column in con.execute(f"PRAGMA index_xinfo('{index_name}')")
            if int(column[5]) == 1
        )
        membership_indexes[index_name] = (
            bool(row[2]),
            str(row[3]),
            bool(row[4]),
            index_columns,
        )
    if membership_indexes.get("host_memberships_owner_sequence") != (
        False,
        "c",
        False,
        (("owner_id", 0, "BINARY"), ("sequence", 0, "BINARY")),
    ):
        raise RuntimeError("marketplace host membership ordering index is invalid")
    if not any(
        unique
        and origin == "u"
        and not partial
        and columns == (("owner_id", 0, "BINARY"), ("document_id", 0, "BINARY"))
        for unique, origin, partial, columns in membership_indexes.values()
    ):
        raise RuntimeError("marketplace host membership uniqueness is invalid")
    return schema_version


def verify_sqlite_host_store(path: Path) -> Path:
    """Read-only schema and integrity proof for a durable store file."""

    path = Path(path)
    if not path.is_file() or path.is_symlink():
        raise FileNotFoundError(f"marketplace host database is not a regular file: {path}")
    uri = f"{path.resolve().as_uri()}?mode=ro"
    with sqlite3.connect(uri, uri=True, timeout=30) as con:
        con.execute("PRAGMA query_only=ON")
        con.execute("PRAGMA busy_timeout=30000")
        _validate_sqlite_host_schema(con, allowed_versions=frozenset({1}))
        check_rows = con.execute("PRAGMA quick_check").fetchall()
        foreign_key_rows = con.execute("PRAGMA foreign_key_check").fetchall()
        for table, key_column, label in (
            ("hosted_documents", "document_id", "document"),
            ("purchase_receipts", "receipt_id", "receipt"),
        ):
            for key, payload in con.execute(
                f"SELECT {key_column}, payload_json FROM {table}"
            ):
                _decode_json_object(payload, label=f"{label} {key}")
    if check_rows != [("ok",)]:
        raise RuntimeError("marketplace host database failed SQLite quick_check")
    if foreign_key_rows:
        raise RuntimeError("marketplace host database failed foreign_key_check")
    return path


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
        if path.is_symlink() or (path.exists() and not path.is_file()):
            raise ValueError("marketplace host database path must be a file")
        path.parent.mkdir(parents=True, exist_ok=True)
        created = False
        try:
            descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except FileExistsError:
            pass
        else:
            os.close(descriptor)
            created = True
        object.__setattr__(self, "path", path)
        if not created:
            verify_sqlite_host_store(path)
            os.chmod(path, 0o600)
            return
        os.chmod(path, 0o600)
        try:
            with self._connect() as con:
                con.executescript(
                    """
                    CREATE TABLE hosted_documents (
                        document_id TEXT PRIMARY KEY,
                        payload_json TEXT NOT NULL
                    );
                    CREATE TABLE host_memberships (
                        sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                        owner_id TEXT NOT NULL,
                        document_id TEXT NOT NULL,
                        FOREIGN KEY(document_id) REFERENCES hosted_documents(document_id),
                        UNIQUE(owner_id, document_id)
                    );
                    CREATE INDEX host_memberships_owner_sequence
                        ON host_memberships(owner_id, sequence);
                    CREATE TABLE purchase_receipts (
                        receipt_id TEXT PRIMARY KEY,
                        payload_json TEXT NOT NULL
                    );
                    """
                )
                con.execute("PRAGMA user_version=1")
                _validate_sqlite_host_schema(con, allowed_versions=frozenset({1}))
        except BaseException:
            path.unlink(missing_ok=True)
            raise

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
        return _decode_json_object(value, label=label)

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


def backup_sqlite_host_store(source: Path, destination: Path) -> Path:
    """Create and validate an online-consistent marketplace store snapshot."""

    source = Path(source)
    destination = Path(destination)
    if not source.is_file():
        raise FileNotFoundError(f"marketplace host database does not exist: {source}")
    destination_bundle = (
        destination,
        Path(f"{destination}-wal"),
        Path(f"{destination}-shm"),
        Path(f"{destination}-journal"),
    )
    if any(path.exists() for path in destination_bundle):
        raise FileExistsError(
            f"backup destination or SQLite sidecar already exists: {destination}"
        )
    if not destination.parent.is_dir():
        raise FileNotFoundError(
            f"backup destination directory does not exist: {destination.parent}"
        )

    descriptor = os.open(
        destination,
        os.O_CREAT | os.O_EXCL | os.O_WRONLY,
        0o600,
    )
    os.close(descriptor)
    try:
        source_uri = f"{source.resolve().as_uri()}?mode=ro"
        with sqlite3.connect(source_uri, uri=True, timeout=30) as source_con:
            source_con.execute("PRAGMA query_only=ON")
            source_con.execute("PRAGMA busy_timeout=30000")
            with sqlite3.connect(destination, timeout=30) as destination_con:
                destination_con.execute("PRAGMA busy_timeout=30000")
                source_con.backup(destination_con)

        verify_sqlite_host_store(destination)
        os.chmod(destination, 0o600)
        return destination
    except BaseException:
        for path in destination_bundle:
            path.unlink(missing_ok=True)
        raise


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
