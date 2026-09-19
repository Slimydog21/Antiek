from __future__ import annotations

import duckdb
import pytest

from acquisition.urls import adapter as url_adapter
from acquisition.urls.adapter import ingest_url
from acquisition.urls.client import FetchedHtml
from runtime.db_lock import connect_write
from substrate.graph.schema import init_database_at_path
from substrate.investigation_streams import initialize_composite_stream
from substrate.investigation_tenancy import InvestigationAuthority
from substrate.legal_gate.policy_store import (
    LegalPolicyDenied,
    account_policy_authority,
    append_policy_event,
)
from tests.test_acquisition_urls import _HTML_ARTICLE, _StubEmbedder


def _page() -> FetchedHtml:
    return FetchedHtml(
        requested_url="https://example.com/post",
        final_url="https://example.com/post",
        status_code=200,
        content_type="text/html; charset=utf-8",
        charset="utf-8",
        body=_HTML_ARTICLE,
    )


def _changed_page(marker: bytes = b"replacement hostile") -> FetchedHtml:
    page = _page()
    return FetchedHtml(
        requested_url=page.requested_url,
        final_url=page.final_url,
        status_code=page.status_code,
        content_type=page.content_type,
        charset=page.charset,
        body=_HTML_ARTICLE.replace(b"first substantive", marker),
    )


def _setup(tmp_path, monkeypatch):
    root = tmp_path / "events"
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", str(root))
    monkeypatch.setenv("ANTIEK_READER_SNAPSHOTS_DIR", str(tmp_path / "snapshots"))
    root.mkdir()
    authority = InvestigationAuthority("alice", "inv-url", root=root)
    initialize_composite_stream(authority)
    path = str(tmp_path / "graph.duckdb")
    init_database_at_path(path)
    return path, authority


def _allow_example(path, authority):
    with connect_write(path, purpose="url-legal-test") as con:
        return append_policy_event(
            con,
            account_policy_authority(authority),
            scope_kind="account",
            matcher_kind="domain",
            matcher_value="example.com",
            decision="allow",
            citation_ref="license-1",
            issuer_id=f"{authority.account_id}-rights",
            reason_code="licensed",
            effective_at=__import__("datetime").datetime.now(__import__("datetime").UTC),
        )


def test_authorized_url_deny_persists_only_redacted_receipt(tmp_path, monkeypatch):
    path, authority = _setup(tmp_path, monkeypatch)
    result = ingest_url(
        "https://example.com/post",
        investigation_id="inv-url",
        db_path=path,
        embedder=_StubEmbedder(),
        fetched=_page(),
        authority=authority,
    )
    assert result.skipped_reason == "legal_policy:no_explicit_external_allow"
    assert result.admission_receipt_id is not None
    assert result.document_loaded_event_id is None
    assert result.reader_snapshot_path is None
    with duckdb.connect(path, read_only=True) as con:
        assert con.execute("SELECT count(*) FROM documents").fetchone() == (0,)
        assert con.execute("SELECT count(*) FROM chunks").fetchone() == (0,)
        row = con.execute(
            "SELECT decision, canonical_url_digest, metadata_digest FROM legal_document_admissions"
        ).fetchone()
    assert row is not None and row[0] == "deny"
    assert "Better Title" not in " ".join(row)


def test_authorized_url_allow_commits_receipt_document_and_chunks(tmp_path, monkeypatch):
    path, authority = _setup(tmp_path, monkeypatch)
    with connect_write(path, purpose="url-legal-test") as con:
        append_policy_event(
            con,
            account_policy_authority(authority),
            scope_kind="account",
            matcher_kind="domain",
            matcher_value="example.com",
            decision="allow",
            citation_ref="license-1",
            issuer_id="alice-rights",
            reason_code="licensed",
            effective_at=__import__("datetime").datetime.now(__import__("datetime").UTC),
        )
    result = ingest_url(
        "https://example.com/post",
        investigation_id="inv-url",
        db_path=path,
        embedder=_StubEmbedder(),
        fetched=_page(),
        authority=authority,
    )
    assert result.skipped_reason is None
    assert result.admission_receipt_id is not None
    assert result.document_loaded_event_id is not None
    with duckdb.connect(path, read_only=True) as con:
        assert con.execute("SELECT count(*) FROM legal_document_admissions").fetchone() == (1,)
        assert con.execute("SELECT count(*) FROM documents").fetchone() == (1,)
        assert con.execute("SELECT count(*) FROM chunks").fetchone()[0] > 0


def test_authorized_url_fault_rolls_back_receipt_and_graph_before_event(tmp_path, monkeypatch):
    path, authority = _setup(tmp_path, monkeypatch)
    with connect_write(path, purpose="url-legal-test") as con:
        append_policy_event(
            con,
            account_policy_authority(authority),
            scope_kind="account",
            matcher_kind="domain",
            matcher_value="example.com",
            decision="allow",
            citation_ref="license-1",
            issuer_id="alice-rights",
            reason_code="licensed",
            effective_at=__import__("datetime").datetime.now(__import__("datetime").UTC),
        )

    class FaultingEmbedder:
        def encode(self, _text):
            raise RuntimeError("fault-after-document")

    with pytest.raises(RuntimeError, match="fault-after-document"):
        ingest_url(
            "https://example.com/post",
            investigation_id="inv-url",
            db_path=path,
            embedder=FaultingEmbedder(),
            fetched=_page(),
            authority=authority,
        )
    with duckdb.connect(path, read_only=True) as con:
        assert con.execute("SELECT count(*) FROM legal_document_admissions").fetchone() == (0,)
        assert con.execute("SELECT count(*) FROM documents").fetchone() == (0,)
        assert con.execute("SELECT count(*) FROM chunks").fetchone() == (0,)
    event_bytes = b"".join(
        item.read_bytes() for item in authority.root.rglob("*.jsonl") if item.is_file()
    )
    assert b"document.loaded" not in event_bytes


def test_authorized_reingest_cannot_bypass_existing_document(tmp_path, monkeypatch):
    path, authority = _setup(tmp_path, monkeypatch)
    assert (
        ingest_url(
            "https://example.com/post",
            investigation_id="legacy",
            db_path=path,
            embedder=_StubEmbedder(),
            fetched=_page(),
        ).chunks_written
        > 0
    )
    result = ingest_url(
        "https://example.com/post",
        investigation_id="inv-url",
        db_path=path,
        embedder=_StubEmbedder(),
        fetched=_page(),
        authority=authority,
    )
    assert result.skipped_reason == "legal_policy:no_explicit_external_allow"
    assert result.admission_receipt_id is not None


def test_post_commit_event_failure_returns_explicit_pending_state(tmp_path, monkeypatch):
    path, authority = _setup(tmp_path, monkeypatch)
    with connect_write(path, purpose="url-legal-test") as con:
        append_policy_event(
            con,
            account_policy_authority(authority),
            scope_kind="account",
            matcher_kind="domain",
            matcher_value="example.com",
            decision="allow",
            citation_ref="license-1",
            issuer_id="alice-rights",
            reason_code="licensed",
            effective_at=__import__("datetime").datetime.now(__import__("datetime").UTC),
        )
    monkeypatch.setattr(
        url_adapter,
        "emit_typed",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("event down")),
    )
    result = ingest_url(
        "https://example.com/post",
        investigation_id="inv-url",
        db_path=path,
        embedder=_StubEmbedder(),
        fetched=_page(),
        authority=authority,
    )
    assert result.skipped_reason == "post_commit_publication_pending"
    assert result.admission_receipt_id is not None
    assert result.chunks_written > 0
    with duckdb.connect(path, read_only=True) as con:
        assert con.execute("SELECT count(*) FROM legal_document_admissions").fetchone() == (1,)
        assert con.execute("SELECT count(*) FROM documents").fetchone() == (1,)


def test_authorized_ignore_is_idempotent_and_changed_ignore_does_not_admit(tmp_path, monkeypatch):
    path, authority = _setup(tmp_path, monkeypatch)
    _allow_example(path, authority)
    first = ingest_url(
        "https://example.com/post", investigation_id="inv-url", db_path=path,
        embedder=_StubEmbedder(), fetched=_page(), authority=authority,
    )
    same = ingest_url(
        "https://example.com/post", investigation_id="inv-url", db_path=path,
        embedder=_StubEmbedder(), fetched=_page(), authority=authority,
    )
    changed_page = _changed_page(b"changed hostile")
    changed = ingest_url(
        "https://example.com/post", investigation_id="inv-url", db_path=path,
        embedder=_StubEmbedder(), fetched=changed_page, authority=authority,
    )
    assert same.skipped_reason is None
    assert same.admission_receipt_id == first.admission_receipt_id
    assert changed.skipped_reason == "changed_content_requires_replace"
    with duckdb.connect(path, read_only=True) as con:
        assert con.execute("SELECT count(*) FROM legal_document_admissions").fetchone() == (1,)
        assert "changed hostile" not in con.execute("SELECT raw_text FROM documents").fetchone()[0]


def test_authorized_replace_archives_exact_admitted_manifest(tmp_path, monkeypatch):
    path, authority = _setup(tmp_path, monkeypatch)
    _allow_example(path, authority)
    first = ingest_url(
        "https://example.com/post", investigation_id="inv-url", db_path=path,
        embedder=_StubEmbedder(), fetched=_page(), authority=authority,
    )
    with connect_write(path, purpose="reference-old-chunk") as con:
        for node_id in ("url-source", "url-target"):
            con.execute(
                "INSERT INTO nodes "
                "(node_id, canonical_label, node_type, graph_scope) "
                "VALUES (?, ?, 'entity', 'cross_domain')",
                [node_id, node_id],
            )
        con.execute(
            """INSERT INTO edges (
                   edge_id, source_node_id, target_node_id, relation, chunk_id,
                   source_document_id, source_tier, extraction_confidence,
                   graph_scope, investigation_id
               ) VALUES (?, ?, ?, ?, NULL, ?, 4, 1.0, 'cross_domain', ?)""",
            [
                "document-only-reference",
                "url-source",
                "url-target",
                "supports",
                first.document_id,
                "inv-url",
            ],
        )
        con.execute(
            "INSERT INTO chunk_tier_overrides "
            "(chunk_id, original_tier, override_tier, reason, set_by) "
            "VALUES (?, 4, 2, 'hostile', 'test')",
            [first.chunk_ids[0]],
        )
    changed_page = _changed_page()
    replaced = ingest_url(
        "https://example.com/post", investigation_id="inv-url", db_path=path,
        embedder=_StubEmbedder(), fetched=changed_page, authority=authority,
        on_conflict="replace",
    )
    assert replaced.skipped_reason is None
    with duckdb.connect(path, read_only=True) as con:
        revision_id, receipt_id = con.execute(
            "SELECT document_id, receipt_id FROM legal_document_admissions "
            "WHERE document_id LIKE ? AND decision = 'allow'",
            [f"{first.document_id}::rev::%"],
        ).fetchone()
        manifest = con.execute(
            "SELECT chunk_id, text_sha256 FROM legal_chunk_admissions WHERE receipt_id = ?",
            [receipt_id],
        ).fetchall()
        archived = con.execute(
            "SELECT chunk_id, text FROM chunks WHERE document_id = ? ORDER BY chunk_index",
            [revision_id],
        ).fetchall()
        document_reference = con.execute(
            "SELECT source_document_id FROM edges WHERE edge_id = 'document-only-reference'"
        ).fetchone()[0]
    assert [row[0] for row in manifest] == [row[0] for row in archived]
    assert [row[1] for row in manifest] == [__import__("hashlib").sha256(row[1].encode()).hexdigest() for row in archived]
    assert document_reference == revision_id


def test_authorized_replace_fails_closed_after_policy_revoke(tmp_path, monkeypatch):
    path, authority = _setup(tmp_path, monkeypatch)
    allowed_event_id = _allow_example(path, authority)
    first = ingest_url(
        "https://example.com/post",
        investigation_id="inv-url",
        db_path=path,
        embedder=_StubEmbedder(),
        fetched=_page(),
        authority=authority,
    )
    with connect_write(path, purpose="revoke-url-policy") as con:
        append_policy_event(
            con,
            account_policy_authority(authority),
            scope_kind="account",
            matcher_kind="domain",
            matcher_value="example.com",
            decision="revoke",
            citation_ref="license-revoked",
            issuer_id="alice-rights",
            reason_code="revoked",
            effective_at=__import__("datetime").datetime.now(__import__("datetime").UTC),
            supersedes_event_id=allowed_event_id,
        )
    with pytest.raises(LegalPolicyDenied, match="unavailable"):
        ingest_url(
            "https://example.com/post",
            investigation_id="inv-url",
            db_path=path,
            embedder=_StubEmbedder(),
            fetched=_changed_page(),
            authority=authority,
            on_conflict="replace",
        )
    with duckdb.connect(path, read_only=True) as con:
        assert con.execute("SELECT count(*) FROM legal_document_admissions").fetchone() == (1,)
        assert con.execute("SELECT raw_text FROM documents").fetchone()[0]
        assert con.execute("SELECT count(*) FROM chunks").fetchone()[0] == len(first.chunk_ids)


def test_authorized_replace_rejects_tampered_old_chunk_before_admission(tmp_path, monkeypatch):
    path, authority = _setup(tmp_path, monkeypatch)
    _allow_example(path, authority)
    first = ingest_url(
        "https://example.com/post",
        investigation_id="inv-url",
        db_path=path,
        embedder=_StubEmbedder(),
        fetched=_page(),
        authority=authority,
    )
    with connect_write(path, purpose="tamper-url-chunk") as con:
        con.execute("UPDATE chunks SET text = 'tampered' WHERE chunk_id = ?", [first.chunk_ids[0]])
    with pytest.raises(LegalPolicyDenied, match="unavailable"):
        ingest_url(
            "https://example.com/post",
            investigation_id="inv-url",
            db_path=path,
            embedder=_StubEmbedder(),
            fetched=_changed_page(),
            authority=authority,
            on_conflict="replace",
        )
    with duckdb.connect(path, read_only=True) as con:
        assert con.execute("SELECT count(*) FROM legal_document_admissions").fetchone() == (1,)
        assert con.execute("SELECT count(*) FROM documents").fetchone() == (1,)


def test_foreign_account_cannot_replace_colliding_url_document(tmp_path, monkeypatch):
    path, alice = _setup(tmp_path, monkeypatch)
    _allow_example(path, alice)
    first = ingest_url(
        "https://example.com/post",
        investigation_id="inv-url",
        db_path=path,
        embedder=_StubEmbedder(),
        fetched=_page(),
        authority=alice,
    )
    bob = InvestigationAuthority("bob", "inv-bob", root=alice.root)
    initialize_composite_stream(bob)
    _allow_example(path, bob)
    with pytest.raises(LegalPolicyDenied, match="unavailable"):
        ingest_url(
            "https://example.com/post",
            investigation_id="inv-bob",
            db_path=path,
            embedder=_StubEmbedder(),
            fetched=_changed_page(),
            authority=bob,
            on_conflict="replace",
        )
    with duckdb.connect(path, read_only=True) as con:
        assert con.execute("SELECT count(*) FROM legal_document_admissions").fetchone() == (1,)
        assert con.execute("SELECT count(*) FROM documents").fetchone() == (1,)
        assert con.execute("SELECT count(*) FROM chunks").fetchone()[0] == len(first.chunk_ids)


def test_same_account_other_investigation_cannot_replace(tmp_path, monkeypatch):
    path, owner = _setup(tmp_path, monkeypatch)
    _allow_example(path, owner)
    first = ingest_url(
        "https://example.com/post",
        investigation_id="inv-url",
        db_path=path,
        embedder=_StubEmbedder(),
        fetched=_page(),
        authority=owner,
    )
    sibling = InvestigationAuthority("alice", "inv-sibling", root=owner.root)
    initialize_composite_stream(sibling)
    with pytest.raises(LegalPolicyDenied, match="unavailable"):
        ingest_url(
            "https://example.com/post",
            investigation_id="inv-sibling",
            db_path=path,
            embedder=_StubEmbedder(),
            fetched=_changed_page(),
            authority=sibling,
            on_conflict="replace",
        )
    with duckdb.connect(path, read_only=True) as con:
        assert con.execute("SELECT count(*) FROM documents").fetchone() == (1,)
        assert con.execute("SELECT count(*) FROM chunks").fetchone()[0] == len(first.chunk_ids)


@pytest.mark.parametrize(
    "tamper_sql",
    [
        "DELETE FROM legal_chunk_admissions WHERE chunk_id = ?",
        "UPDATE documents SET title = 'forged title' WHERE document_id = ?",
        "UPDATE documents SET metadata = '{\"forged\":true}' WHERE document_id = ?",
    ],
)
def test_replacement_rejects_truncated_manifest_or_unsealed_metadata(
    tmp_path, monkeypatch, tamper_sql
):
    path, authority = _setup(tmp_path, monkeypatch)
    _allow_example(path, authority)
    first = ingest_url(
        "https://example.com/post",
        investigation_id="inv-url",
        db_path=path,
        embedder=_StubEmbedder(),
        fetched=_page(),
        authority=authority,
    )
    target = first.chunk_ids[0] if tamper_sql.startswith("DELETE") else first.document_id
    with connect_write(path, purpose="tamper-admitted-url-state") as con:
        con.execute(tamper_sql, [target])
    with pytest.raises(LegalPolicyDenied, match="unavailable"):
        ingest_url(
            "https://example.com/post",
            investigation_id="inv-url",
            db_path=path,
            embedder=_StubEmbedder(),
            fetched=_changed_page(),
            authority=authority,
            on_conflict="replace",
        )
    with duckdb.connect(path, read_only=True) as con:
        assert con.execute("SELECT count(*) FROM documents").fetchone() == (1,)


def test_authorized_replace_fault_rolls_back_history_and_new_revision(tmp_path, monkeypatch):
    path, authority = _setup(tmp_path, monkeypatch)
    _allow_example(path, authority)
    first = ingest_url(
        "https://example.com/post",
        investigation_id="inv-url",
        db_path=path,
        embedder=_StubEmbedder(),
        fetched=_page(),
        authority=authority,
    )
    with connect_write(path, purpose="reference-url-chunk") as con:
        con.execute(
            "INSERT INTO chunk_tier_overrides "
            "(chunk_id, original_tier, override_tier, reason, set_by) "
            "VALUES (?, 4, 2, 'rollback-proof', 'test')",
            [first.chunk_ids[0]],
        )

    class FaultingEmbedder:
        def encode(self, _text):
            raise RuntimeError("replacement-embedding-fault")

    with pytest.raises(RuntimeError, match="replacement-embedding-fault"):
        ingest_url(
            "https://example.com/post",
            investigation_id="inv-url",
            db_path=path,
            embedder=FaultingEmbedder(),
            fetched=_changed_page(),
            authority=authority,
            on_conflict="replace",
        )
    with duckdb.connect(path, read_only=True) as con:
        assert con.execute("SELECT count(*) FROM legal_document_admissions").fetchone() == (1,)
        assert con.execute("SELECT count(*) FROM documents").fetchone() == (1,)
        assert con.execute("SELECT count(*) FROM chunks").fetchone()[0] == len(first.chunk_ids)
        assert con.execute("SELECT chunk_id FROM chunk_tier_overrides").fetchone() == (
            first.chunk_ids[0],
        )


def test_replacement_event_failure_cannot_leave_old_html_viewable(tmp_path, monkeypatch):
    path, authority = _setup(tmp_path, monkeypatch)
    _allow_example(path, authority)
    first = ingest_url(
        "https://example.com/post",
        investigation_id="inv-url",
        db_path=path,
        embedder=_StubEmbedder(),
        fetched=_page(),
        authority=authority,
    )
    old_projection = __import__("pathlib").Path(first.reader_snapshot_path or "")
    assert old_projection.is_file()
    monkeypatch.setattr(
        url_adapter,
        "emit_typed",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("event down")),
    )
    result = ingest_url(
        "https://example.com/post",
        investigation_id="inv-url",
        db_path=path,
        embedder=_StubEmbedder(),
        fetched=_changed_page(),
        authority=authority,
        on_conflict="replace",
    )
    assert result.skipped_reason == "post_commit_publication_pending"
    assert not old_projection.exists()
    with duckdb.connect(path, read_only=True) as con:
        assert "replacement hostile" in con.execute(
            "SELECT raw_text FROM documents WHERE document_id = ?", [first.document_id]
        ).fetchone()[0]
