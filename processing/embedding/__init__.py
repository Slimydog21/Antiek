"""Embedding providers (Sprint 3 Day 2-3).

Production: sentence-transformers wrapper. Dev / tests: deterministic
hash-based fallback. See ``embed.py`` for the resolution rules.
"""

from .embed import (
    DEFAULT_EMBEDDING_DIM,
    EmbeddingProvider,
    HashEmbedding,
    SentenceTransformerEmbedding,
    _reset_default_provider,
    default_embedding_provider,
    set_default_embedding_provider,
)

__all__ = [
    "DEFAULT_EMBEDDING_DIM",
    "EmbeddingProvider",
    "HashEmbedding",
    "SentenceTransformerEmbedding",
    "default_embedding_provider",
    "set_default_embedding_provider",
    "_reset_default_provider",
]
