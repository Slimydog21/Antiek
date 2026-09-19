from __future__ import annotations

import hashlib
import shutil
from datetime import UTC, datetime, timedelta

import pytest

from runtime.db_lock import connect_read, connect_write
from substrate.graph.ops import insert_chunk_admitted, insert_document_admitted
from substrate.graph.schema import init_database_at_path
from substrate.investigation_streams import initialize_composite_stream
from substrate.investigation_tenancy import InvestigationAuthority
from substrate.legal_gate.admission import admit_staged_document
from substrate.legal_gate.policy_store import (
    LegalPolicyDenied,
    account_policy_authority,
    append_policy_event,
)
from substrate.legal_gate.read import (
    keyword_search_chunks_compatibility,
    read_chunk_ids_compatibility,
    read_chunks,
    read_document,
    readable_document_ids,
)


def test_legacy_chunk_id_projection_never_selects_body_and_preserves_order_clause():
    class _Rows:
        def fetchall(self):
            return [("chunk-b",), ("chunk-a",)]

    class _Connection:
        sql = ""
        params: list[str] = []

        def execute(self, sql, params):
            self.sql = sql
            self.params = params
            return _Rows()

    con = _Connection()
    assert read_chunk_ids_compatibility(
        con, "doc-book", authority=None, enforce=False
    ) == ("chunk-b", "chunk-a")
    assert con.sql == (
        "SELECT chunk_id FROM chunks WHERE document_id = ? ORDER BY chunk_index"
    )
    assert "text" not in con.sql.lower()
    assert con.params == ["doc-book"]


def test_strict_chunk_id_projection_without_authority_fails_closed_before_sql():
    class _Connection:
        def execute(self, *_args, **_kwargs):
            raise AssertionError("strict read without authority must not query custody")

    assert read_chunk_ids_compatibility(
        _Connection(), "doc-book", authority=None, enforce=True
    ) == ()

NOW = datetime(2026, 7, 15, tzinfo=UTC)


def _authority(tmp_path, account: str) -> InvestigationAuthority:
    authority = InvestigationAuthority(account, "legal-read", root=tmp_path / "tenancy")
    initialize_composite_stream(authority)
    return authority


def _admit_and_write(con, authority, *, document_id: str, text: str, external: bool = True):
    digest = hashlib.sha256(text.encode()).hexdigest()
    policy = account_policy_authority(authority)
    if external:
        append_policy_event(
            con,
            policy,
            scope_kind="account",
            matcher_kind="domain",
            matcher_value="example.com",
            decision="allow",
            citation_ref="license-1",
            issuer_id=f"{authority.account_id}-rights",
            reason_code="licensed",
            effective_at=NOW,
        )
    receipt = admit_staged_document(
        con,
        policy,
        investigation_digest=authority.investigation_digest,
        document_id=document_id,
        provenance_class="external_network" if external else "user_authored",
        canonical_url="https://example.com/article" if external else "",
        content_sha256=digest,
        at=NOW,
    )
    assert receipt.decision == "allow"
    insert_document_admitted(
        con,
        authority,
        admission_receipt_id=receipt.receipt_id,
        admitted_content_sha256=digest,
        document_id=document_id,
        source_tier=2,
        document_type="web_article" if external else "note",
        investigation_id=authority.investigation_id,
        raw_text=text,
        on_conflict="ignore",
    )
    insert_chunk_admitted(
        con,
        authority,
        admission_receipt_id=receipt.receipt_id,
        admitted_content_sha256=digest,
        document_id=document_id,
        chunk_index=0,
        text=text,
    )
    return receipt


def test_read_document_and_chunks_require_exact_owner_receipt(tmp_path):
    path = str(tmp_path / "graph.duckdb")
    init_database_at_path(path)
    alice = _authority(tmp_path, "alice")
    bob = _authority(tmp_path, "bob")
    with connect_write(path, purpose="legal-read-test") as con:
        receipt = _admit_and_write(con, alice, document_id="doc-1", text="private body")
        assert read_document(con, alice, "doc-1")["raw_text"] == "private body"
        assert read_document(con, alice, "doc-1")["legal_admission_receipt_id"] == receipt.receipt_id
        assert read_chunks(con, alice, "doc-1")[0]["text"] == "private body"
        assert readable_document_ids(con, alice) == ("doc-1",)
        with pytest.raises(LegalPolicyDenied, match="unavailable"):
            read_document(con, bob, "doc-1")
        assert readable_document_ids(con, bob) == ()


def test_policy_change_immediately_hides_external_without_deleting_custody(tmp_path):
    path = str(tmp_path / "graph.duckdb")
    init_database_at_path(path)
    alice = _authority(tmp_path, "alice")
    with connect_write(path, purpose="legal-read-test") as con:
        _admit_and_write(con, alice, document_id="doc-1", text="licensed body")
        append_policy_event(
            con,
            account_policy_authority(alice),
            scope_kind="account",
            matcher_kind="domain",
            matcher_value="blocked.example",
            decision="deny",
            citation_ref="policy-change",
            issuer_id="alice-rights",
            reason_code="blocked",
            effective_at=NOW,
        )
        with pytest.raises(LegalPolicyDenied, match="unavailable"):
            read_document(con, alice, "doc-1")
        assert con.execute(
            "SELECT raw_text FROM documents WHERE document_id = 'doc-1'"
        ).fetchone() == ("licensed body",)


def test_internal_admission_survives_unrelated_network_policy_and_corruption_fails(tmp_path):
    path = str(tmp_path / "graph.duckdb")
    init_database_at_path(path)
    alice = _authority(tmp_path, "alice")
    with connect_write(path, purpose="legal-read-test") as con:
        _admit_and_write(
            con,
            alice,
            document_id="doc-note",
            text="my note",
            external=False,
        )
        append_policy_event(
            con,
            account_policy_authority(alice),
            scope_kind="account",
            matcher_kind="domain",
            matcher_value="blocked.example",
            decision="deny",
            citation_ref="policy-change",
            issuer_id="alice-rights",
            reason_code="blocked",
            effective_at=NOW + timedelta(seconds=1),
        )
        assert read_document(con, alice, "doc-note")["raw_text"] == "my note"
        con.execute(
            "UPDATE legal_document_admissions SET metadata_digest = ? "
            "WHERE document_id = 'doc-note'",
            ["f" * 64],
        )
        with pytest.raises(LegalPolicyDenied, match="unavailable"):
            read_document(con, alice, "doc-note")


def test_revocation_does_not_resurrect_without_a_fresh_admission(tmp_path):
    path = str(tmp_path / "graph.duckdb")
    init_database_at_path(path)
    alice = _authority(tmp_path, "alice")
    with connect_write(path, purpose="legal-read-test") as con:
        original = _admit_and_write(con, alice, document_id="doc-revoke", text="licensed")
        allow_event = con.execute(
            "SELECT event_id FROM legal_policy_events WHERE decision = 'allow'"
        ).fetchone()[0]
        append_policy_event(
            con,
            account_policy_authority(alice),
            scope_kind="account",
            matcher_kind="domain",
            matcher_value="example.com",
            decision="revoke",
            citation_ref="license-revoked",
            issuer_id="alice-rights",
            reason_code="revoked",
            effective_at=NOW + timedelta(seconds=1),
            supersedes_event_id=allow_event,
        )
        with pytest.raises(LegalPolicyDenied, match="unavailable"):
            read_document(con, alice, "doc-revoke")
        new_allow = append_policy_event(
            con,
            account_policy_authority(alice),
            scope_kind="account",
            matcher_kind="domain",
            matcher_value="example.com",
            decision="allow",
            citation_ref="new-license",
            issuer_id="alice-rights",
            reason_code="relicensed",
            effective_at=NOW + timedelta(seconds=2),
        )
        assert new_allow != allow_event
        with pytest.raises(LegalPolicyDenied, match="unavailable"):
            read_document(con, alice, "doc-revoke")
        digest = hashlib.sha256(b"licensed").hexdigest()
        refreshed = admit_staged_document(
            con,
            account_policy_authority(alice),
            investigation_digest=alice.investigation_digest,
            document_id="doc-revoke",
            provenance_class="external_network",
            canonical_url="https://example.com/article",
            content_sha256=digest,
            at=NOW + timedelta(seconds=2),
        )
        assert refreshed.decision == "allow"
        assert refreshed.receipt_id != original.receipt_id
        assert read_document(con, alice, "doc-revoke")["raw_text"] == "licensed"


def test_tampered_chunk_cannot_ride_a_valid_document_receipt(tmp_path):
    path = str(tmp_path / "graph.duckdb")
    init_database_at_path(path)
    alice = _authority(tmp_path, "alice")
    with connect_write(path, purpose="legal-read-test") as con:
        _admit_and_write(con, alice, document_id="doc-chunk", text="canonical body")
        con.execute(
            "UPDATE chunks SET text = 'injected secret' WHERE document_id = 'doc-chunk'"
        )
        with pytest.raises(LegalPolicyDenied, match="unavailable"):
            read_chunks(con, alice, "doc-chunk")


def test_chunk_cannot_be_replaced_by_a_different_valid_document_substring(tmp_path):
    path = str(tmp_path / "graph.duckdb")
    init_database_at_path(path)
    alice = _authority(tmp_path, "alice")
    with connect_write(path, purpose="legal-read-test") as con:
        _admit_and_write(
            con, alice, document_id="doc-substring", text="first passage second passage"
        )
        con.execute(
            "UPDATE chunks SET text = 'second passage' WHERE document_id = 'doc-substring'"
        )
        with pytest.raises(LegalPolicyDenied, match="unavailable"):
            read_chunks(con, alice, "doc-substring")


@pytest.mark.parametrize(
    "mutation",
    [
        "UPDATE chunks SET chunk_index = 7 WHERE document_id = 'doc-locator'",
        "UPDATE chunks SET section_path = 'forged' WHERE document_id = 'doc-locator'",
        "UPDATE chunks SET token_count = token_count + 1 WHERE document_id = 'doc-locator'",
        "DELETE FROM chunks WHERE document_id = 'doc-locator'",
    ],
)
def test_chunk_manifest_rejects_locator_metadata_mutation_and_deletion(tmp_path, mutation):
    path = str(tmp_path / "graph.duckdb")
    init_database_at_path(path)
    alice = _authority(tmp_path, "alice")
    with connect_write(path, purpose="legal-read-test") as con:
        _admit_and_write(con, alice, document_id="doc-locator", text="canonical body")
        con.execute(mutation)
        with pytest.raises(LegalPolicyDenied, match="unavailable"):
            read_chunks(con, alice, "doc-locator")


def test_strict_keyword_prompt_search_excludes_foreign_and_tampered_chunks(tmp_path):
    path = str(tmp_path / "graph.duckdb")
    init_database_at_path(path)
    alice = _authority(tmp_path, "alice")
    bob = _authority(tmp_path, "bob")
    with connect_write(path, purpose="legal-keyword-test") as con:
        _admit_and_write(con, alice, document_id="alice-doc", text="quantum evidence")
        _admit_and_write(con, bob, document_id="bob-doc", text="quantum foreign")
        rows = keyword_search_chunks_compatibility(
            con,
            ["quantum"],
            top_k=10,
            authority=alice,
            enforce=True,
            legacy_policy_tag="private_research",
        )
        assert [row["document_title"] for row in rows] == [None]
        assert [row["chunk_text"] for row in rows] == ["quantum evidence"]

        con.execute("UPDATE chunks SET text = 'quantum forged' WHERE document_id = 'alice-doc'")
        assert keyword_search_chunks_compatibility(
            con,
            ["quantum"],
            top_k=10,
            authority=alice,
            enforce=True,
            legacy_policy_tag="private_research",
        ) == []


def test_strict_recursive_reuse_is_account_scoped_and_revocation_aware(
    tmp_path, monkeypatch
):
    from substrate.context_pack.knowledge_reuse import retrieve_prior_units
    from substrate.graph.insight_question import promote_insight_authorized

    class Model:
        dimension = 4

        def encode(self, _text):
            return [1.0, 0.0, 0.0, 0.0]

    class Retrieval:
        def __init__(self, con):
            self._con = con
            self._model = Model()

        def query(self, *_args, **_kwargs):
            raise AssertionError("strict reuse must not invoke the global retrieval seam")

    monkeypatch.setenv("ANTIEK_LEGAL_READ_ENFORCEMENT", "1")
    path = str(tmp_path / "graph.duckdb")
    init_database_at_path(path)
    alice = _authority(tmp_path, "alice")
    bob = _authority(tmp_path, "bob")
    with connect_write(path, purpose="legal-reuse-test") as con:
        for authority, document_id, text in (
            (alice, "alice-doc", "quantum evidence supports the claim"),
            (bob, "bob-doc", "quantum foreign private evidence"),
        ):
            _admit_and_write(con, authority, document_id=document_id, text=text)
            chunk_id = read_chunks(con, authority, document_id)[0]["chunk_id"]
            promote_insight_authorized(
                authority,
                text=text,
                source_document_id=document_id,
                chunk_id=chunk_id,
                embedding_provider=Model(),
                con=con,
            )

        units = retrieve_prior_units(
            Retrieval(con),
            question_text="quantum evidence",
            authority=alice,
        )
        assert len(units) == 1
        assert units[0].unit.provenance.source_document_id == "alice-doc"
        assert "foreign" not in units[0].text

        allow_event = con.execute(
            "SELECT event_id FROM legal_policy_events WHERE decision = 'allow' "
            "AND account_digest = ?",
            [account_policy_authority(alice).account_digest],
        ).fetchone()[0]
        append_policy_event(
            con,
            account_policy_authority(alice),
            scope_kind="account",
            matcher_kind="domain",
            matcher_value="example.com",
            decision="revoke",
            citation_ref="reuse-revoked",
            issuer_id="alice-rights",
            reason_code="revoked",
            effective_at=NOW + timedelta(seconds=1),
            supersedes_event_id=allow_event,
        )
        assert retrieve_prior_units(
            Retrieval(con),
            question_text="quantum evidence",
            authority=alice,
        ) == []


def test_backup_restore_preserves_policy_invisibility_and_custody(tmp_path):
    path = str(tmp_path / "graph.duckdb")
    init_database_at_path(path)
    alice = _authority(tmp_path, "alice")
    with connect_write(path, purpose="legal-read-test") as con:
        _admit_and_write(con, alice, document_id="doc-restore", text="retained custody")
        append_policy_event(
            con,
            account_policy_authority(alice),
            scope_kind="account",
            matcher_kind="domain",
            matcher_value="blocked.example",
            decision="deny",
            citation_ref="policy-change",
            issuer_id="alice-rights",
            reason_code="blocked",
            effective_at=NOW,
        )

    restored_db = tmp_path / "restore" / "graph.duckdb"
    restored_db.parent.mkdir()
    shutil.copy2(path, restored_db)
    restored_root = tmp_path / "restored-tenancy"
    shutil.copytree(tmp_path / "tenancy", restored_root)
    restored_authority = InvestigationAuthority(
        "alice", "legal-read", root=restored_root
    )
    with connect_read(str(restored_db)) as con:
        with pytest.raises(LegalPolicyDenied, match="unavailable"):
            read_document(con, restored_authority, "doc-restore")
        assert con.execute(
            "SELECT raw_text FROM documents WHERE document_id = 'doc-restore'"
        ).fetchone() == ("retained custody",)
