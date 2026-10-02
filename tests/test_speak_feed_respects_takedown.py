"""The public feed must not keep disclosing a project under takedown.

``GET /speak/feed`` is unauthenticated (the operator gate opens it) and
returns ``subject_ref`` and ``subject_status`` for every project whose
``publish_intent`` is ``will_be_public``. Its WHERE clause carried that one
predicate and nothing else.

``substrate/speak/publish_gate.py:162`` refuses to publish a project with an
active takedown. So the gate that governs publishing said stop, while the
browsable surface it governs kept serving the subject's identifier to anyone
who asked. A takedown that does not take the subject down is not a takedown.

Scope note: this fixes the takedown half only. The same gate also requires
recorded subject consent (`publish_gate.py` step 3, deny-by-default, an
unrecorded subject treated as living), and the feed does not check that
either. Whether an unconsented project should be hidden entirely, listed
without `subject_ref`, or left as-is is a product and legal decision, not a
bug fix, so it is deliberately NOT changed here — see the PR for the
question. A takedown, by contrast, has exactly one possible meaning.
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
    tmpdir = tempfile.mkdtemp(prefix="speak-feed-takedown-")
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", os.path.join(tmpdir, "t.duckdb"))
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", os.path.join(tmpdir, "events"))
    with TestClient(create_app(register_wrestling=False)) as c:
        yield c


def _public_project(client: TestClient, title: str, subject: str) -> str:
    resp = client.post(
        "/speak/projects",
        json={
            "title": title,
            "subject_ref": subject,
            "publish_intent": "will_be_public",
        },
    )
    assert resp.status_code in (200, 201), resp.text
    return str(resp.json()["project_id"])


def test_taken_down_project_leaves_the_public_feed(client: TestClient) -> None:
    pid = _public_project(client, "Under takedown", "jane.doe@example.test")

    feed = client.get("/speak/feed").json()
    assert feed["count"] == 1, "precondition: the project should start visible"
    assert feed["projects"][0]["subject_ref"] == "jane.doe@example.test"

    resp = client.post(
        f"/speak/projects/{pid}/takedowns",
        json={
            "target_kind": "subject",
            "target_id": "jane.doe@example.test",
            "requested_by": "jane.doe@example.test",
            "reason": "subject withdrew",
        },
    )
    assert resp.status_code == 201, resp.text

    feed = client.get("/speak/feed").json()
    assert feed["count"] == 0, (
        "a project under an active takedown is still on the unauthenticated "
        f"public feed, still disclosing its subject: {feed['projects']}"
    )


def test_unaffected_public_project_stays_visible(client: TestClient) -> None:
    """The predicate must exclude the taken-down project and nothing else."""
    _public_project(client, "Fine one", "someone@example.test")
    pid = _public_project(client, "Under takedown", "other@example.test")
    client.post(
        f"/speak/projects/{pid}/takedowns",
        json={
            "target_kind": "subject",
            "target_id": "other@example.test",
            "requested_by": "other@example.test",
            "reason": "withdrew",
        },
    )
    feed = client.get("/speak/feed").json()
    titles = {p["title"] for p in feed["projects"]}
    assert titles == {"Fine one"}, titles
