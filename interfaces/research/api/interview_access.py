"""Strict request-to-interview operator authority boundary."""

from __future__ import annotations

from interfaces.research.api.notebook_access import NotebookAuthenticationRequired
from substrate.interviews.authority import (
    LOCAL_OPERATOR_ACCOUNT,
    InterviewAccountAuthority,
    operator_interview_account_authority,
)
from substrate.multi_user.auth import UserClaims


def interview_account_authority_from_request(
    request: object,
) -> InterviewAccountAuthority:
    state = getattr(request, "state", None)
    claims = getattr(state, "user_claims", None)
    auth_method = getattr(state, "auth_method", None)
    if (
        not isinstance(claims, UserClaims)
        or getattr(state, "user_id", None) != claims.user_id
        or getattr(state, "scopes", None) != claims.scopes
        or not isinstance(claims.scopes, frozenset)
        or not all(isinstance(scope, str) and scope for scope in claims.scopes)
        or not isinstance(auth_method, str)
        or not auth_method
    ):
        raise NotebookAuthenticationRequired("authenticated interview identity required")
    if auth_method == "unauthenticated_local":
        if claims.user_id != LOCAL_OPERATOR_ACCOUNT:
            raise NotebookAuthenticationRequired("authenticated interview identity required")
        return operator_interview_account_authority()
    try:
        return InterviewAccountAuthority(claims.user_id)
    except (TypeError, ValueError) as exc:
        raise NotebookAuthenticationRequired("authenticated interview identity required") from exc


__all__ = ["interview_account_authority_from_request"]
