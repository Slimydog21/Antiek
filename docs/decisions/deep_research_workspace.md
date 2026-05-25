# Deep Research Workspace — execution record (2026-05-25)

**Branch:** `read/workflow-execution` (work began on `drw/deep-research-workspace`;
the parallel-stream tooling consolidated everything onto the shared branch —
all `feat(drw)` commits below are ancestors of HEAD).
**Source spec:** `specs/deep-research-workspace/` (10 sprints, 4 waves).
**Status:** **Code-complete.** All 10 sprints + the SPR-06/SPR-10 REST
transports + the real Exa→Browserbase browse loop shipped and tested. Full
suite green except the pre-existing `notification_policy` failure (parallel
stream, not DRW); latency lock within tolerance throughout. Activation of true
parallel throughput is operator-gated (§16); the live research loop needs
`EXA_API_KEY` + `BROWSERBASE_*`.

The thesis: a glass box, not a better black box — one problem cascades into many
*focused, steerable* deep researches, watched live, every output distilled into
living insight/question notes that compound into the next researches. Built
**into** the existing product (DuckDB substrate + React `apps/reading/`), not
greenfield.

## What was built (per sprint, with commit SHA)

| Sprint | Commit | Module(s) | Test |
|---|---|---|---|
| SPR-01 insight/question nodes | `70397e4` | `substrate/graph/migrate_v9_insight_question.py`, `insight_question.py`, `backfill_insight_question.py`; `schema.py` (V9 write_log + V1 CHECK); `constants.py` (relation vocab) | `test_graph_insight_question.py` (18) |
| SPR-02 ResearchRunner | `8d58da5` | `runtime/research_runner/` (protocol, host_local, promotion_funnel, budget, daytona_gated) | `test_research_runner.py` (15) |
| SPR-03 async note-taker | `61133f7` | `roles/note_taker/` (distill, document_pass, step_pass, living_note, scheduler) | `test_async_note_taker.py` (9) |
| SPR-04 max-context pack | `f82e717` | `substrate/context_pack/` (note_retrieval, note_budget, note_injection) | `test_max_context_pack.py` (7) |
| SPR-05 cascade planner | `00498a0` | `roles/cascade_planner/` (tree_contract, focus, planner, persist, approval) | `test_cascade_planner.py` (11) |
| SPR-06 orchestration | `e0370a8` | `orchestration/cascade_session.py` | `test_parallel_orchestration.py` (8) |
| SPR-07 gap detection | `8ff4320` | `substrate/gap_detection/` (candidates, unanswered, unsupported, contradiction, ranking) | `test_gap_detection.py` (8) |
| SPR-08 universal ingest | `c4e0fe4` | `substrate/research_bridge/` (extractors, detect_external, ingest_file, versioning) | `test_universal_ingest.py` (10) |
| SPR-06 transport | `dd8100f` | `interfaces/research/api/cascade_routes.py` (+ `cascade_session` is_complete/drain_nowait) | `test_cascade_api.py` (8) |
| SPR-09 monitor UI | `d007ff4` | `apps/reading/src/modes/DeepResearchWorkspace/` + `src/api/research.ts` | vitest (7) |
| SPR-10 transport | `1381577` | `substrate/graph/document_notes.py`, `interfaces/research/api/reading_routes.py` | `test_reading_api.py` (8) |
| SPR-10 reading UI | `2438f61` | `apps/reading/src/modes/DeepResearchReading/` (anchor, DocumentView, NoteCard, GapSidebar, useLiveNotes) + `src/api/reading.ts` | vitest (11) |
| Real browse loop | `841237f` | `runtime/research_runner/browse_loop.py` | `test_browse_loop.py` (6) |

## Binding invariants honored (and where enforced)

- **Single-writer is sacred.** Browse loops only append to their own
  per-investigation JSONL + emit StepEvents; **no loop opens a graph write
  connection**. All graph promotion funnels through one serialized
  `PromotionFunnel` → `runtime/db_lock` (`promotion_funnel.py`, `browse_loop.py`).
  20 near-simultaneous completions promote with zero lock timeouts (tested).
- **Glass box: no launch before approval.** `roles/cascade_planner/approval.py`
  `assert_launchable`; `cascade_routes` `/launch` returns 409 on an unapproved
  plan; editing an approved plan re-opens the gate.
- **Gaps are structural, not free-associated.** `gap_detection/candidates.py`
  `GapCandidate.__post_init__` RAISES on empty `backing_node_ids` — a
  graph-ungrounded gap is impossible to construct (the named failure mode,
  enforced in code, not prose).
- **Anchoring survives edits.** `DeepResearchReading/anchor.ts` anchors notes to
  source-chunk TEXT by whitespace-normalized match → original offsets, marking
  STALE when the text is gone — never silently mis-placed (the spec's mandatory
  gate, `anchor.test.ts`).
- **Latency lock.** `synthesis_rubric.scorer` p95 ≤ 194.85 µs held across every
  sprint (no DRW code touches the scorer).

## Cross-spec contracts (DRW as a dependency)

- **DRW SPR-07 → Speak.** Speak SPR-04's `GapSource` Protocol was a stub when it
  shipped; DRW SPR-07's detector now drops in via `substrate/speak/drw_gap_source.py`
  (`e865fad`, recorded in `speak_workflow.md`).
- **DRW SPR-10 → Read.** The Read workflow's four React sprints (SPR-02/03/04/07)
  were blocked on "DRW SPR-10 — the shared reading surface" (see
  `read-backend-sprints-and-drw-frontend-blocker.md`). DRW SPR-10 has now landed
  (`1381577` + `2438f61`), lifting the blocker — caveat: the primitives are
  DRW-named (`anchor.ts`, `DocumentView`); a small extraction to a shared library
  is the clean next step.

## §16 — the one decision that bounds the headline feature (operator-owned)

"Launch 20 at once" is reachable for *orchestration* (host-local asyncio
multiplexes 20 I/O-bound loops fine), but escalation-heavy work serializes
behind Browserbase's 3-concurrent-session cap regardless of runner — Daytona
would NOT relieve that, and CLAUDE.md §16 forbids it. `daytona_gated.py` is a
§16-gated stub: it conforms to the `ResearchRunner` protocol so the swap is a
provable drop-in, but every method raises a guard until the operator ratifies
§16 (it imports no Daytona SDK and is named `daytona_gated` so the tier-0
integration checker does not read it as importing the REJECTed SDK). **This is
the candidate D13 deferral surfaced for the operator** — not yet recorded in
`engineering_deferrals.md` (that doc had uncommitted parallel WIP at session
end; Memento declined to touch it). Unlock criterion: operator ratifies lifting
§16 for research fan-out → drop the Daytona impl behind the same protocol with
zero call-site changes.

## Deferred (NOT built — honest scope)

- **Real research execution needs live keys.** `_research_loop_factory`
  (`cascade_routes.py`) runs the real Exa→Browserbase browse loop when
  `EXA_API_KEY` is set, else the SPR-02 demo loop. End-to-end research requires
  `EXA_API_KEY` + (for escalation) `BROWSERBASE_API_KEY`/`BROWSERBASE_PROJECT_ID`.
  The loop *logic* is tested against injected stubs; the real providers rely on
  the Exa/Browserbase adapters' own tests (network-bound).
- **Live Playwright e2e** for the monitor + reading flows: needs a running
  server — TestClient/headless can't drive the continuous event loop the live
  stream depends on. Transport is covered by TestClient, UI logic by vitest.
- **Full conversational rabbit-hole chat** (SPR-10 M3): scoped to span-focused
  note + spin-research; a full span-chat reuses existing chat infra (deliberately
  not rebuilt).
- **SSE step-level durable replay after restart:** the per-step stream is
  in-memory; reconnect recovers *lifecycle* state from the event log
  (`reconstruct_session`). Persisting steps is a future enhancement.

## Integration choices worth recovering later

- **Browse loop providers are injected** (`SearchProvider`/`FetchProvider`/
  `Distiller`), so the loop logic is unit-tested with stubs and the real
  Exa→Browserbase wiring is a thin, swappable wrapper.
- **The SSE transport poll-drains** (`CascadeSession.is_complete` +
  `drain_nowait`) rather than consuming the single-consumer `stream()` — robust
  to a request/response server that only advances the loop while a request is in
  flight (never hangs on a queue sentinel).
- **The DRW node-type migration is a procedural staging rebuild** (DuckDB 1.5.2
  can't ALTER a CHECK nor drop an FK-target table): copy nodes → stage edges
  FK-free → drop+rename → recreate edges → restore. Verified against a copy of
  the 1138-node prod graph.

## Repo-hygiene note

Several shared files carry in-flight parallel-stream hunks alongside the DRW
edits (`app.py`, `App.tsx`, `events.py`/`schema.py`/`constants.py`) — each
`feat(drw)` commit body flags this; the hunks belong to the parallel
Read/Write/Speak workflows and were committed whole to keep the tree consistent.
