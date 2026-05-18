// REST + WebSocket client for the Antiek substrate.
//
// All typed payloads come from the codegen output. There is NO local
// schema definition; if a payload field changes in Python, the codegen
// gate fails CI and the TS side breaks at the type level.

import type { Event, TypedPayload } from "../generated/types";

// Mirrors the FastAPI response model. Not in substrate/schemas because
// this is an API-layer concern (the typed event itself is what gets
// emitted; this is only the response wrapper). Keep these field names
// in sync with interfaces/research/api/app.py:EmittedEventResponse.
export interface EmittedEventResponse {
  event_id: string;
  action_type: string;
}

// In development, vite.config.ts proxies /events, /trajectory, /ws,
// /health, /investigations, /chunks to localhost:8000. In production
// the app at app.antiek.ai needs to hit api.antiek.ai explicitly.
//
// Set via VITE_API_BASE_URL at build time (Cloudflare Pages: configure
// in the project's environment variables). Empty string falls back to
// same-origin (dev-server proxy behavior).
const API_BASE = (import.meta.env.VITE_API_BASE_URL as string | undefined) ?? "";

// Auth (H4.5): the web app does NOT carry a bearer token. The
// substrate is gated by Cloudflare Access (configured on
// app.antiek.ai + api.antiek.ai in the same Access application).
// When the operator visits app.antiek.ai, Cloudflare prompts for
// authentication, sets a signed JWT cookie, and AUTOMATICALLY
// injects ``Cf-Access-Authenticated-User-Email`` into requests
// from the authenticated browser to any host in the same Access
// application.
//
// The substrate's middleware reads that header and matches against
// ``ANTIEK_OPERATOR_EMAIL``. No build-time secret; no token in
// the JS bundle.
//
// ``credentials: "include"`` is load-bearing: without it,
// Cloudflare's session cookie does NOT travel cross-origin
// (app.antiek.ai → api.antiek.ai) and every request 401s.
//
// Bearer tokens (``ANTIEK_OPERATOR_TOKEN``) still exist server-side
// for machine callers (smoke runs, probes, CI). Those carry the
// bearer directly. The web app uses neither.

/** Merge caller-supplied headers; auth comes via Cloudflare cookie. */
function authHeaders(extra?: HeadersInit): Record<string, string> {
  const merged: Record<string, string> = {};
  if (extra) {
    if (extra instanceof Headers) {
      extra.forEach((v, k) => { merged[k] = v; });
    } else if (Array.isArray(extra)) {
      for (const [k, v] of extra) merged[k] = v;
    } else {
      Object.assign(merged, extra);
    }
  }
  return merged;
}

/** ``fetch`` wrapper that sends Cloudflare Access cookies. */
function apiFetch(input: RequestInfo | URL, init?: RequestInit): Promise<Response> {
  return fetch(input, {
    ...(init ?? {}),
    headers: authHeaders(init?.headers),
    credentials: "include",
  });
}

// EmittedEventResponse is generated but exported through types; redeclare
// the request envelope here since it lives in the API layer, not in the
// substrate schemas.
export interface TypedEventEnvelope {
  investigation_id: string;
  payload: TypedPayload;
  document_id?: string;
  synthesis_id?: string;
  phase?: number;
  role?: string;
  policy_id?: string;
  parent_event_id?: string;
}

export class ApiError extends Error {
  constructor(
    message: string,
    public readonly status: number,
    public readonly body: string,
  ) {
    super(message);
  }
}

export async function postTypedEvent(
  envelope: TypedEventEnvelope,
): Promise<EmittedEventResponse> {
  const resp = await apiFetch(`${API_BASE}/events/typed`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(envelope),
  });
  if (!resp.ok) {
    const body = await resp.text();
    throw new ApiError(
      `POST /events/typed failed: HTTP ${resp.status}`,
      resp.status,
      body,
    );
  }
  return resp.json();
}

export async function getTrajectory(
  investigationId: string,
  limit?: number,
): Promise<{ investigation_id: string; count: number; events: Event[] }> {
  const url = new URL(
    `${API_BASE}/trajectory/${encodeURIComponent(investigationId)}`,
    window.location.origin,
  );
  if (limit !== undefined) {
    url.searchParams.set("limit", String(limit));
  }
  const resp = await apiFetch(url.toString());
  if (!resp.ok) {
    throw new ApiError(
      `GET /trajectory failed: HTTP ${resp.status}`,
      resp.status,
      await resp.text(),
    );
  }
  return resp.json();
}

export async function getHealth(): Promise<{
  status: string;
  param_version: string;
  schema_version: number;
  subscriber_count: number;
  registered_providers?: string[];
}> {
  const resp = await apiFetch(`${API_BASE}/health`);
  if (!resp.ok) {
    throw new ApiError("GET /health failed", resp.status, await resp.text());
  }
  return resp.json();
}

// ── Sprint 11: investigations + chunks ─────────────────────────────

export interface StartInvestigationRequest {
  question: string;
  context?: string;
  topic_slug?: string;
  parent_investigation_id?: string;
  spawn_context?: string;
  max_sub_questions?: number;
  investigation_id?: string;
}

export interface StartInvestigationResponse {
  investigation_id: string;
  status: string;
  start_event_id: string;
}

/** POST /investigations — kick off a cold research investigation. */
export async function startInvestigation(
  req: StartInvestigationRequest,
): Promise<StartInvestigationResponse> {
  const resp = await apiFetch(`${API_BASE}/investigations`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(req),
  });
  if (!resp.ok) {
    throw new ApiError(
      `POST /investigations failed: HTTP ${resp.status}`,
      resp.status,
      await resp.text(),
    );
  }
  return resp.json();
}

export interface InvestigationSummary {
  investigation_id: string;
  question: string | null;
  status: "in_progress" | "completed" | "failed" | "not_found";
  started_at: string | null;
  completed_at: string | null;
  cost_usd_total: number;
  parent_investigation_id: string | null;
}

/** GET /investigations — list past investigations for the sidebar. */
export async function listInvestigations(opts?: {
  limit?: number;
  status?: "in_progress" | "completed" | "failed";
}): Promise<{ count: number; investigations: InvestigationSummary[] }> {
  const url = new URL(`${API_BASE}/investigations`, window.location.origin);
  if (opts?.limit !== undefined) url.searchParams.set("limit", String(opts.limit));
  if (opts?.status !== undefined) url.searchParams.set("status", opts.status);
  const resp = await apiFetch(url.toString());
  if (!resp.ok) {
    throw new ApiError(
      `GET /investigations failed: HTTP ${resp.status}`,
      resp.status,
      await resp.text(),
    );
  }
  return resp.json();
}

export interface InvestigationStatus {
  investigation_id: string;
  status: "in_progress" | "completed" | "failed" | "not_found";
  current_phase: number | null;
  last_delivered_action_type: string | null;
  terminal_payload: Record<string, unknown> | null;
}

/** GET /investigations/{id} — fetch terminal-state status. */
export async function getInvestigationStatus(
  investigationId: string,
): Promise<InvestigationStatus> {
  const resp = await apiFetch(
    `${API_BASE}/investigations/${encodeURIComponent(investigationId)}`,
  );
  if (!resp.ok) {
    throw new ApiError(
      `GET /investigations/{id} failed: HTTP ${resp.status}`,
      resp.status,
      await resp.text(),
    );
  }
  return resp.json();
}

export interface ChunkResponse {
  chunk_id: string;
  text: string;
  section_path: string | null;
  token_count: number;
  document_id: string;
  document_title: string | null;
  source_tier: number;
}

// ── Sprint 12: source ingest ───────────────────────────────────────

export type SourceKind = "arxiv" | "youtube" | "podcast" | "url";

export interface IngestSourceRequest {
  url: string;
  kind?: SourceKind;
  investigation_id?: string;
  source_tier?: number;
  max_episodes?: number;
}

export interface IngestSourceResponse {
  status: "ingested" | "skipped" | "error";
  detected_kind: string;
  document_id: string | null;
  document_loaded_event_id: string | null;
  chunks_written: number;
  skipped_reason: string | null;
  error_message: string | null;
  title: string | null;
  episodes_processed: number;
  episodes_ingested: number;
}

// ── Sprint 13: deliverables (creation surface) ─────────────────────

export type DeliverableKind =
  | "research_memo"
  | "book_chapter"
  | "biography_section"
  | "investor_brief"
  | "general_essay";

export type BlockKind =
  | "insight"
  | "open_question"
  | "operator_note"
  | "claim";

export interface DeliverableSummary {
  deliverable_id: string;
  title: string;
  deliverable_kind: DeliverableKind;
  investigation_root_id: string | null;
  status: string;
  created_at: string | null;
  updated_at: string | null;
  section_count: number;
}

export interface SectionResponse {
  section_id: string;
  deliverable_id: string;
  parent_section_id: string | null;
  section_index: number;
  title: string | null;
  prose_text: string | null;
  prose_provenance: Record<string, string[]> | null;
  block_count: number;
}

export interface DeliverableDetailResponse {
  deliverable_id: string;
  title: string;
  deliverable_kind: DeliverableKind;
  status: string;
  sections: SectionResponse[];
}

export async function createDeliverable(req: {
  title: string;
  deliverable_kind: DeliverableKind;
  investigation_root_id?: string;
}): Promise<DeliverableSummary> {
  const resp = await apiFetch(`${API_BASE}/deliverables`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(req),
  });
  if (!resp.ok) {
    throw new ApiError(
      `POST /deliverables failed: HTTP ${resp.status}`,
      resp.status,
      await resp.text(),
    );
  }
  return resp.json();
}

export async function listDeliverables(): Promise<{
  count: number;
  deliverables: DeliverableSummary[];
}> {
  const resp = await apiFetch(`${API_BASE}/deliverables`);
  if (!resp.ok) {
    throw new ApiError(
      `GET /deliverables failed: HTTP ${resp.status}`,
      resp.status,
      await resp.text(),
    );
  }
  return resp.json();
}

export async function getDeliverable(
  id: string,
): Promise<DeliverableDetailResponse> {
  const resp = await apiFetch(
    `${API_BASE}/deliverables/${encodeURIComponent(id)}`,
  );
  if (!resp.ok) {
    throw new ApiError(
      `GET /deliverables/{id} failed: HTTP ${resp.status}`,
      resp.status,
      await resp.text(),
    );
  }
  return resp.json();
}

export async function createSection(req: {
  deliverable_id: string;
  section_index: number;
  title?: string;
  parent_section_id?: string;
}): Promise<SectionResponse> {
  const resp = await apiFetch(`${API_BASE}/sections`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(req),
  });
  if (!resp.ok) {
    throw new ApiError(
      `POST /sections failed: HTTP ${resp.status}`,
      resp.status,
      await resp.text(),
    );
  }
  return resp.json();
}

export async function attachBlock(req: {
  section_id: string;
  block_kind: BlockKind;
  block_id: string;
  block_index: number;
}): Promise<void> {
  const resp = await apiFetch(`${API_BASE}/sections/attach-block`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(req),
  });
  if (!resp.ok) {
    throw new ApiError(
      `POST /sections/attach-block failed: HTTP ${resp.status}`,
      resp.status,
      await resp.text(),
    );
  }
}

// ── Sprint 14: block search + reorder ──────────────────────────────

export interface BlockSearchHit {
  block_id: string;
  block_kind: BlockKind;
  label: string;
  body: string;
  source_tier: number | null;
  document_title: string | null;
}

export async function searchBlocks(
  q: string,
  limit = 20,
): Promise<{ count: number; hits: BlockSearchHit[] }> {
  const url = new URL(`${API_BASE}/blocks/search`, window.location.origin);
  url.searchParams.set("q", q);
  url.searchParams.set("limit", String(limit));
  const resp = await apiFetch(url.toString());
  if (!resp.ok) {
    throw new ApiError(
      `GET /blocks/search failed: HTTP ${resp.status}`,
      resp.status,
      await resp.text(),
    );
  }
  return resp.json();
}

export async function reorderBlock(req: {
  section_id: string;
  block_kind: BlockKind;
  block_id: string;
  new_section_id?: string;
  new_block_index: number;
}): Promise<void> {
  const resp = await apiFetch(`${API_BASE}/sections/reorder-block`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(req),
  });
  if (!resp.ok) {
    throw new ApiError(
      `POST /sections/reorder-block failed: HTTP ${resp.status}`,
      resp.status,
      await resp.text(),
    );
  }
}

// ── Sprint 15: prose update + export ───────────────────────────────

export interface UpdateSectionProseRequest {
  prose_text: string;
  original_text?: string;
  promote_to_graph?: boolean;
  cited_chunk_ids?: string[];
  investigation_id?: string;
}

export interface UpdateSectionProseResponse {
  status: "saved" | "saved_and_promoted";
  section_id: string;
  claim_node_id: string | null;
  claim_event_id: string | null;
}

export async function updateSectionProse(
  sectionId: string,
  req: UpdateSectionProseRequest,
): Promise<UpdateSectionProseResponse> {
  const resp = await apiFetch(
    `${API_BASE}/sections/${encodeURIComponent(sectionId)}/prose`,
    {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(req),
    },
  );
  if (!resp.ok) {
    throw new ApiError(
      `PATCH /sections/{id}/prose failed: HTTP ${resp.status}`,
      resp.status,
      await resp.text(),
    );
  }
  return resp.json();
}

export type ExportFormatName = "markdown" | "html" | "json";

export interface ExportFormatResponse {
  format: ExportFormatName;
  content: string;
  filename: string;
}

export async function exportDeliverable(
  id: string,
  format: ExportFormatName,
): Promise<ExportFormatResponse> {
  const url = new URL(
    `${API_BASE}/deliverables/${encodeURIComponent(id)}/export`,
    window.location.origin,
  );
  url.searchParams.set("format", format);
  const resp = await apiFetch(url.toString());
  if (!resp.ok) {
    throw new ApiError(
      `GET /deliverables/{id}/export failed: HTTP ${resp.status}`,
      resp.status,
      await resp.text(),
    );
  }
  return resp.json();
}

// ── Sprint 13: voice notes ─────────────────────────────────────────

export interface VoiceNoteIngestRequest {
  transcript: string;
  investigation_id?: string;
  title?: string;
  duration_seconds?: number;
  language?: string;
}

export interface VoiceNoteIngestResponse {
  status: "ingested" | "skipped";
  document_id: string;
  document_loaded_event_id: string | null;
  chunks_written: number;
  skipped_reason: string | null;
  title: string | null;
}

export async function ingestVoiceNote(
  req: VoiceNoteIngestRequest,
): Promise<VoiceNoteIngestResponse> {
  const resp = await apiFetch(`${API_BASE}/voice-notes/ingest`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(req),
  });
  if (!resp.ok) {
    throw new ApiError(
      `POST /voice-notes/ingest failed: HTTP ${resp.status}`,
      resp.status,
      await resp.text(),
    );
  }
  return resp.json();
}

/** POST /sources/ingest — add a URL to the substrate graph. */
export async function ingestSource(
  req: IngestSourceRequest,
): Promise<IngestSourceResponse> {
  const resp = await apiFetch(`${API_BASE}/sources/ingest`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(req),
  });
  if (!resp.ok) {
    throw new ApiError(
      `POST /sources/ingest failed: HTTP ${resp.status}`,
      resp.status,
      await resp.text(),
    );
  }
  return resp.json();
}

/** GET /chunks/{id} — used by Mode A's claim hover modal. */
export async function getChunk(chunkId: string): Promise<ChunkResponse> {
  const resp = await apiFetch(
    `${API_BASE}/chunks/${encodeURIComponent(chunkId)}`,
  );
  if (!resp.ok) {
    throw new ApiError(
      `GET /chunks/{id} failed: HTTP ${resp.status}`,
      resp.status,
      await resp.text(),
    );
  }
  return resp.json();
}
