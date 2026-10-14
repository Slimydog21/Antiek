import json
from collections.abc import Iterator
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient

from interfaces.research.api import speak_routes
from interfaces.research.api.app import create_app
from runtime.db_lock import connect_read, connect_write
from substrate.auth import mint_session_cookie
from substrate.graph import default_db_path
from substrate.speak import project


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    monkeypatch.delenv("ANTIEK_OPERATOR_TOKEN", raising=False)
    monkeypatch.setenv("ANTIEK_OPERATOR_EMAIL", "speak-first-memory@example.invalid")
    monkeypatch.setenv("ANTIEK_AUTH_SECRET", "speak-first-memory-test-signing-secret")
    app = create_app(register_wrestling=False, register_providers=False, cors_origins=[])
    with TestClient(app) as client:
        client.cookies.set(
            "ANTIEK_SESSION",
            mint_session_cookie(
                user_id="__operator__",
                email="speak-first-memory@example.invalid",
            ),
        )
        assert client.get("/auth/me").status_code == 200
        yield client


def _invite(client: TestClient, project_id: str) -> str:
    response = client.post(
        f"/speak/projects/{project_id}/invites",
        json={
            "informant_handle": "clearly labelled first-memory fixture",
        },
    )
    assert response.status_code == 201
    return f"/speak/invite/{response.json()['token']}"


def test_new_story_has_a_persisted_first_question_without_claiming_an_answer(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    response = client.post(
        "/speak/projects",
        json={
            "title": "Synthetic first-memory fixture",
            "subject_ref": "fixture-subject",
        },
    )
    assert response.status_code == 201
    project_id = response.json()["project_id"]
    assert response.json()["publish_intent"] == "private_never_published"
    assert response.json()["invitation_mode"] == "private"
    path = _invite(client, project_id)
    expected = [{"id": "first_memory", "text": "Share a memory in your own words."}]
    with connect_read(default_db_path()) as con:
        row = con.execute(
            "SELECT interview_guide FROM interview_projects WHERE project_id = ?",
            [project_id],
        ).fetchone()
    assert row is not None
    assert json.loads(row[0]) == {"must_cover": expected}
    landing = client.get(path)
    assert landing.status_code == 200
    assert landing.json()["pending_questions"] == expected
    assert landing.json()["transcript"] == []
    assert landing.json()["granted_consent_scopes"] == []

    forbidden = Mock(side_effect=AssertionError("Unconsented recording reached ASR"))
    monkeypatch.setattr(speak_routes, "transcribe_voice", forbidden)
    voice = client.post(
        f"{path}/voice?question_id=first_memory",
        content=b"not-admitted",
        headers={"Content-Type": "audio/webm", "Content-Length": "invalid"},
    )
    assert voice.status_code == 403
    forbidden.assert_not_called()

    consent = client.post(f"{path}/consent", json={"scopes": ["record"]})
    assert consent.status_code == 200
    assert consent.json()["granted"] == ["record"]
    for _ in range(2):
        resumed = client.get(path)
        assert resumed.status_code == 200
        assert resumed.json()["pending_questions"] == expected
        assert resumed.json()["transcript"] == []
        assert resumed.json()["granted_consent_scopes"] == ["record"]
    invalid = client.post(
        f"{path}/voice?question_id=first_memory",
        content=b"not-admitted",
        headers={"Content-Type": "audio/webm", "Content-Length": "invalid"},
    )
    assert invalid.status_code == 400
    assert invalid.json() == {"detail": "invalid Content-Length"}
    forbidden.assert_not_called()


def test_other_invitation_starts_with_its_own_unanswered_question(client: TestClient) -> None:
    response = client.post("/speak/projects", json={"title": "Synthetic shared-story fixture"})
    assert response.status_code == 201
    first = _invite(client, response.json()["project_id"])
    second = _invite(client, response.json()["project_id"])
    assert first != second
    assert client.post(f"{first}/consent", json={"scopes": ["record"]}).status_code == 200
    a, b = client.get(first).json(), client.get(second).json()
    assert a["interview_id"] != b["interview_id"]
    assert a["pending_questions"] == b["pending_questions"]
    assert len(b["pending_questions"]) == 1
    assert b["granted_consent_scopes"] == []
    assert b["transcript"] == []


@pytest.mark.parametrize(
    "guide", [None, {"must_cover": [{"id": "custom", "text": "An existing guide"}]}]
)
def test_landing_does_not_backfill_or_replace_existing_guides(
    client: TestClient, guide: dict[str, list[dict[str, str]]] | None
) -> None:
    with connect_write(default_db_path(), purpose="speak/test:existing-guide") as con:
        existing = project.create_project(
            con, title="Synthetic existing-guide fixture", interview_guide=guide
        )
    path = _invite(client, existing.project_id)
    expected = [] if guide is None else guide["must_cover"]
    for _ in range(2):
        landing = client.get(path)
        assert landing.status_code == 200
        assert landing.json()["pending_questions"] == expected
        assert landing.json()["transcript"] == []
    with connect_read(default_db_path()) as con:
        row = con.execute(
            "SELECT interview_guide FROM interview_projects WHERE project_id = ?",
            [existing.project_id],
        ).fetchone()
    assert row is not None
    assert (None if row[0] is None else json.loads(row[0])) == guide


def test_unauthenticated_creation_is_still_refused(client: TestClient) -> None:
    client.cookies.clear()
    assert client.post("/speak/projects", json={"title": "Unadmitted fixture"}).status_code == 401
