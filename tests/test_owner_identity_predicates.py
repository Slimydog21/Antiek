"""The two owner predicates must agree on who a person is, and fail closed together.

Antiek resolves "which person is this request" in three places for three purposes:

  * ``account_memory_identity.distinct_signed_owner`` — whose private memory and
    whose ingested documents these are;
  * ``owner_byot_dispatch.authenticated_distinct_owner`` — whose API credential and
    whose budget this request may spend;
  * ``research_tool_search._owner`` — whose connected third-party tool credential
    (X, YouTube, and the finance vendors) this search may spend.

They must return the SAME value for the same human. If they ever diverge, a person's
spend is attributed to an identity their own memory cannot see, and the BYOT usage
dashboard silently reports on an account nobody owns. That invariant is not obvious
from either module in isolation, which is exactly why it is pinned here.

Both predicates previously refused ``__operator__`` outright. That is the user_id all
four production login paths mint, so both refused every real request: account memory and
document ingest answered 401, and all four owner-paid BYOT entry points answered 409 or
422. The shared fallback resolves a stable owner from the verified session e-mail.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from interfaces.research.api.account_memory_identity import (
    SESSION_AUTH_METHOD,
    derive_owner_from_verified_email,
    distinct_signed_owner,
)
from interfaces.research.api.owner_byot_dispatch import (
    OwnerByotDispatchUnavailable,
    authenticated_distinct_owner,
)
from interfaces.research.api.research_tool_search import _PublicError
from interfaces.research.api.research_tool_search import _owner as tool_search_owner

OPERATOR_EMAIL = "operator@example.test"


def _request(method: str, user_id: object, email: object) -> SimpleNamespace:
    return SimpleNamespace(
        state=SimpleNamespace(auth_method=method, user_id=user_id, user_email=email)
    )


def _byot(method: str, user_id: object, email: object) -> str | None:
    try:
        return authenticated_distinct_owner(_request(method, user_id, email))
    except OwnerByotDispatchUnavailable:
        return None


def _memory(user_id: object, email: object) -> str | None:
    return distinct_signed_owner(_request(SESSION_AUTH_METHOD, user_id, email))


def _tools(method: str, user_id: object, email: object) -> str | None:
    try:
        return tool_search_owner(_request(method, user_id, email))
    except _PublicError:
        return None


def test_both_predicates_resolve_the_operator_session_to_one_owner() -> None:
    """The load-bearing invariant: one person, one owner, across memory, spend and tools."""
    memory_owner = _memory("__operator__", OPERATOR_EMAIL)
    spend_owner = _byot(SESSION_AUTH_METHOD, "__operator__", OPERATOR_EMAIL)
    tools_owner = _tools(SESSION_AUTH_METHOD, "__operator__", OPERATOR_EMAIL)

    assert memory_owner is not None, "account memory refused a real operator session"
    assert spend_owner is not None, "BYOT dispatch refused a real operator session"
    assert tools_owner is not None, "connected-tool search refused a real operator session"
    assert memory_owner == spend_owner == tools_owner


def test_connected_tool_search_fails_closed_the_same_way() -> None:
    """The tool predicate shares the boundary, not just the happy path.

    Note the asymmetry this closed: ``settings_tool_connections`` already refused the
    sentinel only for machine auth methods, so STORING a connected credential worked
    while every search that would USE one answered 401. The chassis looked wired end to
    end precisely because nothing downstream of the gate had ever been reached.
    """
    assert _tools(SESSION_AUTH_METHOD, "__operator__", None) is None
    assert _tools("bearer_token", "__operator__", OPERATOR_EMAIL) is None
    assert _tools("cloudflare_service_token", "__operator__", OPERATOR_EMAIL) is None
    for sentinel in ("shared", "service", "local"):
        assert _tools(SESSION_AUTH_METHOD, sentinel, OPERATOR_EMAIL) is None
    assert _tools(SESSION_AUTH_METHOD, "usr_real_123", OPERATOR_EMAIL) == "usr_real_123"


def test_both_predicates_pass_a_genuine_user_id_through_unchanged() -> None:
    """Sprint 22+ per-user ids are used verbatim; the fallback is not reached."""
    assert _memory("usr_real_123", OPERATOR_EMAIL) == "usr_real_123"
    assert _byot(SESSION_AUTH_METHOD, "usr_real_123", OPERATOR_EMAIL) == "usr_real_123"


@pytest.mark.parametrize("method", ["cloudflare_service_token", "bearer_token"])
def test_machine_callers_cannot_spend_a_persons_credential(method: str) -> None:
    """A machine caller carries no verified address, so it resolves to no owner.

    ``app.py`` attaches these two methods with no e-mail, so the fallback finds nothing
    and the predicate raises. A token-authenticated robot must never be handed a
    person's key to spend.
    """
    assert _byot(method, "__operator__", None) is None
    # Even if an address were somehow present, these methods do not prove a person
    # verified it, so they must still refuse.
    assert _byot(method, "__operator__", OPERATOR_EMAIL) is None


def test_unauthenticated_local_never_resolves_an_owner() -> None:
    """Local dev proves no identity. Both predicates stay closed."""
    assert _memory("__operator__", OPERATOR_EMAIL) is not None  # control
    assert distinct_signed_owner(
        _request("unauthenticated_local", "__operator__", OPERATOR_EMAIL)
    ) is None
    assert _byot("unauthenticated_local", "__operator__", OPERATOR_EMAIL) is None


@pytest.mark.parametrize("sentinel", ["shared", "service", "local"])
def test_other_shared_sentinels_get_no_fallback(sentinel: str) -> None:
    """Only ``__operator__`` is rescued. The rest name a shared or machine context.

    No authentication path mints these, so their presence means something genuinely
    shared is calling, and a matching address must not promote it to a person.
    """
    assert _memory(sentinel, OPERATOR_EMAIL) is None
    assert _byot(SESSION_AUTH_METHOD, sentinel, OPERATOR_EMAIL) is None


@pytest.mark.parametrize("email", [None, "", "   ", "not-an-email", "a@b@c", "@no-local"])
def test_missing_or_malformed_address_fails_closed(email: object) -> None:
    """No address, no owner — never a fabricated one."""
    assert _memory("__operator__", email) is None
    assert _byot(SESSION_AUTH_METHOD, "__operator__", email) is None


def test_derivation_is_stable_distinct_and_keeps_the_address_out_of_the_value() -> None:
    first = derive_owner_from_verified_email("Operator@Example.TEST")
    assert first is not None
    assert first == derive_owner_from_verified_email("  operator@example.test  ")
    assert first != derive_owner_from_verified_email("someone-else@example.test")
    assert first.startswith("acct_")
    # The stored owner must not carry the address into rows or diagnostics.
    for fragment in ("operator", "example", "@"):
        assert fragment not in first.removeprefix("acct_")
