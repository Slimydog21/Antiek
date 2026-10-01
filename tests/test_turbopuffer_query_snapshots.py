"""Fixed synthetic TP candidate and DuckDB snapshot controls."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from processing.embedding.embed import HashEmbedding
from runtime.db_lock import connect_write
from substrate.graph import init_database_at_path
from substrate.graph.ops import insert_chunk, insert_document
from substrate.graph.retrieval_adapters import turbopuffer as tp
from substrate.graph.retrieval_adapters.turbopuffer import TurbopufferSubstrate
from substrate.graph.retrieval_substrate import (
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


class RecordingNamespace:
    def __init__(self, ids: list[str]) -> None:
        self.ids = ids
        self.calls: list[dict[str, Any]] = []
        self.error: Exception | None = None
        self.on_call: Any = None

    def multi_query(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        if self.on_call is not None:
            self.on_call()
        if self.error is not None:
            raise self.error
        rows = [SimpleNamespace(id=cid) for cid in self.ids]
        return SimpleNamespace(results=[SimpleNamespace(rows=rows)])


@pytest.fixture
def graph(tmp_path):
    path = str(tmp_path / "graph.duckdb")
    init_database_at_path(path)
    model = CountingHash()
    con = connect_write(path, purpose="tp-snapshot-fixture")
    try:
        for doc_id, cls, owner in (
            ("public", "public_domain", "public-owner"),
            ("licensed", "opt_in_licensed", "public-owner"),
            ("private-a", "user_authored_private", "owner-a"),
            ("private-b", "user_authored_private", "owner-b"),
            ("taken", "public_domain", "public-owner"),
        ):
            text = f"snapshot common {doc_id}"
            insert_document(
                con, document_id=doc_id,
                source_tier=1 if doc_id == "public" else 2,
                document_type="book", title=f"Before {doc_id}", raw_text=text,
                content_class=cls, owner_user_id=owner,
            )
            insert_chunk(
                con, chunk_id=f"chunk-{doc_id}", document_id=doc_id,
                chunk_index=0, text=text, section_path="Page 1", token_count=3,
                embedding=model.encode(text), embedding_provider=model,
            )
        con.execute("INSERT INTO book_assets (document_id,taken_down) VALUES ('taken',TRUE)")
    finally:
        con.close()
    model.calls = 0
    return path, model


def _ids(result: dict[str, Any]) -> list[str]:
    return [row["document_id"] for row in result["results"]]


def _sub(graph, namespace: RecordingNamespace, *, manifest_dir: Path | None = None):
    path, model = graph
    return TurbopufferSubstrate.open(
        path, model=model, api_key="synthetic", namespace=namespace,
        manifest_dir=manifest_dir,
    )


def _pointer(sub: TurbopufferSubstrate, directory: Path, name: str) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "active.json").write_text(
        json.dumps({"context": sub._context, "active_namespace": name}),
        encoding="utf-8",
    )


def test_remote_candidates_local_gate_metadata_and_order(graph, monkeypatch):
    path, model = graph
    writer = connect_write(path, purpose="tp-excluded-metadata")
    try:
        writer.execute(
            "UPDATE embeddings_meta SET fingerprint='other' "
            "WHERE chunk_id='chunk-private-b'"
        )
    finally:
        writer.close()
    namespace = RecordingNamespace([
        "chunk-private-b", "chunk-taken", "chunk-licensed", "chunk-public",
        "missing", "chunk-public",
    ])
    sub = _sub(graph, namespace)
    original = tp.assert_embedding_compatible
    checked: list[tuple[Any, Any]] = []

    def compatibility(con: Any, provider: Any, **kwargs: Any) -> None:
        checked.append((con, provider))
        original(con, provider, **kwargs)

    monkeypatch.setattr(tp, "assert_embedding_compatible", compatibility)
    try:
        with sub.query_snapshot("snapshot common", top_k=6) as snap:
            assert isinstance(sub, SnapshotReadableSubstrate)
            assert snap.con is sub._con
            assert snap.query_vector is not None
            assert _ids(snap.result) == ["licensed", "public", "public"]
            assert snap.result["status"] == "shadow"
            assert snap.result["node_matches"] == []
            assert snap.con.execute("SELECT count(*) FROM documents").fetchone() == (5,)
        assert checked == [(sub._con, model)]
        assert model.calls == 1
        call = namespace.calls[0]
        assert call["rerank_by"] == ("RRF",)
        assert call["consistency"] == {"level": "strong"}
        assert call["timeout"] == 30.0
        assert [query["rank_by"][:2] for query in call["queries"]] == [
            ("vector", "ANN"), ("text", "BM25"),
        ]
        assert "public" in _ids(sub.query("snapshot common", top_k=2))
        scoped = sub.query(
            "snapshot common", top_k=2, source_tier_max=1,
            document_ids=["public", "licensed"],
        )
        assert _ids(scoped) == ["public", "public"]
        vendor_queries = namespace.calls[-1]["queries"]
        assert vendor_queries[0]["filters"] == (
            "And", [("source_tier", "Lte", 1),
                    ("document_id", "In", ["public", "licensed"])],
        )
    finally:
        sub.close()


def test_remote_before_begin_under_exclusive_access_and_empty_scope(graph):
    path, model = graph
    namespace = RecordingNamespace(["chunk-public"])
    sub = _sub(graph, namespace)
    events: list[str] = []
    original_encode = model.encode

    def encode(text: str) -> list[float]:
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

    sub._con = RecordingRead(sub._con)
    model.encode = encode

    def during_remote() -> None:
        events.append("remote")
        with pytest.raises(SnapshotBusyError):
            sub.close()
        with pytest.raises(SnapshotBusyError):
            sub.query("snapshot common")

    namespace.on_call = during_remote
    try:
        assert "public" in _ids(sub.query("snapshot common", top_k=1))
        assert events == ["encode", "remote", "begin"]
        assert model.calls == 1
        namespace.calls.clear()
        with sub.query_snapshot("snapshot common", document_ids=[]) as snap:
            assert snap.query_vector is None
            assert snap.result["results"] == []
            assert snap.con is sub._con
            assert events[-1] == "begin"
        assert len(namespace.calls) == 0
        assert model.calls == 1
        with pytest.raises(ValueError, match="top_k"):
            sub.query("snapshot common", top_k=0)
        assert model.calls == 1
        assert len(namespace.calls) == 0
    finally:
        sub.close()


def test_preparation_and_remote_failures_preserve_useful_fallback(graph, tmp_path, monkeypatch):
    namespace = RecordingNamespace(["chunk-public"])
    sub = _sub(graph, namespace, manifest_dir=tmp_path)
    try:
        (tmp_path / "active.json").write_text("{bad", encoding="utf-8")
        with sub.query_snapshot("snapshot common") as snap:
            assert snap.result["status"] == "degraded — brute_force"
            assert "public" in _ids(snap.result)
            assert snap.query_vector is not None
        with sub.query_snapshot("snapshot common", allow_fallback=False) as snap:
            assert snap.result["status"] == "benchmark-failed"
            assert snap.result["results"] == []
            assert "failure_reason" in snap.result
            assert snap.query_vector is None
        assert namespace.calls == []
        (tmp_path / "active.json").unlink()
        namespace.error = RuntimeError("synthetic outage")
        with sub.query_snapshot("snapshot common") as snap:
            assert "public" in _ids(snap.result)
            assert snap.result["status"] == "degraded — brute_force"
        with sub.query_snapshot("snapshot common", allow_fallback=False) as snap:
            assert snap.result["status"] == "benchmark-failed"
            assert snap.query_vector is None
            assert snap.result["results"] == []
        assert len(namespace.calls) == 2
        namespace.error = None
        namespace.ids = []
        no_ids = sub.query("snapshot common")
        assert no_ids["status"] == "degraded — brute_force"
        assert "public" in _ids(no_ids)
    finally:
        sub.close()

    made: list[str] = []

    def failed_client(**kwargs: Any) -> Any:
        made.append(kwargs["namespace"])
        raise RuntimeError("synthetic client setup")

    monkeypatch.setattr(tp, "make_namespace", failed_client)
    monkeypatch.setenv("ANTIEK_TURBOPUFFER_SHADOW_ENABLED", "1")
    path, model = graph
    factory = TurbopufferSubstrate.open(
        path, model=model, api_key="synthetic", manifest_dir=tmp_path,
    )
    try:
        out = factory.query("snapshot common")
        assert out["status"] == "degraded — brute_force"
        assert "public" in _ids(out)
        assert made
        failed = factory.query("snapshot common", allow_fallback=False)
        assert failed["status"] == "benchmark-failed"
        assert failed["results"] == []
    finally:
        factory.close()


def test_context_mismatch_and_model_error_keep_failure_boundary(graph, tmp_path, monkeypatch):
    path, model = graph
    namespace = RecordingNamespace(["chunk-public"])
    sub = _sub(graph, namespace, manifest_dir=tmp_path)
    try:
        (tmp_path / "active.json").write_text(
            json.dumps({
                "context": {"region": "different"},
                "active_namespace": tp.DEFAULT_NAMESPACE,
            }), encoding="utf-8",
        )
        fallback = sub.query("snapshot common")
        assert fallback["status"] == "degraded — brute_force"
        assert "public" in _ids(fallback)
        assert "context mismatch" in fallback["degraded_reason"]
        refused = sub.query("snapshot common", allow_fallback=False)
        assert refused["status"] == "benchmark-failed"
        assert refused["results"] == []
        assert "context mismatch" in refused["failure_reason"]
        assert namespace.calls == []

        def broken_encode(_text: str) -> list[float]:
            raise RuntimeError("synthetic model failure")

        monkeypatch.setattr(model, "encode", broken_encode)
        with pytest.raises(RuntimeError, match="synthetic model failure"):
            sub.query("snapshot common")
        assert namespace.calls == []
    finally:
        sub.close()


@pytest.mark.parametrize("policy_tag", ["owner_scoped", "operator_only", "private_research"])
def test_privileged_policy_uses_canonical_owner_gate_without_vendor(graph, policy_tag):
    namespace = RecordingNamespace(["chunk-private-b"])
    sub = _sub(graph, namespace)
    try:
        a = sub.query(
            "snapshot common", top_k=20, policy_tag=policy_tag,
            owner_user_id="owner-a",
        )
        assert a["status"] == "duckdb — non_servable_policy"
        assert "private-a" in _ids(a)
        assert "private-b" not in _ids(a)
        assert namespace.calls == []
    finally:
        sub.close()


def test_pointer_status_tracks_bound_client_not_new_pointer(graph, tmp_path, monkeypatch):
    path, model = graph
    a = tp.DEFAULT_NAMESPACE + "-" + "a" * 12
    b = tp.DEFAULT_NAMESPACE + "-" + "b" * 12
    namespace = RecordingNamespace(["chunk-public"])
    made: list[str] = []

    def make_namespace(**kwargs: Any) -> RecordingNamespace:
        made.append(kwargs["namespace"])
        return namespace

    monkeypatch.setattr(tp, "make_namespace", make_namespace)
    monkeypatch.setenv("ANTIEK_TURBOPUFFER_SHADOW_ENABLED", "1")
    sub = TurbopufferSubstrate.open(
        path, model=model, api_key="synthetic", manifest_dir=tmp_path,
    )
    try:
        _pointer(sub, tmp_path, a)
        assert sub.query("snapshot common", allow_fallback=False)["status"] == "servable"
        assert made == [a]
        _pointer(sub, tmp_path, b)
        assert sub.query("snapshot common", allow_fallback=False)["status"] == "shadow"
        assert made == [a]
        _pointer(sub, tmp_path, a)
        namespace.on_call = lambda: _pointer(sub, tmp_path, b)
        assert sub.query("snapshot common", allow_fallback=False)["status"] == "servable"
        namespace.on_call = None
        assert sub.query("snapshot common", allow_fallback=False)["status"] == "shadow"
        assert sub.query_status_label() == "servable"  # current pointer observation
    finally:
        sub.close()

    injected = RecordingNamespace(["chunk-public"])
    matched = TurbopufferSubstrate.open(
        path, model=model, api_key="synthetic", namespace=injected,
        namespace_name=b, manifest_dir=tmp_path,
    )
    try:
        assert matched.query("snapshot common", allow_fallback=False)["status"] == "servable"
    finally:
        matched.close()


def test_skipped_and_invalid_inputs_keep_normal_lease_without_encoding(graph):
    path, model = graph
    sub = TurbopufferSubstrate.open(path, model=model, api_key="")
    try:
        with sub.query_snapshot("snapshot common", allow_fallback=False) as snap:
            assert snap.result["status"] == tp._SKIPPED
            assert snap.result["results"] == []
            assert snap.query_vector is None
            assert snap.con.execute("SELECT 1").fetchone() == (1,)
        assert model.calls == 0
        with pytest.raises(ValueError, match="top_k"):
            sub.query("snapshot common", top_k=0, allow_fallback=False)
        assert model.calls == 0
    finally:
        sub.close()


def test_stored_cursor_snapshot_and_parent_lifetime(graph, monkeypatch):
    path, model = graph
    writer = connect_write(path, purpose="tp-snapshot-interleave")
    namespace = RecordingNamespace(["chunk-public"])
    sub = TurbopufferSubstrate.from_con(
        writer, model=model, db_path=path, api_key="synthetic", namespace=namespace,
    )
    original = tp.assert_embedding_compatible
    changed: list[bool] = []

    def after_metadata(con: Any, provider: Any, **kwargs: Any) -> None:
        assert con is sub._con and con is not writer
        assert provider is model
        original(con, provider, **kwargs)
        if not changed:
            writer.execute(
                "UPDATE documents SET title='After public',content_class='research_only' "
                "WHERE document_id='public'"
            )
            changed.append(True)

    monkeypatch.setattr(tp, "assert_embedding_compatible", after_metadata)
    try:
        with sub.query_snapshot("snapshot common") as snap:
            assert changed == [True]
            assert _ids(snap.result) == ["public"]
            assert snap.result["results"][0]["document_title"] == "Before public"
            assert snap.con.execute(
                "SELECT title,content_class FROM documents WHERE document_id='public'"
            ).fetchone() == ("Before public", "public_domain")
        assert writer.execute(
            "SELECT title,content_class FROM documents WHERE document_id='public'"
        ).fetchone() == ("After public", "research_only")
        assert sub.query("snapshot common")["results"] == []
    finally:
        sub.close()
        assert writer.execute("SELECT 1").fetchone() == (1,)
        writer.close()


def test_tp_commit_failure_surfaces_without_fallback_and_keeps_parent(graph):
    path, model = graph
    writer = connect_write(path, purpose="tp-commit-failure")
    namespace = RecordingNamespace(["chunk-public"])
    sub = TurbopufferSubstrate.from_con(
        writer, model=model, db_path=path, api_key="synthetic", namespace=namespace,
    )

    class FailCommit:
        def __init__(self, con: Any) -> None:
            self.con = con
            self.commands: list[str] = []
            self.close_count = 0

        def execute(self, sql: str, *args: Any) -> Any:
            if sql in {"BEGIN TRANSACTION", "COMMIT", "ROLLBACK"}:
                self.commands.append(sql)
            if sql == "COMMIT":
                raise RuntimeError("synthetic TP COMMIT failure")
            return self.con.execute(sql, *args)

        def close(self) -> None:
            self.close_count += 1
            self.con.close()

        def __getattr__(self, name: str) -> Any:
            return getattr(self.con, name)

    wrapped = FailCommit(sub._con)
    sub._con = wrapped
    try:
        with pytest.raises(RuntimeError, match="synthetic TP COMMIT failure"):
            sub.query("snapshot common")
        assert wrapped.commands == ["BEGIN TRANSACTION", "COMMIT", "ROLLBACK"]
        assert wrapped.close_count == 1
        assert model.calls == 1
        assert len(namespace.calls) == 1
        with pytest.raises(SnapshotClosedError):
            sub.query("snapshot common")
        assert len(namespace.calls) == 1
        assert writer.execute("SELECT 1").fetchone() == (1,)
    finally:
        sub.close()
        writer.close()


def test_local_metadata_and_sql_failures_never_fallback(graph, monkeypatch):
    path, model = graph
    namespace = RecordingNamespace(["chunk-public"])
    original_compatibility = tp.assert_embedding_compatible
    writer = connect_write(path, purpose="tp-metadata-mismatch")
    try:
        writer.execute(
            "UPDATE embeddings_meta SET fingerprint='other' WHERE chunk_id='chunk-public'"
        )
    finally:
        writer.close()
    sub = _sub(graph, namespace)
    try:
        with pytest.raises(ValueError, match="Stored chunk embeddings are pinned"):
            sub.query("snapshot common", allow_fallback=True)
        assert len(namespace.calls) == 1
        # The failed local check rolls back and does not poison the handle.
        namespace.ids = ["chunk-licensed"]
        assert "licensed" in _ids(sub.query(
            "snapshot common", document_ids=["licensed"], allow_fallback=True,
        ))

        def local_failure(*_args: Any, **_kwargs: Any) -> None:
            raise RuntimeError("synthetic local check")

        monkeypatch.setattr(tp, "assert_embedding_compatible", local_failure)
        with pytest.raises(RuntimeError, match="synthetic local check"):
            sub.query("snapshot common", allow_fallback=True)
        assert len(namespace.calls) == 3

        monkeypatch.setattr(tp, "assert_embedding_compatible", original_compatibility)

        def local_scoring_failure(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
            raise RuntimeError("synthetic local scoring")

        monkeypatch.setattr(sub, "_hydrate_candidates", local_scoring_failure)
        with pytest.raises(RuntimeError, match="synthetic local scoring"):
            sub.query("snapshot common", allow_fallback=True)
        assert len(namespace.calls) == 4
    finally:
        sub.close()
