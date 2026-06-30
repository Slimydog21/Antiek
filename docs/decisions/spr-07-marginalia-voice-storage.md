# SPR-07 — voice-anchored marginalia: the note/anchor/voice persistence is a SURFACE integration (ships dormant-correct)

**Date:** 2026-05-27
**Updated:** 2026-06-30
**Branch:** `caffen/physics-spr07` (worktree `antiek-physics-spr07`)
**Source spec:** `docs/philosophy/physics-of-reading.md` (the canon) + the SPR-07
sprint (`voice-anchored-marginalia`)
**Status:** **MARGINALIA WRITE + SHARED VOICE-BLOB STORAGE CLOSED.** SPR-07
capability remains complete + tested: quote-resolution (M1/M6), margin-note
anchored widget (M2), voice resolved-view (M3), plain-text materiality /
re-resolution (M4), and four-augmentation composition (M5). The surface write
path now persists `marginalia.noted` through the shared FloatMenu, and the
shared `useVoiceCapture` path stores the recorded audio blob through
`POST /voice/blob` before emitting `voice.captured` with the returned
`audio_ref`. The augmentation still reads resolved views only; it opens no
writer.
**Owner:** Read-surface instance (whoever wires the note-author write path) +
operator (sequencing the integration).

## What was decided

A margin note anchors to a passage by a short QUOTE (the Canon Cat insight),
carries the reader's typed comment and an OPTIONAL voice clip, and persists as
substrate events — never a private store (PR-2). Three persistence questions and
their settled answers:

1. **The note + its anchor.** Persist as a typed substrate event through the ONE
   shipped funnel (`postTypedEvent` → `POST /events/typed` → `runtime/db_lock`,
   the single-writer invariant — PR-6). The anchor is stored as the QUOTE TEXT
   (`anchorQuote`), **not a coordinate** — so copy/move re-resolve it by quote
   (M4). The augmentation reads the *resolved* note view; it opens no writer.

2. **The voice-clip transcript.** It is the DATA (PR-2 — text is the data) and
   lives in the note's substrate event. **Reuse Speak's existing path, do not
   fork it:** `transcribeAudio(blob)` (`apps/reading/src/api/books.ts` → `POST
   /voice/transcribe`) yields the transcript the reader CORRECTS (ASR mishears;
   `modes/Reading/VoiceNote.tsx` already surfaces the correction step), then
   `saveVoiceNote(documentId, { transcript, audio_ref })` (→ `POST
   /books/{id}/voice-note`) persists it through the funnel. No new transcription
   or note-distillation path is built.

3. **The audio blob.** Lives in local object storage through `POST /voice/blob`,
   returned as a content-addressed `voice-blob://sha256/...` `audio_ref`. The
   blob is NOT in the substrate (DuckDB); only the *reference* + the transcript
   are. `useVoiceCapture` uploads the blob after successful transcription and
   before `voice.captured` persistence, so a persisted voice capture always
   carries the blob pointer unless a caller supplied an existing `audio_ref`.

The augmentation (`augmentations/marginalia/`) therefore only ever READS the
resolved note + clip view (`ResolvedMarginNote` / `VoiceClipView`); it imports no
persistence client (verified — the CI guard is clean on the marginalia package,
and the PR-2 grep is clean).

## The gap, precisely

- **Resolution (read side) — works today.** Given the resolved note views, the
  resolver maps a quote → 0/1/many/withheld honestly (M1/M6), the widget anchors
  + renders, copy carries the quote, move re-resolves by quote (M4), and all four
  augmentations compose (M5). All proved headless in
  `augmentations/marginalia/{resolve-quote,marginalia.compose}.test.ts`.
- **Emit (write side) — closed for the shared FloatMenu/marginalia path.** The
  shared FloatMenu posts `marginalia.noted` through `postTypedEvent`, and its
  voice affordance uses `useVoiceCapture`: record → transcribe → `POST
  /voice/blob` → `voice.captured` with `audio_ref` → fold the user transcript
  into the marginalia note. The note event also carries `voice_transcript`,
  `voice_event_id`, and `audio_ref` by reference so the mounted gutter card can
  show the clip without reading a side store. If transcription or blob storage
  fails, no `voice.captured` event is persisted; the failure is surfaced.

## Why this is separate from the SPR-06 `source.read` + SPR-05 geometry gaps

- **SPR-05 geometry pass** (`spr-05-geometry-pass-gap.md`): a read-time
  `useLayoutEffect` geometry measurement. The margin-note widget rides that same
  pass for its pixel placement (the layout-map's `resolve`).
- **SPR-06 `source.read`** (`spr-06-source-read-event-gap.md`): a write-path emit
  on a *read* gesture.
- **SPR-07 marginalia emit** (this doc): a write-path emit on an *author* gesture
  (the reader commits a note + an optional clip), PLUS the object-storage blob
  write. A distinct integration point from both — recorded here so none is
  mistaken for another. (The voice path itself — transcribe + save — already
  exists in Speak; the shared marginalia author flow is now wired to blob
  storage + the typed event funnel.)

## The exact next step

1. **Exact servable synthesis passage mount:** bounded/restricted marginalia is
   now visible in `MasterMdViewer` (persisted `marginalia.noted` →
   `reResolveNote` → `makeMarginaliaAugmentation`). The remaining synthesis
   surface gap is the servable exact-passage case: it needs a rendered
   `data-passage-*` marker for the resolved `{kind:"passage"}` anchor, not a
   fabricated chunk fallback.
2. The augmentation already maps resolved notes → anchored widgets; no
   augmentation change needed.

## Reconsider if

- A future object store needs remote/S3 semantics → keep the `audio_ref` contract
  and swap the `/voice/blob` backend, not the event shape.
- A `marginalia.note` event shape turns out to overlap the existing voice-note
  event → reuse that event name instead of minting a new one (avoid a duplicate
  signal), and point the resolver at it.
- Live spoken-quote capture is built (the sprint's deferred follow-on) → the
  capture step gains a "speak the quote" path; the resolution + persistence
  decisions here are unchanged (a spoken quote is still a quote string).
- The full transcript-edit algebra (split-the-transcript-around-an-insertion) is
  ever wanted → that is the **Write surface's** transaction-filter facet, NOT the
  reading surface; filed for a future Write-side spec (out of scope here).
