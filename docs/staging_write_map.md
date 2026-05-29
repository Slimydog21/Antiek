# Staging write map — every live-DB write the corpus ingest performs

SPR-01 M1. Diligence artifact: trace exactly which tables the ingest writes,
which columns, under which transaction, keyed how. This is the closed
contract the merge tool (`tools/merge_staging.py`) and every downstream
sprint inherit. Citations are `path:line` against this worktree.

## How the orchestrator reaches the write path

`tools/run_corpus_ingest.py` discovers candidates per source and defers the
write into an *ingest thunk* (`tools/run_corpus_ingest.py:96`,
`IngestThunk = Callable[[str], str]`). `execute_plan` calls each thunk with
the target db_path only on a real (non-dry-run) run
(`tools/run_corpus_ingest.py:225` `status = pc.ingest(db_path)`). Every
source's thunk converges on the same substrate write path:

- public-domain → `ingest_work` → `acquisition.books.ingest_servable_book`
  (`acquisition/books/public_domain.py:625`)
- arXiv → `acquisition.arxiv.adapter` which mirrors `ingest_pdf` directly
  (`acquisition/arxiv/adapter.py:224`) and registers via
  `ingest_servable_book` (`acquisition/arxiv/adapter.py:396`)
- open-access → `ingest_oa_item` → `ingest_servable_book`
  (`acquisition/openaccess/ingest.py:96`)

So the unified write surface is two `connect_write` transactions per work:

1. `ingest_pdf` (`acquisition/books/adapter.py:191`)
   `with connect_write(resolved_db_path, purpose="acquisition/books") as con:`
   — writes `documents`, `chunks`, `nodes`.
2. `ingest_servable_book` (`acquisition/books/adapter.py:331`)
   `with connect_write(resolved_db_path, purpose="read/books/ingest") as con:`
   — calls `register_book` (`substrate/books/ingest.py:80`) which writes the
   document's gate columns, `book_assets`, and (when a rights holder is
   named) `ip_holders`.

Both transactions go through `runtime.db_lock.connect_write`
(`runtime/db_lock.py:255`) — the single-writer flock. The merge tool reuses
exactly this; it never opens a raw `duckdb.connect` on the live file.

## Tables written, with id key and idempotency posture

| Table | Write site | Columns populated | Id / primary key | Idempotency | In merge? |
|---|---|---|---|---|---|
| `documents` | `insert_document` `substrate/graph/ops.py:161` | `document_id, source_uri, title, author, published_at, source_tier, document_type, investigation_id, raw_text, metadata, content_class, ip_holder_id` (`acquired_at`, `owner_user_id` take schema defaults) | `document_id` TEXT PK — content-stable: `doc-book-<sha256(bytes)[:16]>` for byte sources / `<sha256(abspath)[:16]>` for path sources (`acquisition/books/adapter.py:67`) | id-keyed; ingest uses `on_conflict="ignore"` (`acquisition/books/adapter.py:210`) | **YES** |
| `chunks` | `insert_chunk` `substrate/graph/ops.py:282` | `chunk_id, document_id, chunk_index, section_path, text, embedding, token_count` | `chunk_id` TEXT PK — content-addressed `chunk-<sha256(text)[:16]>` (`substrate/graph/ops.py:277`) | id-keyed; `_exists` short-circuits a duplicate insert (`substrate/graph/ops.py:278`) | **YES (with vectors)** |
| `nodes` | `insert_node` `substrate/graph/ops.py:324` | `node_id, canonical_label, node_type, embedding, graph_scope, metadata` (`created_at`, `degree_cached` defaulted) | `node_id` TEXT PK — content-addressed `node-<sha256(label\|type\|scope)[:16]>` (`substrate/graph/ops.py:321`) | id-keyed; ingest uses `on_conflict="ignore"` (`acquisition/books/adapter.py:244`) | **YES** |
| `book_assets` | `upsert_book_asset` `substrate/books/model.py:141` | `document_id, toc_json, page_count, pagination_scheme, cover_uri, provenance, license_basis` (`taken_down` defaults FALSE; takedown columns owned solely by `substrate.books.takedown`) | `document_id` TEXT PK, FK → `documents(document_id)` | id-keyed (upsert on document_id) | **YES** |
| `documents` (gate columns) | `update_document_gate_columns` `substrate/graph/ops.py:239` | `content_class`, `ip_holder_id` (UPDATE, with the index drop/recreate dance for DuckDB 1.5.2 FK-on-indexed-column) | `document_id` | id-keyed UPDATE — but the merged document row already carries the final `content_class` + `ip_holder_id` from staging, so the merge needs no separate UPDATE pass | folded into `documents` |
| `ip_holders` | `create_pre_onboarded` `substrate/ip_holders/__init__.py:82` | `ip_holder_id, display_name, legal_contact_email, status('pre_onboarded'), escrow_balance_usd(0), metadata` | `ip_holder_id` = **random** `ipholder-<uuid4[:12]>` (`substrate/ip_holders/__init__.py:80`); logical identity is `display_name` (found-or-created in `register_book` via `resolve_or_create_ip_holder` `substrate/books/ingest.py:74`) | found-or-created on `display_name`, NOT on the random id | **YES, keyed on `display_name`** (see note) |

### ip_holders — the one non-document-id key

`ip_holders` is the only ingest-touched table whose identity is **not** the
content-stable document id. The id is a random UUID; the dedup identity is
`display_name`. The merge therefore keys ip_holders on `display_name`
(insert only holders whose `display_name` is not already live). Because the
random staging id would otherwise differ from any live id for the same
publisher, and `documents.ip_holder_id` is a *soft* reference (TEXT, **no FK**
in the schema — `substrate/graph/schema.py:416` adds the column with no
`REFERENCES`), the merge resolves each merged document's `ip_holder_id` to
the **live** holder id for that display_name when one already exists live,
so two ingests of the same publisher do not fan out into duplicate escrow
accounts (the invariant `resolve_or_create_ip_holder` enforces within a
single DB). This is handled in dependency order: ip_holders before documents.

This sprint copies whatever escrow state the staged holder carries for a
*new* holder; it never re-decides rights or accrues escrow at merge (escrow
accrual is the attribution pipeline's job, not ingest's). For a holder that
already exists live, the live row (and its escrow balance) is authoritative
and is left untouched — the merge only remaps references.

## Tables explicitly OUT of the merge, with reason

- `edges` — the corpus-ingest path writes **no** edges. `insert_edge`
  (`substrate/graph/ops.py:390`) is never called by `ingest_pdf` /
  `ingest_servable_book` / the arXiv adapter. Edges are produced later by
  extraction, not by acquisition. Excluded.
- `write_log` (`substrate/graph/schema.py:944`) — observability side-effect
  of `connect_write` itself (`runtime/db_lock.py:107` `_log_write_event`),
  written best-effort on every lock close in BOTH staging and live. It is
  per-DB operational telemetry, not corpus content; copying staging's
  write_log into live would pollute live's observability with staging's
  internal lock events. Excluded.
- The typed **event log** is **not a DB table at all**. `emit_typed`
  (`substrate/event_log/events.py:241`) appends to per-investigation JSONL
  files at `{ANTIEK_RESEARCH_EVENTS_DIR}/{investigation_id}.jsonl`
  (`substrate/event_log/events.py:289` → `_append_jsonl` `:172`). It never
  touches the DuckDB file. So a staging-mode ingest's events land in the
  same JSONL trajectory regardless of which DB the rows go to; there is
  nothing event-shaped for the merge to copy, and the merge emits no events.
- Everything else in the schema (`syntheses`, `outcomes`, `deliverables`,
  ad/payout/federation/KYC tables, `discovery_cache`, `url_alias`, …) is
  written by other subsystems, never by the corpus ingest. Out of merge.

## Vector storage — proof vectors can be copied, not recomputed

- `chunks.embedding` and `nodes.embedding` are DuckDB native `FLOAT[]`
  columns (`substrate/graph/schema.py:94`, `:116`) — a nullable list of
  floats. There is **no VSS / HNSW extension and no vector index** anywhere
  in the substrate (grep for `vss|HNSW|create_hnsw|array_cosine` returns
  nothing). Similarity search is pure SQL via `list_dot_product`
  (`substrate/graph/search.py:104`, `cosine_similarity_sql`), reading the
  column directly with no index.
- The embedding is generated in `insert_chunk` / `insert_node` from the
  caller-passed `embedder.encode(...)` (`acquisition/books/adapter.py:219`,
  `:236`) and stored as `list(embedding)` (`substrate/graph/ops.py:288`).
- Consequence: a staging chunk's `embedding` is ordinary column data. A
  bulk `INSERT INTO chunks SELECT ... embedding ... FROM staging.chunks`
  copies the list element-for-element. The merge calls **no** embedding
  model — there is no model import in `tools/merge_staging.py`, asserted by
  the gate `grep -niE "embed|sentence_transformers|model.encode"`.
- **Vector index handling:** there is no index to rebuild or maintain.
  Decision: nothing to do post-merge — the absence of a vector index is the
  reason the keystone is safe today; if a VSS/HNSW index is introduced
  later, its rebuild cost becomes a merge-window concern and is escalated to
  the SPR-09 budget governor. Recorded here per M4.

## Merge order (dependency-respecting)

`ip_holders` (by display_name) → `documents` (ip_holder_id remapped to live
holder ids; document_id anti-joined) → `book_assets` (FK → documents) →
`chunks` (FK → documents) → `nodes` (no FK to documents; ordered last for
clarity). One `connect_write` transaction wraps all five copies so an
interruption rolls back atomically and a re-run inserts only net-new ids.
