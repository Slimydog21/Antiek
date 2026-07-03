from __future__ import annotations

from datetime import date
from pathlib import Path

from acquisition.inbox import ingest_inbox_dir
from processing.chunking.chunker import content_hash
from processing.embedding.embed import HashEmbedding
from runtime.db_lock import connect_read
from substrate.graph.search import search


def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _document_count(db_path: str) -> int:
    con = connect_read(db_path)
    try:
        return con.execute("SELECT COUNT(*) FROM documents").fetchone()[0]
    finally:
        con.close()


def _seed_inbox(root: Path) -> str:
    phrase = "heliotrope telemetry checksum alpha"
    _write(
        root / "2026-07-03" / "source-topic.txt",
        f"# Inbox Article\n\nThe distinctive phrase is {phrase} in this article.",
    )
    return phrase


def test_inbox_ingest_is_idempotent_and_content_addressed(tmp_path, monkeypatch):
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", str(tmp_path / "events"))
    db_path = str(tmp_path / "graph.duckdb")
    inbox = tmp_path / "inbox"
    body = "# Same Body\n\nsame content survives path changes"
    first = _write(inbox / "2026-07-02" / "first-name.txt", body)
    _write(inbox / "2026-07-03" / "second-name.txt", body)

    summary1 = ingest_inbox_dir(inbox, db_path=db_path, embedder=HashEmbedding(16))
    count_after_first = _document_count(db_path)
    summary2 = ingest_inbox_dir(inbox, db_path=db_path, embedder=HashEmbedding(16))
    count_after_second = _document_count(db_path)

    expected_id = f"inbox:{content_hash(first.read_text(encoding='utf-8'))}"
    assert count_after_first == 1
    assert count_after_second == count_after_first
    assert summary1.files_ingested == 1
    assert summary1.duplicates_skipped == 1
    assert summary2.files_ingested == 0
    assert summary2.duplicates_skipped == 2
    assert {r.document_id for r in summary1.results + summary2.results} == {expected_id}


def test_inbox_ingest_sets_personal_reading_content_class(tmp_path, monkeypatch):
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", str(tmp_path / "events"))
    db_path = str(tmp_path / "graph.duckdb")
    inbox = tmp_path / "inbox"
    _seed_inbox(inbox)

    summary = ingest_inbox_dir(inbox, db_path=db_path, embedder=HashEmbedding(16))
    document_id = summary.results[0].document_id

    con = connect_read(db_path)
    try:
        content_class = con.execute(
            "SELECT content_class FROM documents WHERE document_id = ?",
            [document_id],
        ).fetchone()[0]
    finally:
        con.close()
    assert content_class == "personal_reading"


def test_inbox_ingest_is_searchable_on_owner_privileged_path(tmp_path, monkeypatch):
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", str(tmp_path / "events"))
    db_path = str(tmp_path / "graph.duckdb")
    inbox = tmp_path / "inbox"
    phrase = _seed_inbox(inbox)
    embedder = HashEmbedding(32)

    summary = ingest_inbox_dir(inbox, db_path=db_path, embedder=embedder)
    document_id = summary.results[0].document_id

    con = connect_read(db_path)
    try:
        chunk_count, embedded_count = con.execute(
            "SELECT COUNT(*), COUNT(embedding) FROM chunks WHERE document_id = ?",
            [document_id],
        ).fetchone()
        res = search(
            con,
            phrase,
            model=embedder,
            top_k=3,
            policy_tag="operator_only",
        )
    finally:
        con.close()

    assert chunk_count > 0
    assert embedded_count == chunk_count
    assert any(document_id == hit["document_id"] for hit in res["results"])


def test_inbox_dir_counts_skips_honestly(tmp_path, monkeypatch):
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", str(tmp_path / "events"))
    db_path = str(tmp_path / "graph.duckdb")
    inbox = tmp_path / "inbox"
    _write(inbox / "not-a-date" / "article.txt", "ignored because folder is not dated")
    _write(inbox / "2026-07-03" / "article.pdf", "unsupported")
    _write(inbox / "2026-07-03" / "article.txt", "supported")

    summary = ingest_inbox_dir(
        inbox,
        since=date(2026, 7, 1),
        db_path=db_path,
        embedder=HashEmbedding(16),
    )

    assert summary.folders_scanned == 1
    assert summary.files_ingested == 1
    assert summary.files_skipped == 2
    assert summary.skipped_by_reason["unparseable_folder_name"] == 1
    assert summary.skipped_by_reason["unsupported_extension"] == 1


def test_inbox_adapter_uses_single_writer_only():
    src = Path("acquisition/inbox/adapter.py").read_text(encoding="utf-8")
    assert "connect_write" in src
    assert "duckdb.connect" not in src
