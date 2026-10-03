"""Notebook reads distinguish an owner's content from a withheld notebook."""
from __future__ import annotations

import hashlib
import json

import pytest
from fastapi.testclient import TestClient

from interfaces.research.api.app import create_app
from runtime.db_lock import connect_write
from substrate.auth import mint_session_cookie
from substrate.graph import default_db_path
from substrate.notebooks import append_block, create_notebook

PRIVATE = "BOB_PRIVATE_NOTEBOOK_86134"
ROUTES = (
    "/notebooks/{notebook_id}",
    "/api/notebooks/{notebook_id}/artifact.html",
    "/api/notebooks/{notebook_id}/artifact?format=html",
)


@pytest.fixture
def notebook_clients(monkeypatch):
    monkeypatch.setenv("ANTIEK_AUTH_SECRET", "notebook-hermetic-test-signing-secret")
    monkeypatch.setenv("ANTIEK_OPERATOR_EMAIL", "alice@example.test,bob@example.test")
    monkeypatch.delenv("ANTIEK_OPERATOR_TOKEN", raising=False)
    app = create_app(register_wrestling=False, register_providers=False, cors_origins=[])
    clients = {"anonymous": TestClient(app)}
    for caller in ("alice", "bob"):
        client = TestClient(app)
        client.cookies.set("ANTIEK_SESSION", mint_session_cookie(
            user_id=caller, email=caller + "@example.test",
        ))
        identity = client.get("/auth/me")
        assert identity.status_code == 200
        assert identity.json()["user_id"] == caller
        clients[caller] = client
    return clients


def seed_notebook(*, owner="bob", content_class="user_owned", empty=False):
    with connect_write(default_db_path(), purpose="test/notebook-ownership") as con:
        notebook_id = create_notebook(
            con, title="Bob's notebook", owner_user_id=owner, content_class=content_class,
        )
        if not empty:
            append_block(con, notebook_id, block_type="prose", content={
                "type": "paragraph", "content": [{"type": "text", "text": PRIVATE}],
            })
    return notebook_id


def observe(client, caller, path):
    response = client.get(path)
    print("NOTEBOOK_BOUNDARY", json.dumps({
        "caller": caller, "path": path, "status": response.status_code,
        "contains_private_marker": PRIVATE in response.text,
        "bytes": len(response.content),
        "sha256": hashlib.sha256(response.content).hexdigest(),
        "body_excerpt": response.text[:600],
    }, sort_keys=True))
    return response


@pytest.mark.parametrize("route", ROUTES)
def test_notebook_read_as_both_owners_and_anonymous(notebook_clients, route):
    notebook_id = seed_notebook()
    path = route.format(notebook_id=notebook_id)
    # Record all identities before asserting, including on the unfixed code.
    replies = {caller: observe(client, caller, path)
               for caller, client in notebook_clients.items()}
    assert replies["anonymous"].status_code == 401
    assert PRIVATE not in replies["anonymous"].text
    assert replies["bob"].status_code == 200
    assert PRIVATE in replies["bob"].text
    assert replies["alice"].status_code == 403
    assert PRIVATE not in replies["alice"].text
    assert "withheld" in replies["alice"].text.lower()


@pytest.mark.parametrize("route", ROUTES)
@pytest.mark.parametrize("owner", ["", "__operator__"])
def test_unknown_or_legacy_owner_is_not_the_signed_in_caller(notebook_clients, route, owner):
    notebook_id = seed_notebook(owner=owner)
    for caller in ("alice", "bob"):
        response = observe(notebook_clients[caller], caller, route.format(notebook_id=notebook_id))
        assert response.status_code == 403
        assert PRIVATE not in response.text


@pytest.mark.parametrize("route", ROUTES)
def test_owner_cannot_be_asserted_in_query_or_headers(notebook_clients, route):
    notebook_id = seed_notebook()
    path = route.format(notebook_id=notebook_id)
    response = notebook_clients["alice"].get(path, params={
        "owner_user_id": "bob", "user_id": "bob", "owner": "true",
    }, headers={"X-User-Id": "bob", "X-Owner-User-Id": "bob"})
    assert response.status_code == 403
    assert PRIVATE not in response.text


@pytest.mark.parametrize("route", ROUTES)
def test_absent_and_owned_empty_notebook_are_not_withheld(notebook_clients, route):
    notebook_id = seed_notebook(empty=True)
    client = notebook_clients["bob"]
    missing = client.get(route.format(notebook_id="nb-missing"))
    empty = client.get(route.format(notebook_id=notebook_id))
    withheld = notebook_clients["alice"].get(route.format(notebook_id=notebook_id))
    assert missing.status_code == 404
    assert empty.status_code == 200
    assert withheld.status_code == 403
    assert "withheld" in withheld.text.lower()
    if route.startswith("/notebooks/"):
        assert empty.json()["blocks"] == []


@pytest.mark.parametrize("route", ROUTES)
def test_public_class_is_not_a_share_grant(notebook_clients, route):
    # Promotion currently has no owner-bound grant. These are private read routes.
    notebook_id = seed_notebook(content_class="user_public_contribution")
    path = route.format(notebook_id=notebook_id)
    assert notebook_clients["alice"].get(path).status_code == 403
    owner = notebook_clients["bob"].get(path)
    assert owner.status_code == 200
    assert PRIVATE in owner.text



def test_session_creator_can_read_but_cannot_choose_notebook_owner(notebook_clients):
    notebooks = {}
    for caller in ("alice", "bob"):
        foreign = "bob" if caller == "alice" else "alice"
        response = notebook_clients[caller].post(
            "/notebooks", params={"owner_user_id": foreign, "user_id": foreign},
            headers={"X-User-Id": foreign},
            json={"title": f"Created by {caller}", "owner_user_id": foreign, "user_id": foreign},
        )
        assert response.status_code == 201
        notebooks[caller] = response.json()["notebook_id"]
    observed = []
    for caller in ("alice", "bob"):
        for creator, notebook_id in notebooks.items():
            for route in ROUTES:
                response = observe(notebook_clients[caller], caller, route.format(notebook_id=notebook_id))
                observed.append((caller, creator, response))
    for caller, creator, response in observed:
        assert response.status_code == (200 if caller == creator else 403)
        if caller == creator:
            assert f"Created by {creator}" in response.text
        else:
            assert f"Created by {creator}" not in response.text
    with connect_write(default_db_path()) as con:
        stored = dict(con.execute("SELECT notebook_id, owner_user_id FROM notebooks").fetchall())
    assert {creator: stored[notebook_id] for creator, notebook_id in notebooks.items()} == {
        "alice": "alice", "bob": "bob",
    }
    assert notebook_clients["anonymous"].post("/notebooks", json={"title": "no owner"}).status_code == 401
