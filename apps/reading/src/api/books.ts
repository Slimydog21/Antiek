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
  // A source-declared open license (CC-BY / CC-BY-SA): servable, but NOT a
  // §9.10 publisher opt-in. Mirrors the backend ServabilityStatus enum, which
  // defines this member (substrate/books/servability.py) — the union was
  // missing it (drift fix).
  | "source_declared_open"
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
  // Rights context (Read SPR-05). Data-driven: the reader reads these off the
  // backend response, never a local flag. `tier` is the arXiv RightsTier
  // ('T1'|'T2'|'T3') or null for a non-arXiv document; `ad_eligible` is the
  // ad-rail gate (T1-only for arXiv; equals `servable` for non-arXiv,
  // preserving today's behaviour); `canonical_url` is the arxiv.org/abs link
  // or null; `license` is the license URI or null.
  tier: "T1" | "T2" | "T3" | null;
  ad_eligible: boolean;
  canonical_url: string | null;
  license: string | null;
  content_format?: "text" | "html";
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
  let resp = await apiFetch(
    `${API_BASE}/books/${encodeURIComponent(documentId)}/owner-full-text`,
  );
  // Local development and non-owner/public clients deliberately lack the
  // private-read capability; retain the established narrow endpoint there.
  if (resp.status === 403) {
    resp = await apiFetch(
      `${API_BASE}/books/${encodeURIComponent(documentId)}/full-text`,
    );
  }
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

// ── SPR-08 M2: talk-to-book (multi-turn, page-cited) ──────────────────
//
// A book-level conversation. The MULTI-TURN thread lives in the reader's
// SESSION state (the floating bookmark — sessionStorage, the usePosition
// precedent), NOT in substrate truth; the client sends the recent tail as
// `history` each turn. Answers cite page-level locations; the §9.0 gate on the
// backend means a withheld region's body never reaches the model or a citation.

/** One page-level citation in a talk-to-book / meta-reading answer. */
export interface BookCitation {
  chunk_id: string;
  document_id: string;
  /** The 0-based reader page the cited chunk anchors to, or null when the
   * chunk's section did not resolve to a page marker. When null,
   * `page_resolved` is false and the UI shows an honest "page not pinpointed"
   * — never a fabricated page (no false precision). */
  page_index: number | null;
  page_resolved: boolean;
  snippet: string;
}

/** One prior conversation turn carried forward. `question` is user-sourced;
 * `answer` the model's prior reply — kept distinct, never conflated. */
export interface TalkTurn {
  question: string;
  answer: string;
}

export interface AskBookResponse {
  answer_id: string | null;
  capture_status: "captured" | "unavailable";
  answer: string;
  citations: BookCitation[];
  /** False when the book had no extractable text to ground on (scanned-image
   * PDF / fully-withheld) — an honest no-context answer, never a hallucination. */
  grounded: boolean;
  context_chunk_count: number;
}

export interface BookAnswerJudgmentResponse {
  answer_id: string;
  judgment_id: string;
  verdict: "good" | "bad";
  note: string | null;
}

/** Ask one talk-to-book turn (Read SPR-08 M2). Answers CITE pages; a withheld
 * region can never be cited (backend §9.0 gate). 503 when no model provider is
 * configured (no-key) or the embedding model is unavailable. 404 for an
 * unknown book. */
export async function askBook(
  documentId: string,
  question: string,
  opts?: { history?: TalkTurn[]; researchTier?: "fast" | "deep" },
): Promise<AskBookResponse> {
  const resp = await apiFetch(`${API_BASE}/books/${encodeURIComponent(documentId)}/ask`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      question,
      history: opts?.history ?? [],
      research_tier: opts?.researchTier ?? "deep",
    }),
  });
  if (resp.status === 404) throw new Error("book_not_found");
  if (resp.status === 503) throw new Error("Talk-to-book isn’t available right now.");
  if (!resp.ok) throw new Error(`POST /books/{id}/ask: HTTP ${resp.status}`);
  return (await resp.json()) as AskBookResponse;
}

export async function judgeBookAnswer(
  documentId: string,
  answerId: string,
  verdict: "good" | "bad",
): Promise<BookAnswerJudgmentResponse> {
  const resp = await apiFetch(
    `${API_BASE}/books/${encodeURIComponent(documentId)}/answers/${encodeURIComponent(answerId)}/judgment`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ verdict }),
    },
  );
  if (resp.status === 404) throw new Error("book_answer_not_found");
  if (resp.status === 409) throw new Error("book_answer_already_judged");
  if (!resp.ok) throw new Error(`POST book answer judgment: HTTP ${resp.status}`);
  return (await resp.json()) as BookAnswerJudgmentResponse;
}

// ── SPR-08 M4: meta-reading deliverable (PROPOSED boundary) ───────────
//
// One-shot, READ-ONLY, page-cited synthesis over the OWNED corpus
// (internet-agnostic — owned DuckDB graph only). HARD length-box; saved as a
// re-openable Read asset. Built behind the "proposed (sign-off pending)" banner.

export interface MetaReadingRequest {
  prompt: string;
  length_unit: "pages" | "minutes";
  length_amount: number;
  research_tier?: "fast" | "deep";
  /** The owned-corpus scope. "hard" is the PROPOSED Research↔Read boundary;
   * "soft" is the rollback when sign-off is withheld. NEITHER reaches the
   * internet. */
  corpus_scope?: "hard" | "soft";
  /** An explicit pick of owned document ids (intersected with the owned set
   * under "hard" scope). Omit to scope to the whole owned servable corpus. */
  document_ids?: string[];
}

export interface MetaReadingResponse {
  asset_id: string;
  report: string;
  citations: BookCitation[];
  length_unit: "pages" | "minutes";
  length_amount: number;
  word_budget: number;
  /** True when the synthesis overran the budget and was cut — labelled, never
   * silently clipped. */
  truncated: boolean;
  corpus_scope: "hard" | "soft";
  corpus_document_ids: string[];
  /** True when the owned corpus had nothing to synthesize from — honest empty. */
  empty: boolean;
  context_chunk_count: number;
}

/** Generate + save a meta-reading deliverable over the owned corpus (Read
 * SPR-08 M4). 422 when the length is degenerate (stated bound). 503 when the
 * model / embedding is unavailable. */
export async function generateMetaReading(
  req: MetaReadingRequest,
): Promise<MetaReadingResponse> {
  const resp = await apiFetch(`${API_BASE}/corpus/meta-reading`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ research_tier: "deep", corpus_scope: "hard", ...req }),
  });
  if (resp.status === 422) {
    const body = await resp.json().catch(() => ({ detail: "Invalid length." }));
    throw new Error(typeof body.detail === "string" ? body.detail : "Invalid length.");
  }
  if (resp.status === 503) throw new Error("Meta-reading isn’t available right now.");
  if (!resp.ok) throw new Error(`POST /corpus/meta-reading: HTTP ${resp.status}`);
  return (await resp.json()) as MetaReadingResponse;
}

// ── SPR-13 — personal document space (collect / categorize / file) ────
//
// The reader's "bed of information that labels itself": their CREATED
// deliverables (SPR-08 meta-readings) + saved reads (SPR-07 source.read),
// reconstructed server-side from the event log — NO new store, NO localStorage
// of substrate truth. Distinct from listBooks (the raw library of source books).

/** One item in the personal space. ``kind`` distinguishes a created asset from
 * a source-book read (the M4 visible distinction). ``open_route`` re-opens it. */
export interface PersonalAsset {
  asset_id: string;
  kind: "meta_reading" | "saved_read";
  title: string;
  prompt: string | null;
  document_ids: string[];
  emitted_at: string | null;
  open_route: string;
}

export interface PersonalSpaceResponse {
  assets: PersonalAsset[];
  count: number;
}

/** List the personal-space assets (Read SPR-13 M1), newest first. Substrate-
 * backed (event-log scan), not a new store. */
export async function listPersonalSpace(): Promise<PersonalSpaceResponse> {
  const resp = await apiFetch(`${API_BASE}/meta-readings`);
  if (!resp.ok) throw new Error(`GET /meta-readings: HTTP ${resp.status}`);
  return (await resp.json()) as PersonalSpaceResponse;
}

export interface AssetCategory {
  /** Stable unique key the surface renders on — two clusters can share a human
   * label, so the id (not the label) is the safe React list key. */
  category_id: string;
  label: string;
  asset_ids: string[];
  /** "theme" when the label emerged from clustering; "recency" when the corpus
   * was below the stability bound and we fell back honestly (never a fake label). */
  ordering: "theme" | "recency";
}

export interface CategorizedSpaceResponse {
  categories: AssetCategory[];
  ordering: "theme" | "recency";
  /** Asset-count below which categories don't stabilize → recency fallback. */
  stability_bound: number;
}

/** Cluster the personal-space assets into SYSTEM-named categories (Read SPR-13
 * M2). The system names the categories; the user never hand-organizes folders.
 * Honest recency fallback below the stability bound. */
export async function listPersonalSpaceCategories(): Promise<CategorizedSpaceResponse> {
  const resp = await apiFetch(`${API_BASE}/meta-readings/categories`);
  if (!resp.ok) throw new Error(`GET /meta-readings/categories: HTTP ${resp.status}`);
  return (await resp.json()) as CategorizedSpaceResponse;
}

export interface ProjectMatch {
  investigation_id: string;
  question: string;
  score: number;
}

export interface FileSuggestionResponse {
  document_id: string;
  matches: ProjectMatch[];
}

/** Ask which research projects a doc could be filed into (Read SPR-13 M3).
 * SUGGEST-ONLY — this only ranks; filing is the explicit-accept event. 503 when
 * the embedder is unavailable (the surface then shows no suggestion). */
export async function getFileSuggestion(
  documentId: string,
): Promise<FileSuggestionResponse> {
  const params = new URLSearchParams({ document_id: documentId });
  const resp = await apiFetch(`${API_BASE}/meta-readings/file-suggestion?${params.toString()}`);
  if (resp.status === 503) {
    // Embedder unavailable — no suggestion, not an error the surface surfaces.
    return { document_id: documentId, matches: [] };
  }
  if (!resp.ok) throw new Error(`GET /meta-readings/file-suggestion: HTTP ${resp.status}`);
  return (await resp.json()) as FileSuggestionResponse;
}

export interface SavedMetaReading {
  asset_id: string;
  prompt: string;
  report: string;
  citations: BookCitation[];
  length_unit: "pages" | "minutes";
  length_amount: number;
  truncated: boolean;
  corpus_scope: "hard" | "soft";
  corpus_document_ids: string[];
}

/** Re-open a saved meta-reading asset by id (Read SPR-13 M1 — opens back into
 * the meta-doc view). Reads the saved event off the log. */
export async function getSavedMetaReading(assetId: string): Promise<SavedMetaReading> {
  const resp = await apiFetch(`${API_BASE}/meta-readings/${encodeURIComponent(assetId)}`);
  if (resp.status === 404) throw new Error(`Saved reading ${assetId} not found.`);
  if (!resp.ok) throw new Error(`GET /meta-readings/{id}: HTTP ${resp.status}`);
  return (await resp.json()) as SavedMetaReading;
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
    case "source_declared_open":
      return { label: "Open license", colour: "aurora" };
    case "gated_metadata_only":
      return { label: "Preview only", colour: "sun" };
    case "taken_down":
      return { label: "Removed", colour: "danger" };
  }
}
