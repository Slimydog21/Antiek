"""Tests for processing/chunking/ + processing/embedding/.

Coverage:

1. ``content_hash`` is deterministic SHA-256.
2. ``chunk_markdown`` splits on headings + max_chunk_tokens, carries
   section context forward when splitting a long section.
3. ``HashEmbedding`` is deterministic, L2-normalized, dim-correct.
4. ``HashEmbedding`` ranks word-overlapping texts higher on cosine
   similarity than disjoint texts (the fallback's whole purpose).
5. ``default_embedding_provider`` honors env vars.
"""

from __future__ import annotations

import math
import os
import sys

import pytest

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_HERE))

from processing.chunking import (  # noqa: E402
    Chunk,
    chunk_markdown,
    content_hash,
    estimate_tokens,
)
from processing.embedding import (  # noqa: E402
    DEFAULT_EMBEDDING_DIM,
    HashEmbedding,
    _reset_default_provider,
    default_embedding_provider,
    set_default_embedding_provider,
)


# ---------------------------------------------------------------------------
# 1. content_hash
# ---------------------------------------------------------------------------


def test_content_hash_is_deterministic_sha256():
    h1 = content_hash("hello world")
    h2 = content_hash("hello world")
    assert h1 == h2
    assert len(h1) == 64  # SHA-256 hex
    # Different content → different hash.
    assert content_hash("hello world!") != h1


def test_estimate_tokens_is_whitespace_count():
    assert estimate_tokens("") == 0
    assert estimate_tokens("one") == 1
    assert estimate_tokens("one two three") == 3


# ---------------------------------------------------------------------------
# 2. chunk_markdown
# ---------------------------------------------------------------------------


def test_chunk_markdown_splits_on_headings():
    text = "# Section A\nfoo\n\n## Section B\nbar\n\n## Section C\nbaz"
    chunks = chunk_markdown(text)
    assert [c.section for c in chunks] == ["Section A", "Section B", "Section C"]


def test_chunk_markdown_preserves_section_context_on_long_sections():
    """A section longer than max_chunk_tokens splits into multiple
    chunks. The Researchmaxx convention is to inject a section comment
    on the carry-forward chunks so the section anchor is preserved."""
    long_body = "\n".join(f"word_{i}" for i in range(500))
    text = f"# Long Section\n{long_body}"
    chunks = chunk_markdown(text, max_chunk_tokens=100)
    assert len(chunks) >= 2
    # First chunk has the heading.
    assert "Long Section" in chunks[0].text
    # Subsequent chunks have the section comment marker.
    for c in chunks[1:]:
        assert "section: Long Section" in c.text


def test_chunk_markdown_empty_text_returns_empty():
    assert chunk_markdown("") == []
    assert chunk_markdown("\n\n\n") == []


def test_chunk_dataclass_is_frozen():
    """Chunk is frozen so callers can't mutate it after chunk_markdown
    returns."""
    c = Chunk(text="x", section="s", token_count=1)
    with pytest.raises(Exception):
        c.text = "y"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# 3. HashEmbedding
# ---------------------------------------------------------------------------


def test_hash_embedding_is_deterministic():
    e = HashEmbedding(dimension=16)
    a = e.encode("quantum computing")
    b = e.encode("quantum computing")
    assert a == b


def test_hash_embedding_dimension_matches():
    e = HashEmbedding(dimension=128)
    vec = e.encode("anything")
    assert len(vec) == 128
    assert e.dimension == 128


def test_hash_embedding_default_dim():
    e = HashEmbedding()
    assert e.dimension == DEFAULT_EMBEDDING_DIM
    assert len(e.encode("x")) == DEFAULT_EMBEDDING_DIM


def test_hash_embedding_is_l2_normalized():
    e = HashEmbedding(dimension=32)
    vec = e.encode("some text with several words")
    norm = math.sqrt(sum(x * x for x in vec))
    assert norm == pytest.approx(1.0, rel=1e-6)


def test_hash_embedding_handles_empty_text():
    e = HashEmbedding(dimension=8)
    vec = e.encode("")
    assert len(vec) == 8
    # Norm must still be > 0 so cosine SQL doesn't divide by zero.
    assert any(x != 0 for x in vec)


def _cosine(a: list[float], b: list[float]) -> float:
    num = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(x * x for x in b))
    return num / (na * nb) if na and nb else 0.0


def test_hash_embedding_word_overlap_ranks_above_disjoint():
    """The whole point of the hash fallback: shared vocabulary →
    higher cosine sim than disjoint vocabulary. Without this, the
    grounder's search-against-chunks degrades to noise in dev envs."""
    e = HashEmbedding(dimension=512)
    query = e.encode("quantum photonic qubit error correction")
    overlapping = e.encode("photonic qubit error correction approach")
    disjoint = e.encode("weather forecast tomorrow sunny warm")
    sim_overlap = _cosine(query, overlapping)
    sim_disjoint = _cosine(query, disjoint)
    assert sim_overlap > sim_disjoint
    assert sim_overlap > 0.3  # sanity — shared vocab produces real similarity
    assert sim_disjoint < 0.2  # disjoint vocab is near-zero


# ---------------------------------------------------------------------------
# 4. default_embedding_provider env-var resolution
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _reset_provider_singleton():
    _reset_default_provider()
    yield
    _reset_default_provider()


def test_default_provider_returns_hash_when_env_says_hash(monkeypatch):
    monkeypatch.setenv("ANTIEK_EMBEDDING_PROVIDER", "hash")
    p = default_embedding_provider()
    assert isinstance(p, HashEmbedding)


def test_default_provider_is_singleton(monkeypatch):
    monkeypatch.setenv("ANTIEK_EMBEDDING_PROVIDER", "hash")
    p1 = default_embedding_provider()
    p2 = default_embedding_provider()
    assert p1 is p2


def test_set_default_embedding_provider_overrides(monkeypatch):
    monkeypatch.setenv("ANTIEK_EMBEDDING_PROVIDER", "hash")
    stub = HashEmbedding(dimension=64)
    set_default_embedding_provider(stub)
    assert default_embedding_provider() is stub
