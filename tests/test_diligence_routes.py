"""Diligence-queue route proofs (autonomous-diligence SPR-01).

FastAPI TestClient against a REAL DuckDB fixture (the api_env shape from
tests/test_book_anchor_routes.py): flag → GET shows it queued; re-flag is
idempotent; dismiss transitions; the owner boundary; write-time ref
grounding (422 on ungroundable refs); the CHECK layer rejecting a bad
kind/status directly at the DB; the note cap at both layers. The auth
middleware's enforcement-disabled default stamps the single-operator
identity ("__operator__") unless a test re-keys a row at the store layer.
"""

from __future__ import annotations

import os
import tempfile

import duckdb
import pytest
from fastapi.testclient import TestClient

from interfaces.research.api.app import create_app
from runtime.db_lock import connect_write
from substrate.diligence.schema import init_diligence_schema
from substrate.graph import ensure_initialized
from substrate.graph.ops import insert_document


@pytest.fixture
def api_env(monkeypatch):
    tmpdir = tempfile.mkdtemp(prefix="diligence-api-")
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


def _client() -> TestClient:
    return TestClient(create_app(register_wrestling=False))


def _seed_graph(db: str) -> None:
    """A document + one question node + one insight node for ref grounding."""
    with connect_write(db, purpose="test/seed-diligence") as con:
        insert_document(
            con,
            document_id="doc-1",
            source_tier=2,
            document_type="book",
            title="Diligence Book",
            raw_text="A book worth flagging.",
            content_class="public_domain",
            on_conflict="ignore",
        )
        con.execute(
            "INSERT INTO nodes (node_id, canonical_label, node_type, graph_scope) "
            "VALUES ('q-1', 'an open question', 'question', 'depth'), "
            "('i-1', 'an insight', 'insight', 'depth')",
        )


def _flag_payload(**over: object) -> dict:
    body = {
        "kind": "open_question",
        "object_ref": "q-1",
        "source_investigation_id": "inv-1",
    }
    body.update(over)
    return body


# ── Proof 1: flag → queue → idempotency → dismiss → owner boundary ─────────


def test_flag_get_reflag_and_dismiss(api_env) -> None:
    db = api_env["db"]
    _seed_graph(db)
    client = _client()

    # Flag → 201, queued by default.
    created = client.post("/diligence/flags", json=_flag_payload(note="worth a look"))
    assert created.status_code == 201
    flag = created.json()
    assert flag["status"] == "queued"
    assert flag["object_ref"] == "q-1"
    assert flag["note"] == "worth a look"
    assert flag["spawned_investigation_id"] is None

    # GET shows it queued, newest first.
    queue = client.get("/diligence/queue").json()
    assert queue["count"] == 1
    assert queue["flags"][0]["flag_id"] == flag["flag_id"]
    assert queue["flags"][0]["status"] == "queued"

    # Re-flag the SAME object → 200 with the SAME row, never a duplicate.
    again = client.post("/diligence/flags", json=_flag_payload())
    assert again.status_code == 200
    assert again.json()["flag_id"] == flag["flag_id"]
    assert client.get("/diligence/queue").json()["count"] == 1

    # Dismiss → status dismissed; a second dismiss is idempotent (200).
    dismissed = client.post(f"/diligence/flags/{flag['flag_id']}/dismiss")
    assert dismissed.status_code == 200
    assert dismissed.json()["status"] == "dismissed"
    assert client.post(f"/diligence/flags/{flag['flag_id']}/dismiss").status_code == 200

    # Re-flagging AFTER a dismissal revives the SAME row to queued (the
    # gesture stays safe — still one row per object).
    revived = client.post("/diligence/flags", json=_flag_payload())
    assert revived.status_code == 200
    assert revived.json()["flag_id"] == flag["flag_id"]
    assert revived.json()["status"] == "queued"
    assert client.get("/diligence/queue").json()["count"] == 1


def test_concept_keys_normalize_and_converge(api_env) -> None:
    db = api_env["db"]
    _seed_graph(db)
    client = _client()
    first = client.post(
        "/diligence/flags", json={"kind": "concept", "object_ref": "  Dark Matter "}
    )
    assert first.status_code == 201
    assert first.json()["object_ref"] == "dark matter"
    second = client.post(
        "/diligence/flags", json={"kind": "concept", "object_ref": "dark   matter"}
    )
    assert second.status_code == 200
    assert second.json()["flag_id"] == first.json()["flag_id"]
    assert client.get("/diligence/queue").json()["count"] == 1


def test_second_owner_sees_nothing(api_env) -> None:
    db = api_env["db"]
    _seed_graph(db)
    client = _client()
    created = client.post("/diligence/flags", json=_flag_payload())
    assert created.status_code == 201
    flag_id = created.json()["flag_id"]

    # Re-key the row to another owner at the store layer (the request is
    # always the single test operator; the row's owner is what filters).
    with connect_write(db, purpose="test/rekey-owner") as con:
        con.execute(
            "UPDATE diligence_queue SET owner_user_id = 'someone-else' WHERE flag_id = ?",
            [flag_id],
        )

    assert client.get("/diligence/queue").json()["count"] == 0
    # And another owner's flag is not dismissable through this identity.
    assert client.post(f"/diligence/flags/{flag_id}/dismiss").status_code == 404


def test_ungroundable_ref_is_a_422(api_env) -> None:
    db = api_env["db"]
    _seed_graph(db)
    client = _client()

    # A distilled-node flag must name a real node of the matching type.
    missing = client.post("/diligence/flags", json=_flag_payload(object_ref="no-such-node"))
    assert missing.status_code == 422
    assert "diligence_ref_ungrounded" in missing.json()["detail"]
    # An insight flag pointing at a QUESTION node is equally ungrounded.
    wrong_type = client.post(
        "/diligence/flags", json=_flag_payload(kind="insight", object_ref="q-1")
    )
    assert wrong_type.status_code == 422
    # A lawful insight flag grounds fine.
    ok = client.post("/diligence/flags", json=_flag_payload(kind="insight", object_ref="i-1"))
    assert ok.status_code == 201
    # A source document that does not exist is refused; the real one passes.
    bad_source = client.post(
        "/diligence/flags",
        json={"kind": "concept", "object_ref": "x", "source_document_id": "no-such-doc"},
    )
    assert bad_source.status_code == 422
    assert "diligence_source_ungrounded" in bad_source.json()["detail"]
    good_source = client.post(
        "/diligence/flags",
        json={"kind": "concept", "object_ref": "x", "source_document_id": "doc-1"},
    )
    assert good_source.status_code == 201


# ── Proof 2: the CHECK layer + the note cap ────────────────────────────────


def test_check_constraints_reject_bad_kind_and_status_at_the_db(api_env) -> None:
    db = api_env["db"]
    _seed_graph(db)
    with connect_write(db, purpose="test/check-init") as con:
        init_diligence_schema(con)

    # A kind outside the vocabulary violates the CHECK directly at the DB.
    with pytest.raises(duckdb.ConstraintException), connect_write(
        db, purpose="test/bad-kind"
    ) as con:
        con.execute(
            "INSERT INTO diligence_queue (flag_id, owner_user_id, kind, object_ref) "
            "VALUES ('dfl-bad', '__operator__', 'made_up', 'q-1')",
        )
    # A status outside the lifecycle is equally rejected.
    with pytest.raises(duckdb.ConstraintException), connect_write(
        db, purpose="test/bad-status"
    ) as con:
        con.execute(
            "INSERT INTO diligence_queue (flag_id, owner_user_id, kind, object_ref, status) "
            "VALUES ('dfl-bad', '__operator__', 'concept', 'x', 'flying')",
        )


def test_note_beyond_the_cap_is_a_422_at_the_api_and_a_check_at_the_db(api_env) -> None:
    db = api_env["db"]
    _seed_graph(db)
    client = _client()

    too_long = "x" * 281
    resp = client.post("/diligence/flags", json=_flag_payload(note=too_long))
    assert resp.status_code == 422

    with connect_write(db, purpose="test/note-check-init") as con:
        init_diligence_schema(con)
    with pytest.raises(duckdb.ConstraintException), connect_write(
        db, purpose="test/note-check"
    ) as con:
        con.execute(
            "INSERT INTO diligence_queue (flag_id, owner_user_id, kind, object_ref, note) "
            f"VALUES ('dfl-note', '__operator__', 'concept', 'x', '{too_long}')",
        )

    # The cap itself is lawful.
    ok = client.post("/diligence/flags", json=_flag_payload(note="x" * 280))
    assert ok.status_code == 201


def test_dismiss_of_a_spawned_flag_is_a_409(api_env) -> None:
    db = api_env["db"]
    _seed_graph(db)
    client = _client()
    created = client.post("/diligence/flags", json=_flag_payload())
    flag_id = created.json()["flag_id"]
    with connect_write(db, purpose="test/force-spawned") as con:
        con.execute(
            "UPDATE diligence_queue SET status = 'spawned', "
            "spawned_investigation_id = 'inv-spawned' WHERE flag_id = ?",
            [flag_id],
        )
    resp = client.post(f"/diligence/flags/{flag_id}/dismiss")
    assert resp.status_code == 409
    assert "diligence_not_dismissable" in resp.json()["detail"]
