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

// The dev server proxies these prefixes to the Python backend
// (vite.config.ts). Production should serve both from the same origin.
const API_BASE = "";

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
  const resp = await fetch(`${API_BASE}/events/typed`, {
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
  const resp = await fetch(url.toString());
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
  const resp = await fetch(`${API_BASE}/health`);
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
  const resp = await fetch(`${API_BASE}/investigations`, {
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
  const resp = await fetch(url.toString());
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
  const resp = await fetch(
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

/** GET /chunks/{id} — used by Mode A's claim hover modal. */
export async function getChunk(chunkId: string): Promise<ChunkResponse> {
  const resp = await fetch(
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
