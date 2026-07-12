"""Real magic-link credentials through the complete owner-native research loop."""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import parse_qs, urlparse

from fastapi.testclient import TestClient

from interfaces.research.api.engagement_routes import reset_engagement_stores
from processing.embedding import HashEmbedding, _reset_default_provider
from runtime.db_lock import connect_write
from substrate.auth import MockEmailProvider, SqliteAuthStore
from substrate.dispatch import (
    NormalizedUsage,
    RawProviderResponse,
    register_provider,
    reset_provider_registry,
)
from substrate.graph.ops import insert_chunk, insert_document
from substrate.graph.schema import init_database
from substrate.graph_per_user.runtime import owner_graph_db_path

_SECRET = "multi-user-test-secret-" + "x" * 48


class _Provider:
    name = "zai"

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def call(self, *, model, prompt, max_tokens, temperature) -> RawProviderResponse:
        self.calls.append({"prompt": prompt})
        return RawProviderResponse(
            text='{"shape":"synthesis","synthesis_text":"grounded"}',
            raw_usage={"input_tokens": 1, "output_tokens": 1},
            finish_reason="stop",
            latency_ms=1,
            request_id="multi-user-owner-path",
        )

    def normalize_usage(self, raw_usage: dict[str, Any]) -> NormalizedUsage:
        return NormalizedUsage(input_tokens=1, output_tokens=1)


def _token_from_email(sender: MockEmailProvider, index: int) -> str:
    body = sender.sent[index].email.text_body
    match = re.search(r"https://[^\s]+", body)
    assert match is not None
    return parse_qs(urlparse(match.group(0)).query)["token"][0]


def test_registration_modes_fail_closed_and_operator_stays_explicit(
    monkeypatch, tmp_path
):
    from interfaces.research.api.app import create_app

    sender = MockEmailProvider(log_to_stdout=False)
    monkeypatch.setattr("interfaces.research.api.auth.get_email_provider", lambda: sender)
    monkeypatch.setenv("ANTIEK_AUTH_SECRET", _SECRET)
    monkeypatch.setenv("ANTIEK_MULTI_USER_AUTH", "1")
    monkeypatch.setenv("ANTIEK_AUTH_DB_PATH", str(tmp_path / "auth.sqlite3"))
    monkeypatch.setenv("ANTIEK_COOKIE_INSECURE", "1")
    monkeypatch.setenv("ANTIEK_OPERATOR_EMAIL", "operator@example.com")
    monkeypatch.delenv("ANTIEK_OPERATOR_TOKEN", raising=False)
    monkeypatch.delenv("ANTIEK_OPERATOR_SERVICE_TOKEN_CLIENT_ID", raising=False)

    monkeypatch.setenv("ANTIEK_AUTH_REGISTRATION_MODE", "operator_only")
    app = create_app(register_wrestling=False, register_providers=False, cors_origins=[])
    client = TestClient(app)
    hidden = client.post("/auth/request", json={"email": "user@example.com"})
    assert hidden.status_code == 200
    assert hidden.json() == {"sent": True}
    assert sender.sent == []

    operator_request = client.post(
        "/auth/request", json={"email": "operator@example.com"}
    )
    assert operator_request.status_code == 200
    operator_token = _token_from_email(sender, 0)
    callback = client.get(
        f"/auth/callback?token={operator_token}", follow_redirects=False
    )
    assert callback.status_code == 302
    identity = client.get("/auth/me").json()
    assert identity["user_id"] == "__operator__"
    assert identity["email"] == "operator@example.com"
    assert identity["is_operator"] is True

    monkeypatch.setenv("ANTIEK_AUTH_REGISTRATION_MODE", "allowlist")
    monkeypatch.setenv("ANTIEK_USER_EMAIL", "user@example.com")
    allowlist_app = create_app(
        register_wrestling=False, register_providers=False, cors_origins=[]
    )
    allowlist_client = TestClient(allowlist_app)
    allowed = allowlist_client.post(
        "/auth/request", json={"email": "user@example.com"}
    )
    assert allowed.status_code == 200
    assert len(sender.sent) == 2


def test_multi_user_dev_login_mints_a_durable_operator_session(monkeypatch, tmp_path):
    from interfaces.research.api.app import create_app
    from substrate.auth import mint_session_cookie, verify_session_cookie

    monkeypatch.setenv("ANTIEK_AUTH_SECRET", _SECRET)
    monkeypatch.setenv("ANTIEK_MULTI_USER_AUTH", "1")
    monkeypatch.setenv("ANTIEK_AUTH_DB_PATH", str(tmp_path / "auth.sqlite3"))
    monkeypatch.setenv("ANTIEK_COOKIE_INSECURE", "1")
    monkeypatch.setenv("ANTIEK_DEV_LOGIN_TOKEN", "local-browser-bootstrap")
    monkeypatch.delenv("ANTIEK_OPERATOR_EMAIL", raising=False)
    app = create_app(register_wrestling=False, register_providers=False, cors_origins=[])
    client = TestClient(app)

    login = client.get(
        "/auth/dev-login?token=local-browser-bootstrap", follow_redirects=False
    )
    assert login.status_code == 302
    identity = client.get("/auth/me")
    assert identity.status_code == 200
    assert identity.json()["user_id"] == "__operator__"
    assert identity.json()["is_operator"] is True

    valid_cookie = client.cookies.get("ANTIEK_SESSION")
    assert valid_cookie is not None
    valid_claims = verify_session_cookie(valid_cookie)
    assert valid_claims.session_id is not None
    tampered_identity = mint_session_cookie(
        user_id="usr_attacker",
        email="attacker@example.com",
        session_id=valid_claims.session_id,
    )
    rejected = TestClient(app).get(
        "/auth/me", headers={"Cookie": f"ANTIEK_SESSION={tampered_identity}"}
    )
    assert rejected.status_code == 401

    assert client.post("/auth/logout").status_code == 204
    revoked = TestClient(app).get(
        "/auth/me", headers={"Cookie": f"ANTIEK_SESSION={valid_cookie}"}
    )
    assert revoked.status_code == 401


def test_real_user_credentials_reach_only_their_owner_research_path(
    monkeypatch, tmp_path
):
    from interfaces.research.api.app import create_app

    auth_db = tmp_path / "auth.sqlite3"
    canonical_db = tmp_path / "canonical.duckdb"
    owner_root = tmp_path / "owners"
    monkeypatch.setenv("ANTIEK_AUTH_SECRET", _SECRET)
    monkeypatch.setenv("ANTIEK_MULTI_USER_AUTH", "1")
    monkeypatch.setenv("ANTIEK_AUTH_REGISTRATION_MODE", "open")
    monkeypatch.setenv("ANTIEK_AUTH_DB_PATH", str(auth_db))
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", str(canonical_db))
    monkeypatch.setenv("ANTIEK_USER_GRAPH_DIR", str(owner_root))
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", str(tmp_path / "events"))
    monkeypatch.setenv("ANTIEK_EMBEDDING_PROVIDER", "hash")
    monkeypatch.setenv("ANTIEK_COOKIE_INSECURE", "1")
    monkeypatch.setenv("ANTIEK_OPERATOR_TOKEN", "operator-machine-token")
    monkeypatch.delenv("ANTIEK_OPERATOR_EMAIL", raising=False)
    monkeypatch.delenv("ANTIEK_OPERATOR_SERVICE_TOKEN_CLIENT_ID", raising=False)
    _reset_default_provider()
    reset_engagement_stores()
    reset_provider_registry()

    canonical = connect_write(str(canonical_db), purpose="multi_user_public_seed")
    try:
        init_database(canonical)
        model = HashEmbedding()
        insert_document(
            canonical,
            document_id="public-doc",
            source_tier=1,
            document_type="paper",
            title="Public evidence",
            content_class="public_domain",
        )
        insert_chunk(
            canonical,
            document_id="public-doc",
            chunk_index=0,
            text="PUBLIC SHARED PHOTONIC EVIDENCE",
            embedding=model.encode("PUBLIC SHARED PHOTONIC EVIDENCE"),
            embedding_provider=model,
        )
        insert_document(
            canonical,
            document_id="operator-private-doc",
            source_tier=1,
            document_type="paper",
            title="Operator private evidence",
            content_class="personal_reading",
        )
        insert_chunk(
            canonical,
            document_id="operator-private-doc",
            chunk_index=0,
            text="OPERATOR PRIVATE PHOTONIC EVIDENCE",
            embedding=model.encode("OPERATOR PRIVATE PHOTONIC EVIDENCE"),
            embedding_provider=model,
        )
    finally:
        canonical.close()

    import importlib

    search_mod = importlib.import_module("substrate.graph.search")
    monkeypatch.setattr(search_mod, "SentenceTransformerEmbedding", HashEmbedding)
    sender = MockEmailProvider(log_to_stdout=False)
    monkeypatch.setattr("interfaces.research.api.auth.get_email_provider", lambda: sender)
    store = SqliteAuthStore(auth_db)
    app = create_app(
        register_wrestling=False,
        register_providers=False,
        cors_origins=[],
        auth_account_store=store,
    )
    provider = _Provider()
    register_provider(provider)
    alice = TestClient(app)
    bob = TestClient(app)

    def login(client: TestClient, email: str, email_index: int) -> tuple[str, str]:
        requested = client.post("/auth/request", json={"email": email})
        assert requested.status_code == 200
        token = _token_from_email(sender, email_index)
        callback = client.get(
            f"/auth/callback?token={token}", follow_redirects=False
        )
        assert callback.status_code == 302
        replay = TestClient(app).get(
            f"/auth/callback?token={token}", follow_redirects=False
        )
        assert "magic_link_invalid" in replay.headers["location"]
        identity = client.get("/auth/me")
        assert identity.status_code == 200
        body = identity.json()
        assert body["email"] == email
        assert body["is_operator"] is False
        assert body["scopes"] == ["basic", "private_research"]
        assert body["user_id"].startswith("usr_")
        cookie = client.cookies.get("ANTIEK_SESSION")
        assert cookie is not None
        return body["user_id"], cookie

    alice_id, alice_cookie = login(alice, "alice@example.com", 0)
    bob_id, _bob_cookie = login(bob, "bob@example.com", 1)
    assert alice_id != bob_id

    def promote_and_prompt(client: TestClient, owner: str) -> str:
        marker = f"{owner.upper()} PRIVATE PHOTONIC MEMORY"
        opened = client.post(
            "/engagement/sessions/open",
            json={"asset_id": "shared-asset", "selection_text": "same passage"},
        )
        assert opened.status_code == 200, opened.text
        session_id = opened.json()["session_id"]
        recorded = client.post(
            f"/engagement/sessions/{session_id}/twins",
            json={"kind": "insight", "text": marker},
        )
        assert recorded.status_code == 200
        preview = client.post(
            f"/engagement/sessions/{session_id}/twins/promote-preview",
            json={"include_html": False},
        )
        confirmed = client.post(
            f"/engagement/sessions/{session_id}/twins/promote-confirm",
            json={
                "include_html": False,
                "expected_preview_sha256": preview.json()["promotion_preview_sha256"],
                "idempotency_key": f"{owner}-real-credential-proof",
            },
        )
        assert confirmed.status_code == 200, confirmed.text
        legacy = client.post(
            "/engagement/merge",
            json={"parent_asset_id": "shared-asset", "spawn_ids": []},
        )
        assert legacy.status_code == 403
        response = client.post(
            "/thought-partner", json={"prompt": "private photonic memory"}
        )
        assert response.status_code == 200, response.text
        return provider.calls[-1]["prompt"]

    alice_prompt = promote_and_prompt(alice, "alice")
    bob_prompt = promote_and_prompt(bob, "bob")
    assert "PUBLIC SHARED PHOTONIC EVIDENCE" in alice_prompt
    assert "PUBLIC SHARED PHOTONIC EVIDENCE" in bob_prompt
    assert "OPERATOR PRIVATE PHOTONIC EVIDENCE" not in alice_prompt
    assert "OPERATOR PRIVATE PHOTONIC EVIDENCE" not in bob_prompt
    assert "ALICE PRIVATE PHOTONIC MEMORY" in alice_prompt
    assert "BOB PRIVATE PHOTONIC MEMORY" not in alice_prompt
    assert "BOB PRIVATE PHOTONIC MEMORY" in bob_prompt
    assert "ALICE PRIVATE PHOTONIC MEMORY" not in bob_prompt
    assert "alice@example.com" not in owner_graph_db_path(alice_id)
    assert "bob@example.com" not in owner_graph_db_path(bob_id)
    owner_db = connect_write(
        owner_graph_db_path(alice_id), purpose="multi_user_identifier_audit"
    )
    try:
        owner_identifiers = [
            row[0] for row in owner_db.execute("SELECT node_id FROM nodes").fetchall()
        ]
    finally:
        owner_db.close()
    assert owner_identifiers
    assert all("alice@example.com" not in value for value in owner_identifiers)
    assert all("bob@example.com" not in value for value in owner_identifiers)

    # Authentication is not blanket authorization: historically global
    # surfaces remain operator-only until explicitly migrated to owner-native
    # request.state identity.
    for method, path, payload in (
        ("POST", "/events/typed", {}),
        ("POST", "/loop-3/checklist", {}),
        ("GET", "/ops/provider-ratio", None),
        ("GET", "/meta-readings", None),
        ("POST", "/engagement/merge", {"parent_asset_id": "x", "spawn_ids": []}),
    ):
        denied = alice.request(method, path, json=payload)
        assert denied.status_code == 403, (method, path, denied.text)

    operator = TestClient(app).get(
        "/auth/whoami",
        headers={"Authorization": "Bearer operator-machine-token"},
    )
    assert operator.status_code == 200
    assert operator.json()["user_id"] == "__operator__"
    assert operator.json()["is_operator"] is True

    assert alice.post("/auth/logout").status_code == 204
    replay = TestClient(app).get(
        "/auth/me", headers={"Cookie": f"ANTIEK_SESSION={alice_cookie}"}
    )
    assert replay.status_code == 401

    alice_id_again, _ = login(alice, "alice@example.com", 2)
    assert alice_id_again == alice_id
    store.set_status(alice_id, "disabled")
    assert alice.get("/auth/me").status_code == 401
    assert bob.get("/auth/me").status_code == 200
    operator_after_disable = TestClient(app).get(
        "/auth/whoami",
        headers={"Authorization": "Bearer operator-machine-token"},
    )
    assert operator_after_disable.status_code == 200
    reset_provider_registry()
    _reset_default_provider()
