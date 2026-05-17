"""Chunking — text-into-chunks helpers (Sprint 3 Day 2-3).

Heading-aware markdown chunker + content_hash. File/PDF readers
deferred to ``acquisition/`` — they belong with the source-specific
ingestion adapters, not in the shared processing layer.
"""

from .chunker import (
    DEFAULT_MAX_CHUNK_TOKENS,
    Chunk,
    chunk_markdown,
    content_hash,
    estimate_tokens,
)

__all__ = [
    "Chunk",
    "DEFAULT_MAX_CHUNK_TOKENS",
    "chunk_markdown",
    "content_hash",
    "estimate_tokens",
]
