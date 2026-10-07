"""Signed HTTP controls for the generic event writer's authority boundary."""
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from interfaces.research.api.app import create_app
from substrate.auth import mint_session_cookie
from substrate.event_log import log_event, trajectory
from substrate.graph import default_db_path
from substrate.research_artifact.paths import research_artifacts_dir
from substrate.research_artifact.store import ResearchArtifactStore


@pytest.fixture
def client(monkeypatch, tmp_path):
    monkeypatch.setenv("ANTIEK_AUTH_SECRET", "typed-authority-hermetic-secret")
    monkeypatch.setenv("ANTIEK_OPERATOR_EMAIL", "alice@example.test,bob@example.test")
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", str(tmp_path / "events"))
    monkeypatch.setenv("ANTIEK_RESEARCH_ARTIFACTS_DIR", str(tmp_path / "artifacts"))
    monkeypatch.delenv("ANTIEK_OPERATOR_TOKEN", raising=False)
    monkeypatch.delenv("ANTIEK_OPERATOR_SERVICE_TOKEN_CLIENT_ID", raising=False)
    app = create_app(register_wrestling=False, register_providers=False, cors_origins=[])
    app.state.broadcaster.broadcast = AsyncMock(wraps=app.state.broadcaster.broadcast)
    result = TestClient(app)
    result.cookies.set("ANTIEK_SESSION", mint_session_cookie(
        user_id="alice", email="alice@example.test",
    ))
    assert result.get("/auth/me").json()["user_id"] == "alice"
    return result


def _assert_unknown_owner_export_refused(client, inv):
    files = {
        str(path): path.read_bytes() for path in research_artifacts_dir().rglob("*")
        if path.is_file()
    }
    existing = trajectory(inv)
    store = ResearchArtifactStore(default_db_path())
    assert store.get(inv) is None
    response = client.post(f"/research/{inv}/artifact/export")
    assert response.status_code == 403, response.text
    assert response.json() == {"detail": "investigation export access withheld"}
    assert store.get(inv) is None
    assert trajectory(inv) == existing
    assert {
        str(path): path.read_bytes() for path in research_artifacts_dir().rglob("*")
        if path.is_file()
    } == files


@pytest.mark.parametrize("ownership", [
    {"owner_user_id": "alice"},
    {"owner_user_id": "bob"},
    {"owner_user_id": None},
    {},
], ids=["alice", "bob", "null", "omitted"])
def test_generic_writer_refuses_every_start_without_append_or_broadcast(client, ownership):
    response = client.post("/events/typed", json={
        "investigation_id": "forged-start",
        "payload": {
            "action_type": "investigation.start_requested",
            "question": "Forged owner",
            **ownership,
        },
    })
    assert response.status_code == 403, response.text
    assert response.json() == {
        "detail": "investigation.start_requested is server-owned; use POST /investigations."
    }
    assert trajectory("forged-start") == []
    client.app.state.broadcaster.broadcast.assert_not_called()


def test_generic_start_cannot_turn_withheld_legacy_reader_into_disclosure(client):
    inv = "legacy-without-start"
    secret = "LEGACY_OPAQUE_SECRET_1384"
    log_event(inv, "investigation.completed", payload={"thesis_summary": secret})
    _assert_unknown_owner_export_refused(client, inv)
    before = client.get(f"/research/{inv}/artifact.html")
    assert before.status_code == 200
    assert secret not in before.text
    existing = trajectory(inv)
    client.app.state.broadcaster.broadcast.reset_mock()
    minted = client.post("/events/typed", json={
        "investigation_id": inv, "payload": {
            "action_type": "investigation.start_requested",
            "question": "My claimed investigation", "owner_user_id": "alice",
        },
    })
    after = client.get(f"/research/{inv}/artifact.html")
    assert after.status_code == 200
    assert secret not in after.text
    assert minted.status_code == 403, minted.text
    assert trajectory(inv) == existing
    client.app.state.broadcaster.broadcast.assert_not_called()
    _assert_unknown_owner_export_refused(client, inv)


def test_real_creator_keeps_its_normal_result_and_unknown_context_withheld(client):
    question = "CREATOR_PRIVATE_8193"
    response = client.post("/investigations", json={"question": question})
    assert response.status_code == 202, response.text
    body = response.json()
    inv = body["investigation_id"]
    starts = [row for row in trajectory(inv)
              if row["action_type"] == "investigation.start_requested"]
    assert len(starts) == 1
    assert starts[0]["event_id"] == body["start_event_id"]
    assert starts[0]["payload"]["question"] == question
    assert starts[0]["payload"]["owner_user_id"] is None
    secret = "CREATOR_SYNTHESIS_PRIVATE_8193"
    log_event(inv, "investigation.completed", payload={"thesis_summary": secret})
    _assert_unknown_owner_export_refused(client, inv)
    reader = client.get(f"/research/{inv}/artifact.html")
    assert reader.status_code == 200
    assert question not in reader.text
    assert secret not in reader.text


def _seed_document(document_id, owner):
    from runtime.db_lock import connect_write
    from substrate.graph import default_db_path

    with connect_write(default_db_path()) as con:
        con.execute(
            "INSERT INTO documents (document_id, source_tier, document_type, "
            "source_uri, title, owner_user_id) VALUES (?, 3, 'pdf', 'file:///t.pdf', 'Book', ?)",
            [document_id, owner],
        )


def _document_home(document_id):
    from runtime.db_lock import connect_read
    from substrate.graph import default_db_path

    with connect_read(default_db_path()) as con:
        return con.execute(
            "SELECT investigation_id FROM documents WHERE document_id = ?", [document_id],
        ).fetchone()[0]


def _filing_body(document_id="alice-doc"):
    return {
        "investigation_id": "filing-target", "document_id": document_id,
        "payload": {
            "action_type": "document.filed_into_investigation",
            "filed_document_id": document_id,
            "target_investigation_id": "filing-target",
        },
    }


@pytest.mark.parametrize("field,value", [
    ("owner_user_id", "bob"),
    ("owner_id", "bob"),
    ("owner_operation_id", "forged-operation"),
    ("owner_model_choices", {"synthesizer": {"model": "forged"}}),
    ("owner_launch_digest", "forged-digest"),
    ("owner_launch_version", 1),
    ("owner_semantic_call_id", "forged-call"),
])
@pytest.mark.parametrize("placement", ["envelope", "payload"])
def test_filing_refuses_authority_assertions_before_any_side_effect(
    client, field, value, placement,
):
    _seed_document("alice-doc", "alice")
    body = _filing_body()
    target = body if placement == "envelope" else body["payload"]
    target[field] = value
    response = client.post("/events/typed", json=body)
    assert response.status_code == 422, response.text
    error = response.json()["detail"][0]
    assert error["type"] == "extra_forbidden"
    assert error["loc"][-1] == field
    assert trajectory("filing-target") == []
    assert _document_home("alice-doc") is None
    client.app.state.broadcaster.broadcast.assert_not_called()


def test_generic_writer_refuses_schema_recognized_ownership_assertions(client):
    response = client.post("/events/typed", json={
        "investigation_id": "forged-edge",
        "payload": {
            "action_type": "graph.edge.inserted", "edge_id": "edge-forged",
            "source_node_id": "alice-node", "target_node_id": "bob-node",
            "relation": "supports", "source_tier": 3, "extraction_confidence": 0.9,
            "graph_scope": "depth", "owner_user_id": "bob",
        },
    })
    assert response.status_code == 403, response.text
    assert response.json() == {"detail": "Ownership and launch authority are server-owned."}
    assert trajectory("forged-edge") == []
    client.app.state.broadcaster.broadcast.assert_not_called()


@pytest.mark.parametrize(
    "owner", ["alice", "bob", "__operator__"], ids=["owned", "foreign", "legacy-operator"],
)
def test_filing_client_control_requires_document_owner_before_append(client, owner):
    _seed_document("selected-doc", owner)
    response = client.post("/events/typed", json=_filing_body("selected-doc"))
    if owner == "alice":
        assert response.status_code == 201, response.text
        assert response.json()["action_type"] == "document.filed_into_investigation"
        rows = trajectory("filing-target")
        assert len(rows) == 1
        assert rows[0]["event_id"] == response.json()["event_id"]
        assert _document_home("selected-doc") == "filing-target"
        client.app.state.broadcaster.broadcast.assert_awaited_once()
    else:
        assert response.status_code == 404, response.text
        assert response.json() == {"detail": "document_not_found"}
        assert trajectory("filing-target") == []
        assert _document_home("selected-doc") is None
        client.app.state.broadcaster.broadcast.assert_not_called()


@pytest.mark.parametrize("selector", ["document_id", "investigation_id"])
def test_filing_rejects_contradictory_envelope_before_append(client, selector):
    _seed_document("alice-doc", "alice")
    body = _filing_body()
    body[selector] = "foreign-selector"
    response = client.post("/events/typed", json=body)
    assert response.status_code == 422, response.text
    assert response.json() == {"detail": "Filing selectors must match the event envelope."}
    assert trajectory("foreign-selector") == []
    assert trajectory("filing-target") == []
    assert _document_home("alice-doc") is None
    client.app.state.broadcaster.broadcast.assert_not_called()


def test_filing_missing_document_refuses_before_append(client):
    response = client.post("/events/typed", json=_filing_body("missing-doc"))
    assert response.status_code == 404, response.text
    assert response.json() == {"detail": "document_not_found"}
    assert trajectory("filing-target") == []
    client.app.state.broadcaster.broadcast.assert_not_called()
