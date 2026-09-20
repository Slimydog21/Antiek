"""Env-gated TurboPuffer hybrid mount for reuse/cascade + Thought Partner."""

from __future__ import annotations

import pytest

from benchmarks.retrieval_bench import HashEmbedding, seed_graph
from runtime.db_lock import connect_write
from substrate.graph.embedding_meta import _identity
from substrate.graph.retrieval_adapters.turbopuffer import TurbopufferSubstrate
from substrate.graph.retrieval_substrate import (
    make_substrate_from_con,
    resolve_reuse_substrate_kind,
)


@pytest.fixture
def graph(tmp_path):
    db = str(tmp_path / "graph.duckdb")
    seed_graph(db, HashEmbedding())
    con = connect_write(db, purpose="tpuf-hybrid-meta")
    try:
        rows = con.execute("SELECT chunk_id FROM chunks WHERE embedding IS NOT NULL").fetchall()
        provider, model, dim, fingerprint = _identity(HashEmbedding())
        con.executemany(
            "INSERT OR REPLACE INTO embeddings_meta VALUES (?,?,?,?,?,CURRENT_TIMESTAMP)",
            [(r[0], provider, model, dim, fingerprint) for r in rows],
        )
    finally:
        con.close()
    return db


def test_resolve_reuse_substrate_kind_env_gated(monkeypatch):
    monkeypatch.delenv("ANTIEK_TURBOPUFFER_SERVABLE", raising=False)
    monkeypatch.delenv("TURBOPUFFER_API_KEY", raising=False)
    assert resolve_reuse_substrate_kind() == "brute_force"
    monkeypatch.setenv("ANTIEK_TURBOPUFFER_SERVABLE", "1")
    assert resolve_reuse_substrate_kind() == "brute_force"  # no key
    monkeypatch.setenv("TURBOPUFFER_API_KEY", "test-key")
    assert resolve_reuse_substrate_kind() == "turbopuffer"


def test_from_con_hybrid_attribution_hits_vendor(graph, tmp_path, monkeypatch):
    from tests.test_turbopuffer_shadow import FakeNamespace

    monkeypatch.setenv("ANTIEK_TURBOPUFFER_SERVABLE", "1")
    fake = FakeNamespace()
    import duckdb

    parent = duckdb.connect(graph)
    try:
        sub = TurbopufferSubstrate.from_con(
            parent, model=HashEmbedding(), db_path=graph, api_key="x",
            namespace=fake, manifest_dir=tmp_path,
        )
        staged = sub.rebuild_shadow()
        fake.ids = [str(r["id"]) for r in fake.upserted_rows]
        sub.promote(
            staged["manifest_path"],
            confirmation="PROMOTE-" + staged["content_hash"][:12],
        )
        # fresh from_con with same db_path context
        sub2 = TurbopufferSubstrate.from_con(
            parent, model=HashEmbedding(), db_path=graph, api_key="x",
            namespace=None, manifest_dir=tmp_path,
        )
        # inject namespace via make_namespace monkeypatch after promote pointer
        made = []
        monkeypatch.setattr(
            "substrate.graph.retrieval_adapters.turbopuffer.make_namespace",
            lambda **kwargs: made.append(kwargs) or fake,
        )
        out = sub2.query("government", top_k=3, allow_fallback=False)
        assert out["status"] == "servable", f"vendor path failed: {out.get('failure_reason')}"
        assert out["results"]
        assert made and made[0]["namespace"] == staged["namespace"]
    finally:
        parent.close()


def test_from_con_privileged_policy_stays_duckdb(graph, tmp_path, monkeypatch):
    from tests.test_turbopuffer_shadow import FakeNamespace

    monkeypatch.setenv("ANTIEK_TURBOPUFFER_SERVABLE", "1")
    fake = FakeNamespace()
    import duckdb

    parent = duckdb.connect(graph)
    try:
        sub = TurbopufferSubstrate.from_con(
            parent, model=HashEmbedding(), db_path=graph, api_key="x",
            namespace=fake, manifest_dir=tmp_path,
        )
        out = sub.query("government", top_k=3, policy_tag="operator_only")
        assert out["status"] == "duckdb — non_servable_policy"
        assert fake.queries == []  # never called vendor
    finally:
        parent.close()


def test_make_substrate_from_con_turbopuffer_requires_db_path(graph):
    import duckdb

    parent = duckdb.connect(graph)
    try:
        with pytest.raises(ValueError, match="db_path"):
            make_substrate_from_con("turbopuffer", parent, model=HashEmbedding())
    finally:
        parent.close()


def test_make_substrate_from_con_resolves_turbopuffer(graph, tmp_path, monkeypatch):
    monkeypatch.setenv("ANTIEK_TURBOPUFFER_SERVABLE", "1")
    monkeypatch.setenv("TURBOPUFFER_API_KEY", "x")
    import duckdb

    parent = duckdb.connect(graph)
    try:
        # without injected namespace + with key+env, status not skipped
        sub = make_substrate_from_con(
            "turbopuffer", parent, model=HashEmbedding(), db_path=graph,
            manifest_dir=tmp_path,
        )
        assert sub.name == "turbopuffer"
        assert not sub.skipped
    finally:
        parent.close()
