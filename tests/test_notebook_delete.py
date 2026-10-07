"""Owner deletion removes the notebook and blocks without deleting source data."""

import pytest
from fastapi.testclient import TestClient

from interfaces.research.api.app import create_app
from interfaces.research.api.auth import reset_auth_throttles
from runtime.db_lock import LockedConnection, connect_write
from substrate.auth import MockEmailProvider
from substrate.graph import default_db_path
from substrate.notebooks import (
    NotebookDeleteConflict,
    NotebookReadWithheld,
    append_block,
    create_notebook,
    delete_notebook,
    get_notebook,
)


def notebook_rows(con):
    return {
        table: con.execute(f"SELECT * FROM {table} ORDER BY 1").fetchall()
        for table in ("notebooks", "notebook_blocks")
    }


@pytest.fixture
def notebook_accounts(monkeypatch, tmp_path):
    monkeypatch.setenv("ANTIEK_AUTH_SECRET", "notebook-delete-private-test-" + "x" * 48)
    monkeypatch.setenv("ANTIEK_OPERATOR_EMAIL", "operator@example.test")
    monkeypatch.delenv("ANTIEK_LEGACY_OPERATOR_EMAIL", raising=False)
    monkeypatch.setenv("ANTIEK_OPEN_SIGNUP", "1")
    monkeypatch.setenv("ANTIEK_COOKIE_INSECURE", "1")
    monkeypatch.setenv("ANTIEK_ACCOUNT_STORE", str(tmp_path / "accounts.json"))
    monkeypatch.setenv("ANTIEK_PASSKEY_STORE", str(tmp_path / "passkeys.json"))
    monkeypatch.delenv("ANTIEK_OPERATOR_TOKEN", raising=False)
    monkeypatch.delenv("ANTIEK_DEV_LOGIN_TOKEN", raising=False)
    sender = MockEmailProvider(log_to_stdout=False)
    monkeypatch.setattr("interfaces.research.api.auth.get_email_provider", lambda: sender)
    reset_auth_throttles()
    app = create_app(register_wrestling=False, register_providers=False, cors_origins=[])
    clients = {"anonymous": TestClient(app, raise_server_exceptions=False)}
    for name in ("alice", "bob"):
        client = TestClient(app, raise_server_exceptions=False)
        clients[name] = client
        requested = client.post("/auth/request", json={"email": f"{name}@example.test"})
        assert requested.status_code == 200
        assert sender.sent[-1].email.to == f"{name}@example.test"
        code = sender.sent[-1].email.subject.rsplit("·", 1)[-1].strip()
        claimed = client.post("/auth/claim", json={
            **{key: requested.json()[key] for key in ("attempt_id", "claim_secret")},
            "code": code,
        })
        assert claimed.status_code == 200
        identity = client.get("/auth/whoami")
        assert identity.status_code == 200
        assert identity.json()["is_operator"] is False
    yield clients
    for client in clients.values():
        client.close()
    reset_auth_throttles()


def test_store_deletes_notebook_with_blocks():
    with connect_write(default_db_path(), purpose="test/notebook-delete") as con:
        notebook_id = create_notebook(con, title="Delete me", owner_user_id="owner")
        append_block(con, notebook_id, block_type="prose", content={"text": "Saved work"})
        assert delete_notebook(con, notebook_id, owner_user_id="owner") is True
        assert get_notebook(con, notebook_id) is None
        assert con.execute(
            "SELECT COUNT(*) FROM notebook_blocks WHERE notebook_id = ?", [notebook_id],
        ).fetchone() == (0,)


@pytest.mark.parametrize("caller", ["foreign", "", "__operator__"])
def test_store_refuses_other_owner_without_changes(caller):
    with connect_write(default_db_path(), purpose="test/notebook-delete") as con:
        notebook_id = create_notebook(con, title="Private", owner_user_id="owner")
        append_block(con, notebook_id, block_type="prose", content={"text": "Retain me"})
        before = notebook_rows(con)
        with pytest.raises(NotebookReadWithheld):
            delete_notebook(con, notebook_id, owner_user_id=caller)
        assert notebook_rows(con) == before


@pytest.mark.parametrize("reference", ["notebook", "block"])
def test_store_refuses_incoming_reference_without_changes(reference):
    with connect_write(default_db_path(), purpose="test/notebook-delete") as con:
        notebook_id = create_notebook(con, title="Source", owner_user_id="owner")
        block_id = append_block(con, notebook_id, block_type="prose", content={"text": "Source"})
        other_id = create_notebook(con, title="Referencing", owner_user_id="other")
        append_block(con, other_id, block_type="note", content={},
                     ref_id=notebook_id if reference == "notebook" else block_id)
        before = notebook_rows(con)
        with pytest.raises(NotebookDeleteConflict):
            delete_notebook(con, notebook_id, owner_user_id="owner")
        assert notebook_rows(con) == before


def test_store_refuses_nested_transaction_without_changes():
    with connect_write(default_db_path(), purpose="test/notebook-delete") as con:
        notebook_id = create_notebook(con, title="Keep me", owner_user_id="owner")
        append_block(con, notebook_id, block_type="prose", content={"text": "Keep me"})
        before = notebook_rows(con)
        with con.transaction(), pytest.raises(ValueError, match="standalone writer lease"):
            delete_notebook(con, notebook_id, owner_user_id="owner")
        assert notebook_rows(con) == before


def test_ordinary_owner_create_edit_and_delete_preserves_source_objects(notebook_accounts):
    client = notebook_accounts["alice"]
    owner = client.get("/auth/me").json()["user_id"]
    with connect_write(default_db_path(), purpose="test/notebook-delete-sources") as con:
        con.execute(
            "INSERT INTO documents (document_id, title, source_tier, document_type, owner_user_id) "
            "VALUES ('doc-source', 'Shared source', 1, 'paper', ?)", [owner],
        )
        for node_id in ("node-source", "node-target"):
            con.execute(
                "INSERT INTO nodes (node_id, canonical_label, node_type, graph_scope) "
                "VALUES (?, ?, 'entity', 'depth')", [node_id, node_id],
            )
        con.execute(
            "INSERT INTO edges (edge_id, source_node_id, target_node_id, relation, "
            "source_document_id, source_tier, extraction_confidence, graph_scope) "
            "VALUES ('edge-source', 'node-source', 'node-target', 'supports', "
            "'doc-source', 1, 1, 'depth')",
        )
        retained = {table: con.execute(f"SELECT * FROM {table} ORDER BY 1").fetchall()
                    for table in ("documents", "nodes", "edges")}
    created = client.post("/notebooks", json={"title": "antiek-e2e delete", "document_id": "doc-source"})
    assert created.status_code == 201
    notebook_id = created.json()["notebook_id"]
    path = f"/notebooks/{notebook_id}"
    first = client.post(path + "/blocks", json={"block_type": "prose", "content": {"text": "Initial"}})
    assert first.status_code == 201
    block_id = first.json()["blocks"][0]["block_id"]
    edited = client.patch(path + f"/blocks/{block_id}", json={"content": {"text": "Edited"}})
    assert edited.status_code == 200
    assert edited.json()["blocks"][0]["content_json"] == {"text": "Edited"}
    linked = client.post(path + "/blocks", json={
        "block_type": "region_embed", "ref_id": "doc-source", "content": {},
    })
    assert linked.status_code == 201
    claim = client.post(path + "/blocks", json={
        "block_type": "claim_card", "ref_id": "node-source", "content": {},
    })
    assert claim.status_code == 201
    block_deleted = client.delete(path + f"/blocks/{block_id}")
    assert block_deleted.status_code == 200
    assert [block["block_index"] for block in block_deleted.json()["blocks"]] == [0, 1]
    assert client.get(path).json()["blocks"] == block_deleted.json()["blocks"]
    with connect_write(default_db_path(), purpose="test/notebook-delete-observe") as con:
        assert get_notebook(con, notebook_id).owner_user_id == owner
        other_id = create_notebook(con, title="Unrelated", owner_user_id="other-owner")
        append_block(con, other_id, block_type="note", content={"text": "Untouched"}, ref_id="doc-source")
        other_before = get_notebook(con, other_id)
    deleted = client.delete(path)
    assert deleted.status_code == 204
    assert deleted.content == b""
    assert client.get(path).status_code == 404
    listing = client.get("/notebooks")
    assert listing.status_code == 200
    assert notebook_id not in {item["notebook_id"] for item in listing.json()["notebooks"]}
    assert client.delete(path).status_code == 404
    with connect_write(default_db_path(), purpose="test/notebook-delete-observe") as con:
        assert con.execute("SELECT * FROM notebook_blocks WHERE notebook_id = ?", [notebook_id]).fetchall() == []
        assert get_notebook(con, other_id) == other_before
        assert {table: con.execute(f"SELECT * FROM {table} ORDER BY 1").fetchall()
                for table in retained} == retained


@pytest.mark.parametrize("caller,status", [("bob", 403), ("anonymous", 401)])
@pytest.mark.parametrize("content_class", ["user_owned", "user_public_contribution"])
def test_http_delete_refuses_foreign_and_unauthenticated_without_changes(notebook_accounts, caller, status, content_class):
    created = notebook_accounts["alice"].post("/notebooks", json={
        "title": "Alice private", "content_class": content_class,
    })
    assert created.status_code == 201
    notebook_id = created.json()["notebook_id"]
    with connect_write(default_db_path(), purpose="test/notebook-delete-seed") as con:
        append_block(con, notebook_id, block_type="prose", content={"text": "Private retained content"})
        before = notebook_rows(con)
    response = notebook_accounts[caller].delete(f"/notebooks/{notebook_id}", params={"owner_user_id": "alice"})
    assert response.status_code == status
    assert "Private retained content" not in response.text
    with connect_write(default_db_path(), purpose="test/notebook-delete-observe") as con:
        assert notebook_rows(con) == before


def test_http_incoming_reference_refused_without_disclosing_foreign_notebook(notebook_accounts):
    client = notebook_accounts["alice"]
    notebook_id = client.post("/notebooks", json={"title": "Source"}).json()["notebook_id"]
    with connect_write(default_db_path(), purpose="test/notebook-delete-seed") as con:
        other_id = create_notebook(con, title="Foreign private title", owner_user_id="other")
        append_block(con, other_id, block_type="note", content={}, ref_id=notebook_id)
        before = notebook_rows(con)
    response = client.delete(f"/notebooks/{notebook_id}")
    assert response.status_code == 409
    assert response.json() == {"detail": "notebook still has incoming references"}
    assert other_id not in response.text
    assert "Foreign private title" not in response.text
    with connect_write(default_db_path(), purpose="test/notebook-delete-observe") as con:
        assert notebook_rows(con) == before


@pytest.mark.parametrize("method,suffix", [("PATCH", ""), ("POST", ""), ("DELETE", "/promote-public")])
def test_ordinary_account_detail_admission_does_not_broaden_other_methods(notebook_accounts, method, suffix):
    client = notebook_accounts["alice"]
    notebook_id = client.post("/notebooks", json={"title": "Keep private"}).json()["notebook_id"]
    with connect_write(default_db_path(), purpose="test/notebook-delete-observe") as con:
        before = notebook_rows(con)
    assert client.request(method, f"/notebooks/{notebook_id}" + suffix).status_code == 403
    with connect_write(default_db_path(), purpose="test/notebook-delete-observe") as con:
        assert notebook_rows(con) == before


@pytest.mark.parametrize("failing_delete,expected_blocks", [("notebook_blocks", 1), ("notebooks", 0)])
def test_delete_failure_is_not_success_and_owner_retry_finishes(notebook_accounts, monkeypatch, failing_delete, expected_blocks):
    client = notebook_accounts["alice"]
    notebook_id = client.post("/notebooks", json={"title": "Delete failure"}).json()["notebook_id"]
    with connect_write(default_db_path(), purpose="test/notebook-delete-seed") as con:
        append_block(con, notebook_id, block_type="prose", content={"text": "Stored"})
    real_execute = LockedConnection.execute

    def failing_execute(self, sql, parameters=None):
        if sql == f"DELETE FROM {failing_delete} WHERE notebook_id = ?":
            raise RuntimeError("controlled delete failure")
        return real_execute(self, sql, parameters)

    with monkeypatch.context() as patch:
        patch.setattr(LockedConnection, "execute", failing_execute)
        assert client.delete(f"/notebooks/{notebook_id}").status_code == 500
    retained = client.get(f"/notebooks/{notebook_id}")
    assert retained.status_code == 200
    assert len(retained.json()["blocks"]) == expected_blocks
    assert client.delete(f"/notebooks/{notebook_id}").status_code == 204
    assert client.get(f"/notebooks/{notebook_id}").status_code == 404
