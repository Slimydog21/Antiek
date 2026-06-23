# DuckDB plane — canonical reference

**Status:** Operator + agent source of truth for how DuckDB is used across Antiek.  
**Complements:** `docs/architecture_notes.md` §2.1–§2.3, `infrastructure/SKILL.md`, `runtime/db_lock.py`, `CLAUDE.md` invariants.

The implementation is disciplined so the design is **hard to vary**: one write funnel, many explicit read paths, no second truth store.

### Objective function (egghead verdict — not “more tables”)

**MINIMIZE** writable DuckDB stores per product stage; duplicate ledgers; raw
`duckdb.connect` on graph paths; Harness/Engine OLTP for cost or session state.

**MAXIMIZE** enforced **W / R / E / —** per layer (§10); `connect_write(purpose=…)`
and `connect_read`; export manifests + `analytics.duckdb` rebuild views; mechanical
gates (`check_duckdb_funnel`, harness boundary); jsonl-first Engine cost;
single-writer-per-store (L3, L7).

---

## 1. Seven laws (invariants)

| # | Law | Enforcement |
|---|-----|-------------|
| L1 | Append-only **typed events** are truth | `substrate/event_log`, `research_events/*.jsonl` |
| L2 | **DuckDB** holds derived OLTP state | Graph, syntheses, outcomes — replayable from events |
| L3 | **One graph writer process** (per store) | Stage 0: one `antiek.duckdb` writer; Stage 1+: single-writer-per-personal-graph + single-writer-on-`shared_substrate` (`substrate/multi_user/graph_router.py`); `uvicorn --workers 1`, `connect_write` only |
| L4 | Every write names a **`purpose`** | Stamped in `.write.lock` + `write_log` table |
| L5 | Every substrate read uses **`connect_read`** | `read_only=True`; never open writer path for analytics |
| L6 | Primary file on **local NVMe** | Not Hetzner Volume / network disk |
| L7 | Remote research fan-out **never** writes the host graph | §16 exemption: per-investigation logs only; host `db_lock` sole graph writer |

**Escalation (measured):** Postgres + externalized event log — not `--workers 4`, not ClickHouse (see `integration_posthog.md` REJECT).

---

## 2. Store topology

### Stage 0 vs Stage 1+ (substrate transition)

| Stage | OLTP layout | Lock identity | Code anchor |
|-------|-------------|---------------|-------------|
| **Stage 0** (operator-only baseline) | Single file `$ANTIEK_DUCKDB_PATH` (`~/.antiek/antiek.duckdb`) | One graph writer process on that file | Prod default until migration |
| **Stage 1+** (multi-user) | `~/.antiek/personal_graphs/{user_id}.duckdb` per user + `~/.antiek/shared_substrate.duckdb` | `user_id` flock per personal graph; global flock on shared substrate | `GraphRouter`, `resolve_personal_graph`, `resolve_shared_substrate` in `substrate/multi_user/graph_router.py`; env `ANTIEK_PERSONAL_GRAPHS_DIR`, `ANTIEK_SHARED_SUBSTRATE_DB` |

Stage-0 file is the migration source for operator `__operator__` into Stage-1 paths;
**do not** run parallel writers on the same `.duckdb` file. Remote research remains
**E-only** on the host graph (L7) in all stages.

| Store | Path | Writer | Role |
|-------|------|--------|------|
| **Antiek OLTP** | Stage 0: `$ANTIEK_DUCKDB_PATH` (prod: `~/.antiek/antiek.duckdb`); Stage 1+: personal + shared paths above | Host FastAPI (per-store locks) | Graph schema V1–V13, syntheses, outcomes, federation |
| **Event log** | `~/.antiek/research_events/` | Same process (+ remote child logs) | Primary audit / replay |
| **Corpuscrawl** | `~/.corpuscrawl/corpus.duckdb` | `corpuscrawl build/sync` | FTS/BM25 over specs/memory — **not graph truth** |
| **Analytics** | `~/.antiek/analytics.duckdb` | `scripts/rebuild_analytics_duckdb.py` | Rebuild-only; joins exports + PostHog Parquet |
| **Nightly backup** | R2 `nightly/antiek-*.tar.gz` | `antiek-backup` | `EXPORT DATABASE` Parquet + jsonl rsync |

Do **not** merge corpuscrawl into `antiek.duckdb`. Do **not** use InsForge Postgres as a second graph writer.

---

## 3. Schema craftsmanship

- **Versioned SQL blocks** in `substrate/graph/schema.py`: `ANTIEK_GRAPH_SCHEMA_V1_SQL` … **V13**.
- **`CHECK` constraints** mirror Pydantic literals (`syntheses.status`, `node_type`, …) — `tests/test_backtest_db.py`.
- **SOLE writer** documented per table in schema comments (e.g. `middleware/archive/` for syntheses).
- **JSON as `TEXT`** until a concrete SQL `WHERE` on JSON fields forces VARIANT (documented in schema header).
- **`write_log` (V9)** — observability for every `connect_write` close (duration, purpose, success).

**New table checklist**

1. Row in `docs/ATOM_LAYER_REGISTRY.md`
2. `SOLE writer` line in `schema.py`
3. Drift test if enums match Pydantic
4. Migration block `ANTIEK_GRAPH_SCHEMA_VN_*` — never hand-edit prod without migration

---

## 4. Write funnel

```python
from runtime.db_lock import connect_write

with connect_write(db_path, purpose="ingest") as con:
    con.execute(...)
```

- `purpose` is diagnostic + `write_log` — prefer stable verbs from `substrate/schemas/actions.py` where applicable.
- **Quack swap (2026+):** `connect_write` / `LockedConnection` shape is the abstraction; do not add a parallel coordinator above `db_lock`.

---

## 5. Read funnel

```python
from runtime.db_lock import connect_read

con = connect_read(db_path)
try:
    con.execute("SELECT ...")
finally:
    con.close()
```

- API federation, `corpus_audit`, eval harnesses, **export scripts** — all `connect_read`.
- Operator ad hoc: `duckdb -readonly antiek.duckdb` on VM only.

---

## 6. Analytics plane (maximize DuckDB without touching the writer)

### 6.1 Operator / CI export (curated tables)

```bash
./.venv/bin/python scripts/export_analytics_parquet.py \
  --db "$ANTIEK_DUCKDB_PATH" \
  --out ~/.antiek/exports/parquet/$(date -u +%Y%m%d)
```

Writes Parquet shards + `manifest.json` (`ANTIEK_PARAM_VERSION`, row counts,
`table_layers` map per §10, UTC timestamp). Default export bundles:

| Bundle | Tables | §10 layer |
|--------|--------|-----------|
| Research | `syntheses`, `outcomes`, `manifest`, `write_log`, `documents`, `chunks`, `nodes`, `edges` | Deep Research |
| Write / Speak | `deliverables`, `deliverable_sections`, `section_blocks`, `notebooks`, `notebook_blocks`, `loop_3_checklist`, `interview_projects`, `interviews` | Write, Speak, Loop 3 |
| Marketplace | `payout_decisions`, `payout_transfers`, `discovery_summary` | Read monetization + discovery |
| **Engine** (jsonl) | `dispatch_calls.parquet` from `scripts/export_dispatch_events_parquet.py` | AI Engine — `dispatch.call` cost; joins syntheses in analytics views |
| **Agents** (OLTP slice) | `agent_write_log.parquet` — `promotion_funnel`, `cascade_merge`, `merge_staging`, `monitor_*`, `exercise:*` | Host graph writer audit; pairs with Engine jsonl on investigations |

**Read-only** on `antiek.duckdb` — safe while `antiek.service` is running. Engine export reads
``research_events/*`` (jsonl **or** sealed parquet) via ``trajectory()`` — never the graph writer.

**Discovery (corpuscrawl):** ``manifest.json`` → ``plane_artifacts.corpuscrawl`` snapshots
``~/.corpuscrawl/corpus.duckdb`` via ``connect_read`` (FTS store — not merged into ``antiek.duckdb``).

### 6.2 Rebuild analytics DuckDB

```bash
./.venv/bin/python scripts/rebuild_analytics_duckdb.py \
  --parquet-dir ~/.antiek/exports/parquet/20260101 \
  --out ~/.antiek/analytics.duckdb
```

Optional: drop PostHog export Parquet into the same dir (`posthog_events.parquet`) before rebuild for JOIN queries.

Rebuild installs cross-layer **views** when base tables exist:
`v_research_synthesis_outcomes`, `v_write_deliverable_depth`,
`v_speak_interview_funnel`, `v_write_log_purpose_rollup`,
`v_engine_dispatch_by_workflow`, `v_research_investigation_dispatch_cost`
(when `dispatch_calls` + `syntheses` loaded),
`v_agents_write_log`, `v_agents_write_rollup` (when `write_log` loaded).

**Product mirror (PostHog):** `substrate/observability/product_mirror.py` — optional
capture at `middleware/archive` (synthesis archived) and `interviews/complete`
(speak), always keyed by `antiek_event_id` when jsonl emitted first.

### 6.3 Full consistent snapshot (nightly)

`infrastructure/ansible/templates/backup.sh.j2` already runs:

```sql
EXPORT DATABASE '...' (FORMAT PARQUET);
```

Use backup Parquet for disaster recovery; use **§6.1** for lightweight analyst tables between backups.

---

## 7. PostHog boundary

- **DuckDB:** defensibility — syntheses, outcomes, cohort SQL, Phase 8 skill growth signals.
- **PostHog:** product liveness — UI funnels, errors, session replay (DOM).

Bridge: `posthog.capture(..., properties={"antiek_event_id": ...})` matching jsonl `event_id`.  
Weekly: PostHog → Parquet → ingest in `rebuild_analytics_duckdb.py`.  
PostHog is **never** the sole record of `archive_synthesis` or tier overrides.

---

## 8. DuckDB features — intentional use

| Feature | Location | Rule |
|---------|----------|------|
| Recursive CTEs | `graph/traverse` | Golden fixtures |
| `FLOAT[]` embeddings | `chunks`, `nodes` | CI dimension / null checks |
| FTS | corpuscrawl only | BM25 + provenance; no fake semantic search |
| `read_parquet` / `EXPORT` | analytics + backup | Immutable snapshots |
| Window functions | `middleware/cohort` | One owning module + snapshot tests |
| Temporal edges | `valid_from` / `valid_to` | Prefer one documented `edges_asof` view |

---

## 9. Gates (fail closed)

| Gate | Location |
|------|----------|
| Single-writer concurrency | tests on `db_lock` |
| CHECK ↔ Pydantic | `test_backtest_db.py` |
| Agent regressions | `tests/regression/agent_failures/*.yaml` |
| Session discipline | `docs/agent-execution/HARD_TO_VARY.md` |
| Corpuscrawl citation hygiene | `corpuscrawl doctor` (exit 5) |
| Remote fan-out | `substrate/invariants/single-writer-remote-exec.toml` |

---

## 10. Antiek product & engine matrix (maximize DuckDB per layer)

Surfaces are replaceable; **substrate + DuckDB discipline** compounds. Each row states
how that layer may touch DuckDB. **W** = write via `connect_write`; **R** = read via
`connect_read`; **E** = emit typed event (jsonl truth, may not need DB on hot path);
**—** = must not open `antiek.duckdb` for write.

| Layer | Product meaning in Antiek | DuckDB | Primary tables / artifacts | Maximize means (enforce, not expand OLTP) |
|-------|---------------------------|--------|----------------------------|-------------------|
| **Deep Research Workflow** | Loop 1 — 8-phase protocol, ingest → graph → synthesize → archive (`interfaces/research/`, `orchestration/loop_one/`) | **W+R+E** | `documents`, `chunks`, `nodes`, `edges`, `syntheses`, `synthesis_substrate_manifest`, `outcomes`, `chunk_tier_overrides` | Every phase transition **E**; graph mutations **W** only through acquisition/middleware/graph writers; syntheses **SOLE** `middleware/archive/` |
| **Read** | Surface B — Wrestle / PDF region → distillation (Loop 2); `apps/reading/` + `read/*` API routes | **R** (+ **W** for impressions/audit only) | Reads: `chunks`, `nodes`, `documents`; writes: `read/ad_impressions`, `arxiv_serve_audit` where routed | Read path never holds write lock for “query PDF”; promotion into graph uses same ingest funnel as research |
| **Write** | Surface C — deliverables, sections, prose (`deliverables/*`, `write_routes.py`, notebooks) | **W+R+E** | `deliverables`, `deliverable_sections`, `section_blocks`, `notebooks`, `notebook_blocks` | Creation prose is product state; still **one writer process**; purposes `deliverables/*`, `sections/*`, `api:*notebook*` |
| **Speak** | Surface D — interview / voice (`interview/`, `speak_routes.py`, Loop 4 turns) | **W+R+E** | `interview_projects`, `interviews`; transcripts → `documents` + graph ingest | Interview completes → **primary source** in graph; dispatch for transcription is **E** (`dispatch.call`), not a second DB |
| **AI Engine** | `substrate/dispatch/` + `context_pack/` + `constants.py` — routes models, assembles packs | **E** (cost); **R** for pack assembly | Reads graph/chunks for retrieval; emits `dispatch.call` events | Engine does **not** bypass schemas; `ANTIEK_PARAM_VERSION` stamped on every archived synthesis |
| **AI Harness** | `substrate/cli harness`, hooks, conversation compaction, project forks | **—** (filesystem + conversation event logs) | `.antiek/` harness state per project; not OLTP graph | Harness mutates **git + session logs**, not graph directly; graph effects only through substrate APIs/CLI that call **W** |
| **AI CLIs** | `antiek` subcommands: `burn`, `branch`, `compact`, `queue`, `lint`, acquisition `__main__` tools | **W** or **R** per command | `burn` → telemetry tables/events; ingest CLIs → `connect_write(purpose="ingest")`; `export_analytics_parquet.py` → **R only** | CLIs that write graph **must** use `connect_write`; never `duckdb.connect(path)` for write |
| **AI Agents** | Roles (`roles/`), bridges, orchestrator, remote fan-out (Daytona) | Host: **W+R+E**; remote: **E** only | Orchestrator **R** for chunk resolvers; promotion **W** `promotion_funnel`; cascade **W** `cascade_merge` | Remote agents append child jsonl; **host** `connect_write` is the only graph writer (L7) |

**Loops (master-spec vocabulary):**

| Loop | DuckDB role |
|------|-------------|
| Loop 1 (research) | Full graph + syntheses lifecycle |
| Loop 2 (wrestle/read) | Read-heavy; distilled claims enter graph via ingest/extract |
| Loop 3 (creation checklist) | `loop_3_checklist` + deliverables/notebooks |
| Loop 4 (speak / interviewer) | `interviews` state machine + document ingest |

---

## 11. Table ownership (SOLE writers — do not vary)

Extract from `substrate/graph/schema.py` comments and middleware READMEs. If code
writes a row without going through the named owner, that is a **defensibility defect**.

| Table | SOLE writer path (conceptual) |
|-------|-------------------------------|
| `syntheses`, `synthesis_substrate_manifest` | `middleware/archive/` |
| `outcomes` | `middleware/outcomes/` |
| `chunk_tier_overrides` | tier override emit path |
| `documents`, `chunks`, `nodes`, `edges` | `acquisition/*`, `processing/*`, graph ingest (always `connect_write`) |
| `deliverables`, sections, blocks | `interfaces/research/api/app.py` write routes + write helpers |
| `notebooks`, `notebook_blocks` | notebook API routes |
| `interview_projects`, `interviews` | interview + speak routes |
| `write_log` | `runtime/db_lock` (automatic on every write close) |
| Federation tables | `substrate/cross_graph/*` via federation API purposes |

New table → add row here **before** merge.

---

## 12. `connect_write` purpose discipline

`purpose` is freeform but must be **stable and grep-able**. Prefer `surface/verb` or
`api:verb` namespaces. Known families (extend only deliberately):

| Namespace | Examples | Layer |
|-----------|----------|-------|
| `ingest`, `extract`, `promotion_funnel` | acquisition, remote merge | Research / agents |
| `deliverables/*`, `sections/*` | create, prose_update, attach_block | Write |
| `interview_projects/*`, `interviews/*` | create, invite, turn, complete | Speak |
| `federation/*` | register_partner, inbound_citation | Research / federation |
| `monitor_*` | monitor_create, monitor_refresh | Engine / ops |
| `read/*` | ad_impressions | Read (monetization telemetry) |
| `api:*` | file_document, ai_undo, notebook CRUD | HTTP surface |
| `exercise:*` | scripts/exercise_substrate.py only | CI / dev |

**Lint (shipped):** ``scripts/check_duckdb_funnel.py`` — AST scan of production
layers; allowlist in that script (``runtime/db_lock.py``, analytics rebuild,
``retrieval_substrate`` copy path, ``escape_hatch``). Wired in
``scripts/canonical_verify.sh agent-gates``.

---

## 13. AI Engine, Harness, CLIs, Agents — DuckDB contracts

### AI Engine (`dispatch` + `context_pack`)

- **Reads** graph evidence through `connect_read` resolvers (chunk text, traverse).
- **Writes** only indirect: role outputs trigger middleware that owns table writes.
- **Emits** `dispatch.call` (and similar) on jsonl with provider, model, role, cost —
  export to `analytics.duckdb` for $/investigation joins.
- **Does not** store prompts in DuckDB by default (defensibility: prompts live in
  events if at all, with redaction policy).

### AI Harness (`antiek harness`, hooks, compaction)

- **Compaction** (`antiek compact`) operates on **conversation** event logs under
  project roots — not a substitute for `substrate/event_log` compaction.
- **Harness fork/apply** — filesystem; graph changes only when a harnessed run calls
  substrate ingest through normal **W** paths.
- **Lint (shipped):** ``scripts/check_harness_graph_boundary.py`` — ``substrate/cli/``
  must not import ``duckdb``, ``runtime.db_lock``, or call ``connect_write`` /
  ``connect_read`` (wired in ``canonical_verify.sh agent-gates``).

### AI CLIs

| CLI | DuckDB |
|-----|--------|
| `antiek burn` | `report` — jsonl ``dispatch.call`` (+ optional ``analytics.duckdb``); `write-log` — ``connect_read`` ``write_log`` rollup (`substrate/observability/burn_cli.py`) |
| `antiek queue` | Inspect bounded queues (no graph write) |
| `antiek compact` | Conversation logs only |
| `scripts/export_analytics_parquet.py` | **R only** |
| `scripts/export_dispatch_events_parquet.py` | **jsonl only** (Engine) |
| `scripts/rebuild_analytics_duckdb.py` | Separate `analytics.duckdb` file |
| `scripts/run_analytics_plane.sh` | Chains OLTP export + dispatch export + rebuild |
| Acquisition modules (`tools/run_corpus_ingest.py`, exa, substack, …) | **W** with explicit purpose |

### AI Agents (orchestrator, roles, remote exec)

- **Orchestrator** holds in-process futures — single VM, single writer (infra SKILL).
- **Remote fan-out** (§16 exemption): child investigations log to **their** jsonl;
  **promotion_funnel** / **cascade_merge** merge on host with `connect_write`.
- **Agents must not** open writer connections in parallel processes.
- **Analytics:** ``agent_write_log.parquet`` (slice of ``write_log``) + views
  ``v_agents_write_log``, ``v_agents_write_rollup``; purposes defined in
  ``substrate/analytics/agent_write_purposes.py`` (do not fork).
- **Sealed investigations:** ``export_dispatch_events_parquet.py`` reads sealed
  ``*.parquet`` trajectories via ``trajectory()`` — same as live jsonl.

---

## 14. Event log ↔ DuckDB (two-layer truth)

| Layer | Path | Compaction |
|-------|------|------------|
| Substrate events | `~/.antiek/events.jsonl` (+ per-investigation under `research_events/`) | `antiek compact` / future Parquet per `substrate/event_log/README.md` |
| Graph projection | `antiek.duckdb` | Rebuild from replay if needed; nightly `EXPORT DATABASE` |

**Maximize DuckDB:** periodic `events.parquet` (when compaction ships) **feeds**
`analytics.duckdb` alongside `export_analytics_parquet.py` — same manifest contract,
`ANTIEK_PARAM_VERSION` in path.

**Export parity (v1 gate):** after `scripts/export_analytics_parquet.py` against a
temp or fixture DuckDB, `manifest.json` in the output dir must include
`antiek_param_version` (stamped from `ANTIEK_PARAM_VERSION`) and a
`table_layers` object mapping exported table names to §10 layer keys. CI or
operator smoke: run export on a disposable DB, then `jq` the manifest for those
keys before trusting a dated Parquet dir for rebuild.

---

## 15. Test funnel policy (new tests)

- **Production layers** (`interfaces/`, `substrate/`, `orchestration/`, `acquisition/`,
  `middleware/`, `scripts/` except allowlisted rebuild): no raw `duckdb.connect` for
  graph paths — use `runtime.db_lock.connect_read` / `connect_write` or `:memory:` /
  temp fixtures documented in the test.
- **New tests** that touch a real `.duckdb` path should prefer `connect_read` helpers
  from `tests/conftest.py` when added; full-suite migration is phased (grep debt logged
  in sprint handoff, not a single-PR requirement).
- **Allowlist** for intentional raw connects: `tests/`, `runtime/db_lock.py`,
  `scripts/rebuild_analytics_duckdb.py`, analytics rebuild paths — see
  `scripts/check_duckdb_funnel.py`.

## 15b. Funnel violations to eliminate (craftsmanship debt)

- **Fixed:** `orchestration/loop_one/orchestrator.py` hybrid search uses `connect_read`.
- **Fixed (2026-06-23):** `interfaces/research/api/*` read handlers (incl. `app.py`,
  `write_routes`, federation, coordination, monetization routers, `wrestling.py`);
  acquisition read caches (`exa/cache`, `retention`, `urls/adapter`, `paulgraham`);
  substrate CLIs (`cross_graph/__main__`, `ad_inventory/__main__`) and
  `substrate/attribution/compute.py`.
- **Ongoing audit:** `rg 'duckdb\\.connect' --glob '*.py'` excluding `tests/`,
  `runtime/db_lock.py`, `analytics.duckdb` rebuild, and `:memory:` fixtures.
  Write sites must be zero outside `db_lock` + tests.
- **PostHog bridge:** `substrate/observability/posthog.py` (Tier 2); weekly plane via
  `scripts/run_analytics_plane.sh` (+ optional `posthog_events.parquet` in export dir).

---

## 16. Operator checklist (weekly)

1. `scripts/export_analytics_parquet.py` → dated Parquet dir.
2. `scripts/rebuild_analytics_duckdb.py` → refresh `analytics.duckdb`.
3. Confirm nightly R2 backup landed (`antiek-backup` log).
4. `corpuscrawl doctor` + `status` before citing specs in research outputs.
5. Cohort / outcome SQL runs on **analytics** or **read_only** — never against writer.
6. ``./scripts/duckdb_plane_verify.sh`` — funnel + harness + plane unit gates.

---

## 17. North star (one sentence)

**Truth in append-only events; operational state in one NVMe DuckDB behind `connect_write(purpose=…)`; discovery in corpuscrawl FTS; learning in versioned Parquet and rebuild-only `analytics.duckdb`; product motion in PostHog with shared `event_id` — reads explicit, writes singular, every table with a named owner; Research, Read, Write, and Speak differ in API surface but share one graph writer and one schema discipline.**