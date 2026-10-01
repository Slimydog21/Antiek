"""Ordinary fixed-candidate proof for BF/VSS read snapshots."""

from __future__ import annotations

import importlib
from concurrent.futures import ThreadPoolExecutor
from typing import Any

import duckdb
import pytest

from processing.embedding.embed import HashEmbedding
from runtime.db_lock import connect_read, connect_write
from substrate.graph import init_database_at_path
from substrate.graph.ops import insert_chunk, insert_document, insert_edge, insert_node
from substrate.graph.retrieval_substrate import (
    BruteForceSubstrate,
    DuckDbVssSubstrate,
    SnapshotBusyError,
    SnapshotClosedError,
    SnapshotReadableSubstrate,
)


class CountingHash(HashEmbedding):
    def __init__(self) -> None:
        super().__init__(dimension=4)
        self.calls = 0

    def encode(self, text: str) -> list[float]:
        self.calls += 1
        return super().encode(text)


@pytest.fixture
def graph_db(tmp_path):
    path = str(tmp_path / "graph.duckdb")
    init_database_at_path(path)
    model = CountingHash()
    con = connect_write(path, purpose="adapter-snapshot-seed")
    try:
        docs = [
            ("public", "public_domain", "public-owner"),
            ("licensed", "opt_in_licensed", "public-owner"),
            ("private-a", "user_authored_private", "owner-a"),
            ("private-b", "user_authored_private", "owner-b"),
            ("personal-a", "personal_reading", "owner-a"),
            ("personal-b", "personal_reading", "owner-b"),
            ("restricted", "restricted_pending_opt_in", "owner-a"),
            ("research", "research_only", "public-owner"),
            ("taken", "public_domain", "public-owner"),
        ]
        for document_id, content_class, owner in docs:
            text = f"snapshot common {document_id}"
            insert_document(
                con, document_id=document_id, source_tier=2,
                document_type="book", title=f"Before {document_id}",
                raw_text=text, content_class=content_class, owner_user_id=owner,
            )
            insert_chunk(
                con, document_id=document_id, chunk_index=0, text=text,
                section_path="Page 1", token_count=3,
                embedding=model.encode(text), embedding_provider=model,
            )
        con.execute(
            "INSERT INTO book_assets (document_id,taken_down) VALUES ('taken',TRUE)"
        )
        con.execute("ALTER TABLE chunks ADD COLUMN embedding_vss FLOAT[4]")
        con.execute("UPDATE chunks SET embedding_vss=embedding::FLOAT[4]")
        public_chunk = con.execute(
            "SELECT chunk_id FROM chunks WHERE document_id='public'"
        ).fetchone()[0]
        source = insert_node(
            con, canonical_label="Snapshot Source", node_type="entity",
            graph_scope="cross_domain", investigation_id="synthetic",
            emit_event=False,
        )
        target = insert_node(
            con, canonical_label="Snapshot Target", node_type="entity",
            graph_scope="cross_domain", investigation_id="synthetic",
            emit_event=False,
        )
        insert_edge(
            con, source_node_id=source, target_node_id=target,
            relation="links", source_tier=2, extraction_confidence=0.9,
            graph_scope="cross_domain", investigation_id="synthetic",
            chunk_id=public_chunk, source_document_id="public", emit_event=False,
        )
    finally:
        con.close()
    model.calls = 0
    return path, model


def _ids(result: dict[str, Any]) -> set[str]:
    return {row["document_id"] for row in result["results"]}


@pytest.mark.parametrize("kind", ["bf", "vss_fallback", "vss_sql"])
def test_adapter_policy_and_original_model_identity(graph_db, kind: str):
    path, model = graph_db
    con = connect_read(path)
    sub = (
        BruteForceSubstrate(con, model=model) if kind == "bf"
        else DuckDbVssSubstrate(con, model=model, vss_active=kind == "vss_sql")
    )
    try:
        assert isinstance(sub, SnapshotReadableSubstrate)
        with sub.query_snapshot(
            "snapshot common", top_k=20, policy_tag="owner_scoped",
            owner_user_id="owner-a",
        ) as snap:
            assert snap.con is con
            assert snap.query_vector is not None
            assert model.calls == 1
            assert {"public", "licensed", "private-a", "personal-a"} <= _ids(snap.result)
            assert not {"private-b", "personal-b", "restricted", "research", "taken"} & _ids(snap.result)
            assert con.execute("SELECT title FROM documents WHERE document_id='public'").fetchone() == ("Before public",)
        assert model.calls == 1
        assert "public" in _ids(sub.query("snapshot common", top_k=20))
        assert model.calls == 2
        assert not {"private-a", "private-b", "personal-a", "personal-b"} & _ids(
            sub.query("snapshot common", top_k=20)
        )
    finally:
        sub.close()


@pytest.mark.parametrize("kind", ["bf", "vss_fallback", "vss_sql"])
def test_stored_cursor_keeps_one_snapshot_across_result_and_followup(
    graph_db, monkeypatch: pytest.MonkeyPatch, kind: str,
):
    path, model = graph_db
    writer = connect_write(path, purpose="adapter-snapshot-interleave")
    sub = (
        BruteForceSubstrate.from_con(writer, model=model) if kind == "bf"
        else DuckDbVssSubstrate.from_con(writer, model=model)
        if kind == "vss_fallback"
        else DuckDbVssSubstrate(writer.cursor(), model=model, vss_active=True)
    )
    search_mod = importlib.import_module("substrate.graph.search")
    adapter_mod = importlib.import_module("substrate.graph.retrieval_substrate")
    module = adapter_mod if kind == "vss_sql" else search_mod
    original = module.assert_embedding_compatible
    changed: list[bool] = []

    def after_metadata_read(con: Any, provider: Any, **kwargs: Any) -> None:
        assert con is sub._con
        assert con is not writer
        assert provider is model
        original(con, provider, **kwargs)
        if not changed:
            writer.execute(
                "UPDATE documents SET title='After public',content_class='research_only' "
                "WHERE document_id='public'"
            )
            changed.append(True)

    monkeypatch.setattr(module, "assert_embedding_compatible", after_metadata_read)
    try:
        with sub.query_snapshot("snapshot common", top_k=20) as snap:
            assert changed == [True]
            assert "public" in _ids(snap.result)
            assert next(r for r in snap.result["results"] if r["document_id"] == "public")["document_title"] == "Before public"
            assert snap.con.execute(
                "SELECT title,content_class FROM documents WHERE document_id='public'"
            ).fetchone() == ("Before public", "public_domain")
            with pytest.raises(SnapshotBusyError):
                sub.close()
            with pytest.raises(SnapshotBusyError):
                sub.query("snapshot common")
        assert writer.execute(
            "SELECT title,content_class FROM documents WHERE document_id='public'"
        ).fetchone() == ("After public", "research_only")
        assert "public" not in _ids(sub.query("snapshot common", top_k=20))
    finally:
        sub.close()
        writer.close()


def test_prepared_search_encodes_before_begin_once(graph_db, monkeypatch):
    path, model = graph_db
    events: list[str] = []
    original_encode = model.encode

    def recording_encode(text: str) -> list[float]:
        events.append("encode")
        return original_encode(text)

    class RecordingRead:
        def __init__(self, con: Any) -> None:
            self.con = con

        def execute(self, sql: str, *args: Any) -> Any:
            if sql == "BEGIN TRANSACTION":
                events.append("begin")
            return self.con.execute(sql, *args)

        def __getattr__(self, name: str) -> Any:
            return getattr(self.con, name)

    monkeypatch.setattr(model, "encode", recording_encode)
    sub = BruteForceSubstrate(RecordingRead(connect_read(path)), model=model)
    try:
        assert "public" in _ids(sub.query("snapshot common", top_k=20))
        assert events == ["encode", "begin"]
        assert model.calls == 1
    finally:
        sub.close()


def test_open_uses_native_read_only_handle_when_quiescent(graph_db):
    path, model = graph_db
    sub = BruteForceSubstrate.open(path, model=model)
    try:
        assert isinstance(sub._con, duckdb.DuckDBPyConnection)
        with sub.query_snapshot("snapshot common", top_k=20) as snap:
            assert snap.con is sub._con
            assert "public" in _ids(snap.result)
        assert "public" in _ids(sub.query("snapshot common", top_k=20))
    finally:
        sub.close()


def test_empty_scope_keeps_transaction_without_encoding(graph_db):
    path, model = graph_db
    sub = BruteForceSubstrate.open(path, model=model)
    try:
        with sub.query_snapshot("snapshot common", document_ids=[]) as snap:
            assert snap.query_vector is None
            assert snap.result == {
                "query": "snapshot common", "top_k": 5,
                "results": [], "node_matches": [],
            }
            assert model.calls == 0
            assert snap.con.execute("SELECT 1").fetchone() == (1,)
        assert "public" in _ids(sub.query("snapshot common", top_k=20))
        assert model.calls == 1
    finally:
        sub.close()


def test_empty_scope_owns_normal_transaction_on_stored_handle():
    con = FakeRead()
    model = CountingHash()
    sub = BruteForceSubstrate(con, model=model)
    with sub.query_snapshot("fixed", document_ids=[]) as snap:
        assert snap.con is con
        assert snap.query_vector is None
        assert snap.result["results"] == []
        assert con.commands == ["BEGIN TRANSACTION"]
    assert con.commands == ["BEGIN TRANSACTION", "COMMIT"]
    assert model.calls == 0
    sub.close()


def test_active_vss_compatibility_uses_exact_eligible_sized_rows(graph_db):
    path, model = graph_db
    writer = connect_write(path, purpose="adapter-snapshot-metadata")
    try:
        writer.execute(
            "UPDATE embeddings_meta SET fingerprint='other' WHERE chunk_id="
            "(SELECT chunk_id FROM chunks WHERE document_id='private-b')"
        )
    finally:
        writer.close()
    sub = DuckDbVssSubstrate.open(path, model=model)
    # Exercise the active SQL path without installing or claiming HNSW.
    sub.vss_active = True
    sub._emb_col = "embedding_vss"
    try:
        assert "public" in _ids(sub.query("snapshot common", top_k=20))
        assert "private-b" not in _ids(sub.query("snapshot common", top_k=20))
    finally:
        sub.close()
    writer = connect_write(path, purpose="adapter-snapshot-sized-null")
    try:
        writer.execute(
            "UPDATE chunks SET embedding_vss=NULL WHERE document_id='licensed'"
        )
        writer.execute(
            "UPDATE embeddings_meta SET fingerprint='other' WHERE chunk_id="
            "(SELECT chunk_id FROM chunks WHERE document_id='licensed')"
        )
    finally:
        writer.close()
    sub = DuckDbVssSubstrate(connect_read(path), model=model, vss_active=True)
    try:
        assert "public" in _ids(sub.query("snapshot common", top_k=20))
        assert "licensed" not in _ids(sub.query("snapshot common", top_k=20))
    finally:
        sub.close()
    writer = connect_write(path, purpose="adapter-snapshot-metadata-eligible")
    try:
        writer.execute(
            "UPDATE embeddings_meta SET fingerprint='other' WHERE chunk_id="
            "(SELECT chunk_id FROM chunks WHERE document_id='public')"
        )
    finally:
        writer.close()
    sub = DuckDbVssSubstrate(connect_read(path), model=model, vss_active=True)
    try:
        with pytest.raises(ValueError, match="Stored chunk embeddings are pinned"):
            sub.query("snapshot common", top_k=20)
        assert "private-a" in _ids(sub.query(
            "snapshot common", top_k=20, document_ids=["private-a"],
            policy_tag="owner_scoped", owner_user_id="owner-a",
        ))
    finally:
        sub.close()

class FakeRead:
    def __init__(self, *, fail_on: str | None = None, close_fails: bool = False) -> None:
        self.fail_on = fail_on
        self.close_fails = close_fails
        self.commands: list[str] = []
        self.close_count = 0

    def execute(self, sql: str, *_args: Any) -> FakeRead:
        self.commands.append(sql)
        if self.fail_on == sql:
            self.fail_on = None
            raise RuntimeError(f"synthetic {sql} failure")
        return self

    def close(self) -> None:
        self.close_count += 1
        if self.close_fails:
            raise RuntimeError("synthetic close failure")


def _fake_sub(con: FakeRead) -> BruteForceSubstrate:
    sub = BruteForceSubstrate(con, model=CountingHash())
    sub._query_prepared = lambda *_args, **_kwargs: {
        "query": "fixed", "top_k": 5, "results": [], "node_matches": [],
    }
    return sub


def test_begin_failure_does_not_rollback_or_poison():
    con = FakeRead(fail_on="BEGIN TRANSACTION")
    sub = _fake_sub(con)
    with pytest.raises(RuntimeError, match="synthetic BEGIN TRANSACTION failure"):
        sub.query("fixed")
    assert con.commands == ["BEGIN TRANSACTION"]
    assert con.close_count == 0
    assert sub.query("fixed")["query"] == "fixed"
    assert con.commands[-2:] == ["BEGIN TRANSACTION", "COMMIT"]
    sub.close()
    assert con.close_count == 1


def test_body_failure_rolls_back_and_handle_remains_reusable():
    con = FakeRead()
    sub = _fake_sub(con)
    with pytest.raises(RuntimeError, match="synthetic body failure"), sub.query_snapshot("fixed"):
        raise RuntimeError("synthetic body failure")
    assert con.commands == ["BEGIN TRANSACTION", "ROLLBACK"]
    assert con.close_count == 0
    assert sub.query("fixed")["query"] == "fixed"
    assert con.commands[-2:] == ["BEGIN TRANSACTION", "COMMIT"]
    sub.close()


@pytest.mark.parametrize("failing_sql", ["COMMIT", "ROLLBACK"])
def test_uncertain_transaction_poisons_and_closes_preserving_primary(
    failing_sql: str,
):
    con = FakeRead(fail_on=failing_sql, close_fails=True)
    sub = _fake_sub(con)
    if failing_sql == "COMMIT":
        with pytest.raises(RuntimeError, match="synthetic COMMIT failure") as exc:
            sub.query("fixed")
        assert con.commands == ["BEGIN TRANSACTION", "COMMIT", "ROLLBACK"]
    else:
        with pytest.raises(RuntimeError, match="synthetic body failure") as exc, sub.query_snapshot("fixed"):
            raise RuntimeError("synthetic body failure")
        assert con.commands == ["BEGIN TRANSACTION", "ROLLBACK"]
        assert any("rollback also failed" in note for note in exc.value.__notes__)
    assert any("close also failed" in note for note in exc.value.__notes__)
    assert con.close_count == 1
    with pytest.raises(SnapshotClosedError):
        sub.query("fixed")
    sub.close()
    assert con.close_count == 1


def test_commit_and_rollback_failures_preserve_commit_as_primary():
    class DoubleFailure(FakeRead):
        def execute(self, sql: str, *_args: Any) -> FakeRead:
            self.commands.append(sql)
            if sql in {"COMMIT", "ROLLBACK"}:
                raise RuntimeError(f"synthetic {sql} failure")
            return self

    con = DoubleFailure(close_fails=True)
    sub = _fake_sub(con)
    with pytest.raises(RuntimeError, match="synthetic COMMIT failure") as exc:
        sub.query("fixed")
    assert con.commands == ["BEGIN TRANSACTION", "COMMIT", "ROLLBACK"]
    assert any("rollback also failed" in note for note in exc.value.__notes__)
    assert any("close also failed" in note for note in exc.value.__notes__)
    assert con.close_count == 1
    with pytest.raises(SnapshotClosedError):
        sub.query("fixed")
    sub.close()
    assert con.close_count == 1


def test_busy_query_and_close_leave_live_lease_unchanged():
    con = FakeRead()
    sub = _fake_sub(con)
    with sub.query_snapshot("fixed") as snap:
        assert snap.con is con
        with pytest.raises(SnapshotBusyError):
            sub.query("fixed")
        with pytest.raises(SnapshotBusyError):
            sub.close()
        with ThreadPoolExecutor(max_workers=1) as pool:
            result = pool.submit(sub.query, "fixed")
            with pytest.raises(SnapshotBusyError):
                result.result()
        assert con.commands == ["BEGIN TRANSACTION"]
        assert con.close_count == 0
    assert con.commands == ["BEGIN TRANSACTION", "COMMIT"]
    assert sub.query("fixed")["query"] == "fixed"
    sub.close()
    assert con.close_count == 1
    with pytest.raises(SnapshotClosedError):
        sub.query("fixed")


def test_explicit_close_failure_is_visible_once_and_marks_closed():
    con = FakeRead(close_fails=True)
    sub = _fake_sub(con)
    with pytest.raises(RuntimeError, match="synthetic close failure"):
        sub.close()
    assert con.close_count == 1
    sub.close()
    assert con.close_count == 1
    with pytest.raises(SnapshotClosedError):
        sub.query("fixed")
