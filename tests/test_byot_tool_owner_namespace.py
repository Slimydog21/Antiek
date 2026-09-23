"""A connected BYO tool must be readable by the search that spends it.

`settings_tool_connections._owner` returned `request.state.user_id` verbatim,
refusing the `__operator__` sentinel only for machine auth methods. Every
production login mints exactly that sentinel on a session cookie, so a
connection was WRITTEN under `__operator__` while `research_tool_search` READ it
under the derived `acct_<hash>`. `registry._record_key` hashes the owner into
the dict key, so the two never named the same row: connecting a tool appeared to
succeed and the credential was then invisible to every search that would spend
it.

The read half had already been fixed and its docstring recorded the asymmetry.
Only the write half was left.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from interfaces.research.api.research_tool_search import _owner as read_owner
from interfaces.research.api.research_tool_search import _PublicError
from interfaces.research.api.settings_tool_connections import _owner as write_owner

ADDRESS = "operator@example.com"


def _request(*, auth_method: str, user_id: str, email: str | None = ADDRESS) -> SimpleNamespace:
    return SimpleNamespace(
        state=SimpleNamespace(auth_method=auth_method, user_id=user_id, user_email=email)
    )


def _both_refuse(request: SimpleNamespace) -> None:
    """Both halves must refuse, each in its own error type.

    The two raise different exceptions by design — the settings route is FastAPI
    (``HTTPException``) and the search path wraps its own ``_PublicError`` — so
    this asserts each precisely rather than catching ``Exception`` and proving
    only that something went wrong.
    """
    with pytest.raises(HTTPException) as write_exc:
        write_owner(request)
    assert write_exc.value.status_code == 401
    with pytest.raises(_PublicError) as read_exc:
        read_owner(request)
    assert read_exc.value.args[0] == 401


# ---------------------------------------------------------------------------
# The defect
# ---------------------------------------------------------------------------

def test_write_and_read_resolve_the_same_owner_for_a_real_login():
    """The production posture: session cookie carrying the operator sentinel."""
    request = _request(auth_method="antiek_session_cookie", user_id="__operator__")
    assert write_owner(request) == read_owner(request)


def test_the_resolved_owner_is_derived_not_the_sentinel():
    request = _request(auth_method="antiek_session_cookie", user_id="__operator__")
    owner = write_owner(request)
    assert owner.startswith("acct_")
    assert owner != "__operator__"


def test_a_genuine_per_user_id_passes_through_unchanged():
    """Sprint 22+ multi-user sessions must not be rewritten."""
    request = _request(auth_method="antiek_session_cookie", user_id="user-7f3a")
    assert write_owner(request) == "user-7f3a"
    assert read_owner(request) == "user-7f3a"


# ---------------------------------------------------------------------------
# Fail-closed: both halves must refuse identically
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("auth_method", ["bearer_token", "cloudflare_service_token"])
def test_machine_methods_are_refused_by_both_halves(auth_method):
    """A machine proves no person, so the sentinel must not resolve to one."""
    request = _request(auth_method=auth_method, user_id="__operator__")
    _both_refuse(request)


@pytest.mark.parametrize("shared", ["shared", "service", "local"])
def test_other_shared_sentinels_get_no_fallback_in_either_half(shared):
    request = _request(auth_method="antiek_session_cookie", user_id=shared)
    _both_refuse(request)


def test_a_session_without_a_verified_address_fails_closed_in_both_halves():
    request = _request(auth_method="antiek_session_cookie", user_id="__operator__", email=None)
    _both_refuse(request)


# ---------------------------------------------------------------------------
# Control: the two halves share ONE predicate, so they cannot drift apart
# ---------------------------------------------------------------------------

def test_both_halves_delegate_to_the_shared_predicate():
    """Structural, not behavioural.

    Four hand-rolled copies of this logic is how the write half drifted from
    the read half in the first place. If a future edit re-inlines either one,
    this fails even when the behaviour still happens to agree.
    """
    import inspect

    from interfaces.research.api import research_tool_search, settings_tool_connections

    for module in (settings_tool_connections, research_tool_search):
        source = inspect.getsource(module._owner)
        assert "distinct_signed_owner(" in source, f"{module.__name__} re-inlined the predicate"
        assert "derive_owner_from_verified_email" not in source, (
            f"{module.__name__} hand-rolls the derivation again"
        )
