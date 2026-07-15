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

export interface DerivedAssetReadingResponse {
  derived_asset_id: string;
  title: string;
  asset_kind: "document" | "analysis" | "synthesis" | "composite";
  revision_id: string;
  content_sha256: string;
  generation: number;
  member_count: number;
  is_current: boolean;
  canonical_html: string;
  stable_reader_path: string;
  exact_reader_path: string;
}

export interface DerivedCompanionCitation {
  citation_id: string;
  chunk_ordinal: number;
  member_index: number;
  section_anchor: string;
  section_path: string;
  text: string;
  text_sha256: string;
}

export interface DerivedCompanionAnswer {
  schema_version: "antiek.derived-companion-answer.v1";
  answer_id: string;
  evidence_pack_sha256: string;
  provider: string;
  model: string;
  claims: Array<{
    claim_id: string;
    ordinal: number;
    text: string;
    citation_ids: string[];
    supported: boolean;
  }>;
  cited_citation_ids: string[];
  unsupported_claim_count: number;
  answer_html: string;
  answer_html_sha256: string;
  artifact_sha256: string;
}

export interface DerivedCompanionExecutionProjection {
  schema_version: "antiek.derived-companion-execution.v1";
  scope: Pick<DerivedAssetReadingResponse,
    "derived_asset_id" | "revision_id" | "content_sha256" | "generation">;
  available: false;
  reservable: false;
  dispatch_authorized: false;
  reason: "no_provider_route_qualified" | "qualification_registry_invalid"
    | "executable_route_not_registered";
  pricing_status: "unavailable";
  recommended_ceiling_cents: null;
  routes: Array<{
    provider: string;
    model: string;
    operation: string;
    checked_at: string;
    verdict: "qualified" | "refused";
    blocking_dimensions: Array<
      "pinned_pricing" | "durable_idempotency" | "hidden_retries_disabled"
      | "authoritative_reconciliation" | "stable_provider_evidence"
    >;
  }>;
}

export interface DerivedEvidenceBriefing {
  schema_version: "antiek.derived-evidence-briefing.v1";
  question: string;
  question_sha256: string;
  derived_asset_id: string;
  revision_id: string;
  content_sha256: string;
  generation: number;
  evidence_pack_sha256: string;
  section_count: number;
  passage_count: number;
  sections: Array<{
    section_path: string;
    passages: DerivedCompanionCitation[];
  }>;
  briefing_json_sha256: string;
  briefing_html: string;
  briefing_html_sha256: string;
  artifact_sha256: string;
}

export interface DerivedCompanionEvidenceResponse {
  client_turn_id: string;
  state: "evidence_ready" | "insufficient_evidence";
  failure_code: "no_matching_revision_evidence" | null;
  replayed: boolean;
  scope: Pick<DerivedAssetReadingResponse,
    "derived_asset_id" | "revision_id" | "content_sha256" | "generation" | "is_current">;
  evidence_pack: {
    pack_sha256: string;
    citations: DerivedCompanionCitation[];
  };
  briefing: DerivedEvidenceBriefing | null;
  answer: DerivedCompanionAnswer | null;
  execution: DerivedCompanionExecutionProjection;
}

export interface DerivedCompanionConversationResponse {
  scope: DerivedCompanionEvidenceResponse["scope"] & { exact_reader_path: string };
  execution: DerivedCompanionExecutionProjection;
  turns: Array<Pick<DerivedCompanionEvidenceResponse,
    "client_turn_id" | "state" | "failure_code" | "evidence_pack" | "briefing" | "answer">
    & { question: string }>;
}

export interface DerivedEvidenceSource {
  derived_asset_id: string;
  revision_id: string;
  content_sha256: string;
  generation: number;
  citation_id: string;
  chunk_ordinal: number;
  chunk_text_sha256: string;
  excerpt: string;
}

export interface DerivedEvidenceCollectionSummary {
  collection_id: string;
  label: string;
  derived_asset_id: string;
  revision_id: string;
  content_sha256: string;
  generation: number;
  version: number;
  member_count: number;
  collection_sha256: string;
  created_at: string;
  updated_at: string;
  etag: string;
}

export interface DerivedEvidenceCollection extends DerivedEvidenceCollectionSummary {
  sources: DerivedEvidenceSource[];
  locations: Array<{
    citation_id: string;
    chunk_ordinal: number;
    member_index: number;
    section_anchor: string;
    section_path: string;
  }>;
  is_current: boolean;
}

export interface DerivedEvidenceCollectionList {
  collections: DerivedEvidenceCollectionSummary[];
  limits: { collections: number };
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

export function getDerivedAssetReading(
  assetId: string,
  revisionId?: string,
): Promise<DerivedAssetReadingResponse> {
  const asset = encodeURIComponent(assetId);
  return get(revisionId
    ? `/research/derived-assets/assets/${asset}/revisions/${encodeURIComponent(revisionId)}/reading`
    : `/research/derived-assets/assets/${asset}/reading`);
}

export function prepareDerivedCompanionEvidence(
  model: DerivedAssetReadingResponse,
  clientTurnId: string,
  question: string,
): Promise<DerivedCompanionEvidenceResponse> {
  const asset = encodeURIComponent(model.derived_asset_id);
  const path = model.is_current
    ? `/research/derived-assets/assets/${asset}/companion/evidence`
    : `/research/derived-assets/assets/${asset}/revisions/${encodeURIComponent(model.revision_id)}/companion/evidence`;
  return post(path, {
    client_turn_id: clientTurnId,
    question,
    expected_revision_id: model.is_current ? model.revision_id : null,
    expected_content_sha256: model.is_current ? model.content_sha256 : null,
  });
}

export function getDerivedCompanionConversation(
  model: DerivedAssetReadingResponse,
): Promise<DerivedCompanionConversationResponse> {
  const asset = encodeURIComponent(model.derived_asset_id);
  return get(model.is_current
    ? `/research/derived-assets/assets/${asset}/companion`
    : `/research/derived-assets/assets/${asset}/revisions/${encodeURIComponent(model.revision_id)}/companion`);
}

export function createDerivedEvidenceCollection(
  label: string, sources: DerivedEvidenceSource[], idempotencyKey: string,
): Promise<DerivedEvidenceCollection> {
  const path = "/research/derived-assets/evidence-collections";
  return apiFetch(`${API_BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json", "Idempotency-Key": idempotencyKey },
    body: JSON.stringify({ label, sources }),
  }).then((response) => jsonOrThrow<DerivedEvidenceCollection>(response, `POST ${path}`));
}

export function listDerivedEvidenceCollections(
  assetId: string, revisionId: string,
): Promise<DerivedEvidenceCollectionList> {
  return get(`/research/derived-assets/evidence-collections?asset_id=${encodeURIComponent(assetId)}&revision_id=${encodeURIComponent(revisionId)}`);
}

export function listAllDerivedEvidenceCollections(): Promise<DerivedEvidenceCollectionList> {
  return get("/research/derived-assets/evidence-collections");
}

export function getDerivedEvidenceCollection(
  collectionId: string,
): Promise<DerivedEvidenceCollection> {
  return get(`/research/derived-assets/evidence-collections/${encodeURIComponent(collectionId)}`);
}

export function launchDerivedEvidenceCollection(
  collectionId: string,
  etag: string,
  idempotencyKey: string,
  body: { question: string; parent_investigation_id?: string; research_tier?: "fast" | "deep" },
): Promise<{ investigation_id: string; status: string; start_event_id: string }> {
  const path = `/research/derived-assets/evidence-collections/${encodeURIComponent(collectionId)}/launch`;
  return apiFetch(`${API_BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json", "If-Match": etag,
      "Idempotency-Key": idempotencyKey },
    body: JSON.stringify(body),
  }).then((response) => jsonOrThrow(response, `POST ${path}`));
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

// ── Cycle 71: Cross-asset evidence manifests ─────────────────────────
//
// A manifest composes 2–8 saved evidence collections into one ordered
// research context without flattening provenance. Collections remain the
// sole passage authority; the manifest stores bound references + digests.
//
// Mirrors interfaces/research/api/manifest_routes.py
// (prefix /research/derived-assets/evidence-manifests).

/** One bound collection reference inside a manifest. The manifest stores
 * the immutable collection version + digest at creation time so detail
 * reads can detect drift. */
export interface ManifestCollectionRef {
  collection_id: string;
  version: number;
  collection_sha256: string;
  ordinal: number;
}

/** Summary row for the owner list. No excerpts — passage content lives
 * in the collection, never duplicated onto the manifest. */
export interface EvidenceManifestSummary {
  manifest_id: string;
  label: string;
  version: number;
  collection_count: number;
  total_passage_count: number;
  manifest_sha256: string;
  created_at: string;
  updated_at: string;
}

/** Full manifest detail with ordered collection summaries, verified
 * nested sources/locations for inspection, and an ETag for launch
 * If-Match. Detail reopens every bound collection in one snapshot and
 * rejects drift (version, digest, order, cardinality, member, revision,
 * index, or location). */
export interface EvidenceManifestDetail extends EvidenceManifestSummary {
  collection_refs: ManifestCollectionRef[];
  collections: DerivedEvidenceCollection[];
  etag: string;
}

/** The owner-scoped list response. Bounded and summary-only. */
export interface EvidenceManifestList {
  manifests: EvidenceManifestSummary[];
  limits: { manifests: number };
}

/** Create manifest request. The server requires bounded idempotency key,
 * label, and 2–8 unique collection IDs. Within one write transaction it
 * resolves every collection under owner scope, revalidates revision chain,
 * complete index, members, digest, and locations, binds the current
 * immutable version/digest, and rejects a total passage count outside
 * 4–32 or canonical context above 96 KiB. */
export interface CreateEvidenceManifestRequest {
  label: string;
  collection_ids: string[];
  idempotency_key: string;
}

/** Launch manifest request. Accepts only manifest ID in the path, exact
 * If-Match, idempotency key, question, parent investigation, and closed
 * research tier. Accepts no context, collection array, source array,
 * provider, model, spend, asset, revision, or digest. The server
 * revalidates the complete manifest after reservation and before append,
 * then builds context server-side. */
export interface LaunchEvidenceManifestRequest {
  question: string;
  parent_investigation_id?: string;
  research_tier?: "fast" | "deep";
}

/** The launch response. One logical investigation per manifest launch. */
export interface LaunchEvidenceManifestResponse {
  investigation_id: string;
  status: string;
  start_event_id: string;
}

/** GET /research/derived-assets/evidence-manifests — owner-scoped
 *  summary list. No excerpts; no spend. */
export function listEvidenceManifests(): Promise<EvidenceManifestList> {
  return get("/research/derived-assets/evidence-manifests");
}

/** GET /research/derived-assets/evidence-manifests/{id} — full manifest
 *  detail with verified nested sources/locations and ETag. Reopens every
 *  bound collection in one snapshot and rejects drift. No spend. */
export function getEvidenceManifest(manifestId: string): Promise<EvidenceManifestDetail> {
  return get(`/research/derived-assets/evidence-manifests/${encodeURIComponent(manifestId)}`);
}

/** POST /research/derived-assets/evidence-manifests — create a manifest.
 *  2–8 unique collection IDs. Atomic: resolves, revalidates, binds
 *  versions/digests, persists manifest + ordered refs + create receipt. */
export function createEvidenceManifest(
  request: CreateEvidenceManifestRequest,
): Promise<EvidenceManifestDetail> {
  const path = "/research/derived-assets/evidence-manifests";
  return apiFetch(`${API_BASE}${path}`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "Idempotency-Key": request.idempotency_key,
    },
    body: JSON.stringify({ label: request.label, collection_ids: request.collection_ids }),
  }).then((response) => jsonOrThrow<EvidenceManifestDetail>(response, `POST ${path}`));
}

/** POST /research/derived-assets/evidence-manifests/{id}/launch —
 *  launch a research trajectory from a manifest. Manifest-authoritative:
 *  If-Match must match the manifest's ETag; context is built server-side
 *  from verified bound collections. One explicit confirmation gesture;
 *  mounting/inspecting never launches. */
export function launchEvidenceManifest(
  manifestId: string,
  etag: string,
  idempotencyKey: string,
  request: LaunchEvidenceManifestRequest,
): Promise<LaunchEvidenceManifestResponse> {
  const path = `/research/derived-assets/evidence-manifests/${encodeURIComponent(manifestId)}/launch`;
  return apiFetch(`${API_BASE}${path}`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "If-Match": etag,
      "Idempotency-Key": idempotencyKey,
    },
    body: JSON.stringify(request),
  }).then((response) => jsonOrThrow<LaunchEvidenceManifestResponse>(response, `POST ${path}`));
}
