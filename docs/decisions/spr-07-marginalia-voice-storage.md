# SPR-07 — voice-anchored marginalia: the note/anchor/voice persistence is a SURFACE integration (ships dormant-correct)

**Date:** 2026-05-27
**Branch:** `caffen/physics-spr07` (worktree `antiek-physics-spr07`)
**Source spec:** `docs/philosophy/physics-of-reading.md` (the canon) + the SPR-07
sprint (`voice-anchored-marginalia`)
**Status:** SPR-07 capability complete + tested. The quote-resolution (M1/M6),
the margin-note anchored widget (M2), the voice resolved-view (M3), the
plain-text materiality / re-resolution (M4), and the four-augmentation
composition (M5) are all built + green against the resolved views. The actual
**emit** of the note/anchor/voice substrate event + the **audio-blob object
storage** are a SURFACE/BACKEND integration the augmentation cannot perform
(PR-2 / PR-6) — they ship dormant-correct, exactly like the SPR-06
`source.read` emit and the SPR-05 geometry pass.
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

3. **The audio blob.** Lives in **object storage keyed by the note's substrate
   event id** — referenced by the event's `audio_ref` field (the same field
   `saveVoiceNote` already accepts). The blob is NOT in the substrate (DuckDB);
   only the *reference* + the transcript are. This is the canon's "the audio blob
   lives in object storage keyed by the event" verbatim, and it reuses the field
   Speak's voice path already carries.

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
- **Emit (write side) — deferred SURFACE integration.** Capturing the typed note,
  posting the `marginalia.note` event through the funnel, and storing the audio
  blob (keyed by the event id) is a surface/backend wiring the augmentation may
  not do (PR-2 / PR-6). Until the surface wires it, there are no persisted notes
  to resolve — the augmentation is **dormant-correct**: it renders the moment the
  resolved-note view carries an entry.

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
  exists in Speak; what's deferred is wiring the marginalia author flow to it.)

## The exact next step

1. **Capture:** in the reading surface, when the reader anchors a note (type a
   quote + comment; optionally record/attach a clip), call Speak's
   `transcribeAudio` for the clip → correct the transcript → `saveVoiceNote`
   (or a `marginalia.note`-shaped typed event via `postTypedEvent`) with the
   `anchorQuote`, `comment`, and `audio_ref` (the object-storage blob key).
2. **Resolve:** read the persisted note events for the synthesis, run each
   through `reResolveNote(authored, ctx)` (re-resolves the anchor BY QUOTE), and
   hand the `ResolvedMarginNote[]` to `makeMarginaliaAugmentation`.
3. The augmentation already maps resolved notes → anchored widgets; no
   augmentation change needed.

## Reconsider if

- The surface wires the marginalia author flow + blob store (this gap closes) →
  mark superseded and record the wiring commit.
- A `marginalia.note` event shape turns out to overlap the existing voice-note
  event → reuse that event name instead of minting a new one (avoid a duplicate
  signal), and point the resolver at it.
- Live spoken-quote capture is built (the sprint's deferred follow-on) → the
  capture step gains a "speak the quote" path; the resolution + persistence
  decisions here are unchanged (a spoken quote is still a quote string).
- The full transcript-edit algebra (split-the-transcript-around-an-insertion) is
  ever wanted → that is the **Write surface's** transaction-filter facet, NOT the
  reading surface; filed for a future Write-side spec (out of scope here).
