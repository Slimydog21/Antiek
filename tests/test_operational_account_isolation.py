"""Private local account regressions. No real mailbox or production session."""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from interfaces.research.api.account_memory_identity import derive_owner_from_verified_email
from interfaces.research.api.app import create_app
from interfaces.research.api.auth import reset_auth_throttles
from substrate.auth import MockEmailProvider, mint_session_cookie

OPERATOR = "operator@example.test"
ALICE = "alice@example.test"
BOB = "bob@example.test"


@pytest.fixture
def account_api(monkeypatch, tmp_path):
    monkeypatch.setenv("ANTIEK_AUTH_SECRET", "local-account-regression-" + "x" * 48)
    monkeypatch.setenv("ANTIEK_OPERATOR_EMAIL", OPERATOR)
    monkeypatch.setenv("ANTIEK_LEGACY_OPERATOR_EMAIL", OPERATOR)
    monkeypatch.setenv("ANTIEK_OPEN_SIGNUP", "1")
    monkeypatch.setenv("ANTIEK_COOKIE_INSECURE", "1")
    monkeypatch.setenv("ANTIEK_ACCOUNT_STORE", str(tmp_path / "accounts.json"))
    monkeypatch.setenv("ANTIEK_PASSKEY_STORE", str(tmp_path / "passkeys.json"))
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", str(tmp_path / "graph.duckdb"))
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", str(tmp_path / "events"))
    monkeypatch.setenv("ANTIEK_USER_MODELS_PATH", str(tmp_path / "models.json"))
    monkeypatch.setenv("ANTIEK_BYOK_ARTIFACT", str(tmp_path / "credentials.enc"))
    monkeypatch.setenv("ANTIEK_BYOK_KEY_FILE", str(tmp_path / "master.key"))
    for name in (
        "ANTIEK_OPERATOR_TOKEN",
        "ANTIEK_DEV_LOGIN_TOKEN",
        "ANTIEK_OPERATOR_SERVICE_TOKEN_CLIENT_ID",
        "CF_ACCESS_CLIENT_SECRET",
    ):
        monkeypatch.delenv(name, raising=False)
    sender = MockEmailProvider(log_to_stdout=False)
    monkeypatch.setattr("interfaces.research.api.auth.get_email_provider", lambda: sender)
    reset_auth_throttles()
    app = create_app(register_wrestling=False, register_providers=False)
    return app, sender, tmp_path


def sign_in(app, sender, email):
    client = TestClient(app)
    requested = client.post("/auth/request", json={"email": email, "next": "/notebooks"})
    assert requested.status_code == 200
    assert sender.sent and sender.sent[-1].email.to == email.strip().lower()
    code = sender.sent[-1].email.subject.rsplit("·", 1)[-1].strip()
    payload = requested.json()
    assert "device_code" not in payload
    claimed = client.post("/auth/claim", json={**payload_without_sent(payload), "code": code})
    assert claimed.status_code == 200
    assert claimed.json()["authenticated"] is True
    return client, payload, code


def payload_without_sent(payload):
    return {name: payload[name] for name in ("attempt_id", "claim_secret")}


def test_public_email_proof_persists_distinct_namespace_without_operator_scopes(account_api):
    app, sender, root = account_api
    identities = {}
    for email in (ALICE, BOB, OPERATOR):
        client, _payload, _code = sign_in(app, sender, email)
        identity = client.get("/auth/whoami").json()
        assert identity["user_id"] == derive_owner_from_verified_email(email)
        assert identity["is_operator"] is (email == OPERATOR)
        if email != OPERATOR:
            assert "operator" not in identity["scopes"]
            assert "shared_substrate_write" not in identity["scopes"]
        identities[email] = identity["user_id"]
    assert len(set(identities.values())) == 3
    store = root / "accounts.json"
    assert store.stat().st_mode & 0o777 == 0o600
    persisted = json.loads(store.read_text())
    assert {row["user_id"] for row in persisted["accounts"]} == set(identities.values())


def test_public_subject_survives_normalized_relogin(account_api):
    app, sender, _root = account_api
    first, _payload, _code = sign_in(app, sender, ALICE)
    second, _payload, _code = sign_in(app, sender, " ALICE@EXAMPLE.TEST ")
    assert first.get("/auth/me").json()["user_id"] == second.get("/auth/me").json()["user_id"]


def test_two_accounts_cannot_hydrate_or_mutate_each_others_notebook(account_api):
    app, sender, _root = account_api
    alice, _payload, _code = sign_in(app, sender, ALICE)
    bob, _payload, _code = sign_in(app, sender, BOB)
    created = alice.post(
        "/notebooks", json={"title": "Alice local fixture", "owner_user_id": "bob"}
    )
    assert created.status_code == 201
    notebook = created.json()["notebook_id"]
    appended = alice.post(
        f"/notebooks/{notebook}/blocks",
        json={
            "block_type": "prose",
            "content": {
                "type": "paragraph",
                "content": [
                    {"type": "text", "text": "ALICE_LOCAL_PRIVATE_TEXT"},
                ],
            },
        },
    )
    assert appended.status_code == 201
    for route in (f"/notebooks/{notebook}", f"/notebooks/{notebook}/content"):
        owned = alice.get(route)
        foreign = bob.get(route, headers={"X-User-Id": alice.get("/auth/me").json()["user_id"]})
        assert owned.status_code == 200
        assert "ALICE_LOCAL_PRIVATE_TEXT" in owned.text
        assert foreign.status_code == 403
        assert "ALICE_LOCAL_PRIVATE_TEXT" not in foreign.text
        assert TestClient(app).get(route).status_code == 401
    assert (
        bob.put(
            f"/notebooks/{notebook}/content", json={"doc": {"type": "doc", "content": []}}
        ).status_code
        == 403
    )
    assert alice.get(f"/notebooks/{notebook}/content").json()["doc"]["content"]
    assert bob.get("/notebooks/nb-missing/content").status_code == 404


def test_public_session_cannot_claim_operator_or_another_stored_subject(account_api):
    app, sender, _root = account_api
    alice, _payload, _code = sign_in(app, sender, ALICE)
    operator, _payload, _code = sign_in(app, sender, OPERATOR)
    operator_id = operator.get("/auth/me").json()["user_id"]
    for subject in ("__operator__", operator_id, "acct_" + "0" * 32):
        forged = TestClient(app)
        forged.cookies.set("ANTIEK_SESSION", mint_session_cookie(user_id=subject, email=ALICE))
        assert forged.get("/auth/me").status_code == 401
    assert alice.get("/auth/me").status_code == 200


def test_account_claim_stays_one_use_and_wrong_code_does_not_sign_in(account_api):
    app, sender, _root = account_api
    client, payload, code = sign_in(app, sender, ALICE)
    assert (
        client.post("/auth/claim", json={**payload_without_sent(payload), "code": code}).status_code
        == 410
    )
    client.post("/auth/logout")
    request = client.post("/auth/request", json={"email": ALICE}).json()
    delivered = sender.sent[-1].email.subject.rsplit("·", 1)[-1].strip()
    wrong = "0000" if delivered != "0000" else "0001"
    assert (
        client.post(
            "/auth/claim", json={**payload_without_sent(request), "code": wrong}
        ).status_code
        == 400
    )
    assert client.get("/auth/me").status_code == 401


def test_signup_with_no_operator_config_still_requires_auth(account_api, monkeypatch):
    from starlette.websockets import WebSocketDisconnect

    app, sender, _root = account_api
    monkeypatch.delenv("ANTIEK_OPERATOR_EMAIL")
    assert TestClient(app).get("/notebooks").status_code == 401
    with pytest.raises(WebSocketDisconnect), TestClient(app).websocket_connect("/ws/events"):
        pytest.fail("unscoped bus admitted an anonymous account-mode client")
    alice, _payload, _code = sign_in(app, sender, ALICE)
    assert alice.get("/auth/whoami").json()["is_operator"] is False


def test_consumed_claim_cannot_rearm_email_failure_budget(account_api):
    from urllib.parse import parse_qs, urlsplit

    app, sender, _root = account_api
    client, consumed, consumed_code = sign_in(app, sender, ALICE)
    client.post("/auth/logout")
    # Ten wrong guesses across two attempts lock code entry. A retained
    # successful claim must not erase those misses when replayed between them.
    for _ in range(2):
        attempt = client.post("/auth/request", json={"email": ALICE}).json()
        code = sender.sent[-1].email.subject.rsplit("·", 1)[-1].strip()
        wrong = "0000" if code != "0000" else "0001"
        for index in range(5):
            miss = client.post(
                "/auth/claim", json={**payload_without_sent(attempt), "code": wrong}
            )
            assert miss.status_code == (410 if index == 4 else 400)
            replay = client.post(
                "/auth/claim",
                json={**payload_without_sent(consumed), "code": consumed_code},
            )
            assert replay.status_code == 410
    fresh = client.post("/auth/request", json={"email": ALICE}).json()
    delivered = sender.sent[-1].email
    code = delivered.subject.rsplit("·", 1)[-1].strip()
    locked = client.post(
        "/auth/claim", json={**payload_without_sent(fresh), "code": code}
    )
    assert locked.status_code == 429
    assert locked.json()["detail"]["code"] == "code_entry_locked"
    assert client.get("/auth/me").status_code == 401

    # The actual newly delivered mailbox link remains a recovery path.
    link = delivered.text_body.split("\n")
    link = next(line.strip() for line in link if "/auth/callback?" in line)
    query = parse_qs(urlsplit(link).query)
    recovered = client.get(
        "/auth/callback",
        params={"token": query["token"][0], "attempt": query["attempt"][0]},
        follow_redirects=False,
    )
    assert recovered.status_code == 302
    assert client.get("/auth/me").json()["user_id"] == derive_owner_from_verified_email(ALICE)


def test_closed_mode_preserves_nonmember_enumeration_guard(account_api, monkeypatch):
    app, sender, root = account_api
    monkeypatch.delenv("ANTIEK_OPEN_SIGNUP")
    response = TestClient(app).post("/auth/request", json={"email": ALICE})
    assert response.status_code == 200
    assert response.json()["sent"] is True
    assert not sender.sent
    assert not (root / "accounts.json").exists()


def test_public_accounts_cannot_inherit_operator_models_tools_or_budget(account_api):
    app, sender, _root = account_api
    operator, _payload, _code = sign_in(app, sender, OPERATOR)
    alice, _payload, _code = sign_in(app, sender, ALICE)
    bob, _payload, _code = sign_in(app, sender, BOB)
    spec = {
        "provider_kind": "openai_compat",
        "provider_catalog_id": "deepseek",
        "model_id": "deepseek-flash",
        "display_name": "Local operator model",
        "api_key": "sk-local-unit-only-abcdefghijklmnopqrstuvwxyz",
    }
    owned = operator.post("/settings/models/user", json=spec)
    assert owned.status_code == 201
    model_id = owned.json()["id"]
    choice = {"authority": "user_model", "provider_id": model_id, "model_id": "deepseek-flash"}
    for client in (alice, bob):
        assert client.get("/settings/models/catalog").status_code == 200
        assert client.get("/settings/models/user").json()["models"] == []
        assert client.post("/settings/models/user/resolve", json=choice).status_code == 409
        assert client.delete(f"/settings/models/user/{model_id}").status_code == 404
        for method, path in (
            ("get", "/settings/models"),
            ("get", "/tools"),
            ("get", "/books/curate"),
            ("post", "/investigations"),
            ("post", "/context/compose"),
            ("post", "/multimedia/generate"),
        ):
            assert getattr(client, method)(path).status_code == 403
    assert operator.get("/settings/models/user").json()["count"] == 1
    alice_model = alice.post("/settings/models/user", json={**spec, "display_name": "Alice model"})
    assert alice_model.status_code == 201
    assert alice.get("/settings/models/user").json()["count"] == 1
    assert bob.get("/settings/models/user").json()["count"] == 0


def test_book_catalogue_body_and_default_model_join_actual_owner(account_api):
    from runtime import db_lock
    from substrate.books.ingest import register_book
    from substrate.books.takedown import take_down
    from substrate.graph import ensure_initialized
    from substrate.graph.ops import insert_document

    app, sender, root = account_api
    alice, _payload, _code = sign_in(app, sender, ALICE)
    bob, _payload, _code = sign_in(app, sender, BOB)
    operator, _payload, _code = sign_in(app, sender, OPERATOR)
    db = str(root / "graph.duckdb")
    ensure_initialized(db)
    subject = alice.get("/auth/me").json()["user_id"]
    with db_lock.connect_write(db, purpose="test/account-private-book", keepalive_s=0) as con:
        for doc, owner in (("local-alice-book", subject), ("local-legacy-book", "__operator__")):
            insert_document(
                con,
                document_id=doc,
                source_tier=2,
                document_type="book",
                title=doc,
                raw_text="LOCAL_ACCOUNT_PRIVATE_BODY",
                content_class="personal_reading",
                owner_user_id=owner,
            )
            register_book(con, document_id=doc, content_class="personal_reading")
        insert_document(
            con,
            document_id="local-doc-without-book-asset",
            source_tier=2,
            document_type="book",
            title="Document-only fixture",
            raw_text="LOCAL_DOCUMENT_ONLY_PRIVATE_BODY",
            content_class="personal_reading",
            owner_user_id=subject,
        )
    db_lock.flush_warm_writers(db)
    assert alice.get("/books/local-alice-book/owner-full-text").status_code == 200
    assert "LOCAL_ACCOUNT_PRIVATE_BODY" in alice.get("/books/local-alice-book/owner-full-text").text
    for route in (
        "/books/local-alice-book",
        "/books/local-alice-book/owner-full-text",
        "/books/local-alice-book/full-text",
    ):
        foreign = bob.get(route, headers={"X-User-Id": subject})
        assert foreign.status_code == 403
        assert "LOCAL_ACCOUNT_PRIVATE_BODY" not in foreign.text
    assert bob.get("/books?status=all").json()["books"] == []
    assert bob.get("/documents").json()["documents"] == []
    assert operator.get("/books/local-legacy-book/owner-full-text").status_code == 200
    assert alice.get("/books/local-legacy-book/owner-full-text").status_code == 403
    assert operator.get("/books/local-alice-book/owner-full-text").status_code == 403
    assert bob.get("/books/local-doc-without-book-asset/owner-full-text").status_code == 403
    assert bob.get("/books/local-doc-without-book-asset/full-text").status_code == 403
    assert (
        alice.post("/books/local-alice-book/ask", json={"question": "Explain this"}).status_code
        == 403
    )
    assert alice.get("/books/local-alice-book/reading-state").status_code == 404
    state = {"page_index": 2, "revision": 0, "owner_user_id": bob.get("/auth/me").json()["user_id"]}
    assert alice.put("/books/local-alice-book/reading-state", json=state).status_code == 200
    assert alice.get("/books/local-alice-book/reading-state").json()["page_index"] == 2

    assert bob.get("/books/local-alice-book/reading-state").status_code == 403
    assert bob.put("/books/local-alice-book/reading-state", json=state).status_code == 403
    project = alice.post(
        "/projects",
        json={
            "title": "Alice reading",
            "kind": "reading",
            "primary_document_id": "local-alice-book",
        },
    )
    assert project.status_code == 201
    project_id = project.json()["project_id"]
    assert bob.get(f"/projects/{project_id}").status_code == 404
    assert (
        bob.post(
            "/projects",
            json={"title": "Foreign", "kind": "reading", "primary_document_id": "local-alice-book"},
        ).status_code
        == 403
    )
    assert (
        alice.post(
            f"/projects/{project_id}/members",
            json={"member_kind": "document", "member_id": "local-legacy-book"},
        ).status_code
        == 403
    )
    with db_lock.connect_write(db, purpose="test/account-takedown", keepalive_s=0) as con:
        take_down(con, "local-alice-book", reason="local account test")
    db_lock.flush_warm_writers(db)
    assert alice.get("/books/local-alice-book").status_code == 404


def test_issued_accounts_corpus_search_denies_all_foreign_private_classes(account_api, monkeypatch):
    from processing.embedding.embed import HashEmbedding
    from runtime import db_lock
    from substrate.graph import ensure_initialized
    from substrate.graph.ops import insert_document

    app, sender, root = account_api
    alice, _payload, _code = sign_in(app, sender, ALICE)
    bob, _payload, _code = sign_in(app, sender, BOB)
    operator, _payload, _code = sign_in(app, sender, OPERATOR)
    alice_subject = alice.get("/auth/me").json()["user_id"]
    bob_subject = bob.get("/auth/me").json()["user_id"]
    model = HashEmbedding(dimension=8)
    # Only the external embedding dependency is deterministic. HTTP issuance,
    # middleware, owner resolver and real DuckDB search remain in the control.
    monkeypatch.setattr("substrate.graph.search.SentenceTransformerEmbedding", lambda: model)
    db = str(root / "graph.duckdb")
    ensure_initialized(db)
    rows = [(f"alice-{kind}", alice_subject, kind) for kind in (
        "user_owned", "personal_reading", "restricted_pending_opt_in", None,
    )]
    rows += [("bob-own", bob_subject, "user_owned"), ("legacy-own", "__operator__", "personal_reading"),
             ("shared-public", alice_subject, "public_domain")]
    with db_lock.connect_write(db, purpose="test/account-corpus-isolation", keepalive_s=0) as con:
        for document_id, owner, content_class in rows:
            insert_document(con, document_id=document_id, title=document_id, source_tier=2,
                            document_type="book", raw_text=f"PRIVATE_{document_id}",
                            owner_user_id=owner, content_class=content_class)
            con.execute("INSERT INTO chunks (chunk_id, document_id, chunk_index, text, embedding) "
                        "VALUES (?, ?, 0, ?, ?)",
                        [f"chunk-{document_id}", document_id, f"PRIVATE_{document_id}", model.encode("ownership")])
    db_lock.flush_warm_writers(db)
    foreign = bob.get("/corpus/search?q=ownership", headers={"X-User-Id": alice_subject})
    assert foreign.status_code == 200
    assert {hit["document_id"] for hit in foreign.json()["hits"]} == {"bob-own", "shared-public"}
    assert "alice-" not in foreign.text
    assert "legacy-own" not in foreign.text
    owned = alice.get("/corpus/search?q=ownership")
    assert {hit["document_id"] for hit in owned.json()["hits"]} == {doc for doc, owner, _kind in rows if owner == alice_subject}
    scoped_foreign = bob.get("/corpus/search?q=ownership&document_id=alice-user_owned")
    assert scoped_foreign.status_code == 200 and scoped_foreign.json()["hits"] == []
    legacy = operator.get("/corpus/search?q=ownership")
    assert {hit["document_id"] for hit in legacy.json()["hits"]} == {"legacy-own", "shared-public"}

def test_passkey_login_uses_verified_stored_account_not_first_operator(account_api, monkeypatch):
    from types import SimpleNamespace

    app, sender, _root = account_api
    alice, _payload, _code = sign_in(app, sender, ALICE)
    alice_id = alice.get("/auth/me").json()["user_id"]
    record = SimpleNamespace(user_id=alice_id, email=ALICE)
    monkeypatch.setattr("interfaces.research.api.auth.complete_authentication", lambda **kw: record)
    client = TestClient(app)
    verified = client.post(
        "/auth/passkey/login/verify", json={"ceremony_id": "c" * 24, "credential": {}}
    )
    assert verified.status_code == 204
    identity = client.get("/auth/whoami").json()
    assert identity["user_id"] == alice_id
    assert identity["is_operator"] is False
    record.user_id = "__operator__"
    record.email = None
    # There has been no email proof/persisted alias for the old operator.
    assert (
        TestClient(app)
        .post("/auth/passkey/login/verify", json={"ceremony_id": "d" * 24, "credential": {}})
        .status_code
        == 400
    )


def test_disabling_signup_does_not_upgrade_retained_public_passkey(account_api, monkeypatch):
    from types import SimpleNamespace

    app, sender, _root = account_api
    alice, _payload, _code = sign_in(app, sender, ALICE)
    record = SimpleNamespace(user_id=alice.get("/auth/me").json()["user_id"], email=ALICE)
    monkeypatch.setattr("interfaces.research.api.auth.complete_authentication", lambda **kw: record)
    monkeypatch.delenv("ANTIEK_OPEN_SIGNUP")
    anonymous = TestClient(app)
    result = anonymous.post(
        "/auth/passkey/login/verify", json={"ceremony_id": "r" * 24, "credential": {}}
    )
    assert result.status_code == 204
    identity = anonymous.get("/auth/whoami").json()
    assert identity["user_id"] == record.user_id
    assert identity["is_operator"] is False
    assert "operator" not in identity["scopes"]
    assert anonymous.get("/settings/models").status_code == 403


def test_magic_link_is_one_use_and_cannot_move_to_a_new_attempt(account_api):
    from urllib.parse import parse_qs, urlsplit

    app, sender, _root = account_api
    client = TestClient(app)
    first = client.post("/auth/request", json={"email": ALICE}).json()
    link = next(
        line.strip()
        for line in sender.sent[-1].email.text_body.splitlines()
        if "/auth/callback?" in line
    )
    query = parse_qs(urlsplit(link).query)
    token = query["token"][0]
    callback = client.get(
        "/auth/callback",
        params={"token": token, "attempt": first["attempt_id"]},
        follow_redirects=False,
    )
    assert callback.status_code == 302
    assert "ANTIEK_SESSION" in callback.cookies
    assert client.get("/auth/me").status_code == 200
    reused = TestClient(app).get(
        "/auth/callback",
        params={"token": token, "attempt": first["attempt_id"]},
        follow_redirects=False,
    )
    assert "ANTIEK_SESSION" not in reused.cookies
    second = client.post("/auth/request", json={"email": ALICE}).json()
    assert second["attempt_id"] != first["attempt_id"]
    moved = TestClient(app).get(
        "/auth/callback",
        params={"token": token, "attempt": second["attempt_id"]},
        follow_redirects=False,
    )
    assert "ANTIEK_SESSION" not in moved.cookies
    assert "magic_link_invalid" in moved.headers["location"]


def test_unsupported_unicode_address_cannot_alias_an_ascii_operator(account_api, monkeypatch):
    app, sender, root = account_api
    monkeypatch.setenv("ANTIEK_OPERATOR_EMAIL", "strasse@example.test")
    response = TestClient(app).post("/auth/request", json={"email": "straße@example.test"})
    assert response.status_code == 422
    assert not sender.sent
    assert not (root / "accounts.json").exists()


def test_public_passkey_status_never_counts_an_operators_credentials(account_api, monkeypatch):
    from types import SimpleNamespace

    app, sender, _root = account_api
    alice, _payload, _code = sign_in(app, sender, ALICE)
    operator, _payload, _code = sign_in(app, sender, OPERATOR)
    operator_id = operator.get("/auth/me").json()["user_id"]
    monkeypatch.setattr(
        "interfaces.research.api.auth.list_credentials",
        lambda: [SimpleNamespace(user_id=operator_id)],
    )
    assert alice.get("/auth/passkey/status").json() == {"available": False, "count": 0}
    assert operator.get("/auth/passkey/status").json() == {"available": True, "count": 1}


@pytest.mark.parametrize("email,legacy", [(ALICE, False), (OPERATOR, True)])
def test_account_export_and_status_use_only_the_proven_owner(account_api, monkeypatch, email, legacy):
    from runtime.db_lock import connect_write
    from substrate.event_log import log_event, trajectory
    from substrate.graph import default_db_path
    from substrate.graph.insight_question import promote_insight
    from substrate.graph.ops import insert_document
    from substrate.research_artifact.store import ResearchArtifactStore

    app, sender, root = account_api
    monkeypatch.setenv("ANTIEK_RESEARCH_ARTIFACTS_DIR", str(root / "artifacts"))
    monkeypatch.setenv("ANTIEK_EMBEDDING_PROVIDER", "hash")
    owner, _payload, _code = sign_in(app, sender, email)
    foreign, _payload, _code = sign_in(app, sender, BOB)
    owner_id = owner.get("/auth/me").json()["user_id"]
    stored_owner = "__operator__" if legacy else owner_id
    investigation = "account-export"
    with connect_write(default_db_path(), purpose="test/account-export-source") as con:
        insert_document(
            con, document_id="account-export-source", document_type="web", source_tier=2,
            raw_text="OWNED_EXPORT_SOURCE_CONTROL", content_class="personal_reading",
            owner_user_id=stored_owner,
        )
    promote_insight(
        text="OWNED_EXPORT_FINDING_CONTROL", investigation_id=investigation,
        source_document_id="account-export-source", owner_user_id=stored_owner,
    )
    log_event(investigation, "investigation.start_requested", payload={
        "question": "Owned account export control", "owner_user_id": stored_owner,
    })

    def files():
        return {str(path): path.read_bytes() for path in (root / "artifacts").rglob("*") if path.is_file()}

    before_files, before_events = files(), trajectory(investigation)
    denied = foreign.post(f"/research/{investigation}/artifact/export", json={"owner_user_id": stored_owner})
    assert denied.status_code == 403
    assert files() == before_files and trajectory(investigation) == before_events
    assert ResearchArtifactStore(default_db_path()).get(investigation) is None
    assert TestClient(app).post(f"/research/{investigation}/artifact/export").status_code == 401

    exported = owner.post(f"/research/{investigation}/artifact/export")
    assert exported.status_code == 200, exported.text
    record = ResearchArtifactStore(default_db_path()).get(investigation)
    assert record is not None and record.owner_user_id == stored_owner
    assert b"OWNED_EXPORT_FINDING_CONTROL" in record.source_path.read_bytes()
    status = owner.get(f"/research/{investigation}/artifact")
    assert status.status_code == 200
    assert status.json()["artifact_id"] == exported.json()["artifact_id"]
    assert foreign.get(f"/research/{investigation}/artifact").status_code == 404
    before_files, before_events = files(), trajectory(investigation)
    assert foreign.post(f"/research/{investigation}/artifact/export").status_code == 403
    assert files() == before_files and trajectory(investigation) == before_events
    assert owner.post(f"/research/{investigation}/artifact/export").status_code == 200


@pytest.mark.parametrize("path", [
    "/research/account-export/artifact/import-notes",
    "/research/artifacts/compose",
    "/research/artifacts/source-merge/restore",
])
def test_account_export_admission_does_not_open_unscoped_siblings(account_api, path):
    app, sender, _root = account_api
    alice, _payload, _code = sign_in(app, sender, ALICE)
    assert alice.post(path, json={}).status_code == 403
    assert alice.get("/research/account-export/artifact/blocks").status_code == 403
