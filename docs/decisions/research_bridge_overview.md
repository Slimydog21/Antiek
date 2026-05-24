# Deep Research Bridge — overview + integration notes

Branch: `adrb/durable-2026-05-24`. Spec:
`~/specs/antiek-deep-research-bridge/index.html`.

## What it is

A new top-level Antiek surface that lets the operator paste
deep-research outputs from ChatGPT / Anthropic / Grok / AlphaSense
as discrete "blocks" (one paste = one `documents` row with
`document_type='external_deep_research'`), extract insights + open
questions from each, then operate on them in two modes:

- **Mode A — outline writing.** Reuses Antiek's existing
  `deliverables` / `deliverable_sections` / `section_blocks`
  pipeline. The SPR-04 patch promotes each extracted insight to a
  `nodes` row (`node_type='claim'`), so paste insights surface in
  `/blocks/search` and are draggable into existing deliverable
  sections with no further work.
- **Mode B — gap-finder + cascaded prompts.** Net-new. Clusters open
  questions across a scope of pastes, generates a provider-routed
  cascade of prompts the operator runs externally, and closes the
  loop via paste-back.

## Substrate (11 tables, all single-writer + audit-disciplined)

Paste-side (SPR-01/02): `research_pastes`, `research_paste_events`,
`research_paste_open_questions`, `research_paste_insights`,
`research_paste_extractions`.

Gap-side (SPR-05): `research_gap_runs`, `research_gap_clusters`,
`research_gap_cluster_questions`, `research_gap_prompts`,
`research_gap_prompt_answers`, `research_gap_prompt_signals`.

Single-writer invariant: every `INSERT INTO research_*` lives in
exactly one module function (`ingest.py`, `extractor.py`, `gap.py`),
enforced by `rg` grep tests. Audit tables are append-only (no
UPDATE/DELETE), enforced by source grep tests.

## Surfaces

- **HTTP API**: `interfaces/research/api/research_bridge.py`, mounted
  via a 5-line `register_research_bridge_routes(app)` call in
  `app.py`. Routes under `/research/pastes` + `/research/gaps`.
- **CLI**: `python -m tools.research_bridge_cli` — list/show/paste/
  detect/extract/find-gaps/gaps-show/gaps-list/signal/would-run/
  eval-precision/dogfood-report.
- **Frontend kit + surfaces**: `apps/reading/src/modes/research_bridge/`
  — kit (ResearchBlock, BlockShelf, DropTarget, PromptCard), pages
  (PastePage = front door, GapFinderPage = mode B), the
  ResearchBridgeHome shell (Paste | Gap-finder tabs), typed
  api_client, hooks. Composed on the Lemon kit; zero new deps.

## To integrate the frontend

One line in the app's route table — mount the home shell, which
wires its own HTTP client and routes between the Paste and
Gap-finder tabs:

```tsx
const ResearchBridgeHome = lazy(() => import("./modes/research_bridge/ResearchBridgeHome"));
// <Route path="/research-bridge" element={<ResearchBridgeHome />} />
```

The shell builds the real client (`createHttpClient()`) internally;
pass a `client` prop only in tests/stories. A paste saved on the
Paste tab is immediately in scope on the Gap-finder tab — both read
`/research/pastes`.

## Tests

- Backend: 131 tests in `tests/research_bridge/` (schema, source
  detection, ingest, extractor, eval, gap, node promotion, API, CLI,
  dogfood-report). Run: `./.venv/bin/python -m pytest tests/research_bridge/`.
- Frontend: 28 vitest tests in
  `apps/reading/src/modes/research_bridge/research_bridge.test.tsx`.
  Run: `npx vitest run src/modes/research_bridge/` from `apps/reading/`.

## LLM wiring

Extraction + clustering + cascade all route through the existing
dispatch router (`note_taker` role) via
`substrate/research_bridge/llm_dispatch.py`. The functions take an
injectable `LlmCallable` so tests run with a fake — no API credits
burned in CI.

## SPR-06 (operator dogfood) — not engineering work

The dogfood loop is operator-driven. Engineering shipped the
substrate, CLI, API, frontend, `dogfood-report` metrics tool, and
templates (`runs/adrb/`, `docs/decisions/adrb_post_dogfood_verdict_template.md`).
The operator runs 5 real research projects, then writes the verdict.

## Provenance note

This branch was authored against an active parallel-stream tooling
process that repeatedly reset the working tree and switched branches.
The work is committed here in three durable commits + this branch is
pushed to origin specifically so it survives that. Merge or rebase as
the operator sees fit.
