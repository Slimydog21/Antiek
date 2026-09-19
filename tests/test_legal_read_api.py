from __future__ import annotations

import hashlib
from datetime import UTC, datetime

from fastapi.testclient import TestClient

from interfaces.research.api.app import create_app
from runtime.db_lock import connect_write
from substrate.graph.ops import insert_chunk_admitted, insert_document_admitted
from substrate.graph.schema import init_database_at_path
from substrate.investigation_streams import initialize_composite_stream
from substrate.investigation_tenancy import InvestigationAuthority
from substrate.legal_gate.admission import admit_staged_document
from substrate.legal_gate.policy_store import account_policy_authority, append_policy_event


def _seed(con, authority: InvestigationAuthority) -> tuple[str, str]:
    document_id = "doc-legal-api"
    text = "legally admitted API body"
    digest = hashlib.sha256(text.encode()).hexdigest()
    policy = account_policy_authority(authority)
    append_policy_event(
        con,
        policy,
        scope_kind="account",
        matcher_kind="domain",
        matcher_value="example.com",
        decision="allow",
        citation_ref="license",
        issuer_id="operator-rights",
        reason_code="licensed",
        effective_at=datetime(2026, 7, 15, tzinfo=UTC),
    )
    receipt = admit_staged_document(
        con,
        policy,
        investigation_digest=authority.investigation_digest,
        document_id=document_id,
        provenance_class="external_network",
        canonical_url="https://example.com/article",
        content_sha256=digest,
        at=datetime(2026, 7, 15, tzinfo=UTC),
    )
    insert_document_admitted(
        con,
        authority,
        admission_receipt_id=receipt.receipt_id,
        admitted_content_sha256=digest,
        document_id=document_id,
        source_tier=2,
        document_type="note",
        investigation_id=authority.investigation_id,
        title="Legal API document",
        raw_text=text,
    )
    chunk_id = insert_chunk_admitted(
        con,
        authority,
        admission_receipt_id=receipt.receipt_id,
        admitted_content_sha256=digest,
        document_id=document_id,
        chunk_index=0,
        text=text,
    )
    return document_id, chunk_id


def test_enforced_document_list_and_chunk_hide_after_policy_change(tmp_path, monkeypatch):
    path = str(tmp_path / "graph.duckdb")
    events = tmp_path / "events"
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", path)
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", str(events))
    monkeypatch.setenv("ANTIEK_LEGAL_READ_ENFORCEMENT", "1")
    init_database_at_path(path)
    authority = InvestigationAuthority("__operator__", "inv-legal")
    initialize_composite_stream(authority)
    with connect_write(path, purpose="legal-read-api-test") as con:
        document_id, chunk_id = _seed(con, authority)

    client = TestClient(create_app(register_wrestling=False))
    listed = client.get("/documents?investigation_id=inv-legal")
    assert listed.status_code == 200
    assert [row["document_id"] for row in listed.json()["documents"]] == [document_id]
    chunk = client.get(f"/chunks/{chunk_id}")
    assert chunk.status_code == 200
    assert chunk.json()["text"] == "legally admitted API body"

    with connect_write(path, purpose="legal-read-api-test") as con:
        append_policy_event(
            con,
            account_policy_authority(authority),
            scope_kind="account",
            matcher_kind="domain",
            matcher_value="blocked.example",
            decision="deny",
            citation_ref="policy-change",
            issuer_id="operator-rights",
            reason_code="blocked",
            effective_at=datetime(2026, 7, 15, tzinfo=UTC),
        )
    assert client.get("/documents?investigation_id=inv-legal").json() == {"documents": []}
    assert client.get(f"/chunks/{chunk_id}").status_code == 404


def test_enforced_document_list_requires_investigation(tmp_path, monkeypatch):
    path = str(tmp_path / "graph.duckdb")
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", path)
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", str(tmp_path / "events"))
    monkeypatch.setenv("ANTIEK_LEGAL_READ_ENFORCEMENT", "1")
    init_database_at_path(path)
    client = TestClient(create_app(register_wrestling=False))
    response = client.get("/documents")
    assert response.status_code == 422


def test_enforced_groundedness_resolver_never_receives_foreign_or_tampered_bytes(
    tmp_path, monkeypatch
):
    from substrate.eval.groundedness.provenance import duckdb_chunk_text_resolver

    path = str(tmp_path / "graph.duckdb")
    events = tmp_path / "events"
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", path)
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", str(events))
    monkeypatch.setenv("ANTIEK_LEGAL_READ_ENFORCEMENT", "1")
    init_database_at_path(path)
    alice = InvestigationAuthority("alice", "inv-legal", root=events)
    bob = InvestigationAuthority("bob", "inv-legal", root=events)
    initialize_composite_stream(alice)
    initialize_composite_stream(bob)
    with connect_write(path, purpose="legal-groundedness-test") as con:
        _, chunk_id = _seed(con, alice)

    allowed = duckdb_chunk_text_resolver(
        path, chunk_ids=[chunk_id], authority=alice
    )
    foreign = duckdb_chunk_text_resolver(path, chunk_ids=[chunk_id], authority=bob)
    unbounded = duckdb_chunk_text_resolver(path, authority=alice)
    assert allowed(chunk_id) == "legally admitted API body"
    assert foreign(chunk_id) is None
    assert unbounded(chunk_id) is None

    with connect_write(path, purpose="legal-groundedness-test") as con:
        con.execute("UPDATE chunks SET text = ? WHERE chunk_id = ?", ["tampered", chunk_id])

    tampered = duckdb_chunk_text_resolver(
        path, chunk_ids=[chunk_id], authority=alice
    )
    assert tampered(chunk_id) is None


def test_enforcement_leaves_legacy_scalar_wrestling_handlers_inert(monkeypatch):
    from interfaces.research.api.broadcast import EventBroadcaster
    from interfaces.research.api.wrestling import register_handlers

    monkeypatch.setenv("ANTIEK_LEGAL_READ_ENFORCEMENT", "1")
    broadcaster = EventBroadcaster()
    register_handlers(broadcaster)
    assert broadcaster._handlers == {}


def test_enforcement_leaves_legacy_scalar_grounding_handler_inert(monkeypatch):
    from interfaces.research.api.broadcast import EventBroadcaster
    from interfaces.research.api.grounding import register_handlers

    monkeypatch.setenv("ANTIEK_LEGAL_READ_ENFORCEMENT", "1")
    broadcaster = EventBroadcaster()
    register_handlers(broadcaster)
    assert broadcaster._handlers == {}


def test_enforced_thought_partner_requires_investigation_before_dispatch(
    tmp_path, monkeypatch
):
    path = str(tmp_path / "graph.duckdb")
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", path)
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", str(tmp_path / "events"))
    monkeypatch.setenv("ANTIEK_LEGAL_READ_ENFORCEMENT", "1")
    init_database_at_path(path)

    response = TestClient(create_app(register_wrestling=False)).post(
        "/thought-partner", json={"prompt": "show me my library"}
    )

    assert response.status_code == 422
    assert response.json()["detail"] == "investigation_id is required"


def test_enforced_block_search_requires_exact_node_membership(tmp_path, monkeypatch):
    from substrate.graph.ops import insert_node

    path = str(tmp_path / "graph.duckdb")
    events = tmp_path / "events"
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", path)
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", str(events))
    monkeypatch.setenv("ANTIEK_LEGAL_READ_ENFORCEMENT", "1")
    init_database_at_path(path)
    authority = InvestigationAuthority("__operator__", "inv-blocks", root=events)
    initialize_composite_stream(authority)
    with connect_write(path, purpose="legal-block-search-test") as con:
        visible = insert_node(
            con,
            canonical_label="visible private note",
            node_type="insight",
            graph_scope="depth",
            investigation_id=authority.investigation_id,
        )
        insert_node(
            con,
            canonical_label="foreign private insight",
            node_type="insight",
            graph_scope="depth",
            investigation_id="other",
        )
        con.execute(
            "INSERT INTO investigation_node_memberships "
            "(account_digest, investigation_digest, node_id, role, "
            "source_row_digest, membership_metadata) VALUES (?, ?, ?, ?, ?, ?)",
            [
                authority.account_digest,
                authority.investigation_digest,
                visible,
                "note",
                "a" * 64,
                "{}",
            ],
        )

    client = TestClient(create_app(register_wrestling=False))
    missing = client.get("/blocks/search", params={"q": "private"})
    assert missing.status_code == 422
    response = client.get(
        "/blocks/search",
        params={"q": "private", "investigation_id": "inv-blocks"},
    )
    assert response.status_code == 200
    assert [hit["label"] for hit in response.json()["hits"]] == [
        "visible private note"
    ]
