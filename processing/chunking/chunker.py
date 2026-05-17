"""Markdown chunker — heading-aware splitter.

Migrated from Researchmaxx ``ingest.py:chunk_markdown`` (~70 LOC).
The other half of ingest.py (PDF readers, file ingestion CLI) is
deferred to ``acquisition/`` — chunking belongs in ``processing/``
because it operates on already-loaded text regardless of source.

Strategy (matches the Researchmaxx implementation byte-for-byte):

1. Walk lines. Detect ``# / ## / ### / ####`` headings and start a
   new chunk on each.
2. Within a section, accumulate lines until the token estimate would
   exceed ``max_chunk_tokens``. Flush, then carry the section
   identifier forward as a comment so the next chunk still
   anchors to its section context.
3. Empty chunks are dropped; the section heading itself counts
   toward the next chunk's tokens.

Token estimate uses whitespace-split word count — same as the
Researchmaxx heuristic. ~20% off vs real tokenizers; good enough for
sizing decisions in a batch pipeline.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass

# Default max-tokens. Same as Researchmaxx ingest.py default.
DEFAULT_MAX_CHUNK_TOKENS = 2000


@dataclass(frozen=True)
class Chunk:
    """One chunked segment from ``chunk_markdown``. Used as the input
    to ``substrate/graph/ops.insert_chunk``."""

    text: str
    section: str
    token_count: int


def content_hash(text: str) -> str:
    """Full SHA-256 hex of the text — content-addressed chunk id. Same
    format as Researchmaxx, so a migrated corpus's chunk ids stay
    recognizable across systems."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def estimate_tokens(text: str) -> int:
    """Whitespace-split word count. Approximate but cheap and
    deterministic."""
    return len(text.split())


_HEADING_RE = re.compile(r"^(#{1,4})\s+(.+)")


def chunk_markdown(
    text: str,
    *,
    max_chunk_tokens: int = DEFAULT_MAX_CHUNK_TOKENS,
) -> list[Chunk]:
    """Split markdown into Chunks. Heading-aware; long sections split
    on paragraph (token-budget) boundary with a carry-forward comment
    so downstream consumers still know the section context."""
    lines = text.split("\n")
    chunks: list[Chunk] = []
    current_section = ""
    current_lines: list[str] = []
    current_tokens = 0

    def flush() -> None:
        nonlocal current_lines, current_tokens
        if not current_lines:
            return
        body = "\n".join(current_lines).strip()
        if body:
            chunks.append(Chunk(text=body, section=current_section, token_count=estimate_tokens(body)))
        current_lines = []
        current_tokens = 0

    for line in lines:
        m = _HEADING_RE.match(line)
        if m:
            flush()
            current_section = m.group(2).strip()
            current_lines.append(line)
            current_tokens += estimate_tokens(line)
            continue

        line_tokens = estimate_tokens(line)
        if current_tokens + line_tokens > max_chunk_tokens and current_lines:
            flush()
            if current_section:
                # Carry section context forward so the next chunk
                # still has anchor metadata in its body.
                current_lines.append(f"<!-- section: {current_section} -->")
                current_tokens += 3

        current_lines.append(line)
        current_tokens += line_tokens

    flush()
    return chunks
