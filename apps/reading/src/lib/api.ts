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

/** Closed set — docs/decisions/drw-plan-failure-contract.md */
export type FailureCode =
  | "backend_unreachable"
  | "provider_unconfigured"
  | "provider_upstream_error"
  | "timeout"
  | "unknown";

const FAILURE_CODES: ReadonlySet<string> = new Set([
  "backend_unreachable",
  "provider_unconfigured",
  "provider_upstream_error",
  "timeout",
  "unknown",
]);

/** Verbatim headlines — frontend must match contract §4. */
export const FAILURE_HEADLINES: Record<FailureCode, string> = {
  backend_unreachable:
    "The research engine isn't running. Start the backend, then retry.",
  provider_unconfigured:
    "No model provider is configured. Set a provider key and restart.",
  provider_upstream_error:
    "The model provider returned an error. Retry, or check your key's quota.",
  timeout: "The engine took too long to respond. Try again.",
  unknown: "Something unexpected went wrong. Try again.",
};

export const FAILURE_RETRYABLE_DEFAULT: Record<FailureCode, boolean> = {
  backend_unreachable: true,
  provider_unconfigured: false,
  provider_upstream_error: true,
  timeout: true,
  unknown: true,
};

export interface ClientFailureClassification {
  code: FailureCode;
  message?: string;
  retryable: boolean;
}

function isFailureDetailObject(
  value: unknown,
): value is { code: string; message?: string; retryable?: boolean } {
  if (typeof value !== "object" || value === null) return false;
  const o = value as Record<string, unknown>;
  return typeof o.code === "string";
}

function parseApiErrorEnvelope(err: ApiError): ClientFailureClassification {
  try {
    const parsed = JSON.parse(err.body) as { detail?: unknown };
    const detail = parsed.detail;
    if (isFailureDetailObject(detail) && FAILURE_CODES.has(detail.code)) {
      const code = detail.code as FailureCode;
      return {
        code,
        message:
          typeof detail.message === "string" ? detail.message : undefined,
        retryable:
          typeof detail.retryable === "boolean"
            ? detail.retryable
            : FAILURE_RETRYABLE_DEFAULT[code],
      };
    }
  } catch {
    // unparseable body
  }
  return {
    code: "unknown",
    retryable: FAILURE_RETRYABLE_DEFAULT.unknown,
  };
}

/** Classify a thrown value from apiFetch / research client calls. */
export function classifyClientError(e: unknown): ClientFailureClassification {
  if (e instanceof ApiError) {
    return parseApiErrorEnvelope(e);
  }
  return {
    code: "backend_unreachable",
    retryable: FAILURE_RETRYABLE_DEFAULT.backend_unreachable,
  };
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

/**
 * SPR-01 M3 — the curated research tier. CLOSED two-value set offered ONLY
 * at the research entry (not a raw model dropdown anywhere). "fast" → MiMo
 * V2.5 Pro, "deep" → DeepSeek V4 Pro. The tier→provider map lives in ONE
 * place server-side (substrate/dispatch/research_tier.py); the client only
 * sends the chosen label. Mirrors the closed set in
 * substrate/dispatch/research_tier.py:RESEARCH_TIERS.
 */
/** Curated research-entry tiers (closed set; residual gp adds wrestle). */
export type ResearchTier = "fast" | "deep" | "wrestle";

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
  /** Explicit hard authority for paid calls in the initial Loop One run. */
  approved_run_ceiling_usd: number;
  research_quote_token?: string;
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
  const quoteResp = await apiFetch(`${API_BASE}/investigations/quote`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(req),
  });
  if (!quoteResp.ok) {
    throw new ApiError(
      `POST /investigations/quote failed: HTTP ${quoteResp.status}`,
      quoteResp.status,
      await quoteResp.text(),
    );
  }
  const quote = (await quoteResp.json()) as { quote_token?: unknown };
  if (typeof quote.quote_token !== "string" || !quote.quote_token) {
    throw new ApiError("POST /investigations/quote returned an invalid quote", 502, "");
  }
  const resp = await apiFetch(`${API_BASE}/investigations`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ ...req, research_quote_token: quote.quote_token }),
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

export interface ReservedQuestionLaunchRequest {
  question: string;
  context?: string;
  research_tier: ResearchTier;
  approved_run_ceiling_usd: number;
  approved_chase_ceiling_usd: number;
  research_quote_token?: string;
}

/** Launch the server-derived child for one exact authorized reservation. */
export async function launchReservedQuestion(
  parentInvestigationId: string,
  questionId: string,
  req: ReservedQuestionLaunchRequest,
): Promise<StartInvestigationResponse> {
  const base = `${API_BASE}/research/${encodeURIComponent(parentInvestigationId)}/questions/${encodeURIComponent(questionId)}/reserved-launch`;
  const quoteResp = await apiFetch(`${base}/quote`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(req),
  });
  if (!quoteResp.ok) {
    throw new ApiError(
      `POST reserved question quote failed: HTTP ${quoteResp.status}`,
      quoteResp.status,
      await quoteResp.text(),
    );
  }
  const quote = (await quoteResp.json()) as { quote_token?: unknown };
  if (typeof quote.quote_token !== "string" || !quote.quote_token) {
    throw new ApiError("reserved question quote was invalid", 502, "");
  }
  const resp = await apiFetch(
    base,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ ...req, research_quote_token: quote.quote_token }),
    },
  );
  if (!resp.ok) {
    throw new ApiError(
      `POST reserved question launch failed: HTTP ${resp.status}`,
      resp.status,
      await resp.text(),
    );
  }
  return resp.json();
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

/** GET /watch-for-later — list unsharpened parked questions. */
export async function listWatchForLater(
  opts?: { limit?: number },
): Promise<{ count: number; questions: ParkedQuestionEntry[] }> {
  const url = new URL(`${API_BASE}/watch-for-later`, window.location.origin);
  if (opts?.limit !== undefined) url.searchParams.set("limit", String(opts.limit));
  const resp = await apiFetch(url.toString());
  if (!resp.ok) {
    throw new ApiError(
      `GET /watch-for-later failed: HTTP ${resp.status}`,
      resp.status,
      await resp.text(),
    );
  }
  return resp.json();
}

/** POST /watch-for-later/{question_id}/launch — spawn investigation
 * seeded by the parked question. Returns the new investigation handle. */
export async function launchParkedQuestion(
  question_id: string,
  approvedRunCeilingUsd: number,
): Promise<StartInvestigationResponse> {
  const base = `${API_BASE}/watch-for-later/${encodeURIComponent(question_id)}/launch`;
  const request = { approved_run_ceiling_usd: approvedRunCeilingUsd };
  const quoteResp = await apiFetch(`${base}/quote`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(request),
  });
  if (!quoteResp.ok) {
    throw new ApiError(
      `POST parked question quote failed: HTTP ${quoteResp.status}`,
      quoteResp.status,
      await quoteResp.text(),
    );
  }
  const quote = (await quoteResp.json()) as { quote_token?: unknown };
  if (typeof quote.quote_token !== "string" || !quote.quote_token) {
    throw new ApiError("parked question quote was invalid", 502, "");
  }
  const resp = await apiFetch(
    base,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        ...request,
        research_quote_token: quote.quote_token,
      }),
    },
  );
  if (!resp.ok) {
    throw new ApiError(
      `POST /watch-for-later/${question_id}/launch failed: HTTP ${resp.status}`,
      resp.status,
      await resp.text(),
    );
  }
  return resp.json();
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

/** GET /notebooks/{id} — fetch a notebook + ordered blocks. */
export async function getNotebook(notebookId: string): Promise<NotebookShape> {
  const resp = await apiFetch(
    `${API_BASE}/notebooks/${encodeURIComponent(notebookId)}`,
  );
  if (!resp.ok) {
    throw new ApiError(
      `GET /notebooks/${notebookId} failed: HTTP ${resp.status}`,
      resp.status,
      await resp.text(),
    );
  }
  return resp.json();
}

/** The composed TipTap document for a notebook (SPR-01 hydration).
 * Mirrors interfaces/research/api/app.py:NotebookContentResponse. */
export interface NotebookContentShape {
  notebook_id: string;
  title: string;
  investigation_id: string | null;
  /** ProseMirror/TipTap document JSON: {type:"doc", content:[...]}. */
  doc: Record<string, unknown>;
  revision: number;
  content_sha256: string;
  updated_at: string;
  account_scope: string;
  recovery_scope: string;
}

/** GET /notebooks/{id}/content — the composed TipTap doc the editor hydrates
 * from on mount (localStorage is only a cache/offline mirror). Inverse of the
 * autosave PUT that decomposes the doc into notebook_blocks rows. */
export async function getNotebookContent(
  notebookId: string,
  signal?: AbortSignal,
): Promise<NotebookContentShape> {
  const resp = await apiFetch(
    `${API_BASE}/notebooks/${encodeURIComponent(notebookId)}/content`,
    { signal },
  );
  if (!resp.ok) {
    throw new ApiError(
      `GET /notebooks/${notebookId}/content failed: HTTP ${resp.status}`,
      resp.status,
      await resp.text(),
    );
  }
  return resp.json();
}

export interface NotebookMutationReceiptShape {
  schema_version: 1;
  notebook_id: string;
  revision: number;
  content_sha256: string;
  replayed: boolean;
}

export async function putNotebookContent(
  notebookId: string,
  request: {
    schema_version: 1;
    base_revision: number;
    mutation_key: string;
    doc: Record<string, unknown>;
  },
  signal?: AbortSignal,
): Promise<NotebookMutationReceiptShape> {
  const resp = await apiFetch(
    `${API_BASE}/notebooks/${encodeURIComponent(notebookId)}/content`,
    {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(request),
      signal,
    },
  );
  if (!resp.ok) {
    throw new ApiError(
      `PUT /notebooks/${notebookId}/content failed: HTTP ${resp.status}`,
      resp.status,
      await resp.text(),
    );
  }
  return resp.json();
}

export interface InterviewMarginShape {
  schema_version: 1;
  interview_id: string;
  revision: number;
  content_sha256: string;
  body: string;
  account_scope: string;
  recovery_scope: string;
  replayed: boolean;
}

export async function getInterviewMargin(
  interviewId: string,
  signal?: AbortSignal,
): Promise<InterviewMarginShape> {
  const resp = await apiFetch(
    `${API_BASE}/interviews/${encodeURIComponent(interviewId)}/margin`,
    { signal },
  );
  if (!resp.ok) {
    throw new ApiError(`GET interview margin failed: HTTP ${resp.status}`, resp.status, await resp.text());
  }
  return resp.json();
}

export async function putInterviewMargin(
  interviewId: string,
  request: { schema_version: 1; base_revision: number; mutation_key: string; body: string },
  signal?: AbortSignal,
): Promise<InterviewMarginShape> {
  const resp = await apiFetch(
    `${API_BASE}/interviews/${encodeURIComponent(interviewId)}/margin`,
    {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(request),
      signal,
    },
  );
  if (!resp.ok) {
    throw new ApiError(`PUT interview margin failed: HTTP ${resp.status}`, resp.status, await resp.text());
  }
  return resp.json();
}

export interface PrivateWriteDocumentShape {
  write_document_id: string;
  project_id: string;
  title: string;
  revision: number;
  html: string;
  html_sha256: string;
  visibility: "private";
  origin_kind: "ai_composition" | "owner_native";
}

export type PrivateWriteOperation = "accept" | "undo" | "create" | "edit" | "restore" | "evidence_insert" | "evidence_bundle" | "synthesis_accept";

export interface PrivateWriteRevisionShape {
  write_document_id?: string;
  project_id?: string;
  revision: number;
  operation: PrivateWriteOperation;
  event_id: string;
  html_sha256: string;
  prior_html_sha256: string | null;
  root_acceptance_event_id: string | null;
  proposal_id: string | null;
  target_revision: number | null;
  target_html_sha256: string | null;
  created_at: string;
  has_summary: boolean;
  html?: string;
  is_current?: boolean;
  origin_kind: "ai_composition" | "owner_native";
}

export interface PrivateWriteHistoryShape {
  write_document_id: string;
  project_id: string;
  current_revision: number;
  revisions: PrivateWriteRevisionShape[];
  origin_kind: "ai_composition" | "owner_native";
}

export interface PrivateWriteMutationShape {
  event_id: string;
  write_document_id: string;
  project_id: string;
  revision: number;
  prior_revision: number;
  html_sha256: string;
  replayed: boolean;
  visibility: "private";
  operation?: "restore" | "evidence_insert" | "evidence_bundle";
  bundle_id?: string;
  target_revision?: number;
}

export interface PrivateWriteDocumentSummaryShape {
  write_document_id: string;
  project_id: string;
  title: string;
  revision: number;
  html_sha256: string;
  visibility: "private";
  updated_at: string;
  origin_kind: "ai_composition" | "owner_native";
}

export interface NativeWriteCreateShape {
  event_id: string;
  write_document_id: string;
  project_id: string;
  title: string;
  revision: 1;
  html_sha256: string;
  visibility: "private";
  origin_kind: "owner_native";
  replayed: boolean;
}

export interface WriteCitationEvidenceShape {
  source_kind: "synthesis_claim";
  source_asset_id: string;
  claim_id: string;
  chunk_ids: string[];
  document_id: string;
  receipt_sha256: string;
}

export interface WriteEvidencePreviewShape {
  write_document_id: string;
  project_id: string;
  base_revision: number;
  base_html_sha256: string;
  proposed_html: string;
  proposed_html_sha256: string;
  excerpt_sha256: string;
  source_title: string;
  citation_receipt_sha256: string;
  preview_sha256: string;
  visibility: "private";
  origin_kind: "owner_native";
}

export type EvidenceRelationship = "supports" | "contradicts" | "context" | "unresolved";
export interface WriteEvidenceBundleItemShape {
  citation_evidence: WriteCitationEvidenceShape;
  relationship: EvidenceRelationship;
  operator_label?: string | null;
}
export interface WriteEvidenceBundlePreviewShape {
  write_document_id: string; project_id: string; base_revision: number;
  base_html_sha256: string; proposed_html: string; proposed_html_sha256: string;
  manifest_sha256: string; preview_sha256: string; items: Array<Record<string, unknown>>;
  visibility: "private"; origin_kind: "owner_native"; operation: "evidence_bundle";
}
export interface EvidenceBundleSynthesisProjectionShape {
  source_kind: "evidence_bundle"; bundle_id: string; write_document_id: string;
  project_id: string; provider_id: string; model_id: string;
  projected_max_cents: number; expected_output_tokens: number; item_count: number;
  budget: { daily_cap_usd: number | null; spent_usd: number | null;
    remaining_usd: number | null; spent_status: "known" | "unknown" | "no_cap";
    cap_env: string | null; notes: string[] };
  visibility: "private";
}
export interface EvidenceBundleSynthesisProposalShape {
  proposal_id: string; source_kind: "evidence_bundle"; bundle_id: string;
  write_document_id: string; project_id: string; revision: number; base_revision: number;
  source_manifest_sha256: string; source_content_sha256: string;
  source_receipt_sha256: string; provider_id: string; model_id: string;
  projected_max_cents: number; approved_ceiling_cents: number;
  instruction: string; state: "staged"; item_count: number; visibility: "private";
}
export interface EvidenceBundleSynthesisExecutionShape {
  proposal_id: string; attempt_id: string; run_id: string;
  state: "dispatching" | "reconcile_required" | "call_not_dispatched" |
    "provider_returned" | "rejected" | "ready_for_review";
  prompt_sha256: string; route_sha256: string; hold_id: string | null;
  actual_cents: number | null; html: string | null; html_sha256: string | null;
  rejection_reason: string | null; visibility: "private";
}
export interface EvidenceSynthesisWritePreviewShape {
  write_document_id: string; project_id: string; bundle_id: string; proposal_id: string;
  execution_run_id: string; base_revision: number; base_html_sha256: string;
  result_html_sha256: string; proposed_html: string; proposed_html_sha256: string;
  preview_sha256: string; visibility: "private"; origin_kind: "owner_native";
  operation: "synthesis_accept";
}
export interface EvidenceSynthesisWriteAcceptanceShape {
  acceptance_id: string; event_id: string; proposal_id: string; bundle_id: string;
  execution_run_id: string; write_document_id: string; project_id: string;
  prior_revision: number; revision: number; html_sha256: string; receipt_sha256: string;
  replayed: boolean; visibility: "private"; origin_kind: "owner_native";
  operation: "synthesis_accept";
}
export interface SynthesisKnowledgeEvidenceShape {
  evidence_unit_id: string; relationship: EvidenceRelationship;
  operator_label: string | null; citation_receipt_sha256: string;
  source_asset_id: string; claim_id: string; source_document_id: string;
  chunk_ids: string[]; source_content_sha256: string; excerpt_sha256: string;
}
export interface SynthesisKnowledgeSourceUnitShape {
  unit_index: number; text: string; original_text_sha256: string;
  evidence: SynthesisKnowledgeEvidenceShape[];
}
export interface SynthesisKnowledgeCandidatePageShape {
  acceptance_id: string; proposal_id: string; units: SynthesisKnowledgeSourceUnitShape[];
  epistemic_status: "model_proposed"; verification: "unverified"; visibility: "private";
}
export interface SynthesisKnowledgeCandidateInputShape {
  unit_index: number; kind: "insight" | "question"; text: string;
}
export interface SynthesisKnowledgePreviewItemShape {
  ordinal: number; unit_index: number; kind: "insight" | "question";
  original_text_sha256: string; admitted_text: string;
  admitted_text_sha256: string; canonical_text: string; graph_node_id: string;
  disposition: "created" | "reused"; evidence_sha256: string;
  item_receipt_sha256: string; evidence: SynthesisKnowledgeEvidenceShape[];
}
export interface SynthesisKnowledgePreviewShape {
  acceptance_id: string; proposal_id: string; target_investigation_id: string;
  target_investigation_digest: string; item_manifest_sha256: string;
  preview_sha256: string; items: SynthesisKnowledgePreviewItemShape[];
  epistemic_status: "model_proposed_operator_admitted";
  verification: "unverified"; visibility: "private";
}
export interface SynthesisKnowledgeAdmissionShape {
  admission_id: string; acceptance_id: string; proposal_id: string; bundle_id: string;
  write_document_id: string; project_id: string; target_investigation_id: string;
  receipt_sha256: string; replayed: boolean; items: SynthesisKnowledgePreviewItemShape[];
  epistemic_status: "model_proposed_operator_admitted";
  verification: "unverified"; visibility: "private";
}

export interface PrivateWriteDocumentPageShape {
  documents: PrivateWriteDocumentSummaryShape[];
  next_after_document_id: string | null;
}

const privateWritePath = (projectId: string, writeDocumentId: string) =>
  `${API_BASE}/speak/projects/${encodeURIComponent(projectId)}/private-write/${encodeURIComponent(writeDocumentId)}`;

export async function listPrivateWriteDocuments(
  signal?: AbortSignal, afterDocumentId = "", limit = 100,
): Promise<PrivateWriteDocumentPageShape> {
  const query = new URLSearchParams({ after_document_id: afterDocumentId, limit: String(limit) });
  return privateWriteJson(await apiFetch(
    `${API_BASE}/speak/private-write?${query}`, { signal },
  ), "GET private Write documents");
}

export async function createNativePrivateWrite(
  title: string, idempotencyKey: string, signal?: AbortSignal,
): Promise<NativeWriteCreateShape> {
  return privateWriteJson(await apiFetch(`${API_BASE}/speak/private-write`, {
    method: "POST", headers: {
      "Content-Type": "application/json", "Idempotency-Key": idempotencyKey,
    }, body: JSON.stringify({ title }), signal,
  }), "POST private Write document");
}

async function privateWriteJson<T>(resp: Response, label: string): Promise<T> {
  if (!resp.ok) throw new ApiError(`${label}: HTTP ${resp.status}`, resp.status, await resp.text());
  return resp.json() as Promise<T>;
}

export async function getPrivateWriteDocument(
  projectId: string, writeDocumentId: string, signal?: AbortSignal,
): Promise<PrivateWriteDocumentShape> {
  return privateWriteJson(await apiFetch(privateWritePath(projectId, writeDocumentId), { signal }), "GET private Write");
}

export async function getPrivateWriteHistory(
  projectId: string, writeDocumentId: string, signal?: AbortSignal,
  afterRevision = 0, limit = 500,
): Promise<PrivateWriteHistoryShape> {
  const query = new URLSearchParams({ after_revision: String(afterRevision), limit: String(limit) });
  return privateWriteJson(await apiFetch(
    `${privateWritePath(projectId, writeDocumentId)}/history?${query}`, { signal },
  ), "GET private Write history");
}

export async function getPrivateWriteRevision(
  projectId: string, writeDocumentId: string, revision: number, signal?: AbortSignal,
): Promise<PrivateWriteRevisionShape> {
  return privateWriteJson(await apiFetch(
    `${privateWritePath(projectId, writeDocumentId)}/revisions/${revision}`, { signal },
  ), "GET private Write revision");
}

export async function editPrivateWriteDocument(
  projectId: string, writeDocumentId: string,
  request: { base_revision: number; base_html_sha256: string; html: string; summary?: string },
  idempotencyKey: string, signal?: AbortSignal,
): Promise<PrivateWriteMutationShape> {
  return privateWriteJson(await apiFetch(`${privateWritePath(projectId, writeDocumentId)}/edits`, {
    method: "POST", headers: { "Content-Type": "application/json", "Idempotency-Key": idempotencyKey },
    body: JSON.stringify(request), signal,
  }), "POST private Write edit");
}

export async function restorePrivateWriteDocument(
  projectId: string, writeDocumentId: string,
  request: { base_revision: number; base_html_sha256: string; target_revision: number },
  idempotencyKey: string, signal?: AbortSignal,
): Promise<PrivateWriteMutationShape> {
  return privateWriteJson(await apiFetch(`${privateWritePath(projectId, writeDocumentId)}/restores`, {
    method: "POST", headers: { "Content-Type": "application/json", "Idempotency-Key": idempotencyKey },
    body: JSON.stringify(request), signal,
  }), "POST private Write restore");
}

export async function previewPrivateWriteEvidenceInsertion(
  projectId: string, writeDocumentId: string,
  request: { base_revision: number; base_html_sha256: string; citation_evidence: WriteCitationEvidenceShape },
  signal?: AbortSignal,
): Promise<WriteEvidencePreviewShape> {
  return privateWriteJson(await apiFetch(
    `${privateWritePath(projectId, writeDocumentId)}/evidence-insertions/preview`, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify(request), signal,
    },
  ), "POST private Write evidence preview");
}

export async function applyPrivateWriteEvidenceInsertion(
  projectId: string, writeDocumentId: string,
  request: { base_revision: number; base_html_sha256: string; citation_evidence: WriteCitationEvidenceShape; preview_sha256: string; proposed_html_sha256: string },
  idempotencyKey: string, signal?: AbortSignal,
): Promise<PrivateWriteMutationShape> {
  return privateWriteJson(await apiFetch(
    `${privateWritePath(projectId, writeDocumentId)}/evidence-insertions`, {
      method: "POST", headers: {
        "Content-Type": "application/json", "Idempotency-Key": idempotencyKey,
      }, body: JSON.stringify(request), signal,
    },
  ), "POST private Write evidence insertion");
}

export async function previewPrivateWriteEvidenceBundle(
  projectId: string, writeDocumentId: string,
  request: { base_revision: number; base_html_sha256: string; items: WriteEvidenceBundleItemShape[] },
  signal?: AbortSignal,
): Promise<WriteEvidenceBundlePreviewShape> {
  return privateWriteJson(await apiFetch(
    `${privateWritePath(projectId, writeDocumentId)}/evidence-bundles/preview`, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify(request), signal,
    },
  ), "POST private Write evidence bundle preview");
}

export async function applyPrivateWriteEvidenceBundle(
  projectId: string, writeDocumentId: string,
  request: { base_revision: number; base_html_sha256: string; items: WriteEvidenceBundleItemShape[]; preview_sha256: string; manifest_sha256: string; proposed_html_sha256: string },
  idempotencyKey: string, signal?: AbortSignal,
): Promise<PrivateWriteMutationShape> {
  return privateWriteJson(await apiFetch(
    `${privateWritePath(projectId, writeDocumentId)}/evidence-bundles`, {
      method: "POST", headers: { "Content-Type": "application/json", "Idempotency-Key": idempotencyKey },
      body: JSON.stringify(request), signal,
    },
  ), "POST private Write evidence bundle");
}

const evidenceSynthesisPath = (
  projectId: string, writeDocumentId: string, bundleId: string,
) => `${privateWritePath(projectId, writeDocumentId)}/evidence-bundles/${encodeURIComponent(bundleId)}/ai-proposals`;

export async function projectEvidenceBundleSynthesis(
  projectId: string, writeDocumentId: string, bundleId: string,
  request: { instruction: string; provider_id: string; model_id: string; expected_output_tokens: number },
  signal?: AbortSignal,
): Promise<EvidenceBundleSynthesisProjectionShape> {
  return privateWriteJson(await apiFetch(`${evidenceSynthesisPath(projectId, writeDocumentId, bundleId)}/projection`, {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify(request), signal,
  }), "POST evidence synthesis projection");
}

export async function createEvidenceBundleSynthesisProposal(
  projectId: string, writeDocumentId: string, bundleId: string,
  request: { base_revision: number; instruction: string; provider_id: string; model_id: string;
    approved_ceiling_cents: number; expected_output_tokens: number },
  idempotencyKey: string, signal?: AbortSignal,
): Promise<EvidenceBundleSynthesisProposalShape> {
  return privateWriteJson(await apiFetch(evidenceSynthesisPath(projectId, writeDocumentId, bundleId), {
    method: "POST", headers: { "Content-Type": "application/json", "Idempotency-Key": idempotencyKey },
    body: JSON.stringify(request), signal,
  }), "POST evidence synthesis proposal");
}

export async function executeEvidenceBundleSynthesis(
  projectId: string, writeDocumentId: string, bundleId: string, proposalId: string,
  idempotencyKey: string, signal?: AbortSignal,
): Promise<EvidenceBundleSynthesisExecutionShape> {
  return privateWriteJson(await apiFetch(
    `${evidenceSynthesisPath(projectId, writeDocumentId, bundleId)}/${encodeURIComponent(proposalId)}/execute`, {
      method: "POST", headers: { "Idempotency-Key": idempotencyKey }, signal,
    },
  ), "POST evidence synthesis execution");
}

export async function reconcileEvidenceBundleSynthesis(
  projectId: string, writeDocumentId: string, bundleId: string, proposalId: string,
  signal?: AbortSignal,
): Promise<EvidenceBundleSynthesisExecutionShape> {
  return privateWriteJson(await apiFetch(
    `${evidenceSynthesisPath(projectId, writeDocumentId, bundleId)}/${encodeURIComponent(proposalId)}/reconcile`, {
      method: "POST", signal,
    },
  ), "POST evidence synthesis reconciliation");
}

export async function previewEvidenceSynthesisWriteAcceptance(
  projectId: string, writeDocumentId: string, bundleId: string, proposalId: string,
  request: { base_revision: number; base_html_sha256: string }, signal?: AbortSignal,
): Promise<EvidenceSynthesisWritePreviewShape> {
  return privateWriteJson(await apiFetch(
    `${evidenceSynthesisPath(projectId, writeDocumentId, bundleId)}/${encodeURIComponent(proposalId)}/write-preview`, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify(request), signal,
    },
  ), "POST evidence synthesis Write preview");
}

export async function applyEvidenceSynthesisWriteAcceptance(
  projectId: string, writeDocumentId: string, bundleId: string, proposalId: string,
  request: { base_revision: number; base_html_sha256: string; preview_sha256: string;
    proposed_html_sha256: string }, idempotencyKey: string, signal?: AbortSignal,
): Promise<EvidenceSynthesisWriteAcceptanceShape> {
  return privateWriteJson(await apiFetch(
    `${evidenceSynthesisPath(projectId, writeDocumentId, bundleId)}/${encodeURIComponent(proposalId)}/write-acceptance`, {
      method: "POST", headers: { "Content-Type": "application/json", "Idempotency-Key": idempotencyKey },
      body: JSON.stringify(request), signal,
    },
  ), "POST evidence synthesis Write acceptance");
}

const synthesisKnowledgePath = (
  projectId: string, writeDocumentId: string, bundleId: string,
  proposalId: string, acceptanceId: string,
) => `${evidenceSynthesisPath(projectId, writeDocumentId, bundleId)}/${encodeURIComponent(proposalId)}` +
  `/acceptances/${encodeURIComponent(acceptanceId)}`;

export async function listSynthesisKnowledgeCandidates(
  projectId: string, writeDocumentId: string, bundleId: string,
  proposalId: string, acceptanceId: string, signal?: AbortSignal,
): Promise<SynthesisKnowledgeCandidatePageShape> {
  return privateWriteJson(await apiFetch(
    `${synthesisKnowledgePath(projectId, writeDocumentId, bundleId, proposalId, acceptanceId)}/knowledge-candidates`,
    { signal },
  ), "GET synthesis knowledge candidates");
}

export async function previewSynthesisKnowledgeAdmission(
  projectId: string, writeDocumentId: string, bundleId: string,
  proposalId: string, acceptanceId: string,
  request: { target_investigation_id: string; items: SynthesisKnowledgeCandidateInputShape[] },
  signal?: AbortSignal,
): Promise<SynthesisKnowledgePreviewShape> {
  return privateWriteJson(await apiFetch(
    `${synthesisKnowledgePath(projectId, writeDocumentId, bundleId, proposalId, acceptanceId)}/knowledge-preview`,
    { method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify(request), signal },
  ), "POST synthesis knowledge preview");
}

export async function applySynthesisKnowledgeAdmission(
  projectId: string, writeDocumentId: string, bundleId: string,
  proposalId: string, acceptanceId: string,
  request: { target_investigation_id: string; items: SynthesisKnowledgeCandidateInputShape[];
    preview_sha256: string }, idempotencyKey: string, signal?: AbortSignal,
): Promise<SynthesisKnowledgeAdmissionShape> {
  return privateWriteJson(await apiFetch(
    `${synthesisKnowledgePath(projectId, writeDocumentId, bundleId, proposalId, acceptanceId)}/knowledge-admission`,
    { method: "POST", headers: { "Content-Type": "application/json",
      "Idempotency-Key": idempotencyKey }, body: JSON.stringify(request), signal },
  ), "POST synthesis knowledge admission");
}

export async function appendNotebookContent(
  notebookId: string,
  request: {
    schema_version: 1;
    account_scope: string;
    base_revision: number;
    mutation_key: string;
    block: Record<string, unknown>;
  },
  signal?: AbortSignal,
): Promise<NotebookMutationReceiptShape> {
  const resp = await apiFetch(
    `${API_BASE}/notebooks/${encodeURIComponent(notebookId)}/content/append`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(request),
      signal,
    },
  );
  if (!resp.ok) {
    throw new ApiError(
      `POST /notebooks/${notebookId}/content/append failed: HTTP ${resp.status}`,
      resp.status,
      await resp.text(),
    );
  }
  return resp.json();
}

/** POST /notebooks/{id}/blocks — append a block. */
export async function appendNotebookBlock(
  notebookId: string,
  req: { block_type: string; content: unknown; ref_id?: string | null },
): Promise<NotebookShape> {
  const resp = await apiFetch(
    `${API_BASE}/notebooks/${encodeURIComponent(notebookId)}/blocks`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(req),
    },
  );
  if (!resp.ok) {
    throw new ApiError(
      `POST /notebooks/${notebookId}/blocks failed: HTTP ${resp.status}`,
      resp.status,
      await resp.text(),
    );
  }
  return resp.json();
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
  const resp = await apiFetch(
    `${API_BASE}/notebooks/${encodeURIComponent(notebookId)}/blocks/${encodeURIComponent(blockId)}`,
    {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    },
  );
  if (!resp.ok) {
    throw new ApiError(
      `PATCH notebook block failed: HTTP ${resp.status}`,
      resp.status,
      await resp.text(),
    );
  }
  return resp.json();
}

/** DELETE /notebooks/{id}/blocks/{block_id} — remove one block. */
export async function deleteNotebookBlock(
  notebookId: string,
  blockId: string,
): Promise<NotebookShape> {
  const resp = await apiFetch(
    `${API_BASE}/notebooks/${encodeURIComponent(notebookId)}/blocks/${encodeURIComponent(blockId)}`,
    { method: "DELETE" },
  );
  if (!resp.ok) {
    throw new ApiError(
      `DELETE notebook block failed: HTTP ${resp.status}`,
      resp.status,
      await resp.text(),
    );
  }
  return resp.json();
}

/** POST /notebooks/{id}/blocks/reorder — move blocks. */
export async function reorderNotebookBlocks(
  notebookId: string,
  orderedBlockIds: string[],
): Promise<NotebookShape> {
  const resp = await apiFetch(
    `${API_BASE}/notebooks/${encodeURIComponent(notebookId)}/blocks/reorder`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ ordered_block_ids: orderedBlockIds }),
    },
  );
  if (!resp.ok) {
    throw new ApiError(
      `Reorder failed: HTTP ${resp.status}`,
      resp.status,
      await resp.text(),
    );
  }
  return resp.json();
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
  /** SPR-09 M1: the piece↔research link (deliverables.investigation_root_id).
   * The Write header shows it; the canvas imports the linked research's blocks.
   * Read back here to verify the link exists (not a UI claim). */
  investigation_root_id: string | null;
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

// ── CK-4: context picker (cursor-for-knowledge) ─────────────────────
//
// Mirrors interfaces/research/api/app.py:ContextItem / ComposeContextRequest
// / ComposeContextResponse. The client ships the operator's @-selected items
// (@doc @insight) and the substrate composes a §9.0-aware ``system_context``
// string for chat / agent / edit. This is what makes CK-1/CK-2 grounded
// instead of opaque — the operator explicitly picks what reaches the model.
//
// §9.0 gate is SERVER-DERIVED and fail-closed (CWE-862): the effective policy
// is resolved from authenticated request state in the endpoint, NEVER trusted
// from this body. So a ``personal_reading`` / restricted doc is WITHHELD on the
// non-owner path (listed in ``withheld``) and reaches the context only on the
// authenticated single-operator path. The client never decides owner status.

/** The closed enum of pickable @-mention kinds. ``investigation`` + ``note``
 *  are a documented server-side follow-up; only ``doc`` (§9.0-gated third-party
 *  content) + ``insight`` (operator-authored node text) ship today. */
export type ContextItemKind = "doc" | "insight";

/** One @-mention item. ``id`` is the graph handle — a ``document_id`` for
 *  ``doc`` (resolved through the SAME ``serve_full_text`` §9.0 gate the
 *  book-serve path uses) or a ``node_id`` for ``insight`` (the node's
 *  ``canonical_label``). */
export interface ContextItem {
  kind: ContextItemKind;
  id: string;
}

export interface ComposeContextRequest {
  /** 1–20 items (the server enforces ``min_length=1, max_length=20`` — a
   *  cost / latency blast-radius bound; the picker mirrors the cap). */
  items: ContextItem[];
}

export interface ComposeContextResponse {
  /** The model-facing composed context string (``@doc``/``@insight`` blocks
   *  joined by blank lines; empty when every item was missing/withheld). */
  system_context: string;
  /** Item ids whose content the §9.0 gate withheld (personal_reading /
   *  restricted on the non-owner path). The surface must show these by their
   *  label, plainly — "transparent intelligence, not magic". */
  withheld: string[];
  /** Item ids that resolved to no record (absent graph, deleted doc/node). */
  missing: string[];
}

/** POST /compose-context — compose a §9.0-aware system_context from the
 *  operator's @-selected items. Never raises on absent content: a missing id
 *  is reported in ``missing``, a gated doc in ``withheld``. Throws ``ApiError``
 *  only on a transport/validation failure (e.g. 422 on an empty or >20 list). */
export async function composeContext(
  req: ComposeContextRequest,
): Promise<ComposeContextResponse> {
  const resp = await apiFetch(`${API_BASE}/compose-context`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(req),
  });
  if (!resp.ok) {
    throw new ApiError(
      `POST /compose-context failed: HTTP ${resp.status}`,
      resp.status,
      await resp.text(),
    );
  }
  return resp.json();
}

// Mirrors interfaces/research/api/write_routes.py:EditSelectionRequest /
// EditSelectionResponse. The Cmd+K selection-edit client (CK-5).
export interface EditSelectionRequest {
  deliverable_id: string;
  section_id: string;
  /** The highlighted span of deliverable prose (1–8000 chars). */
  selection_text: string;
  /** The writer's natural-language edit instruction (1–1000 chars). */
  instruction: string;
}

export interface EditSelectionResponse {
  edited_text: string;
  deliverable_id: string;
  section_id: string;
}

/** POST /write/edit-selection — the Cursor Cmd+K writing-flow affordance:
 *  rewrite a highlighted span of deliverable prose per a natural-language
 *  instruction (creative_writer / GLM-5.2). The selection is deliverable
 *  prose, so a stylistic edit adds no new claims and prose_provenance stays
 *  valid. Throws ``ApiError`` on a transport/validation/provider failure. */
export async function editSelection(
  req: EditSelectionRequest,
): Promise<EditSelectionResponse> {
  const resp = await apiFetch(`${API_BASE}/write/edit-selection`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(req),
  });
  if (!resp.ok) {
    throw new ApiError(
      `POST /write/edit-selection failed: HTTP ${resp.status}`,
      resp.status,
      await resp.text(),
    );
  }
  return resp.json();
}

// Mirrors interfaces/research/api write complete route. Tab autocomplete client (CK-3).
export interface CompleteRequest {
  /** Text before the cursor (min length 1). */
  prefix: string;
  /** Optional cursor-neighborhood context (max 8000 chars). */
  document_context?: string;
  /** Continuation length bound (1..512, default 128). */
  max_tokens?: number;
}

export interface CompleteResponse {
  text: string;
}

/** POST /complete — inline Tab autocomplete: fetch a continuation for the
 * prefix at the cursor. Returns only the new text to append (not a rewrite).
 * Throws ``ApiError`` on a transport/validation failure. */
export async function completeInline(
  req: CompleteRequest,
): Promise<CompleteResponse> {
  const resp = await apiFetch(`${API_BASE}/complete`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(req),
  });
  if (!resp.ok) {
    throw new ApiError(
      `POST /complete failed: HTTP ${resp.status}`,
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

/** POST /voice/transcribe — audio blob → transcript (Whisper). 503 when
 *  the operator OpenAI key is unset (honest no-key). Preserves the status
 *  on ApiError so the caller can distinguish no-key from a transient. */
export async function transcribeAudio(audio: Blob): Promise<TranscribeResponse> {
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
  /** How many times this note has changed (a living-note signal). */
  refinement_count: number;
  /** A question whose challenge needs new research (escalation seam). */
  escalated: boolean;
  escalated_question_id?: string | null;
  /** The reserved (NOT launched) child research id; SPR-04/05 launch it. */
  reserved_child_investigation_id?: string | null;
}

export interface DistillationResponse {
  investigation_id: string;
  insights: DistilledNode[];
  questions: DistilledNode[];
}

/** ANT-AHT — outline blocks for Write drag (same node_ids as distill). */
export interface ResearchArtifactBlock {
  node_id: string;
  kind: string;
  label: string;
  investigation_id: string;
}

export interface ResearchArtifactBlocksResponse {
  investigation_id: string;
  blocks: ResearchArtifactBlock[];
}

export interface ResearchArtifactExportResponse {
  investigation_id: string;
  view_url: string;
  content_hash: string;
  size_bytes: number;
  event_id: string | null;
}

export interface ResearchArtifactInheritedClaimSupport {
  unit_id: string;
  qualification_state: "complete" | "partial" | "unknown" | "legacy_unqualified";
  source_investigation_id: string | null;
  supporting_leaf_investigation_id: string;
}

export interface ResearchArtifactClaimSupport {
  claim_index: number;
  claim: string;
  supporting_chunk_ids: string[];
  supporting_path_indices: number[];
  inherited_support: ResearchArtifactInheritedClaimSupport[];
  direct_evidence: Array<{
    source_kind: "synthesis_claim";
    source_asset_id: string;
    claim_id: string;
    chunk_ids: string[];
    document_id: string;
    receipt_sha256: string;
  }>;
  evaluation: {
    advisory: true;
    event_id: string;
    scorer_id: string;
    backend: string;
    score: number;
    supported: boolean;
    supported_threshold: number;
    relation: "entailed" | "contradicted" | "not_established" | null;
  } | null;
  reviews?: Array<{
    schema_version: 1;
    status:
      | "later_owner_accepted_counter_analysis"
      | "later_owner_reversed_counter_analysis";
    challenge_receipt_sha256: string;
    acceptance_receipt_sha256: string;
    reversal_receipt_sha256: string | null;
    session_id: string;
    spawn_id: string;
    candidate_sha256: string;
    candidate_text: string;
    evaluation_event_id: string;
    evidence_receipt_sha256s: string[];
    grants_authority: false;
  }>;
  reconsiderations?: Array<{
    schema_version: 1;
    status: "owner_authored_reconsideration_proposal";
    receipt_sha256: string;
    selected_acceptance_receipt_sha256s: string[];
    proposed_claim: string;
    rationale: string;
    grants_authority: false;
  }>;
  owner_revision?: null | {
    status: "owner_accepted_claim_revision";
    prior_artifact_content_hash: string;
    proposal_receipt_sha256: string;
    transition_sha256: string;
    revised_claim: string;
    rationale: string;
    effective_claim: string;
    head_transition_sha256: string;
    compensations: Array<{
      operation: "restore_archived_terminal" | "supersede_owner_revision";
      prior_artifact_content_hash: string;
      supersedes_transition_sha256: string;
      transition_sha256: string;
      prior_effective_claim: string;
      replacement_claim: string;
      rationale: string;
      source_context_receipt_sha256: string | null;
      source_review_receipt_sha256: string | null;
      source_proposal_receipt_sha256: string | null;
      archive_grounded: false;
      grants_authority: false;
    }>;
    archive_grounded: false;
    grants_authority: false;
  };
}

export interface ResearchArtifactClaimChallengeReceipt {
  schema_version: 1 | 2;
  owner_account_digest: string;
  source_asset_id: string;
  artifact_content_hash: string;
  synthesis_event_id: string;
  claim_index: number;
  claim_id: string;
  claim_sha256: string;
  evaluation_event_id: string | null;
  scorer_id: string | null;
  relation: "entailed" | "contradicted" | "not_established" | null;
  score: number | null;
  evidence_receipt_sha256s: string[];
  model_id: string | null;
  research_tier: "fast" | "deep" | "wrestle";
  goal_sha256: string;
  receipt_sha256: string;
  selection_kind?: "effective_owner_claim" | null;
  purpose?: "investigate_effective_owner_claim" | null;
  question_sha256?: string | null;
  artifact_investigation_digest?: string | null;
  archived_claim?: string | null;
  archived_claim_sha256?: string | null;
  effective_claim?: string | null;
  root_transition_sha256?: string | null;
  head_transition_sha256?: string | null;
  revision_transition_sha256s?: string[];
  revision_chain_sha256?: string | null;
  mutation_key_sha256?: string | null;
  archived_evaluation_event_id?: string | null;
  archived_scorer_id?: string | null;
  archived_relation?: "entailed" | "contradicted" | "not_established" | null;
  archived_score?: number | null;
  archived_evidence_receipt_sha256s?: string[];
  archived_inherited_support?: Array<{
    unit_id: string;
    qualification_state: "complete" | "partial" | "unknown" | "legacy_unqualified";
    source_investigation_id: string | null;
    supporting_leaf_investigation_id: string;
  }>;
  archived_evidence_sha256?: string | null;
  archive_grounded?: false | null;
  grants_authority?: false | null;
  permits_provider_call?: false | null;
  permits_spend?: false | null;
  permits_graph_admission?: false | null;
  permits_write?: false | null;
  permits_benchmark_feedback?: false | null;
  permits_publication?: false | null;
}

export interface EffectiveClaimIteration {
  ordinal: number;
  prior_artifact_content_hash: string;
  result_artifact_content_hash: string;
  claim_index: number;
  archived_claim: string;
  prior_effective_claim: string;
  candidate_text: string;
  candidate_sha256: string;
  review_rationale: string;
  proposed_claim: string;
  replacement_claim: string;
  context_receipt_sha256: string;
  review_receipt_sha256: string;
  proposal_receipt_sha256: string;
  transition_sha256: string;
  session_id: string;
  spawn_id: string;
  question: string;
  purpose: string;
  model_id: string | null;
  research_tier: string;
  prior_html_url: string;
  result_html_url: string;
  result_is_current: boolean;
  archive_grounded: false;
  grants_authority: false;
  permits_graph_admission: false;
  permits_write: false;
  permits_benchmark_feedback: false;
  permits_publication: false;
  permits_provider_call: false;
  permits_spend: false;
}

export interface EffectiveClaimIterationsResponse {
  investigation_id: string;
  claim_index: number;
  artifact_content_hash: string;
  current_effective_claim: string;
  current_head_transition_sha256: string;
  next_round_eligible: boolean;
  rounds: EffectiveClaimIteration[];
}

export interface ReasoningAncestryNode {
  ordinal: number;
  transition_sha256: string;
  session_id: string;
  spawn_id: string;
  candidate_sha256: string;
  parent_ordinals: number[];
  child_ordinals: number[];
  inherited_questions: string[];
  depth: number;
  is_root: boolean;
  is_recombination: boolean;
  recursive_pack_receipt_sha256: string | null;
  recursive_context_pack: Record<string, unknown> | null;
  ancestry_sha256: string;
  prior_html_url: string;
  result_html_url: string;
  archive_grounded: false;
  grants_authority: false;
  permits_graph_admission: false;
  permits_write: false;
  permits_benchmark_feedback: false;
  permits_publication: false;
  permits_provider_call: false;
  permits_spend: false;
}

export interface ReasoningAncestryResponse {
  investigation_id: string;
  claim_index: number;
  artifact_content_hash: string;
  current_effective_claim: string;
  current_head_transition_sha256: string;
  graph_sha256: string;
  nodes: ReasoningAncestryNode[];
}

export interface ReasoningAncestryInterrogationCommand {
  content_hash: string;
  selected_terminal_ordinals: number[];
  question: string;
  mutation_key: string;
}

export interface ReasoningAncestryInterrogationResponse {
  status: "candidate" | "accepted";
  preview_sha256: string;
  receipt: {
    receipt_id: string;
    receipt_sha256: string;
    artifact_content_hash: string;
    head_transition_sha256: string;
    selected_terminal_ordinals: number[];
    closure_ordinals: number[];
    ordered_spawn_ids: string[];
    question: string;
    collective_id: string;
    manifest_id: string;
    membership_sha256: string;
    archive_grounded: false;
    grants_authority: false;
    permits_provider_call: false;
    permits_spend: false;
    permits_graph_admission: false;
    permits_write: false;
    permits_benchmark_feedback: false;
    permits_publication: false;
  };
  manifest: {
    manifest_id: string;
    collective_id: string;
    ordered_spawn_ids: string[];
    membership_sha256: string;
    availability: "ready" | "unavailable";
    view_format: "html";
  };
  stale: boolean;
}

export interface AncestryContinuationChoice {
  role: "synthesizer";
  projection_scope: "selected_synthesizer_call_only";
  provider_id: string;
  model_id: string;
  fallback_index: number;
  route_identity: string;
  pricing_fingerprint: string;
  estimated_usd_low: number;
  estimated_usd_high: number;
  remaining_after_high_usd: number | null;
  would_exceed_budget: boolean | null;
  pricing_source_url: string;
  pricing_verified_at: string;
  pricing_expires_at: string;
  boot_ready: boolean;
  available: boolean;
  reason: string;
  whole_run_envelope: AncestryWholeRunEnvelope;
}

export interface AncestryWholeRunRoleEnvelope {
  role: string;
  mandatory_calls: number;
  conditional_calls: number;
  max_calls: number;
  selected_route_only: boolean;
  route_max_usd: string;
  role_max_usd: string;
  pricing_fingerprints: string[];
}

export interface AncestryWholeRunEnvelope {
  schema_version: 1;
  projection_kind: "admission_upper_bound";
  plan_sha256: string;
  maximum_usd: string;
  forecast_usd_low: null;
  forecast_usd_high: null;
  forecast_status: "not_measured";
  roles: AncestryWholeRunRoleEnvelope[];
}

export interface AncestryContinuationOptions {
  schema_version: 1;
  investigation_id: string;
  receipt_id: string;
  receipt_sha256: string;
  context_sha256: string;
  task_class: "ancestry_collective_continuation";
  stale: boolean;
  assumed_input_tokens: number;
  whole_run_cost_projected: true;
  choices: AncestryContinuationChoice[];
  budget: { daily_cap_usd?: number | null; spent_usd?: number | null; remaining_usd?: number | null; spent_status?: string };
  view_format: "html";
  action_authority: false;
}

export interface AncestryContinuationCommand {
  expected_receipt_sha256: string;
  provider_id: string;
  model_id: string;
  pricing_fingerprint: string;
  research_tier: "fast" | "deep" | "wrestle";
  approved_run_ceiling_usd: number;
}

export interface AncestryContinuationQuote {
  quote_token: string;
  quote_id: string;
  quote_payload_sha256: string;
  route_manifest_fingerprint: string;
  context_sha256: string;
  receipt_sha256: string;
  selected_driver_role: "synthesizer";
  selected_driver_provider: string;
  selected_driver_model: string;
  selected_driver_pricing_fingerprint: string;
  workload_plan_sha256: string;
  whole_run_maximum_usd: string;
  approved_run_ceiling_usd: string;
  issued_at_ms: number;
  expires_at_ms: number;
  view_format: "html";
  spend_performed: false;
}

export interface AncestryContinuationLaunch {
  investigation_id: string;
  status: "started";
  start_event_id: string;
  parent_investigation_id: string;
  ancestry_interrogation_receipt_id: string;
  selected_driver_provider: string;
  selected_driver_model: string;
  view_format: "html";
}

export interface RecursiveRoundContextCommand {
  content_hash: string;
  selected_round_ordinals: number[];
  follow_up_questions: string[];
  mutation_key: string;
  view_mode?: "floating" | "full";
  model_id?: string | null;
  research_tier?: "fast" | "deep" | "wrestle";
}

export interface RecursiveRoundContextPreview {
  receipt_sha256: string;
  pack_sha256: string;
  artifact_content_hash: string;
  current_effective_claim: string;
  current_head_transition_sha256: string;
  selected_round_ordinals: number[];
  selected_transition_sha256s: string[];
  follow_up_questions: string[];
  rows: Array<Record<string, unknown>>;
  pack_bytes: number;
  view_mode: "floating" | "full";
  preview_sha256: string;
  archive_grounded: false;
  grants_authority: false;
  permits_provider_call: false;
  permits_spend: false;
  permits_graph_admission: false;
  permits_twin_promotion: false;
  permits_write: false;
  permits_benchmark_feedback: false;
  permits_publication: false;
}

export interface RecursiveRoundContextResponse {
  status: "candidate" | "accepted";
  preview: RecursiveRoundContextPreview | null;
  reservation: ResearchArtifactClaimChallengeResponse | null;
}

export interface EffectiveOwnerContextPreview {
  artifact_content_hash: string;
  archived_claim: string;
  effective_claim: string;
  head_transition_sha256: string;
  receipt_sha256: string;
  preview_sha256: string;
  revision_transition_sha256s: string[];
  archive_grounded: false;
  grants_authority: false;
  permits_provider_call: false;
  permits_spend: false;
  permits_graph_admission: false;
  permits_write: false;
  permits_benchmark_feedback: false;
  permits_publication: false;
}

export interface EffectiveOwnerContextCommand {
  content_hash: string;
  goal: string;
  mutation_key: string;
  view_mode?: "floating" | "full";
  model_id?: string | null;
  research_tier?: "fast" | "deep" | "wrestle";
}

export interface EffectiveOwnerContextAcceptCommand extends EffectiveOwnerContextCommand {
  preview_sha256: string;
  receipt_sha256: string;
}

export interface ResearchArtifactClaimChallengeResponse {
  session_id: string;
  spawn_id: string;
  investigation_id: string;
  parent_asset_id: string;
  selection_text: string;
  status: string;
  view_mode: "floating" | "full";
  model_id: string | null;
  research_tier: string;
  view_format: "html";
  claim_challenge: ResearchArtifactClaimChallengeReceipt;
}

export interface ClaimReviewAcceptance {
  schema_version: 1;
  kind: "claim_challenge_acceptance";
  receipt_sha256: string;
  candidate_sha256: string;
  candidate_text: string;
  preview_sha256: string;
}

export interface ClaimReviewReversal {
  schema_version: 1;
  kind: "claim_challenge_reversal";
  receipt_sha256: string;
  acceptance_receipt_sha256: string;
  rationale: string;
}

export type EffectiveContextReviewCommand = {
  content_hash: string;
  disposition: "retain_current" | "propose_compensation";
  rationale: string;
  proposed_claim: string | null;
};

export type EffectiveContextReviewResponse = {
  status: "candidate" | "accepted";
  preview: {
    artifact_content_hash: string;
    claim_index: number;
    context_receipt_sha256: string;
    head_transition_sha256: string;
    archived_claim: string;
    effective_claim: string;
    candidate_sha256: string;
    candidate_text: string;
    archived_evaluation: {
      event_id: string;
      scorer_id: string;
      relation: "entailed" | "contradicted" | "not_established" | null;
      score: number;
    };
    archived_direct_evidence_receipt_sha256s: string[];
    archived_inherited_support: Array<{
      unit_id: string;
      qualification_state: "complete" | "partial" | "unknown" | "legacy_unqualified";
      source_investigation_id: string | null;
      supporting_leaf_investigation_id: string;
    }>;
    disposition: "retain_current" | "propose_compensation";
    rationale: string;
    proposed_claim: string | null;
    preview_sha256: string;
    archive_grounded: false;
    grants_authority: false;
    permits_canonical_append: false;
  };
  acceptance: null | {
    receipt_sha256: string;
    disposition: "retain_current" | "propose_compensation";
    rationale: string;
    permits_canonical_append: false;
    archive_grounded: false;
    grants_authority: false;
    permits_graph_admission: false;
    permits_write: false;
    permits_benchmark_feedback: false;
    permits_publication: false;
    permits_provider_call: false;
    permits_spend: false;
  };
  proposal: null | {
    receipt_sha256: string;
    review_receipt_sha256: string;
    proposed_claim: string;
    rationale: string;
    permits_canonical_append: false;
    grants_authority: false;
  };
};

export type EffectiveContextReviewReadResponse = {
  status: "accepted";
  archived_claim: string;
  archived_evaluation: EffectiveContextReviewResponse["preview"]["archived_evaluation"];
  archived_direct_evidence_receipt_sha256s: string[];
  archived_inherited_support: EffectiveContextReviewResponse["preview"]["archived_inherited_support"];
  effective_claim: string;
  candidate_text: string;
  acceptance: NonNullable<EffectiveContextReviewResponse["acceptance"]>;
  proposal: EffectiveContextReviewResponse["proposal"];
  consumption: EffectiveContextCompensationResponse["acceptance"];
};

export type EffectiveContextCompensationResponse = {
  status: "candidate" | "accepted";
  preview: null | {
    prior_artifact_content_hash: string;
    prospective_artifact_content_hash: string;
    supersedes_transition_sha256: string;
    prior_effective_claim: string;
    replacement_claim: string;
    rationale: string;
    transition_sha256: string;
    preview_sha256: string;
    source_context_receipt_sha256: string;
    source_review_receipt_sha256: string;
    source_proposal_receipt_sha256: string;
  };
  acceptance: null | {
    artifact_content_hash: string;
    transition_sha256: string;
    effective_owner_claim: string;
    source_context_receipt_sha256: string;
    source_review_receipt_sha256: string;
    source_proposal_receipt_sha256: string;
    archive_grounded: false;
    grants_authority: false;
  };
};

export interface ClaimReviewResponse {
  status: "candidate" | "accepted" | "reversed";
  preview: {
    preview_sha256: string;
    candidate_sha256: string;
    candidate_text: string;
    html: string;
    view_format: "html";
  } | null;
  acceptance: ClaimReviewAcceptance | null;
  reversal: ClaimReviewReversal | null;
  view_format: "html";
}

export interface ResearchArtifactClaimsResponse {
  investigation_id: string;
  content_hash: string;
  claims: ResearchArtifactClaimSupport[];
}

export type InvestigationPromotionGate =
  | "status"
  | "recommendation"
  | "no_source_nodes"
  | "all_dangling";

export interface InvestigationPromotionResponse {
  deliverable_id: string;
  section_id: string;
  block_count: number;
  dangling_count: number;
  source_node_count: number;
  /** Deprecated server compatibility field; promotion eligibility is conveyed
   * by the typed 409 refusal rather than a successful insufficient draft. */
  insufficient_evidence: boolean;
  synthesis_id: string | null;
  synthesis_status: string | null;
  synthesis_recommendation: string | null;
}

export type InvestigationPromotionFailure =
  | { kind: "no_synthesis"; reason: string }
  | {
      kind: "not_promotable";
      reason: string;
      gate_failed: InvestigationPromotionGate;
    }
  | { kind: "unknown"; reason: string | null };

/** Start a provenance-preserving Write deliverable from the authoritative
 * completed synthesis. The server owns every eligibility decision. */
export async function promoteInvestigationToWrite(
  investigationId: string,
): Promise<InvestigationPromotionResponse> {
  const resp = await apiFetch(`${API_BASE}/write/deliverables/from-investigation`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      investigation_id: investigationId,
      deliverable_kind: "research_memo",
    }),
  });
  if (!resp.ok) {
    throw new ApiError(
      `POST /write/deliverables/from-investigation failed: HTTP ${resp.status}`,
      resp.status,
      await resp.text(),
    );
  }
  return resp.json();
}

/** Decode only the closed 404/409 promotion contract. Unknown envelopes stay
 * unknown so UI copy never guesses why evidence admission refused a draft. */
export function classifyInvestigationPromotionFailure(
  error: unknown,
): InvestigationPromotionFailure {
  if (!(error instanceof ApiError)) return { kind: "unknown", reason: null };
  try {
    const envelope = JSON.parse(error.body) as { detail?: unknown };
    const detail = envelope.detail;
    if (typeof detail !== "object" || detail === null) {
      return { kind: "unknown", reason: null };
    }
    const value = detail as Record<string, unknown>;
    const reason = typeof value.reason === "string" ? value.reason : "";
    if (error.status === 404 && value.error === "no_synthesis" && reason) {
      return { kind: "no_synthesis", reason };
    }
    if (
      error.status === 409 &&
      value.error === "not_promotable" &&
      reason &&
      ["status", "recommendation", "no_source_nodes", "all_dangling"].includes(
        String(value.gate_failed),
      )
    ) {
      return {
        kind: "not_promotable",
        reason,
        gate_failed: value.gate_failed as InvestigationPromotionGate,
      };
    }
  } catch {
    return { kind: "unknown", reason: null };
  }
  return { kind: "unknown", reason: null };
}

/** GET /research/{id}/artifact/blocks — Lego refs for Write outline drops. */
export async function getResearchArtifactBlocks(
  investigationId: string,
): Promise<ResearchArtifactBlocksResponse> {
  const resp = await apiFetch(
    `${API_BASE}/research/${encodeURIComponent(investigationId)}/artifact/blocks`,
  );
  if (!resp.ok) {
    throw new ApiError(
      `GET /research/{id}/artifact/blocks failed: HTTP ${resp.status}`,
      resp.status,
      await resp.text(),
    );
  }
  return resp.json();
}

/** Canonical, account-gated claim-support projection. This is deliberately
 * separate from the HTML view so clients never parse provenance from markup. */
export async function getResearchArtifactClaims(
  investigationId: string,
): Promise<ResearchArtifactClaimsResponse> {
  const resp = await apiFetch(
    `${API_BASE}/research/${encodeURIComponent(investigationId)}/artifact/claims`,
  );
  if (!resp.ok) {
    throw new ApiError(
      `GET /research/{id}/artifact/claims failed: HTTP ${resp.status}`,
      resp.status,
      await resp.text(),
    );
  }
  return resp.json();
}

export async function getResearchArtifactClaim(
  investigationId: string,
  claimIndex: number,
  contentHash: string,
): Promise<ResearchArtifactClaimSupport> {
  const query = new URLSearchParams({ content_hash: contentHash });
  const resp = await apiFetch(
    `${API_BASE}/research/${encodeURIComponent(investigationId)}/artifact/claims/${claimIndex}?${query}`,
  );
  if (!resp.ok) {
    throw new ApiError(
      `GET /research/{id}/artifact/claims/{index} failed: HTTP ${resp.status}`,
      resp.status,
      await resp.text(),
    );
  }
  return resp.json();
}

export async function getEffectiveClaimIterations(
  investigationId: string,
  claimIndex: number,
): Promise<EffectiveClaimIterationsResponse> {
  const resp = await apiFetch(
    `${API_BASE}/research/${encodeURIComponent(investigationId)}/artifact/claims/${claimIndex}/owner-iterations`,
  );
  if (!resp.ok) {
    throw new ApiError(
      `GET effective claim iterations failed: HTTP ${resp.status}`,
      resp.status,
      await resp.text(),
    );
  }
  return resp.json();
}

export async function getReasoningAncestry(
  investigationId: string,
  claimIndex: number,
): Promise<ReasoningAncestryResponse> {
  const resp = await apiFetch(
    `${API_BASE}/research/${encodeURIComponent(investigationId)}/artifact/claims/${claimIndex}/owner-ancestry`,
  );
  if (!resp.ok) {
    throw new ApiError(
      `GET reasoning ancestry failed: HTTP ${resp.status}`,
      resp.status,
      await resp.text(),
    );
  }
  return resp.json();
}

export async function previewReasoningAncestryInterrogation(
  investigationId: string,
  claimIndex: number,
  body: ReasoningAncestryInterrogationCommand,
): Promise<ReasoningAncestryInterrogationResponse> {
  const resp = await apiFetch(
    `${API_BASE}/research/${encodeURIComponent(investigationId)}/artifact/claims/${claimIndex}/ancestry-interrogation/preview`,
    { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) },
  );
  if (!resp.ok) throw new ApiError(`POST ancestry interrogation preview failed: HTTP ${resp.status}`, resp.status, await resp.text());
  return resp.json();
}

export async function acceptReasoningAncestryInterrogation(
  investigationId: string,
  claimIndex: number,
  body: ReasoningAncestryInterrogationCommand & { preview_sha256: string; receipt_sha256: string },
): Promise<ReasoningAncestryInterrogationResponse> {
  const resp = await apiFetch(
    `${API_BASE}/research/${encodeURIComponent(investigationId)}/artifact/claims/${claimIndex}/ancestry-interrogation/accept`,
    { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) },
  );
  if (!resp.ok) throw new ApiError(`POST ancestry interrogation accept failed: HTTP ${resp.status}`, resp.status, await resp.text());
  return resp.json();
}

export async function getReasoningAncestryInterrogation(
  investigationId: string,
  receiptId: string,
  signal?: AbortSignal,
): Promise<ReasoningAncestryInterrogationResponse> {
  const resp = await apiFetch(
    `${API_BASE}/research/${encodeURIComponent(investigationId)}/artifact/ancestry-interrogations/${encodeURIComponent(receiptId)}`,
    { signal },
  );
  if (!resp.ok) throw new ApiError(`GET ancestry interrogation failed: HTTP ${resp.status}`, resp.status, await resp.text());
  return resp.json();
}

export async function getAncestryContinuationOptions(
  investigationId: string,
  receiptId: string,
  signal?: AbortSignal,
): Promise<AncestryContinuationOptions> {
  const resp = await apiFetch(
    `${API_BASE}/research/${encodeURIComponent(investigationId)}/artifact/ancestry-interrogations/${encodeURIComponent(receiptId)}/continuation-options`,
    { signal },
  );
  if (!resp.ok) throw new ApiError(`GET ancestry continuation options failed: HTTP ${resp.status}`, resp.status, await resp.text());
  return resp.json();
}

export async function quoteAncestryContinuation(
  investigationId: string,
  receiptId: string,
  body: AncestryContinuationCommand,
  signal?: AbortSignal,
): Promise<AncestryContinuationQuote> {
  const resp = await apiFetch(
    `${API_BASE}/research/${encodeURIComponent(investigationId)}/artifact/ancestry-interrogations/${encodeURIComponent(receiptId)}/continuation/quote`,
    { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body), signal },
  );
  if (!resp.ok) throw new ApiError(`POST ancestry continuation quote failed: HTTP ${resp.status}`, resp.status, await resp.text());
  return resp.json();
}

export async function launchAncestryContinuation(
  investigationId: string,
  receiptId: string,
  body: AncestryContinuationCommand & { research_quote_token: string },
  signal?: AbortSignal,
): Promise<AncestryContinuationLaunch> {
  const resp = await apiFetch(
    `${API_BASE}/research/${encodeURIComponent(investigationId)}/artifact/ancestry-interrogations/${encodeURIComponent(receiptId)}/continuation`,
    { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body), signal },
  );
  if (!resp.ok) throw new ApiError(`POST ancestry continuation failed: HTTP ${resp.status}`, resp.status, await resp.text());
  return resp.json();
}

export async function previewRecursiveRoundContext(
  investigationId: string,
  claimIndex: number,
  body: RecursiveRoundContextCommand,
): Promise<RecursiveRoundContextResponse> {
  const resp = await apiFetch(
    `${API_BASE}/research/${encodeURIComponent(investigationId)}/artifact/claims/${claimIndex}/recursive-context/preview`,
    { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) },
  );
  if (!resp.ok) throw new ApiError(`POST recursive context preview failed: HTTP ${resp.status}`, resp.status, await resp.text());
  return resp.json();
}

export async function acceptRecursiveRoundContext(
  investigationId: string,
  claimIndex: number,
  body: RecursiveRoundContextCommand & { preview_sha256: string; receipt_sha256: string },
): Promise<RecursiveRoundContextResponse> {
  const resp = await apiFetch(
    `${API_BASE}/research/${encodeURIComponent(investigationId)}/artifact/claims/${claimIndex}/recursive-context/accept`,
    { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) },
  );
  if (!resp.ok) throw new ApiError(`POST recursive context accept failed: HTTP ${resp.status}`, resp.status, await resp.text());
  return resp.json();
}

export async function reserveResearchArtifactClaimChallenge(
  investigationId: string,
  claimIndex: number,
  body: {
    content_hash: string;
    goal: string;
    view_mode?: "floating" | "full";
    model_id?: string | null;
    research_tier?: "fast" | "deep" | "wrestle";
  },
): Promise<ResearchArtifactClaimChallengeResponse> {
  const resp = await apiFetch(
    `${API_BASE}/research/${encodeURIComponent(investigationId)}/artifact/claims/${claimIndex}/challenge`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    },
  );
  if (!resp.ok) {
    throw new ApiError(
      `POST /research/{id}/artifact/claims/{index}/challenge failed: HTTP ${resp.status}`,
      resp.status,
      await resp.text(),
    );
  }
  return resp.json();
}

async function effectiveOwnerContextCommand(
  investigationId: string,
  claimIndex: number,
  action: "preview" | "accept",
  body: EffectiveOwnerContextCommand | EffectiveOwnerContextAcceptCommand,
): Promise<{
  status: "candidate" | "accepted";
  preview: EffectiveOwnerContextPreview | null;
  reservation: ResearchArtifactClaimChallengeResponse | null;
}> {
  const resp = await apiFetch(
    `${API_BASE}/research/${encodeURIComponent(investigationId)}/artifact/claims/${claimIndex}/owner-context/${action}`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    },
  );
  if (!resp.ok) {
    throw new ApiError(
      `POST owner-context/${action} failed: HTTP ${resp.status}`,
      resp.status,
      await resp.text(),
    );
  }
  return resp.json();
}

export const previewEffectiveOwnerContext = (
  investigationId: string,
  claimIndex: number,
  body: EffectiveOwnerContextCommand,
) => effectiveOwnerContextCommand(investigationId, claimIndex, "preview", body);

export const acceptEffectiveOwnerContext = (
  investigationId: string,
  claimIndex: number,
  body: EffectiveOwnerContextAcceptCommand,
) => effectiveOwnerContextCommand(investigationId, claimIndex, "accept", body);

async function claimReviewCommand(
  investigationId: string,
  sessionId: string,
  action: "preview" | "accept" | "reverse",
  body: Record<string, unknown>,
): Promise<ClaimReviewResponse> {
  const resp = await apiFetch(
    `${API_BASE}/research/${encodeURIComponent(investigationId)}/artifact/claim-challenges/${encodeURIComponent(sessionId)}/review/${action}`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    },
  );
  if (!resp.ok) {
    throw new ApiError(
      `POST claim challenge review/${action} failed: HTTP ${resp.status}`,
      resp.status,
      await resp.text(),
    );
  }
  return resp.json();
}

export const previewClaimChallengeReview = (
  investigationId: string,
  sessionId: string,
  contentHash: string,
) =>
  claimReviewCommand(investigationId, sessionId, "preview", {
    content_hash: contentHash,
  });

export const acceptClaimChallengeReview = (
  investigationId: string,
  sessionId: string,
  body: { content_hash: string; preview_sha256: string; mutation_key: string },
) => claimReviewCommand(investigationId, sessionId, "accept", body);

async function effectiveContextReviewCommand(
  investigationId: string,
  sessionId: string,
  action: "preview" | "accept",
  body: EffectiveContextReviewCommand & {
    preview_sha256?: string;
    mutation_key?: string;
  },
): Promise<EffectiveContextReviewResponse> {
  const resp = await apiFetch(
    `${API_BASE}/research/${encodeURIComponent(investigationId)}/artifact/owner-contexts/${encodeURIComponent(sessionId)}/review/${action}`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    },
  );
  if (!resp.ok) {
    throw new ApiError(
      `POST effective context review/${action} failed: HTTP ${resp.status}`,
      resp.status,
      await resp.text(),
    );
  }
  return resp.json();
}

export const previewEffectiveContextReview = (
  investigationId: string,
  sessionId: string,
  body: EffectiveContextReviewCommand,
) => effectiveContextReviewCommand(investigationId, sessionId, "preview", body);

export const acceptEffectiveContextReview = (
  investigationId: string,
  sessionId: string,
  body: EffectiveContextReviewCommand & {
    preview_sha256: string;
    mutation_key: string;
  },
) => effectiveContextReviewCommand(investigationId, sessionId, "accept", body);

export async function getEffectiveContextReview(
  investigationId: string,
  sessionId: string,
): Promise<EffectiveContextReviewReadResponse> {
  const resp = await apiFetch(
    `${API_BASE}/research/${encodeURIComponent(investigationId)}/artifact/owner-contexts/${encodeURIComponent(sessionId)}/review`,
  );
  if (!resp.ok) {
    throw new ApiError(
      `GET effective context review failed: HTTP ${resp.status}`,
      resp.status,
      await resp.text(),
    );
  }
  return resp.json();
}

async function effectiveContextCompensationCommand(
  investigationId: string,
  sessionId: string,
  action: "preview" | "accept",
  body: {
    content_hash: string;
    proposal_receipt_sha256: string;
    mutation_key: string;
    preview_sha256?: string;
    transition_sha256?: string;
  },
): Promise<EffectiveContextCompensationResponse> {
  const resp = await apiFetch(
    `${API_BASE}/research/${encodeURIComponent(investigationId)}/artifact/owner-contexts/${encodeURIComponent(sessionId)}/review/compensation/${action}`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    },
  );
  if (!resp.ok) {
    throw new ApiError(
      `POST effective context compensation/${action} failed: HTTP ${resp.status}`,
      resp.status,
      await resp.text(),
    );
  }
  return resp.json();
}

export const previewEffectiveContextCompensation = (
  investigationId: string,
  sessionId: string,
  body: {
    content_hash: string;
    proposal_receipt_sha256: string;
    mutation_key: string;
  },
) => effectiveContextCompensationCommand(investigationId, sessionId, "preview", body);

export const acceptEffectiveContextCompensation = (
  investigationId: string,
  sessionId: string,
  body: {
    content_hash: string;
    proposal_receipt_sha256: string;
    mutation_key: string;
    preview_sha256: string;
    transition_sha256: string;
  },
) => effectiveContextCompensationCommand(investigationId, sessionId, "accept", body);

export const reverseClaimChallengeReview = (
  investigationId: string,
  sessionId: string,
  body: {
    content_hash: string;
    acceptance_receipt_sha256: string;
    rationale: string;
    mutation_key: string;
  },
) => claimReviewCommand(investigationId, sessionId, "reverse", body);

export interface ClaimReconsiderationCommandResponse {
  status: "candidate" | "created";
  preview: null | {
    preview_sha256: string;
    proposed_claim: string;
    rationale: string;
    html: string;
  };
  proposal: null | {
    receipt_sha256: string;
    proposed_claim: string;
    rationale: string;
    grants_authority: false;
  };
  view_format: "html";
}

async function claimReconsiderationCommand(
  investigationId: string,
  claimIndex: number,
  action: "preview" | "create",
  body: Record<string, unknown>,
): Promise<ClaimReconsiderationCommandResponse> {
  const resp = await apiFetch(
    `${API_BASE}/research/${encodeURIComponent(investigationId)}/artifact/claims/${claimIndex}/reconsideration/${action}`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    },
  );
  if (!resp.ok) {
    throw new ApiError(
      `POST claim reconsideration/${action} failed: HTTP ${resp.status}`,
      resp.status,
      await resp.text(),
    );
  }
  return resp.json();
}

export const previewClaimReconsideration = (
  investigationId: string,
  claimIndex: number,
  body: {
    content_hash: string;
    acceptance_receipt_sha256s: string[];
    proposed_claim: string;
    rationale: string;
  },
) => claimReconsiderationCommand(investigationId, claimIndex, "preview", body);

export const createClaimReconsideration = (
  investigationId: string,
  claimIndex: number,
  body: {
    content_hash: string;
    acceptance_receipt_sha256s: string[];
    proposed_claim: string;
    rationale: string;
    preview_sha256: string;
    mutation_key: string;
  },
) => claimReconsiderationCommand(investigationId, claimIndex, "create", body);

export interface ClaimRevisionCommandResponse {
  status: "candidate" | "accepted";
  preview: null | {
    prior_artifact_content_hash: string;
    prospective_artifact_content_hash: string;
    proposal_receipt_sha256: string;
    transition_sha256: string;
    preview_sha256: string;
    original_claim: string;
    revised_claim: string;
    rationale: string;
    html: string;
  };
  acceptance: null | {
    prior_artifact_content_hash: string;
    artifact_content_hash: string;
    proposal_receipt_sha256: string;
    transition_sha256: string;
    history_content_hash: string;
    archive_grounded: false;
    grants_authority: false;
  };
  view_format: "html";
}

async function claimRevisionCommand(
  investigationId: string,
  claimIndex: number,
  action: "preview" | "accept",
  body: Record<string, unknown>,
): Promise<ClaimRevisionCommandResponse> {
  const resp = await apiFetch(
    `${API_BASE}/research/${encodeURIComponent(investigationId)}/artifact/claims/${claimIndex}/revision/${action}`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    },
  );
  if (!resp.ok) {
    throw new ApiError(
      `POST claim revision/${action} failed: HTTP ${resp.status}`,
      resp.status,
      await resp.text(),
    );
  }
  return resp.json();
}

export const previewClaimRevision = (
  investigationId: string,
  claimIndex: number,
  body: { content_hash: string; proposal_receipt_sha256: string; mutation_key: string },
) => claimRevisionCommand(investigationId, claimIndex, "preview", body);

export const acceptClaimRevision = (
  investigationId: string,
  claimIndex: number,
  body: {
    content_hash: string;
    proposal_receipt_sha256: string;
    mutation_key: string;
    preview_sha256: string;
    transition_sha256: string;
  },
) => claimRevisionCommand(investigationId, claimIndex, "accept", body);

export interface ClaimRevisionCompensationCommandResponse {
  status: "candidate" | "accepted";
  preview: null | {
    operation: "restore_archived_terminal" | "supersede_owner_revision";
    prior_artifact_content_hash: string;
    prospective_artifact_content_hash: string;
    supersedes_transition_sha256: string;
    prior_effective_claim: string;
    replacement_claim: string;
    rationale: string;
    transition_sha256: string;
    preview_sha256: string;
    html: string;
  };
  acceptance: null | {
    operation: "restore_archived_terminal" | "supersede_owner_revision";
    prior_artifact_content_hash: string;
    artifact_content_hash: string;
    supersedes_transition_sha256: string;
    transition_sha256: string;
    history_content_hash: string;
    effective_owner_claim: string;
    archive_grounded: false;
    grants_authority: false;
  };
  view_format: "html";
}

async function claimRevisionCompensationCommand(
  investigationId: string,
  claimIndex: number,
  action: "preview" | "accept",
  body: Record<string, unknown>,
): Promise<ClaimRevisionCompensationCommandResponse> {
  const resp = await apiFetch(
    `${API_BASE}/research/${encodeURIComponent(investigationId)}/artifact/claims/${claimIndex}/revision/compensation/${action}`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    },
  );
  if (!resp.ok) {
    throw new ApiError(
      `POST claim revision compensation/${action} failed: HTTP ${resp.status}`,
      resp.status,
      await resp.text(),
    );
  }
  return resp.json();
}

export const previewClaimRevisionCompensation = (
  investigationId: string,
  claimIndex: number,
  body: {
    content_hash: string;
    supersedes_transition_sha256: string;
    operation: "restore_archived_terminal" | "supersede_owner_revision";
    replacement_claim: string | null;
    rationale: string;
    mutation_key: string;
  },
) => claimRevisionCompensationCommand(investigationId, claimIndex, "preview", body);

export const acceptClaimRevisionCompensation = (
  investigationId: string,
  claimIndex: number,
  body: {
    content_hash: string;
    supersedes_transition_sha256: string;
    operation: "restore_archived_terminal" | "supersede_owner_revision";
    replacement_claim: string | null;
    rationale: string;
    mutation_key: string;
    preview_sha256: string;
    transition_sha256: string;
  },
) => claimRevisionCompensationCommand(investigationId, claimIndex, "accept", body);

/** POST /research/{id}/artifact/export — write Profile B HTML to operator store. */
export async function exportResearchArtifact(
  investigationId: string,
): Promise<ResearchArtifactExportResponse> {
  const resp = await apiFetch(
    `${API_BASE}/research/${encodeURIComponent(investigationId)}/artifact/export`,
    { method: "POST" },
  );
  if (!resp.ok) {
    throw new ApiError(
      `POST /research/{id}/artifact/export failed: HTTP ${resp.status}`,
      resp.status,
      await resp.text(),
    );
  }
  return resp.json();
}

/** GET /research/{id}/distill — the durable product of a research:
 *  its insights + open questions, read off the graph. */
export async function getDistillation(
  investigationId: string,
): Promise<DistillationResponse> {
  const resp = await apiFetch(
    `${API_BASE}/research/${encodeURIComponent(investigationId)}/distill`,
  );
  if (!resp.ok) {
    throw new ApiError(
      `GET /research/{id}/distill failed: HTTP ${resp.status}`,
      resp.status,
      await resp.text(),
    );
  }
  return resp.json();
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

/** POST /research/{investigationId}/notes/{nodeId}/challenge — drive the shipped living-note
 *  path. Resolves → mutates in place; declines → escalation (reserved, not
 *  launched). 503 = no model configured (honest no-key); the caller shows
 *  the shared failure surface, never a fabricated change. */
export async function challengeNote(
  nodeId: string,
  investigationId: string,
  req: { challenge_text?: string } = {},
): Promise<ChallengeNoteResponse> {
  const resp = await apiFetch(
    `${API_BASE}/research/${encodeURIComponent(investigationId)}/notes/${encodeURIComponent(nodeId)}/challenge`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ challenge_text: "", ...req }),
    },
  );
  if (!resp.ok) {
    throw new ApiError(
      `POST /research/{investigationId}/notes/{id}/challenge failed: HTTP ${resp.status}`,
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

/** GET /attribution/synthesis/{id} — Phase 1 telemetry only; no payout is
 *  attached to the result. The accrual view defaults to Option B (§9.3
 *  recommended default). ``emit_event`` defaults false (a read shouldn't write
 *  the log). */
export async function getAttributionReport(
  synthesisId: string,
): Promise<AttributionReportResponse> {
  const resp = await apiFetch(
    `${API_BASE}/attribution/synthesis/${encodeURIComponent(synthesisId)}`,
  );
  if (!resp.ok) {
    throw new ApiError(
      `GET /attribution/synthesis/{id} failed: HTTP ${resp.status}`,
      resp.status,
      await resp.text(),
    );
  }
  return resp.json();
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
  return resp.json();
}
