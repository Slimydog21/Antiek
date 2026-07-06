"""Context-picker composition API tests (CK-4 cursor-for-knowledge).

Exercises the §9.0 retrieval gate end-to-end through the REAL
``serve_full_text`` path: a ``personal_reading`` doc is WITHHELD on the
default (unauthenticated) path and included only on the authenticated
owner path. This is the master-spec §6 rigor gate — "a context-composition
test with a withheld personal_reading case".
"""

from __future__ import annotations

import os
import tempfile

import pytest
from fastapi.testclient import TestClient

from runtime.db_lock import connect_write
from substrate.graph.ops import insert_document
from substrate.graph.schema import init_database


@pytest.fixture
def client(monkeypatch):
    tmpdir = tempfile.mkdtemp(prefix="compose-context-test-")
    db_path = os.path.join(tmpdir, "graph.duckdb")
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", db_path)
    events_dir = os.path.join(tmpdir, "events")
    os.makedirs(events_dir, exist_ok=True)
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", events_dir)
    monkeypatch.delenv("ANTIEK_OPERATOR_TOKEN", raising=False)
    monkeypatch.delenv("ANTIEK_OPERATOR_EMAIL", raising=False)

    # Seed a servable doc, a personal_reading doc, and an authored insight.
    # init_database(con) creates the schema; explicit content_class bypasses
    # the third-party ingest defaulting guard (we seed read-side fixtures).
    con = connect_write(db_path, purpose="ck4-seed")
    init_database(con)
    try:
        insert_document(
            con,
            document_id="doc-public",
            source_tier=2,
            document_type="paper",
            title="Public Paper",
            content_class="user_owned",  # servable → full_text on every path
            raw_text="Public body text that is fully servable.",
        )
        insert_document(
            con,
            document_id="doc-private",
            source_tier=2,
            document_type="paper",
            title="Private Clipping",
            content_class="personal_reading",  # §9.0 withholdable
            raw_text="Private personal-reading body withheld from public.",
        )
        con.execute(
            "INSERT INTO nodes (node_id, canonical_label, node_type, graph_scope) "
            "VALUES (?, ?, ?, ?)",
            [
                "insight-1",
                "An authored insight the operator @-mentioned.",
                "insight",
                "depth",
            ],
        )
    finally:
        con.close()

    from interfaces.research.api.app import create_app

    app = create_app(
        register_wrestling=False, register_providers=False, cors_origins=[],
    )
    return TestClient(app)


def test_compose_context_withholds_personal_reading_on_default_path(client):
    """§6 rigor gate: a personal_reading doc is WITHHELD on the default
    (unauthenticated) path — it never reaches system_context — while a
    servable doc + an authored insight compose in."""
    response = client.post(
        "/compose-context",
        json={
            "items": [
                {"kind": "doc", "id": "doc-public"},
                {"kind": "doc", "id": "doc-private"},
                {"kind": "insight", "id": "insight-1"},
            ],
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    ctx = body["system_context"]
    assert "Public body text" in ctx                  # servable doc included
    assert "Private personal-reading" not in ctx      # personal_reading withheld
    assert "authored insight" in ctx                  # insight composes in
    assert body["withheld"] == ["doc-private"]
    assert body["missing"] == []


def test_compose_context_includes_personal_reading_on_owner_path(
    client, monkeypatch,
):
    """The owner path (authenticated single-operator) includes the
    personal_reading doc in full — the §9.0 owner full-read lane. The
    gate is SERVER-DERIVED: the endpoint resolves the tag via
    _owner_read_policy_tag, so monkeypatching that resolver flips owner."""
    import interfaces.research.api.books as books_mod

    monkeypatch.setattr(
        books_mod, "_owner_read_policy_tag", lambda _req: "operator_only",
    )

    response = client.post(
        "/compose-context",
        json={"items": [{"kind": "doc", "id": "doc-private"}]},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert "Private personal-reading" in body["system_context"]  # owner full-read
    assert body["withheld"] == []


def test_compose_context_reports_missing_ids(client):
    response = client.post(
        "/compose-context",
        json={"items": [{"kind": "doc", "id": "does-not-exist"}]},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["system_context"] == ""
    assert body["missing"] == ["does-not-exist"]
    assert body["withheld"] == []


def test_compose_context_rejects_empty_and_overlong_item_lists(client):
    empty = client.post("/compose-context", json={"items": []})
    assert empty.status_code == 422

    overlong = client.post(
        "/compose-context",
        json={"items": [{"kind": "doc", "id": f"d{i}"} for i in range(21)]},
    )
    assert overlong.status_code == 422
