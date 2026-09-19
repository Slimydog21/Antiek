from __future__ import annotations

import hashlib
from datetime import UTC, datetime

from runtime.db_lock import connect_write
from services.html_projection.resolvers.substrate_refs import resolve_refs
from substrate.graph.ops import insert_document_admitted
from substrate.graph.schema import init_database_at_path
from substrate.investigation_streams import initialize_composite_stream
from substrate.investigation_tenancy import InvestigationAuthority
from substrate.legal_gate.admission import admit_staged_document
from substrate.legal_gate.policy_store import account_policy_authority, append_policy_event

NOW = datetime(2026, 7, 15, tzinfo=UTC)


def test_projection_refs_require_membership_and_current_source_admission(tmp_path, monkeypatch):
    path = str(tmp_path / "graph.duckdb")
    authority = InvestigationAuthority("alice", "projection", root=tmp_path / "tenancy")
    initialize_composite_stream(authority)
    init_database_at_path(path)
    body = "source body"
    digest = hashlib.sha256(body.encode()).hexdigest()
    policy = account_policy_authority(authority)
    with connect_write(path, purpose="legal-projection-test") as con:
        append_policy_event(
            con,
            policy,
            scope_kind="account",
            matcher_kind="domain",
            matcher_value="example.com",
            decision="allow",
            citation_ref="license",
            issuer_id="alice-rights",
            reason_code="licensed",
            effective_at=NOW,
        )
        receipt = admit_staged_document(
            con,
            policy,
            investigation_digest=authority.investigation_digest,
            document_id="doc-source",
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
            document_id="doc-source",
            source_tier=2,
            document_type="note",
            investigation_id=authority.investigation_id,
            title="Allowed source",
            raw_text=body,
        )
        con.execute(
            "INSERT INTO nodes (node_id, canonical_label, node_type, graph_scope, metadata) "
            "VALUES ('claim-1', 'Allowed claim', 'claim', 'depth', ?)",
            ['{"source_document_id":"doc-source"}'],
        )
        con.execute(
            "INSERT INTO investigation_node_memberships "
            "(account_digest, investigation_digest, node_id, role, source_row_digest) "
            "VALUES (?, ?, 'claim-1', 'claim', ?)",
            [authority.account_digest, authority.investigation_digest, "a" * 64],
        )
    monkeypatch.setenv("ANTIEK_LEGAL_READ_ENFORCEMENT", "1")
    assert resolve_refs(["claim-1"], db_path=path) == {}
    resolved = resolve_refs(["claim-1"], db_path=path, authority=authority)
    assert resolved["claim-1"].title == "Allowed source"

    with connect_write(path, purpose="legal-projection-test") as con:
        append_policy_event(
            con,
            policy,
            scope_kind="account",
            matcher_kind="domain",
            matcher_value="blocked.example",
            decision="deny",
            citation_ref="policy-change",
            issuer_id="alice-rights",
            reason_code="blocked",
            effective_at=NOW,
        )
    assert resolve_refs(["claim-1"], db_path=path, authority=authority) == {}
