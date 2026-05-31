# Sprint SPR-01 — Handoff (Staging-DB → merge write path)

## Status
done (sharpen round applied — both MERGE-WITH-FIXES defects closed)

## Files touched
- `docs/staging_write_map.md` — M1 write-map: every live-DB write at file:line, merged-table list, vector-copy proof, vector-index decision.
- `runtime/staging_db.py` — `prepare_staging_db` (schema bootstrapped by the canonical `init_database`, never hand DDL), `resolve_ingest_target`, `is_staging_mode`.
- `tools/run_corpus_ingest.py` — `--staging-db` mode (zero live writes during ingest; prod-write guard + lock pre-flight skipped because staging is never prod; prints the follow-up merge command).
- `tools/merge_staging.py` — ATTACH staging READ_ONLY + explicit-column anti-join `INSERT…SELECT` per table inside one `connect_write`/one BEGIN-COMMIT. Dependency order ip_holders→documents→book_assets→chunks→nodes. Idempotent on the content-stable id; atomic rollback; vectors copied as `FLOAT[]`, never recomputed. **Sharpen #1:** explicit projected column list + `_assert_schema_compatible` pre-merge guard (names AND order, filtered on `table_catalog`) — a positional `s.*` is gone.
- `tools/measure_merge_window.py` — **Sharpen #2:** re-runnable production-scale window measurement + batch-size slope.
- `tests/test_merge_staging.py` — 19 tests (15 original + 4 added this round): the original keystone properties plus `test_merge_into_migration_path_live_db`, `test_schema_divergence_aborts_merge_before_any_insert`, `test_merge_window_at_production_scale`.

## Milestones
- [x] M1: Write-map of every live-DB write (file:line) — `docs/staging_write_map.md`.
- [x] M2: Staging connection helper + `--staging-db` mode (zero live writes during ingest) — proven by `test_staging_ingest_zero_live_writes`; **column-order divergence under migration now guarded** (sharpen #1).
- [x] M3: `tools/merge_staging.py` — ATTACH + explicit-column `INSERT…SELECT` in one `connect_write` — `test_merge_is_single_connect_write`, `test_counts_match_after_merge`, `test_merge_leaves_no_orphans`.
- [x] M4: Vectors COPIED not recomputed — `test_vectors_copied_element_identical`, `test_no_embedding_call_in_merge_module`.
- [x] M5: Idempotency + atomic rollback + resumable + id-keyed-not-title — `test_remerge_is_idempotent_zero_inserts`, `test_atomic_rollback_on_mid_merge_failure`, `test_resumable_after_interruption`, `test_idempotency_keys_on_document_id_not_title`.
- [x] M6: API readable during ingest + bounded merge window — `test_live_readable_during_ingest`, `test_merge_window_is_bounded` (toy regression guard), `test_merge_window_at_production_scale` + `tools/measure_merge_window.py` (production figure).

## Merge-window measurement (M6) — the keystone number
Measured via `.venv/bin/python -m tools.measure_merge_window` against temp DBs
(the spec sanctions a temp-DB measurement; numbers below are dev hardware —
Apple Silicon — not the CCX23, so the box may differ; the SHAPE and the slope
are the defensible claim).

Batch shape = first prod ingest (2026-05-29): **31 documents, 5,017 chunks**, one node/doc.

| embedding dim | chunks | connect_write-held window |
|---|---|---|
| 16 (stub embedder) | 500 | 0.059s |
| 16 | 2,000 | 0.063s |
| 16 | 5,017 | **0.072s** (range 0.071–0.084s over 4 runs) |
| 384 | 1,000 | 0.070s |
| 384 | 5,017 | **0.125s** |
| 768 | 5,017 | ~0.13s |

- **connect_write-held merge window at production scale (5,017 chunks): ~0.07s at 16-dim, ~0.13s at 384/768-dim ← the keystone number.**
- staging ingest duration: NOT in the window (off the live writer by design). The first prod ingest's slow work was minutes; the merge holds the live writer only for the copy above.
- live reads during ingest: succeed throughout (`test_live_readable_during_ingest`: ok > 0, fail == 0) — the ingest writes a separate staging file, so the live reader is never contended by it.

### Slope (rigor #1 — did the window grow with batch size?)
Yes, **linear in chunk count**, as expected for a single `INSERT…SELECT`:
- 16-dim: ~2.76 µs/chunk
- 384-dim: ~13.9 µs/chunk (≈ linear in embedding dim — a 24× wider vector ≈ 5× the per-chunk cost, the rest being fixed per-row overhead)

Extrapolation is honest and reassuring: even at 100,000 chunks / 768-dim the
window is ~2-3s — still seconds-scale, still bounded, still distinct from the
ingest. The slope, not a single number, is the defensible contract.

## Merged-table list (from M1 write-map)
- `ip_holders` — keyed on **display_name** (random UUID id; merge remaps documents to the live holder id).
- `documents` — `document_id` (content-stable).
- `book_assets` — `document_id` (FK → documents).
- `chunks` (+vectors) — `chunk_id` (content-addressed).
- `nodes` — `node_id` (content-addressed).
- Excluded: `edges` (ingest writes none), `write_log` (per-DB lock telemetry), the typed event log (JSONL, not a DB table), all other subsystems' tables.

## Decisions made mid-flight
- **Vector index handling:** there is no VSS/HNSW index in the substrate (similarity is pure-SQL `list_dot_product`), so nothing to rebuild post-merge. If one is added later its rebuild cost becomes a merge-window concern → escalate to SPR-09 budget governor. Recorded in `docs/staging_write_map.md`.
- **Staging schema bootstrap:** run the canonical `substrate.graph.schema.init_database` against the staging file — same DDL as live, cannot drift. Reverse-if: never; a hand-copied DDL is the anti-pattern this avoids.
- **Sharpen #1 — explicit column projection + pre-merge schema guard:** `SELECT s.*` was replaced by `INSERT INTO t (c1…cn) SELECT s.c1…s.cn` where the column list is read from the LIVE catalog at merge time, and `_assert_schema_compatible` aborts (raising `SchemaDivergence`, before BEGIN) if any merged table's column names+order differ between staging and live. The introspection filters on `table_catalog` (not `table_schema`) because `information_schema` spans every ATTACHed database and both live+staging expose a `main` schema. This closes the latent silent-corruption vector: a future migration that rebuilds/reorders a live table while a fresh staging file keeps the new order now fails loudly instead of shuffling data into wrong columns. Reverse-if: only if the substrate adopts a column-name-addressed bulk-copy primitive that DuckDB guarantees order-independent (it does not today).

## Assumptions surfaced (rigor #1)
- The measurement uses a bulk-insert to fill staging because the merge's copy cost is independent of HOW staging was filled (it reads `staging.<table>` and copies). Verified: the copy path under measurement is byte-identical to the connector-fed path.
- Embedding dim caveat is explicit: stub is 16-dim; prod embedders are wider. Measured at 16/384/768 so the reader can interpolate; the slope scales ≈ linearly in dim.

## Steelman of rejected alternative (rigor #2)
"Background queue writing live, interleaved via db_lock in short bursts" — honestly the simpler model: no second file, no merge step, reuses the single-writer path directly. **Why it loses:** the slow work (embedding 5,017+ chunks, minutes-to-hours) happens *inside* a held `connect_write`, so a long embed run stalls the live API exactly under load; interleaving can't decouple the minutes-to-hours embed cost from the lock — it only chops it into still-blocking bursts. Staging moves ALL slow work off the lock; only the ~0.1s copy (measured above) ever holds it. The measurement is the evidence the steelman loses: 0.07–0.13s held vs minutes-to-hours of embedding.

## Open questions discovered
- Does a VSS/HNSW index rebuild dominate the merge window if one is introduced at scale? → SPR-09 budget governor. (No index today, so moot now.)
- The box (CCX23) figure is unmeasured here (dev-hardware numbers only); an on-box run of `tools.measure_merge_window` against a temp DB confirms the box-specific window when convenient. The slope/shape claim does not depend on it.

## Out-of-scope temptations encountered
- None acted on. Did NOT touch connector internals, rights re-classification, scheduling/cadence, cross-source dedup, or any second DB engine. The keystone is the write path only.

## Downstream can start when
- SPR-02/03/04 + Wave-2 connectors write via `--staging-db` and merge via `tools/merge_staging.py`. The explicit-column + schema-guard contract means a connector that adds a column to a merged table will trip `SchemaDivergence` loudly until both live and staging carry it in the same order — a guard, not a silent corruption.
