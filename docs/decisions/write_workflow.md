# Write workflow — execution record (2026-05-25)

**Status:** Built + tested, committed + pushed on branch
`read/workflow-execution` (the operator's parallel-stream integration
branch; commits also reachable from `drw/deep-research-workspace` +
`unified/*`). ≈92 backend+REST tests green; 44 frontend vitest across 7
suites; the SPR-04 `write-editor` Playwright e2e passes 2/2 in chromium;
0 tsc errors; codegen staleness in sync; synthesis_rubric latency lock
held (p95 ≤ 194.85 µs). Live draft generation is activation-gated on an
operator-supplied provider credential — see D13 in
`engineering_deferrals.md` — and is the only non-code gap.

Spec: `specs/write/` (master `index.html` + 9 sprint pages). Write is the
third Antiek workflow (Research · Read · Write · Speak): author research
and books from lego blocks — insight/question notes traced to a source of
truth — composed into an outline, drafted in one move, then *truly
written* in the edit, where the style signal and the gated RL signal both
come from. Write closes the flywheel — its `platform_authored` output is
the servable content the Read workflow serves.

## What was built

Two genuinely net-new substrates (per the spec): the graph-node-referencing
`OutlineBlock` model and edit/trajectory capture. The rest is organize-and-wire
over CreationStudio / BrainstormStation / Interview / `creative_writer` /
`voice_style` / `loop_3` and the shared BookReader.

| Sprint | Module(s) | Tests |
|---|---|---|
| SPR-01 OutlineBlock | `substrate/write/{outline_block,outline,provenance,clustering,migrate_outline_block}.py` + `outline_blocks` table (graph/schema.py V8) + 3 typed events (`outline_block.placed/moved/removed`, v13) | `test_outline_block.py` (20) |
| SPR-02 edit capture | `substrate/edit/{edit_pair,authoring_trajectory,harvest_authoring}.py` + `edit.captured` event (v15) | `test_edit_capture.py` (12) |
| SPR-03 repository/folders | `substrate/write/{folders,block_search}.py`; `Write/Repository/` (dragToOutline + useOutlineDrop + Repository.tsx) + `writeApi.ts`; `/write/repository` route | `test_block_repository.py` (11) + `dragToOutline.test.ts` (4) |
| SPR-04 block editor | `Write/Editor/` (TipTap: locator, editCapture, Citation, BlockNode, tiptapAdapter, Editor) + CreationStudio textarea→WriteEditor swap | `locator.test.ts` + `editCapture.test.ts` (16) + `write-editor.spec.ts` e2e (2) |
| SPR-05 brainstorm→blocks | `roles/interviewer/drivers.py` + `substrate/write/brainstorm_blocks.py`; `Write/Brainstorm/` (clarifyLoop + IdeaDump) | `test_brainstorm_interview.py` (7) + `clarifyLoop.test.ts` (4) |
| SPR-06 draft generation | `substrate/write/draft_generation.py` (wires `creative_writer`); `creative_writer: synthesis` in dispatch config | `test_draft_generation.py` (10) |
| SPR-07 trace-to-source | `substrate/write/trace.py` (gated-source-no-leak); `Write/Trace/` (traceController + useTrace + TraceListener) + chunk-span anchor (`Reading/anchorToChunk.ts`) | `test_trace_to_source.py` (6) + `traceController.test.ts` (7) + `anchorToChunk.test.ts` (7) |
| SPR-08 context window | `substrate/write/promote_context.py`; `Write/ContextWindow/` (contextModel + ContextWindow.tsx) + `/write/context` route | `test_promote_context.py` (2) + `contextModel.test.ts` (7) |
| SPR-09 style conditioning | `substrate/write/style_profile.py` | `test_style_conditioning.py` (11) |
| REST surface | `interfaces/research/api/write_routes.py` (`/write/*` APIRouter, mirrors `speak_routes.py`; one-line `include_router`) | `test_write_routes.py` (13) |

## Binding invariants honored (and where enforced)

- **Provenance is the moat — no orphan prose.** Enforced at THREE layers:
  Python (`outline_block._validate_composition`), Pydantic (the
  `OutlineBlockPlacedPayload` Literal), and the DB CHECK on `outline_blocks`
  (`graph_node ⟺ node_id present`; user-originated ⟹ node_id absent — no
  fabricated citation). Surfaces as a 400 over HTTP. `node_id` is a SOFT
  reference (no FK) so a deleted source is *detectable* (dangling) and a
  not-yet-promoted note id resolves later.
- **Capture ≠ training.** Edit/authoring capture is ungated and writes
  `reward=None`; the training-bound harvest is hard-gated by
  `loop_3.unlock_gate` (G8). An AST-level test asserts the capture +
  style-conditioning modules import NO trainer (`sft_runner`/`rubric_verifier`).
- **The gate wins.** Generated prose below the `voice_style` gate (≈0.70)
  returns `gate_failed` even with perfect citations; a style prompt can
  never push output below it.
- **Gated-source-no-leak.** `trace.resolve_trace_target` combines
  provenance with Read's `books/servability`: a gated/taken-down/unknown
  source resolves to `servable_snippet` (`full_text_allowed=False`) — Write
  is never a side door around Read's gate. Verified in unit tests AND over
  HTTP (`/write/blocks/{id}/trace`).
- **Single-writer.** Every graph write goes through
  `db_lock.connect_write` (LockedConnection required, TypeError otherwise);
  new events through codegen (`EVENT_SCHEMA_VERSION` 13→15, TS regenerated).
- **Latency lock + codegen.** `synthesis_rubric` p95 ≤ 194.85 µs unmoved;
  `check_staleness.py` in sync.

## Key decisions (auditable)

- **TipTap is the Write editor** (SPR-04 M1, a long-lived commitment). It
  is already the house dependency (the Notebook mode is built on it), so
  the choice adds no new surface and inherits the Notebook's custom-node +
  attr-round-trip conventions. Reversal condition: a need for true
  nested-tree block editing that ProseMirror's flat-block model fights
  (then reconsider Lexical). Commits `a2850f7`, `0813348`.
- **`OutlineBlock` is a composition layer over graph nodes, not a parallel
  store.** New `outline_blocks` table supersedes `section_blocks` (migrated
  idempotently); blocks reference insight/question/claim nodes. Commit
  `a2850f7`.
- **REST as a standalone router**, not inlined into the 5k-line `app.py`
  factory — mirrors `speak_routes.py`, included with one line, so the hot
  shared file stays mergeable. Commit `a2850f7`.
- **Trace lands on the exact span via a `?chunk=` URL param** (Read-side
  BookReader enhancement, operator-authorized) rather than a Write-owned
  viewer; the reader still enforces its own servability. Commit `e667dc8`.
- **Live generation is credential-graceful**: `creative_writer` wired to
  the synthesis tier; absent a key the endpoint 503s cleanly (never
  fabricates). The credential is operator-supplied (D13). Commit `e667dc8`.

## Deferred within Write

- **D13 (engineering_deferrals.md)** — live draft generation on an operator
  provider credential. The substantive deferral.
- **Typed folder events + folder DDL into `graph/schema.py` V9** —
  `folders.py` uses a self-contained `ensure_folders_schema` and a
  defensive typed-event import (auto-activates once registered); the formal
  fold-in was deferred to avoid destabilizing the freshly-green shared
  codegen during the parallel-stream session. Minor; not assigned a
  D-number pending operator confirmation it's worth tracking.
- **NavRail nav links for `/write/context` + `/write/repository`, and an
  optional combined Write workspace** (Repository + editor + context window
  on one screen) — UI polish whose only real verification is a browser;
  the combined workspace overlaps the existing CreationStudio. Not a
  spec gap.

## Honesty note on Loop-3 (declined edit)

Write's authoring-trajectory capture (`substrate/edit/`) is a NEW, distinct,
gated trajectory source (deliverable-scoped, `reward=None`). It is **not**
the denominator of `loop_3_unlock_criteria.md` criterion #1 (which counts
≥10,000 *sealed research investigations* in the research-events parquet).
That doc was therefore left untouched — recording Write capture as a
contribution to criterion #1 would be confident drift. Whether authoring
trajectories become a recognized criterion-#1 (or separate) training source
is an operator call.

## Commit trail

`a2850f7` (substrate + editor + REST) · `46e07cf` (idea-dump + context
window UIs) · `54c61df` (SPR-04 e2e) · `0813348` (CreationStudio textarea
swap) · `e667dc8` (chunk-span anchor + credential-graceful gen) · `e639d73`
(Repository route). The four-gap follow-up (trace wiring, routing, dispatch
config, browser runs) was swept into the parallel-stream batch integration
commit; events.py/schema.py edits rode the same batch tooling.
