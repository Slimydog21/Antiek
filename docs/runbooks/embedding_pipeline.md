# Runbook · embedding pipeline

**Owner:** substrate
**Last verified:** 2026-05-24

## Symptom

- Cosine similarity queries return weird ordering (top-k looks
  unrelated to the query).
- A query that should return rich results returns nothing.
- `chunks.embedding IS NULL` for rows that were ingested days ago.

## Likely cause

Three buckets, ordered by frequency:

1. **Ingest succeeded, embedding step skipped or crashed.** The chunk
   row landed; the embedding compute failed (model load, OOM, network)
   and was logged but didn't block ingest.
2. **Embedding model mismatch.** The query is encoded with one model
   (e.g., MiniLM 384-dim); the stored vectors are from another model
   (e.g., the previous Antiek model). Cosine sim across dimensions is
   nonsense.
3. **Dimension mismatch.** The DuckDB cosine SQL expects a vector of
   the declared dimension; a chunk with a different-length embedding
   gives garbage (or an error).

## Quick diagnostics

```bash
# How many chunks have NULL embeddings?
.venv/bin/python -c "
from runtime.db_lock import connect_read
with connect_read('<path>.duckdb') as con:
    print(con.execute('SELECT COUNT(*) FROM chunks WHERE embedding IS NULL').fetchone())
"

# Sample dimensions across the table — every row should match
# the configured EmbeddingModel.dimension.
.venv/bin/python -c "
from runtime.db_lock import connect_read
with connect_read('<path>.duckdb') as con:
    print(con.execute('SELECT DISTINCT array_length(embedding) FROM chunks WHERE embedding IS NOT NULL').fetchall())
"

# Dry-run the reconstruction script.
.venv/bin/python scripts/reconstruct_vector_index.py --db <path>.duckdb --dry-run
```

If `--dry-run` reports `missing_before > 0`: that's bucket 1 (missing
embeddings). The reconstruction script is the fix; see the worked
example below.

If the distinct array-length query returns more than one value:
bucket 3 (dimension mismatch).

## Root-cause path

For missing embeddings (bucket 1):

- The ingest path computes embeddings; if the model is slow / OOM /
  network-blocked, the embedding step may have skipped while the chunk
  insert succeeded. The substrate's append-only invariant means we
  preserve the chunk + recompute later, which is what P8 / SPR-06 is
  about.

For model mismatch (bucket 2):

- Each chunk's `embedding` is computed at ingest time with the
  then-current model. After a model upgrade, OLD chunks have OLD
  vectors. Cosine sim BETWEEN old and new is nonsense.
- The fix: re-embed everything with the new model.

For dimension mismatch (bucket 3):

- Almost always means two ingest paths used different models. Re-embed
  with the canonical one.

## Mitigation

**For missing embeddings:**

```bash
.venv/bin/python scripts/reconstruct_vector_index.py --db <path>.duckdb
```

Idempotent. Re-running on a clean substrate makes zero writes. See
`docs/decisions/vector_index_as_derived_data.md`.

**For model mismatch / dimension mismatch:**

```bash
# Force re-embed everything with the canonical EmbeddingModel.
.venv/bin/python scripts/reconstruct_vector_index.py --db <path>.duckdb --rebuild
```

For bounded windows (large substrate, want to spread the work):

```bash
.venv/bin/python scripts/reconstruct_vector_index.py \
    --db <path>.duckdb --rebuild --max-chunks 5000
```

Re-run until `missing_before == 0` (or `embedded_this_run == 0` on
rebuild — meaning the loop has finished).

## Reference

- Code: `substrate/graph/search.py` (`cosine_similarity_sql`,
  `EmbeddingModel`, `SentenceTransformerEmbedding`)
- Schema: `substrate/graph/schema.py` (`chunks.embedding FLOAT[]`)
- Reconstruction: `scripts/reconstruct_vector_index.py`
- Decision: `docs/decisions/vector_index_as_derived_data.md`
- Tests: `tests/test_reconstruct_vector_index.py`

## Worked example

```
2026-05-24 cosine_similarity_sql shows nan for half the top-k results.
```

Trace:

1. Diagnostic: dimension query returns `[(384,), (1536,)]` — two
   different vector lengths in the same table.
2. Cause: an earlier ingest run used `text-embedding-3-small` (1536-d);
   subsequent runs use the local MiniLM (384-d). Cosine sim across
   dimensions returns nonsense.
3. Mitigation: pick one canonical model (the substrate's
   `SentenceTransformerEmbedding` default), run:
   ```bash
   .venv/bin/python scripts/reconstruct_vector_index.py \
       --db <path>.duckdb --rebuild
   ```
4. Verify: dimension query now returns `[(384,)]`. Re-run the failing
   cosine query — top-k makes sense.
