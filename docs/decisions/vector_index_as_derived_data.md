# Vector index as derived data

**Sprint:** SPR-06 (DDIA-execution) · **Date:** 2026-05-24 · **Owner:** substrate
**Anchor:** Philosophy P8 (vector indexes are secondary, derived data over substrate-owned truth)

## The claim

Antiek's vector index — the `embedding FLOAT[]` column on `chunks` and `nodes`
in DuckDB — is **derived data**. It exists for query performance, not as a
source of truth. If lost (schema migration breaks, file corruption,
turbopuffer namespace wiped post-spike-graduation), it is rebuildable from
the underlying `text` column on the same rows.

The proof that the rebuild is real lives in
`scripts/reconstruct_vector_index.py` plus
`tests/test_reconstruct_vector_index.py`. Without those, P8 is aspiration.
With them, P8 is a runbook.

## Properties the script preserves

1. **Idempotent.** Running twice on a fully-embedded namespace makes zero
   writes. Verified by `test_reconstruct_is_idempotent`.
2. **Bounded.** `--max-chunks N` caps work per invocation; resumable across
   runs. Verified by `test_max_chunks_caps_work`.
3. **Cost-aware.** `--cost-budget USD` stops cleanly when projected spend
   exceeds the budget; reports skipped count so the operator can resume.
   Verified by `test_cost_budget_stops_cleanly`.
4. **Round-trip bit-identical.** A deterministic embedding model's output
   stored and re-read is byte-identical. Verified by
   `test_round_trip_preserves_vectors_bit_identical`. (Real OpenAI/
   Anthropic embedding models are stable but not deterministic between
   model versions; an ε-tolerance variant is the right next step when
   we move to a remote embedding model.)
5. **Single-writer.** Acquires the substrate flock via
   `runtime.db_lock.connect_write`; never touches DuckDB directly. The
   chaos test for db_lock (SPR-01) defends the underlying invariant.

## Why DuckDB-native, not a separate vector DB

Antiek's `embedding FLOAT[]` column + `cosine_similarity_sql` in
`substrate/graph/search.py` already serves the read path. Turbopuffer is
a documented future option (the spike script in `scripts/turbopuffer_spike.py`
is allowlisted under the boundary lint per SPR-03) but is NOT the source
of truth either way:

- DuckDB-native (today): vectors live next to the chunks they index.
  Reconstruction is "compute embedding, UPDATE chunks". Single table, single
  flock.
- Turbopuffer (eventual, gated): vectors mirror DuckDB. Reconstruction is
  "for each chunk in DuckDB, write vector to turbopuffer namespace". The
  source of truth is still DuckDB.

In both shapes, P8 holds. The reconstruction script today walks
DuckDB; a turbopuffer-aware variant would write to both. The reconstruction
property doesn't change.

## Turbopuffer path (future)

When `scripts/turbopuffer_spike.py` graduates from spike → adopted, the
reconstruction script gains a `--target=turbopuffer` flag. The flow:

1. Iterate chunks where vectors are missing in the turbopuffer namespace.
2. Compute embedding (same code path).
3. Write to BOTH DuckDB's `embedding` column AND the turbopuffer namespace
   in one txn-equivalent block (best-effort; turbopuffer's eventual
   consistency model means the substrate is the truth).

The flag is not landed today because turbopuffer adoption is operator-gated.

## Cost estimate at production scale

Operator-runnable: with the local SentenceTransformer model
(`sentence-transformers/all-MiniLM-L6-v2`, 384-dim), embedding cost is CPU
time only — no per-call USD. At ~10ms per chunk on a 2026-era laptop,
embedding 100k chunks takes ~15 minutes wall-clock with one flock window.

If/when the operator switches to a remote embedding model (OpenAI
text-embedding-3-small at ~$0.02/1M tokens):

- 100k chunks × 200 tokens average ≈ 20M tokens ≈ $0.40 per full rebuild.
- The `--cost-budget` flag bounds spend; a partial rebuild can be resumed.

These are estimates pinned to operator-verifiable inputs. The actual rate
table lives in the burn-telemetry ledger (`substrate/observability/burn.py`);
the reconstruction script doesn't duplicate it.

## Rejected alternatives

### A — Just rerun the original ingest

Tempting (ingest already embeds; just re-ingest). Rejected because:

- Ingest re-parses + chunks + embeds. Embedding is the only expensive step
  for a healthy substrate. Re-running ingest doubles the network + parse
  cost for no benefit.
- The reconstruction script can run on a substrate whose ingest path is
  partially broken (e.g., source URL gone, API rate-limited). The chunks
  are already there; we just need their vectors.

### B — Keep vectors in a separate file (parquet snapshot)

The vector index is small relative to the chunks table itself; the
storage win is marginal. The complexity win is real (no `embedding`
column in the schema), but the operability loss is significant — recall
queries would need to join across two stores. P8's claim ("derived data
over substrate-owned truth") is already satisfied by the in-table column.

### C — Build a long-running daemon that watches event_log

Auto-reconstruct on detected NULL embeddings. Tempting but adds a
moving part: another process, another set of failure modes. The script is
operator-invoked; the daemon can come later when the ops surface justifies
it.

## What would change this design

- Switching to turbopuffer as primary (currently spike-only). The script
  grows the `--target` flag; the property still holds.
- A future embedding model that is non-deterministic between calls (e.g.,
  a fine-tuned model with stochastic inference). The round-trip test
  switches from bit-identical to ε-tolerance with a documented ε.
- Multi-host substrate (P3 reconsider trigger). Reconstruction becomes a
  distributed problem; today's single-host script wouldn't fit.

## References

- `~/specs/antiek-ddia-philosophy/index.html` — P8.
- `scripts/reconstruct_vector_index.py` — the canonical implementation.
- `tests/test_reconstruct_vector_index.py` — the proof.
- `substrate/graph/search.py` — `EmbeddingModel` Protocol + cosine-similarity SQL.
- `substrate/graph/schema.py` — `chunks.embedding FLOAT[]` column.
- `docs/integration_turbopuffer.md` — turbopuffer adoption gating.
- Kleppmann × Pragmatic Engineer interview — vector indexes added to DDIA-2e
  as an indexing strategy (storage-engine chapter), not a data model.
