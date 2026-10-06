"""An active takedown must revoke capabilities that were already issued.

Checking takedown at MINT time stops future issuance. It leaves every token already in
circulation working, so a withdrawn subject stayed reachable through the landing this
route serves. Reported by the adversarial review of that fix:

    "takedown does not revoke existing open-contribution tokens; the unauthenticated
     landing still returns the withdrawn subject after takedown."

The sibling module puts the principle plainly: "A takedown that does not take the subject
down is not a takedown." This route is the landing; the mint path was fixed first and this
one was not, which is the difference between withdrawing a listing and withdrawing access.
"""

from __future__ import annotations

import os
import tempfile
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from interfaces.research.api.app import create_app

_OPERATOR_TOKEN = "test-operator-token"


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    tmpdir = tempfile.mkdtemp(prefix="speak-takedown-revokes-")
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", os.path.join(tmpdir, "t.duckdb"))
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", os.path.join(tmpdir, "events"))
    monkeypatch.setenv("ANTIEK_SPEAK_PUBLIC_ECOSYSTEM", "1")
    # The env var is the EXPECTED token; the header PRESENTS it. Both are required.
    monkeypatch.setenv("ANTIEK_OPERATOR_TOKEN", _OPERATOR_TOKEN)
    with TestClient(
        create_app(register_wrestling=False),
        headers={"Authorization": f"Bearer {_OPERATOR_TOKEN}"},
    ) as c:
        yield c


def _public_project(client: TestClient, subject: str) -> str:
    resp = client.post(
        "/speak/projects",
        json={"title": "T", "subject_ref": subject, "publish_intent": "will_be_public"},
    )
    assert resp.status_code in (200, 201), resp.text
    return str(resp.json()["project_id"])


def _take_down(client: TestClient, pid: str, subject: str) -> None:
    resp = client.post(
        f"/speak/projects/{pid}/takedowns",
        json={"target_kind": "subject", "target_id": subject,
              "requested_by": subject, "reason": "subject withdrew"},
    )
    assert resp.status_code == 201, resp.text


def test_a_token_issued_before_a_takedown_stops_resolving_after_it(client: TestClient) -> None:
    """The property: withdrawal reaches tokens already in circulation."""
    subject = "withdrawn@example.test"
    pid = _public_project(client, subject)

    minted = client.post(f"/speak/projects/{pid}/open-contribute", json={})
    assert minted.status_code == 201, minted.text
    token = minted.json()["token"]

    # Control: the token works before the takedown, so the assertion below is about the
    # takedown and not about a token that never worked.
    assert client.get("/speak/invites/resolve", params={"token": token}).status_code == 200

    _take_down(client, pid, subject)

    after = client.get("/speak/invites/resolve", params={"token": token})
    assert after.status_code == 404, (
        "a capability issued before the takedown still resolves, so the withdrawn "
        f"subject remains reachable: {after.status_code} {after.text[:160]}"
    )


def test_an_unknown_token_answers_the_same_way(client: TestClient) -> None:
    """Same status AND same message: a takedown must not announce that the project existed."""
    subject = "quiet@example.test"
    pid = _public_project(client, subject)
    token = client.post(f"/speak/projects/{pid}/open-contribute", json={}).json()["token"]
    _take_down(client, pid, subject)

    withdrawn = client.get("/speak/invites/resolve", params={"token": token})
    unknown = client.get("/speak/invites/resolve", params={"token": "not-a-real-token"})

    assert withdrawn.status_code == unknown.status_code
    assert withdrawn.json() == unknown.json()
