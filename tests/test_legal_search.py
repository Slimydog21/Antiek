from __future__ import annotations

import hashlib
from datetime import UTC, datetime

from runtime.db_lock import connect_write
from substrate.graph.ops import insert_chunk_admitted, insert_document_admitted
from substrate.graph.schema import init_database_at_path
from substrate.graph.search import search_authorized
from substrate.investigation_streams import initialize_composite_stream
from substrate.investigation_tenancy import InvestigationAuthority
from substrate.legal_gate.admission import admit_staged_document
from substrate.legal_gate.policy_store import account_policy_authority, append_policy_event


class _Model:
    dimension = 2

    def encode(self, _text: str) -> list[float]:
        return [1.0, 0.0]


def _authority(tmp_path, account: str) -> InvestigationAuthority:
    authority = InvestigationAuthority(account, "search", root=tmp_path / "tenancy")
    initialize_composite_stream(authority)
    return authority


def _seed(con, authority, document_id: str, text: str) -> None:
    digest = hashlib.sha256(text.encode()).hexdigest()
    policy = account_policy_authority(authority)
    append_policy_event(
        con,
        policy,
        scope_kind="account",
        matcher_kind="domain",
        matcher_value=f"{authority.account_id}.example",
        decision="allow",
        citation_ref="license",
        issuer_id=f"{authority.account_id}-rights",
        reason_code="licensed",
        effective_at=datetime(2026, 7, 15, tzinfo=UTC),
    )
    receipt = admit_staged_document(
        con,
        policy,
        investigation_digest=authority.investigation_digest,
        document_id=document_id,
        provenance_class="external_network",
        canonical_url=f"https://{authority.account_id}.example/article",
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
        document_type="web_article",
        investigation_id=authority.investigation_id,
        raw_text=text,
    )
    insert_chunk_admitted(
        con,
        authority,
        admission_receipt_id=receipt.receipt_id,
        admitted_content_sha256=digest,
        document_id=document_id,
        chunk_index=0,
        text=text,
        embedding=[1.0, 0.0],
    )


def test_search_is_exact_owner_scoped_and_policy_drift_hides_results(tmp_path):
    path = str(tmp_path / "graph.duckdb")
    init_database_at_path(path)
    alice = _authority(tmp_path, "alice")
    bob = _authority(tmp_path, "bob")
    with connect_write(path, purpose="legal-search-test") as con:
        _seed(con, alice, "doc-alice", "alice secret")
        assert [r["document_id"] for r in search_authorized(
            con, alice, "secret", model=_Model()
        )["results"]] == ["doc-alice"]
        assert search_authorized(con, bob, "secret", model=_Model())["results"] == []
        append_policy_event(
            con,
            account_policy_authority(alice),
            scope_kind="account",
            matcher_kind="domain",
            matcher_value="blocked.example",
            decision="deny",
            citation_ref="changed-policy",
            issuer_id="alice-rights",
            reason_code="blocked",
            effective_at=datetime(2026, 7, 15, tzinfo=UTC),
        )
        assert search_authorized(con, alice, "secret", model=_Model())["results"] == []
