// voice_note_anchor REST client (SPR-02, Wave 1 substrate).
//
// Mirrors the Python anchor_api surface in
// substrate/voice/anchor_api.py. Source of truth for shape +
// semantics is the Python module; this client is the typed binding
// SPR-05 calls when wiring the recording / glyph UI.
//
// The substrate REST routes that back these calls are not in this
// sprint — SPR-05 mounts them when the UI lands. Until then,
// callers can:
//   1. Use this module as the typed contract surface (compile-time
//      check that UI code expects the right shapes).
//   2. Mock the four functions in tests that need to exercise the
//      glyph UI without a live substrate.
//
// Endpoint URLs follow the Antiek convention of `/voice/anchors/...`
// with the same Cloudflare-Access auth posture as
// apps/reading/src/lib/api.ts (credentials: "include").

import type { ChunkResponse } from "./api";

// Re-exported for the small set of callers that need to know the
// chunk-id type without importing api.ts. The actual chunk lookup
// still goes through getChunk(chunkId) in api.ts.
export type { ChunkResponse };

const API_BASE =
  (import.meta.env.VITE_API_BASE_URL as string | undefined) ?? "";

// ─────────────────────────────────────────────────────────────────────
// Types — mirror substrate/voice/anchor_api.py:VoiceNoteAnchor + BBox.
// ─────────────────────────────────────────────────────────────────────

export interface BBox {
  x0: number;
  y0: number;
  x1: number;
  y1: number;
}

export interface VoiceNoteAnchor {
  anchor_id: string;
  voice_note_id: string;
  document_id: string;
  page: number;
  bbox: BBox;
  // null when no chunk meets the 30% overlap threshold OR when the
  // substrate's chunker doesn't expose per-chunk geometry (current
  // state — see substrate/voice/SCHEMA_NOTES.md).
  chunk_id: string | null;
  chunker_version: string;
  // ISO 8601 timestamp.
  created_at: string;
}

export interface CreateAnchorRequest {
  voice_note_id: string;
  document_id: string;
  page: number;
  bbox: BBox;
}

// ─────────────────────────────────────────────────────────────────────
// Errors
// ─────────────────────────────────────────────────────────────────────

/**
 * Thrown when the substrate returns a 409 on create_anchor because
 * an anchor for this voice_note_id already exists. The UI layer
 * should treat this as "the voice note is already anchored" and
 * fall back to get_anchor_by_voice_note rather than retrying the
 * create.
 *
 * Mirrors the DuckDB unique-constraint violation raised by the
 * Python create_anchor path (see SCHEMA_NOTES.md for the
 * concurrency contract).
 */
export class VoiceAnchorAlreadyExistsError extends Error {
  constructor(public voiceNoteId: string) {
    super(`voice_note_anchor already exists for ${voiceNoteId}`);
    this.name = "VoiceAnchorAlreadyExistsError";
  }
}

// ─────────────────────────────────────────────────────────────────────
// Client
// ─────────────────────────────────────────────────────────────────────

function url(path: string): string {
  return `${API_BASE}${path}`;
}

async function jsonOrThrow<T>(res: Response): Promise<T> {
  if (res.ok) {
    return (await res.json()) as T;
  }
  const body = await res.text();
  throw new Error(
    `voiceAnchors: ${res.status} ${res.statusText} — ${body}`,
  );
}

/**
 * Create one voice_note_anchor. Resolves chunk_id at write time
 * via the substrate-side bbox-overlap computation.
 *
 * Throws VoiceAnchorAlreadyExistsError on 409 (the unique
 * constraint on voice_note_id fired). The caller should NOT retry
 * — the substrate is the source of truth for 1:1.
 */
export async function createAnchor(
  req: CreateAnchorRequest,
): Promise<VoiceNoteAnchor> {
  const res = await fetch(url("/voice/anchors"), {
    method: "POST",
    headers: { "content-type": "application/json" },
    credentials: "include",
    body: JSON.stringify(req),
  });
  if (res.status === 409) {
    throw new VoiceAnchorAlreadyExistsError(req.voice_note_id);
  }
  return jsonOrThrow<VoiceNoteAnchor>(res);
}

/**
 * List anchors on a (document_id, page). Returned in stable order
 * (created_at ASC, anchor_id ASC). Used by the SPR-05 glyph layer.
 */
export async function getAnchorsOnPage(
  documentId: string,
  page: number,
): Promise<VoiceNoteAnchor[]> {
  const params = new URLSearchParams({
    document_id: documentId,
    page: String(page),
  });
  const res = await fetch(url(`/voice/anchors?${params}`), {
    credentials: "include",
  });
  return jsonOrThrow<VoiceNoteAnchor[]>(res);
}

/**
 * Fetch the anchor for one voice note. Returns null if unanchored
 * (Sprint 13 voice notes may exist without an anchor).
 */
export async function getAnchorByVoiceNote(
  voiceNoteId: string,
): Promise<VoiceNoteAnchor | null> {
  const res = await fetch(
    url(`/voice/anchors/by-voice-note/${encodeURIComponent(voiceNoteId)}`),
    { credentials: "include" },
  );
  if (res.status === 404) {
    return null;
  }
  return jsonOrThrow<VoiceNoteAnchor>(res);
}

/**
 * Diagnostic: ask the substrate which chunk it would resolve for a
 * given bbox without creating an anchor. Useful for preview UIs.
 *
 * Returns null when no chunk meets the 30% overlap threshold or
 * when chunks lack per-chunk geometry on this substrate.
 */
export async function resolveChunkForBBox(
  documentId: string,
  page: number,
  bbox: BBox,
): Promise<string | null> {
  const res = await fetch(url("/voice/anchors/resolve-chunk"), {
    method: "POST",
    headers: { "content-type": "application/json" },
    credentials: "include",
    body: JSON.stringify({ document_id: documentId, page, bbox }),
  });
  if (res.status === 404) {
    return null;
  }
  const body = await jsonOrThrow<{ chunk_id: string | null }>(res);
  return body.chunk_id;
}
