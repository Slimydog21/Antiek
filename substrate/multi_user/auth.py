"""Verified subject identity and durable owner mapping.

The API boundary resolves provider credentials into :class:`VerifiedPrincipal`.
Owner IDs are derived here and stored in the primary DuckDB; callers cannot
supply or rebind them. ``__operator__`` remains a separate local-compatibility
identity and is never inserted into ``auth_subjects``.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Protocol

from runtime.db_lock import LockedConnection, connect_read, connect_write
from substrate.auth.magic_link import (
    InvalidSessionCookie,
    verify_session_cookie,
)
from substrate.auth.magic_link import (
    mint_session_cookie as _mint_signed_session_cookie,
)
from substrate.graph import default_db_path

_PROVIDER_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,63}$")
_SUBJECT_RE = re.compile(r"^[\x20-\x7e]{1,256}$")
_SESSION_COOKIE_NAME = "ANTIEK_SESSION"

AUTH_SUBJECTS_DDL = r"""
CREATE TABLE IF NOT EXISTS auth_subjects (
  provider VARCHAR NOT NULL CHECK(regexp_matches(provider,'^[a-z0-9][a-z0-9._-]{0,63}$')),
  subject VARCHAR NOT NULL CHECK(regexp_matches(subject,'^[\x20-\x7e]{1,256}$')),
  owner_user_id VARCHAR NOT NULL CHECK(regexp_matches(owner_user_id,'^[\x20-\x7e]{1,256}$')),
  created_at TIMESTAMPTZ NOT NULL,
  last_seen_at TIMESTAMPTZ NOT NULL,
  PRIMARY KEY(provider,subject),
  UNIQUE(owner_user_id)
);
"""

_AUTH_SUBJECT_COLUMNS: tuple[tuple[str, str, str, int], ...] = (
    ("provider", "VARCHAR", "NO", 1),
    ("subject", "VARCHAR", "NO", 2),
    ("owner_user_id", "VARCHAR", "NO", 3),
    ("created_at", "TIMESTAMP WITH TIME ZONE", "NO", 4),
    ("last_seen_at", "TIMESTAMP WITH TIME ZONE", "NO", 5),
)
_AUTH_SUBJECT_KEYS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("PRIMARY KEY", ("provider", "subject")),
    ("UNIQUE", ("owner_user_id",)),
)
_AUTH_SUBJECT_CHECKS: tuple[tuple[tuple[str, ...], str], ...] = (
    (("owner_user_id",), r"CHECK(regexp_matches(owner_user_id, '^[\x20-\x7e]{1,256}$'))"),
    (("provider",), r"CHECK(regexp_matches(provider, '^[a-z0-9][a-z0-9._-]{0,63}$'))"),
    (("subject",), r"CHECK(regexp_matches(subject, '^[\x20-\x7e]{1,256}$'))"),
)
AUTH_SUBJECTS_SCHEMA_SHA256 = hashlib.sha256(
    json.dumps(
        {
            "columns": _AUTH_SUBJECT_COLUMNS,
            "keys": _AUTH_SUBJECT_KEYS,
            "checks": _AUTH_SUBJECT_CHECKS,
        },
        separators=(",", ":"),
    ).encode()
).hexdigest()


class AuthError(Exception):
    """A credential did not resolve to a verified principal."""


class AuthSchemaMigrationError(AuthError):
    """The durable subject table exists with an unexpected shape."""


class AuthSubjectConflict(AuthError):
    """A verified subject could not converge to its deterministic owner."""


@dataclass(frozen=True, slots=True)
class UserClaims:
    """Decoded subject + scope claims from an external auth provider."""

    user_id: str
    email: str | None
    scopes: frozenset[str]
    issued_at: str


@dataclass(frozen=True, slots=True)
class VerifiedPrincipal:
    """A verified provider subject mapped to one durable Antiek owner."""

    owner_user_id: str
    provider: str
    subject: str
    email: str | None
    auth_method: str
    scopes: frozenset[str]


class AuthProvider(Protocol):
    """Decode a bearer token into :class:`UserClaims`."""

    def decode(self, token: str) -> UserClaims: ...


@dataclass
class MockAuthProvider:
    """Test-only provider used by the pre-existing unit seam."""

    tokens: dict[str, UserClaims]

    def decode(self, token: str) -> UserClaims:
        if token not in self.tokens:
            raise AuthError(f"unknown token: {token[:8]}…")
        return self.tokens[token]


def _now_iso() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def decode_token(provider: AuthProvider, bearer_token: str) -> UserClaims:
    """Decode and validate a bearer token via the injected provider."""

    if not bearer_token:
        raise AuthError("empty token")
    if bearer_token.lower().startswith("bearer "):
        bearer_token = bearer_token[7:]
    return provider.decode(bearer_token)


def normalize_subject(provider: str, subject: str) -> tuple[str, str]:
    """Return the canonical provider/subject pair or fail closed."""

    normalized_provider = provider.strip().lower()
    normalized_subject = subject.strip()
    if normalized_provider in {"magic_link", "passkey"}:
        normalized_subject = normalized_subject.lower()
    if not _PROVIDER_RE.fullmatch(normalized_provider):
        raise AuthError("invalid authenticated subject")
    if not _SUBJECT_RE.fullmatch(normalized_subject):
        raise AuthError("invalid authenticated subject")
    return normalized_provider, normalized_subject


def subject_owner_id(provider: str, subject: str) -> str:
    """Derive the only legal owner ID for a verified provider subject."""

    normalized_provider, normalized_subject = normalize_subject(provider, subject)
    digest = hashlib.sha256(normalized_subject.encode("ascii")).hexdigest()[:32]
    return f"user:{normalized_provider}:{digest}"


def ensure_auth_subjects_schema(primary_con: LockedConnection) -> None:
    """Create and verify the exact additive ``auth_subjects`` schema."""

    if not isinstance(primary_con, LockedConnection):
        raise TypeError("ensure_auth_subjects_schema requires a LockedConnection")
    primary_con.execute(AUTH_SUBJECTS_DDL)
    columns = tuple(
        (str(name), str(data_type), str(nullable), int(position))
        for name, data_type, nullable, position in primary_con.execute(
            "SELECT column_name,data_type,is_nullable,ordinal_position "
            "FROM information_schema.columns WHERE table_schema='main' "
            "AND table_name='auth_subjects' ORDER BY ordinal_position"
        ).fetchall()
    )
    keys = tuple(
        sorted(
            (
                str(kind),
                tuple(str(column) for column in names),
            )
            for kind, names in primary_con.execute(
                "SELECT constraint_type,constraint_column_names "
                "FROM duckdb_constraints() WHERE schema_name='main' "
                "AND table_name='auth_subjects' "
                "AND constraint_type IN ('PRIMARY KEY','UNIQUE')"
            ).fetchall()
        )
    )
    checks = tuple(
        sorted(
            (
                tuple(str(column) for column in names),
                str(text),
            )
            for names, text in primary_con.execute(
                "SELECT constraint_column_names,constraint_text "
                "FROM duckdb_constraints() WHERE schema_name='main' "
                "AND table_name='auth_subjects' AND constraint_type='CHECK'"
            ).fetchall()
        )
    )
    if (
        columns != _AUTH_SUBJECT_COLUMNS
        or keys != tuple(sorted(_AUTH_SUBJECT_KEYS))
        or checks != tuple(sorted(_AUTH_SUBJECT_CHECKS))
    ):
        raise AuthSchemaMigrationError("auth_schema_migration_required")


def mint_session_cookie(provider: str, subject: str, email: str) -> str:
    """Resolve/create a subject mapping and mint its signed session cookie.

    The owner is derived internally. The primary writer transaction contains
    schema verification, collision-safe insertion, exact readback, and cookie
    construction; a failed mint commits no subject mutation.
    """

    normalized_provider, normalized_subject = normalize_subject(provider, subject)
    normalized_email = email.strip().lower()
    if normalized_provider == "magic_link" and normalized_email != normalized_subject:
        raise AuthError("invalid authenticated subject")
    owner_user_id = subject_owner_id(normalized_provider, normalized_subject)
    db_path = default_db_path()
    con = connect_write(db_path, purpose="auth:mint_subject_session")
    try:
        con.execute("BEGIN TRANSACTION")
        ensure_auth_subjects_schema(con)
        now = datetime.now(UTC)
        con.execute(
            "INSERT INTO auth_subjects "
            "(provider,subject,owner_user_id,created_at,last_seen_at) "
            "VALUES (?,?,?,?,?) ON CONFLICT DO NOTHING",
            [normalized_provider, normalized_subject, owner_user_id, now, now],
        )
        row = con.execute(
            "SELECT owner_user_id FROM auth_subjects WHERE provider=? AND subject=?",
            [normalized_provider, normalized_subject],
        ).fetchone()
        if row is None or str(row[0]) != owner_user_id:
            raise AuthSubjectConflict("authenticated subject conflict")
        con.execute(
            "UPDATE auth_subjects SET last_seen_at=? WHERE provider=? AND subject=? "
            "AND owner_user_id=?",
            [now, normalized_provider, normalized_subject, owner_user_id],
        )
        cookie = _mint_signed_session_cookie(
            user_id=owner_user_id,
            email=normalized_email,
            provider=normalized_provider,
            subject=normalized_subject,
        )
        con.execute("COMMIT")
        return cookie
    except BaseException:
        with contextlib.suppress(Exception):
            con.execute("ROLLBACK")
        raise
    finally:
        con.close()


def resolve_authenticated_principal(request: Any) -> VerifiedPrincipal:
    """Verify a subject-bearing session and its durable owner relation.

    Request state is intentionally ignored. The caller must present signed
    credential bytes; a hand-written ``request.state.user_id`` is never proof.
    """

    cookie = request.cookies.get(_SESSION_COOKIE_NAME, "")
    if not cookie:
        raise AuthError("authenticated principal required")
    try:
        claims = verify_session_cookie(cookie)
    except InvalidSessionCookie as exc:
        raise AuthError("authenticated principal required") from exc
    if claims.provider is None or claims.subject is None:
        raise AuthError("authenticated principal required")
    provider, subject = normalize_subject(claims.provider, claims.subject)
    owner_user_id = subject_owner_id(provider, subject)
    if claims.user_id != owner_user_id:
        raise AuthError("authenticated principal required")
    if provider == "magic_link" and claims.email.strip().lower() != subject:
        raise AuthError("authenticated principal required")
    try:
        con = connect_read(default_db_path())
    except Exception as exc:
        raise AuthError("authenticated principal required") from exc
    try:
        row = con.execute(
            "SELECT owner_user_id FROM auth_subjects WHERE provider=? AND subject=?",
            [provider, subject],
        ).fetchone()
    except Exception as exc:
        raise AuthError("authenticated principal required") from exc
    finally:
        con.close()
    if row is None or str(row[0]) != owner_user_id:
        raise AuthError("authenticated principal required")
    return VerifiedPrincipal(
        owner_user_id=owner_user_id,
        provider=provider,
        subject=subject,
        email=claims.email,
        auth_method="antiek_session_cookie",
        scopes=frozenset({"private_research", "shared_substrate_write"}),
    )


def operator_claims() -> UserClaims:
    """Return the explicit local-compatibility operator identity."""

    return UserClaims(
        user_id="__operator__",
        email=None,
        scopes=frozenset({"operator", "private_research", "shared_substrate_write"}),
        issued_at=_now_iso(),
    )


__all__ = [
    "AUTH_SUBJECTS_DDL",
    "AUTH_SUBJECTS_SCHEMA_SHA256",
    "AuthError",
    "AuthProvider",
    "AuthSchemaMigrationError",
    "AuthSubjectConflict",
    "MockAuthProvider",
    "UserClaims",
    "VerifiedPrincipal",
    "decode_token",
    "ensure_auth_subjects_schema",
    "mint_session_cookie",
    "normalize_subject",
    "operator_claims",
    "resolve_authenticated_principal",
    "subject_owner_id",
]
