"""Export cannot mint an owner receipt for another caller's investigation."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from interfaces.research.api.app import create_app
from runtime.db_lock import connect_write
from substrate.auth import mint_session_cookie
from substrate.event_log import log_event, trajectory
from substrate.graph import default_db_path
from substrate.graph.insight_question import promote_insight
from substrate.graph.ops import insert_document
from substrate.research_artifact.paths import research_artifacts_dir
from substrate.research_artifact.store import ResearchArtifactStore

PRIVATE = "BOB_PRIVATE_EXPORT_42891"


@pytest.fixture
def export_clients(monkeypatch, tmp_path):
    monkeypatch.setenv("ANTIEK_AUTH_SECRET", "export-hermetic-test-signing-secret")
    monkeypatch.setenv("ANTIEK_OPERATOR_EMAIL", "alice@example.test,bob@example.test")
    monkeypatch.delenv("ANTIEK_OPERATOR_TOKEN", raising=False)
    monkeypatch.setenv("ANTIEK_RESEARCH_ARTIFACTS_DIR", str(tmp_path / "artifacts"))
    monkeypatch.setenv("ANTIEK_EMBEDDING_PROVIDER", "hash")
    app = create_app(register_wrestling=False, register_providers=False, cors_origins=[])
    clients = {"anonymous": TestClient(app)}
    for caller in ("alice", "bob"):
        client = TestClient(app)
        client.cookies.set("ANTIEK_SESSION", mint_session_cookie(
            user_id=caller, email=caller + "@example.test",
        ))
        identity = client.get("/auth/me")
        assert identity.status_code == 200
        assert identity.json()["user_id"] == caller
        clients[caller] = client
    return clients


def seed_investigation(inv, *, owner="bob", node_owner="bob", source_owner="bob",
                       content_class="personal_reading", starts=True):
    with connect_write(default_db_path(), purpose="test/export-ownership") as con:
        insert_document(
            con, document_id=inv + "-source", source_tier=2, document_type="web",
            title="Private source", raw_text=PRIVATE, owner_user_id=source_owner,
            content_class=content_class,
        )
    promote_insight(
        text=PRIVATE + " finding " + inv, investigation_id=inv,
        source_document_id=inv + "-source", owner_user_id=node_owner,
    )
    if starts:
        log_event(inv, "investigation.start_requested", payload={
            "question": PRIVATE + " question", "owner_user_id": owner,
        })
    log_event(inv, "investigation.completed", payload={"thesis_summary": PRIVATE + " synthesis"})


def artifact_files():
    return {str(path): path.read_bytes() for path in research_artifacts_dir().rglob("*")
            if path.is_file()}


def spoof_request(surface, owner):
    spoof = {"owner_user_id": owner, "user_id": owner, "owner": "true"}
    return {
        "none": {}, "body": {"json": spoof}, "query": {"params": spoof},
        "header": {"headers": {"X-User-Id": owner, "X-Owner-User-Id": owner}},
    }[surface]


def observe_export(client, caller, inv, **kwargs):
    store = ResearchArtifactStore(default_db_path())
    before_record = store.get(inv)
    before_files, before_events = artifact_files(), trajectory(inv)
    response = client.post(f"/research/{inv}/artifact/export", **kwargs)
    record = store.get(inv)
    raw = record.source_path.read_bytes() if record is not None else b""
    observation = {
        "caller": caller, "investigation": inv, "status": response.status_code,
        "body": response.json(), "owner_before": before_record.owner_user_id if before_record else None,
        "receipt_owner": record.owner_user_id if record else None,
        "receipt_investigation": record.investigation_id if record else None,
        "stored_private_marker": PRIVATE.encode() in raw,
        "stored_sha256": hashlib.sha256(raw).hexdigest(),
        "files_unchanged": artifact_files() == before_files,
        "events_unchanged": trajectory(inv) == before_events,
    }
    print("EXPORT_BOUNDARY", json.dumps(observation, sort_keys=True))
    return response, record, raw, observation


def assert_denied(result, *, status=403):
    response, record, raw, observation = result
    assert response.status_code == status
    assert PRIVATE not in response.text
    assert record is None
    assert raw == b""
    assert observation["files_unchanged"]
    assert observation["events_unchanged"]


def assert_owner_export(result, inv):
    response, record, raw, _ = result
    assert response.status_code == 200
    assert record is not None
    assert record.owner_user_id == "bob"
    assert record.investigation_id == inv
    assert str(record.source_path) == response.json()["path"]
    assert PRIVATE.encode() in raw
    assert (PRIVATE + " question").encode() in raw
    assert (PRIVATE + " synthesis").encode() in raw
    assert record.source_hash == hashlib.sha256(raw).hexdigest()
    assert response.json()["size_bytes"] == len(raw)
    assert PRIVATE in Path(response.json()["twin_notes_path"]).read_text()
    event = next(row for row in trajectory(inv) if row["event_id"] == response.json()["event_id"])
    assert event["action_type"] == "artifact.generated"
    assert event["payload"]["artifact_path"] == str(record.source_path)


@pytest.mark.parametrize("surface", ["none", "body", "query", "header"])
def test_export_denies_foreign_receipt_and_preserves_true_owner(export_clients, surface):
    observations = {}
    # Separate fresh targets prove the true owner's first export even if an
    # attacker captured the first artifact ID on the unfixed implementation.
    for caller in ("anonymous", "alice", "bob"):
        inv = f"export-{surface}-{caller}"
        seed_investigation(inv)
        spoof = "alice" if caller == "bob" else "bob"
        observations[caller] = observe_export(
            export_clients[caller], caller, inv, **spoof_request(surface, spoof),
        )
    assert_owner_export(observations["bob"], f"export-{surface}-bob")
    assert_denied(observations["anonymous"], status=401)
    assert_denied(observations["alice"])


def test_denied_export_cannot_claim_id_before_owner_and_retry(export_clients):
    inv = "export-first-writer"
    seed_investigation(inv)
    attacker = observe_export(export_clients["alice"], "alice", inv)
    owner = observe_export(export_clients["bob"], "bob", inv)
    assert_owner_export(owner, inv)
    assert_denied(attacker)
    repeated = observe_export(export_clients["bob"], "bob", inv)
    assert_owner_export(repeated, inv)
    before_files, before_events = artifact_files(), trajectory(inv)
    denied_retry = export_clients["alice"].post(f"/research/{inv}/artifact/export")
    assert denied_retry.status_code == 403
    assert artifact_files() == before_files
    assert trajectory(inv) == before_events
    assert ResearchArtifactStore(default_db_path()).get(inv) == repeated[1]


@pytest.mark.parametrize("owner", [None, "", "   ", "__operator__", "shared", "conflicting", "missing"])
def test_unknown_or_conflicting_start_owner_cannot_mint_receipt(export_clients, owner):
    inv = "export-unknown"
    seed_investigation(inv, owner="bob" if owner == "conflicting" else owner,
                       starts=owner != "missing")
    if owner == "conflicting":
        log_event(inv, "investigation.start_requested", payload={
            "question": "conflicting start", "owner_user_id": "alice",
        })
    assert_denied(observe_export(export_clients["bob"], "bob", inv))


@pytest.mark.parametrize("node_owner,source_owner,content_class", [
    ("alice", "alice", "personal_reading"),
    ("bob", "alice", "personal_reading"),
    (None, "alice", "personal_reading"),
])
def test_owned_start_does_not_authorize_foreign_graph_body(
    export_clients, node_owner, source_owner, content_class,
):
    inv = "export-mixed-graph"
    seed_investigation(inv, node_owner=node_owner, source_owner=source_owner,
                       content_class=content_class)
    assert_denied(observe_export(export_clients["bob"], "bob", inv))


def test_owned_start_can_export_publicly_servable_shared_graph(export_clients):
    inv = "export-public-graph"
    seed_investigation(inv, node_owner=None, source_owner="alice", content_class="public_domain")
    assert_owner_export(observe_export(export_clients["bob"], "bob", inv), inv)
