"""Real account admission and private text storage; no mailbox or paid inference."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from unittest.mock import Mock

import httpx
import pytest
from fastapi.testclient import TestClient

from acquisition.voice import adapter
from interfaces.research.api import speak_routes
from interfaces.research.api.app import create_app
from interfaces.research.api.auth import reset_auth_throttles
from processing.embedding.embed import HashEmbedding, embedding_provider_fingerprint
from runtime.db_lock import connect_read, connect_write
from substrate.auth import MockEmailProvider
from substrate.graph import default_db_path
from substrate.graph.schema import init_database
from substrate.rights.register import GATED_DEFAULT_CONTENT_CLASS
from substrate.speak import project

OPERATOR = "legacy-speak@example.invalid"
ALICE = "speak-a@example.invalid"
BOB = "speak-b@example.invalid"


def _sign_in(app, sender, email: str) -> TestClient:
    client = TestClient(app)
    requested = client.post("/auth/request", json={"email": email, "next": "/speak"})
    assert requested.status_code == 200
    assert sender.sent[-1].email.to == email
    payload = requested.json()
    code = sender.sent[-1].email.subject.rsplit("·", 1)[-1].strip()
    claimed = client.post(
        "/auth/claim",
        json={
            "attempt_id": payload["attempt_id"],
            "claim_secret": payload["claim_secret"],
            "code": code,
        },
    )
    assert claimed.status_code == 200
    assert claimed.json()["authenticated"] is True
    assert client.get("/auth/me").status_code == 200
    return client


@pytest.fixture
def accounts(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    monkeypatch.setenv("ANTIEK_AUTH_SECRET", "synthetic-speak-account-signing-secret-" + "x" * 48)
    monkeypatch.setenv("ANTIEK_OPERATOR_EMAIL", OPERATOR)
    monkeypatch.setenv("ANTIEK_LEGACY_OPERATOR_EMAIL", OPERATOR)
    monkeypatch.setenv("ANTIEK_OPEN_SIGNUP", "1")
    monkeypatch.setenv("ANTIEK_COOKIE_INSECURE", "1")
    for variable, relative in {
        "ANTIEK_ACCOUNT_STORE": "accounts.json",
        "ANTIEK_PASSKEY_STORE": "passkeys.json",
        "ANTIEK_DUCKDB_PATH": "graph.duckdb",
        "ANTIEK_RESEARCH_EVENTS_DIR": "events",
        "ANTIEK_USER_MODELS_PATH": "models.json",
        "ANTIEK_BYOK_ARTIFACT": "credentials.enc",
        "ANTIEK_BYOK_KEY_FILE": "master.key",
    }.items():
        monkeypatch.setenv(variable, str(tmp_path / relative))
    for variable in (
        "ANTIEK_OPERATOR_TOKEN",
        "ANTIEK_DEV_LOGIN_TOKEN",
        "ANTIEK_OPERATOR_SERVICE_TOKEN_CLIENT_ID",
        "CF_ACCESS_CLIENT_SECRET",
        "OPENAI_API_KEY",
    ):
        monkeypatch.delenv(variable, raising=False)
    with connect_write(
        default_db_path(), purpose="speak/test:initialized-account-catalogue", keepalive_s=0
    ) as con:
        init_database(con)
    sender = MockEmailProvider(log_to_stdout=False)
    monkeypatch.setattr("interfaces.research.api.auth.get_email_provider", lambda: sender)
    reset_auth_throttles()
    app = create_app(register_wrestling=False, register_providers=False, cors_origins=[])
    alice, bob = (_sign_in(app, sender, address) for address in (ALICE, BOB))
    for client in (alice, bob):
        identity = client.get("/auth/whoami").json()
        assert identity["is_operator"] is False
        assert "operator" not in identity["scopes"]
    assert alice.get("/auth/me").json()["user_id"] != bob.get("/auth/me").json()["user_id"]
    yield app, sender, tmp_path, alice, bob
    alice.close()
    bob.close()


def _create(client: TestClient, title: str = "Synthetic owner-bound story", **extra) -> str:
    created = client.post("/speak/projects", json={"title": title, **extra})
    assert created.status_code == 201
    assert created.json()["publish_intent"] == "private_never_published"
    return created.json()["project_id"]


def _invite(client: TestClient, project_id: str) -> dict:
    invited = client.post(
        f"/speak/projects/{project_id}/invites",
        json={
            "informant_handle": "synthetic contributor, not a principal",
        },
    )
    assert invited.status_code == 201
    return invited.json()


def _unchanged_rows_and_events(root: Path) -> tuple:
    with connect_read(default_db_path()) as con:
        counts = tuple(
            con.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
            for table in (
                "interview_projects",
                "speak_projects",
                "interviews",
                "speak_invites",
                "speak_consent",
                "documents",
                "chunks",
                "nodes",
            )
        )
    events = tuple(
        sorted(
            (str(path.relative_to(root)), hashlib.sha256(path.read_bytes()).hexdigest())
            for path in (root / "events").rglob("*.jsonl")
            if path.is_file()
        )
    )
    return counts, events


def test_actual_accounts_create_list_detail_and_share_only_their_own_projects(accounts):
    _app, _sender, _root, alice, bob = accounts
    a_subject = alice.get("/auth/me").json()["user_id"]
    b_subject = bob.get("/auth/me").json()["user_id"]
    a = _create(alice, owner_user_id=b_subject, user_id=b_subject, email=BOB)
    b = _create(bob, "A second synthetic owner story")
    with connect_read(default_db_path()) as con:
        assert dict(
            con.execute("SELECT project_id, owner_user_id FROM interview_projects").fetchall()
        ) == {
            a: a_subject,
            b: b_subject,
        }
    for client, owned in ((alice, a), (bob, b)):
        listed = client.get("/speak/projects")
        assert listed.status_code == 200
        assert [row["project_id"] for row in listed.json()["projects"]] == [owned]
        assert client.get(f"/speak/projects/{owned}").status_code == 200
        invite = _invite(client, owned)
        invites = client.get(f"/speak/projects/{owned}/invites")
        assert invites.status_code == 200
        assert [row["interview_id"] for row in invites.json()["invites"]] == [
            invite["interview_id"]
        ]
        with TestClient(client.app) as contributor:
            landing = contributor.get(f"/speak/invite/{invite['token']}")
        assert landing.status_code == 200
        assert landing.json()["pending_questions"] == [
            {
                "id": "first_memory",
                "text": "Share a memory in your own words.",
            }
        ]
        assert landing.json()["transcript"] == []


@pytest.mark.parametrize("method,suffix", [("GET", ""), ("GET", "/invites"), ("POST", "/invites")])
def test_foreign_and_unknown_private_projects_refuse_without_mutation_or_provider(
    accounts,
    monkeypatch: pytest.MonkeyPatch,
    method: str,
    suffix: str,
):
    _app, _sender, root, alice, bob = accounts
    a = _create(alice)
    _invite(alice, a)
    forbidden = Mock(side_effect=AssertionError("Denied owner reached provider"))
    monkeypatch.setattr(adapter, "default_embedding_provider", forbidden)
    monkeypatch.setattr(speak_routes, "transcribe_voice", forbidden)
    before = _unchanged_rows_and_events(root)
    results = []
    for project_id in (a, "ivp-unknown-owner-fixture"):
        response = bob.request(
            method,
            f"/speak/projects/{project_id}{suffix}",
            json={"informant_handle": "unadmitted"} if method == "POST" else None,
        )
        results.append((response.status_code, response.json()))
    assert results == [(404, {"detail": "project_not_found"})] * 2
    assert _unchanged_rows_and_events(root) == before
    forbidden.assert_not_called()


@pytest.mark.parametrize(
    "method,path",
    [
        ("GET", "/speak/projects"),
        ("POST", "/speak/projects"),
        ("GET", "/speak/projects/{project}"),
        ("GET", "/speak/projects/{project}/invites"),
        ("POST", "/speak/projects/{project}/invites"),
    ],
)
def test_anonymous_private_project_access_never_borrows_an_owner(accounts, method, path):
    app, _sender, root, alice, _bob = accounts
    project_id = _create(alice)
    before = _unchanged_rows_and_events(root)
    with TestClient(app) as anonymous:
        refused = anonymous.request(
            method,
            path.format(project=project_id),
            json={
                "title": "not admitted",
                "informant_handle": "not admitted",
                "owner_user_id": "__operator__",
            },
        )
    assert refused.status_code == 401
    assert _unchanged_rows_and_events(root) == before


def test_token_text_memory_uses_stored_owner_for_real_documents_nodes_and_retrieval(
    accounts,
    monkeypatch: pytest.MonkeyPatch,
):
    app, _sender, _root, alice, bob = accounts
    # Use the existing deterministic local backend for storage/authority controls,
    # never as native/pretrained/provider evidence or a production fallback.
    embedder = HashEmbedding(dimension=16)
    monkeypatch.setattr(adapter, "default_embedding_provider", lambda: embedder)
    text = "A synthetic contributor remembers checking a notebook before sharing a story."
    saved = []
    with TestClient(app) as contributor:
        for client in (alice, bob):
            owner = client.get("/auth/me").json()["user_id"]
            pid = _create(client)
            invitation = _invite(client, pid)
            path = f"/speak/invite/{invitation['token']}"
            assert (
                contributor.post(f"{path}/consent", json={"scopes": ["record"]}).status_code == 200
            )
            answered = contributor.post(
                f"{path}/answer",
                json={
                    "question_id": "first_memory",
                    "transcript": text,
                    "owner_user_id": "__operator__",
                },
            )
            assert answered.status_code == 201
            document_id = answered.json()["document_id"]
            assert document_id and answered.json()["skipped_reason"] is None
            resumed = contributor.get(path)
            assert resumed.status_code == 200
            assert any(
                turn["role"] == "informant" and turn["text"] == text
                for turn in resumed.json()["transcript"]
            )
            assert not any(q["id"] == "first_memory" for q in resumed.json()["pending_questions"])
            with connect_read(default_db_path()) as con:
                row = con.execute(
                    "SELECT owner_user_id, investigation_id, content_class, raw_text "
                    "FROM documents WHERE document_id = ?",
                    [document_id],
                ).fetchone()
                assert row[:3] == (owner, pid, GATED_DEFAULT_CONTENT_CLASS)
                assert text in row[3]
                chunks = con.execute(
                    "SELECT chunk_id, text FROM chunks WHERE document_id = ?", [document_id]
                ).fetchall()
                assert any(text in chunk[1] for chunk in chunks)
                nodes = con.execute(
                    "SELECT node_id, owner_user_id, metadata FROM nodes WHERE metadata LIKE ?",
                    [f'%"operator_id": "{owner}"%'],
                ).fetchall()
                assert nodes and all(row[1] == owner for row in nodes)
                assert {json.loads(node[2])["chunk_id"] for node in nodes} == {
                    chunk[0] for chunk in chunks
                }
                fingerprints = con.execute(
                    "SELECT DISTINCT m.fingerprint FROM embeddings_meta m "
                    "JOIN chunks c ON c.chunk_id = m.chunk_id WHERE c.document_id = ?",
                    [document_id],
                ).fetchall()
                assert fingerprints == [(embedding_provider_fingerprint(embedder),)]
            saved.append((owner, document_id, {row[0] for row in nodes}))
    assert saved[0][1] != saved[1][1]
    assert saved[0][2].isdisjoint(saved[1][2])
    for client, own, foreign in (
        (alice, saved[0][1], saved[1][1]),
        (bob, saved[1][1], saved[0][1]),
    ):
        # Existing HTTP body retrieval retains its independent rights gate.
        owned = client.get(f"/books/{own}/owner-full-text")
        assert owned.status_code == 200
        assert owned.json()["full_text"] is None
        assert client.get(f"/books/{foreign}/owner-full-text").status_code == 403


@pytest.mark.asyncio
async def test_account_owned_token_voice_refuses_before_buffering_or_paid_provider(
    accounts,
    monkeypatch: pytest.MonkeyPatch,
):
    app, _sender, root, alice, _bob = accounts
    invitation = _invite(alice, _create(alice))
    path = f"/speak/invite/{invitation['token']}"
    with TestClient(app) as contributor:
        assert contributor.post(f"{path}/consent", json={"scopes": ["record"]}).status_code == 200
    forbidden = Mock(side_effect=AssertionError("Account text authority reached paid voice"))
    monkeypatch.setattr(speak_routes, "transcribe_voice", forbidden)
    before = _unchanged_rows_and_events(root)
    read = []

    async def body():
        read.append(True)
        raise AssertionError("Unadmitted voice body was consumed")
        yield b"unadmitted"  # pragma: no cover

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as caller:
        refused = await caller.post(
            f"{path}/voice?question_id=first_memory",
            content=body(),
            headers={"Content-Type": "audio/webm"},
        )
    assert refused.status_code == 403
    assert "type your memory" in refused.json()["detail"]
    assert read == []
    forbidden.assert_not_called()
    assert _unchanged_rows_and_events(root) == before


@pytest.mark.asyncio
async def test_voice_rechecks_stored_owner_after_the_body_and_before_provider(
    accounts, monkeypatch
):
    app, sender, root, _alice, bob = accounts
    operator = _sign_in(app, sender, OPERATOR)
    with connect_write(default_db_path(), purpose="speak/test:voice-legacy-fixture") as con:
        legacy = project.create_project(con, title="Synthetic voice ownership race")
    invitation = _invite(operator, legacy.project_id)
    path = f"/speak/invite/{invitation['token']}"
    with TestClient(app) as contributor:
        assert contributor.post(f"{path}/consent", json={"scopes": ["record"]}).status_code == 200
    forbidden = Mock(side_effect=AssertionError("Retired legacy authority reached voice provider"))
    monkeypatch.setattr(speak_routes, "transcribe_voice", forbidden)
    before = _unchanged_rows_and_events(root)
    subject = bob.get("/auth/me").json()["user_id"]
    read = []

    async def body():
        read.append(True)
        with connect_write(default_db_path(), purpose="speak/test:voice-owned-race") as con:
            con.execute(
                "UPDATE interview_projects SET owner_user_id = ? WHERE project_id = ?",
                [subject, legacy.project_id],
            )
        yield b"synthetic negative control, never sent to ASR"

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as caller:
        refused = await caller.post(
            f"{path}/voice?question_id=first_memory",
            content=body(),
            headers={"Content-Type": "audio/webm"},
        )
    assert read == [True]
    assert refused.status_code == 403
    forbidden.assert_not_called()
    assert _unchanged_rows_and_events(root) == before
    operator.close()


def test_unconsented_text_never_writes_owned_memory_or_calls_embedding(accounts, monkeypatch):
    app, _sender, root, alice, _bob = accounts
    invitation = _invite(alice, _create(alice))
    forbidden = Mock(side_effect=AssertionError("Unconsented text reached embedding"))
    monkeypatch.setattr(adapter, "default_embedding_provider", forbidden)
    before = _unchanged_rows_and_events(root)
    with TestClient(app) as contributor:
        refused = contributor.post(
            f"/speak/invite/{invitation['token']}/answer",
            json={
                "question_id": "first_memory",
                "transcript": "Not consented, so this must never be ingested.",
            },
        )
    assert refused.status_code == 403
    assert _unchanged_rows_and_events(root) == before
    forbidden.assert_not_called()


def test_original_operator_legacy_alias_reads_old_project_without_reassigning_it(accounts):
    app, sender, _root, alice, _bob = accounts
    operator = _sign_in(app, sender, OPERATOR)
    with connect_write(default_db_path(), purpose="speak/test:legacy-owned-project") as con:
        old = project.create_project(con, title="Synthetic existing legacy story")
    assert operator.get(f"/speak/projects/{old.project_id}").status_code == 200
    _invite(operator, old.project_id)
    assert alice.get(f"/speak/projects/{old.project_id}").status_code == 404
    fresh = _create(operator)
    with connect_read(default_db_path()) as con:
        rows = dict(
            con.execute("SELECT project_id, owner_user_id FROM interview_projects").fetchall()
        )
    assert rows[old.project_id] == "__operator__"
    assert rows[fresh] == operator.get("/auth/me").json()["user_id"] != "__operator__"
    operator.close()


@pytest.mark.parametrize(
    "method,path",
    [
        ("GET", "/speak/projects/{project}/economics"),
        ("POST", "/speak/biography"),
        ("GET", "/speak/interviews/unadmitted"),
        ("POST", "/speak/interviews/unadmitted/consent"),
        ("POST", "/speak/interviews/unadmitted/answers"),
        ("POST", "/speak/projects/{project}/draft"),
        ("POST", "/speak/projects/{project}/publish"),
        ("POST", "/speak/projects/{project}/release-payout"),
        ("GET", "/speak/pushes"),
    ],
)
def test_five_private_ports_never_confer_unaudited_or_paid_authority(accounts, method, path):
    _app, _sender, root, alice, _bob = accounts
    pid = _create(alice)
    before = _unchanged_rows_and_events(root)
    refused = alice.request(method, path.format(project=pid), json={})
    assert refused.status_code == 403
    assert refused.json() == {"detail": "operator_access_required"}
    assert _unchanged_rows_and_events(root) == before
