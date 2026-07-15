/**
 * Deep Research Workspace API client (DRW SPR-06 transport → SPR-09 UI).
 *
 * Mirrors `interfaces/research/api/cascade_routes.py` (prefix `/research`).
 * The cascade lifecycle: plan → edit → approve → launch → watch → steer.
 * The frontend never decides launchability or cost — it renders what the
 * backend's glass-box gate + runner report.
 */

import { API_BASE, ApiError, apiFetch } from "../lib/api";

// ── Plan tree (mirrors roles/cascade_planner PlanTree.to_dict) ──────────

export interface PlanNode {
  local_id: string;
  question: string;
  rationale: string;
  focus_boundary: string;
  budget_usd: number | null;
  max_depth: number | null;
  graph_node_id: string | null;
  children: PlanNode[];
}

export interface PlanApproval {
  state: "draft" | "approved";
  approved_at: string | null;
  approved_by: string | null;
  plan_version: number;
}

export interface PlanTree {
  root: PlanNode;
  seed_kind: string;
  seed_provenance: Record<string, unknown>;
  approval: PlanApproval;
  root_investigation_id: string | null;
}

export interface CreatePlanResponse {
  root_node_id: string;
  tree: PlanTree;
  capped_nodes: string[];
  over_broad_leaves: string[];
}

export interface PlanResponse {
  root_node_id: string;
  tree: PlanTree;
  launchable: boolean;
}

export interface ApproveResponse {
  root_node_id: string;
  approval: PlanApproval;
  launchable: boolean;
}

// ── Session (mirrors CascadeSession status/cost) ────────────────────────

export type ResearchRunState =
  | "pending" | "running" | "paused" | "stopping"
  | "done" | "stopped" | "failed" | "budget_halted";

export const TERMINAL_STATES: ReadonlySet<ResearchRunState> = new Set<ResearchRunState>([
  "done", "stopped", "failed", "budget_halted",
]);

export interface ResearchStatus {
  investigation_id: string;
  sub_question: string;
  state: ResearchRunState;
  question_node_id?: string | null;
  plan_node_local_id?: string | null;
  control_available?: boolean;
}

export interface SessionCost {
  per_research: Record<string, number>;
  session_total_usd: number;
  aggregate_spent_usd: number;
  aggregate_cap_usd: number;
}

export interface SessionStatus {
  session_id: string;
  live: boolean;
  plan?: SessionPlan | null;
  researches: ResearchStatus[];
  cost?: SessionCost | null;
  all_terminal?: boolean;
}

export interface SessionPlan {
  root_node_id: string;
  tree: PlanTree;
}

export interface LaunchResponse {
  session_id: string;
  researches: {
    investigation_id: string;
    sub_question: string;
    question_node_id: string | null;
    plan_node_local_id: string | null;
  }[];
  aggregate_cap_usd: number | null;
}

export type SteerKind = "pause" | "resume" | "stop" | "redirect" | "deepen";

/** The per-research stop limit the runner applies when launch omits one
 * (mirrors runtime/research_runner protocol.BudgetCap). The entry UI reads
 * this to recommend a stop limit for N researches, never a hardcoded
 * number that would drift from the contract. */
export interface BudgetDefaults {
  per_research_cost_usd: number;
  per_research_max_steps: number;
  /** The host-local runner's real bounded-semaphore concurrency cap
   * (mirrors runtime/research_runner/host_local.DEFAULT_MAX_CONCURRENCY). The
   * multi-research monitor reads this to show an honest "N running, M queued"
   * — the surplus past the cap is queued behind the semaphore, never a number
   * the UI invents. */
  host_local_max_concurrency: number;
}

// ── Suggested next researches (SPR-09 — the compounding flywheel) ───────
//
// The §7 continuous daemon already computes scored evidentiary gaps. This is
// the read-only surface over its output: each suggestion is a plain-language
// "thread worth chasing", grounded in the research it came from. The client
// never sees the daemon's vocabulary (evidentiary_gap / chase score /
// policy_id) — those are translated server-side. `key` is the opaque dedupe
// handle, never rendered.

export interface Suggestion {
  key: string;
  question: string;
  suggested_retrieval: string | null;
  seen_in_research_count: number;
  source_investigation_id: string | null;
}

export interface SuggestionsResponse {
  count: number;
  suggestions: Suggestion[];
}

export interface ResearchComposeMember {
  investigation_id: string;
  content_hash: string;
}

export interface ResearchCompose {
  compose_id: string;
  selection_fingerprint: string;
  members: ResearchComposeMember[];
  identical_content: [string, string][];
  view_url: string | null;
  reused: boolean;
}

export interface ComposeWriteWorkspace {
  compose_id: string;
  deliverable_id: string;
  section_id: string;
  write_url: string;
  member_count: number;
  snapshot_occurrence_count: number;
  unique_block_count: number;
  duplicate_count: number;
  kind_conflict_count: number;
  dangling_count: number;
  reused: boolean;
}

export interface ComposeInterrogationPreview {
  schema_version: number;
  compose_id: string;
  selection_fingerprint: string;
  prompt_hash: string;
  context: string;
  member_receipts: Array<{
    index: number;
    investigation_id: string;
    content_hash: string;
    included_chars: number;
    omitted_chars: number;
    truncated_fields: number;
    omitted_fields: number;
  }>;
  prompt_chars: number;
  context_chars: number;
  max_prompt_chars: number;
  max_context_chars: number;
  truncated_fields: number;
  omitted_fields: number;
  omitted_chars: number;
  provider_called: false;
}

// ── Request helpers ─────────────────────────────────────────────────────

async function jsonOrThrow<T>(resp: Response, what: string): Promise<T> {
  if (!resp.ok) {
    throw new ApiError(`${what} failed: HTTP ${resp.status}`, resp.status, await resp.text());
  }
  return resp.json() as Promise<T>;
}

function post<T>(path: string, body: unknown): Promise<T> {
  return apiFetch(`${API_BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  }).then((r) => jsonOrThrow<T>(r, `POST ${path}`));
}

function get<T>(path: string): Promise<T> {
  return apiFetch(`${API_BASE}${path}`).then((r) => jsonOrThrow<T>(r, `GET ${path}`));
}

// ── Plan lifecycle (SPR-05 over HTTP) ───────────────────────────────────

export function getBudgetDefaults(): Promise<BudgetDefaults> {
  return get("/research/budget-defaults");
}

/** SPR-09: the daemon's scored gaps as suggested next researches. READ-ONLY —
 * a plain GET that costs nothing; the only spend is an explicit chase, which
 * goes through `startInvestigation` (the existing capped launch path), not
 * here. `limit` bounds the displayed count (rank + cap, never a flood). */
export function getSuggestions(limit = 8): Promise<SuggestionsResponse> {
  return get(`/research/suggestions?limit=${encodeURIComponent(String(limit))}`);
}

export function previewResearchCompose(investigationIds: string[]): Promise<ResearchCompose> {
  return post("/research/artifact-composes/preview", { investigation_ids: investigationIds });
}

export function createResearchCompose(
  investigationIds: string[], selectionFingerprint: string,
): Promise<ResearchCompose> {
  return post("/research/artifact-composes", {
    investigation_ids: investigationIds,
    selection_fingerprint: selectionFingerprint,
  });
}

export function createComposeWriteWorkspace(composeId: string): Promise<ComposeWriteWorkspace> {
  return post(`/research/artifact-composes/${encodeURIComponent(composeId)}/write-workspace`, {});
}

export function previewComposeInterrogation(
  composeId: string,
  prompt: string,
  selectionFingerprint: string,
): Promise<ComposeInterrogationPreview> {
  return post(
    `/research/artifact-composes/${encodeURIComponent(composeId)}/interrogations/preview`,
    { prompt, selection_fingerprint: selectionFingerprint },
  );
}

export function createPlan(req: {
  problem: string;
  sub_questions?: string[];
  max_depth?: number;
}): Promise<CreatePlanResponse> {
  return post("/research/plans", req);
}

export function getPlan(rootId: string): Promise<PlanResponse> {
  return get(`/research/plans/${encodeURIComponent(rootId)}`);
}

export function editPlan(rootId: string, edit: {
  op: "add_child" | "remove" | "reword" | "set_budget" | "split";
  target_local_id: string;
  question?: string;
  budget_usd?: number;
  max_depth?: number;
  into?: string[];
}): Promise<PlanResponse> {
  return post(`/research/plans/${encodeURIComponent(rootId)}/edit`, edit);
}

export function approvePlan(rootId: string, approver = "__operator__"): Promise<ApproveResponse> {
  return post(`/research/plans/${encodeURIComponent(rootId)}/approve`, { approver });
}

// ── Launch + session (SPR-06) ───────────────────────────────────────────

export function launchPlan(rootId: string, req: {
  per_research_budget_usd?: number;
  aggregate_budget_usd?: number | null;
} = {}): Promise<LaunchResponse> {
  return post(`/research/plans/${encodeURIComponent(rootId)}/launch`, req);
}

export function getSession(sessionId: string): Promise<SessionStatus> {
  return get(`/research/sessions/${encodeURIComponent(sessionId)}`);
}

export function getSessionCost(sessionId: string): Promise<SessionCost> {
  return get(`/research/sessions/${encodeURIComponent(sessionId)}/cost`);
}

export function steerResearch(
  sessionId: string,
  investigationId: string,
  kind: SteerKind,
  payload?: Record<string, unknown>,
): Promise<{ session_id: string; investigation_id: string; state: ResearchRunState | null }> {
  return post(
    `/research/sessions/${encodeURIComponent(sessionId)}/researches/${encodeURIComponent(investigationId)}/steer`,
    { kind, payload: payload ?? null },
  );
}

/** SSE endpoint URL — the finer-grained per-step stream. The SPR-09 monitor
 * polls `getSession` (the durable, authoritative source) for robustness;
 * this is here for a future EventSource upgrade to step-level liveness. */
export function sessionStreamUrl(sessionId: string): string {
  return `${API_BASE}/research/sessions/${encodeURIComponent(sessionId)}/stream`;
}
