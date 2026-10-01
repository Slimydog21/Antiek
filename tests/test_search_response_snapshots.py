"""Direct search callers keep dependent reads on one actual DB snapshot."""

from __future__ import annotations

import importlib
from typing import Any

import pytest
from test_owner_scoped_http_retrieval import (
    _ALICE,
    _BOB,
    StubEmbedding,
    _setup_http,
)

from runtime.db_lock import connect_write
from substrate.graph.ops import insert_chunk, insert_document, insert_edge, insert_node


@pytest.fixture
def search_fixture(monkeypatch: pytest.MonkeyPatch, tmp_path):
    client, owners, cookies, _provider, db_path, reset = _setup_http(
        monkeypatch, tmp_path, operator_emails=(_ALICE, _BOB),
    )
    con = connect_write(db_path, purpose="snapshot-public-seed")
    try:
        insert_document(
            con, document_id="public-snapshot", source_tier=2,
            document_type="book", title="Public Before", raw_text="snapshot word",
            content_class="public_domain",
        )
        chunk_id = insert_chunk(
            con, document_id="public-snapshot", chunk_index=0,
            text="snapshot word", section_path="Page 1", token_count=2,
            embedding=StubEmbedding().encode("snapshot word"),
        )
        source_id = insert_node(
            con, canonical_label="Snapshot Source", node_type="entity",
            graph_scope="cross_domain", investigation_id="synthetic-snapshot",
            emit_event=False,
        )
        target_id = insert_node(
            con, canonical_label="Snapshot Target", node_type="entity",
            graph_scope="cross_domain", investigation_id="synthetic-snapshot",
            emit_event=False,
        )
        insert_edge(
            con, source_node_id=source_id, target_node_id=target_id,
            relation="links", source_tier=2, extraction_confidence=0.9,
            graph_scope="cross_domain", investigation_id="synthetic-snapshot",
            chunk_id=chunk_id, source_document_id="public-snapshot",
            emit_event=False,
        )
    finally:
        con.close()
    yield client, owners, cookies, db_path
    reset()


def _interleave_after_first_read(
    monkeypatch: pytest.MonkeyPatch, writer: Any,
) -> list[bool]:
    graph_search = importlib.import_module("substrate.graph.search")
    original = graph_search.assert_embedding_compatible
    changed: list[bool] = []

    def after_metadata_read(con: Any, provider: Any, **kwargs: Any) -> None:
        assert type(con).__name__ == "_ReadOrientedConnection"
        original(con, provider, **kwargs)
        if not changed:
            writer.execute(
                "UPDATE documents SET title=?, content_class=? WHERE document_id=?",
                ["Public After", "research_only", "public-snapshot"],
            )
            changed.append(True)

    monkeypatch.setattr(graph_search, "assert_embedding_compatible", after_metadata_read)
    return changed


def test_signed_corpus_search_keeps_old_snapshot_then_next_request_sees_commit(
    search_fixture, monkeypatch: pytest.MonkeyPatch,
):
    client, _owners, cookies, db_path = search_fixture
    # Holding the canonical RW handle makes connect_read choose its guarded
    # same-configuration fallback. The hook writes after a real metadata
    # SELECT but before the ranked chunk/title SELECT.
    writer = connect_write(db_path, purpose="snapshot-corpus-interleave")
    try:
        changed = _interleave_after_first_read(monkeypatch, writer)
        first = client.get(
            "/corpus/search", params={"q": "snapshot word"},
            cookies=cookies[_ALICE],
        )
        assert first.status_code == 200, first.text
        assert changed == [True]
        first_hit = next(
            hit for hit in first.json()["hits"]
            if hit["document_id"] == "public-snapshot"
        )
        assert first_hit["document_title"] == "Public Before"
        assert "private-a" in {h["document_id"] for h in first.json()["hits"]}
        assert "private-b" not in {h["document_id"] for h in first.json()["hits"]}
        persisted = writer.execute(
            "SELECT title,content_class FROM documents WHERE document_id='public-snapshot'"
        ).fetchone()
        assert persisted == ("Public After", "research_only")
        second = client.get(
            "/corpus/search", params={"q": "snapshot word"},
            cookies=cookies[_BOB],
        )
        assert second.status_code == 200, second.text
        assert "public-snapshot" not in {
            hit["document_id"] for hit in second.json()["hits"]
        }
        assert "private-a" not in {h["document_id"] for h in second.json()["hits"]}
    finally:
        writer.close()


def test_public_rlm_keeps_old_snapshot_then_next_tool_call_sees_commit(
    search_fixture, monkeypatch: pytest.MonkeyPatch,
):
    _client, _owners, _cookies, db_path = search_fixture
    graph = importlib.import_module("substrate.graph")
    rlm = importlib.import_module("substrate.graph.rlm_tools")
    monkeypatch.setattr(graph, "ensure_initialized", lambda _path: None)
    monkeypatch.setattr(graph, "default_db_path", lambda: db_path)
    graph_search = importlib.import_module("substrate.graph.search")
    monkeypatch.setattr(graph_search, "SentenceTransformerEmbedding", StubEmbedding)
    writer = connect_write(db_path, purpose="snapshot-rlm-interleave")
    try:
        changed = _interleave_after_first_read(monkeypatch, writer)
        first = rlm.search_graph("snapshot word", top_k=5)
        assert changed == [True]
        assert "Public Before" in first
        assert "Public After" not in first
        assert "Snapshot Source" in first
        assert "Snapshot Target" in first
        assert "links" in first
        assert writer.execute(
            "SELECT title,content_class FROM documents WHERE document_id='public-snapshot'"
        ).fetchone() == ("Public After", "research_only")
        second = rlm.search_graph("snapshot word", top_k=5)
        assert "Public Before" not in second
        assert "Public After" not in second
        assert "Snapshot Source" not in second
        assert "Snapshot Target" not in second
        assert "PRIVATE_A_MARKER" not in second
        assert "PRIVATE_B_MARKER" not in second
    finally:
        writer.close()


@pytest.mark.parametrize("caller", ["corpus", "rlm"])
def test_true_read_only_mode_returns_public_result(
    search_fixture, monkeypatch: pytest.MonkeyPatch, caller: str,
):
    client, _owners, cookies, db_path = search_fixture
    db_lock = importlib.import_module("runtime.db_lock")
    original_connect_read = db_lock.connect_read
    actual_reads: list[str] = []

    def observe_read(path: str) -> Any:
        con = original_connect_read(path)
        if path == db_path:
            actual_reads.append(type(con).__name__)
            assert type(con).__name__ == "DuckDBPyConnection"
        return con

    # Patch only the invocation below. Both callers import connect_read inside
    # the target function; observing a separate preflight handle proves nothing.
    monkeypatch.setattr(db_lock, "connect_read", observe_read)
    if caller == "corpus":
        response = client.get(
            "/corpus/search", params={"q": "snapshot word"},
            cookies=cookies[_ALICE],
        )
        assert response.status_code == 200, response.text
        assert "public-snapshot" in {h["document_id"] for h in response.json()["hits"]}
    else:
        graph = importlib.import_module("substrate.graph")
        monkeypatch.setattr(graph, "default_db_path", lambda: db_path)
        monkeypatch.setattr(graph, "ensure_initialized", lambda _path: None)
        graph_search = importlib.import_module("substrate.graph.search")
        monkeypatch.setattr(graph_search, "SentenceTransformerEmbedding", StubEmbedding)
        result = importlib.import_module("substrate.graph.rlm_tools").search_graph(
            "snapshot word"
        )
        assert "Public Before" in result
        assert "PRIVATE_A_MARKER" not in result
    assert actual_reads == ["DuckDBPyConnection"]

@pytest.mark.parametrize("caller", ["corpus", "rlm"])
@pytest.mark.parametrize("close_fails", [False, True])
def test_search_failure_rolls_back_closes_and_preserves_error_contract(
    search_fixture, monkeypatch: pytest.MonkeyPatch, caller: str,
    close_fails: bool,
):
    client, _owners, cookies, db_path = search_fixture
    db_lock = importlib.import_module("runtime.db_lock")
    graph = importlib.import_module("substrate.graph")
    graph_search = importlib.import_module("substrate.graph.search")
    original_connect_read = db_lock.connect_read
    commands: list[str] = []
    closed: list[bool] = []

    class RecordedRead:
        def __init__(self, real: Any) -> None:
            self.real = real

        def execute(self, sql: str, *args: Any) -> Any:
            commands.append(sql)
            return self.real.execute(sql, *args)

        def close(self) -> None:
            closed.append(True)
            self.real.close()
            if close_fails:
                raise RuntimeError("synthetic close failure")

    monkeypatch.setattr(
        db_lock, "connect_read", lambda path: RecordedRead(original_connect_read(path)),
    )

    def query_failed(*_args: Any, **_kwargs: Any) -> Any:
        raise RuntimeError("synthetic query failure")

    monkeypatch.setattr(graph_search, "search", query_failed)
    if caller == "corpus":
        with pytest.raises(RuntimeError, match="synthetic query failure"):
            client.get(
                "/corpus/search", params={"q": "snapshot word"},
                cookies=cookies[_ALICE],
            )
    else:
        monkeypatch.setattr(graph, "default_db_path", lambda: db_path)
        monkeypatch.setattr(graph_search, "SentenceTransformerEmbedding", StubEmbedding)
        result = importlib.import_module("substrate.graph.rlm_tools").search_graph(
            "snapshot word"
        )
        assert result == "search_graph error: RuntimeError('synthetic query failure')"
    assert commands == ["BEGIN TRANSACTION", "ROLLBACK"]
    assert closed == [True]
