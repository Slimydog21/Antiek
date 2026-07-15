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

export type SpendMode = "stop_limit" | "hard_ceiling";

export interface SpendPreview {
  spend_mode: SpendMode;
  currency: "USD";
  amount_cents: number;
  eligible: boolean;
  reasons: string[];
  authority_digest: string | null;
  recovery_session_id?: string | null;
  approval_revision: number;
  assumptions: string[];
}

export interface HardCeilingSnapshot {
  currency: "USD";
  approval_revision: number;
  authority_digest: string;
  ceiling_cents: number;
  authorized_spent_cents: number;
  observed_provider_spend_cents: number;
  held_cents: number;
  available_cents: number;
  run_state: "active" | "ceiling_breached" | "closed_unresolved" | "closed_reconciled";
  ceiling_breached: boolean;
  unknown_outcome_count: number;
  blocked_stages: string[];
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
  researches: ResearchStatus[];
  cost?: SessionCost | null;
  all_terminal?: boolean;
  hard_ceiling?: HardCeilingSnapshot | null;
}

export interface LaunchResponse {
  session_id: string;
  researches: { investigation_id: string; sub_question: string; question_node_id: string | null }[];
  aggregate_cap_usd: number | null;
  spend_mode?: SpendMode;
  replayed?: boolean;
  resumed?: boolean;
  hard_ceiling?: HardCeilingSnapshot;
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

// ── Immutable twin notes (Cycle 48) ───────────────────────────────────

export interface TwinNoteRevision {
  revision_id: string;
  asset_id: string;
  note_count: number;
  source_count: number;
  created_at?: string;
}

export interface TwinNoteAsset {
  asset_id: string;
  asset_label: string;
  current_revision: TwinNoteRevision;
  revision_count: number;
}

export interface TwinNoteListResponse {
  assets: TwinNoteAsset[];
}

export interface TwinNoteHistoryResponse {
  asset_id: string;
  revisions: TwinNoteRevision[];
}

export interface TwinNoteCompositionResponse {
  composition_id: string;
  url: string;
  members: Array<TwinNoteRevision & { member_ordinal: number }>;
}
export interface TwinNotePreviewResponse {
  asset_id: string; expected_predecessor: string | null; preview_digest: string;
  members: Array<{member_ordinal:number; investigation_id:string; window_id:string}>;
  note_count:number; source_count:number;
}
export interface TwinNoteApplyResponse extends TwinNoteRevision {
  supersedes_revision_id:string|null; replayed:boolean; url:string;
}

export type TwinNoteCandidateExclusionReason =
  | "evidence_incomplete"
  | "evidence_digest_mismatch"
  | "evidence_noncanonical"
  | "evidence_binding_mismatch"
  | "evidence_output_invalid";

export interface TwinNoteRevisionCandidate {
  window_id: string;
  investigation_id: string;
  consumer_version: number;
  window_ordinal: number;
  note_count: number;
  source_count: number;
  eligibility: "eligible" | "excluded";
  exclusion_reason: TwinNoteCandidateExclusionReason | null;
}

export interface TwinNoteRevisionCandidateAsset {
  asset_id: string;
  asset_label: string;
  windows: TwinNoteRevisionCandidate[];
  truncated: boolean;
}

export interface TwinNoteRevisionCandidatesResponse {
  assets: TwinNoteRevisionCandidateAsset[];
  truncated: boolean;
  limits: {
    assets: number;
    windows_per_asset: number;
    total_windows: number;
    selection_members: number;
  };
}

export interface TwinNoteMergeContextNote {
  note_ordinal: number;
  text: string;
  source_count: number;
}

export interface TwinNoteMergeContextSource {
  kind: "revision" | "composition";
  id: string;
  label: string;
  html_url: string;
  revisions: Array<{
    member_ordinal: number | null;
    revision_id: string;
    notes: TwinNoteMergeContextNote[];
  }>;
}

export interface TwinNoteMergeContextResponse {
  source_projections: Array<{
    projection_id: string;
    source_asset_id: string;
    source_document_id: string;
    label: string;
    preview_url: string;
  }>;
  twin_sources: TwinNoteMergeContextSource[];
  limits: { source_projections: number; twin_sources: number; notes: number };
}

export interface TwinNoteMergeProjectionResponse {
  projection_id: string;
  source_projection_id: string;
  twin_source: { kind: "revision" | "composition"; id: string };
  member_count: number;
  hosted_html_sha256: string;
  merge_draft_input: { projection_ids: [string, string] };
}

export interface DerivedMergeDraftResponse {
  draft_id: string;
  canonical_sha256: string;
  manifest_sha256: string;
  sanitizer_policy: string;
  sanitizer_version: string;
  projection_ids: [string, string];
}

export interface DerivedMergeReviewResponse {
  review_id: string;
  draft_id: string;
  canonical_sha256: string;
  manifest_sha256: string;
  acknowledgement_version: string;
}

export interface DerivedMergeApplyResponse {
  operation_id: string;
  derived_asset_id: string;
  revision_id: string;
  content_sha256: string;
  generation: number;
  replayed: boolean;
}

export interface DerivedAssetCurrent {
  revision_id: string;
  content_sha256: string;
  generation: number;
  member_count: number;
  preview_url: string;
}

export interface DerivedAssetSummary {
  derived_asset_id: string;
  title: string;
  asset_kind: "document" | "analysis" | "synthesis" | "composite";
  current: DerivedAssetCurrent;
  revision_count: number;
}

export interface DerivedAssetRevision {
  revision_id: string;
  operation_kind: "create" | "revise" | "restore";
  content_sha256: string;
  parent_revision_id: string | null;
  restored_from_revision_id: string | null;
  member_count: number;
  is_current: boolean;
  preview_url: string;
}

export interface DerivedAssetDiscoveryResponse {
  assets: DerivedAssetSummary[];
  limits: { assets: number; revisions_per_asset: number };
}

export interface DerivedAssetHistoryResponse extends DerivedAssetSummary {
  revisions: DerivedAssetRevision[];
}

/** Owner-scoped verified current twin-note revisions. */
export function listTwinNotes(): Promise<TwinNoteListResponse> {
  return get("/research/twin-notes");
}

/** Owner-derived, advisory candidates for a Cycle 49 revision command. */
export function discoverTwinNoteRevisionCandidates(): Promise<TwinNoteRevisionCandidatesResponse> {
  return get("/research/twin-notes/revision-candidates");
}

export function getTwinNoteMergeContext(): Promise<TwinNoteMergeContextResponse> {
  return get("/research/twin-notes/merge-context");
}

export function createTwinNoteMergeProjection(request: {
  source_projection_id: string;
  source: { kind: "revision" | "composition"; id: string };
  selected_notes: Array<{ revision_id: string; note_ordinal: number }>;
  idempotency_key: string;
}): Promise<TwinNoteMergeProjectionResponse> {
  return post("/research/twin-notes/merge-projections", request);
}

export function createDerivedMergeDraft(request: {
  projection_ids: [string, string];
  intent: "create";
  title: string;
  asset_kind: "document" | "analysis" | "synthesis" | "composite";
}): Promise<DerivedMergeDraftResponse> {
  return post("/research/derived-assets/merge/drafts", request);
}

export function createDerivedMergeReview(draftId: string): Promise<DerivedMergeReviewResponse> {
  return post(`/research/derived-assets/merge/drafts/${encodeURIComponent(draftId)}/reviews`, {});
}

export function applyDerivedMergeReview(
  reviewId: string,
  operationId: string,
): Promise<DerivedMergeApplyResponse> {
  return post(`/research/derived-assets/merge/reviews/${encodeURIComponent(reviewId)}/apply`, {
    operation_id: operationId,
    expected_generation: null,
  });
}

export function discoverDerivedAssets(): Promise<DerivedAssetDiscoveryResponse> {
  return get("/research/derived-assets");
}

export function getDerivedAssetHistory(assetId: string): Promise<DerivedAssetHistoryResponse> {
  return get(`/research/derived-assets/assets/${encodeURIComponent(assetId)}/revisions`);
}

export function restoreDerivedAsset(
  assetId: string,
  request: {
    operation_id: string;
    selected_revision_id: string;
    expected_revision_id: string;
    expected_content_sha256: string;
    expected_generation: number;
  },
): Promise<DerivedMergeApplyResponse> {
  return post(`/research/derived-assets/merge/assets/${encodeURIComponent(assetId)}/restore`, request);
}

/** Verified current-to-root history for one owner-scoped asset. */
export function getTwinNoteHistory(assetId: string): Promise<TwinNoteHistoryResponse> {
  return get(`/research/twin-notes/assets/${encodeURIComponent(assetId)}/revisions`);
}

/** Create or replay a composition from exact revisions in semantic order. */
export function composeTwinNotes(revisionIds: string[]): Promise<TwinNoteCompositionResponse> {
  return post("/research/twin-notes/compositions", { revision_ids: revisionIds });
}
export function previewTwinNoteRevision(asset_id:string, window_ids:string[]):Promise<TwinNotePreviewResponse> {
  return post("/research/twin-notes/revision-previews", {asset_id,window_ids});
}
export function applyTwinNoteRevision(request:{asset_id:string;window_ids:string[];expected_predecessor:string|null;preview_digest:string;idempotency_key:string}):Promise<TwinNoteApplyResponse> {
  return post("/research/twin-notes/revisions",request);
}
export function createTwinNoteWriteDraft(request:{source:{kind:"revision"|"composition";id:string};idempotency_key:string;title:string;deliverable_kind:string}):Promise<{deliverable_id:string;replayed:boolean}> {
  return post("/write/deliverables/from-twin-note",request);
}

export function twinNoteRevisionUrl(revisionId: string): string {
  return `/research/twin-notes/revisions/${encodeURIComponent(revisionId)}`;
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

export function getSpendPreview(
  rootId: string,
  spendMode: SpendMode,
  amountUsd: string,
): Promise<SpendPreview> {
  return post(`/research/plans/${encodeURIComponent(rootId)}/spend-preview`, {
    spend_mode: spendMode,
    amount_usd: amountUsd,
  });
}

export function approveSpend(
  rootId: string,
  amountUsd: string,
  perResearchBudgetUsd = 0.5,
): Promise<SpendPreview> {
  return post(`/research/plans/${encodeURIComponent(rootId)}/spend-approval`, {
    spend_mode: "hard_ceiling",
    amount_usd: amountUsd,
    per_research_budget_usd: perResearchBudgetUsd,
  });
}

// ── Launch + session (SPR-06) ───────────────────────────────────────────

export function launchPlan(rootId: string, req: {
  per_research_budget_usd?: number;
  aggregate_budget_usd?: number | null;
  spend_mode?: SpendMode;
  hard_ceiling_usd?: string;
  authority_digest?: string;
} = {}): Promise<LaunchResponse> {
  return post(`/research/plans/${encodeURIComponent(rootId)}/launch`, req);
}

export function reconcileSessionSpend(sessionId: string): Promise<{
  hard_ceiling: HardCeilingSnapshot;
  provider_checks_started: number;
  message: string;
}> {
  return post(`/research/sessions/${encodeURIComponent(sessionId)}/spend/reconcile`, {});
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
