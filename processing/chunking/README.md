# processing/chunking/

Content-addressed chunking.

Chunk IDs are derived from content hash (SHA-256 of the chunk text plus
its position within the source). Re-ingesting the same source produces
the same chunk IDs and short-circuits downstream work (embedding,
extraction) that has already run for those chunks.

## Heuristics

- Paragraph-aware splitting where structure is detectable.
- Token-budget fallback (target ~500 tokens per chunk) when structure
  is absent.
- Overlap window for chunks at section boundaries.

## Discipline

The chunker is deterministic given the same input. This is what makes
content-addressing reliable.
