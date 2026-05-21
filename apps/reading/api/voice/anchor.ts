// SPR-05 / M3 — Anchored voice-note save client.
//
// The TS-side mirror of services/voice/anchor_service.py:
// save_anchored_voice_note. SPR-05's VoiceAnchor.tsx calls this when
// the user clicks "Save". The substrate FastAPI handler mounts
// POST /api/voice/anchor onto save_anchored_voice_note; this client
// is just the typed envelope.
//
// Why a thin client module rather than fetch() inline at the call
// site: matches the polyglot-seam convention in
// apps/reading/api/library/ingest.ts. If the URL shape or status
// semantics shift, the recording widget (VoiceAnchor.tsx) doesn't
// need to know.
//
// Two-part wire shape — the route accepts multipart/form-data:
//   - field "audio": the recorded blob (audio/webm)
//   - field "params": JSON with document_id, page, bbox, transcript,
//                     duration_seconds, language?, title?
// This shape lets the handler stream the audio straight to whisper
// without buffering JSON-encoded base64 (master-spec §11.5 — keep
// audio off the JSON wire). The Sprint 13 transcription pipeline
// (acquisition.voice.client) is reused server-side.

import type { BBox, VoiceNoteAnchor } from "../../src/lib/voiceAnchors";

/** Base URL for the substrate API; resolved the same way as
 *  api/library/ingest.ts so dev / staging / prod can re-target. */
function apiBase(): string {
  const env = (import.meta as { env?: { VITE_API_BASE_URL?: string } }).env;
  return (env?.VITE_API_BASE_URL || "").replace(/\/+$/, "");
}

/** Params half of the multipart POST. The audio blob travels as
 *  the other field — see ``saveAnchoredVoiceNote`` below. */
export interface SaveAnchoredVoiceNoteParams {
  document_id: string;
  page: number;
  bbox: BBox;
  /** Pre-transcribed text. Optional: when omitted, the substrate
   *  side transcribes the audio via the Sprint 13 whisper pipeline.
   *  Pre-supplied transcripts skip the whisper round-trip — used by
   *  tests + future on-device whisper. */
  transcript?: string;
  duration_seconds: number;
  /** ISO 8601. Defaults to "now" on the server side. */
  recorded_at?: string;
  language?: string;
  title?: string;
}

export interface SaveAnchoredVoiceNoteResponse {
  voice_note_id: string;
  anchor: VoiceNoteAnchor;
}

/** Typed error from the anchor-save endpoint. */
export class SaveAnchoredVoiceNoteError extends Error {
  constructor(
    message: string,
    public status: number,
    public body: string,
  ) {
    super(message);
    this.name = "SaveAnchoredVoiceNoteError";
  }
}

/**
 * POST /api/voice/anchor — atomically save a voice note + its
 * anchor. The substrate handler wraps both writes in one DuckDB
 * transaction (see services/voice/anchor_service.py); on any
 * failure the handler returns 5xx and NO row persists.
 *
 * The 409 case (a voice_note_anchor already exists for this voice
 * note) is surfaced via SaveAnchoredVoiceNoteError; the caller
 * SHOULD NOT retry — the substrate is the source of truth for 1:1.
 */
export async function saveAnchoredVoiceNote(
  audio: Blob,
  params: SaveAnchoredVoiceNoteParams,
): Promise<SaveAnchoredVoiceNoteResponse> {
  const url = `${apiBase()}/api/voice/anchor`;
  const fd = new FormData();
  fd.append("audio", audio, "voice-note.webm");
  fd.append("params", JSON.stringify(params));
  const res = await fetch(url, {
    method: "POST",
    credentials: "include",
    body: fd,
  });
  if (!res.ok) {
    const body = await res.text().catch(() => "");
    throw new SaveAnchoredVoiceNoteError(
      `save anchored voice note failed: HTTP ${res.status}`,
      res.status,
      body,
    );
  }
  return res.json() as Promise<SaveAnchoredVoiceNoteResponse>;
}
