from __future__ import annotations

import hashlib
from datetime import UTC, datetime

import pytest

from runtime.db_lock import connect_write
from substrate.graph.ops import insert_chunk_admitted, insert_document_admitted
from substrate.graph.schema import init_database_at_path
from substrate.investigation_streams import initialize_composite_stream
from substrate.investigation_tenancy import InvestigationAuthority
from substrate.legal_gate.admission import admit_staged_document, require_allowed_receipt
from substrate.legal_gate.policy_store import (
    LegalPolicyDenied,
    account_policy_authority,
    append_policy_event,
)

NOW = datetime(2026, 7, 15, tzinfo=UTC)


def _authority(tmp_path, account: str):
    raw = InvestigationAuthority(account, "legal-admission", root=tmp_path / "tenancy")
    initialize_composite_stream(raw)
    return raw, account_policy_authority(raw)


def test_external_document_requires_explicit_allow_and_receipt_is_redacted(tmp_path):
    path = str(tmp_path / "graph.duckdb")
    init_database_at_path(path)
    raw, alice = _authority(tmp_path, "alice")
    with connect_write(path, purpose="legal-admission-test") as con:
        denied = admit_staged_document(
            con,
            alice,
            investigation_digest=raw.investigation_digest,
            document_id="doc-1",
            provenance_class="external_network",
            canonical_url="https://example.com/private-title",
            title="Sensitive title",
            author="Author",
            source_corpus="web",
            content_sha256="a" * 64,
            at=NOW,
        )
        assert denied.decision == "deny"
        with pytest.raises(LegalPolicyDenied):
            require_allowed_receipt(
                con,
                alice,
                receipt_id=denied.receipt_id,
                document_id="doc-1",
                investigation_digest=raw.investigation_digest,
                content_sha256="a" * 64,
            )
        stored = con.execute(
            "SELECT canonical_url_digest, metadata_digest, content_sha256 "
            "FROM legal_document_admissions WHERE receipt_id = ?",
            [denied.receipt_id],
        ).fetchone()
        assert stored is not None
        assert "Sensitive" not in " ".join(stored)


def test_allowed_receipt_is_owner_scoped_and_transactional(tmp_path):
    path = str(tmp_path / "graph.duckdb")
    init_database_at_path(path)
    raw, alice = _authority(tmp_path, "alice")
    _, bob = _authority(tmp_path, "bob")
    with connect_write(path, purpose="legal-admission-test") as con:
        append_policy_event(
            con,
            alice,
            scope_kind="account",
            matcher_kind="domain",
            matcher_value="example.com",
            decision="allow",
            citation_ref="license-1",
            issuer_id="alice-rights",
            reason_code="licensed",
            effective_at=NOW,
        )
        receipt = admit_staged_document(
            con,
            alice,
            investigation_digest=raw.investigation_digest,
            document_id="doc-1",
            provenance_class="external_network",
            canonical_url="https://example.com/article",
            content_sha256="b" * 64,
            at=NOW,
        )
        assert receipt.decision == "allow"
        require_allowed_receipt(
            con,
            alice,
            receipt_id=receipt.receipt_id,
            document_id="doc-1",
            investigation_digest=raw.investigation_digest,
            content_sha256="b" * 64,
        )
        with pytest.raises(LegalPolicyDenied):
            require_allowed_receipt(
                con,
                bob,
                receipt_id=receipt.receipt_id,
                document_id="doc-1",
                investigation_digest=raw.investigation_digest,
                content_sha256="b" * 64,
            )

        con.execute("BEGIN TRANSACTION")
        rolled_back = admit_staged_document(
            con,
            alice,
            investigation_digest=raw.investigation_digest,
            document_id="doc-rollback",
            provenance_class="user_authored",
            content_sha256="c" * 64,
            at=NOW,
        )
        con.execute("ROLLBACK")
        assert (
            con.execute(
                "SELECT 1 FROM legal_document_admissions WHERE receipt_id = ?",
                [rolled_back.receipt_id],
            ).fetchone()
            is None
        )


def test_admitted_graph_writers_reject_receipt_retargeting(tmp_path):
    path = str(tmp_path / "graph.duckdb")
    init_database_at_path(path)
    raw, alice = _authority(tmp_path, "alice")
    with connect_write(path, purpose="legal-admission-test") as con:
        staged_text = "allowed staged document"
        staged_digest = hashlib.sha256(staged_text.encode()).hexdigest()
        receipt = admit_staged_document(
            con,
            alice,
            investigation_digest=raw.investigation_digest,
            document_id="doc-allowed",
            provenance_class="user_authored",
            content_sha256=staged_digest,
            at=NOW,
        )
        with pytest.raises(LegalPolicyDenied):
            insert_document_admitted(
                con,
                raw,
                admission_receipt_id=receipt.receipt_id,
                admitted_content_sha256=staged_digest,
                document_id="doc-retargeted",
                source_tier=1,
                document_type="note",
                raw_text=staged_text,
            )
        insert_document_admitted(
            con,
            raw,
            admission_receipt_id=receipt.receipt_id,
            admitted_content_sha256=staged_digest,
            document_id="doc-allowed",
            source_tier=1,
            document_type="note",
            raw_text=staged_text,
        )
        with pytest.raises(LegalPolicyDenied):
            insert_chunk_admitted(
                con,
                raw,
                admission_receipt_id="lda-" + "0" * 32,
                admitted_content_sha256=staged_digest,
                document_id="doc-allowed",
                chunk_index=0,
                text="must not land",
            )
        assert con.execute(
            "SELECT count(*) FROM chunks WHERE document_id = 'doc-allowed'"
        ).fetchone() == (0,)


def test_receipt_tampering_and_policy_drift_fail_closed(tmp_path):
    path = str(tmp_path / "graph.duckdb")
    init_database_at_path(path)
    raw, alice = _authority(tmp_path, "alice")
    with connect_write(path, purpose="legal-admission-test") as con:
        append_policy_event(
            con,
            alice,
            scope_kind="account",
            matcher_kind="domain",
            matcher_value="example.com",
            decision="allow",
            citation_ref="license-1",
            issuer_id="alice-rights",
            reason_code="licensed",
            effective_at=NOW,
        )
        receipt = admit_staged_document(
            con,
            alice,
            investigation_digest=raw.investigation_digest,
            document_id="doc-drift",
            provenance_class="external_network",
            canonical_url="https://example.com/article",
            content_sha256="e" * 64,
            at=NOW,
        )
        con.execute(
            "UPDATE legal_document_admissions SET metadata_digest = ? WHERE receipt_id = ?",
            ["f" * 64, receipt.receipt_id],
        )
        with pytest.raises(LegalPolicyDenied, match="authentication"):
            require_allowed_receipt(
                con,
                alice,
                receipt_id=receipt.receipt_id,
                document_id="doc-drift",
                investigation_digest=raw.investigation_digest,
                content_sha256="e" * 64,
            )

        original_metadata_digest = hashlib.sha256(
            b'{"author":"","source_corpus":"","title":""}'
        ).hexdigest()
        con.execute(
            "UPDATE legal_document_admissions SET metadata_digest = ? WHERE receipt_id = ?",
            [original_metadata_digest, receipt.receipt_id],
        )
        append_policy_event(
            con,
            alice,
            scope_kind="account",
            matcher_kind="domain",
            matcher_value="blocked.example",
            decision="deny",
            citation_ref="policy-2",
            issuer_id="alice-rights",
            reason_code="blocked",
            effective_at=NOW,
        )
        with pytest.raises(LegalPolicyDenied, match="stale"):
            require_allowed_receipt(
                con,
                alice,
                receipt_id=receipt.receipt_id,
                document_id="doc-drift",
                investigation_digest=raw.investigation_digest,
                content_sha256="e" * 64,
            )


def test_admitted_ignore_conflict_rejects_different_stored_bytes(tmp_path):
    path = str(tmp_path / "graph.duckdb")
    init_database_at_path(path)
    raw, alice = _authority(tmp_path, "alice")
    staged = "new admitted bytes"
    digest = hashlib.sha256(staged.encode()).hexdigest()
    with connect_write(path, purpose="legal-admission-test") as con:
        from substrate.graph.ops import insert_document

        insert_document(
            con,
            document_id="doc-conflict",
            source_tier=1,
            document_type="note",
            raw_text="old retained bytes",
        )
        receipt = admit_staged_document(
            con,
            alice,
            investigation_digest=raw.investigation_digest,
            document_id="doc-conflict",
            provenance_class="user_authored",
            content_sha256=digest,
            at=NOW,
        )
        with pytest.raises(LegalPolicyDenied, match="existing document bytes"):
            insert_document_admitted(
                con,
                raw,
                admission_receipt_id=receipt.receipt_id,
                admitted_content_sha256=digest,
                document_id="doc-conflict",
                source_tier=1,
                document_type="note",
                raw_text=staged,
                on_conflict="ignore",
            )
