# Read workflow — backend sprints landed + the DRW frontend blocker

**Date:** 2026-05-25
**Branch:** `read/wave-1-legal-spine`
**Source spec:** `specs/read/` (9 sprints, 4 waves)
**Status:** SPR-01 complete; SPR-05/06/08/09 **backend** complete; the four
React-frontend sprints (SPR-02/03/04/07) are blocked on the unbuilt DRW
shared reading surface.

## What's built (this session)

| Sprint | What landed | Tests |
|---|---|---|
| **SPR-01** | Book asset model + servable-corpus legal gate (full) | `test_book_corpus_gate.py` (31) + reader TOC (2) |
| **SPR-05** | Ad-border **backend**: slot model, impression/attention semantics, targeting allowlist | `test_reader_ad_slots.py` (12) |
| **SPR-09** | Ad-revenue → rights-holder escrow accrual (full backend) | `test_read_ad_escrow.py` (6) |
| **SPR-06** | Voice notes **backend**: transcribe + corrected-transcript-gated distill + provenance | `test_voice_notes.py` (6) |
| **SPR-08** | Spin-research **backend**: gated-seed-no-leak guard + two-way passage↔research link | `test_passage_research.py` (8) |

All reuse existing substrate rather than reinventing it: SPR-05/09 ride
`substrate/ad_inventory/payout.py` + `ip_holders` escrow; SPR-06 rides
`acquisition/voice` (Whisper) + `roles/note_taker`; SPR-08 rides
`substrate/books/serve.py` (the SPR-01 gate) + the existing
`question.escalated_to_research` event.

## The DRW frontend blocker (intellectual honesty)

Read's README states it plainly: Read is **downstream of the Research
(DRW) spec**, depending on **DRW SPR-10 — the shared reading surface** —
which is *not built*. Four Read sprints are primarily that React surface
specialized for books, so their UI cannot be honestly built against a
contract that doesn't exist yet:

| Sprint | Frontend deliverable | Blocked on |
|---|---|---|
| SPR-02 | Library/browse mode (`apps/reading/src/modes/Library/`) | DRW SPR-10 surface + AppShell/NavRail mode registration |
| SPR-03 | Book reader (pagination, TOC, inline notes) | DRW SPR-10 (it *specializes* the shared reader) |
| SPR-04 | Prompt-to-curate browsing | SPR-02 + DRW SPR-10 |
| SPR-07 | Conversational rabbit hole (text/audio) | DRW SPR-10 rabbit-hole UI + SPR-03 |

Building these now would mean fabricating a React surface against a
non-existent contract — the opposite of the technical taste this execution
is held to. The **backend halves** of the ad/voice/research sprints were
built precisely because they *don't* need the surface; their UI
counterparts wait behind DRW SPR-10.

### What the surface-blocked work needs (contracts to define when DRW SPR-10 lands)

- **SPR-02/03**: the servable-corpus query API (`interfaces/research/api/books.py`,
  built in SPR-01) is the data contract — `GET /books`, `GET /books/{id}`,
  `GET /books/{id}/full-text`. The reader consumes these; the full-text
  endpoint already enforces the gate. The React reader needs DRW SPR-10's
  highlight/note/position primitives (`usePosition.ts`, the note rail).
- **SPR-05 UI**: `AdBorder.tsx` / `HouseSlot.tsx` consume
  `substrate/ad_inventory/reader_slots.py` (`slots_for_page_window`,
  `fill_slot`) and post impressions to a `record_impression`-backed
  endpoint. The slot/fill/impression semantics are fixed; only rendering
  remains.
- **SPR-06 UI**: `VoiceNote.tsx` reuses `InterviewVoiceCapture` + WebRTC,
  POSTs audio → `transcribe_voice_note`, shows the transcript for
  correction, then calls `distill_voice_note(confirmed=True, ...)`. The
  corrected-transcript guard is already enforced server-side.
- **SPR-08 UI**: `ResearchThis.tsx` calls `build_research_seed` (gate-safe)
  then DRW SPR-05's cascade planner + SPR-06 monitor; `link_passage_to_research`
  records provenance. The gated-seed-no-leak guard is already enforced
  server-side, so the UI cannot leak even if it tries.

## Why the backend-first split is the right call

The two strategically-consequential, "hard to vary" layers of Read are the
**legal gate** (SPR-01) and the **ad-economics engine** (SPR-05/09) — and
both are now real, tested code, not UI mockups. The legal-gate-critical
seam in SPR-08 (a research must never be seeded with gated full text) is
also enforced server-side, so it holds regardless of when the UI lands.
The reader experience (SPR-02/03/04/07) is valuable but is presentation
over these foundations, and it correctly waits for the shared surface so
Read doesn't fork the reader DRW owns.

## Files (SPR-05/06/08/09)

- `substrate/ad_inventory/reader_slots.py` — border slots over book locators + house fill
- `substrate/ad_inventory/reader_impressions.py` — impression/attention semantics (dedup, idle-exclusion)
- `substrate/ad_inventory/targeting.py` — targeting allowlist; never gated text
- `substrate/marketplace_metrics/book_escrow.py` — reading-session → escrow accrual; disbursement-gate read
- `substrate/books/voice_note.py` — transcribe + corrected-transcript-gated distill + provenance
- `substrate/books/passage_research.py` — gate-safe research seed + two-way passage↔research link
- `substrate/constants.py` §J — ad/escrow constants (dwell, slot positions, targeting allowlist, unattributed bucket)
- tests: `test_reader_ad_slots.py`, `test_read_ad_escrow.py`, `test_voice_notes.py`, `test_passage_research.py`

## Deferred last-miles (honest)

- SPR-05 ad-impression *persistence* to a table (events/records defined; the
  reader posts them when the surface lands).
- SPR-06 voice-note provenance *table* (the `VoiceNoteResult` data model is
  defined; persistence wires up with the capture UI).
- All four React surfaces + their Storybook/Playwright tests (DRW SPR-10).
