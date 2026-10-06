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
    # A public class alone does not grant access to these owner-only routes.
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


MUTATIONS = ("append", "patch", "patch-noop", "delete", "reorder", "replace", "promote")


def mutation_request(operation, notebook_id, blocks):
    first, second = [block.block_id for block in blocks]
    if operation == "append":
        return "POST", f"/notebooks/{notebook_id}/blocks", {
            "block_type": "prose", "content": {"text": "OWNER_APPEND"},
        }
    if operation in ("patch", "patch-noop"):
        payload = {} if operation == "patch-noop" else {
            "content": {"text": "OWNER_PATCH"}, "ref_id": "owner-chosen-ref",
        }
        return "PATCH", f"/notebooks/{notebook_id}/blocks/{first}", payload
    if operation == "delete":
        return "DELETE", f"/notebooks/{notebook_id}/blocks/{first}", None
    if operation == "reorder":
        return "POST", f"/notebooks/{notebook_id}/blocks/reorder", {
            "ordered_block_ids": [second, first],
        }
    if operation == "replace":
        return "PUT", f"/notebooks/{notebook_id}/content", {
            "doc": {"type": "doc", "content": [
                {"type": "paragraph", "content": [{"type": "text", "text": "OWNER_REPLACE"}]},
            ]},
        }
    assert operation == "promote"
    return "POST", f"/notebooks/{notebook_id}/promote-public?force=true", None


@pytest.mark.parametrize("operation", MUTATIONS)
def test_mutations_preserve_foreign_notebook_and_serve_owning_bob(notebook_clients, operation):
    from substrate.notebooks import get_notebook

    observed = []
    for caller, client in notebook_clients.items():
        notebook_id = seed_notebook()
        with connect_write(default_db_path()) as con:
            append_block(con, notebook_id, block_type="prose", content={"text": "SECOND_BLOCK"})
            before = get_notebook(con, notebook_id)
        method, path, payload = mutation_request(operation, notebook_id, before.blocks)
        response = client.request(method, path, json=payload)
        with connect_write(default_db_path()) as con:
            after = get_notebook(con, notebook_id)
        print("NOTEBOOK_MUTATION", json.dumps({
            "caller": caller, "operation": operation, "method": method, "path": path,
            "status": response.status_code, "contains_private_marker": PRIVATE in response.text,
            "persisted_unchanged": before == after, "blocks_before": len(before.blocks),
            "blocks_after": len(after.blocks), "owner_after": after.owner_user_id,
            "class_after": after.content_class, "body_excerpt": response.text[:600],
        }, sort_keys=True))
        observed.append((caller, response, before, after))
    # Bob runs even when Alice's assertion would fail on the original routes.
    for caller, response, before, after in observed:
        if caller != "bob":
            assert response.status_code == (401 if caller == "anonymous" else 403)
            assert PRIVATE not in response.text
            assert after == before
            continue
        assert response.status_code == (201 if operation == "append" else 200)
        assert after.owner_user_id == "bob"
        assert response.json()["notebook_id"] == after.notebook_id
        assert [b["content_json"] for b in response.json()["blocks"]] == [
            b.content_json for b in after.blocks
        ]
        if operation == "append":
            assert after.blocks[:2] == before.blocks
            assert after.blocks[2].content_json == {"text": "OWNER_APPEND"}
        elif operation == "patch":
            assert after.blocks[0].content_json == {"text": "OWNER_PATCH"}
            assert after.blocks[0].ref_id == "owner-chosen-ref"
            assert after.blocks[1] == before.blocks[1]
        elif operation == "patch-noop":
            assert after == before
            assert PRIVATE in response.text
        elif operation == "delete":
            assert len(after.blocks) == 1
            assert after.blocks[0].block_id == before.blocks[1].block_id
            assert after.blocks[0].block_index == 0
        elif operation == "reorder":
            assert [b.block_id for b in after.blocks] == [b.block_id for b in reversed(before.blocks)]
        elif operation == "replace":
            assert len(after.blocks) == 1
            assert after.blocks[0].content_json["content"][0]["text"] == "OWNER_REPLACE"
        elif operation == "promote":
            assert before.content_class == "user_owned"
            assert after.content_class == "user_public_contribution"
            assert after.blocks == before.blocks
            assert PRIVATE in response.text

def test_notebook_list_keeps_bobs_notebook_out_of_alices_list(notebook_clients):
    notebook_id = seed_notebook()
    replies = {caller: observe(client, caller, "/notebooks")
               for caller, client in notebook_clients.items()}
    detail = observe(notebook_clients["alice"], "alice", f"/notebooks/{notebook_id}")
    assert replies["anonymous"].status_code == 401
    assert replies["bob"].status_code == 200
    assert [nb["notebook_id"] for nb in replies["bob"].json()["notebooks"]] == [notebook_id]
    assert detail.status_code == 403
    assert replies["alice"].status_code == 200
    assert replies["alice"].json() == {"count": 0, "notebooks": []}
    assert PRIVATE not in replies["alice"].text
    assert PRIVATE not in replies["bob"].text
    assert "blocks" not in replies["bob"].json()["notebooks"][0]
    owner_detail = notebook_clients["bob"].get(f"/notebooks/{notebook_id}")
    assert owner_detail.status_code == 200
    assert PRIVATE in owner_detail.text


@pytest.mark.parametrize("owner", ["", "   ", "__operator__", "shared", "bob"])
@pytest.mark.parametrize("content_class", ["user_owned", "user_public_contribution"])
def test_notebook_list_excludes_unknown_shared_and_foreign_rows(
    notebook_clients, owner, content_class,
):
    hidden = seed_notebook(owner=owner, content_class=content_class)
    own = seed_notebook(owner="alice", empty=True)
    response = observe(notebook_clients["alice"], "alice", "/notebooks")
    assert response.status_code == 200
    body = response.json()
    assert body["count"] == 1
    assert [nb["notebook_id"] for nb in body["notebooks"]] == [own]
    assert hidden not in response.text
    assert PRIVATE not in response.text
    assert set(body["notebooks"][0]) == {
        "notebook_id", "title", "investigation_id", "document_id",
        "content_class", "created_at", "updated_at",
    }


@pytest.mark.parametrize("caller,foreign", [("alice", "bob"), ("bob", "alice")])
@pytest.mark.parametrize("surface", ["body", "query", "header"])
def test_notebook_list_ignores_spoofed_owner(notebook_clients, caller, foreign, surface):
    own = seed_notebook(owner=caller)
    hidden = seed_notebook(owner=foreign)
    spoof = {"owner_user_id": foreign, "user_id": foreign, "owner": "true"}
    kwargs = {
        "body": {"json": spoof},
        "query": {"params": spoof},
        "header": {"headers": {"X-User-Id": foreign, "X-Owner-User-Id": foreign}},
    }[surface]
    response = notebook_clients[caller].request("GET", "/notebooks", **kwargs)
    print("NOTEBOOK_LIST_SPOOF", json.dumps({
        "caller": caller, "surface": surface, "status": response.status_code,
        "body": response.json(),
    }, sort_keys=True))
    assert response.status_code == 200
    assert response.json()["count"] == 1
    assert [nb["notebook_id"] for nb in response.json()["notebooks"]] == [own]
    assert hidden not in response.text
    assert PRIVATE not in response.text


@pytest.mark.parametrize("filters", [
    {"investigation_id": "inv-shared"},
    {"document_id": "doc-shared"},
    {"investigation_id": "inv-shared", "document_id": "doc-shared"},
])
def test_notebook_list_scopes_before_filters_and_limit(notebook_clients, filters):
    with connect_write(default_db_path(), purpose="test/notebook-list-filter") as con:
        ids = {}
        for caller in ("alice", "bob"):
            ids[caller] = create_notebook(
                con, title=caller, owner_user_id=caller,
                investigation_id="inv-shared", document_id="doc-shared",
            )
        create_notebook(con, title="Other binding", owner_user_id="alice",
                        investigation_id="inv-other", document_id="doc-other")
        con.execute("UPDATE notebooks SET updated_at = '2100-01-01' WHERE notebook_id = ?",
                    [ids["bob"]])
    for caller in ("alice", "bob"):
        response = notebook_clients[caller].get("/notebooks", params={**filters, "limit": 1})
        assert response.status_code == 200
        assert response.json()["count"] == 1
        assert [nb["notebook_id"] for nb in response.json()["notebooks"]] == [ids[caller]]
    missing = notebook_clients["alice"].get("/notebooks", params={"document_id": "missing"})
    assert missing.json() == {"count": 0, "notebooks": []}


def test_notebook_list_owned_empty_and_public_notebooks_remain_visible(notebook_clients):
    empty = seed_notebook(empty=True)
    public = seed_notebook(content_class="user_public_contribution")
    response = observe(notebook_clients["bob"], "bob", "/notebooks")
    assert response.status_code == 200
    assert response.json()["count"] == 2
    assert {nb["notebook_id"] for nb in response.json()["notebooks"]} == {empty, public}
    assert all("blocks" not in nb for nb in response.json()["notebooks"])
    assert PRIVATE not in response.text
    assert notebook_clients["alice"].get("/notebooks").json() == {"count": 0, "notebooks": []}
