from collections.abc import Iterator
from pathlib import Path
from unittest.mock import Mock

import pytest
from fastapi import HTTPException, Request
from fastapi.testclient import TestClient

from interfaces.research.api import speak_routes
from interfaces.research.api.app import create_app
from runtime.db_lock import connect_read, connect_write
from substrate.graph import default_db_path
from substrate.speak import invitations, takedown

_OPERATOR_HEADERS = {"Authorization": "Bearer speak-takedown-test-operator"}


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    monkeypatch.setenv("ANTIEK_OPERATOR_TOKEN", "speak-takedown-test-operator")
    monkeypatch.setenv("ANTIEK_SPEAK_PUBLIC_ECOSYSTEM", "1")
    app = create_app(register_wrestling=False, register_providers=False, cors_origins=[])
    with TestClient(app) as client:
        yield client


def _project(client: TestClient, intent: str = "will_be_public") -> str:
    response = client.post(
        "/speak/projects", headers=_OPERATOR_HEADERS,
        json={"title": "Synthetic takedown fixture", "subject_ref": "fixture-subject", "publish_intent": intent},
    )
    assert response.status_code == 201, response.text
    return response.json()["project_id"]


def _mint(client: TestClient, project_id: str) -> dict:
    response = client.post(f"/speak/projects/{project_id}/open-contribute")
    assert response.status_code == 201, response.text
    return response.json()


def _withdraw(client: TestClient, project_id: str) -> str:
    response = client.post(
        f"/speak/projects/{project_id}/takedowns", headers=_OPERATOR_HEADERS,
        json={"target_kind": "subject", "target_id": "fixture-subject", "requested_by": "fixture-subject"},
    )
    assert response.status_code == 201, response.text
    return response.json()["takedown_id"]


def _state() -> tuple:
    with connect_read(default_db_path()) as con:
        return (
            con.execute("SELECT project_id, invitation_mode FROM speak_projects ORDER BY project_id").fetchall(),
            con.execute("SELECT interview_id, status, transcript_turns, consent_recorded FROM interviews ORDER BY interview_id").fetchall(),
            con.execute("SELECT count(*) FROM speak_invites").fetchone(),
            con.execute("SELECT interview_id, scope, granted, revoked_at FROM speak_consent ORDER BY interview_id, scope").fetchall(),
        )


def test_public_token_controls_use_real_consent_and_operator_auth(client: TestClient) -> None:
    assert client.post("/speak/projects", json={"title": "Unadmitted"}).status_code == 401
    project_id = _project(client)
    minted = _mint(client, project_id)
    response = client.get(minted["invite_path"])
    assert response.status_code == 200
    assert response.json()["project_id"] == project_id
    consent = client.post(f"{minted['invite_path']}/consent", json={"scopes": ["record"]})
    assert consent.status_code == 200
    assert consent.json()["granted"] == ["record"]
    assert client.get(minted["invite_path"]).json()["granted_consent_scopes"] == ["record"]
    voice = client.post(
        f"{minted['invite_path']}/voice?question_id=q1", content=b"unread-upload",
        headers={"Content-Type": "audio/webm", "Content-Length": "invalid"},
    )
    assert voice.status_code == 400
    assert voice.json() == {"detail": "invalid Content-Length"}


@pytest.mark.parametrize("action", ["landing", "consent", "answer", "voice", "followups", "decline"])
def test_withdrawn_public_token_matches_unknown_without_work(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, action: str,
) -> None:
    project_id = _project(client)
    minted = _mint(client, project_id)
    path = minted["invite_path"]
    assert client.get(path).status_code == 200
    consent = client.post(f"{path}/consent", json={"scopes": ["record"]})
    assert consent.status_code == 200
    _withdraw(client, project_id)
    before = _state()
    writers: list[str] = []
    bodies: list[str] = []
    original_write = speak_routes._write
    original_body = Request.body

    def observed_write(purpose: str):
        writers.append(purpose)
        return original_write(purpose)

    async def observed_body(request: Request) -> bytes:
        if request.url.path.endswith("/voice"):
            bodies.append(request.url.path)
        return await original_body(request)

    forbidden = Mock(side_effect=AssertionError("Withdrawn token reached downstream work"))
    monkeypatch.setattr(speak_routes, "_write", observed_write)
    monkeypatch.setattr(Request, "body", observed_body)
    for name in ("submit_answer", "transcribe_voice", "next_followups", "decline"):
        monkeypatch.setattr(speak_routes, name, forbidden)

    def call(token_path: str):
        if action == "landing":
            return client.get(token_path)
        if action == "consent":
            return client.post(f"{token_path}/consent", json={"scopes": ["record", "publish"]})
        if action == "answer":
            return client.post(f"{token_path}/answer", json={"question_id": "q1", "transcript": "Must not be stored"})
        if action == "voice":
            return client.post(f"{token_path}/voice?question_id=q1", content=b"denied-upload", headers={"Content-Type": "audio/webm"})
        return client.post(f"{token_path}/{action}")

    withdrawn = call(path)
    unknown = call("/speak/invite/not-a-real-fixture-token")
    assert withdrawn.status_code == unknown.status_code == 404
    assert withdrawn.json() == unknown.json() == {"detail": "unknown or expired invite link"}
    assert not writers
    assert not bodies
    forbidden.assert_not_called()
    assert _state() == before


def test_writer_admission_rechecks_takedown_and_reversal(client: TestClient) -> None:
    project_id = _project(client)
    minted = _mint(client, project_id)
    with connect_write(default_db_path(), purpose="speak/test:token-control") as con:
        assert speak_routes._require_token(con, minted["token"]) == (minted["interview_id"], project_id)
    takedown_id = _withdraw(client, project_id)
    with connect_write(default_db_path(), purpose="speak/test:token-denial") as con:
        with pytest.raises(HTTPException) as withdrawn:
            speak_routes._require_token(con, minted["token"])
        with pytest.raises(HTTPException) as unknown:
            speak_routes._require_token(con, "not-a-real-fixture-token")
        assert withdrawn.value.status_code == unknown.value.status_code == 404
        assert withdrawn.value.detail == unknown.value.detail
        takedown.reverse_takedown(con, takedown_id=takedown_id)
        assert speak_routes._require_token(con, minted["token"]) == (minted["interview_id"], project_id)


def test_withdrawn_project_mints_nothing_or_changes_mode(client: TestClient) -> None:
    project_id = _project(client)
    _withdraw(client, project_id)
    before = _state()
    response = client.post(f"/speak/projects/{project_id}/open-contribute")
    assert response.status_code == 404
    assert response.json() == {"detail": f"project {project_id!r} not found"}
    assert _state() == before


def test_mint_preserves_other_projects_and_reversed_takedowns(client: TestClient) -> None:
    withdrawn_id = _project(client)
    takedown_id = _withdraw(client, withdrawn_id)
    other_id = _project(client)
    minted = _mint(client, other_id)
    assert client.get(minted["invite_path"]).status_code == 200
    with connect_write(default_db_path(), purpose="speak/test:reverse-control") as con:
        takedown.reverse_takedown(con, takedown_id=takedown_id)
        invite = invitations.mint_open_contribution(con, withdrawn_id)
        assert invite.project_id == withdrawn_id
    assert client.get(f"/speak/invite/{invite.token}").status_code == 200


@pytest.mark.parametrize("intent,g7", [("private_never_published", "1"), ("will_be_public", "0")])
def test_mint_keeps_private_and_g7_gates(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, intent: str, g7: str,
) -> None:
    project_id = _project(client, intent)
    monkeypatch.setenv("ANTIEK_SPEAK_PUBLIC_ECOSYSTEM", g7)
    before = _state()
    response = client.post(f"/speak/projects/{project_id}/open-contribute")
    assert response.status_code == 403
    assert _state() == before


@pytest.mark.parametrize("store", ["missing", "graph_without_speak"])
def test_public_reads_refuse_cold_store_without_schema_writes(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, store: str,
) -> None:
    db = tmp_path / "missing.duckdb" if store == "missing" else Path(default_db_path())
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", str(db))
    before = db.read_bytes() if db.exists() else None
    landing = client.get("/speak/invite/unknown-cold-token")
    voice = client.post(
        "/speak/invite/unknown-cold-token/voice?question_id=q1", content=b"unread-upload",
        headers={"Content-Type": "audio/webm"},
    )
    assert landing.status_code == voice.status_code == 404
    assert landing.json() == voice.json() == {"detail": "unknown or expired invite link"}
    assert (db.read_bytes() if db.exists() else None) == before
