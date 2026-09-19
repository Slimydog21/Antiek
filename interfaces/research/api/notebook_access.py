"""Strict request-to-notebook authority boundary."""

from __future__ import annotations

from typing import Protocol

from substrate.multi_user.auth import UserClaims
from substrate.notebooks.authority import (
    LOCAL_OPERATOR_ACCOUNT,
    NotebookAccountAuthority,
    operator_notebook_account_authority,
)


class RequestState(Protocol):
    user_claims: UserClaims
    user_id: str
    scopes: frozenset[str]
    auth_method: str


class RequestLike(Protocol):
    state: RequestState


class NotebookAccessDenied(RuntimeError):
    pass


class NotebookAuthenticationRequired(NotebookAccessDenied):
    pass


def notebook_account_authority_from_request(
    request: RequestLike,
    *,
    allow_missing_local_state: bool = False,
) -> NotebookAccountAuthority:
    """Validate canonical middleware claims; never accept caller identity input."""

    state = getattr(request, "state", None)
    claims = getattr(state, "user_claims", None)
    auth_method = getattr(state, "auth_method", None)
    if claims is None and auth_method is None and allow_missing_local_state:
        return operator_notebook_account_authority()
    if not isinstance(claims, UserClaims):
        raise NotebookAuthenticationRequired("authenticated notebook identity required")
    if (
        getattr(state, "user_id", None) != claims.user_id
        or getattr(state, "scopes", None) != claims.scopes
        or not isinstance(claims.scopes, frozenset)
        or not all(isinstance(scope, str) and scope for scope in claims.scopes)
        or not isinstance(auth_method, str)
        or not auth_method
    ):
        raise NotebookAuthenticationRequired("authenticated notebook identity required")
    if auth_method == "unauthenticated_local":
        if claims.user_id != LOCAL_OPERATOR_ACCOUNT:
            raise NotebookAuthenticationRequired(
                "authenticated notebook identity required"
            )
        return operator_notebook_account_authority()
    try:
        return NotebookAccountAuthority(claims.user_id)
    except (TypeError, ValueError) as exc:
        raise NotebookAuthenticationRequired(
            "authenticated notebook identity required"
        ) from exc


__all__ = [
    "NotebookAccessDenied",
    "NotebookAuthenticationRequired",
    "notebook_account_authority_from_request",
]
