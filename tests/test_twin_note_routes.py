from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from interfaces.research.api.app import create_app
from substrate.auth import mint_session_cookie
from substrate.twin_note_taker.compression import DurableTwinNoteCompression
from tests.test_twin_note_serving import served


@pytest.fixture
def client(served, monkeypatch):
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", served[0])
    return TestClient(create_app(register_wrestling=False, register_providers=False))


def test_list_history_exact_headers_and_blob(client, served):
    _, _, a, _ = served
    listed = client.get("/research/twin-notes")
    assert listed.status_code == 200 and listed.json()["assets"][0]["asset_id"] == "asset"
    assert listed.headers["cache-control"] == "private, no-store"
    history = client.get("/research/twin-notes/assets/asset/revisions")
    assert history.json()["revisions"][1]["revision_id"] == a.revision_id
    exact = client.get(f"/research/twin-notes/revisions/{a.revision_id}")
    assert exact.content == a.html_bytes and exact.headers["x-content-type-options"] == "nosniff"
    assert "default-src 'none'" in exact.headers["content-security-policy"]


def test_compose_strict_value_free_422_and_order(client, served):
    _, _, a, b = served
    bad = client.post("/research/twin-notes/compositions", json={"revision_ids": [a.revision_id, b.revision_id], "account_id": "leak"})
    assert bad.status_code == 422 and bad.json() == {"detail": "twin-note request is invalid"}
    assert "leak" not in bad.text and bad.headers["cache-control"] == "private, no-store"
    made = client.post("/research/twin-notes/compositions", json={"revision_ids": [a.revision_id, b.revision_id]})
    assert [m["member_ordinal"] for m in made.json()["members"]] == [0, 1]
    opened = client.get(made.json()["url"]); assert opened.status_code == 200 and opened.headers["cache-control"] == "private, no-store"


def test_foreign_missing_no_oracle(client, served):
    missing = client.get("/research/twin-notes/revisions/tnr-" + "0" * 32)
    assert missing.status_code == 404 and missing.json() == {"detail": "twin-note resource is unavailable"}
    assert "sha" not in missing.text and "path" not in missing.text


@pytest.fixture
def authenticated_accounts(served, tmp_path, monkeypatch):
    db, _, own_a, own_b = served
    foreign = DurableTwinNoteCompression(lambda *_: True, db_path=db,
        publication_root=tmp_path / "foreign-published", events_dir=str(tmp_path / "events"))
    foreign_a = foreign.compress(account_id="account-b", asset_id="asset", window_ids=("w-a",))
    foreign_b = foreign.compress(account_id="account-b", asset_id="asset", window_ids=("w-b",),
                                 expected_predecessor=foreign_a.revision_id)
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", db)
    monkeypatch.setenv("ANTIEK_AUTH_SECRET", "cycle-48-test-secret")
    monkeypatch.setenv("ANTIEK_OPERATOR_EMAIL", "a@example.test,b@example.test")
    app = create_app(register_wrestling=False, register_providers=False)
    clients = {}
    for account, email in (("__operator__", "a@example.test"), ("account-b", "b@example.test")):
        c = TestClient(app)
        c.cookies.set("ANTIEK_SESSION", mint_session_cookie(user_id=account, email=email))
        clients[account] = c
    return clients, (own_a, own_b), (foreign_a, foreign_b)


def test_real_signed_sessions_are_owner_bound_and_propagate_user_id(authenticated_accounts, monkeypatch):
    clients, own, foreign = authenticated_accounts
    seen = []
    from interfaces.research.api import twin_note_routes
    real_service = twin_note_routes._service
    class RecordingService:
        def __getattr__(self, name):
            target = getattr(real_service(), name)
            def call(account_id, *args, **kwargs):
                seen.append(account_id)
                return target(account_id, *args, **kwargs)
            return call
    monkeypatch.setattr(twin_note_routes, "_service", RecordingService)
    for account, revisions in (("__operator__", own), ("account-b", foreign)):
        c = clients[account]
        listed = c.get("/research/twin-notes")
        assert listed.status_code == 200
        assert [(x["asset_label"], x["current_revision"]["revision_id"]) for x in listed.json()["assets"]] == [("asset", revisions[1].revision_id)]
        history = c.get("/research/twin-notes/assets/asset/revisions")
        assert [x["revision_id"] for x in history.json()["revisions"]] == [revisions[1].revision_id, revisions[0].revision_id]
        assert c.get(f"/research/twin-notes/revisions/{revisions[0].revision_id}").content == revisions[0].html_bytes
    assert seen == ["__operator__"] * 3 + ["account-b"] * 3


@pytest.mark.parametrize("kind", ["asset", "history", "revision", "composition"])
def test_foreign_and_missing_http_resources_are_equivalent(authenticated_accounts, kind):
    clients, own, foreign = authenticated_accounts
    c = clients["__operator__"]
    made = clients["account-b"].post("/research/twin-notes/compositions",
        json={"revision_ids": [foreign[0].revision_id, foreign[1].revision_id]}).json()
    probes = {
        "asset": ("/research/twin-notes/assets/missing/revisions", "/research/twin-notes/assets/foreign/revisions"),
        "history": ("/research/twin-notes/assets/missing/revisions", "/research/twin-notes/assets/foreign/revisions"),
        "revision": ("/research/twin-notes/revisions/tnr-" + "0" * 32, f"/research/twin-notes/revisions/{foreign[0].revision_id}"),
        "composition": ("/research/twin-notes/compositions/tnc-" + "0" * 32, made["url"]),
    }
    responses = [c.get(url) for url in probes[kind]]
    assert [(r.status_code, r.json()) for r in responses] == [(404, {"detail": "twin-note resource is unavailable"})] * 2


def test_mixed_owner_composition_is_same_oracle_as_missing(authenticated_accounts):
    clients, own, foreign = authenticated_accounts
    c = clients["__operator__"]
    mixed = c.post("/research/twin-notes/compositions", json={"revision_ids": [own[0].revision_id, foreign[0].revision_id]})
    missing = c.post("/research/twin-notes/compositions", json={"revision_ids": [own[0].revision_id, "tnr-" + "0" * 32]})
    assert (mixed.status_code, mixed.json()) == (missing.status_code, missing.json()) == (404, {"detail": "twin-note resource is unavailable"})


def test_authentication_is_required_when_real_auth_is_enabled(authenticated_accounts):
    clients, _, _ = authenticated_accounts
    anonymous = TestClient(clients["__operator__"].app)
    response = anonymous.get("/research/twin-notes")
    assert response.status_code == 401
