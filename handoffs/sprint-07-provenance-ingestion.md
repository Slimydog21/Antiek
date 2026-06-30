## Sprint SPR-07 — Handoff

### Status
done

### Honesty banner (rigor #1) — DO NOT DROP
Provenance persistence is REAL and TESTED against SPR-04 cassettes.
Live research runs are INERT until activation SPR-03 flips provider keys.
A green SPR-07 != "the operator can run live research."

### Deliverables
- `runtime/research_runner/provenance_ingest.py` — source ingest + supported_by wiring
- `runtime/research_runner/promotion_funnel.py` — cascade source persistence path
- `substrate/graph/ops.py` — URL+hash dedup helpers, anchor nodes, provenance edges
- `substrate/constants.py` — `CITES_RELATION` vocabulary
- `interfaces/research/api/cascade_synthesizer.py` — synthesis artifact as Document
- `orchestration/cascade_session.py` — artifact persist on `join_and_merge`
- `apps/reading/src/components/reader/blocks/Citation.tsx` — unresolved citation degrade
- `apps/reading/src/modes/DeepResearchWorkspace/index.tsx` — cite source + chunkId
- `roles/note_taker/distill_query.py` + `distill_routes.py` — chunk_id on distilled nodes
- `tests/test_provenance_ingestion_spr07.py`

### Milestones
- [x] M1 sources persisted as readable Documents (content_class NOT NULL)
- [x] M2 dedup (normalized URL + content hash; threshold + false-merge risk documented)
- [x] M3 synthesis artifact persisted (synthesizer path via cascade_synthesizer; no longer ephemeral)
- [x] M4 provenance edges (cites / supported_by written; resolved_by preserved)
- [x] M5 citation opens the real source at the cited chunk

### Verification gate results
- sources-readable: **pass** — `test_web_source_persisted_as_readable_document`
- dedup: **pass** — `test_dedup_reingest_same_url_and_body`, `test_dedup_same_url_different_hash_does_not_merge`
- artifact-persisted: **pass** — `test_cascade_persists_artifact_and_edges`
- edges: **pass** — supported_by + cites asserted in cascade test; resolved_by preserved in orchestration suite
- citation-opens: **pass** — Reader.test citation click + DRW `openDocument(..., { chunkId })` conformance
- single-writer+rights: **pass** — all writes via `substrate/graph/ops`; `personal_reading` stamped; legal gate flagged below

### Gate commands + results
```bash
# Python (venv)
.venv/bin/python -m pytest tests/test_provenance_ingestion_spr07.py -q
# 8 passed

.venv/bin/python -m pytest tests/test_parallel_orchestration.py -q
# 8 passed

# TypeScript
cd apps/reading && npm test -- --run src/components/reader/Reader.test.tsx src/__tests__/oneReader.conformance.test.ts
# 50 passed
```

### Logged decisions (rigor #5)
- **dedup threshold** = exact match on `normalize_source_url(url)` AND `sha256(content_hash(raw_text))`. Rationale: byte-identical bodies only; avoids slug-reuse false merge. Reversal: if >1% same-url/different-revision cases need side-by-side retention, operator adds version suffixes (documented in `substrate/graph/ops.py`).
- **content_class for fetched web sources** = `personal_reading` (deny-by-default via `ingest_url` + `PERSONAL_READING_CONTENT_CLASS`). Rationale: third-party web fetch; owner-readable, never public-servable without operator gate.
- **edge-type names** `cites` / `supported_by` — checked existing vocab: `supported_by` already in `INSIGHT_QUESTION_RELATIONS` with `source_document_id`/`chunk_id` columns; `resolved_by` preserved unchanged. `cites` is NEW (no synonym existed) for artifact→source bibliography; uses `CITES_RELATION` constant.

### OPERATOR DECISION surfaced (rigor #1, #5) — NOT resolved here
Serving fetched web sources touches the legal gate. Sources are ingested as `personal_reading` and open through the §9.0 `/read` gate (deny panel for non-servable). Operator owns whether/when fetched web bodies become servable.

### Partial-failure behaviors enumerated + tested (rigor #3)
| Path | Behavior |
|------|----------|
| mid-run fetch failure | `source_ingest_skipped` on insight metadata; no `supported_by` edge |
| dedup collision (same URL, different hash) | No merge; new body would ingest on next unlike hash |
| paywalled/blocked source | `ingest_skipped` / low_word_count; insight promotes without source edge |
| artifact cites failed-fetch source | CitationSpan omitted; `Citation.tsx` renders non-clickable `[marker]` |
| source already personal_reading | `content_class` not re-stamped servable (`test_personal_reading_source_not_restamped_servable`) |

### Steelman of artifact-only ingestion (rigor #2)
Storing only the synthesis report with outbound URLs is lighter — no per-source fetch, storage, or rights surface. **Full ingestion still wins**: clicking a citation stays inside the one Reader at the cited chunk; source bodies are durable in the graph for dedup and provenance queries.

### Single-writer invariant
Every node + edge + document write goes through `substrate/graph/ops` (`insert_document`, `insert_node`, `insert_edge`) on a `LockedConnection`. Source ingest runs in a **separate** short lock before promotion BEGIN (avoids nesting `ingest_url`'s lock — deadlock). Cascade artifact persist runs in `join_and_merge` on one `connect_write` transaction.

### Next sprints can start when
This branch merges to `reader/integration`: SPR-08 (search opens results) and SPR-09 (convergence verification) can consume the persisted provenance graph.