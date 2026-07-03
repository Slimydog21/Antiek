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


def _event_log_lines(events_dir: Path) -> int:
    return sum(
        len(p.read_text(encoding="utf-8").splitlines())
        for p in events_dir.rglob("*.jsonl")
    )


def test_inbox_reingest_emits_no_new_events(tmp_path, monkeypatch):
    """glm-cc SPR-05 finding 1: a daily idempotent re-run must NOT append a
    document.loaded event for an already-present document, or the event log
    grows unboundedly on a cron."""
    events = tmp_path / "events"
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", str(events))
    db_path = str(tmp_path / "graph.duckdb")
    inbox = tmp_path / "inbox"
    _seed_inbox(inbox)

    ingest_inbox_dir(inbox, db_path=db_path, embedder=HashEmbedding(16))
    lines_after_first = _event_log_lines(events)
    ingest_inbox_dir(inbox, db_path=db_path, embedder=HashEmbedding(16))
    lines_after_second = _event_log_lines(events)

    assert lines_after_first > 0
    assert lines_after_second == lines_after_first, (
        "re-ingest appended events for already-present docs — event-log idempotency broken"
    )


def test_inbox_empty_file_is_skipped_not_a_ghost_document(tmp_path, monkeypatch):
    """glm-cc SPR-05 finding 4: an empty/whitespace file yields zero chunks;
    it must be a counted skip, never a chunk-less unsearchable document row."""
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", str(tmp_path / "events"))
    db_path = str(tmp_path / "graph.duckdb")
    inbox = tmp_path / "inbox"
    _write(inbox / "2026-07-03" / "empty.txt", "   \n\n  ")
    _write(inbox / "2026-07-03" / "real.txt", "# Real\n\nreal content here")

    summary = ingest_inbox_dir(inbox, db_path=db_path, embedder=HashEmbedding(16))

    assert summary.files_ingested == 1
    assert summary.skipped_by_reason["empty_file"] == 1
    assert _document_count(db_path) == 1  # only the real article, no ghost


def test_inbox_non_utf8_file_falls_back_losslessly(tmp_path, monkeypatch):
    """glm-cc SPR-05 finding 3: a non-UTF-8 file is decoded latin-1 (lossless)
    and tagged, not silently mangled with U+FFFD."""
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", str(tmp_path / "events"))
    db_path = str(tmp_path / "graph.duckdb")
    inbox = tmp_path / "inbox"
    folder = inbox / "2026-07-03"
    folder.mkdir(parents=True)
    # 0xE9 is 'é' in latin-1 but an invalid UTF-8 start byte.
    (folder / "latin.txt").write_bytes(b"caf\xe9 macchiato tasting notes\n\nbody")

    summary = ingest_inbox_dir(inbox, db_path=db_path, embedder=HashEmbedding(16))

    assert summary.files_ingested == 1
    document_id = summary.results[0].document_id
    con = connect_read(db_path)
    try:
        raw = con.execute(
            "SELECT raw_text, metadata FROM documents WHERE document_id = ?",
            [document_id],
        ).fetchone()
    finally:
        con.close()
    assert "�" not in raw[0]  # no replacement chars — lossless
    assert "café" in raw[0]
    assert "latin-1-fallback" in raw[1]  # degradation is recorded, not silent


def test_inbox_adapter_uses_single_writer_only():
    src = Path("acquisition/inbox/adapter.py").read_text(encoding="utf-8")
    assert "connect_write" in src
    assert "duckdb.connect" not in src
