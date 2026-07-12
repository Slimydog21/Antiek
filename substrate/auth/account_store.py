"""Durable account, one-time magic-link, and revocable session authority."""

from __future__ import annotations

import hashlib
import os
import secrets
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path

ACCOUNT_ROLES = frozenset({"user", "operator"})
ACCOUNT_STATUSES = frozenset({"active", "disabled"})


@dataclass(frozen=True)
class AuthAccount:
    user_id: str
    email: str
    role: str
    status: str


def auth_db_path() -> Path:
    raw = os.environ.get("ANTIEK_AUTH_DB_PATH", "").strip()
    return Path(raw).expanduser() if raw else Path.home() / ".antiek" / "auth.sqlite3"


def _normalize_email(email: str) -> str:
    normalized = email.strip().lower()
    if not normalized or "@" not in normalized:
        raise ValueError("email is required")
    return normalized


def _normalize_session_email(email: str, user_id: str) -> str:
    """Normalize an account email or the server-owned operator sentinel."""

    if user_id == "__operator__" and email.strip().lower() == "__operator__":
        return "__operator__"
    return _normalize_email(email)


def _secret_hash(domain: bytes, value: str) -> str:
    return hashlib.sha256(domain + b"\0" + value.encode("utf-8")).hexdigest()


class SqliteAuthStore:
    """Small cross-process auth authority using stdlib SQLite transactions."""

    def __init__(self, path: Path | str | None = None) -> None:
        self.path = Path(path) if path is not None else auth_db_path()
        self.path = self.path.expanduser()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()
        os.chmod(self.path, 0o600)

    def _connect(self) -> sqlite3.Connection:
        con = sqlite3.connect(self.path, timeout=10.0, isolation_level=None)
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA busy_timeout = 10000")
        con.execute("PRAGMA journal_mode = WAL")
        return con

    def _initialize(self) -> None:
        con = self._connect()
        try:
            con.executescript(
                """
                CREATE TABLE IF NOT EXISTS auth_accounts (
                    user_id TEXT PRIMARY KEY,
                    email TEXT NOT NULL UNIQUE,
                    role TEXT NOT NULL CHECK (role IN ('user', 'operator')),
                    status TEXT NOT NULL CHECK (status IN ('active', 'disabled')),
                    created_at INTEGER NOT NULL,
                    updated_at INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS auth_magic_links (
                    nonce_hash TEXT PRIMARY KEY,
                    email TEXT NOT NULL,
                    expires_at INTEGER NOT NULL,
                    consumed_at INTEGER
                );
                CREATE TABLE IF NOT EXISTS auth_sessions (
                    session_hash TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    email TEXT NOT NULL,
                    issued_at INTEGER NOT NULL,
                    expires_at INTEGER NOT NULL,
                    revoked_at INTEGER
                );
                CREATE INDEX IF NOT EXISTS idx_auth_sessions_user
                    ON auth_sessions(user_id, expires_at);
                CREATE TABLE IF NOT EXISTS auth_rate_limits (
                    bucket_hash TEXT PRIMARY KEY,
                    window_start INTEGER NOT NULL,
                    request_count INTEGER NOT NULL
                );
                """
            )
        finally:
            con.close()

    def get_by_email(self, email: str) -> AuthAccount | None:
        con = self._connect()
        try:
            row = con.execute(
                "SELECT user_id, email, role, status FROM auth_accounts WHERE email = ?",
                [_normalize_email(email)],
            ).fetchone()
        finally:
            con.close()
        return AuthAccount(**dict(row)) if row is not None else None

    def get_by_user_id(self, user_id: str) -> AuthAccount | None:
        con = self._connect()
        try:
            row = con.execute(
                "SELECT user_id, email, role, status FROM auth_accounts WHERE user_id = ?",
                [user_id],
            ).fetchone()
        finally:
            con.close()
        return AuthAccount(**dict(row)) if row is not None else None

    def get_or_create_user(self, email: str) -> AuthAccount:
        normalized = _normalize_email(email)
        now = int(time.time())
        con = self._connect()
        try:
            con.execute("BEGIN IMMEDIATE")
            row = con.execute(
                "SELECT user_id, email, role, status FROM auth_accounts WHERE email = ?",
                [normalized],
            ).fetchone()
            if row is None:
                user_id = f"usr_{secrets.token_hex(16)}"
                con.execute(
                    "INSERT INTO auth_accounts "
                    "(user_id, email, role, status, created_at, updated_at) "
                    "VALUES (?, ?, 'user', 'active', ?, ?)",
                    [user_id, normalized, now, now],
                )
                row = con.execute(
                    "SELECT user_id, email, role, status FROM auth_accounts WHERE email = ?",
                    [normalized],
                ).fetchone()
            con.execute("COMMIT")
        except Exception:
            con.execute("ROLLBACK")
            raise
        finally:
            con.close()
        assert row is not None
        return AuthAccount(**dict(row))

    def set_status(self, user_id: str, status: str) -> None:
        if status not in ACCOUNT_STATUSES:
            raise ValueError("invalid account status")
        con = self._connect()
        try:
            changed = con.execute(
                "UPDATE auth_accounts SET status = ?, updated_at = ? WHERE user_id = ?",
                [status, int(time.time()), user_id],
            ).rowcount
        finally:
            con.close()
        if changed != 1:
            raise KeyError(user_id)

    def register_magic_link(self, *, email: str, nonce: str, expires_at: int) -> None:
        con = self._connect()
        try:
            con.execute(
                "INSERT INTO auth_magic_links (nonce_hash, email, expires_at) VALUES (?, ?, ?)",
                [_secret_hash(b"antiek.magic-link.nonce.v1", nonce), _normalize_email(email), expires_at],
            )
        finally:
            con.close()

    def allow_magic_link_request(
        self,
        *,
        email: str,
        client_key: str,
        now: int | None = None,
        window_seconds: int = 3600,
        per_email: int = 3,
        per_client: int = 20,
    ) -> bool:
        """Atomically enforce enumeration-safe email and client rate ceilings."""
        timestamp = int(time.time()) if now is None else int(now)
        window_start = timestamp - (timestamp % int(window_seconds))
        buckets = (
            (
                _secret_hash(
                    b"antiek.auth-rate.email.v1", _normalize_email(email)
                ),
                int(per_email),
            ),
            (
                _secret_hash(b"antiek.auth-rate.client.v1", client_key or "unknown"),
                int(per_client),
            ),
        )
        con = self._connect()
        try:
            con.execute("BEGIN IMMEDIATE")
            for bucket_hash, limit in buckets:
                row = con.execute(
                    "SELECT window_start, request_count FROM auth_rate_limits "
                    "WHERE bucket_hash = ?",
                    [bucket_hash],
                ).fetchone()
                count = (
                    int(row["request_count"])
                    if row is not None and int(row["window_start"]) == window_start
                    else 0
                )
                if count >= limit:
                    con.execute("ROLLBACK")
                    return False
            for bucket_hash, _limit in buckets:
                con.execute(
                    "INSERT INTO auth_rate_limits "
                    "(bucket_hash, window_start, request_count) VALUES (?, ?, 1) "
                    "ON CONFLICT(bucket_hash) DO UPDATE SET "
                    "window_start = excluded.window_start, "
                    "request_count = CASE "
                    "WHEN auth_rate_limits.window_start = excluded.window_start "
                    "THEN auth_rate_limits.request_count + 1 ELSE 1 END",
                    [bucket_hash, window_start],
                )
            con.execute("COMMIT")
            return True
        except Exception:
            con.execute("ROLLBACK")
            raise
        finally:
            con.close()

    def consume_magic_link(self, *, email: str, nonce: str, now: int | None = None) -> bool:
        timestamp = int(time.time()) if now is None else int(now)
        con = self._connect()
        try:
            con.execute("BEGIN IMMEDIATE")
            changed = con.execute(
                "UPDATE auth_magic_links SET consumed_at = ? "
                "WHERE nonce_hash = ? AND email = ? AND consumed_at IS NULL AND expires_at >= ?",
                [
                    timestamp,
                    _secret_hash(b"antiek.magic-link.nonce.v1", nonce),
                    _normalize_email(email),
                    timestamp,
                ],
            ).rowcount
            con.execute("COMMIT")
            return changed == 1
        except Exception:
            con.execute("ROLLBACK")
            raise
        finally:
            con.close()

    def create_session(
        self, *, user_id: str, email: str, ttl_seconds: int
    ) -> str:
        session_id = secrets.token_urlsafe(32)
        now = int(time.time())
        con = self._connect()
        try:
            con.execute(
                "INSERT INTO auth_sessions "
                "(session_hash, user_id, email, issued_at, expires_at) "
                "VALUES (?, ?, ?, ?, ?)",
                [
                    _secret_hash(b"antiek.auth-session.v1", session_id),
                    user_id,
                    _normalize_session_email(email, user_id),
                    now,
                    now + int(ttl_seconds),
                ],
            )
        finally:
            con.close()
        return session_id

    def validate_session(
        self, *, session_id: str, user_id: str, email: str, operator: bool = False
    ) -> AuthAccount | None:
        now = int(time.time())
        con = self._connect()
        try:
            session = con.execute(
                "SELECT user_id, email FROM auth_sessions WHERE session_hash = ? "
                "AND revoked_at IS NULL AND expires_at >= ?",
                [_secret_hash(b"antiek.auth-session.v1", session_id), now],
            ).fetchone()
            if (
                session is None
                or session["user_id"] != user_id
                or session["email"] != _normalize_session_email(email, user_id)
            ):
                return None
            if operator and user_id == "__operator__":
                return AuthAccount(
                    user_id,
                    _normalize_session_email(email, user_id),
                    "operator",
                    "active",
                )
            account = con.execute(
                "SELECT user_id, email, role, status FROM auth_accounts WHERE user_id = ?",
                [user_id],
            ).fetchone()
        finally:
            con.close()
        if account is None:
            return None
        decoded = AuthAccount(**dict(account))
        if decoded.email != _normalize_email(email) or decoded.status != "active":
            return None
        return decoded

    def revoke_session(self, session_id: str) -> bool:
        con = self._connect()
        try:
            changed = con.execute(
                "UPDATE auth_sessions SET revoked_at = ? "
                "WHERE session_hash = ? AND revoked_at IS NULL",
                [int(time.time()), _secret_hash(b"antiek.auth-session.v1", session_id)],
            ).rowcount
        finally:
            con.close()
        return changed == 1
