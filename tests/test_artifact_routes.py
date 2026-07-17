"""ANT-AHT — research artifact HTTP routes."""

from __future__ import annotations

import os
import tempfile

import pytest
from fastapi.testclient import TestClient

from interfaces.research.api.app import create_app
from substrate.event_log import log_event
from substrate.graph import ensure_initialized
from substrate.graph.insight_question import promote_insight
from substrate.schemas import ActionType


@pytest.fixture
def api_env(monkeypatch):
    tmpdir = tempfile.mkdtemp(prefix="ra-api-")
    db = os.path.join(tmpdir, "t.duckdb")
    events = os.path.join(tmpdir, "events")
    arts = os.path.join(tmpdir, "artifacts")
    os.makedirs(events, exist_ok=True)
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", db)
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", events)
    monkeypatch.setenv("ANTIEK_RESEARCH_ARTIFACTS_DIR", arts)
    monkeypatch.setenv("ANTIEK_EMBEDDING_PROVIDER", "hash")
    ensure_initialized(db)
    return {"db": db, "events": events, "arts": arts}


def _client():
    return TestClient(create_app(register_wrestling=False))


def test_post_export_artifact(api_env):
    promote_insight(
        text="API export insight.",
        investigation_id="inv-api",
        confidence="moderate",
        source_document_id="doc-1",
    )
    client = _client()
    resp = client.post("/research/inv-api/artifact/export")
    assert resp.status_code == 200
    body = resp.json()
    assert body["investigation_id"] == "inv-api"
    assert body["path"]
    assert body["content_hash"]
    assert body["size_bytes"] > 0
    assert os.path.isfile(body["path"])


def test_get_artifact_blocks_empty(api_env):
    client = _client()
    resp = client.get("/research/inv-empty/artifact/blocks")
    assert resp.status_code == 200
    body = resp.json()
    assert body["investigation_id"] == "inv-empty"
    assert body["blocks"] == []


def test_get_artifact_blocks_after_insight(api_env):
    promote_insight(
        text="Outline block source.",
        investigation_id="inv-blocks",
        confidence="high",
        source_document_id="doc-2",
    )
    client = _client()
    resp = client.get("/research/inv-blocks/artifact/blocks")
    assert resp.status_code == 200
    blocks = resp.json()["blocks"]
    assert len(blocks) >= 1
    assert blocks[0]["investigation_id"] == "inv-blocks"
    assert blocks[0]["kind"] in ("insight", "question", "synthesis")


def _terminal(iid: str, action: ActionType, payload=None):
    log_event(iid, action, payload=payload or {}, role="user_agent")


@pytest.mark.parametrize(
    "ids,events",
    [
        (["inv-a"], []),
        ([f"inv-{i}" for i in range(9)], []),
        (["inv-a", "inv-a"], []),
        ([" inv-a", "inv-b"], []),
        (["inv-a", "inv-missing"], [("inv-a", ActionType.INVESTIGATION_COMPLETED, {})]),
        (["inv-a", "inv-running"], [("inv-a", ActionType.INVESTIGATION_COMPLETED, {})]),
        (["inv-a", "inv-failed"], [("inv-a", ActionType.INVESTIGATION_COMPLETED, {}), ("inv-failed", ActionType.INVESTIGATION_FAILED, {})]),
        (["inv-a", "inv-stopped"], [("inv-a", ActionType.INVESTIGATION_COMPLETED, {}), ("inv-stopped", ActionType.INVESTIGATION_COMPLETED, {"outcome": "stopped"})]),
        (["inv-a", "inv-restarted"], [
            ("inv-a", ActionType.INVESTIGATION_COMPLETED, {}),
            ("inv-restarted", ActionType.INVESTIGATION_COMPLETED, {}),
            ("inv-restarted", ActionType.INVESTIGATION_START_REQUESTED, {"question": "Try again"}),
        ]),
    ],
)
def test_compose_rejects_entire_invalid_basket_before_export(api_env, monkeypatch, ids, events):
    for iid, action, payload in events:
        _terminal(iid, action, payload)
    called = False

    def forbidden(*args, **kwargs):
        nonlocal called
        called = True
        raise AssertionError("compose side effect ran")

    monkeypatch.setattr("interfaces.research.api.artifact_routes.compose_artifacts", forbidden)
    response = _client().post("/research/artifacts/compose", json={"investigation_ids": ids})
    assert response.status_code in (409, 422)
    assert called is False


def test_compose_returns_ordered_path_free_artifact_index(api_env, monkeypatch):
    from types import SimpleNamespace

    for iid in ("inv-b", "inv-a"):
        _terminal(iid, ActionType.INVESTIGATION_COMPLETED)

    monkeypatch.setattr(
        "interfaces.research.api.artifact_routes.compose_artifacts",
        lambda ids, **kwargs: SimpleNamespace(
            members=[
                SimpleNamespace(investigation_id=iid, content_hash=hash_value, artifact_path="/secret")
                for iid, hash_value in (("inv-b", "b" * 64), ("inv-a", "b" * 64))
            ],
            hash_conflicts=[("inv-b", "inv-a")],
            path="/secret/index.html",
            composition_id="c" * 64,
            composition_version=1,
        ),
    )
    monkeypatch.setattr(
        "interfaces.research.api.artifact_routes.problem_question_from_events",
        lambda iid: f"Question {iid}",
    )
    monkeypatch.setattr(
        "interfaces.research.api.artifact_routes.list_outline_blocks",
        lambda iid, **kwargs: [
            SimpleNamespace(node_id=f"node-{iid}", kind="insight", label=f"Block {iid}", investigation_id=iid, artifact_path="/secret")
        ],
    )

    response = _client().post(
        "/research/artifacts/compose",
        json={"investigation_ids": ["inv-b", "inv-a"]},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["kind"] == "artifact_index"
    assert body["composition_id"] == "c" * 64
    assert body["composition_version"] == 1
    assert [member["investigation_id"] for member in body["members"]] == ["inv-b", "inv-a"]
    assert body["conflicts"] == [{
        "first_investigation_id": "inv-b",
        "second_investigation_id": "inv-a",
        "content_hash": "b" * 64,
    }]
    assert "secret" not in response.text
    assert "html" not in response.text.lower()


def test_composition_identity_binds_order_and_content_hash():
    from pathlib import Path

    from substrate.research_artifact.compose import ComposeMember, composition_identity

    first = ComposeMember("inv-a", "a" * 64, Path("/unused/a"))
    second = ComposeMember("inv-b", "b" * 64, Path("/unused/b"))

    identity = composition_identity([first, second])
    assert len(identity) == 64
    assert identity == composition_identity([first, second])
    assert identity != composition_identity([second, first])
    assert identity != composition_identity([
        first,
        ComposeMember("inv-b", "c" * 64, Path("/unused/b")),
    ])
