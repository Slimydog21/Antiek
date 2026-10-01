"""Embedding pinning follows the exact eligible chunk set for graph search."""

from __future__ import annotations

import duckdb
import pytest

from processing.embedding import embedding_provider_fingerprint
from processing.embedding.embed import HashEmbedding
from substrate.graph.embedding_meta import assert_embedding_compatible
from substrate.graph.schema import init_database_at_path
from substrate.graph.search import search


@pytest.fixture
def db(tmp_path):
    path = str(tmp_path / "search.duckdb")
    init_database_at_path(path)
    con = duckdb.connect(path)
    try:
        yield con
    finally:
        con.close()


def add_chunk(db, doc_id: str, provider, *, content_class: str = "user_owned",
              tier: int = 2, with_embedding: bool = True, with_meta: bool = True,
              owner: str = "__operator__") -> str:
    chunk_id = f"chunk-{doc_id}"
    db.execute(
        "INSERT INTO documents (document_id, title, source_tier, document_type, "
        "content_class, owner_user_id) VALUES (?, ?, ?, 'book', ?, ?)",
        [doc_id, doc_id, tier, content_class, owner],
    )
    db.execute(
        "INSERT INTO chunks (chunk_id, document_id, chunk_index, text, embedding) "
        "VALUES (?, ?, 0, 'quantum book', ?)",
        [chunk_id, doc_id, provider.encode("quantum book") if with_embedding else None],
    )
    if with_meta:
        db.execute(
            "INSERT INTO embeddings_meta "
            "(chunk_id, provider, model_name, dimension, fingerprint) "
            "VALUES (?, 'test', 'test', ?, ?)",
            [chunk_id, provider.dimension, embedding_provider_fingerprint(provider)],
        )
    return chunk_id


def hits(db, model, **kwargs):
    return [r["document_id"] for r in search(db, "quantum", model=model,
                                               top_k=20, **kwargs)["results"]]


class OtherSpace:
    """Equal-dimensional vectors with a different persisted fingerprint."""

    provider_name = "other-space"
    model_name = "other-model"
    dimension = 8

    def encode(self, text: str) -> list[float]:
        return HashEmbedding(dimension=8).encode(text)


class CountingHash(HashEmbedding):
    def __init__(self):
        super().__init__(dimension=8)
        self.calls = 0

    def encode(self, text: str) -> list[float]:
        self.calls += 1
        return super().encode(text)


def test_document_scope_ignores_unrelated_embedding_model(db):
    model_a = HashEmbedding(dimension=8)
    model_b = HashEmbedding(dimension=16)
    add_chunk(db, "book-a", model_a)
    assert [r["document_id"] for r in search(db, "quantum", model=model_a,
                                             document_id="book-a")["results"]] == ["book-a"]
    add_chunk(db, "book-b", model_b)
    assert hits(db, model_a, document_id="book-a") == ["book-a"]


def test_set_and_union_scope_keep_compatible_books(db):
    model = HashEmbedding(dimension=8)
    add_chunk(db, "a", model)
    add_chunk(db, "b", model)
    add_chunk(db, "outside", OtherSpace())
    assert set(hits(db, model, document_ids=["a", "b"])) == {"a", "b"}
    assert set(hits(db, model, document_ids=["a"], document_id="b")) == {"a", "b"}
    assert hits(db, model, document_ids=["a", "a"]) == ["a"]


def test_explicit_empty_and_absent_document(db):
    model = CountingHash()
    add_chunk(db, "outside", OtherSpace())
    model.calls = 0
    assert hits(db, model, document_ids=[]) == []
    assert model.calls == 0
    assert hits(db, model, document_id="missing") == []


@pytest.mark.parametrize("provider", [OtherSpace(), HashEmbedding(dimension=16)])
def test_in_scope_incompatible_vector_fails_before_ranking(db, provider):
    model = HashEmbedding(dimension=8)
    add_chunk(db, "a", model)
    add_chunk(db, "b", provider)
    with pytest.raises(ValueError, match="pinned to"):
        hits(db, model, document_ids=["a", "b"])
    with pytest.raises(ValueError, match="pinned to"):
        hits(db, model)  # Unscoped search must not silently omit b.
    assert hits(db, model, document_id="a") == ["a"]


def test_tier_and_rights_gates_define_compatibility_candidates(db):
    model = HashEmbedding(dimension=8)
    add_chunk(db, "allowed", model)
    add_chunk(db, "low-tier", OtherSpace(), tier=5)
    add_chunk(db, "restricted", OtherSpace(), content_class="restricted_pending_opt_in")
    add_chunk(db, "other-owner", OtherSpace(), content_class="personal_reading",
              owner="another-user")
    assert hits(db, model, source_tier_max=2) == ["allowed"]
    with pytest.raises(ValueError, match="pinned to"):
        hits(db, model, policy_tag="private_research",
             owner_user_id="__operator__", source_tier_max=2)
    db.execute("DELETE FROM embeddings_meta WHERE chunk_id = 'chunk-restricted'")
    assert hits(db, model, policy_tag="private_research",
                owner_user_id="__operator__", source_tier_max=2) == ["allowed", "restricted"]
    with pytest.raises(ValueError, match="pinned to"):
        hits(db, model, source_tier_max=5)
    with pytest.raises(ValueError, match="pinned to"):
        hits(db, model, policy_tag="private_research", owner_user_id="another-user",
             source_tier_max=2)


def test_null_embedding_orphan_meta_and_unpinned_vector(db):
    model = HashEmbedding(dimension=8)
    add_chunk(db, "allowed", model)
    add_chunk(db, "null-vector", OtherSpace(), with_embedding=False)
    add_chunk(db, "legacy-unpinned", model, with_meta=False)
    db.execute(
        "INSERT INTO embeddings_meta (chunk_id, provider, model_name, dimension, fingerprint) "
        "VALUES ('orphan', 'other', 'other', 16, 'other')"
    )
    assert set(hits(db, model)) == {"allowed", "legacy-unpinned"}


def test_empty_or_absent_metadata_keeps_legacy_search(db):
    model = HashEmbedding(dimension=8)
    add_chunk(db, "legacy", model, with_meta=False)
    assert hits(db, model) == ["legacy"]
    db.execute("DROP TABLE embeddings_meta")
    assert hits(db, model) == ["legacy"]


def test_direct_helper_stays_global_and_other_sql_errors_surface(db):
    model = HashEmbedding(dimension=8)
    add_chunk(db, "a", model)
    add_chunk(db, "outside", OtherSpace())
    with pytest.raises(ValueError, match="pinned to"):
        assert_embedding_compatible(db, model)
    db.execute("DROP INDEX idx_embeddings_meta_fingerprint")
    db.execute("ALTER TABLE embeddings_meta RENAME COLUMN dimension TO broken_dimension")
    with pytest.raises(duckdb.BinderException):
        hits(db, model, document_id="a")


def test_missing_candidate_table_is_not_treated_as_absent_metadata(db):
    model = HashEmbedding(dimension=8)
    with pytest.raises(duckdb.CatalogException):
        assert_embedding_compatible(
            db, model, candidate_sql="SELECT chunk_id FROM missing_candidates",
        )


@pytest.mark.parametrize("column", ["fingerprint", "dimension"])
def test_present_null_identity_fails_closed(db, column):
    model = HashEmbedding(dimension=8)
    add_chunk(db, "a", model)
    add_chunk(db, "compatible", model)
    with pytest.raises(duckdb.ConstraintException):
        db.execute(f"UPDATE embeddings_meta SET {column} = NULL WHERE chunk_id = 'chunk-a'")
    db.execute("DROP INDEX idx_embeddings_meta_fingerprint")
    db.execute(f"ALTER TABLE embeddings_meta ALTER COLUMN {column} DROP NOT NULL")
    db.execute(f"UPDATE embeddings_meta SET {column} = NULL WHERE chunk_id = 'chunk-a'")
    with pytest.raises(ValueError, match="pinned to"):
        hits(db, model, document_id="a")
    assert hits(db, model, document_id="compatible") == ["compatible"]
