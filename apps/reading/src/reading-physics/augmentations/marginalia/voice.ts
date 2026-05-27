// ─────────────────────────────────────────────────────────────────────────
// voice.ts — the optional voice clip on a margin note (SPR-07 M3).
//
// The talk's demo: the reader speaks a comment after the quote. On Antiek that
// comment is a voice clip whose TRANSCRIPT is the data (PR-2 — text is the data)
// and whose audio BLOB lives in object storage keyed by the note's substrate
// event id. Speak ALREADY handles this exact path — DO NOT fork it:
//
//   - `transcribeAudio(blob)` (apps/reading/src/api/books.ts) → POST
//     /voice/transcribe → `{ transcript, language, duration_seconds }`. The
//     reader CORRECTS the transcript (ASR mishears; VoiceNote.tsx surfaces the
//     correction step) before it becomes the note's data.
//   - `saveVoiceNote(documentId, { …, transcript, audio_ref })` → POST
//     /books/{id}/voice-note → persists through the ONE shipped funnel; the
//     `audio_ref` field is the object-storage reference to the blob.
//
// So the voice path's storage decision is SETTLED by reuse: the transcript +
// the `audio_ref` reference are a SUBSTRATE event (text is the data), and the
// audio blob lives in object storage keyed by the event id. The augmentation
// does NOT open a new store (PR-2). See reading-physics/README.md + the decision
// doc `docs/decisions/spr-07-marginalia-voice-storage.md`.
//
// ── WHAT THIS MODULE IS (and is NOT) ───────────────────────────────────────
//
// Like SPR-06's `source.read` and SPR-05's geometry pass, the actual EMIT (post
// the note event, store the blob) is a SURFACE/BACKEND integration — it needs a
// write funnel + object storage, which an augmentation may not touch (PR-2 /
// PR-6). This module therefore does NOT capture audio, transcribe, or persist.
// It defines the RESOLVED VIEW the surface hands the augmentation — the
// substrate-ref + transcript a note's clip resolves to — and the pure helpers
// that read it. The augmentation renders the note against this view; it lights
// up fully the moment the surface wires the emit (documented-deferred).
//
// A note with NO clip works fully — voice is OPTIONAL, not required (M3). And a
// clip with a FAILED/ABSENT transcript is honest: the note still anchors and
// shows its text comment; the clip is marked "transcript unavailable", never
// fabricated (rigor #3).
//
// PR-2 (no side store): the transcript + `audioRef` are substrate-derived,
//   handed in by the surface; stored nowhere here; no persistence import.
// PR-6 (substrate upstream): the surface owns the one write funnel + the blob
//   store; this module reads the resolved view, never writes.
// PR-8 (agent-authorable): imports NOTHING at runtime — type + pure-helper only.
// ─────────────────────────────────────────────────────────────────────────

// (types-only import; no runtime dependency — keeps the module PR-8-clean and
//  forkless of Speak's component tree.)

/**
 * The resolved voice-clip view a margin note may carry (M3). The SURFACE
 * resolves this from the note's substrate event (the transcript + the
 * `audio_ref` it persisted via Speak's `saveVoiceNote`) and hands it in. Every
 * field originates in the substrate (PR-2); the augmentation invents nothing.
 *
 * `transcript: null` is the HONEST failed/absent-transcript state (ASR
 * unavailable, or the reader never confirmed one). The note still works — it
 * shows its typed comment + a "transcript unavailable" marker, never a guessed
 * transcript (rigor #3).
 */
export interface VoiceClipView {
  /** The object-storage reference to the audio blob, keyed by the note's
   *  substrate event id (PR-2 — the blob is NOT in the substrate; only this
   *  reference + the transcript are). Null when no clip was attached. */
  readonly audioRef: string | null;
  /** The clip's transcript — the DATA (PR-2: text is the data). Null when ASR
   *  failed or the reader attached a clip without confirming a transcript
   *  (honest, never fabricated). */
  readonly transcript: string | null;
  /** Optional clip duration in seconds (Speak's `transcribeAudio` returns it).
   *  Purely for the surface's "0:07" affordance; null when unknown. */
  readonly durationSeconds?: number | null;
}

/** A note with no clip — the canonical "voice is optional" value. */
export const NO_VOICE_CLIP: VoiceClipView = {
  audioRef: null,
  transcript: null,
  durationSeconds: null,
};

/** True iff a note actually carries a clip (an audio reference exists). A clip
 *  may exist WITHOUT a transcript (the failed/absent-transcript case — M3). */
export function hasVoiceClip(clip: VoiceClipView | null | undefined): boolean {
  return !!clip && clip.audioRef !== null;
}

/** True iff a clip carries usable transcript text. Distinct from `hasVoiceClip`:
 *  a clip can exist with a null transcript (ASR failed) — that is honest, not an
 *  error. The note renders the typed comment regardless. */
export function hasTranscript(clip: VoiceClipView | null | undefined): boolean {
  return !!clip && typeof clip.transcript === "string" && clip.transcript.trim().length > 0;
}

/**
 * The plain-text the note materialises for a clip (M3 + M4). Voice marginalia is
 * "just plain text material": the CLIP's contribution to the note's text is its
 * TRANSCRIPT (PR-2 — text is the data). When the transcript is absent/failed,
 * the materialised text is the honest marker, never a fabricated transcript.
 *
 * Returns null when there is no clip at all (the note is then pure typed
 * comment). The surface composes this with the note's typed comment to render
 * the margin note; copying the note carries this materialised text (M4).
 */
export function clipMaterialText(clip: VoiceClipView | null | undefined): string | null {
  if (!hasVoiceClip(clip)) return null;
  if (hasTranscript(clip)) return clip!.transcript!.trim();
  // A clip with no transcript: honest marker, never a guess.
  return "[voice clip — transcript unavailable]";
}
