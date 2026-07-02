// REST + WebSocket client for the Antiek substrate.
//
// All typed payloads come from the codegen output. There is NO local
// schema definition; if a payload field changes in Python, the codegen
// gate fails CI and the TS side breaks at the type level.

import type { Event, TypedPayload } from "../generated/types";
import { isEventFrame } from "./eventFrame";

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
export const API_BASE = (import.meta.env.VITE_API_BASE_URL as string | undefined) ?? "";

// Auth: the reading app uses Antiek-issued magic-link sessions, not a
// bearer token in the JS bundle.
//
//   POST /auth/request   → email with sign-in link (Resend / AgentMail)
//   GET  /auth/callback  → 302 + Set-Cookie ANTIEK_SESSION on api host
//   GET  /auth/me        → session identity when cookie is valid
//
// ``credentials: "include"`` is load-bearing: without it, the session
// cookie does NOT travel cross-origin (antiek.ai → api.antiek.ai) and
// authenticated API calls 401.
//
// Bearer tokens (``ANTIEK_OPERATOR_TOKEN``) still exist server-side for
// machine callers (smoke runs, probes, CI). The web app uses neither.

/** Merge caller-supplied headers; session auth is cookie-based. */
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

/** ``fetch`` wrapper that sends session cookies (``credentials: include``).
 * Exported for new mode components that need direct API access
 * outside the typed helper functions (e.g. OperatorDashboard,
 * PrivacyDashboard, Notebook). */
export function apiFetch(input: RequestInfo | URL, init?: RequestInit): Promise<Response> {
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

function malformedApiResponse(message: string): ApiError {
  return new ApiError(message, 502, "");
}

function requireApiString(value: unknown, field: string): string {
  const text = nonEmptyString(value);
  if (!text) throw malformedApiResponse(`Malformed API response: ${field}`);
  return text;
}

function safeEmittedEventResponse(value: unknown): EmittedEventResponse {
  const body = record(value);
  if (!body) throw malformedApiResponse("Malformed API response: body");
  return {
    event_id: requireApiString(body.event_id, "event_id"),
    action_type: requireApiString(body.action_type, "action_type"),
  };
}

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

function requireRequestString(value: unknown, field: string): string {
  const text = nonEmptyString(value);
  if (!text) throw new TypeError(`${field} must be a non-empty string`);
  return text;
}

function optionalRequestString(value: unknown): string | undefined {
  return nonEmptyString(value) ?? undefined;
}

function sanitizeTypedEventEnvelope(envelope: TypedEventEnvelope): TypedEventEnvelope {
  if (!record(envelope.payload)) {
    throw new TypeError("payload must be an object");
  }
  if (envelope.phase !== undefined) {
    assertNonNegativeSafeInteger(envelope.phase, "phase");
  }
  const documentId = optionalRequestString(envelope.document_id);
  const synthesisId = optionalRequestString(envelope.synthesis_id);
  const role = optionalRequestString(envelope.role);
  const policyId = optionalRequestString(envelope.policy_id);
  const parentEventId = optionalRequestString(envelope.parent_event_id);
  return {
    investigation_id: requireRequestString(envelope.investigation_id, "investigation_id"),
    payload: envelope.payload,
    ...(documentId ? { document_id: documentId } : {}),
    ...(synthesisId ? { synthesis_id: synthesisId } : {}),
    ...(envelope.phase !== undefined ? { phase: envelope.phase } : {}),
    ...(role ? { role } : {}),
    ...(policyId ? { policy_id: policyId } : {}),
    ...(parentEventId ? { parent_event_id: parentEventId } : {}),
  };
}

export async function postTypedEvent(
  envelope: TypedEventEnvelope,
): Promise<EmittedEventResponse> {
  const body = sanitizeTypedEventEnvelope(envelope);
  const resp = await apiFetch(`${API_BASE}/events/typed`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!resp.ok) {
    const body = await resp.text();
    throw new ApiError(
      `POST /events/typed failed: HTTP ${resp.status}`,
      resp.status,
      body,
    );
  }
  return safeEmittedEventResponse(await resp.json());
}

export interface AIUndoRequest {
  event_id: string;
  investigation_id: string;
}

export async function undoAiAction(
  req: AIUndoRequest,
): Promise<EmittedEventResponse> {
  const body = {
    event_id: requireRequestString(req.event_id, "event_id"),
    investigation_id: requireRequestString(req.investigation_id, "investigation_id"),
  };
  const resp = await apiFetch(`${API_BASE}/ai/undo`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!resp.ok) {
    const body = await resp.text();
    throw new ApiError(
      `POST /ai/undo failed: HTTP ${resp.status}`,
      resp.status,
      body,
    );
  }
  return safeEmittedEventResponse(await resp.json());
}

export async function getTrajectory(
  investigationId: string,
  limit?: number,
): Promise<{ investigation_id: string; count: number; events: Event[] }> {
  const resolvedInvestigationId = requireRequestString(investigationId, "investigationId");
  const url = new URL(
    `${API_BASE}/trajectory/${encodeURIComponent(resolvedInvestigationId)}`,
    window.location.origin,
  );
  if (limit !== undefined) {
    assertPositiveSafeInteger(limit, "limit");
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
  return safeTrajectoryResponse(await resp.json(), resolvedInvestigationId);
}

function safeTrajectoryResponse(
  value: unknown,
  fallbackInvestigationId: string,
): { investigation_id: string; count: number; events: Event[] } {
  const body = record(value);
  const events = Array.isArray(body?.events)
    ? body.events.filter(isEventFrame)
    : [];
  return {
    investigation_id:
      nonEmptyString(body?.investigation_id) ?? fallbackInvestigationId,
    count: nonNegativeInteger(body?.count) ?? events.length,
    events,
  };
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
  return safeHealthResponse(await resp.json());
}

function safeHealthResponse(value: unknown): {
  status: string;
  param_version: string;
  schema_version: number;
  subscriber_count: number;
  registered_providers?: string[];
} {
  const body = record(value);
  const providers = Array.isArray(body?.registered_providers)
    ? body.registered_providers.flatMap((item) => {
        const provider = nonEmptyString(item);
        return provider ? [provider] : [];
      })
    : undefined;
  return {
    status: nonEmptyString(body?.status) ?? "unknown",
    param_version: nonEmptyString(body?.param_version) ?? "",
    schema_version: nonNegativeInteger(body?.schema_version) ?? 0,
    subscriber_count: nonNegativeInteger(body?.subscriber_count) ?? 0,
    ...(providers ? { registered_providers: providers } : {}),
  };
}

// ── Sprint 11: investigations + chunks ─────────────────────────────

/**
 * SPR-01 M3 — the curated research tier. CLOSED two-value set offered ONLY
 * at the research entry (not a raw model dropdown anywhere). "fast" → MiMo
 * V2.5 Pro, "deep" → DeepSeek V4 Pro. The tier→provider map lives in ONE
 * place server-side (substrate/dispatch/research_tier.py); the client only
 * sends the chosen label. Mirrors the closed set in
 * substrate/dispatch/research_tier.py:RESEARCH_TIERS.
 */
export type ResearchTier = "fast" | "deep";

export interface StartInvestigationRequest {
  question: string;
  context?: string;
  topic_slug?: string;
  parent_investigation_id?: string;
  spawn_context?: string;
  max_sub_questions?: number;
  investigation_id?: string;
  /** Curated fast/deep tier; defaults server-side to "deep" when omitted. */
  research_tier?: ResearchTier;
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
  const body: StartInvestigationRequest = {
    question: requireRequestString(req.question, "question"),
  };
  const context = optionalRequestString(req.context);
  const topicSlug = optionalRequestString(req.topic_slug);
  const parentInvestigationId = optionalRequestString(req.parent_investigation_id);
  const spawnContext = optionalRequestString(req.spawn_context);
  const investigationId = optionalRequestString(req.investigation_id);
  if (context) body.context = context;
  if (topicSlug) body.topic_slug = topicSlug;
  if (parentInvestigationId) body.parent_investigation_id = parentInvestigationId;
  if (spawnContext) body.spawn_context = spawnContext;
  if (investigationId) body.investigation_id = investigationId;
  if (req.max_sub_questions !== undefined) {
    assertPositiveSafeInteger(req.max_sub_questions, "max_sub_questions");
    body.max_sub_questions = req.max_sub_questions;
  }
  if (req.research_tier === "fast" || req.research_tier === "deep") {
    body.research_tier = req.research_tier;
  }
  const resp = await apiFetch(`${API_BASE}/investigations`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!resp.ok) {
    throw new ApiError(
      `POST /investigations failed: HTTP ${resp.status}`,
      resp.status,
      await resp.text(),
    );
  }
  return safeStartInvestigationResponse(await resp.json());
}

export interface InvestigationSummary {
  investigation_id: string;
  question: string | null;
  status: "in_progress" | "completed" | "failed" | "stopped" | "not_found";
  started_at: string | null;
  completed_at: string | null;
  cost_usd_total: number;
  parent_investigation_id: string | null;
  /** SPR-09: true when the §7 continuous daemon spawned this research (its
   * start event carried the daemon's policy_id, translated to this boolean
   * server-side). The surface badges it "found by the loop"; the raw
   * policy_id is never sent. Optional for back-compat with older responses. */
  spawned_by_daemon?: boolean;
}

function safeInvestigationStatus(
  value: unknown,
): InvestigationSummary["status"] {
  return value === "in_progress" ||
    value === "completed" ||
    value === "failed" ||
    value === "stopped" ||
    value === "not_found"
    ? value
    : "failed";
}

function finiteNonNegativeNumber(value: unknown): number | null {
  const parsed =
    typeof value === "number"
      ? value
      : typeof value === "string" && value.trim() !== ""
        ? Number(value)
        : Number.NaN;
  return Number.isFinite(parsed) && parsed >= 0 ? parsed : null;
}

function safeInvestigationSummary(value: unknown): InvestigationSummary | null {
  const row = record(value);
  const investigationId = nonEmptyString(row?.investigation_id);
  if (!row || !investigationId) return null;
  return {
    investigation_id: investigationId,
    question: nullableString(row.question),
    status: safeInvestigationStatus(row.status),
    started_at: nullableString(row.started_at),
    completed_at: nullableString(row.completed_at),
    cost_usd_total: finiteNonNegativeNumber(row.cost_usd_total) ?? 0,
    parent_investigation_id: nullableString(row.parent_investigation_id),
    ...(typeof row.spawned_by_daemon === "boolean"
      ? { spawned_by_daemon: row.spawned_by_daemon }
      : {}),
  };
}

function safeInvestigationList(value: unknown): {
  count: number;
  investigations: InvestigationSummary[];
} {
  const body = record(value);
  const investigations = Array.isArray(body?.investigations)
    ? body.investigations.flatMap((item) => {
        const investigation = safeInvestigationSummary(item);
        return investigation ? [investigation] : [];
      })
    : [];
  return {
    count: nonNegativeInteger(body?.count) ?? investigations.length,
    investigations,
  };
}

/** GET /investigations — list past investigations for the sidebar. */
export async function listInvestigations(opts?: {
  limit?: number;
  status?: "in_progress" | "completed" | "failed";
}): Promise<{ count: number; investigations: InvestigationSummary[] }> {
  const url = new URL(`${API_BASE}/investigations`, window.location.origin);
  if (opts?.limit !== undefined) {
    assertPositiveSafeInteger(opts.limit, "limit");
    url.searchParams.set("limit", String(opts.limit));
  }
  if (opts?.status !== undefined) url.searchParams.set("status", opts.status);
  const resp = await apiFetch(url.toString());
  if (!resp.ok) {
    throw new ApiError(
      `GET /investigations failed: HTTP ${resp.status}`,
      resp.status,
      await resp.text(),
    );
  }
  return safeInvestigationList(await resp.json());
}

// ── Brainstorming Workstation — watch-for-later folder ──
//
// Mirrors interfaces/research/api/app.py ParkedQuestionEntry +
// WatchForLaterResponse. The folder is unsharpened
// question.identified events across all investigations. See
// master-spec §2.6 + §4.5.

export interface ParkedQuestionEntry {
  question_id: string;
  question_text: string;
  source_investigation_id: string;
  source_document_id: string | null;
  anchor_region_id: string | null;
  parked_at: string;
  parent_event_id: string | null;
}

function safeParkedQuestion(value: unknown): ParkedQuestionEntry | null {
  const row = record(value);
  if (!row) return null;
  const questionId = nonEmptyString(row.question_id);
  const questionText = nonEmptyString(row.question_text);
  const sourceInvestigationId = nonEmptyString(row.source_investigation_id);
  const parkedAt = nonEmptyString(row.parked_at);
  if (!questionId || !questionText || !sourceInvestigationId || !parkedAt) {
    return null;
  }
  return {
    question_id: questionId,
    question_text: questionText,
    source_investigation_id: sourceInvestigationId,
    source_document_id: nullableString(row.source_document_id),
    anchor_region_id: nullableString(row.anchor_region_id),
    parked_at: parkedAt,
    parent_event_id: nullableString(row.parent_event_id),
  };
}

function safeWatchForLaterList(value: unknown): {
  count: number;
  questions: ParkedQuestionEntry[];
} {
  const body = record(value);
  const rawQuestions = Array.isArray(body?.questions)
    ? body.questions
    : Array.isArray(body?.parked)
      ? body.parked
      : [];
  const questions = rawQuestions.flatMap((item) => {
    const question = safeParkedQuestion(item);
    return question ? [question] : [];
  });
  return {
    count: nonNegativeInteger(body?.count) ?? questions.length,
    questions,
  };
}

function safeStartInvestigationResponse(value: unknown): StartInvestigationResponse {
  const body = record(value);
  if (!body) throw malformedApiResponse("Malformed API response: body");
  return {
    investigation_id: requireApiString(body.investigation_id, "investigation_id"),
    status: nonEmptyString(body.status) ?? "in_progress",
    start_event_id: requireApiString(body.start_event_id, "start_event_id"),
  };
}

/** GET /watch-for-later — list unsharpened parked questions. */
export async function listWatchForLater(
  opts?: { limit?: number },
): Promise<{ count: number; questions: ParkedQuestionEntry[] }> {
  const url = new URL(`${API_BASE}/watch-for-later`, window.location.origin);
  if (opts?.limit !== undefined) {
    assertPositiveSafeInteger(opts.limit, "limit");
    url.searchParams.set("limit", String(opts.limit));
  }
  const resp = await apiFetch(url.toString());
  if (!resp.ok) {
    throw new ApiError(
      `GET /watch-for-later failed: HTTP ${resp.status}`,
      resp.status,
      await resp.text(),
    );
  }
  return safeWatchForLaterList(await resp.json());
}

/** POST /watch-for-later/{question_id}/launch — spawn investigation
 * seeded by the parked question. Returns the new investigation handle. */
export async function launchParkedQuestion(
  question_id: string,
): Promise<StartInvestigationResponse> {
  const resolvedQuestionId = requireRequestString(question_id, "question_id");
  const resp = await apiFetch(
    `${API_BASE}/watch-for-later/${encodeURIComponent(resolvedQuestionId)}/launch`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
    },
  );
  if (!resp.ok) {
    throw new ApiError(
      `POST /watch-for-later/{question_id}/launch failed: HTTP ${resp.status}`,
      resp.status,
      await resp.text(),
    );
  }
  return safeStartInvestigationResponse(await resp.json());
}

export interface ParkQuestionRequest {
  investigation_id: string;
  question_text: string;
  source_document_id?: string | null;
  anchor_region_id?: string | null;
  parent_event_id?: string | null;
}

export interface ParkQuestionResult extends EmittedEventResponse {
  question_id: string;
}

function newQuestionId(): string {
  const cryptoApi = globalThis.crypto;
  if (cryptoApi && "randomUUID" in cryptoApi) {
    return `q-${cryptoApi.randomUUID()}`;
  }
  return `q-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`;
}

/** POST /events/typed — park a question into the watch-for-later folder.
 * Watch-for-later is not a separate table; it is the set of unsharpened
 * question.identified events, so extensions from the thought-partner must
 * enter through the same typed-event boundary. */
export async function parkQuestionForLater(
  req: ParkQuestionRequest,
): Promise<ParkQuestionResult> {
  const investigationId = requireRequestString(req.investigation_id, "investigation_id");
  const questionText = requireRequestString(req.question_text, "question_text");
  const sourceDocumentId = optionalRequestString(req.source_document_id);
  const parentEventId = optionalRequestString(req.parent_event_id);
  const anchorRegionId = optionalRequestString(req.anchor_region_id);
  const question_id = newQuestionId();
  const emitted = await postTypedEvent({
    investigation_id: investigationId,
    document_id: sourceDocumentId,
    parent_event_id: parentEventId,
    role: "operator",
    policy_id: "operator/brainstorm",
    payload: {
      action_type: "question.identified",
      question_id,
      question_text: questionText,
      anchor_region_id: anchorRegionId ?? null,
    },
  });
  return { ...emitted, question_id };
}

// ── Notebook surface — Wedge 2 linchpin (master-spec §4.2) ──

export interface NotebookBlockShape {
  block_id: string;
  block_index: number;
  block_type: string;
  ref_id: string | null;
  content_json: Record<string, unknown>;
  created_at: string;
}

export interface NotebookShape {
  notebook_id: string;
  title: string;
  investigation_id: string | null;
  document_id: string | null;
  content_class: "user_owned" | "user_public_contribution";
  created_at: string;
  updated_at: string;
  blocks: NotebookBlockShape[];
}

const NOTEBOOK_BLOCK_TYPES = new Set<NotebookBlockShape["block_type"]>([
  "prose",
  "region_embed",
  "claim_card",
  "note",
  "question_card",
  "cross_doc_link",
  "chat_exchange",
  "master_md_section",
  "image",
  "latex",
]);

function requireNotebookBlockType(value: unknown): NotebookBlockShape["block_type"] {
  const blockType = requireRequestString(value, "block_type");
  if (!NOTEBOOK_BLOCK_TYPES.has(blockType as NotebookBlockShape["block_type"])) {
    throw new TypeError("block_type must be a supported notebook block type");
  }
  return blockType as NotebookBlockShape["block_type"];
}

function sanitizeAppendNotebookBlockRequest(req: {
  block_type: string;
  content: unknown;
  ref_id?: string | null;
}): { block_type: NotebookBlockShape["block_type"]; content: unknown; ref_id?: string } {
  const refId = optionalRequestString(req.ref_id);
  return {
    block_type: requireNotebookBlockType(req.block_type),
    content: req.content,
    ...(refId ? { ref_id: refId } : {}),
  };
}

function sanitizePatchNotebookBlockRequest(body: {
  content?: Record<string, unknown> | null;
  ref_id?: string | null;
  clear_ref_id?: boolean;
}): {
  content?: Record<string, unknown> | null;
  ref_id?: string;
  clear_ref_id?: boolean;
} {
  const refId = optionalRequestString(body.ref_id);
  return {
    ...(body.content !== undefined ? { content: body.content } : {}),
    ...(refId ? { ref_id: refId } : {}),
    ...(body.clear_ref_id !== undefined ? { clear_ref_id: body.clear_ref_id } : {}),
  };
}

function sanitizeOrderedBlockIds(orderedBlockIds: string[]): string[] {
  const resolvedIds = orderedBlockIds.map((blockId) =>
    requireRequestString(blockId, "ordered_block_ids"),
  );
  if (new Set(resolvedIds).size !== resolvedIds.length) {
    throw new TypeError("ordered_block_ids must not contain duplicates");
  }
  return resolvedIds;
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

function nonNegativeInteger(value: unknown): number | null {
  return typeof value === "number" && Number.isSafeInteger(value) && value >= 0
    ? value
    : null;
}

function safeNotebookBlock(value: unknown): NotebookBlockShape | null {
  const block = record(value);
  if (!block) return null;
  const blockId = nonEmptyString(block?.block_id);
  const blockType = nonEmptyString(block?.block_type);
  const blockIndex = nonNegativeInteger(block?.block_index);
  if (
    !blockId ||
    !blockType ||
    !NOTEBOOK_BLOCK_TYPES.has(blockType as NotebookBlockShape["block_type"]) ||
    blockIndex === null
  ) {
    return null;
  }
  return {
    block_id: blockId,
    block_index: blockIndex,
    block_type: blockType as NotebookBlockShape["block_type"],
    ref_id: nullableString(block.ref_id),
    content_json: record(block.content_json) ?? {},
    created_at: nonEmptyString(block.created_at) ?? "",
  };
}

function safeNotebookShape(value: unknown): NotebookShape {
  const notebook = record(value);
  const notebookId = nonEmptyString(notebook?.notebook_id);
  if (!notebook || !notebookId) {
    throw new ApiError("Malformed notebook response", 502, "");
  }
  const blocks = Array.isArray(notebook.blocks)
    ? notebook.blocks.flatMap((item) => {
        const block = safeNotebookBlock(item);
        return block ? [block] : [];
      })
    : [];
  return {
    notebook_id: notebookId,
    title: nonEmptyString(notebook.title) ?? notebookId,
    investigation_id: nullableString(notebook.investigation_id),
    document_id: nullableString(notebook.document_id),
    content_class:
      notebook.content_class === "user_public_contribution"
        ? "user_public_contribution"
        : "user_owned",
    created_at: nonEmptyString(notebook.created_at) ?? "",
    updated_at: nonEmptyString(notebook.updated_at) ?? "",
    blocks,
  };
}

/** GET /notebooks/{id} — fetch a notebook + ordered blocks. */
export async function getNotebook(notebookId: string): Promise<NotebookShape> {
  const resolvedNotebookId = requireRequestString(notebookId, "notebookId");
  const resp = await apiFetch(
    `${API_BASE}/notebooks/${encodeURIComponent(resolvedNotebookId)}`,
  );
  if (!resp.ok) {
    throw new ApiError(
      `GET /notebooks/{id} failed: HTTP ${resp.status}`,
      resp.status,
      await resp.text(),
    );
  }
  return safeNotebookShape(await resp.json());
}

/** POST /notebooks/{id}/blocks — append a block. */
export async function appendNotebookBlock(
  notebookId: string,
  req: { block_type: string; content: unknown; ref_id?: string | null },
): Promise<NotebookShape> {
  const resolvedNotebookId = requireRequestString(notebookId, "notebookId");
  const body = sanitizeAppendNotebookBlockRequest(req);
  const resp = await apiFetch(
    `${API_BASE}/notebooks/${encodeURIComponent(resolvedNotebookId)}/blocks`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    },
  );
  if (!resp.ok) {
    throw new ApiError(
      `POST /notebooks/{id}/blocks failed: HTTP ${resp.status}`,
      resp.status,
      await resp.text(),
    );
  }
  return safeNotebookShape(await resp.json());
}

/** PATCH /notebooks/{id}/blocks/{block_id} — edit one block in place. */
export async function patchNotebookBlock(
  notebookId: string,
  blockId: string,
  body: {
    content?: Record<string, unknown> | null;
    ref_id?: string | null;
    clear_ref_id?: boolean;
  },
): Promise<NotebookShape> {
  const resolvedNotebookId = requireRequestString(notebookId, "notebookId");
  const resolvedBlockId = requireRequestString(blockId, "blockId");
  const req = sanitizePatchNotebookBlockRequest(body);
  const resp = await apiFetch(
    `${API_BASE}/notebooks/${encodeURIComponent(resolvedNotebookId)}/blocks/${encodeURIComponent(resolvedBlockId)}`,
    {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(req),
    },
  );
  if (!resp.ok) {
    throw new ApiError(
      `PATCH notebook block failed: HTTP ${resp.status}`,
      resp.status,
      await resp.text(),
    );
  }
  return safeNotebookShape(await resp.json());
}

/** DELETE /notebooks/{id}/blocks/{block_id} — remove one block. */
export async function deleteNotebookBlock(
  notebookId: string,
  blockId: string,
): Promise<NotebookShape> {
  const resolvedNotebookId = requireRequestString(notebookId, "notebookId");
  const resolvedBlockId = requireRequestString(blockId, "blockId");
  const resp = await apiFetch(
    `${API_BASE}/notebooks/${encodeURIComponent(resolvedNotebookId)}/blocks/${encodeURIComponent(resolvedBlockId)}`,
    { method: "DELETE" },
  );
  if (!resp.ok) {
    throw new ApiError(
      `DELETE notebook block failed: HTTP ${resp.status}`,
      resp.status,
      await resp.text(),
    );
  }
  return safeNotebookShape(await resp.json());
}

/** POST /notebooks/{id}/blocks/reorder — move blocks. */
export async function reorderNotebookBlocks(
  notebookId: string,
  orderedBlockIds: string[],
): Promise<NotebookShape> {
  const resolvedNotebookId = requireRequestString(notebookId, "notebookId");
  const ordered_block_ids = sanitizeOrderedBlockIds(orderedBlockIds);
  const resp = await apiFetch(
    `${API_BASE}/notebooks/${encodeURIComponent(resolvedNotebookId)}/blocks/reorder`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ ordered_block_ids }),
    },
  );
  if (!resp.ok) {
    throw new ApiError(
      `Reorder failed: HTTP ${resp.status}`,
      resp.status,
      await resp.text(),
    );
  }
  return safeNotebookShape(await resp.json());
}

/** SPR-11 M3 — the §14.4 inline-rubric verdict for a completed research's
 *  answer, READ from the persisted `rubric.scored` event (never recomputed
 *  client-side). `composite` is the headline score in [0, 1]; the four
 *  sub-scores are present only when the persisted note encoded them, and are
 *  null otherwise (honest, never invented). The surface renders a quiet
 *  plain-language quality cue from this, and flags a low score so the operator
 *  knows the answer may want another pass. Absent (`null` on the parent) ⇒ no
 *  score was persisted ⇒ the surface shows nothing. */
export interface RubricScore {
  composite: number;
  voice_style: number | null;
  conviction: number | null;
  citation_density: number | null;
  constraint_compliance: number | null;
  notes: string;
}

export interface InvestigationStatus {
  investigation_id: string;
  status: "in_progress" | "completed" | "failed" | "not_found";
  current_phase: number | null;
  last_delivered_action_type: string | null;
  terminal_payload: Record<string, unknown> | null;
  /** The inline-rubric verdict for this research's answer; null when no
   *  score was persisted (the no-synthesis / no-key case). */
  rubric_score: RubricScore | null;
}

function safeDetailedInvestigationStatus(
  value: unknown,
): InvestigationStatus["status"] {
  return value === "in_progress" ||
    value === "completed" ||
    value === "failed" ||
    value === "not_found"
    ? value
    : "failed";
}

function rubricScore(value: unknown): number | null {
  const score = finiteNonNegativeNumber(value);
  return score === null ? null : Math.min(score, 1);
}

function safeRubricScore(value: unknown): RubricScore | null {
  const score = record(value);
  if (!score) return null;
  return {
    composite: rubricScore(score.composite) ?? 0,
    voice_style: rubricScore(score.voice_style),
    conviction: rubricScore(score.conviction),
    citation_density: rubricScore(score.citation_density),
    constraint_compliance: rubricScore(score.constraint_compliance),
    notes: nonEmptyString(score.notes) ?? "",
  };
}

function safeInvestigationStatusResponse(
  value: unknown,
  fallbackInvestigationId: string,
): InvestigationStatus {
  const body = record(value);
  return {
    investigation_id:
      nonEmptyString(body?.investigation_id) ?? fallbackInvestigationId,
    status: safeDetailedInvestigationStatus(body?.status),
    current_phase: nonNegativeInteger(body?.current_phase),
    last_delivered_action_type: nullableString(body?.last_delivered_action_type),
    terminal_payload: record(body?.terminal_payload),
    rubric_score: safeRubricScore(body?.rubric_score),
  };
}

/** GET /investigations/{id} — fetch terminal-state status. */
export async function getInvestigationStatus(
  investigationId: string,
): Promise<InvestigationStatus> {
  const resolvedInvestigationId = requireRequestString(investigationId, "investigationId");
  const resp = await apiFetch(
    `${API_BASE}/investigations/${encodeURIComponent(resolvedInvestigationId)}`,
  );
  if (!resp.ok) {
    throw new ApiError(
      `GET /investigations/{id} failed: HTTP ${resp.status}`,
      resp.status,
      await resp.text(),
    );
  }
  return safeInvestigationStatusResponse(await resp.json(), resolvedInvestigationId);
}

export interface ChunkResponse {
  chunk_id: string;
  text: string;
  section_path: string | null;
  token_count: number;
  document_id: string;
  document_title: string | null;
  source_tier: number;
  /** §9.0: whether this source may be opened on the reading surface.
   *  False ⇒ the body (`text`) is withheld by the endpoint and the
   *  surface must show "not available to open", never the content. */
  servable: boolean;
  /** SPR-10 M1 — "whose work grounds this": the source's IP-holder name
   *  (e.g. "MIT Press"), or null when no owner is resolved (honest
   *  "unknown owner", never invented). §9.0: a non-servable source
   *  withholds its owner with its body, so this is null for a restricted /
   *  taken-down source. */
  ip_holder_name?: string | null;
  /** The IP holder's lifecycle word (pre_onboarded … claimed); null when
   *  no owner or non-servable. Lets the surface frame escrow opt-in-only. */
  ip_holder_status?: string | null;
  /** Why a source is withheld ("restricted" | "taken_down"); null when
   *  servable. Mirrors interfaces/research/api/app.py:ChunkResponse. */
  servability: string | null;
}

// ── Sprint 12: source ingest ───────────────────────────────────────

export type SourceKind = "arxiv" | "youtube" | "podcast" | "url";

const SOURCE_KINDS = new Set<SourceKind>([
  "arxiv",
  "youtube",
  "podcast",
  "url",
]);

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

function requireSourceKind(value: unknown): SourceKind {
  const kind = requireRequestString(value, "kind");
  if (!SOURCE_KINDS.has(kind as SourceKind)) {
    throw new TypeError("kind must be a supported source kind");
  }
  return kind as SourceKind;
}

function optionalNonNegativeNumber(value: unknown, field: string): number | undefined {
  if (value === undefined) return undefined;
  const number = finiteNonNegativeNumber(value);
  if (number === null) throw new RangeError(`${field} must be a non-negative finite number`);
  return number;
}

function optionalNonNegativeInteger(value: unknown, field: string): number | undefined {
  if (value === undefined) return undefined;
  if (typeof value !== "number") {
    throw new RangeError(`${field} must be a non-negative safe integer`);
  }
  assertNonNegativeSafeInteger(value, field);
  return value;
}

function optionalPositiveInteger(value: unknown, field: string): number | undefined {
  if (value === undefined) return undefined;
  if (typeof value !== "number") {
    throw new RangeError(`${field} must be a positive safe integer`);
  }
  assertPositiveSafeInteger(value, field);
  return value;
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

const DELIVERABLE_KINDS = new Set<DeliverableKind>([
  "research_memo",
  "book_chapter",
  "biography_section",
  "investor_brief",
  "general_essay",
]);

const BLOCK_KINDS = new Set<BlockKind>([
  "insight",
  "open_question",
  "operator_note",
  "claim",
]);

const EXPORT_FORMATS = new Set<ExportFormatName>([
  "markdown",
  "html",
  "json",
  "pdf",
  "epub",
  "substack",
]);

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
  /** SPR-09 M1: the piece↔research link (deliverables.investigation_root_id).
   * The Write header shows it; the canvas imports the linked research's blocks.
   * Read back here to verify the link exists (not a UI claim). */
  investigation_root_id: string | null;
  sections: SectionResponse[];
}

function safeDeliverableKind(value: unknown): DeliverableKind {
  return DELIVERABLE_KINDS.has(value as DeliverableKind)
    ? (value as DeliverableKind)
    : "general_essay";
}

function requireDeliverableKind(value: unknown): DeliverableKind {
  const deliverableKind = requireRequestString(value, "deliverable_kind");
  if (!DELIVERABLE_KINDS.has(deliverableKind as DeliverableKind)) {
    throw new TypeError("deliverable_kind must be a supported deliverable kind");
  }
  return deliverableKind as DeliverableKind;
}

function requireBlockKind(value: unknown): BlockKind {
  const blockKind = requireRequestString(value, "block_kind");
  if (!BLOCK_KINDS.has(blockKind as BlockKind)) {
    throw new TypeError("block_kind must be a supported block kind");
  }
  return blockKind as BlockKind;
}

function requireExportFormat(value: unknown): ExportFormatName {
  const format = requireRequestString(value, "format");
  if (!EXPORT_FORMATS.has(format as ExportFormatName)) {
    throw new TypeError("format must be a supported export format");
  }
  return format as ExportFormatName;
}

function sanitizeWriteStringList(value: unknown, field: string): string[] | undefined {
  if (value === undefined) return undefined;
  if (!Array.isArray(value)) throw new TypeError(`${field} must be an array`);
  const items = value.map((item) => requireRequestString(item, field));
  if (new Set(items).size !== items.length) {
    throw new TypeError(`${field} must not contain duplicates`);
  }
  return items;
}

function safeStringList(value: unknown): string[] {
  if (!Array.isArray(value)) return [];
  return value.flatMap((item) => {
    const text = nonEmptyString(item);
    return text ? [text] : [];
  });
}

function uniqueStringList(value: unknown): string[] {
  return Array.from(new Set(safeStringList(value)));
}

function safeProseProvenance(value: unknown): Record<string, string[]> | null {
  const provenance = record(value);
  if (!provenance) return null;
  return Object.fromEntries(
    Object.entries(provenance).flatMap(([key, raw]) => {
      const safeKey = nonEmptyString(key);
      const ids = safeStringList(raw);
      return safeKey && ids.length > 0 ? [[safeKey, ids]] : [];
    }),
  );
}

function safeDeliverableSummary(value: unknown): DeliverableSummary | null {
  const deliverable = record(value);
  if (!deliverable) return null;
  const deliverableId = nonEmptyString(deliverable.deliverable_id);
  if (!deliverableId) return null;
  return {
    deliverable_id: deliverableId,
    title: nonEmptyString(deliverable.title) ?? deliverableId,
    deliverable_kind: safeDeliverableKind(deliverable.deliverable_kind),
    investigation_root_id: nullableString(deliverable.investigation_root_id),
    status: nonEmptyString(deliverable.status) ?? "draft",
    created_at: nullableString(deliverable.created_at),
    updated_at: nullableString(deliverable.updated_at),
    section_count: nonNegativeInteger(deliverable.section_count) ?? 0,
  };
}

function safeDeliverableList(value: unknown): {
  count: number;
  deliverables: DeliverableSummary[];
} {
  const body = record(value);
  const deliverables = Array.isArray(body?.deliverables)
    ? body.deliverables.flatMap((item) => {
        const deliverable = safeDeliverableSummary(item);
        return deliverable ? [deliverable] : [];
      })
    : [];
  return {
    count: nonNegativeInteger(body?.count) ?? deliverables.length,
    deliverables,
  };
}

function safeSectionResponse(value: unknown): SectionResponse | null {
  const section = record(value);
  if (!section) return null;
  const sectionId = nonEmptyString(section.section_id);
  const deliverableId = nonEmptyString(section.deliverable_id);
  if (!sectionId || !deliverableId) return null;
  return {
    section_id: sectionId,
    deliverable_id: deliverableId,
    parent_section_id: nullableString(section.parent_section_id),
    section_index: nonNegativeInteger(section.section_index) ?? 0,
    title: nullableString(section.title),
    prose_text: nullableString(section.prose_text),
    prose_provenance: safeProseProvenance(section.prose_provenance),
    block_count: nonNegativeInteger(section.block_count) ?? 0,
  };
}

function requireSectionResponse(value: unknown): SectionResponse {
  const section = safeSectionResponse(value);
  if (!section) throw malformedApiResponse("Malformed API response: section");
  return section;
}

function safeDeliverableDetail(value: unknown): DeliverableDetailResponse {
  const summary = safeDeliverableSummary(value);
  const body = record(value);
  if (!summary || !body) {
    throw malformedApiResponse("Malformed API response: deliverable");
  }
  const sections = Array.isArray(body.sections)
    ? body.sections.flatMap((item) => {
        const section = safeSectionResponse(item);
        return section ? [section] : [];
      })
    : [];
  return {
    deliverable_id: summary.deliverable_id,
    title: summary.title,
    deliverable_kind: summary.deliverable_kind,
    status: summary.status,
    investigation_root_id: summary.investigation_root_id,
    sections,
  };
}

export async function createDeliverable(req: {
  title: string;
  deliverable_kind: DeliverableKind;
  investigation_root_id?: string;
}): Promise<DeliverableSummary> {
  const investigationRootId = optionalRequestString(req.investigation_root_id);
  const body = {
    title: requireRequestString(req.title, "title"),
    deliverable_kind: requireDeliverableKind(req.deliverable_kind),
    ...(investigationRootId ? { investigation_root_id: investigationRootId } : {}),
  };
  const resp = await apiFetch(`${API_BASE}/deliverables`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!resp.ok) {
    throw new ApiError(
      `POST /deliverables failed: HTTP ${resp.status}`,
      resp.status,
      await resp.text(),
    );
  }
  const deliverable = safeDeliverableSummary(await resp.json());
  if (!deliverable) throw malformedApiResponse("Malformed API response: deliverable");
  return deliverable;
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
  return safeDeliverableList(await resp.json());
}

export async function getDeliverable(
  id: string,
): Promise<DeliverableDetailResponse> {
  const resolvedId = requireRequestString(id, "deliverable_id");
  const resp = await apiFetch(
    `${API_BASE}/deliverables/${encodeURIComponent(resolvedId)}`,
  );
  if (!resp.ok) {
    throw new ApiError(
      `GET /deliverables/{id} failed: HTTP ${resp.status}`,
      resp.status,
      await resp.text(),
    );
  }
  return safeDeliverableDetail(await resp.json());
}

export async function createSection(req: {
  deliverable_id: string;
  section_index: number;
  title?: string;
  parent_section_id?: string;
}): Promise<SectionResponse> {
  assertNonNegativeSafeInteger(req.section_index, "section_index");
  const title = optionalRequestString(req.title);
  const parentSectionId = optionalRequestString(req.parent_section_id);
  const body = {
    deliverable_id: requireRequestString(req.deliverable_id, "deliverable_id"),
    section_index: req.section_index,
    ...(title ? { title } : {}),
    ...(parentSectionId ? { parent_section_id: parentSectionId } : {}),
  };
  const resp = await apiFetch(`${API_BASE}/sections`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!resp.ok) {
    throw new ApiError(
      `POST /sections failed: HTTP ${resp.status}`,
      resp.status,
      await resp.text(),
    );
  }
  return requireSectionResponse(await resp.json());
}

export async function attachBlock(req: {
  section_id: string;
  block_kind: BlockKind;
  block_id: string;
  block_index: number;
}): Promise<void> {
  assertNonNegativeSafeInteger(req.block_index, "block_index");
  const body = {
    section_id: requireRequestString(req.section_id, "section_id"),
    block_kind: requireBlockKind(req.block_kind),
    block_id: requireRequestString(req.block_id, "block_id"),
    block_index: req.block_index,
  };
  const resp = await apiFetch(`${API_BASE}/sections/attach-block`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
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

function safeBlockKind(value: unknown): BlockKind {
  return BLOCK_KINDS.has(value as BlockKind) ? (value as BlockKind) : "claim";
}

function safeBlockSearchHit(value: unknown): BlockSearchHit | null {
  const hit = record(value);
  if (!hit) return null;
  const blockId = nonEmptyString(hit.block_id);
  const body = nonEmptyString(hit.body);
  if (!blockId || !body) return null;
  return {
    block_id: blockId,
    block_kind: safeBlockKind(hit.block_kind),
    label: nonEmptyString(hit.label) ?? body,
    body,
    source_tier: nonNegativeInteger(hit.source_tier),
    document_title: nullableString(hit.document_title),
  };
}

function safeBlockSearchResponse(value: unknown): {
  count: number;
  hits: BlockSearchHit[];
} {
  const body = record(value);
  const hits = Array.isArray(body?.hits)
    ? body.hits.flatMap((item) => {
        const hit = safeBlockSearchHit(item);
        return hit ? [hit] : [];
      })
    : [];
  return {
    count: nonNegativeInteger(body?.count) ?? hits.length,
    hits,
  };
}

export async function searchBlocks(
  q: string,
  limit = 20,
): Promise<{ count: number; hits: BlockSearchHit[] }> {
  assertPositiveSafeInteger(limit, "limit");
  const query = requireRequestString(q, "q");
  const url = new URL(`${API_BASE}/blocks/search`, window.location.origin);
  url.searchParams.set("q", query);
  url.searchParams.set("limit", String(limit));
  const resp = await apiFetch(url.toString());
  if (!resp.ok) {
    throw new ApiError(
      `GET /blocks/search failed: HTTP ${resp.status}`,
      resp.status,
      await resp.text(),
    );
  }
  return safeBlockSearchResponse(await resp.json());
}

export async function reorderBlock(req: {
  section_id: string;
  block_kind: BlockKind;
  block_id: string;
  new_section_id?: string;
  new_block_index: number;
}): Promise<void> {
  assertNonNegativeSafeInteger(req.new_block_index, "new_block_index");
  const newSectionId = optionalRequestString(req.new_section_id);
  const body = {
    section_id: requireRequestString(req.section_id, "section_id"),
    block_kind: requireBlockKind(req.block_kind),
    block_id: requireRequestString(req.block_id, "block_id"),
    ...(newSectionId ? { new_section_id: newSectionId } : {}),
    new_block_index: req.new_block_index,
  };
  const resp = await apiFetch(`${API_BASE}/sections/reorder-block`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
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

function safeUpdateSectionProseResponse(value: unknown): UpdateSectionProseResponse {
  const body = record(value);
  if (!body) throw malformedApiResponse("Malformed API response: section prose");
  return {
    status: body.status === "saved_and_promoted" ? "saved_and_promoted" : "saved",
    section_id: requireApiString(body.section_id, "section_id"),
    claim_node_id: nullableString(body.claim_node_id),
    claim_event_id: nullableString(body.claim_event_id),
  };
}

export async function updateSectionProse(
  sectionId: string,
  req: UpdateSectionProseRequest,
): Promise<UpdateSectionProseResponse> {
  const citedChunkIds = sanitizeWriteStringList(req.cited_chunk_ids, "cited_chunk_ids");
  const originalText = optionalRequestString(req.original_text);
  const investigationId = optionalRequestString(req.investigation_id);
  const body = {
    prose_text: requireRequestString(req.prose_text, "prose_text"),
    ...(originalText ? { original_text: originalText } : {}),
    ...(req.promote_to_graph !== undefined ? { promote_to_graph: req.promote_to_graph } : {}),
    ...(citedChunkIds ? { cited_chunk_ids: citedChunkIds } : {}),
    ...(investigationId ? { investigation_id: investigationId } : {}),
  };
  const resolvedSectionId = requireRequestString(sectionId, "sectionId");
  const resp = await apiFetch(
    `${API_BASE}/sections/${encodeURIComponent(resolvedSectionId)}/prose`,
    {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    },
  );
  if (!resp.ok) {
    throw new ApiError(
      `PATCH /sections/{id}/prose failed: HTTP ${resp.status}`,
      resp.status,
      await resp.text(),
    );
  }
  return safeUpdateSectionProseResponse(await resp.json());
}

export type ExportFormatName =
  | "markdown"
  | "html"
  | "json"
  | "pdf"
  | "epub"
  | "substack";

export interface ExportFormatResponse {
  format: ExportFormatName;
  content: string;
  filename: string;
  /** "text" for markdown/html/json/substack; "base64" for binary
   * formats (pdf, epub). When base64, the caller decodes via
   * ``atob`` and wraps in a Blob with the right MIME for download. */
  content_encoding: "text" | "base64";
}

function safeExportFormat(value: unknown, fallbackFormat: ExportFormatName): ExportFormatName {
  return value === "markdown" ||
    value === "html" ||
    value === "json" ||
    value === "pdf" ||
    value === "epub" ||
    value === "substack"
    ? value
    : fallbackFormat;
}

function safeExportResponse(
  value: unknown,
  fallbackFormat: ExportFormatName,
): ExportFormatResponse {
  const body = record(value);
  const content = typeof body?.content === "string" ? body.content : null;
  if (!body || content === null) {
    throw malformedApiResponse("Malformed API response: export");
  }
  return {
    format: safeExportFormat(body.format, fallbackFormat),
    content,
    filename: nonEmptyString(body.filename) ?? `deliverable.${fallbackFormat}`,
    content_encoding: body.content_encoding === "base64" ? "base64" : "text",
  };
}

export async function exportDeliverable(
  id: string,
  format: ExportFormatName,
): Promise<ExportFormatResponse> {
  const resolvedId = requireRequestString(id, "deliverable_id");
  const resolvedFormat = requireExportFormat(format);
  const url = new URL(
    `${API_BASE}/deliverables/${encodeURIComponent(resolvedId)}/export`,
    window.location.origin,
  );
  url.searchParams.set("format", resolvedFormat);
  const resp = await apiFetch(url.toString());
  if (!resp.ok) {
    throw new ApiError(
      `GET /deliverables/{id}/export failed: HTTP ${resp.status}`,
      resp.status,
      await resp.text(),
    );
  }
  return safeExportResponse(await resp.json(), resolvedFormat);
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

function safeVoiceNoteIngestResponse(value: unknown): VoiceNoteIngestResponse {
  const body = record(value);
  if (!body) throw malformedApiResponse("Malformed API response: voice note ingest");
  return {
    status: body.status === "skipped" ? "skipped" : "ingested",
    document_id: requireApiString(body.document_id, "document_id"),
    document_loaded_event_id: nullableString(body.document_loaded_event_id),
    chunks_written: nonNegativeInteger(body.chunks_written) ?? 0,
    skipped_reason: nullableString(body.skipped_reason),
    title: nullableString(body.title),
  };
}

export async function ingestVoiceNote(
  req: VoiceNoteIngestRequest,
): Promise<VoiceNoteIngestResponse> {
  const investigationId = optionalRequestString(req.investigation_id);
  const title = optionalRequestString(req.title);
  const durationSeconds = optionalNonNegativeNumber(req.duration_seconds, "duration_seconds");
  const language = optionalRequestString(req.language);
  const body = {
    transcript: requireRequestString(req.transcript, "transcript"),
    ...(investigationId ? { investigation_id: investigationId } : {}),
    ...(title ? { title } : {}),
    ...(durationSeconds !== undefined ? { duration_seconds: durationSeconds } : {}),
    ...(language ? { language } : {}),
  };
  const resp = await apiFetch(`${API_BASE}/voice-notes/ingest`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!resp.ok) {
    throw new ApiError(
      `POST /voice-notes/ingest failed: HTTP ${resp.status}`,
      resp.status,
      await resp.text(),
    );
  }
  return safeVoiceNoteIngestResponse(await resp.json());
}

// ── Read SPR-06 / SPR-04: voice transcription ──────────────────────
//
// Mirrors interfaces/research/api/read_voice.py:transcribe. Posts raw
// audio bytes (e.g. audio/webm) and gets back a transcript. Gated on the
// operator OpenAI key: a 503 is the honest no-key state, surfaced as
// AIActionFailure by the caller — never a fabricated transcript.
//
// NB: api/books.ts has a sibling transcribeAudio for the Reading mode; it
// flattens the HTTP status into a plain Error. This one preserves the
// status via ApiError so the Research chase can tell 503 (no key) apart
// from a transient failure and show the right honest state.

export interface TranscribeResponse {
  transcript: string;
  language: string | null;
  duration_seconds: number;
}

function safeTranscribeResponse(value: unknown): TranscribeResponse {
  const body = record(value);
  if (!body || typeof body.transcript !== "string") {
    throw malformedApiResponse("Malformed API response: transcription");
  }
  return {
    transcript: body.transcript.trim(),
    language: nullableString(body.language),
    duration_seconds: finiteNonNegativeNumber(body.duration_seconds) ?? 0,
  };
}

/** POST /voice/transcribe — audio blob → transcript (Whisper). 503 when
 *  the operator OpenAI key is unset (honest no-key). Preserves the status
 *  on ApiError so the caller can distinguish no-key from a transient. */
export async function transcribeAudio(audio: Blob): Promise<TranscribeResponse> {
  if (!(audio instanceof Blob) || audio.size <= 0) {
    throw new TypeError("audio must be a non-empty Blob");
  }
  const resp = await apiFetch(`${API_BASE}/voice/transcribe`, {
    method: "POST",
    headers: { "Content-Type": audio.type || "application/octet-stream" },
    body: audio,
  });
  if (!resp.ok) {
    throw new ApiError(
      `POST /voice/transcribe failed: HTTP ${resp.status}`,
      resp.status,
      await resp.text(),
    );
  }
  return safeTranscribeResponse(await resp.json());
}

function safeIngestStatus(value: unknown): IngestSourceResponse["status"] {
  return value === "skipped" || value === "error" ? value : "ingested";
}

function safeIngestSourceResponse(value: unknown): IngestSourceResponse {
  const body = record(value);
  if (!body) throw malformedApiResponse("Malformed API response: source ingest");
  return {
    status: safeIngestStatus(body.status),
    detected_kind: nonEmptyString(body.detected_kind) ?? "url",
    document_id: nullableString(body.document_id),
    document_loaded_event_id: nullableString(body.document_loaded_event_id),
    chunks_written: nonNegativeInteger(body.chunks_written) ?? 0,
    skipped_reason: nullableString(body.skipped_reason),
    error_message: nullableString(body.error_message),
    title: nullableString(body.title),
    episodes_processed: nonNegativeInteger(body.episodes_processed) ?? 0,
    episodes_ingested: nonNegativeInteger(body.episodes_ingested) ?? 0,
  };
}

/** POST /sources/ingest — add a URL to the substrate graph. */
export async function ingestSource(
  req: IngestSourceRequest,
): Promise<IngestSourceResponse> {
  const kind = req.kind === undefined ? undefined : requireSourceKind(req.kind);
  const investigationId = optionalRequestString(req.investigation_id);
  const sourceTier = optionalNonNegativeInteger(req.source_tier, "source_tier");
  const maxEpisodes = optionalPositiveInteger(req.max_episodes, "max_episodes");
  const body = {
    url: requireRequestString(req.url, "url"),
    ...(kind ? { kind } : {}),
    ...(investigationId ? { investigation_id: investigationId } : {}),
    ...(sourceTier !== undefined ? { source_tier: sourceTier } : {}),
    ...(maxEpisodes !== undefined ? { max_episodes: maxEpisodes } : {}),
  };
  const resp = await apiFetch(`${API_BASE}/sources/ingest`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!resp.ok) {
    throw new ApiError(
      `POST /sources/ingest failed: HTTP ${resp.status}`,
      resp.status,
      await resp.text(),
    );
  }
  return safeIngestSourceResponse(await resp.json());
}

// ── SPR-03: distill surface (insights / open questions / living notes) ──
//
// Mirrors interfaces/research/api/distill_routes.py. The node_id is an
// opaque handle echoed back on a challenge — never rendered as a label
// (copy-lint: no raw-id leaks). "research" is the user-facing word for an
// investigation (see language.ts GLOSSARY).

export interface DistilledNode {
  node_id: string;
  /** "insight" | "question" — the §2.1 primitive. */
  kind: string;
  /** Current text; reflects any living-note refinement (read from the node). */
  text: string;
  confidence?: string | null;
  /** The source that grounds it (a document handle); null when ungrounded. */
  source_document_id?: string | null;
  /** Cited chunk for openDocument({ chunkId }) — SPR-07 provenance. */
  chunk_id?: string | null;
  /** How many times this note has changed (a living-note signal). */
  refinement_count: number;
  /** A question whose challenge needs new research (escalation seam). */
  escalated: boolean;
  /** The reserved (NOT launched) child research id; SPR-04/05 launch it. */
  reserved_child_investigation_id?: string | null;
}

export interface DistillationResponse {
  investigation_id: string;
  insights: DistilledNode[];
  questions: DistilledNode[];
}

function safeDistilledNode(value: unknown, fallbackKind: "insight" | "question"): DistilledNode | null {
  const node = record(value);
  if (!node) return null;
  const nodeId = nonEmptyString(node.node_id);
  const text = nonEmptyString(node.text);
  if (!nodeId || !text) return null;
  return {
    node_id: nodeId,
    kind: nonEmptyString(node.kind) ?? fallbackKind,
    text,
    confidence: nullableString(node.confidence),
    source_document_id: nullableString(node.source_document_id),
    chunk_id: nullableString(node.chunk_id),
    refinement_count: nonNegativeInteger(node.refinement_count) ?? 0,
    escalated: node.escalated === true,
    reserved_child_investigation_id: nullableString(node.reserved_child_investigation_id),
  };
}

function safeDistillationResponse(
  value: unknown,
  fallbackInvestigationId: string,
): DistillationResponse {
  const body = record(value);
  const insights = Array.isArray(body?.insights)
    ? body.insights.flatMap((item) => {
        const node = safeDistilledNode(item, "insight");
        return node ? [node] : [];
      })
    : [];
  const questions = Array.isArray(body?.questions)
    ? body.questions.flatMap((item) => {
        const node = safeDistilledNode(item, "question");
        return node ? [node] : [];
      })
    : [];
  return {
    investigation_id:
      nonEmptyString(body?.investigation_id) ?? fallbackInvestigationId,
    insights,
    questions,
  };
}

/** GET /research/{id}/distill — the durable product of a research:
 *  its insights + open questions, read off the graph. */
export async function getDistillation(
  investigationId: string,
): Promise<DistillationResponse> {
  const resolvedInvestigationId = requireRequestString(investigationId, "investigationId");
  const resp = await apiFetch(
    `${API_BASE}/research/${encodeURIComponent(resolvedInvestigationId)}/distill`,
  );
  if (!resp.ok) {
    throw new ApiError(
      `GET /research/{id}/distill failed: HTTP ${resp.status}`,
      resp.status,
      await resp.text(),
    );
  }
  return safeDistillationResponse(await resp.json(), resolvedInvestigationId);
}

export interface ChallengeNoteResponse {
  node_id: string;
  /** The note's text changed in place (living note). */
  applied: boolean;
  /** A stale refinement lost the seq race; the visible text is unchanged. */
  superseded: boolean;
  new_text?: string | null;
  /** The challenge couldn't be resolved — a deeper research is reserved. */
  escalated: boolean;
  /** The reserved (un-launched) child research id, when escalated. */
  reserved_child_investigation_id?: string | null;
}

function safeChallengeNoteResponse(value: unknown): ChallengeNoteResponse {
  const body = record(value);
  if (!body) throw malformedApiResponse("Malformed API response: challenge note");
  return {
    node_id: requireApiString(body.node_id, "node_id"),
    applied: body.applied === true,
    superseded: body.superseded === true,
    new_text: nullableString(body.new_text),
    escalated: body.escalated === true,
    reserved_child_investigation_id: nullableString(body.reserved_child_investigation_id),
  };
}

/** POST /research/notes/{nodeId}/challenge — drive the shipped living-note
 *  path. Resolves → mutates in place; declines → escalation (reserved, not
 *  launched). 503 = no model configured (honest no-key); the caller shows
 *  the shared failure surface, never a fabricated change. */
export async function challengeNote(
  nodeId: string,
  req: { investigation_id: string; challenge_text?: string },
): Promise<ChallengeNoteResponse> {
  const resolvedNodeId = requireRequestString(nodeId, "nodeId");
  const resolvedInvestigationId = requireRequestString(req.investigation_id, "investigation_id");
  const challengeText = optionalRequestString(req.challenge_text) ?? "";
  const resp = await apiFetch(
    `${API_BASE}/research/notes/${encodeURIComponent(resolvedNodeId)}/challenge`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        investigation_id: resolvedInvestigationId,
        challenge_text: challengeText,
      }),
    },
  );
  if (!resp.ok) {
    throw new ApiError(
      `POST /research/notes/{id}/challenge failed: HTTP ${resp.status}`,
      resp.status,
      await resp.text(),
    );
  }
  return safeChallengeNoteResponse(await resp.json());
}

function safeChunkResponse(value: unknown, fallbackChunkId: string): ChunkResponse {
  const body = record(value);
  if (!body) throw malformedApiResponse("Malformed API response: chunk");
  const documentId = nonEmptyString(body.document_id);
  if (!documentId) throw malformedApiResponse("Malformed API response: document_id");
  const servable = body.servable === true;
  return {
    chunk_id: nonEmptyString(body.chunk_id) ?? fallbackChunkId,
    text: typeof body.text === "string" ? body.text : "",
    section_path: nullableString(body.section_path),
    token_count: nonNegativeInteger(body.token_count) ?? 0,
    document_id: documentId,
    document_title: nullableString(body.document_title),
    source_tier: nonNegativeInteger(body.source_tier) ?? 0,
    servable,
    ip_holder_name: servable ? nullableString(body.ip_holder_name) : null,
    ip_holder_status: servable ? nullableString(body.ip_holder_status) : null,
    servability: nullableString(body.servability),
  };
}

/** GET /chunks/{id} — used by Mode A's claim hover modal. */
export async function getChunk(chunkId: string): Promise<ChunkResponse> {
  const resolvedChunkId = requireRequestString(chunkId, "chunkId");
  const resp = await apiFetch(
    `${API_BASE}/chunks/${encodeURIComponent(resolvedChunkId)}`,
  );
  if (!resp.ok) {
    throw new ApiError(
      `GET /chunks/{id} failed: HTTP ${resp.status}`,
      resp.status,
      await resp.text(),
    );
  }
  return safeChunkResponse(await resp.json(), resolvedChunkId);
}

// ── SPR-10: §9 provenance + economics, surfaced (accrual, NOT disbursement) ──
//
// The accrual view (Economics/AccrualView) reads two SHIPPED, read-only
// surfaces and shows them honestly: attribution shares (whose work grounds a
// synthesis, under the §9.3 algorithms) and the consent/escrow view (what is
// ACCRUING per IP holder, with every balance labelled gated-on-G2+G3). Neither
// call can move money — there is no disburse/payout/publish client here.

/** One §9.3 algorithm's per-document attribution result. Mirrors
 *  interfaces/research/api/app.py:AttributionAlgorithmShares. ``shares`` is
 *  document_id → share-of-total; the parallel maps carry the human title and
 *  the provenance chain's last link (ip_holder). A §9.0-restricted source is
 *  excluded upstream in compute.py — it never appears in any of these maps. */
export interface AttributionAlgorithmShares {
  algorithm: "A" | "B" | "C";
  shares: Record<string, number>;
  document_titles: Record<string, string>;
  document_count: number;
  claim_count: number;
  /** document_id → ip_holder_id (or null = unknown owner, never invented). */
  document_ip_holders: Record<string, string | null>;
  /** ip_holder_id → lifecycle word (pre_onboarded … claimed). */
  document_ip_holder_status: Record<string, string>;
}

export interface AttributionReportResponse {
  synthesis_id: string;
  target_question: string;
  option_a: AttributionAlgorithmShares;
  option_b: AttributionAlgorithmShares;
  option_c: AttributionAlgorithmShares;
}

function safeNumberMap(value: unknown): Record<string, number> {
  const source = record(value);
  if (!source) return {};
  return Object.fromEntries(
    Object.entries(source).flatMap(([key, raw]) => {
      const id = nonEmptyString(key);
      const amount = finiteNonNegativeNumber(raw);
      return id && amount !== null ? [[id, amount]] : [];
    }),
  );
}

function safeStringMap(value: unknown): Record<string, string> {
  const source = record(value);
  if (!source) return {};
  return Object.fromEntries(
    Object.entries(source).flatMap(([key, raw]) => {
      const id = nonEmptyString(key);
      const text = nonEmptyString(raw);
      return id && text ? [[id, text]] : [];
    }),
  );
}

function safeNullableStringMap(value: unknown): Record<string, string | null> {
  const source = record(value);
  if (!source) return {};
  return Object.fromEntries(
    Object.entries(source).flatMap(([key, raw]) => {
      const id = nonEmptyString(key);
      return id ? [[id, nullableString(raw)]] : [];
    }),
  );
}

function safeAttributionAlgorithm(
  value: unknown,
  fallbackAlgorithm: AttributionAlgorithmShares["algorithm"],
): AttributionAlgorithmShares {
  const body = record(value);
  const algorithm =
    body?.algorithm === "A" || body?.algorithm === "B" || body?.algorithm === "C"
      ? body.algorithm
      : fallbackAlgorithm;
  return {
    algorithm,
    shares: safeNumberMap(body?.shares),
    document_titles: safeStringMap(body?.document_titles),
    document_count: nonNegativeInteger(body?.document_count) ?? 0,
    claim_count: nonNegativeInteger(body?.claim_count) ?? 0,
    document_ip_holders: safeNullableStringMap(body?.document_ip_holders),
    document_ip_holder_status: safeStringMap(body?.document_ip_holder_status),
  };
}

function safeAttributionReport(
  value: unknown,
  fallbackSynthesisId: string,
): AttributionReportResponse {
  const body = record(value);
  return {
    synthesis_id: nonEmptyString(body?.synthesis_id) ?? fallbackSynthesisId,
    target_question: nonEmptyString(body?.target_question) ?? "",
    option_a: safeAttributionAlgorithm(body?.option_a, "A"),
    option_b: safeAttributionAlgorithm(body?.option_b, "B"),
    option_c: safeAttributionAlgorithm(body?.option_c, "C"),
  };
}

/** GET /attribution/synthesis/{id} — Phase 1 telemetry only; no payout is
 *  attached to the result. The accrual view defaults to Option B (§9.3
 *  recommended default). ``emit_event`` defaults false (a read shouldn't write
 *  the log). */
export async function getAttributionReport(
  synthesisId: string,
): Promise<AttributionReportResponse> {
  const resolvedSynthesisId = requireRequestString(synthesisId, "synthesisId");
  const resp = await apiFetch(
    `${API_BASE}/attribution/synthesis/${encodeURIComponent(resolvedSynthesisId)}`,
  );
  if (!resp.ok) {
    throw new ApiError(
      `GET /attribution/synthesis/{id} failed: HTTP ${resp.status}`,
      resp.status,
      await resp.text(),
    );
  }
  return safeAttributionReport(await resp.json(), resolvedSynthesisId);
}

/** Why an accrued balance is NOT disbursable. ``disbursable`` is always false
 *  on this surface — no field flips it, no endpoint disburses. */
export interface DisbursementGate {
  disbursable: boolean; // always false
  open_gate_ids: string[]; // subset of {G2, G3} currently open
  holder_claimed: boolean;
  fully_unlocked: boolean;
  label: string;
}

export interface IpHolderConsent {
  ip_holder_id: string;
  display_name: string;
  status: string; // pre_onboarded | invited | claimed | opted_out
  escrow_balance_usd: string; // accruing; "0" is an honest zero
  gate: DisbursementGate;
  serves_full_text: boolean | null;
  servability_note: string | null;
}

export interface ConsentViewResponse {
  holders: IpHolderConsent[];
  escrow_report: {
    pre_onboarded: number;
    invited: number;
    claimed: number;
    opted_out: number;
    claim_rate: number;
    total_escrow_accrued_cents: number;
    total_escrow_paid_cents: number; // honestly 0 — no payout has run
    unclaimed_escrow_cents: number;
    publishers_with_nontrivial_accrual: number;
  };
  disbursement_gates_open: string[];
  total_escrow_accruing_usd: string;
  any_disbursable: boolean; // false while a legal gate is open
  gate_source_path: string;
}

function safeDisbursementGate(value: unknown): DisbursementGate {
  const gate = record(value);
  return {
    disbursable: gate?.disbursable === true,
    open_gate_ids: uniqueStringList(gate?.open_gate_ids),
    holder_claimed: gate?.holder_claimed === true,
    fully_unlocked: gate?.fully_unlocked === true,
    label: nonEmptyString(gate?.label) ?? "gated",
  };
}

function safeIpHolderConsent(value: unknown): IpHolderConsent | null {
  const holder = record(value);
  if (!holder) return null;
  const ipHolderId = nonEmptyString(holder.ip_holder_id);
  const displayName = nonEmptyString(holder.display_name);
  if (!ipHolderId || !displayName) return null;
  return {
    ip_holder_id: ipHolderId,
    display_name: displayName,
    status: nonEmptyString(holder.status) ?? "pre_onboarded",
    escrow_balance_usd: nonEmptyString(holder.escrow_balance_usd) ?? "0",
    gate: safeDisbursementGate(holder.gate),
    serves_full_text:
      typeof holder.serves_full_text === "boolean" ? holder.serves_full_text : null,
    servability_note: nullableString(holder.servability_note),
  };
}

function safeEscrowReport(value: unknown): ConsentViewResponse["escrow_report"] {
  const report = record(value);
  return {
    pre_onboarded: nonNegativeInteger(report?.pre_onboarded) ?? 0,
    invited: nonNegativeInteger(report?.invited) ?? 0,
    claimed: nonNegativeInteger(report?.claimed) ?? 0,
    opted_out: nonNegativeInteger(report?.opted_out) ?? 0,
    claim_rate: finiteNonNegativeNumber(report?.claim_rate) ?? 0,
    total_escrow_accrued_cents: nonNegativeInteger(report?.total_escrow_accrued_cents) ?? 0,
    total_escrow_paid_cents: nonNegativeInteger(report?.total_escrow_paid_cents) ?? 0,
    unclaimed_escrow_cents: nonNegativeInteger(report?.unclaimed_escrow_cents) ?? 0,
    publishers_with_nontrivial_accrual:
      nonNegativeInteger(report?.publishers_with_nontrivial_accrual) ?? 0,
  };
}

function safeConsentViewResponse(value: unknown): ConsentViewResponse {
  const body = record(value);
  const holders = Array.isArray(body?.holders)
    ? body.holders.flatMap((item) => {
        const holder = safeIpHolderConsent(item);
        return holder ? [holder] : [];
      })
    : [];
  return {
    holders,
    escrow_report: safeEscrowReport(body?.escrow_report),
    disbursement_gates_open: uniqueStringList(body?.disbursement_gates_open),
    total_escrow_accruing_usd: nonEmptyString(body?.total_escrow_accruing_usd) ?? "0",
    any_disbursable: body?.any_disbursable === true,
    gate_source_path: nonEmptyString(body?.gate_source_path) ?? "",
  };
}

/** GET /coordination/consent — the read-only escrow/consent view. Every
 *  balance is accruing-not-paid; ``any_disbursable`` is false while a legal
 *  gate is open. Read-only on the backend (no escrow write, no payout). */
export async function getConsentView(): Promise<ConsentViewResponse> {
  const resp = await apiFetch(`${API_BASE}/coordination/consent`);
  if (!resp.ok) {
    throw new ApiError(
      `GET /coordination/consent failed: HTTP ${resp.status}`,
      resp.status,
      await resp.text(),
    );
  }
  return safeConsentViewResponse(await resp.json());
}

// ── antiek-reader SPR-06: passage-Dialogue Region wire helper ──────────────
//
// The substrate noun ``block_id`` is the pinned SPR-01 Region field name (the
// wire contract the /thought-partner endpoint anchors a thread to). It lives
// HERE in the api layer (not in the user-facing FloatMenu surface) so the
// copy-lint stays green — the noun belongs with the API contract, never in
// front of a reader. ``regionFromProvenance`` maps a FloatMenu selection's
// resolved provenance (camelCase, user-surface) onto the generated ``Region``
// (snake_case, wire), or null when the host resolved no anchor.

import type { Region as DialogueRegion } from "../types/document_model.gen";

export type { Region as DialogueRegion } from "../types/document_model.gen";

/** Map a selection's resolved provenance to the SPR-01 Region the Dialogue
 * thread anchors to, or null when there is no resolvable anchor (no document /
 * block — a free-prose selection). char offsets are block-relative (M3). */
export function regionFromProvenance(p: {
  documentId?: string | null;
  blockId?: string | null;
  charStart?: number | null;
  charEnd?: number | null;
}): DialogueRegion | null {
  if (!p.documentId || !p.blockId) return null;
  return {
    document_id: p.documentId,
    block_id: p.blockId,
    char_start: p.charStart ?? null,
    char_end: p.charEnd ?? null,
  };
}
