from __future__ import annotations

from datetime import UTC, datetime

import duckdb

from acquisition.substack.adapter import ingest_post
from acquisition.substack.client import Post, Publication
from runtime.db_lock import connect_write
from substrate.graph.schema import init_database_at_path
from substrate.investigation_streams import initialize_composite_stream
from substrate.investigation_tenancy import InvestigationAuthority
from substrate.legal_gate.policy_store import account_policy_authority, append_policy_event


class StubEmbedder:
    def encode(self, _text):
        return [0.1, 0.2, 0.3]


def _post() -> Post:
    body = "# Essay\n\n" + "Substantive newsletter research sentence. " * 80
    return Post(
        guid="substack-legal-1",
        title="Private newsletter title",
        body_html=f"<article>{body}</article>",
        body_markdown=body,
        published_at=datetime(2026, 7, 15, tzinfo=UTC),
        post_url="https://writer.substack.com/p/research",
        author="Writer",
    )


def _setup(tmp_path, monkeypatch):
    root = tmp_path / "events"
    root.mkdir()
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", str(root))
    authority = InvestigationAuthority("alice", "substack-inv", root=root)
    initialize_composite_stream(authority)
    path = str(tmp_path / "graph.duckdb")
    init_database_at_path(path)
    publication = Publication(
        feed_url="https://writer.substack.com/feed",
        title="Writer publication",
        posts=[_post()],
    )
    return path, authority, publication


def test_substack_denial_retains_only_redacted_receipt(tmp_path, monkeypatch):
    path, authority, publication = _setup(tmp_path, monkeypatch)
    result = ingest_post(
        publication.posts[0],
        publication=publication,
        investigation_id=authority.investigation_id,
        db_path=path,
        embedder=StubEmbedder(),
        authority=authority,
    )
    assert result.status == "skipped"
    assert result.skipped_reason == "legal_policy:no_explicit_external_allow"
    assert result.title is None
    assert result.document_loaded_event_id is None
    with duckdb.connect(path, read_only=True) as con:
        assert con.execute("SELECT count(*) FROM documents").fetchone() == (0,)
        assert con.execute("SELECT count(*) FROM chunks").fetchone() == (0,)
        row = con.execute(
            "SELECT decision, canonical_url_digest, metadata_digest FROM legal_document_admissions"
        ).fetchone()
    assert row is not None and row[0] == "deny"
    assert "newsletter" not in " ".join(row).lower()


def test_substack_allow_commits_receipt_document_and_chunks(tmp_path, monkeypatch):
    path, authority, publication = _setup(tmp_path, monkeypatch)
    with connect_write(path, purpose="substack-legal-test") as con:
        append_policy_event(
            con,
            account_policy_authority(authority),
            scope_kind="account",
            matcher_kind="domain",
            matcher_value="writer.substack.com",
            decision="allow",
            citation_ref="subscription-1",
            issuer_id="alice-rights",
            reason_code="personal-subscription",
            effective_at=datetime.now(UTC),
        )
    result = ingest_post(
        publication.posts[0],
        publication=publication,
        investigation_id=authority.investigation_id,
        db_path=path,
        embedder=StubEmbedder(),
        authority=authority,
    )
    assert result.status == "ingested"
    assert result.admission_receipt_id is not None
    assert result.document_loaded_event_id is not None
    with duckdb.connect(path, read_only=True) as con:
        assert con.execute("SELECT count(*) FROM legal_document_admissions").fetchone() == (1,)
        assert con.execute("SELECT count(*) FROM documents").fetchone() == (1,)
        assert con.execute("SELECT count(*) FROM chunks").fetchone()[0] > 0
