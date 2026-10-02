"""A withdrawn project must not mint capabilities from an unauthenticated route.

Measured before the fix, with a synthetic project and no credentials:

    TAKEDOWN_FILTER  /speak/feed           200  False     <- removed from listings
    TAKEDOWN_FILTER  /speak/opportunities  200  False     <- removed from listings
    TAKEDOWN_MINT    .../open-contribute   201  [invite]  <- STILL MINTED
    TAKEDOWN_LANDING                       200  private-subject@example.invalid

A takedown removed the project from every public listing and left the capability path open, so
anyone who had learned a previously public project id could mint a fresh invite and read the
withdrawn subject. No guessing of a token was required.

The predicate already existed on both browse surfaces --
`interfaces/research/api/speak_routes.py:493` and `substrate/speak/pushes.py:232` -- and the browse
code states the principle it is applying: "the browsable surface has to agree with the gate that
governs it". This is the surface that did not.
"""

from __future__ import annotations

import os
import tempfile
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from interfaces.research.api.app import create_app


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    tmpdir = tempfile.mkdtemp(prefix="speak-open-contribute-takedown-")
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", os.path.join(tmpdir, "t.duckdb"))
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", os.path.join(tmpdir, "events"))
    monkeypatch.setenv("ANTIEK_SPEAK_PUBLIC_ECOSYSTEM", "1")
    # Creating a project needs an operator token; the feed and open-contribute do not.
    # Without this the fixture 401s on setup and every assertion here is about the wrong
    # thing -- which is exactly how the two sibling tests in this directory fail on this
    # machine, for the same environmental reason rather than a product defect.
    monkeypatch.setenv("ANTIEK_OPERATOR_TOKEN", "test-operator-token")
    # The env var is the EXPECTED token and the header PRESENTS it; both are needed.
    with TestClient(
        create_app(register_wrestling=False),
        headers={"Authorization": "Bearer test-operator-token"},
    ) as c:
        yield c


def _public_project(client: TestClient, title: str, subject: str) -> str:
    resp = client.post(
        "/speak/projects",
        json={"title": title, "subject_ref": subject, "publish_intent": "will_be_public"},
    )
    assert resp.status_code in (200, 201), resp.text
    return str(resp.json()["project_id"])


def _take_down(client: TestClient, pid: str, subject: str) -> None:
    resp = client.post(
        f"/speak/projects/{pid}/takedowns",
        json={
            "target_kind": "subject",
            "target_id": subject,
            "requested_by": subject,
            "reason": "subject withdrew",
        },
    )
    assert resp.status_code == 201, resp.text


def test_a_live_public_project_can_still_mint(client: TestClient) -> None:
    """The control. The predicate must exclude takedowns and nothing else."""
    pid = _public_project(client, "Still public", "still@example.test")

    resp = client.post(f"/speak/projects/{pid}/open-contribute", json={})

    assert resp.status_code == 201, resp.text


def test_a_taken_down_project_cannot_mint(client: TestClient) -> None:
    pid = _public_project(client, "Under takedown", "withdrawn@example.test")
    _take_down(client, pid, "withdrawn@example.test")

    resp = client.post(f"/speak/projects/{pid}/open-contribute", json={})

    assert resp.status_code != 201, (
        "a project under an active takedown still minted an invite from an "
        f"unauthenticated route: {resp.status_code} {resp.text[:200]}"
    )
