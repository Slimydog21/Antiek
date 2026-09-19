from __future__ import annotations

from datetime import UTC, datetime

import duckdb

from acquisition.arxiv.adapter import ingest_paper
from acquisition.arxiv.client import ArxivPaper
from runtime.db_lock import connect_write
from substrate.graph.schema import init_database_at_path
from substrate.investigation_streams import initialize_composite_stream
from substrate.investigation_tenancy import InvestigationAuthority
from substrate.legal_gate.policy_store import account_policy_authority, append_policy_event


class StubEmbedder:
    def encode(self, _text):
        return [0.1, 0.2, 0.3]


def _paper() -> ArxivPaper:
    now = datetime(2026, 7, 15, tzinfo=UTC)
    return ArxivPaper(
        arxiv_id="2607.12345",
        version="v1",
        title="A private test of research systems",
        authors=["Ada Researcher"],
        abstract="A substantial abstract about knowledge systems. " * 40,
        categories=["cs.IR"],
        primary_category="cs.IR",
        published_at=now,
        updated_at=now,
        abs_url="https://arxiv.org/abs/2607.12345",
        pdf_url="https://arxiv.org/pdf/2607.12345",
    )


def _setup(tmp_path, monkeypatch):
    root = tmp_path / "events"
    root.mkdir()
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", str(root))
    authority = InvestigationAuthority("alice", "arxiv-inv", root=root)
    initialize_composite_stream(authority)
    path = str(tmp_path / "graph.duckdb")
    init_database_at_path(path)
    return path, authority


def test_arxiv_denial_does_not_persist_abstract_or_metadata(tmp_path, monkeypatch):
    path, authority = _setup(tmp_path, monkeypatch)
    result = ingest_paper(
        _paper(),
        investigation_id=authority.investigation_id,
        db_path=path,
        embedder=StubEmbedder(),
        authority=authority,
    )
    assert result.status == "skipped"
    assert result.skipped_reason == "legal_policy:no_explicit_external_allow"
    assert result.document_loaded_event_id is None
    with duckdb.connect(path, read_only=True) as con:
        assert con.execute("SELECT count(*) FROM documents").fetchone() == (0,)
        assert con.execute("SELECT count(*) FROM chunks").fetchone() == (0,)
        assert con.execute("SELECT decision FROM legal_document_admissions").fetchone() == ("deny",)


def test_arxiv_allow_commits_owner_receipt_document_and_chunks(tmp_path, monkeypatch):
    path, authority = _setup(tmp_path, monkeypatch)
    with connect_write(path, purpose="arxiv-legal-test") as con:
        append_policy_event(
            con,
            account_policy_authority(authority),
            scope_kind="account",
            matcher_kind="domain",
            matcher_value="arxiv.org",
            decision="allow",
            citation_ref="research-license-1",
            issuer_id="alice-rights",
            reason_code="research-use",
            effective_at=datetime.now(UTC),
        )
    result = ingest_paper(
        _paper(),
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
