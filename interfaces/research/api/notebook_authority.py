"""Request-bound authority for ordinary notebook reads and mutations."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from fastapi import HTTPException, Request

from substrate.auth import InvalidSessionCookie, verify_session_cookie
from substrate.constants import FORBIDDEN_OWNERS
from substrate.multi_user.auth import AuthError, resolve_authenticated_principal
from substrate.notebooks import VALID_NOTEBOOK_CONTENT_CLASSES

from .operator_allowlist import operator_allowlist_from_env


@dataclass(frozen=True)
class NotebookAuthority:
    owner_user_id: str | None
    public_reader: bool
    historical_sentinel: bool


@dataclass(frozen=True)
class NotebookParent:
    notebook_id: str
    title: str
    owner_user_id: str | None
    content_class: str | None
    document_id: str | None


def _usable_owner(value: object) -> bool:
    return (
        isinstance(value, str)
        and bool(value)
        and value == value.strip()
        and value.casefold() not in FORBIDDEN_OWNERS
    )


def authority_from_request(request: Request) -> NotebookAuthority:
    """Accept a current mapped human, a real legacy cookie, or a machine reader."""

    state = request.state
    method = getattr(state, "auth_method", None)
    state_owner = getattr(state, "user_id", None)
    state_email = getattr(state, "user_email", None)
    allowlist = operator_allowlist_from_env()
    owner: str | None = None
    public_reader = False
    legacy_claims: Any = None

    if method == "antiek_session_cookie":
        if getattr(state, "legacy_session", False):
            try:
                legacy_claims = verify_session_cookie(request.cookies.get("ANTIEK_SESSION", ""))
            except InvalidSessionCookie:
                legacy_claims = None
            public_reader = (
                legacy_claims is not None
                and legacy_claims.user_id == state_owner
                and legacy_claims.email == state_email
            )
        else:
            try:
                principal = resolve_authenticated_principal(request)
            except AuthError:
                principal = None
            if (
                principal is not None
                and principal.provider == "magic_link"
                and principal.auth_method == method
                and getattr(state, "verified_principal", None) == principal
                and state_owner == principal.owner_user_id
                and state_email == principal.email
                and _usable_owner(principal.owner_user_id)
            ):
                owner = principal.owner_user_id
                public_reader = True
    elif method in {"bearer_token", "cloudflare_service_token"}:
        # Only middleware attaches these methods after validating configured
        # credentials. They may read shared public rows, never own a notebook.
        public_reader = isinstance(state_owner, str) and bool(state_owner)

    if not public_reader:
        raise HTTPException(status_code=401, detail="notebook authentication required")

    only_email = next(iter(allowlist)) if len(allowlist) == 1 else None
    same_email = (
        only_email is not None
        and isinstance(state_email, str)
        and state_email == state_email.strip().lower()
        and state_email == only_email
    )
    verified_sentinel = owner is not None and same_email
    legacy_sentinel = (
        same_email
        and legacy_claims is not None
        and legacy_claims.user_id == "__operator__"
        and legacy_claims.provider is None
        and legacy_claims.subject is None
        and state_owner == "__operator__"
    )
    return NotebookAuthority(
        owner_user_id=owner,
        public_reader=True,
        historical_sentinel=bool(verified_sentinel or legacy_sentinel),
    )


def admit_parent(
    con: Any,
    notebook_id: str,
    authority: NotebookAuthority,
    *,
    mode: Literal["read", "write"],
) -> NotebookParent | None:
    """Read parent metadata only; return no details for denied rows."""

    if mode not in {"read", "write"}:
        raise ValueError("unsupported notebook authority mode")
    row = con.execute(
        "SELECT notebook_id,title,owner_user_id,content_class,document_id "
        "FROM notebooks WHERE notebook_id=?",
        [notebook_id],
    ).fetchone()
    if row is None:
        return None
    parent = NotebookParent(*row)
    if parent.content_class not in VALID_NOTEBOOK_CONTENT_CLASSES:
        return None
    owned = (
        authority.owner_user_id is not None
        and parent.owner_user_id == authority.owner_user_id
    )
    historical = (
        authority.historical_sentinel
        and parent.owner_user_id == "__operator__"
    )
    if owned or historical:
        return parent
    if mode == "read" and authority.public_reader and parent.content_class == "user_public_contribution":
        return parent
    return None


def visible_notebook_ids(
    con: Any,
    authority: NotebookAuthority,
    *,
    investigation_id: str | None,
    document_id: str | None,
    limit: int,
) -> list[str]:
    """Apply visibility before ordering, limit, and block hydration."""

    arms: list[str] = []
    params: list[Any] = [*sorted(VALID_NOTEBOOK_CONTENT_CLASSES)]
    if authority.public_reader:
        arms.append("content_class = ?")
        params.append("user_public_contribution")
    if authority.owner_user_id is not None:
        arms.append("owner_user_id = ?")
        params.append(authority.owner_user_id)
    if authority.historical_sentinel:
        arms.append("owner_user_id = ?")
        params.append("__operator__")
    if not arms:
        return []
    sql = (
        "SELECT notebook_id FROM notebooks "
        "WHERE content_class IN (?, ?) AND (" + " OR ".join(arms) + ")"
    )
    if investigation_id is not None:
        sql += " AND investigation_id = ?"
        params.append(investigation_id)
    if document_id is not None:
        sql += " AND document_id = ?"
        params.append(document_id)
    sql += " ORDER BY updated_at DESC, notebook_id ASC LIMIT ?"
    params.append(limit)
    return [str(row[0]) for row in con.execute(sql, params).fetchall()]
