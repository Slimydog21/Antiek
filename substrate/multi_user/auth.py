"""Auth provider Protocol + mock for tests.

Production wires Clerk or Supabase Auth via the
`auth_provider` injection. Substrate-internal code receives
``UserClaims`` rather than raw tokens; the auth seam is at the API
layer (interfaces/research/api/app.py middleware), not at substrate.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol

from substrate.auth.account_store import AuthAccount


class AuthError(Exception):
    """Raised on token-decode or claim-validation failure."""


@dataclass(frozen=True)
class UserClaims:
    """Decoded subject + scope claims from an auth-provider token.

    Operator's own usage is represented with user_id='__operator__'
    matching the existing `owner_user_id` default in
    substrate/graph/schema.py — multi-user is additive, not a rewrite.
    """

    user_id: str
    email: str | None
    scopes: frozenset[str]
    issued_at: str  # ISO 8601


class AuthProvider(Protocol):
    """Decode a bearer token into UserClaims. Production uses Clerk
    or Supabase; tests use MockAuthProvider."""

    def decode(self, token: str) -> UserClaims: ...


@dataclass
class MockAuthProvider:
    """Test-only auth provider. Maps a static token → UserClaims for
    unit tests. Production NEVER uses this — the only mention should
    be in tests."""

    tokens: dict[str, UserClaims]

    def decode(self, token: str) -> UserClaims:
        if token not in self.tokens:
            raise AuthError(f"unknown token: {token[:8]}…")
        return self.tokens[token]


def _now_iso() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def decode_token(provider: AuthProvider, bearer_token: str) -> UserClaims:
    """Decode and validate a bearer token via the auth provider.

    Strips the optional 'Bearer ' prefix per RFC 6750.
    """
    if not bearer_token:
        raise AuthError("empty token")
    if bearer_token.lower().startswith("bearer "):
        bearer_token = bearer_token[7:]
    return provider.decode(bearer_token)


def operator_claims() -> UserClaims:
    """Convenience: the canonical operator UserClaims. Sprint 17-21
    code paths use this implicitly (owner_user_id='__operator__'
    in DB schema); Sprint 22+ multi-user paths use the auth provider
    instead. Both coexist during the transition."""
    return UserClaims(
        user_id="__operator__",
        email=None,
        scopes=frozenset({"operator", "private_research", "shared_substrate_write"}),
        issued_at=_now_iso(),
    )


def account_claims(account: AuthAccount) -> UserClaims:
    """Derive current request scopes from server-owned account state."""
    if account.status != "active":
        raise AuthError("account is not active")
    if account.role == "operator":
        return UserClaims(
            user_id="__operator__",
            email=account.email,
            scopes=frozenset(
                {"operator", "private_research", "shared_substrate_write"}
            ),
            issued_at=_now_iso(),
        )
    if account.role != "user":
        raise AuthError("account role is invalid")
    return UserClaims(
        user_id=account.user_id,
        email=account.email,
        scopes=frozenset({"basic", "private_research"}),
        issued_at=_now_iso(),
    )
