from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from runtime.db_lock import connect_write
from substrate.graph.schema import init_database
from substrate.notebooks import (
    NotebookMutationConflict,
    append_block,
    append_document_block,
    create_notebook,
    get_notebook,
    list_notebooks,
    replace_document,
)
from substrate.notebooks.authority import NotebookAccountAuthority

DOC_A = {
    "type": "doc",
    "content": [{"type": "paragraph", "content": [{"type": "text", "text": "Alice v1"}]}],
}
DOC_B = {
    "type": "doc",
    "content": [{"type": "paragraph", "content": [{"type": "text", "text": "Bob v1"}]}],
}
DOC_A2 = {
    "type": "doc",
    "content": [{"type": "paragraph", "content": [{"type": "text", "text": "Alice v2"}]}],
}


@pytest.fixture
def db(tmp_path):
    con = connect_write(str(tmp_path / "notebook-authority.duckdb"), purpose="test:notebook-authority")
    init_database(con)
    yield con
    con.close()


def test_same_display_id_isolated_for_create_read_blocks_and_list(db):
    alice = NotebookAccountAuthority("alice")
    bob = NotebookAccountAuthority("bob")
    alice_book = alice.notebook("shared")
    bob_book = bob.notebook("shared")

    create_notebook(db, alice_book, title="Alice private")
    create_notebook(db, bob_book, title="Bob private")
    append_block(db, alice_book, block_type="prose", content=DOC_A["content"][0])
    append_block(db, bob_book, block_type="prose", content=DOC_B["content"][0])

    assert get_notebook(db, alice_book).title == "Alice private"
    assert get_notebook(db, bob_book).title == "Bob private"
    assert get_notebook(db, alice_book).blocks[0].content_json != get_notebook(db, bob_book).blocks[0].content_json
    assert [book.title for book in list_notebooks(db, alice)] == ["Alice private"]
    assert [book.title for book in list_notebooks(db, bob)] == ["Bob private"]


def test_conditional_replace_rejects_stale_writer_without_changing_document(db):
    alice_book = NotebookAccountAuthority("alice").notebook("race")
    create_notebook(db, alice_book, title="Race")

    first = replace_document(
        db,
        alice_book,
        schema_version=1,
        base_revision=0,
        mutation_key="writer-a",
        doc=DOC_A,
    )
    assert first.revision == 1

    with pytest.raises(NotebookMutationConflict) as caught:
        replace_document(
            db,
            alice_book,
            schema_version=1,
            base_revision=0,
            mutation_key="writer-b",
            doc=DOC_A2,
        )
    assert caught.value.code == "stale_revision"
    assert caught.value.revision == 1

    stored = get_notebook(db, alice_book)
    assert stored is not None
    assert stored.revision == first.revision
    assert stored.content_sha256 == first.content_sha256
    assert stored.blocks[0].content_json == DOC_A["content"][0]


def test_exact_mutation_replay_is_idempotent_and_key_reuse_with_new_bytes_conflicts(db):
    book = NotebookAccountAuthority("alice").notebook("replay")
    create_notebook(db, book, title="Replay")

    first = replace_document(
        db,
        book,
        schema_version=1,
        base_revision=0,
        mutation_key="same-key",
        doc=DOC_A,
    )
    replay = replace_document(
        db,
        book,
        schema_version=1,
        base_revision=0,
        mutation_key="same-key",
        doc=DOC_A,
    )
    assert replay.replayed is True
    assert (replay.revision, replay.content_sha256) == (first.revision, first.content_sha256)

    with pytest.raises(NotebookMutationConflict) as caught:
        replace_document(
            db,
            book,
            schema_version=1,
            base_revision=first.revision,
            mutation_key="same-key",
            doc=DOC_A2,
        )
    assert caught.value.code == "mutation_key_reused"
    assert get_notebook(db, book).revision == first.revision


def test_same_mutation_key_and_display_id_do_not_collide_across_accounts(db):
    alice = NotebookAccountAuthority("alice").notebook("shared")
    bob = NotebookAccountAuthority("bob").notebook("shared")
    create_notebook(db, alice, title="Alice")
    create_notebook(db, bob, title="Bob")

    alice_receipt = replace_document(
        db, alice, schema_version=1, base_revision=0, mutation_key="save-1", doc=DOC_A
    )
    bob_receipt = replace_document(
        db, bob, schema_version=1, base_revision=0, mutation_key="save-1", doc=DOC_B
    )

    assert alice_receipt.content_sha256 != bob_receipt.content_sha256
    assert get_notebook(db, alice).blocks[0].content_json == DOC_A["content"][0]
    assert get_notebook(db, bob).blocks[0].content_json == DOC_B["content"][0]


def test_conditional_block_append_is_atomic_idempotent_and_account_qualified(db):
    alice = NotebookAccountAuthority("alice").notebook("shared")
    bob = NotebookAccountAuthority("bob").notebook("shared")
    create_notebook(db, alice, title="Alice")
    create_notebook(db, bob, title="Bob")
    block = {"type": "noteBlock", "attrs": {"note_id": None, "text": "AI note"}}
    first = append_document_block(
        db, alice, schema_version=1, base_revision=0, mutation_key="append-1", block=block
    )
    replay = append_document_block(
        db, alice, schema_version=1, base_revision=0, mutation_key="append-1", block=block
    )
    assert first.revision == 1
    assert replay.replayed is True
    assert len(get_notebook(db, alice).blocks) == 1
    assert get_notebook(db, alice).blocks[0].block_type == "note"
    assert get_notebook(db, alice).blocks[0].content_json == block
    assert get_notebook(db, bob).blocks == []
    with pytest.raises(NotebookMutationConflict):
        append_document_block(
            db, alice, schema_version=1, base_revision=0, mutation_key="append-2", block=block
        )


def test_authenticated_http_same_display_id_and_stale_put_are_isolated(tmp_path, monkeypatch):
    from interfaces.research.api.app import create_app
    from substrate.auth import mint_magic_link_token

    database = str(tmp_path / "http.duckdb")
    monkeypatch.setenv("ANTIEK_DB_PATH", database)
    monkeypatch.setenv("ANTIEK_AUTH_SECRET", "notebook-http-" + "x" * 48)
    monkeypatch.setenv("ANTIEK_COOKIE_INSECURE", "1")
    monkeypatch.setenv(
        "ANTIEK_OPERATOR_EMAIL", "alice@example.test,bob@example.test"
    )
    app = create_app(register_wrestling=False, register_providers=False)
    clients = {
        email: TestClient(app) for email in ("alice@example.test", "bob@example.test")
    }
    for email, client in clients.items():
        response = client.get(
            f"/auth/callback?token={mint_magic_link_token(email)}",
            follow_redirects=False,
        )
        assert response.status_code == 302

    for label, email in (("Alice", "alice@example.test"), ("Bob", "bob@example.test")):
        created = clients[email].post(
            "/notebooks", json={"notebook_id": "shared", "title": label}
        )
        assert created.status_code == 201, created.text
    alice_only = clients["alice@example.test"].post(
        "/notebooks", json={"notebook_id": "alice-only", "title": "Alice only"}
    )
    assert alice_only.status_code == 201

    alice = clients["alice@example.test"]
    bob = clients["bob@example.test"]
    assert alice.get("/notebooks/shared").json()["title"] == "Alice"
    assert bob.get("/notebooks/shared").json()["title"] == "Bob"
    assert {row["title"] for row in alice.get("/notebooks").json()["notebooks"]} == {
        "Alice",
        "Alice only",
    }
    assert [row["title"] for row in bob.get("/notebooks").json()["notebooks"]] == ["Bob"]

    first = alice.put(
        "/notebooks/shared/content",
        json={"schema_version": 1, "base_revision": 0, "mutation_key": "a1", "doc": DOC_A},
    )
    assert first.status_code == 200, first.text
    stale = alice.put(
        "/notebooks/shared/content",
        json={"schema_version": 1, "base_revision": 0, "mutation_key": "a2", "doc": DOC_A2},
    )
    assert stale.status_code == 409
    assert stale.json()["detail"]["code"] == "stale_revision"
    assert alice.get("/notebooks/shared/content").json()["doc"] == DOC_A
    assert bob.get("/notebooks/shared/content").json()["doc"] == {"type": "doc", "content": []}
    alice_content = alice.get("/notebooks/shared/content").json()
    bob_content = bob.get("/notebooks/shared/content").json()
    assert len(alice_content["account_scope"]) == 64
    assert len(alice_content["recovery_scope"]) == 64
    assert alice_content["recovery_scope"] != bob_content["recovery_scope"]
    append = alice.post(
        "/notebooks/shared/content/append",
        json={
            "schema_version": 1,
            "account_scope": alice_content["account_scope"],
            "base_revision": 1,
            "mutation_key": "ai-append-1",
            "block": {"type": "noteBlock", "attrs": {"note_id": None, "text": "Alice AI"}},
        },
    )
    assert append.status_code == 200, append.text
    crossed = bob.post(
        "/notebooks/shared/content/append",
        json={
            "schema_version": 1,
            "account_scope": alice_content["account_scope"],
            "base_revision": 0,
            "mutation_key": "cross-account",
            "block": {"type": "noteBlock", "attrs": {"note_id": None, "text": "leak"}},
        },
    )
    assert crossed.status_code == 409
    assert crossed.json()["detail"]["code"] == "notebook_authority_changed"
    assert bob.get("/notebooks/shared/content").json()["doc"] == {"type": "doc", "content": []}
    foreign = bob.get("/notebooks/alice-only")
    missing = bob.get("/notebooks/never-created")
    assert (foreign.status_code, foreign.json()) == (missing.status_code, missing.json())
    assert all(
        response.headers.get("cache-control") == "no-store"
        for response in (
            alice.get("/notebooks/shared"),
            alice.get("/notebooks/shared/content"),
            stale,
        )
    )

    from substrate.graph import default_db_path

    with connect_write(default_db_path(), purpose="test:corrupt-notebook") as con:
        con.execute(
            "UPDATE notebooks SET owner_user_id = 'mallory' WHERE title = 'Alice only'"
        )
    corrupt = alice.get("/notebooks/alice-only")
    assert corrupt.status_code == 503
    assert corrupt.headers["cache-control"] == "no-store"


def test_legacy_rows_migrate_to_explicit_owner_partition_idempotently(tmp_path):
    import duckdb

    from substrate.notebooks.migration import migrate_notebook_authority_schema

    con = duckdb.connect(str(tmp_path / "legacy.duckdb"))
    con.execute(
        "CREATE TABLE notebooks (notebook_id TEXT PRIMARY KEY, title TEXT NOT NULL, "
        "investigation_id TEXT, document_id TEXT, owner_user_id TEXT NOT NULL, "
        "content_class TEXT NOT NULL, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, "
        "updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, metadata TEXT)"
    )
    con.execute(
        "CREATE TABLE notebook_blocks (block_id TEXT PRIMARY KEY, notebook_id TEXT NOT NULL, "
        "block_index INTEGER NOT NULL, block_type TEXT NOT NULL, ref_id TEXT, "
        "content_json TEXT NOT NULL, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)"
    )
    con.execute(
        "INSERT INTO notebooks (notebook_id,title,owner_user_id,content_class,metadata) "
        "VALUES ('legacy','Private legacy','alice','user_owned','{}')"
    )
    con.execute(
        "INSERT INTO notebooks (notebook_id,title,owner_user_id,content_class,metadata) "
        "VALUES ('operator-legacy','Operator legacy','__operator__','user_owned','{}')"
    )
    con.execute(
        "INSERT INTO notebook_blocks (block_id,notebook_id,block_index,block_type,content_json) "
        "VALUES ('b1','legacy',0,'prose',?)",
        [json.dumps(DOC_A["content"][0])],
    )

    migrate_notebook_authority_schema(con)
    migrate_notebook_authority_schema(con)

    alice = NotebookAccountAuthority("alice").notebook("legacy")
    bob = NotebookAccountAuthority("bob").notebook("legacy")
    from substrate.notebooks.authority import operator_notebook_authority

    assert get_notebook(con, alice).title == "Private legacy"
    assert get_notebook(con, alice).revision == 1
    assert get_notebook(con, bob) is None
    assert get_notebook(con, operator_notebook_authority("operator-legacy")).title == "Operator legacy"
    assert get_notebook(con, NotebookAccountAuthority("alice").notebook("operator-legacy")) is None
    con.close()
