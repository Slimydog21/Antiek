"""Authenticated product reads must preserve authorized inspection, not just deny."""
from __future__ import annotations

import json

import pytest

from runtime.db_lock import connect_write
from substrate.graph.insight_question import promote_insight, promote_question
from substrate.graph.ops import insert_document
from substrate.graph.schema import init_database_at_path

BODY = "The factory makes 100 parts daily."


@pytest.fixture
def boundary_env(tmp_path, monkeypatch):
    db = str(tmp_path / "boundary.duckdb")
    events = str(tmp_path / "events")
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", db)
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", events)
    monkeypatch.setenv("ANTIEK_EMBEDDING_PROVIDER", "hash")
    init_database_at_path(db)
    return db, events


def seed_document(db, document_id, owner, content_class="public_domain", *, metadata=None):
    with connect_write(db, purpose="test/boundary-source") as con:
        insert_document(
            con, document_id=document_id, source_tier=2, document_type="web",
            title=document_id, raw_text=BODY, content_class=content_class,
            owner_user_id=owner, metadata=metadata,
        )
        con.execute(
            "INSERT INTO chunks(chunk_id, document_id, chunk_index, text, token_count) "
            "VALUES (?, ?, 0, ?, 7)", [document_id + "-chunk", document_id, BODY],
        )


def seed_product(inv, node_owner, source, *, question=False):
    promote = promote_question if question else promote_insight
    return promote(
        text="The production evidence for " + inv + str(node_owner) + str(source),
        investigation_id=inv, source_document_id=source, owner_user_id=node_owner,
    )




@pytest.mark.parametrize(
    "case,products,expected_counts",
    [
        ("same-owner", [("alice", "alice", "personal_reading")], (1, 0)),
        ("nonexistent", [], (0, 0)),
        ("foreign-private", [("bob", "bob", "personal_reading")], (0, 1)),
        ("mixed-owner", [("alice", "alice", "personal_reading"), ("bob", "bob", "personal_reading")], (1, 1)),
        ("shared-public", [(None, "bob", "public_domain")], (1, 1)),
        ("legacy-private", [(None, "bob", "personal_reading")], (0, 1)),
        ("legacy-unknown", [(None, "bob", None)], (0, 0)),
        ("owned-node-foreign-source", [("alice", "bob", "personal_reading")], (0, 0)),
    ],
)
def test_distill_as_both_authenticated_owners(
    boundary_env, monkeypatch, case, products, expected_counts,
):
    from fastapi.testclient import TestClient

    from interfaces.research.api.app import create_app
    from substrate.auth import mint_session_cookie

    db, events = boundary_env
    monkeypatch.setenv("ANTIEK_AUTH_SECRET", "d6-hermetic-signing-secret-not-a-credential")
    monkeypatch.setenv("ANTIEK_OPERATOR_EMAIL", "alice@example.test,bob@example.test")
    monkeypatch.delenv("ANTIEK_OPERATOR_TOKEN", raising=False)
    for caller in ("alice", "bob"):
        seed_document(db, "base-" + caller, caller)
    node_ids = []
    for index, (node_owner, source_owner, content_class) in enumerate(products):
        source = f"support-{index}"
        if content_class:
            seed_document(db, source, source_owner, content_class)
        node_ids.append(seed_product(case, node_owner, source, question=index == 1))
    app = create_app(register_wrestling=False, register_providers=False, cors_origins=[])
    anonymous = TestClient(app)
    assert anonymous.get(f"/research/{case}/distill").status_code == 401
    observed = []
    for caller in ("alice", "bob"):
        client = TestClient(app)
        client.cookies.set("ANTIEK_SESSION", mint_session_cookie(
            user_id=caller, email=caller + "@example.test",
        ))
        identity = client.get("/auth/me")
        assert identity.status_code == 200
        assert identity.json()["user_id"] == caller
        response = client.get(f"/research/{case}/distill")
        assert response.status_code == 200
        sources = []
        for source_index, (_, source_owner, content_class) in enumerate(products):
            source = f"support-{source_index}"
            metadata = client.get(f"/books/{source}")
            full_text = client.get(f"/books/{source}/full-text")
            passage = client.get(
                f"/books/{source}/passage?chunk_id={source}-chunk&start_scalar=0&end_scalar=34"
            )
            sources.append({
                "source": source, "metadata_status": metadata.status_code,
                "public_body": full_text.json().get("full_text"),
                "passage_status": passage.status_code, "passage_body": passage.json().get("text"),
            })
            if content_class and source_owner == caller:
                assert passage.status_code == 200
                assert passage.json()["text"] == BODY
            else:
                assert passage.status_code == 404
            if content_class == "public_domain":
                assert full_text.json()["full_text"] == BODY
            else:
                assert full_text.json().get("full_text") is None
        observed.append({
            "case": case, "caller": caller, "identity": identity.json(),
            "distill_status": response.status_code, "distill": response.json(),
            "sources": sources,
        })
        print("API_BOUNDARY", json.dumps(observed[-1], sort_keys=True))
    # Check after both requests so a regression still records the authorized run.
    for index, record in enumerate(observed):
        nodes = record["distill"]["insights"] + record["distill"]["questions"]
        assert len(nodes) == expected_counts[index]
        for node in nodes:
            assert node["node_id"] in node_ids
            assert node["text"].startswith("The production evidence for " + case)
        for node_index, (node_owner, _, _) in enumerate(products):
            if node_owner not in (None, record["caller"]):
                assert node_ids[node_index] not in json.dumps(record["distill"])


@pytest.mark.parametrize("route", ["artifact/twin-notes.html"])
@pytest.mark.parametrize("receipt_owner,start_owner", [
    ("bob", "bob"), ("alice", "bob"), ("bob", None), (None, "bob"), ("bob", "conflicting"),
])
def test_html_artifact_graph_and_opaque_fields_are_owner_scoped(
    boundary_env, monkeypatch, tmp_path, route, receipt_owner, start_owner,
):
    from fastapi.testclient import TestClient

    from interfaces.research.api.app import create_app
    from substrate.auth import mint_session_cookie
    from substrate.event_log import log_event
    from substrate.research_artifact.paths import artifact_path_for, artifact_source_path_for
    from substrate.research_artifact.render import render_html
    from substrate.research_artifact.schema import ResearchArtifactBody
    from substrate.research_artifact.store import ResearchArtifactStore

    db, events = boundary_env
    monkeypatch.setenv("ANTIEK_AUTH_SECRET", "d6-hermetic-signing-secret-not-a-credential")
    monkeypatch.setenv("ANTIEK_OPERATOR_EMAIL", "alice@example.test,bob@example.test")
    monkeypatch.setenv("ANTIEK_RESEARCH_ARTIFACTS_DIR", str(tmp_path / "artifacts"))
    monkeypatch.delenv("ANTIEK_OPERATOR_TOKEN", raising=False)
    seed_document(db, "secret-source", "bob", "personal_reading")
    seed_product("private-artifact", "bob", "secret-source")
    question = "QUESTION_SECRET_81327"
    synthesis = "SYNTHESIS_SECRET_59261"
    note = "AGENT_NOTE_SECRET_37489"
    log_event("private-artifact", "investigation.start_requested",
              payload={"question": question, "owner_user_id": "bob" if start_owner == "conflicting" else start_owner}, events_dir=events)
    if start_owner == "conflicting":
        log_event("private-artifact", "investigation.start_requested",
                  payload={"question": "another launch", "owner_user_id": "alice"}, events_dir=events)
    log_event("private-artifact", "investigation.completed",
              payload={"thesis_summary": synthesis}, events_dir=events)
    body = ResearchArtifactBody(
        investigation_id="private-artifact", problem_question=question,
        synthesis_excerpt=synthesis, agent_notes=[note],
    )
    raw = render_html(body).encode()
    path = artifact_path_for("private-artifact")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(raw)
    import hashlib

    source_path = artifact_source_path_for("private-artifact", hashlib.sha256(raw).hexdigest())
    if receipt_owner is not None:
        ResearchArtifactStore(db).save_source(
            "private-artifact", "private-artifact", receipt_owner, source_path, raw,
        )
    app = create_app(register_wrestling=False, register_providers=False, cors_origins=[])
    observed = []
    for caller in ("alice", "bob"):
        client = TestClient(app)
        client.cookies.set("ANTIEK_SESSION", mint_session_cookie(
            user_id=caller, email=caller + "@example.test",
        ))
        identity = client.get("/auth/me").json()
        assert identity["user_id"] == caller
        response = client.get(f"/research/private-artifact/{route}")
        passage = client.get(
            "/books/secret-source/passage?chunk_id=secret-source-chunk&start_scalar=0&end_scalar=34"
        )
        record = {
            "route": route, "caller": caller, "receipt_owner": receipt_owner,
            "start_owner": start_owner, "status": response.status_code,
            "graph_visible": "The production evidence for private-artifactbobsecret-source" in response.text,
            "question_visible": question in response.text,
            "synthesis_visible": synthesis in response.text,
            "note_visible": note in response.text,
            "passage_status": passage.status_code, "passage_body": passage.json().get("text"),
        }
        print("HTML_BOUNDARY", json.dumps(record, sort_keys=True))
        observed.append(record)
    # Assert after both requests so failures preserve the authorized run too.
    for record in observed:
        assert record["status"] == 200
        assert record["graph_visible"] is (record["caller"] == "bob")
        opaque_allowed = record["caller"] == receipt_owner == start_owner == "bob"
        for field in ("question_visible", "synthesis_visible", "note_visible"):
            assert record[field] is opaque_allowed
        assert record["passage_status"] == (200 if record["caller"] == "bob" else 404)
        assert record["passage_body"] == (BODY if record["caller"] == "bob" else None)
