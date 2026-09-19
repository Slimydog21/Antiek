from __future__ import annotations

from datetime import UTC, datetime

import pytest

from runtime.db_lock import connect_write
from substrate.graph.ops import insert_document
from substrate.graph.schema import init_database_at_path
from substrate.investigation_streams import initialize_composite_stream
from substrate.investigation_tenancy import InvestigationAuthority
from substrate.legal_gate.history_migration import (
    LegacyDocumentClaim,
    migrate_legacy_documents,
    rollback_legacy_migration,
)
from substrate.legal_gate.policy_store import LegalPolicyDenied
from substrate.legal_gate.read import read_document

NOW = datetime(2026, 7, 15, tzinfo=UTC)


def _authority(tmp_path) -> InvestigationAuthority:
    authority = InvestigationAuthority("alice", "legacy", root=tmp_path / "tenancy")
    initialize_composite_stream(authority)
    return authority


def _seed(con):
    insert_document(
        con,
        document_id="doc-claimed",
        source_tier=1,
        document_type="note",
        investigation_id="legacy",
        raw_text="my legacy note",
        owner_user_id="alice",
    )
    insert_document(
        con,
        document_id="doc-unknown",
        source_tier=3,
        document_type="web_article",
        investigation_id="legacy",
        raw_text="unknown external body",
        owner_user_id="alice",
    )


def test_dry_run_is_non_mutating_and_apply_quarantines_unknown(tmp_path):
    path = str(tmp_path / "graph.duckdb")
    init_database_at_path(path)
    authority = _authority(tmp_path)
    claim = LegacyDocumentClaim("doc-claimed", "user_authored", "operator-note-ledger-1")
    with connect_write(path, purpose="legal-history-test") as con:
        _seed(con)
        dry = migrate_legacy_documents(con, authority, claims=(claim,), at=NOW)
        assert (dry.candidate_count, dry.admitted_count, dry.quarantined_count) == (2, 1, 1)
        assert con.execute("SELECT count(*) FROM legal_history_migration_runs").fetchone() == (0,)
        applied = migrate_legacy_documents(
            con, authority, claims=(claim,), apply=True, at=NOW
        )
        assert (applied.admitted_count, applied.quarantined_count) == (1, 1)
        assert read_document(con, authority, "doc-claimed")["raw_text"] == "my legacy note"
        with pytest.raises(LegalPolicyDenied, match="unavailable"):
            read_document(con, authority, "doc-unknown")
        row = con.execute(
            "SELECT disposition, reason_code, citation_digest, admission_receipt_id "
            "FROM legal_history_migration_rows WHERE document_id = 'doc-unknown'"
        ).fetchone()
        assert row == ("quarantined", "unknown_legacy_provenance", None, None)
        assert migrate_legacy_documents(
            con, authority, claims=(claim,), apply=True, at=NOW
        ) == applied


def test_external_claim_still_needs_policy_and_rollback_removes_created_receipts(tmp_path):
    path = str(tmp_path / "graph.duckdb")
    init_database_at_path(path)
    authority = _authority(tmp_path)
    claim = LegacyDocumentClaim(
        "doc-unknown",
        "external_network",
        "source-custody-ledger-1",
        canonical_url="https://example.com/article",
        source_corpus="web",
    )
    with connect_write(path, purpose="legal-history-test") as con:
        _seed(con)
        applied = migrate_legacy_documents(
            con, authority, claims=(claim,), apply=True, at=NOW
        )
        assert applied.admitted_count == 0
        assert applied.quarantined_count == 2
        assert con.execute("SELECT count(*) FROM legal_document_admissions").fetchone() == (1,)
        rolled = rollback_legacy_migration(con, authority, applied.run_id)
        assert rolled.state == "rolled_back"
        assert con.execute("SELECT count(*) FROM legal_document_admissions").fetchone() == (0,)
        assert con.execute("SELECT count(*) FROM legal_history_migration_rows").fetchone() == (0,)
        with pytest.raises(RuntimeError, match="new claim set"):
            migrate_legacy_documents(con, authority, claims=(claim,), apply=True, at=NOW)


def test_migration_cannot_claim_another_owners_same_named_investigation(tmp_path):
    path = str(tmp_path / "graph.duckdb")
    init_database_at_path(path)
    alice = _authority(tmp_path)
    with connect_write(path, purpose="legal-history-owner-test") as con:
        insert_document(
            con,
            document_id="doc-bob",
            source_tier=1,
            document_type="note",
            investigation_id=alice.investigation_id,
            raw_text="bob private legacy note",
            owner_user_id="bob",
        )
        claim = LegacyDocumentClaim("doc-bob", "user_authored", "alice-assertion")
        census = migrate_legacy_documents(con, alice, claims=(claim,), apply=True, at=NOW)
        assert census.candidate_count == 0
        with pytest.raises(LegalPolicyDenied, match="unavailable"):
            read_document(con, alice, "doc-bob")
