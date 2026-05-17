# processing/embedding/

Vector embedding generation. Embeddings feed:

- The evidence retriever (sub-Q → candidate chunks).
- The cross-domain connector (which finds links via embedding
  proximity, not LLM imagination — see architecture_notes §4).

## Model

Sentence-transformer family for the default embedder. The specific
model is chosen for the quality/cost trade-off on long-form research
content; the choice lives in `substrate/dispatch/config.yaml` so it
can be swapped without code changes.

## Storage

Vectors land in DuckDB alongside the chunks. The vector index uses
DuckDB's HNSW extension where available; pgvector-style nearest-neighbor
queries otherwise.

## Discipline

Embeddings are derived from content hash. Same chunk → same vector.
Re-embedding only runs when the embedder model changes.
