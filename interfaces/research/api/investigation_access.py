"""HTTP and machine authority boundary for globally keyed investigation streams."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from substrate.investigation_streams import (
    initialize_composite_stream,
    resolve_investigation_stream,
)
from substrate.investigation_tenancy import (
    InvestigationAuthority,
    InvestigationOwnershipConflict,
)
from substrate.multi_user.auth import UserClaims


class RequestState(Protocol):
    user_claims: UserClaims
    user_id: str
    scopes: frozenset[str]
    auth_method: str


class RequestLike(Protocol):
    state: RequestState


class InvestigationAccessDenied(RuntimeError):
    pass


class InvestigationAuthenticationRequired(InvestigationAccessDenied):
    pass


@dataclass(frozen=True)
class RequestInvestigationAuthority:
    authority: InvestigationAuthority
    scopes: frozenset[str]
    auth_method: str


def _validated_scopes(value: object) -> frozenset[str]:
    if not isinstance(value, frozenset) or not all(
        isinstance(scope, str) and scope for scope in value
    ):
        raise InvestigationAuthenticationRequired(
            "authenticated investigation identity required"
        )
    return value


def authority_from_request(
    request: RequestLike, investigation_id: str
) -> RequestInvestigationAuthority:
    state = getattr(request, "state", None)
    claims = getattr(state, "user_claims", None)
    auth_method = getattr(state, "auth_method", None)
    try:
        if not isinstance(claims, UserClaims):
            raise InvestigationAuthenticationRequired(
                "authenticated investigation identity required"
            )
        scopes = _validated_scopes(claims.scopes)
        # Scalar aliases remain for older endpoint consumers, but they may
        # never become a second source of identity truth.
        if (
            getattr(state, "user_id", None) != claims.user_id
            or getattr(state, "scopes", None) != claims.scopes
        ):
            raise InvestigationAuthenticationRequired(
                "authenticated investigation identity required"
            )
        authority = InvestigationAuthority(claims.user_id, investigation_id)
    except (TypeError, ValueError, InvestigationAuthenticationRequired) as exc:
        raise InvestigationAuthenticationRequired(
            "authenticated investigation identity required"
        ) from exc
    if not isinstance(auth_method, str) or not auth_method:
        raise InvestigationAuthenticationRequired(
            "authenticated investigation identity required"
        )
    return RequestInvestigationAuthority(authority, scopes, auth_method)


def authority_from_claims(
    claims: UserClaims, investigation_id: str
) -> RequestInvestigationAuthority:
    try:
        scopes = _validated_scopes(claims.scopes)
        authority = InvestigationAuthority(claims.user_id, investigation_id)
    except (TypeError, ValueError, InvestigationAccessDenied) as exc:
        raise InvestigationAccessDenied("validated machine identity required") from exc
    return RequestInvestigationAuthority(authority, scopes, "validated_machine_claims")


def authority_for_investigation(
    access: RequestInvestigationAuthority, investigation_id: str
) -> RequestInvestigationAuthority:
    try:
        authority = InvestigationAuthority(access.authority.account_id, investigation_id)
    except (TypeError, ValueError) as exc:
        raise InvestigationAccessDenied("investigation access denied") from exc
    return RequestInvestigationAuthority(authority, access.scopes, access.auth_method)


def event_actor(access: RequestInvestigationAuthority) -> tuple[str, str]:
    if (
        access.authority.account_id == "__operator__"
        and access.auth_method == "unauthenticated_local"
    ):
        return "operator", "operator-cli"
    return "authenticated_account", f"auth/{access.auth_method}"


def bind_new_investigation(access: RequestInvestigationAuthority) -> None:
    try:
        initialize_composite_stream(access.authority)
    except (InvestigationOwnershipConflict, RuntimeError, ValueError) as exc:
        raise InvestigationAccessDenied("investigation access denied") from exc


def bind_child_investigation(
    parent_access: RequestInvestigationAuthority, child_investigation_id: str
) -> RequestInvestigationAuthority:
    """Verify the parent, then allocate the child's account-scoped stream."""
    require_investigation_owner(parent_access)
    child_access = authority_for_investigation(parent_access, child_investigation_id)
    try:
        initialize_composite_stream(child_access.authority)
    except (InvestigationOwnershipConflict, RuntimeError, ValueError) as exc:
        raise InvestigationAccessDenied("investigation access denied") from exc
    return child_access


def require_investigation_owner(access: RequestInvestigationAuthority) -> None:
    try:
        resolve_investigation_stream(access.authority)
    except (InvestigationOwnershipConflict, RuntimeError, ValueError) as exc:
        raise InvestigationAccessDenied("investigation access denied") from exc


def owns_investigation(access: RequestInvestigationAuthority) -> bool:
    try:
        require_investigation_owner(access)
    except InvestigationAccessDenied:
        return False
    return True
