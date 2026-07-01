"""Auth provider Protocol + mock for tests.

Production wires Clerk or Supabase Auth via the
`auth_provider` injection. Substrate-internal code receives
``UserClaims`` rather than raw tokens; the auth seam is at the API
layer (interfaces/research/api/app.py middleware), not at substrate.
"""

from __future__ import annotations

import enum
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Protocol


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


class AuthVendor(enum.StrEnum):
    """Externally-managed auth vendors supported by the Sprint 22 seam.

    This enum does not choose the operator's vendor. It keeps the substrate's
    user-id namespace explicit so a future migration cannot accidentally merge
    identities from two issuers that happened to use the same ``sub`` value.
    """

    CLERK = "clerk"
    SUPABASE = "supabase"


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


def _issued_at_from_claims(claims: Mapping[str, Any]) -> str:
    raw_iat = claims.get("iat")
    if isinstance(raw_iat, int | float) and raw_iat > 0:
        return datetime.fromtimestamp(raw_iat, UTC).isoformat().replace(
            "+00:00", "Z",
        )
    return _now_iso()


def _string_list(value: Any) -> list[str]:
    """Normalize provider metadata into a small list of clean strings."""
    if isinstance(value, str):
        return [part.strip() for part in value.replace(",", " ").split() if part.strip()]
    if isinstance(value, list | tuple | set | frozenset):
        out: list[str] = []
        for item in value:
            if isinstance(item, str) and item.strip():
                out.append(item.strip())
        return out
    return []


def _metadata_scopes(claims: Mapping[str, Any]) -> set[str]:
    """Read Antiek-specific scopes from common vendor metadata homes.

    Clerk and Supabase both support custom JWT/session metadata, but they expose
    it under different keys depending on configuration. Accepting a few explicit
    homes keeps scope mapping deterministic without tying downstream graph code
    to either provider's raw payload shape.
    """
    scopes: set[str] = set()
    for container_key in (
        "app_metadata",
        "user_metadata",
        "public_metadata",
        "private_metadata",
        "metadata",
    ):
        container = claims.get(container_key)
        if isinstance(container, Mapping):
            scopes.update(_string_list(container.get("antiek_scopes")))
            scopes.update(_string_list(container.get("scopes")))
    return scopes


def _provider_scopes(claims: Mapping[str, Any]) -> frozenset[str]:
    scopes: set[str] = {"authenticated"}
    scopes.update(_string_list(claims.get("scope")))
    scopes.update(_string_list(claims.get("scp")))
    scopes.update(_metadata_scopes(claims))
    return frozenset(scopes)


def normalize_verified_claims(
    *,
    vendor: AuthVendor | str,
    claims: Mapping[str, Any],
) -> UserClaims:
    """Convert an already-verified provider JWT payload into ``UserClaims``.

    This function deliberately does **not** verify JWT signatures. Signature,
    issuer, audience, expiry, and key-rotation checks belong to the provider
    adapter at the HTTP boundary. The substrate seam starts only after those
    checks have passed, then enforces the stable shape downstream code needs:
    namespaced user id, optional email, normalized scopes, and ISO issued-at.
    """
    try:
        auth_vendor = vendor if isinstance(vendor, AuthVendor) else AuthVendor(vendor)
    except ValueError as exc:
        raise AuthError(f"unsupported auth vendor: {vendor!r}") from exc

    sub = claims.get("sub")
    if not isinstance(sub, str) or not sub.strip():
        raise AuthError("verified auth claims missing non-empty 'sub'")
    email = claims.get("email")
    if email is not None and not isinstance(email, str):
        raise AuthError("verified auth claim 'email' must be a string when present")

    return UserClaims(
        user_id=f"{auth_vendor.value}:{sub.strip()}",
        email=email.strip().lower() if isinstance(email, str) and email.strip() else None,
        scopes=_provider_scopes(claims),
        issued_at=_issued_at_from_claims(claims),
    )


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
