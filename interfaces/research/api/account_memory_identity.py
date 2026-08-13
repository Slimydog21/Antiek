"""Single owner-identity predicate for private account-memory boundaries."""

from __future__ import annotations

from fastapi import Request

SESSION_AUTH_METHOD = "antiek_session_cookie"
_FORBIDDEN_OWNERS = frozenset({"__operator__", "shared", "service", "local"})


def distinct_signed_owner(request: Request) -> str | None:
    """Return the normalized distinct owner, or ``None`` when proof is unsafe."""
    state = getattr(request, "state", None)
    if getattr(state, "auth_method", None) != SESSION_AUTH_METHOD:
        return None
    value = getattr(state, "user_id", None)
    if not isinstance(value, str):
        return None
    owner = value.strip()
    if not owner or len(owner) > 256 or owner.casefold() in _FORBIDDEN_OWNERS:
        return None
    return owner


__all__ = ["SESSION_AUTH_METHOD", "distinct_signed_owner"]
