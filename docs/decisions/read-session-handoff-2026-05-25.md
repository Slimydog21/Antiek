# Read workflow — session handoff + topology record (2026-05-25)

**Author:** Claude (Read execution session)
**Status:** Read workflow built + PR'd (#5), **NOT merged to `main`**.
Recorded for future agents while the operator waits on one more parallel
agent before analyzing PRs + pushing to `main`.

This file is the **non-redundant** session record: branch/PR topology, the
merge-order dependency, pre-existing hazards, the post-merge doc actions,
and one honest reconciliation flag. The *engineering* detail lives in the
sibling docs — read those for the "what/why" of the code:

- `read-spr-01-servable-corpus-gate.md` — the legal gate (the load-bearing,
  hard-to-vary decision: servability is a derived projection over the
  existing `documents.content_class` G1 gate, reused everywhere).
- `read-backend-sprints-and-drw-frontend-blocker.md` — SPR-05/06/08/09
  backend + the DRW blocker (now lifted — see that doc's Update section).
- `read-frontend-sprints-on-existing-surface.md` — SPR-02/03/04/07 + last-mile.
- `deep_research_workspace.md` — the parallel DRW stream's record (incl. SPR-10).

## What shipped this session (verified, with SHAs)

The whole Read workflow is **one clean commit** `748a5ec` (65 files,
+7637/−12): all 9 sprints + the browser last-mile + Storybook stories.
~110 Read tests green; `tsc -b` clean; `synthesis_rubric` latency lock held
(186.36 µs ≤ 194.85 µs baseline). The substrate edits it depends on
(`book_assets` DDL in `schema.py`, `Book*Payload` in `events.py`, route
registration in `app.py`) were folded into the upstream chain by the batch
tooling **before** `748a5ec`, so they are not in that commit — they live in
its ancestry (`read/base` and below).

## Branch + PR topology (read this before touching any branch)

`origin/main` is at `94aba7a` and is **57+ commits behind** — it does NOT
contain the DRW/Speak/Write/Read backend stack. That stack is unmerged.

| Branch (origin) | Tip | Role |
|---|---|---|
| `read/spotify-for-books` | `748a5ec` | **PR #5 head** — clean Read commit |
| `read/base` | `d007ff4` | **PR #5 base** — the upstream substrate (DRW SPR-09 tip) Read stacks on |
| `read/workflow-execution` | `c426b28` | **LIVE integration branch** — full stack incl. DRW SPR-10 (`2438f61`) + memento records, growing |
| `integration/backend-stack-2026-05-25` | `54c61df` | **STALE snapshot** (pre-SPR-10) — was a preservation ref; superseded by `read/workflow-execution` |

**PR #5** = `read/spotify-for-books` → `read/base`. Its diff is *exactly*
the 65 Read files (verified `d007ff4..748a5ec`) — a deliberately stacked
PR so review sees Read alone, not the substrate it sits on.

**Fairness / do-not-destroy:** the DRW SPR-10 UI commit `2438f61` is, as of
this writing, reachable on origin **only** through `read/workflow-execution`.
Do not force-push or delete that branch without first confirming `2438f61`
(and `ce7938e` speak, `54c61df` write) live elsewhere. An earlier tidy
deleted `read/workflow-execution`; a parallel agent re-created it with more
work on top — treat it as live, not disposable.

## Merge order (the dependency is real, per the spec)

Read is downstream of the DRW/Speak/Write substrate. Merge order to `main`:
the substrate (DRW + Speak + Write) **first**, then Read (PR #5). Read will
not build on `main` until that substrate lands. This matches the Read
README ("downstream of the Research/DRW foundations").

## Honest reconciliation flag (a real task, not a nit)

I built Read's reader as a **self-contained** mode — `modes/Reading/`
(`BookReader`, `paginate.ts`, `usePosition.ts`, `TocPanel`, `AdBorder`,
`HouseSlot`, `ResearchThis`, `VoiceNote`) — because at the time I executed,
DRW SPR-10's shared surface did not exist (I had only `WrestleApp` to point
at). DRW SPR-10 has since landed `modes/DeepResearchReading/` with
**overlapping** primitives: `anchor.ts` (content-anchoring, the edit-robust
analog of my `usePosition.ts`), `DocumentView.tsx` (raw_text + inline
note highlights), `NoteCard.tsx` / `useLiveNotes.ts` (the note rail).

So the reader is **currently forked** between Read and DRW — exactly the
outcome the spec warned against ("don't fork the reader DRW owns"). This
wasn't a wrong call (the surface didn't exist yet), but it is now a
**reconciliation task**: either Read's `BookReader` consumes DRW's
`anchor`/note primitives in place, or the shared bits get extracted to a
common component both reuse. A future agent should do this before both
readers drift further. The backend (the legal gate, escrow, gate-safe
seed) is unaffected — it is correctly shared/single-sourced.

## Pre-existing hazards (not mine — flagged to save the next agent hours)

- **`tests/test_cascade_api.py::test_session_stream_emits_events` HANGS.**
  It's an SSE/streaming test with no timeout; it blocked a full backend
  run for 21 minutes this session. `pytest-timeout` is NOT installed.
  Workaround for a clean tally: `--ignore=tests/test_cascade_api.py`.
  This is parallel-stream (cascade/DRW SPR-06) code; Read never touches it.
- **`apps/reading/src/components/ai/aiActionsEventBridge.test.ts` FLAKES**
  under parallel load (passes in isolation 7/7; in full `vitest run` it
  intermittently fails 2 tests, then passes 147/147 on a re-run). It's
  timing-sensitive (its own "macrotask yield"); it never imports
  `AISidecar`, so the Read rabbit-hole wiring can't affect it.
- **Two pre-existing collection errors**: `test_substrate_cli_unified.py` +
  `test_substrate_end_to_end.py` both import a missing
  `substrate.conversation.compaction` module. Ignore both for a clean run.
- **`test_notification_policy_ast.py::test_notification_policy_module_exists`
  FAILS** on `main` and everywhere — it asserts `substrate/notification_policy.py`
  exists, but that module was never written. The single standing failure
  in an otherwise-green full backend suite (3568 passed / 1 failed / 6
  skipped with `test_cascade_api` ignored). Not a Read regression.

## Post-merge doc actions (for the Memento run AFTER Read lands on `main`)

These were deliberately NOT applied to `main`'s companion docs now —
recording them pre-merge would be confident drift (the work isn't on
`main`). When PR #5 + its substrate base merge:

1. **`engineering_deferrals.md`** — add a Read-workflow entry with the four
   genuine deferrals, each with its unlock criterion (sourced from
   `read-frontend-sprints-on-existing-surface.md`): server-side Whisper
   transcription tier (Sprint-17 scaffold, operator-deferred), real-time
   talk-to-book (gated on speech round-trip < ~1.5 s), Exa web-discovery
   for curation, paid-ad CPM resolution (zero buyers in v1). Plus the
   reader-reconciliation task above.
2. **`operator_gate_actions.md`** — under G2 (lawyer review) + G3 (publisher
   opt-in): note that Read's escrow **accrual** path is live but
   **disbursement stays gated** — Read reinforces, does NOT close, G2/G3.
   `book_escrow.is_disbursement_unlocked` reads `ip_holders.status=='claimed'`,
   never bypassing the gate.
3. The three `read-*.md` decision docs (+ this one) arrive on `main` with
   the merge; no duplication needed.

## Verification snapshot (so the next agent doesn't re-run everything)

- Backend (full, `test_cascade_api` + the 2 broken collections ignored):
  **3568 passed, 1 failed (pre-existing `notification_policy`), 6 skipped.**
- Read backend subset: 73 tests green across
  `test_book_corpus_gate / test_book_curate / test_read_ad_escrow /
  test_reader_ad_slots / test_voice_notes / test_passage_research /
  test_tts_voice_reply / test_acquisition_books`.
- Frontend: Read suites 27 deterministic; full `vitest run` 147/147 (one
  flaky foreign file as noted); `tsc -b` clean.
- All Read/voice/speech routes construct on the FastAPI app.
