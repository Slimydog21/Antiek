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
