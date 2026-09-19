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

NOW = datetime(2026, 7, 15, tzinfo=UTC)


def test_graph_explorer_removes_nodes_and_edges_after_policy_drift(tmp_path, monkeypatch):
    path = str(tmp_path / "graph.duckdb")
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", path)
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", str(tmp_path / "events"))
    monkeypatch.setenv("ANTIEK_LEGAL_READ_ENFORCEMENT", "1")
    init_database_at_path(path)
    authority = InvestigationAuthority("__operator__", "inv-graph")
    initialize_composite_stream(authority)
    text = "graph evidence body"
    digest = hashlib.sha256(text.encode()).hexdigest()
    policy = account_policy_authority(authority)
    with connect_write(path, purpose="legal-graph-test") as con:
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
            effective_at=NOW,
        )
        receipt = admit_staged_document(
            con,
            policy,
            investigation_digest=authority.investigation_digest,
            document_id="doc-graph",
            provenance_class="external_network",
            canonical_url="https://example.com/article",
            content_sha256=digest,
            at=NOW,
        )
        insert_document_admitted(
            con,
            authority,
            admission_receipt_id=receipt.receipt_id,
            admitted_content_sha256=digest,
            document_id="doc-graph",
            source_tier=2,
            document_type="note",
            investigation_id=authority.investigation_id,
            raw_text=text,
        )
        chunk_id = insert_chunk_admitted(
            con,
            authority,
            admission_receipt_id=receipt.receipt_id,
            admitted_content_sha256=digest,
            document_id="doc-graph",
            chunk_index=0,
            text=text,
        )
        con.execute(
            "INSERT INTO nodes (node_id, canonical_label, node_type, graph_scope, metadata) "
            "VALUES ('n1', 'Denied-derived insight', 'insight', 'depth', ?), "
            "('n2', 'Denied-derived mechanism', 'mechanism', 'depth', ?)",
            [
                f'{{"chunk_id":"{chunk_id}"}}',
                f'{{"chunk_id":"{chunk_id}"}}',
            ],
        )
        for node_id, role in (("n1", "insight"), ("n2", "reference")):
            con.execute(
                "INSERT INTO investigation_node_memberships "
                "(account_digest, investigation_digest, node_id, role, source_row_digest) "
                "VALUES (?, ?, ?, ?, ?)",
                [
                    authority.account_digest,
                    authority.investigation_digest,
                    node_id,
                    role,
                    hashlib.sha256(node_id.encode()).hexdigest(),
                ],
            )
        con.execute(
            "INSERT INTO edges (edge_id, source_node_id, target_node_id, relation, "
            "chunk_id, source_document_id, source_tier, extraction_confidence, graph_scope, "
            "investigation_id, account_digest, investigation_digest) "
            "VALUES ('e1', 'n1', 'n2', 'supports', ?, 'doc-graph', 2, 0.9, 'depth', "
            "'inv-graph', ?, ?)",
            [chunk_id, authority.account_digest, authority.investigation_digest],
        )

    client = TestClient(create_app(register_wrestling=False, register_providers=False))
    visible = client.get("/graph/explore?investigation_id=inv-graph")
    assert visible.status_code == 200
    assert {item["node_id"] for item in visible.json()["nodes"]} == {"n1", "n2"}
    assert [item["edge_id"] for item in visible.json()["edges"]] == ["e1"]

    with connect_write(path, purpose="legal-graph-test") as con:
        append_policy_event(
            con,
            policy,
            scope_kind="account",
            matcher_kind="domain",
            matcher_value="blocked.example",
            decision="deny",
            citation_ref="policy-change",
            issuer_id="operator-rights",
            reason_code="blocked",
            effective_at=NOW,
        )
    hidden = client.get("/graph/explore?investigation_id=inv-graph")
    assert hidden.status_code == 200
    assert hidden.json()["nodes"] == []
    assert hidden.json()["edges"] == []
