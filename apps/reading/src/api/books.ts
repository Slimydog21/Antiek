/**
 * Servable-corpus API client (Read SPR-01 → consumed by SPR-02/03).
 *
 * Mirrors `interfaces/research/api/books.py`. The full-text endpoint is
 * the deny-by-default legal gate: a gated book returns `full_text: null`
 * (snippet only), a taken-down book returns neither. The frontend never
 * decides servability — it renders what the gate returns.
 */

import { API_BASE, apiFetch } from "../lib/api";

export type Servability =
  | "public_domain"
  | "platform_authored"
  | "publisher_opted_in"
  | "gated_metadata_only"
  | "taken_down";

export interface BookSummary {
  document_id: string;
  title: string | null;
  author: string | null;
  servability: Servability;
  servable_full_text: boolean;
  page_count: number;
  cover_uri: string | null;
  ip_holder_id: string | null;
  taken_down: boolean;
}

export interface TocItem {
  title: string;
  page_index: number | null;
  level: number;
}

export interface BookDetail extends BookSummary {
  pagination_scheme: string;
  provenance: string | null;
  license_basis: string | null;
  toc: TocItem[];
}

export interface BookListResponse {
  books: BookSummary[];
  count: number;
}

export interface FullTextResponse {
  document_id: string;
  servable: boolean;
  servability: Servability | null;
  full_text: string | null;
  snippet: string | null;
  title: string | null;
  author: string | null;
  reason: string;
}

export type CorpusStatus = "servable" | "gated" | "all";

/** List the corpus. `servable` (default) returns only full-text-servable
 * books; `gated` returns metadata-only books; `all` returns both, each
 * carrying its servability so the caller can flag gated ones. */
export async function listBooks(status: CorpusStatus = "servable"): Promise<BookListResponse> {
  const resp = await apiFetch(`${API_BASE}/books?status=${encodeURIComponent(status)}`);
  if (!resp.ok) throw new Error(`GET /books: HTTP ${resp.status}`);
  return (await resp.json()) as BookListResponse;
}

export async function getBook(documentId: string): Promise<BookDetail> {
  const resp = await apiFetch(`${API_BASE}/books/${encodeURIComponent(documentId)}`);
  if (resp.status === 404) throw new Error("book_not_found");
  if (!resp.ok) throw new Error(`GET /books/{id}: HTTP ${resp.status}`);
  return (await resp.json()) as BookDetail;
}

/** Fetch the body the gate permits: full text for servable books, a
 * bounded snippet for gated books, nothing for taken-down books. */
export async function getBookFullText(documentId: string): Promise<FullTextResponse> {
  const resp = await apiFetch(
    `${API_BASE}/books/${encodeURIComponent(documentId)}/full-text`,
  );
  if (resp.status === 404) throw new Error("book_not_found");
  if (!resp.ok) throw new Error(`GET /books/{id}/full-text: HTTP ${resp.status}`);
  return (await resp.json()) as FullTextResponse;
}

export interface TranscribeResponse {
  transcript: string;
  language: string | null;
  duration_seconds: number;
}

/** Transcribe a captured audio blob (Read SPR-06). 503 when the Whisper
 * tier isn't available (no operator key). */
export async function transcribeAudio(audio: Blob): Promise<TranscribeResponse> {
  const resp = await apiFetch(`${API_BASE}/voice/transcribe`, {
    method: "POST",
    headers: { "Content-Type": audio.type || "audio/webm" },
    body: audio,
  });
  if (resp.status === 503) throw new Error("Transcription isn’t available right now.");
  if (resp.status === 400) throw new Error("No audio captured.");
  if (!resp.ok) throw new Error(`POST /voice/transcribe: HTTP ${resp.status}`);
  return (await resp.json()) as TranscribeResponse;
}

export interface VoiceNoteResult {
  voice_note_id: string;
  document_id: string;
  page_index: number;
  note_count: number;
  notes: string[];
  emitted_event_ids: string[];
}

/** Distill a CONFIRMED voice-note transcript into anchored insight/
 * question notes (Read SPR-06). `confirmed` MUST be true — the server
 * refuses an unconfirmed transcript. */
export async function saveVoiceNote(
  documentId: string,
  body: {
    page_index: number;
    transcript: string;
    investigation_id: string;
    audio_ref?: string | null;
  },
): Promise<VoiceNoteResult> {
  const resp = await apiFetch(`${API_BASE}/books/${encodeURIComponent(documentId)}/voice-note`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ ...body, confirmed: true }),
  });
  if (resp.status === 400) throw new Error("Confirm the transcript before saving.");
  if (resp.status === 503) throw new Error("The note distiller isn’t available right now.");
  if (!resp.ok) throw new Error(`POST /books/{id}/voice-note: HTTP ${resp.status}`);
  return (await resp.json()) as VoiceNoteResult;
}

export interface ImpressionItem {
  slot_id: string;
  page_index: number;
  fill_kind: "ad" | "house";
  revenue_usd_cents: number;
  focused_dwell_ms: number;
  tab_focused: boolean;
}

/** Flush a session's reader ad impressions (Read SPR-05 → SPR-09). The
 * attention rule + accrual are applied server-side; the client's claimed
 * attention isn't trusted. Best-effort: a failed flush never disrupts
 * reading. */
export async function recordAdImpressions(
  documentId: string,
  sessionId: string,
  impressions: ImpressionItem[],
): Promise<void> {
  if (impressions.length === 0) return;
  await apiFetch(`${API_BASE}/books/${encodeURIComponent(documentId)}/ad-impressions`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ session_id: sessionId, impressions }),
    keepalive: true, // survive a page-unload flush
  });
}

export interface SpinResearchResponse {
  investigation_id: string;
  document_id: string;
  page_index: number;
  gated: boolean;
  servability: Servability | string;
  seed_preview: string;
}

/** Spin a deep research from a book passage (Read SPR-08). The seed is
 * built server-side and is gate-safe — a gated book's full text never
 * crosses into the research, even if `passageText` is sent. Returns the
 * child investigation id to navigate to. */
export async function spinResearch(
  documentId: string,
  pageIndex: number,
  passageText?: string,
): Promise<SpinResearchResponse> {
  const resp = await apiFetch(`${API_BASE}/books/${encodeURIComponent(documentId)}/spin-research`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ page_index: pageIndex, passage_text: passageText ?? null }),
  });
  if (resp.status === 404) throw new Error("book_not_found");
  if (!resp.ok) throw new Error(`POST /books/{id}/spin-research: HTTP ${resp.status}`);
  return (await resp.json()) as SpinResearchResponse;
}

export interface CuratedBook {
  document_id: string;
  title: string | null;
  author: string | null;
  score: number;
}

export interface CurateResponse {
  prompt: string;
  books: CuratedBook[];
}

/** Prompt-to-curate (Read SPR-04). Ranks ONLY servable books by relevance
 * to the prompt — a gated book is never curated into a readable list.
 * Returns 503 if the embedding model isn't available server-side. */
export async function curateBooks(prompt: string, limit = 20): Promise<CurateResponse> {
  const params = new URLSearchParams({ prompt, limit: String(limit) });
  const resp = await apiFetch(`${API_BASE}/books/curate?${params.toString()}`);
  if (resp.status === 503) throw new Error("Curation is temporarily unavailable.");
  if (!resp.ok) throw new Error(`GET /books/curate: HTTP ${resp.status}`);
  return (await resp.json()) as CurateResponse;
}

/** Human-readable label + Lemon tag colour for a servability status. One
 * source so Library cards and the reader badge never disagree. */
export function servabilityLabel(s: Servability): { label: string; colour: "aurora" | "sun" | "muted" | "danger" } {
  switch (s) {
    case "public_domain":
      return { label: "Public domain", colour: "aurora" };
    case "platform_authored":
      return { label: "Antiek original", colour: "aurora" };
    case "publisher_opted_in":
      return { label: "Publisher licensed", colour: "aurora" };
    case "gated_metadata_only":
      return { label: "Preview only", colour: "sun" };
    case "taken_down":
      return { label: "Removed", colour: "danger" };
  }
}
