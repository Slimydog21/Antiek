"""Defensive notebook owner admission across ordinary and artifact routes."""

from __future__ import annotations

from dataclasses import replace

import duckdb
import pytest
from fastapi.testclient import TestClient

from interfaces.research.api.app import create_app
from interfaces.research.api.notebook_authority import (
    NotebookAuthority,
    admit_parent,
    visible_notebook_ids,
)
from substrate.auth import mint_magic_link_token
from substrate.auth.magic_link import mint_session_cookie as mint_legacy_cookie
from substrate.multi_user.auth import subject_owner_id

ALICE = "alice@example.test"
BOB = "bob@example.test"


@pytest.fixture
def notebook_clients(monkeypatch: pytest.MonkeyPatch, tmp_path):
    db = tmp_path / "notebooks.duckdb"
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", str(db))
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", str(tmp_path / "events"))
    monkeypatch.setenv("ANTIEK_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("ANTIEK_AUTH_SECRET", "synthetic-notebook-" + "x" * 48)
    monkeypatch.setenv("ANTIEK_OPERATOR_EMAIL", f"{ALICE},{BOB}")
    monkeypatch.setenv("ANTIEK_COOKIE_INSECURE", "1")
    monkeypatch.setenv("ANTIEK_EMAIL_PROVIDER", "mock")
    monkeypatch.delenv("ANTIEK_OPERATOR_TOKEN", raising=False)
    monkeypatch.delenv("ANTIEK_OPERATOR_SERVICE_TOKEN_CLIENT_ID", raising=False)
    from substrate.graph import ensure_initialized

    ensure_initialized(str(db))
    app = create_app(register_wrestling=False, register_providers=False)
    alice, bob = TestClient(app), TestClient(app)
    for client, email in ((alice, ALICE), (bob, BOB)):
        response = client.get(
            f"/auth/callback?token={mint_magic_link_token(email)}",
            follow_redirects=False,
        )
        assert response.status_code == 302, response.text
        assert client.get("/auth/me").json()["user_id"] == subject_owner_id("magic_link", email)
    return db, alice, bob


def _create(client: TestClient, title: str) -> str:
    response = client.post("/notebooks", json={"title": title})
    assert response.status_code == 201, response.text
    return response.json()["notebook_id"]


def _append(client: TestClient, notebook_id: str, text: str) -> str:
    response = client.post(
        f"/notebooks/{notebook_id}/blocks",
        json={"block_type": "prose", "content": {"text": text}},
    )
    assert response.status_code == 201, response.text
    return response.json()["blocks"][-1]["block_id"]


def test_verified_email_create_relogin_private_and_public_reads(notebook_clients):
    db, alice, bob = notebook_clients
    notebook_id = _create(alice, "Alice private")
    block_id = _append(alice, notebook_id, "Alice note")
    with duckdb.connect(str(db), read_only=True) as con:
        assert con.execute(
            "SELECT owner_user_id,content_class FROM notebooks WHERE notebook_id=?",
            [notebook_id],
        ).fetchone() == (subject_owner_id("magic_link", ALICE), "user_owned")
    assert bob.get(f"/notebooks/{notebook_id}").status_code == 404
    assert bob.get(f"/notebooks/{notebook_id}/content").status_code == 404
    assert bob.get(f"/api/notebooks/{notebook_id}/artifact.html").status_code == 404
    assert bob.get("/notebooks").json() == {"count": 0, "notebooks": []}
    assert bob.patch(
        f"/notebooks/{notebook_id}/blocks/{block_id}",
        json={"content": {"text": "other"}},
    ).status_code == 404
    assert bob.post(
        f"/notebooks/{notebook_id}/blocks/reorder",
        json={"ordered_block_ids": [block_id]},
    ).status_code == 404
    assert bob.post(f"/notebooks/{notebook_id}/promote-public?force=true").status_code == 404
    assert alice.get(f"/notebooks/{notebook_id}").status_code == 200
    assert alice.post("/auth/logout").status_code == 204
    assert alice.get(f"/notebooks/{notebook_id}").status_code == 401
    assert alice.get(
        f"/auth/callback?token={mint_magic_link_token(ALICE)}",
        follow_redirects=False,
    ).status_code == 302
    assert alice.get(f"/notebooks/{notebook_id}").status_code == 200
    assert alice.post(f"/notebooks/{notebook_id}/promote-public?force=true").status_code == 200
    assert bob.get(f"/notebooks/{notebook_id}").status_code == 200
    assert bob.get(f"/api/notebooks/{notebook_id}/artifact.html").status_code == 200
    assert bob.get(f"/api/notebooks/{notebook_id}/artifact?format=antiek").status_code == 404
    assert bob.delete(f"/notebooks/{notebook_id}/blocks/{block_id}").status_code == 404


def test_create_rejects_forged_owner_and_public_class(notebook_clients):
    _db, alice, _bob = notebook_clients
    assert alice.post(
        "/notebooks", json={"title": "forged", "owner_user_id": "other"},
    ).status_code == 422
    assert alice.post(
        "/notebooks", json={"title": "premature", "content_class": "user_public_contribution"},
    ).status_code == 422


def test_second_verified_account_owns_and_edits_its_private_notebook(notebook_clients):
    db, alice, bob = notebook_clients
    notebook_id = _create(bob, "Bob private")
    block_id = _append(bob, notebook_id, "Bob original")
    with duckdb.connect(str(db), read_only=True) as con:
        assert con.execute(
            "SELECT owner_user_id,content_class FROM notebooks WHERE notebook_id=?",
            [notebook_id],
        ).fetchone() == (subject_owner_id("magic_link", BOB), "user_owned")
    assert alice.get(f"/notebooks/{notebook_id}").status_code == 404
    changed = bob.patch(
        f"/notebooks/{notebook_id}/blocks/{block_id}",
        json={"content": {"text": "Bob revised"}},
    )
    assert changed.status_code == 200, changed.text
    assert bob.get(f"/notebooks/{notebook_id}").json()["blocks"][0]["content_json"] == {
        "text": "Bob revised",
    }
    assert alice.get(f"/notebooks/{notebook_id}/content").status_code == 404


def test_list_visibility_applies_before_limit_and_ties(notebook_clients):
    db, alice, bob = notebook_clients
    visible = _create(alice, "Visible")
    foreign = [_create(bob, f"Foreign {index}") for index in range(3)]
    with duckdb.connect(str(db)) as con:
        con.execute("UPDATE notebooks SET updated_at='2026-01-01' WHERE notebook_id=?", [visible])
        for notebook_id in foreign:
            con.execute(
                "UPDATE notebooks SET updated_at='2026-09-01' WHERE notebook_id=?",
                [notebook_id],
            )
    response = alice.get("/notebooks?limit=1")
    assert response.status_code == 200
    assert [item["notebook_id"] for item in response.json()["notebooks"]] == [visible]
    second = _create(alice, "Second visible")
    with duckdb.connect(str(db)) as con:
        con.execute(
            "UPDATE notebooks SET updated_at='2026-01-01' WHERE notebook_id IN (?,?)",
            [visible, second],
        )
    tied = alice.get("/notebooks?limit=2")
    assert [item["notebook_id"] for item in tied.json()["notebooks"]] == sorted(
        (visible, second),
    )


def test_foreign_signed_artifact_denied_before_key_creation(notebook_clients, monkeypatch):
    _db, alice, bob = notebook_clients
    notebook_id = _create(alice, "Owner export")
    _append(alice, notebook_id, "Owner text")
    import services.antiek_format.signature as signature

    calls: list[str] = []
    original = signature.ensure_keypair

    def record(user_id: str, *, db_path: str):
        calls.append(user_id)
        return original(user_id, db_path=db_path)

    monkeypatch.setattr(signature, "ensure_keypair", record)
    denied = bob.get(f"/api/notebooks/{notebook_id}/artifact?format=antiek")
    assert denied.status_code == 404
    assert calls == []
    accepted = alice.get(f"/api/notebooks/{notebook_id}/artifact?format=antiek")
    assert accepted.status_code == 200, accepted.text[:150]
    assert calls == [subject_owner_id("magic_link", ALICE)]


def test_denied_parent_does_not_hydrate_or_evaluate(notebook_clients, monkeypatch):
    _db, alice, bob = notebook_clients
    notebook_id = _create(alice, "Private source")
    import compounding.quality_gate as quality_gate
    import substrate.notebooks as notebooks

    def forbidden(*_args, **_kwargs):
        raise AssertionError("denied parent reached protected work")

    monkeypatch.setattr(notebooks, "get_notebook", forbidden)
    monkeypatch.setattr(notebooks, "gather_quality_gate_inputs", forbidden)
    monkeypatch.setattr(quality_gate, "evaluate_notebook_for_public", forbidden)
    assert bob.get(f"/notebooks/{notebook_id}").status_code == 404
    assert bob.put(
        f"/notebooks/{notebook_id}/content",
        json={"doc": {"type": "doc", "content": []}},
    ).status_code == 404
    assert bob.post(f"/notebooks/{notebook_id}/promote-public?force=true").status_code == 404


def test_paired_block_identity_duplicate_reorder_and_rollback(notebook_clients, monkeypatch):
    _db, alice, bob = notebook_clients
    own = _create(alice, "Own")
    other = _create(bob, "Other")
    first = _append(alice, own, "first")
    second = _append(alice, own, "second")
    foreign_block = _append(bob, other, "foreign")
    before = alice.get(f"/notebooks/{own}").json()["blocks"]
    assert alice.patch(
        f"/notebooks/{own}/blocks/{foreign_block}",
        json={"content": {"text": "wrong parent"}},
    ).status_code == 404
    assert alice.delete(f"/notebooks/{own}/blocks/{foreign_block}").status_code == 404
    assert alice.post(
        f"/notebooks/{own}/blocks/reorder",
        json={"ordered_block_ids": [first, second, second]},
    ).status_code == 422
    assert alice.get(f"/notebooks/{own}").json()["blocks"] == before

    import substrate.notebooks as notebooks

    real_delete = notebooks.delete_block

    def failed_delete(con, notebook_id, block_id):
        real_delete(con, notebook_id, block_id)
        raise RuntimeError("synthetic post-delete failure")

    monkeypatch.setattr(notebooks, "delete_block", failed_delete)
    with pytest.raises(RuntimeError, match="synthetic post-delete failure"):
        alice.delete(f"/notebooks/{own}/blocks/{first}")
    assert alice.get(f"/notebooks/{own}").json()["blocks"] == before
    monkeypatch.setattr(notebooks, "delete_block", real_delete)

    real_reorder = notebooks.reorder_blocks

    def failed_reorder(con, notebook_id, *, ordered_block_ids):
        real_reorder(con, notebook_id, ordered_block_ids=ordered_block_ids)
        raise RuntimeError("synthetic post-reorder failure")

    monkeypatch.setattr(notebooks, "reorder_blocks", failed_reorder)
    with pytest.raises(RuntimeError, match="synthetic post-reorder failure"):
        alice.post(
            f"/notebooks/{own}/blocks/reorder",
            json={"ordered_block_ids": [second, first]},
        )
    assert alice.get(f"/notebooks/{own}").json()["blocks"] == before


def test_unknown_notebook_class_denied_before_visibility():
    con = duckdb.connect(":memory:")
    try:
        con.execute(
            "CREATE TABLE notebooks (notebook_id TEXT,title TEXT,owner_user_id TEXT,"
            "content_class TEXT,document_id TEXT,investigation_id TEXT,updated_at TIMESTAMP)"
        )
        con.execute(
            "INSERT INTO notebooks VALUES "
            "('unknown','Unknown','owner-a','future_class',NULL,NULL,CURRENT_TIMESTAMP),"
            "('missing-class','Missing','owner-a',NULL,NULL,NULL,CURRENT_TIMESTAMP),"
            "('missing-owner','Missing owner',NULL,'user_owned',NULL,NULL,CURRENT_TIMESTAMP),"
            "('known','Known','owner-a','user_owned',NULL,NULL,CURRENT_TIMESTAMP)"
        )
        authority = NotebookAuthority("owner-a", True, False)
        assert admit_parent(con, "unknown", authority, mode="read") is None
        assert admit_parent(con, "unknown", authority, mode="write") is None
        assert admit_parent(con, "missing-class", authority, mode="read") is None
        assert admit_parent(con, "missing-owner", authority, mode="read") is None
        assert admit_parent(con, "missing-owner", authority, mode="write") is None
        assert visible_notebook_ids(
            con, authority, investigation_id=None, document_id=None, limit=10,
        ) == ["known"]
    finally:
        con.close()


def test_private_missing_owner_denied_and_cannot_sign(
    notebook_clients, monkeypatch,
):
    stored_owner = ""
    db, alice, bob = notebook_clients
    notebook_id = _create(alice, "Unbound private")
    with duckdb.connect(str(db)) as con:
        con.execute(
            "UPDATE notebooks SET owner_user_id=? WHERE notebook_id=?",
            [stored_owner, notebook_id],
        )
    import services.antiek_format.signature as signature

    def forbidden(*_args, **_kwargs):
        raise AssertionError("unbound private row reached key creation")

    monkeypatch.setattr(signature, "ensure_keypair", forbidden)
    for client in (alice, bob):
        assert client.get(f"/notebooks/{notebook_id}").status_code == 404
        assert client.get(f"/notebooks/{notebook_id}/content").status_code == 404
        assert client.post(
            f"/notebooks/{notebook_id}/blocks",
            json={"block_type": "prose", "content": {"text": "denied"}},
        ).status_code == 404
        assert client.get(
            f"/api/notebooks/{notebook_id}/artifact?format=antiek",
        ).status_code == 404
    with duckdb.connect(str(db), read_only=True) as con:
        assert con.execute(
            "SELECT owner_user_id FROM notebooks WHERE notebook_id=?",
            [notebook_id],
        ).fetchone() == (stored_owner,)
        assert con.execute(
            "SELECT count(*) FROM notebook_blocks WHERE notebook_id=?",
            [notebook_id],
        ).fetchone() == (0,)


def test_historical_sentinel_requires_sole_verified_operator(notebook_clients, monkeypatch):
    db, alice, bob = notebook_clients
    with duckdb.connect(str(db)) as con:
        con.execute(
            "INSERT INTO notebooks (notebook_id,title) VALUES ('historical','Historical')"
        )
    assert alice.get("/notebooks/historical").status_code == 404
    assert bob.get("/notebooks/historical").status_code == 404
    monkeypatch.setenv("ANTIEK_OPERATOR_EMAIL", ALICE)
    assert alice.get("/notebooks/historical").status_code == 200
    legacy = TestClient(alice.app)
    legacy.cookies.set(
        "ANTIEK_SESSION", mint_legacy_cookie(user_id="__operator__", email=ALICE),
    )
    assert legacy.get("/notebooks/historical").status_code == 200
    wrong_legacy = TestClient(alice.app)
    wrong_legacy.cookies.set(
        "ANTIEK_SESSION",
        mint_legacy_cookie(user_id=subject_owner_id("magic_link", BOB), email=ALICE),
    )
    assert wrong_legacy.get("/notebooks/historical").status_code == 404


def test_legacy_non_sentinel_reads_public_but_not_private(notebook_clients):
    _db, alice, _bob = notebook_clients
    public = _create(alice, "Legacy public")
    private = _create(alice, "Legacy private")
    assert alice.post(f"/notebooks/{public}/promote-public?force=true").status_code == 200
    legacy = TestClient(alice.app)
    legacy.cookies.set(
        "ANTIEK_SESSION",
        mint_legacy_cookie(user_id="legacy-reader", email=BOB),
    )
    assert legacy.get(f"/notebooks/{public}").status_code == 200
    assert legacy.get(f"/notebooks/{private}").status_code == 404
    assert legacy.get(f"/api/notebooks/{public}/artifact.html").status_code == 200
    assert legacy.get(f"/api/notebooks/{private}/artifact.html").status_code == 404


def test_revoked_subject_cookie_cannot_reopen_private_or_historical(
    notebook_clients, monkeypatch,
):
    db, alice, _bob = notebook_clients
    private = _create(alice, "Before revocation")
    with duckdb.connect(str(db)) as con:
        con.execute("INSERT INTO notebooks (notebook_id,title) VALUES ('historical','Historical')")
        con.execute("DELETE FROM auth_subjects WHERE subject=?", [ALICE])
    monkeypatch.setenv("ANTIEK_OPERATOR_EMAIL", ALICE)
    assert alice.get(f"/notebooks/{private}").status_code == 404
    assert alice.get("/notebooks/historical").status_code == 404


@pytest.mark.parametrize("mismatch", ("owner", "method", "email"))
def test_verified_principal_must_match_middleware_identity(
    notebook_clients, monkeypatch, mismatch,
):
    _db, alice, _bob = notebook_clients
    notebook_id = _create(alice, "Exact principal")
    from interfaces.research.api import notebook_authority as notebook_policy

    real_resolve = notebook_policy.resolve_authenticated_principal

    def disagree(request):
        principal = real_resolve(request)
        if mismatch == "owner":
            return replace(
                principal, owner_user_id=subject_owner_id("magic_link", BOB),
            )
        if mismatch == "email":
            return replace(principal, email=BOB)
        return replace(principal, auth_method="bearer_token")

    monkeypatch.setattr(notebook_policy, "resolve_authenticated_principal", disagree)
    assert alice.get(f"/notebooks/{notebook_id}").status_code == 401


def test_machine_readers_see_only_public_and_local_default_is_not_auth(
    notebook_clients, monkeypatch,
):
    _db, alice, _bob = notebook_clients
    public = _create(alice, "Shared")
    private = _create(alice, "Private")
    assert alice.post(f"/notebooks/{public}/promote-public?force=true").status_code == 200
    machine = TestClient(alice.app)
    monkeypatch.setenv("ANTIEK_OPERATOR_TOKEN", "synthetic-notebook-token")
    headers = {"Authorization": "Bearer synthetic-notebook-token"}
    assert machine.get(f"/notebooks/{public}", headers=headers).status_code == 200
    assert machine.get(f"/notebooks/{private}", headers=headers).status_code == 404
    assert machine.post("/notebooks", json={"title": "Machine"}, headers=headers).status_code == 403
    monkeypatch.setenv("ANTIEK_OPERATOR_SERVICE_TOKEN_CLIENT_ID", "synthetic-service")
    monkeypatch.setenv("CF_ACCESS_CLIENT_SECRET", "synthetic-service-secret")
    service_headers = {
        "Cf-Access-Client-Id": "synthetic-service",
        "Cf-Access-Client-Secret": "synthetic-service-secret",
    }
    assert machine.get(f"/notebooks/{public}", headers=service_headers).status_code == 200
    assert machine.get(f"/notebooks/{private}", headers=service_headers).status_code == 404
    monkeypatch.delenv("ANTIEK_OPERATOR_TOKEN")
    monkeypatch.delenv("ANTIEK_OPERATOR_EMAIL")
    monkeypatch.delenv("ANTIEK_OPERATOR_SERVICE_TOKEN_CLIENT_ID")
    assert machine.get(f"/notebooks/{public}").status_code == 401


def test_public_blank_owner_remains_html_readable_but_cannot_sign(notebook_clients):
    db, alice, bob = notebook_clients
    notebook_id = _create(alice, "Public with lost owner")
    assert alice.post(f"/notebooks/{notebook_id}/promote-public?force=true").status_code == 200
    with duckdb.connect(str(db)) as con:
        con.execute(
            "UPDATE notebooks SET owner_user_id='' WHERE notebook_id=?", [notebook_id],
        )
    assert bob.get(f"/api/notebooks/{notebook_id}/artifact.html").status_code == 200
    assert alice.get(f"/api/notebooks/{notebook_id}/artifact?format=antiek").status_code == 404


def test_artifact_parent_and_blocks_share_a_read_snapshot(notebook_clients, monkeypatch):
    db, alice, _bob = notebook_clients
    notebook_id = _create(alice, "Before snapshot")
    appended = alice.post(
        f"/notebooks/{notebook_id}/blocks",
        json={
            "block_type": "prose",
            "content": {
                "type": "paragraph",
                "content": [{"type": "text", "text": "Before block"}],
            },
        },
    )
    assert appended.status_code == 201
    block_id = appended.json()["blocks"][0]["block_id"]
    from interfaces.research.api import notebook_artifact as artifact
    from runtime.db_lock import connect_write

    real_admit = artifact.admit_parent
    with connect_write(str(db), purpose="test:interleave_notebook_snapshot") as writer:

        def change_after_parent(con, selected_id, authority, *, mode):
            parent = real_admit(con, selected_id, authority, mode=mode)
            writer.execute(
                "UPDATE notebooks SET title='After snapshot' WHERE notebook_id=?",
                [notebook_id],
            )
            writer.execute(
                "UPDATE notebook_blocks SET content_json=? WHERE block_id=?",
                ['{"type":"paragraph","content":[{"type":"text","text":"After block"}]}', block_id],
            )
            return parent

        monkeypatch.setattr(artifact, "admit_parent", change_after_parent)
        source = artifact.resolve_notebook_export(
            notebook_id,
            authority=NotebookAuthority(subject_owner_id("magic_link", ALICE), True, False),
            mode="read",
            db_path=str(db),
        )
    assert source is not None
    assert source.title == "Before snapshot"
    assert "Before block" in str(source.content_tiptap)
    assert "After block" not in str(source.content_tiptap)


def test_signed_artifact_uses_admitted_snapshot_after_read_close(
    notebook_clients, monkeypatch,
):
    db, alice, _bob = notebook_clients
    notebook_id = _create(alice, "Signed before")
    from interfaces.research.api import notebook_artifact as artifact
    from services.antiek_format import read_antiek

    real_resolve = artifact.resolve_notebook_export

    def change_after_snapshot(*args, **kwargs):
        source = real_resolve(*args, **kwargs)
        assert source is not None
        with duckdb.connect(str(db)) as con:
            con.execute(
                "UPDATE notebooks SET title='Signed after',owner_user_id=? WHERE notebook_id=?",
                [subject_owner_id("magic_link", BOB), notebook_id],
            )
        return source

    monkeypatch.setattr(artifact, "resolve_notebook_export", change_after_snapshot)
    response = alice.get(f"/api/notebooks/{notebook_id}/artifact?format=antiek")
    assert response.status_code == 200
    signed = read_antiek(response.content)
    assert signed.signature_valid is True
    assert signed.title == "Signed before"
    assert signed.user_id == subject_owner_id("magic_link", ALICE)
