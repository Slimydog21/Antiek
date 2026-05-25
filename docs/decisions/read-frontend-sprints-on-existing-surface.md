# Read workflow — frontend sprints built on the existing reading surface

**Date:** 2026-05-25
**Branch:** `read/wave-1-legal-spine`
**Source spec:** `specs/read/` (SPR-02/03/04/05-UI/07)
**Status:** SPR-02/03/04/07 complete; SPR-05's UI (ad-border) landed inside
the SPR-03 reader. All four were thought DRW-blocked; they weren't.

## The blocker that wasn't

The earlier assessment (`read-backend-sprints-and-drw-frontend-blocker.md`)
held the four React sprints behind "DRW SPR-10 — the shared reading
surface — is unbuilt." Grounding in `apps/reading/` corrected that: **the
shared reading surface already exists** as `WrestleApp` + `PanelHost` +
`PdfViewer` + `NotesPanel`/`NotesFeed` + `AISidecar`/`ChatInput`, on a
mature Werner/Lemon design system with react-router mode registration.
DRW SPR-10 would *generalize* that surface; Read can *specialize* it
today. So these sprints were built against the real surface + the real
`/books` API (SPR-01), not a stub.

## What landed

| Sprint | What | Tests |
|---|---|---|
| **SPR-02** Library | New `Library` mode: shelf/grid over the servable corpus, servability-flagged `BookCard`, filters (Shelf/Preview/All), route `/library` + NavRail "Read" entry, typed `/books` client | `Library.test.tsx` (7) + stories |
| **SPR-03** Book reader | `Reading` mode: content-derived pagination (`paginate.ts`, the locator scheme), TOC nav, position persistence (`usePosition`, SPR-08 return-to-reading), gate-aware body (full / snippet / removed), route `/read/:documentId` | `Reading.test.tsx` (10) |
| **SPR-05** UI | `AdBorder` + `HouseSlot` rendered at page-window borders in the reader — never beside the reading column; zero-buyer house state is the default path | covered in reader + stories |
| **SPR-04** Prompt-to-curate | `curate_reading_list` (servable-only, embedding-ranked) + `/books/curate` + `CuratePrompt` wired into Library (re-ranks the shelf) | `test_book_curate.py` (3) + `Library.test.tsx` curate case |
| **SPR-07** Rabbit hole (text/audio) | `OpenAITTSProvider.synthesize` + `/speech/tts` + `useSpeech`/`SpokenReply`/`useReplyMode`, wired into the `AISidecar` reply (text OR auto-spoken per preference) | `test_tts_voice_reply.py` (4) + `SpokenReply.test.tsx` (5) |

138 frontend tests pass; `tsc -b` clean. The new backend tests pass; full
suite shows no new failures.

## The "hard to vary" calls

- **Pagination is content-derived, not scroll-derived** (`paginate.ts`):
  the page-window index is THE locator the whole workflow keys off — TOC
  jumps, ad-slot ids (`slot:doc:p<i>:pos`, SPR-05), spin-research seeds
  (SPR-08), voice notes (SPR-06). Tying it to a DOM offset would make
  every downstream anchor fragile. So it splits on the `## Page N` markers
  the backend already emits, and the same index survives re-layout, font
  changes, and viewport size.
- **Curation ranks only servable books** (`curate.py`): the servable
  allowlist is in the SQL WHERE, not a post-filter — you cannot curate a
  gated book into a reading list you can't read. Same gate as
  `serve.py`/`servability.py`, applied to ranking, so the two can't drift.
- **The reading column is sacred**: ad rails are top/bottom only
  (`AdBorder`), never beside the column; left/right are a wide-viewport
  layout concern, not a default that narrows prose.
- **Voice is layered on text, never a replacement** (`SpokenReply`): the
  reply text is always shown; `useReplyMode` only governs whether replies
  auto-speak. The text-note path stays fully intact (fairness rigor).
- **TTS is gated on the operator key, not autonomously burned**: the
  provider's real `/v1/audio/speech` call is now implemented but still
  raises without a key, the poster is injectable for tests, and the
  endpoint surfaces a clean 503 — so the capability exists without the
  agent spending credits.

## Last-mile (now built)

A follow-up pass closed the browser-side last-mile that earlier sat behind
the reader:

- **SPR-08 spin-research UI** — `POST /books/{id}/spin-research` builds the
  gate-safe seed server-side (gated full text never round-trips through
  the browser), requests a child investigation, links it both ways;
  `ResearchThis.tsx` in the reader hands off to it. Return-to-reading is
  free via `usePosition`. Tests: `test_passage_research.py` endpoint cases
  + `Reading.test.tsx` spin case.
- **SPR-05 impression loop** — `POST /books/{id}/ad-impressions` records
  impressions + accrues (reusing SPR-09), applying the attention rule
  SERVER-SIDE (the client's claimed attention is never trusted);
  `useReaderImpressions` flushes a page's slots on page-change with
  focused dwell (idle-paused). Tests: `test_read_ad_escrow.py` endpoint
  case + `Reading.test.tsx` hook case.
- **SPR-06 voice capture** — `POST /voice/transcribe` (Whisper, key-gated)
  + `POST /books/{id}/voice-note` (corrected-transcript guard + real
  note-taker dispatch distiller); `useVoiceRecorder` + `VoiceNote.tsx`
  drive record → transcribe → CORRECT → save, the correction step
  surfacing the honesty guard. Tests: `test_voice_notes.py` endpoint
  cases + `VoiceNote.test.tsx`.

## Honest deferrals

- **Talk-to-book real-time** stays gated on speech round-trip latency
  (~3–5s); only async voice *replies* ship (the operator's own bar).
- **SPR-04 web discovery (Exa)** — v1 curates over the corpus Antiek
  already has; pulling *new* candidate titles via Exa is an extension,
  and each discovered title would still land through the SPR-01 gate
  before it could be curated.
- **SPR-05 impression posting + SPR-06 voice capture UI**: the backend
  semantics + the reader locators exist; the browser code that emits
  impressions / captures audio mounts on this reader as the last wiring.
- **DRW SPR-10 generalization**: Read specializes `WrestleApp`'s surface
  rather than a formally-shared one. When DRW SPR-10 extracts the shared
  reader, the Read `Reading` mode should consume it instead of carrying
  its own layout — the note/highlight primitives are the seam to share.

## Files

- `apps/reading/src/api/books.ts` — typed `/books` + `/books/curate` client
- `apps/reading/src/modes/Library/` — `index.tsx`, `BookCard.tsx`, `CuratePrompt.tsx` (+ test, stories)
- `apps/reading/src/modes/Reading/` — `index.tsx`, `paginate.ts`, `usePosition.ts`, `TocPanel.tsx`, `AdBorder.tsx`, `HouseSlot.tsx` (+ test, stories)
- `apps/reading/src/hooks/` — `useSpeech.ts`, `useReplyMode.ts`
- `apps/reading/src/components/SpokenReply.tsx` (+ test, stories); `AISidecar.tsx` (rabbit-hole wiring)
- `apps/reading/src/App.tsx`, `components/navigation/NavRail.tsx` — route + nav registration
- `substrate/books/curate.py`; `interfaces/research/api/books.py` (curate endpoint, cover_uri); `interfaces/research/api/speech.py`; `substrate/dispatch/providers/openai_tts.py` (`synthesize`)
- tests: `test_book_curate.py`, `test_tts_voice_reply.py`
