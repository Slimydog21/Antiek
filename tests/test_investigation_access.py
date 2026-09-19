from __future__ import annotations

from types import SimpleNamespace

import pytest

from interfaces.research.api.investigation_access import (
    InvestigationAccessDenied,
    authority_from_claims,
    authority_from_request,
    bind_child_investigation,
    bind_new_investigation,
    event_actor,
    owns_investigation,
    require_investigation_owner,
)
from substrate.multi_user.auth import UserClaims


def _request(user_id: str = "alice", **aliases):
    claims = UserClaims(
        user_id=user_id,
        email=None,
        scopes=frozenset({"private_research"}),
        issued_at="2026-07-15T00:00:00Z",
    )
    state = SimpleNamespace(
        user_claims=claims,
        user_id=user_id,
        scopes=claims.scopes,
        auth_method="session_cookie",
    )
    return SimpleNamespace(state=state, **aliases)


def test_request_authority_uses_only_authenticated_state(tmp_path, monkeypatch):
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", str(tmp_path))
    request = _request(
        "alice",
        account_id="bob",
        owner_id="bob",
        query_params={"user_id": "bob"},
        headers={"X-Owner-Id": "bob"},
    )
    access = authority_from_request(request, "shared")
    assert access.authority.account_id == "alice"


@pytest.mark.parametrize(
    "state",
    [
        SimpleNamespace(),
        SimpleNamespace(user_claims="forged", user_id="alice", scopes=frozenset(), auth_method="session"),
        SimpleNamespace(user_id="alice", scopes=frozenset(), auth_method=""),
        SimpleNamespace(user_id=" alice", scopes=frozenset(), auth_method="session"),
        SimpleNamespace(user_id="alice", scopes={"private_research"}, auth_method="session"),
    ],
)
def test_missing_or_malformed_request_identity_fails_closed(tmp_path, monkeypatch, state):
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", str(tmp_path))
    with pytest.raises(InvestigationAccessDenied, match="identity required"):
        authority_from_request(SimpleNamespace(state=state), "inv")


def test_composite_start_is_idempotent_and_allows_same_display_for_two_accounts(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", str(tmp_path))
    alice = authority_from_request(_request("alice"), "same")
    bob = authority_from_request(_request("bob"), "same")
    bind_new_investigation(alice)
    bind_new_investigation(alice)
    bind_new_investigation(bob)
    require_investigation_owner(alice)
    require_investigation_owner(bob)
    assert owns_investigation(alice) is True
    assert owns_investigation(bob) is True
    assert alice.authority.stream_key != bob.authority.stream_key


def test_machine_authority_requires_explicit_validated_claims(tmp_path, monkeypatch):
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", str(tmp_path))
    claims = UserClaims(
        user_id="machine-account",
        email=None,
        scopes=frozenset({"private_research"}),
        issued_at="2026-07-15T00:00:00Z",
    )
    access = authority_from_claims(claims, "job")
    assert access.authority.account_id == "machine-account"
    assert access.auth_method == "validated_machine_claims"
    assert event_actor(access) == (
        "authenticated_account",
        "auth/validated_machine_claims",
    )


def test_authenticated_start_cannot_first_claim_unbound_historic_stream(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", str(tmp_path))
    stream = tmp_path / "historic.jsonl"
    stream.write_text('{"private":"historic"}\n', encoding="utf-8")
    before = stream.read_bytes()
    access = authority_from_request(_request("alice"), "historic")
    with pytest.raises(InvestigationAccessDenied, match="access denied"):
        bind_new_investigation(access)
    assert stream.read_bytes() == before
    assert not list((tmp_path / ".tenancy" / "legacy-stream-leases").glob("*.json"))


def test_child_inherits_only_from_owned_parent(tmp_path, monkeypatch):
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", str(tmp_path))
    alice_parent = authority_from_request(_request("alice"), "parent")
    bind_new_investigation(alice_parent)

    child = bind_child_investigation(alice_parent, "child")
    require_investigation_owner(child)
    assert child.authority.account_digest == alice_parent.authority.account_digest

    before = sorted(tmp_path.rglob("*"))
    with pytest.raises(InvestigationAccessDenied, match="access denied"):
        bind_child_investigation(authority_from_request(_request("bob"), "parent"), "forged")
    assert sorted(tmp_path.rglob("*")) == before
