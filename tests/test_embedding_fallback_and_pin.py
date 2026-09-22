"""The provider falls back to hash ONLY when the package is missing, and every
stored vector is pinned to a provider identity (audit wave 3, #1)."""
from __future__ import annotations

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import pytest

import processing.embedding.embed as embed_mod
from processing.embedding.embed import HashEmbedding


@pytest.fixture(autouse=True)
def _reset(monkeypatch):
    embed_mod._reset_default_provider()
    monkeypatch.setenv("ANTIEK_EMBEDDING_PROVIDER", "sentence-transformers")
    monkeypatch.delenv("ANTIEK_EMBEDDING_MODEL", raising=False)
    yield
    embed_mod._reset_default_provider()

def _raise_from(cause):
    def _init(self, model_name="all-MiniLM-L6-v2"):
        try:
            raise cause
        except Exception as exc:
            raise RuntimeError("sentence-transformers unavailable") from exc
    return _init

def test_missing_package_falls_back_to_hash(monkeypatch, capsys):
    monkeypatch.setattr(embed_mod.SentenceTransformerEmbedding, "__init__", _raise_from(ImportError("No module named sentence_transformers")))
    p = embed_mod.default_embedding_provider()
    assert isinstance(p, HashEmbedding)
    assert "not installed" in capsys.readouterr().err

@pytest.mark.parametrize("cause", [RuntimeError("DefaultCPUAllocator: not enough memory"), OSError("corrupt weight file"), ValueError("bad device")])
def test_any_other_construction_failure_raises_instead_of_degrading(monkeypatch, cause):
    monkeypatch.setattr(embed_mod.SentenceTransformerEmbedding, "__init__", _raise_from(cause))
    with pytest.raises(RuntimeError):
        embed_mod.default_embedding_provider()
    # and it must NOT have cached a hash provider on the way out
    assert embed_mod._DEFAULT_PROVIDER is None

def test_insert_chunk_pins_the_default_provider_when_none_is_passed(monkeypatch):
    monkeypatch.setenv("ANTIEK_EMBEDDING_PROVIDER", "hash")
    d = tempfile.mkdtemp()
    db = os.path.join(d, "g.duckdb")
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", db)
    from runtime.db_lock import connect_read, connect_write
    from substrate.graph import ensure_initialized, insert_chunk, insert_document
    ensure_initialized(db)
    with connect_write(db, purpose="t") as con:
        insert_document(con, document_id="doc1", source_tier=4, document_type="article", events_dir=d)
        insert_chunk(con, document_id="doc1", chunk_index=0, text="hello", embedding=HashEmbedding().encode("hello"))
    con = connect_read(db)
    n_vec = con.execute("select count(*) from chunks where embedding is not null").fetchone()[0]
    n_meta = con.execute("select count(*) from embeddings_meta").fetchone()[0]
    prov = con.execute("select provider from embeddings_meta limit 1").fetchone()
    assert n_vec == 1 and n_meta == 1, "a stored vector must always carry a provider pin"
    assert prov and "hash" in str(prov[0]).lower()
