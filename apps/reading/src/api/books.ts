/**
 * Servable-corpus API client (Read SPR-01 → consumed by SPR-02/03).
 *
 * Mirrors `interfaces/research/api/books.py`. The full-text endpoint is
 * the deny-by-default legal gate: a gated book returns `full_text: null`
 * (snippet only), a taken-down book returns neither. The frontend never
 * decides servability — it renders what the gate returns.
 */

import { API_BASE, apiFetch } from "../lib/api";

function assertNonNegativeSafeInteger(value: number, field: string): void {
  if (!Number.isSafeInteger(value) || value < 0) {
    throw new RangeError(`${field} must be a non-negative safe integer`);
  }
}

function assertPositiveSafeInteger(value: number, field: string): void {
  if (!Number.isSafeInteger(value) || value <= 0) {
    throw new RangeError(`${field} must be a positive safe integer`);
  }
}

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

function safeServability(value: unknown): Servability {
  switch (value) {
    case "public_domain":
    case "platform_authored":
    case "publisher_opted_in":
    case "source_declared_open":
    case "gated_metadata_only":
    case "taken_down":
      return value;
    default:
      return "gated_metadata_only";
  }
}

function safeNullableServability(value: unknown): Servability | null {
  if (value == null) return null;
  return safeServability(value);
}

function safeBookSummary(value: unknown): BookSummary | null {
  const book = record(value);
  if (!book) return null;
  const documentId = nonEmptyString(book.document_id);
  if (!documentId) return null;
  const servability = safeServability(book.servability);
  const takenDown = book.taken_down === true || servability === "taken_down";
  const servableFullText =
    book.servable_full_text === true &&
    !takenDown &&
    servability !== "gated_metadata_only";
  return {
    document_id: documentId,
    title: nullableString(book.title),
    author: nullableString(book.author),
    servability,
    servable_full_text: servableFullText,
    page_count: nonNegativeSafeInteger(book.page_count) ?? 0,
    cover_uri: nullableString(book.cover_uri),
    ip_holder_id: nullableString(book.ip_holder_id),
    taken_down: takenDown,
  };
}

function safeBookListResponse(value: unknown): BookListResponse {
  const body = record(value);
  const books = Array.isArray(body?.books)
    ? body.books.flatMap((item) => {
        const book = safeBookSummary(item);
        return book ? [book] : [];
      })
    : [];
  return {
    books,
    count: nonNegativeSafeInteger(body?.count) ?? books.length,
  };
}

export interface FullTextResponse {
  document_id: string;
  servable: boolean;
  servability: Servability | null;
  full_text: string | null;
  snippet: string | null;
  // The SPR-01 typed-block `Document`, serialized as JSON (Reader SPR-02 persists
  // it; SPR-03's one `<Reader>` deserializes + renders it for rich typography).
  // §9.0: present ONLY when the gate served the full body — a gated/taken-down
  // book returns null here exactly as it does `full_text`, so withheld content's
  // structured blocks never reach the client. Optional for now: SPR-02's serve
  // change (which populates it, gated identically to full_text) is the deferred,
  // critic-backed remaining work; until it lands the field is absent and the
  // Reader falls back to the legacy `full_text` flattener (additive, never blank).
  structured_blocks?: string | null;
  // Representative chunk anchor for reader-side view-state (`source.read`,
  // marginalia provenance). Returned only when the full body is served.
  representative_chunk_id?: string | null;
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
}

function safeTocItem(value: unknown): TocItem | null {
  const item = record(value);
  if (!item) return null;
  const title = nonEmptyString(item.title);
  if (!title) return null;
  const pageIndex = nonNegativeSafeInteger(item.page_index);
  return {
    title,
    page_index: pageIndex,
    level: nonNegativeSafeInteger(item.level) ?? 1,
  };
}

function safeBookDetail(value: unknown): BookDetail {
  const summary = safeBookSummary(value);
  const body = record(value);
  if (!summary || !body) {
    throw new Error("Malformed book response.");
  }
  const toc = Array.isArray(body.toc)
    ? body.toc.flatMap((item) => {
        const tocItem = safeTocItem(item);
        return tocItem ? [tocItem] : [];
      })
    : [];
  return {
    ...summary,
    pagination_scheme: nonEmptyString(body.pagination_scheme) ?? "unknown",
    provenance: nullableString(body.provenance),
    license_basis: nullableString(body.license_basis),
    toc,
  };
}

function safeRightsTier(value: unknown): "T1" | "T2" | "T3" | null {
  return value === "T1" || value === "T2" || value === "T3" ? value : null;
}

function safeFullTextResponse(value: unknown): FullTextResponse {
  const body = record(value);
  const documentId = body ? nonEmptyString(body.document_id) : null;
  if (!body || !documentId) {
    throw new Error("Malformed book full-text response.");
  }
  const fullText = typeof body.full_text === "string" ? body.full_text : null;
  const servable = body.servable === true && fullText !== null;
  return {
    document_id: documentId,
    servable,
    servability: safeNullableServability(body.servability),
    full_text: servable ? fullText : null,
    snippet: typeof body.snippet === "string" ? body.snippet : null,
    structured_blocks:
      servable && typeof body.structured_blocks === "string" ? body.structured_blocks : null,
    representative_chunk_id: servable ? nullableString(body.representative_chunk_id) : null,
    title: nullableString(body.title),
    author: nullableString(body.author),
    reason: nonEmptyString(body.reason) ?? (servable ? "servable" : "not_servable"),
    tier: safeRightsTier(body.tier),
    ad_eligible: body.ad_eligible === true && servable,
    canonical_url: nullableString(body.canonical_url),
    license: nullableString(body.license),
  };
}

export type CorpusStatus = "servable" | "gated" | "all";

/** List the corpus. `servable` (default) returns only full-text-servable
 * books; `gated` returns metadata-only books; `all` returns both, each
 * carrying its servability so the caller can flag gated ones. */
export async function listBooks(status: CorpusStatus = "servable"): Promise<BookListResponse> {
  const resp = await apiFetch(`${API_BASE}/books?status=${encodeURIComponent(status)}`);
  if (!resp.ok) throw new Error(`GET /books: HTTP ${resp.status}`);
  return safeBookListResponse(await resp.json());
}

export async function getBook(documentId: string): Promise<BookDetail> {
  const resolvedDocumentId = requireNonEmptyRequestString(documentId, "documentId");
  const resp = await apiFetch(`${API_BASE}/books/${encodeURIComponent(resolvedDocumentId)}`);
  if (resp.status === 404) throw new Error("book_not_found");
  if (!resp.ok) throw new Error(`GET /books/{id}: HTTP ${resp.status}`);
  return safeBookDetail(await resp.json());
}

/** Fetch the body the gate permits: full text for servable books, a
 * bounded snippet for gated books, nothing for taken-down books. */
export async function getBookFullText(documentId: string): Promise<FullTextResponse> {
  const resolvedDocumentId = requireNonEmptyRequestString(documentId, "documentId");
  const resp = await apiFetch(
    `${API_BASE}/books/${encodeURIComponent(resolvedDocumentId)}/full-text`,
  );
  if (resp.status === 404) throw new Error("book_not_found");
  if (!resp.ok) throw new Error(`GET /books/{id}/full-text: HTTP ${resp.status}`);
  return safeFullTextResponse(await resp.json());
}

export interface TranscribeResponse {
  transcript: string;
  language: string | null;
  duration_seconds: number;
}

function safeTranscribeResponse(value: unknown): TranscribeResponse {
  const body = record(value);
  if (!body || typeof body.transcript !== "string") {
    throw new Error("Malformed transcription response.");
  }
  return {
    transcript: body.transcript.trim(),
    language: nullableString(body.language),
    duration_seconds: nonNegativeFiniteNumber(body.duration_seconds) ?? 0,
  };
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
  return safeTranscribeResponse(await resp.json());
}

export interface VoiceNoteResult {
  voice_note_id: string;
  document_id: string;
  page_index: number;
  note_count: number;
  notes: string[];
  emitted_event_ids: string[];
}

function safeVoiceNoteResult(value: unknown): VoiceNoteResult {
  const body = record(value);
  const voiceNoteId = body ? nonEmptyString(body.voice_note_id) : null;
  const documentId = body ? nonEmptyString(body.document_id) : null;
  const pageIndex = body ? nonNegativeSafeInteger(body.page_index) : null;
  if (!body || !voiceNoteId || !documentId || pageIndex === null) {
    throw new Error("Malformed voice-note response.");
  }
  const notes = safeStringArray(body.notes);
  return {
    voice_note_id: voiceNoteId,
    document_id: documentId,
    page_index: pageIndex,
    note_count: nonNegativeSafeInteger(body.note_count) ?? notes.length,
    notes,
    emitted_event_ids: safeStringArray(body.emitted_event_ids),
  };
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
    capture_event_id?: string | null;
  },
): Promise<VoiceNoteResult> {
  assertNonNegativeSafeInteger(body.page_index, "page_index");
  const resolvedDocumentId = requireNonEmptyRequestString(documentId, "documentId");
  const transcript = requireNonEmptyRequestString(body.transcript, "transcript");
  const investigationId = requireNonEmptyRequestString(body.investigation_id, "investigation_id");
  const requestBody = {
    page_index: body.page_index,
    transcript,
    investigation_id: investigationId,
    audio_ref: nullableString(body.audio_ref),
    capture_event_id: nullableString(body.capture_event_id),
    confirmed: true,
  };
  const resp = await apiFetch(`${API_BASE}/books/${encodeURIComponent(resolvedDocumentId)}/voice-note`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(requestBody),
  });
  if (resp.status === 400) throw new Error("Confirm the transcript before saving.");
  if (resp.status === 503) throw new Error("The note distiller isn’t available right now.");
  if (!resp.ok) throw new Error(`POST /books/{id}/voice-note: HTTP ${resp.status}`);
  return safeVoiceNoteResult(await resp.json());
}

export interface ImpressionItem {
  slot_id: string;
  page_index: number;
  fill_kind: "ad" | "house";
  revenue_usd_cents: number;
  focused_dwell_ms: number;
  tab_focused: boolean;
}

function nonNegativeSafeInteger(value: unknown): number | null {
  return typeof value === "number" && Number.isSafeInteger(value) && value >= 0
    ? value
    : null;
}

function nonNegativeFiniteNumber(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) && value >= 0
    ? value
    : null;
}

function record(value: unknown): Record<string, unknown> | null {
  return typeof value === "object" && value !== null && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : null;
}

function nonEmptyString(value: unknown): string | null {
  if (typeof value !== "string") return null;
  const trimmed = value.trim();
  return trimmed.length > 0 ? trimmed : null;
}

function nullableString(value: unknown): string | null {
  return value == null ? null : nonEmptyString(value);
}

function requireNonEmptyRequestString(value: unknown, field: string): string {
  const text = nonEmptyString(value);
  if (!text) {
    throw new TypeError(`${field} must be a non-empty string`);
  }
  return text;
}

function sanitizeOptionalRequestStringArray(value: unknown): string[] | undefined {
  const strings = safeStringArray(value);
  const deduped = Array.from(new Set(strings));
  return deduped.length > 0 ? deduped : undefined;
}

function safeStringArray(value: unknown): string[] {
  if (!Array.isArray(value)) return [];
  return value.flatMap((item) => {
    const text = nonEmptyString(item);
    return text ? [text] : [];
  });
}

function sanitizeImpression(item: ImpressionItem): ImpressionItem | null {
  const slotId = typeof item.slot_id === "string" ? item.slot_id.trim() : "";
  const pageIndex = nonNegativeSafeInteger(item.page_index);
  const revenueUsdCents = nonNegativeSafeInteger(item.revenue_usd_cents);
  const focusedDwellMs = nonNegativeFiniteNumber(item.focused_dwell_ms);
  if (
    !slotId ||
    pageIndex === null ||
    revenueUsdCents === null ||
    focusedDwellMs === null ||
    (item.fill_kind !== "ad" && item.fill_kind !== "house")
  ) {
    return null;
  }
  return {
    slot_id: slotId,
    page_index: pageIndex,
    fill_kind: item.fill_kind,
    revenue_usd_cents: revenueUsdCents,
    focused_dwell_ms: focusedDwellMs,
    tab_focused: item.tab_focused === true,
  };
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
  const safeImpressions = impressions
    .map((item) => sanitizeImpression(item))
    .filter((item): item is ImpressionItem => item !== null);
  if (safeImpressions.length === 0) return;
  const resolvedDocumentId = nonEmptyString(documentId);
  const resolvedSessionId = nonEmptyString(sessionId);
  if (!resolvedDocumentId || !resolvedSessionId) return;
  try {
    await apiFetch(`${API_BASE}/books/${encodeURIComponent(resolvedDocumentId)}/ad-impressions`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ session_id: resolvedSessionId, impressions: safeImpressions }),
      keepalive: true, // survive a page-unload flush
    });
  } catch {
    // Best-effort flush: reading must continue if unload/network loses it.
  }
}

export interface SpinResearchResponse {
  investigation_id: string;
  document_id: string;
  page_index: number;
  gated: boolean;
  servability: Servability | (string & Record<never, never>);
  seed_preview: string;
}

function safeSpinResearchResponse(value: unknown): SpinResearchResponse {
  const body = record(value);
  const investigationId = body ? nonEmptyString(body.investigation_id) : null;
  const documentId = body ? nonEmptyString(body.document_id) : null;
  const pageIndex = body ? nonNegativeSafeInteger(body.page_index) : null;
  if (!body || !investigationId || !documentId || pageIndex === null) {
    throw new Error("Malformed spin-research response.");
  }
  return {
    investigation_id: investigationId,
    document_id: documentId,
    page_index: pageIndex,
    gated: body.gated === true,
    servability: nonEmptyString(body.servability) ?? "gated_metadata_only",
    seed_preview: typeof body.seed_preview === "string" ? body.seed_preview.trim() : "",
  };
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
  const resolvedDocumentId = requireNonEmptyRequestString(documentId, "documentId");
  assertNonNegativeSafeInteger(pageIndex, "page_index");
  const safePassageText = nullableString(passageText);
  const resp = await apiFetch(`${API_BASE}/books/${encodeURIComponent(resolvedDocumentId)}/spin-research`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ page_index: pageIndex, passage_text: safePassageText }),
  });
  if (resp.status === 404) throw new Error("book_not_found");
  if (resp.status === 503) throw new Error("Spin research isn’t available right now.");
  if (!resp.ok) throw new Error(`POST /books/{id}/spin-research: HTTP ${resp.status}`);
  return safeSpinResearchResponse(await resp.json());
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

function safeCuratedBook(value: unknown): CuratedBook | null {
  const book = record(value);
  if (!book) return null;
  const documentId = nonEmptyString(book.document_id);
  if (!documentId) return null;
  return {
    document_id: documentId,
    title: nullableString(book.title),
    author: nullableString(book.author),
    score: nonNegativeFiniteNumber(book.score) ?? 0,
  };
}

function safeCurateResponse(value: unknown, fallbackPrompt: string): CurateResponse {
  const body = record(value);
  const books = Array.isArray(body?.books)
    ? body.books.flatMap((item) => {
        const book = safeCuratedBook(item);
        return book ? [book] : [];
      })
    : [];
  return {
    prompt: nonEmptyString(body?.prompt) ?? fallbackPrompt,
    books,
  };
}

/** Prompt-to-curate (Read SPR-04). Ranks ONLY servable books by relevance
 * to the prompt — a gated book is never curated into a readable list.
 * Returns 503 if the embedding model isn't available server-side. */
export async function curateBooks(prompt: string, limit = 20): Promise<CurateResponse> {
  const resolvedPrompt = requireNonEmptyRequestString(prompt, "prompt");
  assertPositiveSafeInteger(limit, "limit");
  const params = new URLSearchParams({ prompt: resolvedPrompt, limit: String(limit) });
  const resp = await apiFetch(`${API_BASE}/books/curate?${params.toString()}`);
  if (resp.status === 503) throw new Error("Curation is temporarily unavailable.");
  if (!resp.ok) throw new Error(`GET /books/curate: HTTP ${resp.status}`);
  return safeCurateResponse(await resp.json(), resolvedPrompt);
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
  answer: string;
  citations: BookCitation[];
  /** False when the book had no extractable text to ground on (scanned-image
   * PDF / fully-withheld) — an honest no-context answer, never a hallucination. */
  grounded: boolean;
  context_chunk_count: number;
}

function sanitizeBookCitation(value: unknown): BookCitation | null {
  const citation = record(value);
  if (!citation) return null;
  const chunkId = nonEmptyString(citation.chunk_id);
  const documentId = nonEmptyString(citation.document_id);
  if (!chunkId || !documentId) return null;
  const pageIndex = nonNegativeSafeInteger(citation.page_index);
  const pageResolved = citation.page_resolved === true && pageIndex !== null;
  return {
    chunk_id: chunkId,
    document_id: documentId,
    page_index: pageResolved ? pageIndex : null,
    page_resolved: pageResolved,
    snippet: typeof citation.snippet === "string" ? citation.snippet.trim() : "",
  };
}

function sanitizeBookCitations(value: unknown): BookCitation[] {
  if (!Array.isArray(value)) return [];
  return value.flatMap((item) => {
    const citation = sanitizeBookCitation(item);
    return citation ? [citation] : [];
  });
}

function sanitizeTalkHistory(value: unknown): TalkTurn[] {
  if (!Array.isArray(value)) return [];
  return value.flatMap((item) => {
    const turn = record(item);
    const question = nonEmptyString(turn?.question);
    const answer = nonEmptyString(turn?.answer);
    return question && answer ? [{ question, answer }] : [];
  });
}

function safeResearchTier(value: unknown): "fast" | "deep" {
  return value === "fast" ? "fast" : "deep";
}

function safeAskBookResponse(value: unknown): AskBookResponse {
  const body = record(value);
  const answer = body ? nonEmptyString(body.answer) : null;
  if (!body || !answer) {
    throw new Error("Malformed talk-to-book response.");
  }
  return {
    answer,
    citations: sanitizeBookCitations(body.citations),
    grounded: body.grounded === true,
    context_chunk_count: nonNegativeSafeInteger(body.context_chunk_count) ?? 0,
  };
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
  const resolvedDocumentId = requireNonEmptyRequestString(documentId, "documentId");
  const resolvedQuestion = requireNonEmptyRequestString(question, "question");
  const history = sanitizeTalkHistory(opts?.history);
  const researchTier = safeResearchTier(opts?.researchTier);
  const resp = await apiFetch(`${API_BASE}/books/${encodeURIComponent(resolvedDocumentId)}/ask`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      question: resolvedQuestion,
      history,
      research_tier: researchTier,
    }),
  });
  if (resp.status === 404) throw new Error("book_not_found");
  if (resp.status === 503) throw new Error("Talk-to-book isn’t available right now.");
  if (!resp.ok) throw new Error(`POST /books/{id}/ask: HTTP ${resp.status}`);
  return safeAskBookResponse(await resp.json());
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

function safeLengthUnit(value: unknown): "pages" | "minutes" {
  return value === "minutes" ? "minutes" : "pages";
}

function safeCorpusScope(value: unknown): "hard" | "soft" {
  return value === "soft" ? "soft" : "hard";
}

function safeMetaReadingResponse(value: unknown): MetaReadingResponse {
  const body = record(value);
  const assetId = body ? nonEmptyString(body.asset_id) : null;
  const report = body ? nonEmptyString(body.report) : null;
  if (!body || !assetId || !report) {
    throw new Error("Malformed meta-reading response.");
  }
  return {
    asset_id: assetId,
    report,
    citations: sanitizeBookCitations(body.citations),
    length_unit: safeLengthUnit(body.length_unit),
    length_amount: nonNegativeSafeInteger(body.length_amount) ?? 0,
    word_budget: nonNegativeSafeInteger(body.word_budget) ?? 0,
    truncated: body.truncated === true,
    corpus_scope: safeCorpusScope(body.corpus_scope),
    corpus_document_ids: safeStringArray(body.corpus_document_ids),
    empty: body.empty === true,
    context_chunk_count: nonNegativeSafeInteger(body.context_chunk_count) ?? 0,
  };
}

/** Generate + save a meta-reading deliverable over the owned corpus (Read
 * SPR-08 M4). 422 when the length is degenerate (stated bound). 503 when the
 * model / embedding is unavailable. */
export async function generateMetaReading(
  req: MetaReadingRequest,
): Promise<MetaReadingResponse> {
  const body: MetaReadingRequest = {
    prompt: requireNonEmptyRequestString(req.prompt, "prompt"),
    length_unit: req.length_unit === "minutes" ? "minutes" : "pages",
    length_amount: req.length_amount,
    research_tier: req.research_tier === "fast" ? "fast" : "deep",
    corpus_scope: req.corpus_scope === "soft" ? "soft" : "hard",
  };
  assertPositiveSafeInteger(body.length_amount, "length_amount");
  const documentIds = sanitizeOptionalRequestStringArray(req.document_ids);
  if (documentIds) body.document_ids = documentIds;
  const resp = await apiFetch(`${API_BASE}/corpus/meta-reading`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (resp.status === 422) {
    const body = record(await resp.json().catch(() => null));
    throw new Error(nonEmptyString(body?.detail) ?? "Invalid length.");
  }
  if (resp.status === 503) throw new Error("Meta-reading isn’t available right now.");
  if (!resp.ok) throw new Error(`POST /corpus/meta-reading: HTTP ${resp.status}`);
  return safeMetaReadingResponse(await resp.json());
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

function safePersonalAsset(value: unknown): PersonalAsset | null {
  const asset = record(value);
  if (!asset) return null;
  const assetId = nonEmptyString(asset.asset_id);
  const title = nonEmptyString(asset.title);
  const kind = asset.kind === "saved_read" ? "saved_read" : "meta_reading";
  const documentIds = safeStringArray(asset.document_ids);
  const openRoute = canonicalPersonalOpenRoute(
    kind,
    nonEmptyString(asset.open_route),
    documentIds,
  );
  if (!assetId || !title || !openRoute) return null;
  return {
    asset_id: assetId,
    kind,
    title,
    prompt: nullableString(asset.prompt),
    document_ids: documentIds,
    emitted_at: nullableString(asset.emitted_at),
    open_route: openRoute,
  };
}

function canonicalPersonalOpenRoute(
  kind: PersonalAsset["kind"],
  openRoute: string | null,
  documentIds: string[],
): string | null {
  if (kind === "saved_read") {
    const documentId = documentIds[0];
    if (documentId) return `/read/${encodeURIComponent(documentId)}`;
    const match = openRoute?.match(/^\/read\/([^/?#]+)(?:[?#].*)?$/);
    if (!match || match[1] === "meta-reading" || match[1] === "meta") return null;
    try {
      return `/read/${encodeURIComponent(decodeURIComponent(match[1]))}`;
    } catch {
      return null;
    }
  }

  if (!openRoute) return null;
  if (openRoute === "/read/meta-reading" || openRoute.startsWith("/read/meta-reading/")) {
    return openRoute;
  }
  if (openRoute === "/read/meta" || openRoute.startsWith("/read/meta/")) {
    return openRoute.replace(/^\/read\/meta/, "/read/meta-reading");
  }
  if (openRoute.startsWith("/write/")) return openRoute;
  return null;
}

function safePersonalSpaceResponse(value: unknown): PersonalSpaceResponse {
  const body = record(value);
  const assets = Array.isArray(body?.assets)
    ? body.assets.flatMap((item) => {
        const asset = safePersonalAsset(item);
        return asset ? [asset] : [];
      })
    : [];
  return {
    assets,
    count: nonNegativeSafeInteger(body?.count) ?? assets.length,
  };
}

/** List the personal-space assets (Read SPR-13 M1), newest first. Substrate-
 * backed (event-log scan), not a new store. */
export async function listPersonalSpace(): Promise<PersonalSpaceResponse> {
  const resp = await apiFetch(`${API_BASE}/meta-readings`);
  if (!resp.ok) throw new Error(`GET /meta-readings: HTTP ${resp.status}`);
  return safePersonalSpaceResponse(await resp.json());
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

function safeAssetCategory(value: unknown): AssetCategory | null {
  const category = record(value);
  if (!category) return null;
  const categoryId = nonEmptyString(category.category_id);
  const label = nonEmptyString(category.label);
  if (!categoryId || !label) return null;
  return {
    category_id: categoryId,
    label,
    asset_ids: safeStringArray(category.asset_ids),
    ordering: category.ordering === "theme" ? "theme" : "recency",
  };
}

function safeCategorizedSpaceResponse(value: unknown): CategorizedSpaceResponse {
  const body = record(value);
  const categories = Array.isArray(body?.categories)
    ? body.categories.flatMap((item) => {
        const category = safeAssetCategory(item);
        return category ? [category] : [];
      })
    : [];
  return {
    categories,
    ordering: body?.ordering === "theme" ? "theme" : "recency",
    stability_bound: nonNegativeSafeInteger(body?.stability_bound) ?? 0,
  };
}

/** Cluster the personal-space assets into SYSTEM-named categories (Read SPR-13
 * M2). The system names the categories; the user never hand-organizes folders.
 * Honest recency fallback below the stability bound. */
export async function listPersonalSpaceCategories(): Promise<CategorizedSpaceResponse> {
  const resp = await apiFetch(`${API_BASE}/meta-readings/categories`);
  if (!resp.ok) throw new Error(`GET /meta-readings/categories: HTTP ${resp.status}`);
  return safeCategorizedSpaceResponse(await resp.json());
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

function safeProjectMatch(value: unknown): ProjectMatch | null {
  const match = record(value);
  if (!match) return null;
  const investigationId = nonEmptyString(match.investigation_id);
  const question = nonEmptyString(match.question);
  if (!investigationId || !question) return null;
  return {
    investigation_id: investigationId,
    question,
    score: nonNegativeFiniteNumber(match.score) ?? 0,
  };
}

function safeFileSuggestionResponse(
  value: unknown,
  fallbackDocumentId: string,
): FileSuggestionResponse {
  const body = record(value);
  const matches = Array.isArray(body?.matches)
    ? body.matches.flatMap((item) => {
        const match = safeProjectMatch(item);
        return match ? [match] : [];
      })
    : [];
  const uniqueMatches = matches.filter(
    (match, index, list) =>
      list.findIndex((candidate) => candidate.investigation_id === match.investigation_id) === index,
  );
  return {
    document_id: nonEmptyString(body?.document_id) ?? fallbackDocumentId,
    matches: uniqueMatches,
  };
}

/** Ask which research projects a doc could be filed into (Read SPR-13 M3).
 * SUGGEST-ONLY — this only ranks; filing is the explicit-accept event. 503 when
 * the embedder is unavailable (the surface then shows no suggestion). */
export async function getFileSuggestion(
  documentId: string,
): Promise<FileSuggestionResponse> {
  const resolvedDocumentId = requireNonEmptyRequestString(documentId, "documentId");
  const params = new URLSearchParams({ document_id: resolvedDocumentId });
  const resp = await apiFetch(`${API_BASE}/meta-readings/file-suggestion?${params.toString()}`);
  if (resp.status === 503) {
    // Embedder unavailable — no suggestion, not an error the surface surfaces.
    return { document_id: resolvedDocumentId, matches: [] };
  }
  if (!resp.ok) throw new Error(`GET /meta-readings/file-suggestion: HTTP ${resp.status}`);
  return safeFileSuggestionResponse(await resp.json(), resolvedDocumentId);
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

function safeSavedMetaReading(value: unknown): SavedMetaReading {
  const body = record(value);
  const assetId = body ? nonEmptyString(body.asset_id) : null;
  const prompt = body ? nonEmptyString(body.prompt) : null;
  const report = body ? nonEmptyString(body.report) : null;
  if (!body || !assetId || !prompt || !report) {
    throw new Error("Malformed saved meta-reading response.");
  }
  return {
    asset_id: assetId,
    prompt,
    report,
    citations: sanitizeBookCitations(body.citations),
    length_unit: safeLengthUnit(body.length_unit),
    length_amount: nonNegativeSafeInteger(body.length_amount) ?? 0,
    truncated: body.truncated === true,
    corpus_scope: safeCorpusScope(body.corpus_scope),
    corpus_document_ids: safeStringArray(body.corpus_document_ids),
  };
}

/** Re-open a saved meta-reading asset by id (Read SPR-13 M1 — opens back into
 * the meta-doc view). Reads the saved event off the log. */
export async function getSavedMetaReading(assetId: string): Promise<SavedMetaReading> {
  const resolvedAssetId = requireNonEmptyRequestString(assetId, "assetId");
  const resp = await apiFetch(`${API_BASE}/meta-readings/${encodeURIComponent(resolvedAssetId)}`);
  if (resp.status === 404) throw new Error(`Saved reading ${resolvedAssetId} not found.`);
  if (!resp.ok) throw new Error(`GET /meta-readings/{id}: HTTP ${resp.status}`);
  return safeSavedMetaReading(await resp.json());
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
