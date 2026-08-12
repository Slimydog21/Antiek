"""Private, durable leased workflow journal for paid Deep Talk operations."""

from __future__ import annotations

import json
import os
import sqlite3
import stat
import threading
import time
from dataclasses import dataclass
from pathlib import Path

_SCHEMA_VERSION = 1
_STATES = frozenset({"claimed", "canonical_complete", "completed", "unknown"})
_MAX_JSON = 4_000_000
_LEASE_MS = 900_000
_INIT_LOCK = threading.Lock()


class DeepOperationConflict(RuntimeError):
    pass


@dataclass(frozen=True)
class DeepOperation:
    owner_id: str
    operation_id: str
    request_digest: str
    state: str
    checkpoint: dict[str, object] | None
    response: dict[str, object] | None
    lease_token: str | None
    lease_expires_at_ms: int | None
    created_at_ms: int
    updated_at_ms: int


class DeepTalkJournal:
    def __init__(self, path: Path) -> None:
        self.path = path
        self._validate_parent()
        with _INIT_LOCK:
            self._initialize()

    def _validate_parent(self) -> None:
        meta = self.path.parent.lstat()
        if (
            not stat.S_ISDIR(meta.st_mode) or self.path.parent.is_symlink()
            or meta.st_uid != os.getuid() or stat.S_IMODE(meta.st_mode) != 0o700
        ):
            raise DeepOperationConflict("deep journal parent is unsafe")

    def _initialize(self) -> None:
        existed_nonempty = False
        try:
            meta = self.path.lstat()
            existed_nonempty = meta.st_size > 0
            if (
                not stat.S_ISREG(meta.st_mode) or self.path.is_symlink()
                or meta.st_uid != os.getuid() or stat.S_IMODE(meta.st_mode) != 0o600
            ):
                raise DeepOperationConflict("deep journal file is unsafe")
        except FileNotFoundError:
            fd = os.open(
                self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os, "O_NOFOLLOW", 0),
                0o600,
            )
            os.close(fd)
        with sqlite3.connect(self.path) as con:
            existing_version = con.execute("PRAGMA user_version").fetchone()[0]
            if existing_version != _SCHEMA_VERSION and existed_nonempty:
                raise DeepOperationConflict("deep journal schema mismatch")
            con.execute("PRAGMA journal_mode=WAL")
            con.execute("PRAGMA synchronous=FULL")
            con.execute("""CREATE TABLE IF NOT EXISTS deep_operations(
                owner_id TEXT NOT NULL CHECK(length(owner_id) BETWEEN 1 AND 256),
                operation_id TEXT NOT NULL CHECK(length(operation_id) BETWEEN 1 AND 128),
                request_digest TEXT NOT NULL CHECK(length(request_digest)=64),
                state TEXT NOT NULL CHECK(state IN ('claimed','canonical_complete','completed','unknown')),
                checkpoint_json TEXT CHECK(checkpoint_json IS NULL OR length(checkpoint_json)<=4000000),
                response_json TEXT CHECK(response_json IS NULL OR length(response_json)<=4000000),
                lease_token TEXT CHECK(lease_token IS NULL OR length(lease_token)=64),
                lease_expires_at_ms INTEGER,
                created_at_ms INTEGER NOT NULL CHECK(created_at_ms>=0),
                updated_at_ms INTEGER NOT NULL CHECK(updated_at_ms>=created_at_ms),
                PRIMARY KEY(owner_id, operation_id))""")
            con.execute("""CREATE TABLE IF NOT EXISTS deep_children(
                owner_id TEXT NOT NULL, operation_id TEXT NOT NULL,
                phase TEXT NOT NULL CHECK(phase IN ('canonical_batch','prime','final_reduce')),
                child_index INTEGER NOT NULL CHECK(child_index>=0),
                request_digest TEXT NOT NULL CHECK(length(request_digest)=64),
                result_json TEXT CHECK(result_json IS NULL OR length(result_json)<=4000000),
                state TEXT NOT NULL CHECK(state IN ('claimed','completed')),
                lease_token TEXT NOT NULL CHECK(length(lease_token)=64),
                updated_at_ms INTEGER NOT NULL CHECK(updated_at_ms>=0),
                PRIMARY KEY(owner_id,operation_id,phase,child_index),
                FOREIGN KEY(owner_id,operation_id) REFERENCES deep_operations(owner_id,operation_id))""")
            con.execute(f"PRAGMA user_version={_SCHEMA_VERSION}")
            if con.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                raise DeepOperationConflict("deep journal integrity failure")
            expected = {"deep_operations", "deep_children"}
            actual = {
                row[0] for row in con.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'deep_%'"
                ).fetchall()
            }
            if actual != expected:
                raise DeepOperationConflict("deep journal schema contract mismatch")
        self._harden_sidecars()

    def _harden_sidecars(self) -> None:
        for suffix in ("", "-wal", "-shm"):
            path = Path(f"{self.path}{suffix}")
            if path.exists():
                meta = path.lstat()
                if not stat.S_ISREG(meta.st_mode) or path.is_symlink() or meta.st_uid != os.getuid():
                    raise DeepOperationConflict("deep journal sidecar is unsafe")
                os.chmod(path, 0o600)

    def _connect(self) -> sqlite3.Connection:
        meta = self.path.lstat()
        if (
            not stat.S_ISREG(meta.st_mode) or self.path.is_symlink()
            or meta.st_uid != os.getuid() or stat.S_IMODE(meta.st_mode) != 0o600
        ):
            raise DeepOperationConflict("deep journal file is unsafe")
        self._harden_sidecars()
        con = sqlite3.connect(self.path, timeout=30, isolation_level=None)
        con.execute("PRAGMA foreign_keys=ON")
        con.execute("PRAGMA busy_timeout=30000")
        if con.execute("PRAGMA user_version").fetchone()[0] != _SCHEMA_VERSION:
            raise DeepOperationConflict("deep journal schema mismatch")
        return con

    def claim(
        self, owner: str, operation: str, digest: str, *, lease_token: str | None = None,
        now_ms: int | None = None,
    ) -> DeepOperation:
        now = _now(now_ms)
        token = lease_token or os.urandom(32).hex()
        _identity(owner, operation, digest, token)
        with self._connect() as con:
            con.execute("BEGIN IMMEDIATE")
            row = con.execute(
                "SELECT * FROM deep_operations WHERE owner_id=? AND operation_id=?",
                (owner, operation),
            ).fetchone()
            if row is None:
                con.execute(
                    "INSERT INTO deep_operations VALUES(?,?,?,?,?,?,?,?,?,?)",
                    (owner, operation, digest, "claimed", None, None, token,
                     now + _LEASE_MS, now, now),
                )
                return self.get(owner, operation, con=con, ephemeral_state="new")
            current = _row(row)
            if current.request_digest != digest:
                raise DeepOperationConflict("deep_operation_conflict")
            if current.state == "completed":
                return current
            if current.lease_expires_at_ms is not None and current.lease_expires_at_ms > now:
                return current
            ambiguous = con.execute(
                "SELECT 1 FROM deep_children WHERE owner_id=? AND operation_id=?"
                " AND state='claimed' LIMIT 1",
                (owner, operation),
            ).fetchone()
            if ambiguous is not None:
                changed = con.execute(
                    "UPDATE deep_operations SET state='unknown',lease_token=NULL,"
                    "lease_expires_at_ms=NULL,updated_at_ms=?"
                    " WHERE owner_id=? AND operation_id=? AND updated_at_ms=?",
                    (now, owner, operation, current.updated_at_ms),
                ).rowcount
                if changed != 1:
                    raise DeepOperationConflict("deep ambiguity quarantine lost")
                return self.get(owner, operation, con=con)
            updated = con.execute(
                "UPDATE deep_operations SET lease_token=?,lease_expires_at_ms=?,updated_at_ms=?"
                " WHERE owner_id=? AND operation_id=? AND updated_at_ms=?",
                (token, now + _LEASE_MS, now, owner, operation, current.updated_at_ms),
            ).rowcount
            if updated != 1:
                raise DeepOperationConflict("deep lease takeover lost")
            return self.get(owner, operation, con=con, ephemeral_state="resumed")

    def checkpoint_canonical(
        self, owner: str, operation: str, token: str, checkpoint: dict[str, object],
    ) -> DeepOperation:
        encoded = _encode(checkpoint)
        now = _now(None)
        with self._connect() as con:
            con.execute("BEGIN IMMEDIATE")
            changed = con.execute(
                "UPDATE deep_operations SET state='canonical_complete',checkpoint_json=?,"
                "updated_at_ms=? WHERE owner_id=? AND operation_id=? AND lease_token=?"
                " AND lease_expires_at_ms>?",
                (encoded, now, owner, operation, token, now),
            ).rowcount
            if changed != 1:
                raise DeepOperationConflict("deep lease is not owned")
            return self.get(owner, operation, con=con)

    def renew(self, owner: str, operation: str, token: str, *, now_ms: int | None = None) -> None:
        now = _now(now_ms)
        with self._connect() as con:
            changed = con.execute(
                "UPDATE deep_operations SET lease_expires_at_ms=?,updated_at_ms=?"
                " WHERE owner_id=? AND operation_id=? AND lease_token=? AND state!='completed'"
                " AND lease_expires_at_ms>?",
                (now + _LEASE_MS, now, owner, operation, token, now),
            ).rowcount
            if changed != 1:
                raise DeepOperationConflict("deep lease is stale")

    def child_result(self, owner: str, operation: str, phase: str, index: int,
                     request_digest: str) -> dict[str, object] | None:
        with self._connect() as con:
            row = con.execute(
                "SELECT request_digest,result_json,state FROM deep_children"
                " WHERE owner_id=? AND operation_id=? AND phase=? AND child_index=?",
                (owner, operation, phase, index),
            ).fetchone()
        if row is None:
            return None
        if row[0] != request_digest:
            raise DeepOperationConflict("deep child replay mismatch")
        return json.loads(row[1]) if row[2] == "completed" and isinstance(row[1], str) else None

    def resumable(self, operation: DeepOperation, *, now_ms: int | None = None) -> bool:
        if operation.state == "completed":
            return False
        now = _now(now_ms)
        if operation.lease_expires_at_ms is not None and operation.lease_expires_at_ms > now:
            return False
        with self._connect() as con:
            ambiguous = con.execute(
                "SELECT 1 FROM deep_children WHERE owner_id=? AND operation_id=?"
                " AND state='claimed' LIMIT 1",
                (operation.owner_id, operation.operation_id),
            ).fetchone()
        return ambiguous is None

    def claim_child(self, owner: str, operation: str, token: str, phase: str, index: int,
                    request_digest: str) -> dict[str, object] | None:
        self.renew(owner, operation, token)
        cached = self.child_result(owner, operation, phase, index, request_digest)
        if cached is not None:
            return cached
        now = _now(None)
        with self._connect() as con:
            con.execute("BEGIN IMMEDIATE")
            try:
                con.execute(
                    "INSERT INTO deep_children VALUES(?,?,?,?,?,NULL,'claimed',?,?)",
                    (owner, operation, phase, index, request_digest, token, now),
                )
            except sqlite3.IntegrityError:
                row = con.execute(
                    "SELECT request_digest,state,lease_token FROM deep_children"
                    " WHERE owner_id=? AND operation_id=? AND phase=? AND child_index=?",
                    (owner, operation, phase, index),
                ).fetchone()
                if row is None or row[0] != request_digest or row[1] != "claimed":
                    raise DeepOperationConflict("deep child claim conflict") from None
                if row[2] != token:
                    changed = con.execute(
                        "UPDATE deep_children SET lease_token=?,updated_at_ms=?"
                        " WHERE owner_id=? AND operation_id=? AND phase=? AND child_index=?",
                        (token, now, owner, operation, phase, index),
                    ).rowcount
                    if changed != 1:
                        raise DeepOperationConflict("deep child takeover lost") from None
        return None

    def complete_child(self, owner: str, operation: str, token: str, phase: str, index: int,
                       request_digest: str, result: dict[str, object]) -> None:
        encoded = _encode(result)
        now = _now(None)
        with self._connect() as con:
            con.execute("BEGIN IMMEDIATE")
            changed = con.execute(
                "UPDATE deep_children SET state='completed',result_json=?,updated_at_ms=?"
                " WHERE owner_id=? AND operation_id=? AND phase=? AND child_index=?"
                " AND request_digest=? AND lease_token=? AND state='claimed'"
                " AND EXISTS(SELECT 1 FROM deep_operations p WHERE p.owner_id=?"
                " AND p.operation_id=? AND p.lease_token=? AND p.lease_expires_at_ms>?)",
                (encoded, now, owner, operation, phase, index, request_digest, token,
                 owner, operation, token, now),
            ).rowcount
            if changed != 1:
                raise DeepOperationConflict("deep child completion fence rejected")
        self.renew(owner, operation, token)

    def complete(
        self, owner: str, operation: str, response: dict[str, object], token: str | None = None,
    ) -> DeepOperation:
        current = self.get(owner, operation)
        if current is None:
            raise DeepOperationConflict("deep_operation_missing")
        return self._advance(
            owner, operation, token or current.lease_token or "", "completed",
            current.checkpoint, response,
        )

    def unknown(self, owner: str, operation: str, token: str | None = None) -> None:
        current = self.get(owner, operation)
        if current is None:
            return
        self._advance(
            owner, operation, token or current.lease_token or "", "unknown",
            current.checkpoint, None,
        )

    def _advance(self, owner: str, operation: str, token: str, state: str,
                 checkpoint: dict[str, object] | None,
                 response: dict[str, object] | None) -> DeepOperation:
        if state not in _STATES:
            raise DeepOperationConflict("invalid deep state")
        checkpoint_json = _encode(checkpoint)
        response_json = _encode(response)
        now = _now(None)
        with self._connect() as con:
            con.execute("BEGIN IMMEDIATE")
            changed = con.execute(
                "UPDATE deep_operations SET state=?,checkpoint_json=?,response_json=?,"
                "lease_token=NULL,lease_expires_at_ms=NULL,updated_at_ms=?"
                " WHERE owner_id=? AND operation_id=? AND lease_token=? AND state!='completed'"
                " AND lease_expires_at_ms>?",
                (state, checkpoint_json, response_json, now, owner, operation, token, now),
            ).rowcount
            if changed != 1:
                existing = self.get(owner, operation, con=con)
                if existing is not None and existing.state == "completed" and state == "completed":
                    return existing
                raise DeepOperationConflict("deep lease is not owned")
            return self.get(owner, operation, con=con)

    def get(self, owner: str, operation: str, *, con: sqlite3.Connection | None = None,
            ephemeral_state: str | None = None) -> DeepOperation | None:
        own = con is None
        connection = con or self._connect()
        try:
            row = connection.execute(
                "SELECT * FROM deep_operations WHERE owner_id=? AND operation_id=?",
                (owner, operation),
            ).fetchone()
        finally:
            if own:
                connection.close()
        if row is None:
            return None
        result = _row(row)
        if ephemeral_state is not None:
            result = DeepOperation(
                result.owner_id, result.operation_id, result.request_digest, ephemeral_state,
                result.checkpoint, result.response, result.lease_token,
                result.lease_expires_at_ms, result.created_at_ms, result.updated_at_ms,
            )
        return result


def _encode(value: dict[str, object] | None) -> str | None:
    if value is None:
        return None
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"))
    if len(encoded.encode()) > _MAX_JSON:
        raise DeepOperationConflict("deep checkpoint is oversized")
    return encoded


def _row(row: tuple[object, ...]) -> DeepOperation:
    return DeepOperation(
        str(row[0]), str(row[1]), str(row[2]), str(row[3]),
        json.loads(row[4]) if isinstance(row[4], str) else None,
        json.loads(row[5]) if isinstance(row[5], str) else None,
        str(row[6]) if isinstance(row[6], str) else None,
        int(row[7]) if isinstance(row[7], int) else None,
        int(row[8]), int(row[9]),
    )


def _identity(owner: str, operation: str, digest: str, token: str) -> None:
    if not (1 <= len(owner) <= 256 and 1 <= len(operation) <= 128):
        raise DeepOperationConflict("deep identity is invalid")
    if len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
        raise DeepOperationConflict("deep digest is invalid")
    if len(token) != 64 or any(c not in "0123456789abcdef" for c in token):
        raise DeepOperationConflict("deep lease token is invalid")


def _now(value: int | None) -> int:
    now = time.time_ns() // 1_000_000 if value is None else value
    if type(now) is not int or now < 0:
        raise DeepOperationConflict("deep timestamp is invalid")
    return now


def deep_talk_journal() -> DeepTalkJournal:
    root = Path(os.environ.get("ANTIEK_PRIME_LEDGER_DIR", Path.home() / ".antiek" / "prime"))
    if root.exists() or root.is_symlink():
        meta = root.lstat()
        if not stat.S_ISDIR(meta.st_mode) or root.is_symlink() or meta.st_uid != os.getuid() \
                or stat.S_IMODE(meta.st_mode) != 0o700:
            raise DeepOperationConflict("deep journal parent is unsafe")
    else:
        root.mkdir(mode=0o700, parents=True)
    return DeepTalkJournal(root / "deep-talk.sqlite3")
