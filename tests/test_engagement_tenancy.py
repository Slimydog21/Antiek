from __future__ import annotations

from fastapi.testclient import TestClient
from starlette.requests import Request

from interfaces.research.api import engagement_routes
from interfaces.research.api.app import create_app
from interfaces.research.api.broadcast import EventBroadcaster
from substrate.auth import mint_magic_link_token
from substrate.engagement_spine import (
    HighlightSelection,
    InMemoryEngagementStore,
    record_twin_insight,
    spawn_from_highlight,
)
from substrate.engagement_spine.authority import EngagementAuthority
from substrate.engagement_spine.store import authorized_store
from substrate.floating_session.store import InMemorySessionStore, authorized_session_store
from substrate.multi_user.auth import UserClaims


def _request(user_id: str) -> Request:
    request = Request({"type": "http", "method": "GET", "path": "/", "headers": []})
    claims = UserClaims(
        user_id=user_id,
        email=None,
        scopes=frozenset({"private_research"}),
        issued_at="2026-07-15T00:00:00Z",
    )
    request.state.user_claims = claims
    request.state.user_id = user_id
    request.state.scopes = claims.scopes
    request.state.auth_method = "session_cookie"
    return request


def test_same_display_asset_isolated_and_spawn_ids_owner_qualified() -> None:
    base = InMemoryEngagementStore()
    alice = authorized_store(base, EngagementAuthority("alice"))
    bob = authorized_store(base, EngagementAuthority("bob"))

    selection = HighlightSelection(
        asset_id="shared-book", selection_text="same passage", region_id="same-region"
    )
    alice_spawn = spawn_from_highlight(selection, store=alice)
    bob_spawn = spawn_from_highlight(selection, store=bob)

    assert alice_spawn.spawn_id != bob_spawn.spawn_id
    assert alice.get_spawn(alice_spawn.spawn_id) is not None
    assert alice.get_spawn(bob_spawn.spawn_id) is None
    assert bob.get_spawn(alice_spawn.spawn_id) is None
    assert [row["spawn_id"] for row in alice.list_spawns("shared-book")] == [alice_spawn.spawn_id]


def test_twins_documents_and_sessions_are_account_scoped() -> None:
    engagement = InMemoryEngagementStore()
    sessions = InMemorySessionStore()
    alice_authority = EngagementAuthority("alice")
    bob_authority = EngagementAuthority("bob")
    alice = authorized_store(engagement, alice_authority)
    bob = authorized_store(engagement, bob_authority)

    record_twin_insight("shared", "Alice private insight", store=alice)
    record_twin_insight("shared", "Bob private insight", store=bob)
    assert [note["text"] for note in alice.list_twins("shared")] == ["Alice private insight"]
    assert [note["text"] for note in bob.list_twins("shared")] == ["Bob private insight"]

    alice.put_document("draft", {"body": "alice"})
    bob.put_document("draft", {"body": "bob"})
    assert alice.get_document("draft")["body"] == "alice"
    assert bob.get_document("draft")["body"] == "bob"

    alice_sessions = authorized_session_store(sessions, alice_authority)
    bob_sessions = authorized_session_store(sessions, bob_authority)
    alice_sessions.put_session(
        {"session_id": "ses-alice", "parent_asset_id": "shared", "status": "open"}
    )
    bob_sessions.put_session(
        {"session_id": "ses-bob", "parent_asset_id": "shared", "status": "open"}
    )
    assert [row["session_id"] for row in alice_sessions.list_sessions("shared")] == ["ses-alice"]
    assert alice_sessions.get_session("ses-bob") is None


def test_embedded_owner_tamper_fails_closed() -> None:
    base = InMemoryEngagementStore()
    alice = authorized_store(base, EngagementAuthority("alice"))
    spawn = spawn_from_highlight(
        HighlightSelection(asset_id="asset", selection_text="passage"), store=alice
    )
    next(iter(base._spawns.values()))["owner_account_digest"] = "tampered"
    assert alice.get_spawn(spawn.spawn_id) is None


def test_request_authority_uses_authenticated_claims_and_not_display_ids() -> None:
    engagement_routes.reset_engagement_stores()
    alice = engagement_routes._eng_for(_request("alice"))
    bob = engagement_routes._eng_for(_request("bob"))
    alice_spawn = spawn_from_highlight(
        HighlightSelection(asset_id="shared", selection_text="alice-only"), store=alice
    )
    assert bob.get_spawn(alice_spawn.spawn_id) is None


def test_authenticated_http_accounts_cannot_read_each_others_engagements(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", str(tmp_path / "events"))
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", str(tmp_path / "graph.duckdb"))
    monkeypatch.setenv("ANTIEK_AUTH_SECRET", "engagement-canary-" + "x" * 48)
    monkeypatch.setenv("ANTIEK_COOKIE_INSECURE", "1")
    monkeypatch.setenv("ANTIEK_OPERATOR_EMAIL", "alice@example.test,bob@example.test")
    monkeypatch.delenv("ANTIEK_OPERATOR_TOKEN", raising=False)
    engagement_routes.reset_engagement_stores()
    app = create_app(
        broadcaster=EventBroadcaster(),
        cors_origins=[],
        register_wrestling=False,
        register_providers=False,
    )
    alice = TestClient(app)
    bob = TestClient(app)
    for email, client in (
        ("alice@example.test", alice),
        ("bob@example.test", bob),
    ):
        response = client.get(
            f"/auth/callback?token={mint_magic_link_token(email)}",
            follow_redirects=False,
        )
        assert response.status_code == 302

    payload = {
        "asset_id": "shared-book",
        "selection_text": "account-private passage",
        "region_id": "same-region",
        "references": ["arxiv:1706.03762"],
    }
    alice_spawn = alice.post("/engagement/spawn-from-highlight", json=payload)
    bob_spawn = bob.post("/engagement/spawn-from-highlight", json=payload)
    assert alice_spawn.status_code == bob_spawn.status_code == 200
    alice_id = alice_spawn.json()["spawn_id"]
    bob_id = bob_spawn.json()["spawn_id"]
    assert alice_id != bob_id

    foreign = bob.get(f"/engagement/progress/{alice_id}")
    nonexistent = bob.get("/engagement/progress/spn_never-created")
    assert (foreign.status_code, foreign.json()) == (
        nonexistent.status_code,
        nonexistent.json(),
    )
    assert foreign.status_code == 404
