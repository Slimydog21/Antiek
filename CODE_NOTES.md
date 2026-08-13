# CODE NOTES — antiek-oym-p0 worktree

Parallel P0 implementation (Own Your Mind brief: docs/own-your-mind/10-p0-implementation-brief.md).
This file is a working ledger, not documentation. Frontend and backend halves
each append their own section.

## FRONTEND — Own Your Mind P0 (apps/reading)

Implemented by the frontend engineer against the same worktree. All surfaces
are additive and read-only; zero mutation endpoints. No commits made.

### Implemented files

- `apps/reading/src/api/ownYourMind.ts` (new) — typed API client for the five
  P0 GETs, modeled on `apps/reading/src/api/research.ts` (apiFetch + ApiError
  + `get<T>` helper). Types mirror the backend payloads that landed in the
  same worktree:
  - `interfaces/research/api/explain_routes.py` (claim_node / supporting_edges
    / chunks / documents / chunk_tier_overrides; synthesis `pins` grouped by
    entity_kind with per-pin chains + honest `unresolved` pins; document
    citing_edges + citing_nodes),
  - `interfaces/research/api/ops_objective.py` (dispatch / gap_scoring /
    retrieval_gates / quality_gate / budgets / reuse_gate),
  - `interfaces/research/api/ops_signal_inventory.py` (signals /
    by_domain / schema_version / count).
  Exported: `explainClaim`, `explainSynthesis`, `explainDocument`,
  `getObjectiveCard`, `getSignalInventory`.
- `apps/reading/src/modes/Explain/index.tsx` (new) — the D1 "why this claim"
  panel at `/explain/:kind/:id` (kind ∈ claim | synthesis | document). Named
  + default export, header docstring, repo page conventions (max-w container,
  ice/charcoal tokens, font-serif headings). Renders:
  - claim: node card (label/type/scope) → supporting-edges rows (relation,
    tier chip, % confidence, source-doc link, chunk id) → chunk excerpts with
    `/read/:documentId` links → tier-override badges (set_by/reason/date);
  - synthesis: manifest pins grouped by entity kind, each resolved to its own
    chain; unresolved pins rendered as honest dashed "unresolved pin" rows;
    links to `/backtest/:synthesisId`;
  - document: reverse provenance — chunks of the document, then the citing
    edges joined to their source nodes, each claim linking into
    `/explain/claim/:id` (the recursive surface), plus tier overrides.
  Every item links to an existing surface; nothing links to a dead route.
- `apps/reading/src/modes/ObjectiveCard/index.tsx` (new) — the C1a
  read-only card at `/objective`. Renders GET /ops/objective-card: dispatch
  tier matrix (role→tier table; tier definitions with provider/model/fallback
  chain via LemonTable; tier defaults; pricing-placeholder honesty note),
  gap-scoring equation + constants + daemon spawn params, retrieval gates
  (deny-by-default policy, privileged/restricted/owner-only/excluded class
  lists), quality-gate thresholds, budget caps, reuse gate. Binding footer
  line verbatim: "Read-only rendering of the live objective; weights are
  operator-owned until P1 user settings ship."
- `apps/reading/src/modes/Signals/index.tsx` (new) — the L15 inventory at
  `/signals`. Filterable LemonTable (domain | ActionType | payload class |
  emitted-by note when present) with a plain client-side filter input + count
  chip. The emitted-by column is data-driven: it only renders when the
  backend payload carries emitter notes (the P0 schema introspection does
  not publish them yet — no fabricated "—" column).
- `apps/reading/src/App.tsx` — three routes wired in the operator/shared
  bucket next to `/coordination`: `/explain/:kind/:id`, `/objective`,
  `/signals` (all inside AuthenticatedRoutes).
- `apps/reading/src/shell/workflowTaxonomy.ts` — three `shared` MODE_TAXONOMY
  entries (Explain / ObjectiveCard / Signals) with `built: true`, routes, and
  sharedReason, so the More launcher, ⌘K, workflowForPath (shared → no rail
  highlight) and the taxonomy completeness test all stay honest. Explain is a
  param route whose index is not a bare route, so the launcher correctly
  treats it as a detail surface (reached from claims/documents, not More).
- `apps/reading/src/components/navigation/Topbar.tsx` — breadcrumb labels for
  the three new segments (explain/objective/signals), same pattern as the
  existing `known` map.
- `apps/reading/vite.config.ts` — dev-proxy entries for the four new backend
  prefixes (`/claims`, `/syntheses`, `/docs`, `/ops`), same explicit-prefix
  discipline as the existing entries. Without these the dev server cannot
  reach the P0 endpoints same-origin.

### Deviations / notes

- The brief's `WhyThis` reusable component (D1) is NOT extracted: the parent
  task scoped this batch to the routed `/explain/:kind/:id` mode. Extraction
  into a component reusable inside ResearchWorkstation / PersonalSpace /
  notebook is a follow-up once the panel is accepted.
- No eslint config exists in apps/reading (checked: no eslint.config.*,
  .eslintrc.*, or eslint devDependency), so the repo's own gates were used
  instead: `tsc -b --noEmit`, `npm run lint:tokens`, `npm run lint:type`,
  `npm run build`, and the full `vitest run` suite.
- The api client types were written against the actual backend payloads as
  they landed in this worktree (not the brief's prose alone); if backend
  shapes drift, `apps/reading/src/api/ownYourMind.ts` is the single typed
  seam to fix.
- No git mutations: no commits, no pushes, nothing outside the worktree was
  written. `dist/` from the verification build is gitignored.

### Verification (project's own env, apps/reading)

```
$ npm ci --no-audit --no-fund
added 690 packages in 13s

$ npx tsc -b --noEmit          # repo's canonical typecheck (strict)
EXIT: 0

$ npm run lint:tokens
token-lint OK — no new hardcoded hex (80 grandfathered; baseline has 120).

$ npm run lint:type
type-scale lint OK — no new chrome font-size above the 24px ceiling.

$ npm run build                # tsc -b && vite build
✓ built in 7.33s
EXIT: 0
(chunk-size warning pre-existing on the main index chunk; not introduced here)

$ npx vitest run
Test Files  236 passed (236)
     Tests  2006 passed (2006)
   Duration  59.79s
EXIT: 0
```

ACCEPT: tsc --noEmit passes; routes wired; api client typed; no commits; no
writes outside the worktree.


## BACKEND — Own Your Mind P0 (substrate + interfaces/research/api + tests)

Implemented by the backend engineer against the same worktree (branch
feat/own-your-mind-p0 @ 2f14a983b). All changes additive; zero mutation
endpoints; no commits/pushes; no writes outside the worktree.

### Implemented files

- `interfaces/research/api/explain_routes.py` (new) — read-only provenance
  surfaces, registered via `register_explain_routes(app)` in `app.py`:
  - `GET /claims/{claim_node_id}/explain` — claim node (node_id,
    canonical_label, node_type, graph_scope, created_at) + supporting edges
    (relation, chunk_id, document_id=edges.source_document_id, source_tier,
    extraction_confidence) + chunk excerpts (text[:500], section_path,
    document_id) + documents (title, author, source_tier, acquired_at) +
    chunk_tier_overrides (set_by, reason, set_at).
  - `GET /syntheses/{synthesis_id}/explain` — same chain via
    `synthesis_substrate_manifest` pins (document / chunk / node / edge);
    unresolved pins are surfaced honestly as `unresolved: true`, never
    dropped; zero-pin syntheses return an empty pins map.
  - `GET /docs/{document_id}/explain` — reverse provenance: document →
    chunks → citing edges (edges whose chunk_id belongs to the document) →
    citing source nodes + tier overrides.
  - Reads go through the sanctioned path: `runtime.db_lock.connect_read`
    over `substrate.graph.default_db_path()`, parameterized SELECTs (the
    same adapter pattern as `services/html_projection/adapters/synthesis.py`;
    no row-level read helper exists in `substrate/graph/` for these tables —
    its helpers are search/traverse/ops). A GET NEVER initializes the store:
    a missing DB file is an honest 404 (`ensure_initialized` needs a write
    connection, which a read surface must not open).
- `interfaces/research/api/ops_objective.py` (new) — `GET /ops/objective-card`
  (ops_router, prefix /ops). Renders the live decision surfaces from their
  owners, values read mechanically at request time:
  - dispatch: `substrate/dispatch/config.yaml` parsed as-is (version,
    role_tiers, tiers with pricing + nested fallback chains, tier_defaults,
    cost_tracking) + `pricing_placeholder` flag (all pricing 0.0 =
    operator-unverified placeholder, per the config's own header).
  - gap_scoring: MAX_CHASE_COUNT / RECENCY_HALF_LIFE_DAYS /
    CO_OCCURRENCE_CAP / INTERACTION_BOOST
    (`orchestration/continuous/scoring.py`) + daemon spawn params
    (DaemonConfig defaults: expected_cost_per_spawn_usd=0.5,
    max_spawns_per_iteration=3, min_score_to_spawn=0.05, spawn_policy_id,
    sleep_seconds).
  - retrieval_gates: PRIVILEGED_POLICY_TAGS + RESTRICTED /
    PERSONAL_ONLY / non-privileged-excluded classes
    (`substrate/graph/retrieval_gate.py`), deny-by-default.
  - quality_gate: voice threshold read from `check_voice_style`'s signature
    default (0.70), SourceTierBounds [1,3], verification rule,
    extraction-quality distinct-chars floor.
  - budgets: TOTAL_ACQUISITION_BUDGET_USD (research runner) +
    PER_INVESTIGATION_CAP_USD / DEFAULT_DAILY_CAP_USD / MAX_TOPIC_DEPTH
    (continuous daemon).
  - reuse_gate: REUSE_GROUNDEDNESS_THRESHOLD (env-overridable).
- `interfaces/research/api/ops_signal_inventory.py` (new) —
  `GET /ops/signal-inventory` (signal_inventory_router, prefix /ops).
  Enumerates the ActionType enum mechanically (135 members after the v35
  addition) + payload class per action type resolved from the TypedPayload
  discriminated union (each variant's `action_type` discriminator default),
  grouped by first dotted segment. Keys: generated_at, schema_version,
  count, signals, by_domain. No hand-maintained duplicate list.
- `substrate/schemas/events.py` — v35: new ActionType
  `SURFACE_SERVED_IMPRESSION = "surface.served_impression"` + payload class
  `SurfaceServedImpressionPayload` (surface, item_kind, item_id,
  ranked_position ge=0, ranked_version, timestamp, user_id), added to the
  TypedPayload union, TYPED_PAYLOAD_ACTION_TYPES, and __all__; bump-log
  comment v35 documents the change; EVENT_SCHEMA_VERSION 34 → 35.
  Audit-only by design: no consumer trains on it (no position-bias
  self-training, brief §5).
- `tools/codegen/emit_types.py` — new payload added to PAYLOAD_MODELS;
  regenerated `apps/reading/src/generated/types.ts` (contains
  SurfaceServedImpressionPayload, schema_version 35); check_staleness passes.
- `substrate/schemas/__init__.py` — re-export SurfaceServedImpressionPayload.
- `interfaces/research/api/app.py` — three register_* calls next to the
  existing registrations (~line 1742), following the established pattern.
- Tests (new): `tests/test_explain_routes.py` (12 tests, full chain + 404 +
  read-only-never-creates-store), `tests/test_ops_objective.py` (10 tests,
  every section compared against its live source module/config),
  `tests/test_signal_inventory.py` (9 tests, mechanical-introspection
  invariants + the v35 event round-trip through the emit → trajectory path).

### Deviations / notes

1. Pre-existing mapping-table drift fixed: `TYPED_PAYLOAD_ACTION_TYPES` was
   missing `book.servability_changed` + `book.taken_down` although both are
   members of the TypedPayload union (the set's own docstring says it lists
   "action types currently covered by the typed union"). The signal-inventory
   test caught the inconsistency; the two missing entries were added
   (additive; no payload shape change, so no version bump). Regenerated
   types.ts picked them up too.
2. Two existing tests pinned `EVENT_SCHEMA_VERSION == 34` and were
   mechanically updated to 35: `tests/test_worker_identity_event.py:64` and
   `tests/substrate/dispatch/test_nd_attribution.py:57` (the bump is
   mandated by the brief; the pins document the version sequence).
3. No row-level read helper exists in `substrate/graph/` for nodes/edges/
   chunks/documents/manifest/overrides, so the explain resolver uses
   parameterized SELECTs over the sanctioned `connect_read` connection —
   the same pattern the synthesis-artifact adapter uses. Noted as the
   sanctioned-read-path adaptation the brief allows.
4. The FastAPI version in this tree (0.138.2) wraps included routers as a
   lazy `_IncludedRouter`, so `app.routes[*].path` is None for router
   routes — harmless for routing; noted only so nobody "fixes" it.
5. Honesty note: during manual endpoint verification an un-isolated
   subprocess briefly opened the REAL ~/.antiek store through
   `ensure_initialized` (my first draft called it on read). The store was
   verified intact afterwards (53 tables, documents=24, nodes=1156,
   chunks=2295, syntheses=2, opens clean read-only, no WAL file). The
   endpoint was then changed to never initialize the store on a GET, and a
   regression test asserts a missing store 404s without creating a file.
6. `uv sync --frozen --extra dev --extra pdf` was required for the test env:
   `uv sync` alone installs neither pytest/ruff (dev extra) nor pypdf
   (pdf extra), and importing the app at module scope pulls
   `acquisition.books.reader` which hard-requires pypdf. CI installs the
   same extras (`.[dev,arxiv,pdf,...]`).

### Verification (project's own env, worktree root)

Env: `uv sync --frozen --extra dev --extra pdf` (uv 0.11.14, CPython 3.13.13,
duckdb 1.5.4, fastapi 0.138.2).

```
$ uv run pytest tests/test_explain_routes.py tests/test_ops_objective.py tests/test_signal_inventory.py -x -q
25 passed, 1 warning in 12.57s        (1 warning = pre-existing StarletteDeprecationWarning from fastapi.testclient)

$ uv run ruff check <all new + touched files>
All checks passed!

$ uv run python tools/codegen/emit_types.py
wrote /Users/slimydog/Antiek/antiek-oym-p0/apps/reading/src/generated/types.ts

$ uv run python tools/codegen/check_staleness.py
OK [events]: apps/reading/src/generated/types.ts in sync with substrate/schemas/events.py.
OK [contracts]: apps/reading/src/generated/contracts.ts in sync with substrate/contracts/.

$ uv run pytest tests/test_codegen.py tests/test_events_schema.py tests/test_worker_identity_event.py tests/substrate/dispatch/test_nd_attribution.py tests/test_api.py -q
137 passed, 1 warning in 14.25s   (adjacent schema/codegen/API suite, all green)
```

ACCEPT: all new pytest files pass; ruff clean on new files; CODE_NOTES.md
exists with verification evidence; no commits/pushes; no writes outside the
worktree.

### Test-suite flakiness note (machine-load timeouts — NOT a regression)

Two pre-existing suites fail intermittently with `Test timed out in 5000ms`
when the machine is under load (parallel agents building/testing on this
Mac-mini). Both were green in this worktree's full run at 23:11 (236 files /
2006 tests) WITH all P0 frontend code in place, and both fail identically on
a pristine origin/main checkout at /tmp/pristine-reading:

- `src/design/token-parity.test.ts` — the test execs
  `npx tsx scripts/check_token_parity.ts` and asserts exit 0. The guard
  reads EXACTLY two files (`src/design/tokens.css`, `tailwind.config.js`),
  both byte-identical to origin/main in this worktree (git diff --quiet
  confirms no changes); the guard exits 0 here AND on the pristine tree.
  Its cold start currently takes ~6.5-6.9s wall on BOTH trees — over the
  test's fixed 5s budget. No token in any new component can affect it; the
  new files also pass `npm run lint:tokens` (exit 0, no new hardcoded hex).
- `src/modes/Reading/Reading.test.tsx` — 1-3 tests time out under load on
  the pristine baseline too (parent-verified, same tests). The worktree's
  new files are not in this suite's import graph.

Not modified: test timeouts are a repo-owner decision, out of P0 scope.

## EMISSION (parent, post-child) — surface.served_impression wiring (brief §5)

The P0 children defined the event type but did not emit it anywhere. Parent
wired the audit-only emission (commit f93dca831):

- apps/reading/src/lib/servedImpression.ts — useServedImpression hook +
  emitServedImpression: once per mount (StrictMode-safe ref), fire-and-forget
  (.catch(() => {}) — audit never breaks the UI), investigation_id "system"
  (reserved non-research namespace), ranked_position 0 / ranked_version ""
  until a ranked stream exists (L8: audit, never train).
- Wired into the three P0 surfaces: Explain (itemKind = kind param,
  itemId = id param), ObjectiveCard ("/objective"), Signals ("/signals").
- apps/reading/src/lib/servedImpression.test.ts — 3 focused tests: single
  emission under double effects, envelope shape (system id + typed payload),
  failure swallowed. All 3 pass; tsc clean; token-parity 6/6; reachability
  clean (routes unchanged).
- Note: reading-stream emission deliberately deferred until a ranked stream
  exists (none today — see docs/own-your-mind/09-objective-card.md).


## P1 §5 — visible tiers, WRITE half (antiek-oym-tiers worktree)

Implemented against a fresh checkout of origin/main @ ea012164c on branch
feat/own-your-mind-p1-tiers. The read half (tier chips + override badges in
the Explain panel) already shipped in P0 (PR #3064, merged on main); this is
the user-settable write half on the EXISTING `chunk_tier_overrides` table
(zero new tables). No commits, no pushes; writes confined to this worktree.

### Backend

- `interfaces/research/api/settings_tiers.py` (new) — two routes:
  - `GET /settings/tier-overrides?chunk_id=...` → `{chunk_id,
    current_original_tier, overrides[]}` (newest first). The chunk's current
    tier is its source document's `source_tier` (the `chunks` table has NO
    tier column — the tier lives on `documents`, which is exactly what the
    Explain panel's tier chips render); resolved via `connect_read`
    (explain_routes' read discipline: missing store = honest 404, never a
    creation event).
  - `POST /settings/tier-overrides` → `{chunk_id, override_tier, reason}`.
    Body is parsed BY HAND (settings_models_admin precedent) so every 4xx is
    a value-free 400 with an honest message — pydantic's 422 would echo
    submitted values. Validations: chunk exists (404), override_tier strict
    int 1..5 (400; bool/float/string refused — no pydantic coercion),
    reason non-empty after strip (400: "the audit trail requires a reason"),
    reason ≤ 2048 chars (400). The chunk's current tier is read on the SAME
    locked `connect_write` connection that appends the row (no TOCTOU
    between tier read and record), then
    `middleware/source_tier/overrides_db.record_chunk_tier_override` runs
    with `set_by=request_owner_user_id(request)` (the
    settings_models_admin.py:209 operator-id pattern) and an explicit
    `set_at` so the created row is read back deterministically. Lock
    contention → 503 (account_memory_routes' `_unavailable` pattern): the
    flock wait is bounded at `_LOCK_TIMEOUT_S = 15.0` (ingest cron can hold
    it for minutes; 15s = settings must answer promptly without 503ing
    through a normal ingest). Missing store on POST → 404 (a chunk cannot
    exist without a store; never implicitly create one).
  - Registered in `interfaces/research/api/app.py` via
    `register_settings_tiers_routes(app)` right after
    `register_settings_budget_routes` (mirrors P1 §2 privacy placement).
- `tests/test_settings_tiers.py` (new) — 15 tests: POST round-trip via GET
  (set_by == request owner id, original_tier == the chunk's current tier),
  authenticated owner stamping (monkeypatched `operator_claims` →
  `user-42`), invalid tier 400 (0/6/-1/1.5/"3" — all refused, no pydantic
  coercion), empty/whitespace reason 400, overlong reason 400, unknown chunk
  404 (both verbs), missing-store 404 never creates (both verbs), append-only
  (two overrides both present, newest first, each with its own
  reason/owner/original_tier snapshot), lock-timeout → 503 via REAL flock
  contention on the sidecar file (monkeypatched `_LOCK_TIMEOUT_S` = 0.2s;
  nothing recorded while blocked), and GET never needs the write lock (200
  while another fd holds the flock).
- Optional-deps note: the worktree needed `uv sync --extra dev --extra pdf`
  (pytest + pypdf for `acquisition.books.reader`), same pattern as P1 §2.

### Frontend (apps/reading)

- `apps/reading/src/api/tiers.ts` (new) — typed client for the two routes
  (`getTierOverrides`, `createTierOverride`); reuses `TierOverride` from
  `ownYourMind.ts` (the single typed seam the Explain panel already reads).
- `apps/reading/src/modes/Explain/index.tsx` — per-chunk `SetTierControl`:
  a "set tier" button on every chunk row (each row has tier chips) reveals a
  form (tier select 1..5 + mandatory reason input), POSTs on save, refreshes
  the chunk's override history from GET, then calls the existing `reload`
  path so the new override badge appears in the chain. The chunk's override
  history (set_by / reason / date, newest first) is listed inside the
  control via `OverrideBadge`. The `onTierChanged` callback threads from
  `Explain` → Claim/Synthesis/Document panels → `ChunksSection` →
  `ChunkBlock`, so all three explain surfaces (claim, synthesis pins,
  document) get the write control. Errors surface inline; the save button
  is disabled while busy or with an empty reason.
- `apps/reading/src/modes/Explain/Explain.test.tsx` (new) — 3 tests
  (PrivacyDashboard-style vi.mock of `../../lib/api` + api modules, wrapped
  in MemoryRouter): control renders + lists per-chunk override history from
  GET; submit POSTs `createTierOverride("chunk-1", 5, reason)` and reloads
  the explain chain (asserted: second `explainClaim` call + the new
  "tier 2 → 5" badge + reason rendered); POST failure surfaces inline with
  no reload.

### Verification (project's own env; tails)

- `uv sync --extra dev --extra pdf` (pytest + pypdf needed by the suite).
- `uv run python -m pytest tests/test_settings_tiers.py -q` →
  `15 passed` (suite uses `python -m pytest`; a bare `uv run pytest`
  resolves the system pytest outside the venv).
- `uv run python -m pytest tests/test_explain_routes.py tests/test_settings_budget_api.py -q` (regression) → `64 passed`.
- `uv run ruff check interfaces/research/api/settings_tiers.py tests/test_settings_tiers.py interfaces/research/api/app.py` → `All checks passed!`.
- `cd apps/reading && npm ci && npx tsc --noEmit` → clean (only NO_COLOR/oxc warnings).
- `cd apps/reading && npx vitest run src/modes/Explain/Explain.test.tsx` → `3 passed`.
- OpenAPI generation (`app.openapi()`) errors on a PRE-EXISTING pydantic
  forward-ref (`PublisherClaimRequest` at app.py:4568, present identically
  on HEAD — unrelated to this change; `git diff --stat` shows the app.py
  delta is exactly 5 registration lines). The app itself builds and serves
  both new routes through TestClient.

### Deviations

- POST body is parsed by hand instead of a pydantic model so invalid tiers
  and empty reasons are honest value-free 400s (task asked for 400; pydantic
  coerces `"3"` → 3 and echoes submitted values in 422s). Response models
  remain pydantic.
- `current_original_tier` on GET is the chunk's DOCUMENT tier, not a
  `chunks` column — the chunks table has no tier column; document
  `source_tier` is the sanctioned tier the Explain chips already render.
- The chunk lookup for POST happens inside the write lock (same connection
  as the append) rather than on a separate read connection first — removes
  the read/write race window while still using the sanctioned
  parameterized-SELECT pattern over `runtime.db_lock` connections.
