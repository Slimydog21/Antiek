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
}

export interface SessionCost {
  per_research: Record<string, number>;
  session_total_usd: number;
  aggregate_spent_usd: number;
  aggregate_cap_usd: number;
}

export interface GatherSourceReceipt {
  source: "exa" | "parallel" | "arxiv" | "substack";
  status: "succeeded" | "failed" | "unknown" | "skipped";
  document_ids: string[];
  actual_cost_micros: number;
  tokens: number;
  provider_receipt_id: string | null;
  failure_code: string | null;
}

export interface GatherReport {
  investigation_id: string;
  contract_version: 1;
  launch_fingerprint: string;
  plan_fingerprint: string;
  legal_policy_snapshot_sha256: string;
  receipts: GatherSourceReceipt[];
  document_ids: string[];
  minimum_evidence_documents: number;
  evidence_complete: boolean;
  partial: boolean;
  unknown_outcome: boolean;
}

export interface SessionStatus {
  session_id: string;
  live: boolean;
  researches: ResearchStatus[];
  gather_reports?: GatherReport[];
  gather_report_errors?: { investigation_id: string; code: "gather_report_invalid" }[];
  cost?: SessionCost | null;
  all_terminal?: boolean;
}

export interface LaunchResponse {
  session_id: string;
  researches: { investigation_id: string; sub_question: string; question_node_id: string | null }[];
  aggregate_cap_usd: number | null;
  gather_receipt: GatherStatus;
  driver_receipt: {
    research_tier: "fast" | "deep" | "wrestle";
    reviewed_primary_provider: string;
    reviewed_primary_model: string;
    why: string;
    reasoning_projected_max_cost_usd: number | null;
    candidate_rank: number;
    availability_source: "boot_registered_providers";
  };
  idempotency_replayed: boolean;
}

export interface CascadeDriverReadiness {
  research_tier: "fast" | "deep" | "wrestle";
  ready: boolean;
  provider: string | null;
  model: string | null;
  candidate_rank: number | null;
  availability_source: "boot_registered_providers";
  reason: string;
}

export interface LaunchAttemptStatus {
  plan_id: string;
  session_id: string;
  state: "claimed" | "completed";
  response_integrity: true | null;
  session_authority_present: boolean;
  launch_evidence_present: boolean;
  action: "inspect_session" | "await_operator_reconciliation";
}

export class LaunchOutcomeUnknownError extends Error {
  constructor(public readonly sessionId: string) {
    super("The launch outcome is unknown; automatic redispatch is refused.");
  }
}

export interface GatherStatus {
  view_format: "html";
  product_panel: "research_gather_status";
  configured_mode: "stub" | "exa" | "multi_source";
  gather_mode: "contract_stub" | "exa_reasoning" | "authorized_multi_source";
  network_retrieval: boolean;
  exa_key_installed: boolean;
  parallel_key_installed: boolean;
  legal_gate_bypassed: boolean;
  legal_policy: {
    schema_version: number;
    policy_snapshot_sha256: string | null;
    issuer_state: "configured" | "not_configured" | "invalid";
    write_enforcement_version: number;
    read_enforcement_version: number;
    migration_state: "current" | "missing" | "invalid";
    production_defensible: boolean;
    reason_code: string | null;
  };
  launch_ready: boolean;
  production_defensible: boolean;
  stub_requires_acknowledgment: boolean;
  reviewed_gather_plan: null | {
    fingerprint: string;
    leaf_count: number;
    per_leaf_max_results: number;
    per_leaf_max_cost_micros: number;
    launch_max_results: number;
    launch_max_cost_micros: number;
    sources: Array<"exa" | "parallel" | "arxiv" | "substack">;
    source_configuration_sha256: Record<string, string>;
  };
  configuration_error: string | null;
  multi_source_execution_activated: boolean;
}

export type LegalPolicyMatcherKind = "domain" | "corpus" | "author" | "title" | "content_sha256";
export type LegalPolicyDecision = "allow" | "deny";

export interface LegalPolicyEventInput {
  matcher_kind: LegalPolicyMatcherKind;
  matcher_value: string;
  decision: LegalPolicyDecision;
  citation_ref: string;
  issuer_id: string;
  reason_code: string;
}

export interface LegalPolicyDryRun {
  operation: "dry_run";
  normalized_matcher_value: string;
  requested_decision: LegalPolicyDecision;
  current_snapshot_sha256: string;
  matching_active_event_ids: string[];
  would_append: boolean;
  applied: false;
}

export interface LegalPolicyMutationReceipt {
  event_id: string;
  policy_snapshot_sha256: string;
  applied: true;
  idempotency_replayed: boolean;
}

export interface LegalPolicyRevokeInput {
  event_id: string;
  matcher_kind: LegalPolicyMatcherKind;
  matcher_value: string;
  citation_ref: string;
  issuer_id: string;
  reason_code: string;
}

export interface LegalPolicyDispatchLease {
  lease_id: string;
  holder_investigation_id: string | null;
  acquired_at: string;
  diagnostic_deadline: string;
  recovery_state: "active" | "terminal_recoverable" | "evidence_invalid";
  terminal_action: "investigation.completed" | "investigation.failed" | "investigation.chase_halted" | null;
}

function verifiedGatherStatus(value: unknown): GatherStatus {
  if (!value || typeof value !== "object") throw new Error("invalid gather readiness response");
  const status = value as Record<string, unknown>;
  const configured = status.configured_mode;
  const gatherMode = status.gather_mode;
  const legal = status.legal_policy as Record<string, unknown> | null;
  const policySnapshot = legal?.policy_snapshot_sha256;
  const bypassed = status.legal_gate_bypassed;
  const network = status.network_retrieval;
  const keyInstalled = status.exa_key_installed;
  const parallelKeyInstalled = status.parallel_key_installed;
  const launchReady = status.launch_ready;
  const defensible = status.production_defensible;
  const requiresAck = status.stub_requires_acknowledgment;
  const executionActivated = status.multi_source_execution_activated;
  const configurationError = status.configuration_error;
  const reviewedRaw = status.reviewed_gather_plan;
  const reviewed = reviewedRaw === null ? null :
    reviewedRaw && typeof reviewedRaw === "object" ? reviewedRaw as Record<string, unknown> : undefined;
  const expectedMode = configured === "exa" ? "exa_reasoning" :
    configured === "multi_source" ? "authorized_multi_source" : "contract_stub";
  const reviewedValid = reviewed === null || (reviewed !== undefined &&
    typeof reviewed.fingerprint === "string" && /^[0-9a-f]{64}$/.test(reviewed.fingerprint) &&
    Number.isInteger(reviewed.leaf_count) && Number(reviewed.leaf_count) > 0 &&
    Number.isInteger(reviewed.per_leaf_max_results) && Number(reviewed.per_leaf_max_results) > 0 &&
    Number.isInteger(reviewed.per_leaf_max_cost_micros) && Number(reviewed.per_leaf_max_cost_micros) >= 0 &&
    Number.isInteger(reviewed.launch_max_results) &&
    reviewed.launch_max_results === Number(reviewed.per_leaf_max_results) * Number(reviewed.leaf_count) &&
    Number.isInteger(reviewed.launch_max_cost_micros) &&
    reviewed.launch_max_cost_micros === Number(reviewed.per_leaf_max_cost_micros) * Number(reviewed.leaf_count) &&
    Array.isArray(reviewed.sources) &&
    reviewed.sources.join("|") === "exa|parallel|arxiv|substack" &&
    !!reviewed.source_configuration_sha256 &&
    typeof reviewed.source_configuration_sha256 === "object" &&
    Object.keys(reviewed.source_configuration_sha256 as Record<string, unknown>).sort().join("|") ===
      "arxiv|exa|parallel|substack" &&
    Object.values(reviewed.source_configuration_sha256 as Record<string, unknown>).every(
      (digest) => typeof digest === "string" && /^[0-9a-f]{64}$/.test(digest) &&
        digest !== "0".repeat(64),
    )
  );
  if (
    !["stub", "exa", "multi_source"].includes(String(configured)) ||
    !legal || typeof bypassed !== "boolean" ||
    legal.schema_version !== 1 || !(
      policySnapshot === null ||
      (typeof policySnapshot === "string" && /^[0-9a-f]{64}$/.test(policySnapshot))
    ) ||
    !["configured", "not_configured", "invalid"].includes(String(legal.issuer_state)) ||
    !["current", "missing", "invalid"].includes(String(legal.migration_state)) ||
    typeof legal.write_enforcement_version !== "number" || typeof legal.read_enforcement_version !== "number" ||
    typeof legal.production_defensible !== "boolean" ||
    !(legal.reason_code === null || typeof legal.reason_code === "string") ||
    typeof network !== "boolean" || typeof keyInstalled !== "boolean" ||
    typeof parallelKeyInstalled !== "boolean" || typeof executionActivated !== "boolean" ||
    !(configurationError === null || typeof configurationError === "string") || !reviewedValid ||
    typeof launchReady !== "boolean" || typeof defensible !== "boolean" ||
    typeof requiresAck !== "boolean" || status.view_format !== "html" ||
    status.product_panel !== "research_gather_status" || gatherMode !== expectedMode ||
    network !== (configured === "exa" || configured === "multi_source") ||
    defensible !== (legal.production_defensible && !bypassed) ||
    requiresAck !== (gatherMode === "contract_stub") ||
    (configured === "multi_source" && reviewed === null && configurationError === null) ||
    launchReady !== (configured === "stub" ||
      (configured === "exa" && keyInstalled && defensible) ||
      (configured === "multi_source" && reviewed !== null && keyInstalled &&
        parallelKeyInstalled && defensible && configurationError === null && executionActivated))
  ) throw new Error("invalid gather readiness response");
  return status as unknown as GatherStatus;
}

function verifiedLaunchResponse(value: unknown): LaunchResponse {
  if (!value || typeof value !== "object") throw new Error("invalid cascade launch response");
  const response = value as Record<string, unknown>;
  const expected = [
    "aggregate_cap_usd", "driver_receipt", "gather_receipt", "idempotency_replayed", "researches", "session_id",
  ];
  if (Object.keys(response).sort().join("|") !== expected.sort().join("|") ||
      typeof response.session_id !== "string" || !response.session_id ||
      typeof response.idempotency_replayed !== "boolean" ||
      !(response.aggregate_cap_usd === null ||
        (typeof response.aggregate_cap_usd === "number" && Number.isFinite(response.aggregate_cap_usd))) ||
      !Array.isArray(response.researches)) {
    throw new Error("invalid cascade launch response");
  }
  for (const item of response.researches) {
    if (!item || typeof item !== "object") throw new Error("invalid cascade launch response");
    const research = item as Record<string, unknown>;
    if (Object.keys(research).sort().join("|") !==
        ["investigation_id", "question_node_id", "sub_question"].sort().join("|") ||
        typeof research.investigation_id !== "string" || !research.investigation_id ||
        typeof research.sub_question !== "string" ||
        !(research.question_node_id === null || typeof research.question_node_id === "string")) {
      throw new Error("invalid cascade launch response");
    }
  }
  verifiedGatherStatus(response.gather_receipt);
  const driver = response.driver_receipt as Record<string, unknown> | null;
  if (!driver || Object.keys(driver).sort().join("|") !== [
    "availability_source", "candidate_rank", "reasoning_projected_max_cost_usd",
    "research_tier", "reviewed_primary_model", "reviewed_primary_provider", "why",
  ].sort().join("|") ||
      !["fast", "deep", "wrestle"].includes(String(driver.research_tier)) ||
      typeof driver.reviewed_primary_provider !== "string" || !driver.reviewed_primary_provider ||
      typeof driver.reviewed_primary_model !== "string" || !driver.reviewed_primary_model ||
      typeof driver.why !== "string" || !driver.why ||
      driver.availability_source !== "boot_registered_providers" ||
      typeof driver.candidate_rank !== "number" || !Number.isInteger(driver.candidate_rank) ||
      driver.candidate_rank < 1 ||
      !(driver.reasoning_projected_max_cost_usd === null ||
        (typeof driver.reasoning_projected_max_cost_usd === "number" &&
         Number.isFinite(driver.reasoning_projected_max_cost_usd)))) {
    throw new Error("invalid cascade launch response");
  }
  return response as unknown as LaunchResponse;
}

export type SteerKind = "pause" | "resume" | "stop" | "redirect" | "deepen";

/** The per-research spend ceiling the runner applies when launch omits one
 * (mirrors runtime/research_runner protocol.BudgetCap). The entry UI reads
 * this to show "estimated up to $X for N researches" — never a hardcoded
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

// ── Plan lifecycle (SPR-05 over HTTP) ───────────────────────────────────

export function getBudgetDefaults(): Promise<BudgetDefaults> {
  return get("/research/budget-defaults");
}

export function getGatherStatus(rootNodeId: string): Promise<GatherStatus> {
  const path = `/research/plans/${encodeURIComponent(rootNodeId)}/gather-status`;
  return apiFetch(`${API_BASE}${path}`, { cache: "no-store" }).then((r) =>
    jsonOrThrow<unknown>(r, `GET ${path}`),
  ).then(verifiedGatherStatus);
}

export function dryRunLegalPolicy(
  rootNodeId: string,
  body: LegalPolicyEventInput,
): Promise<LegalPolicyDryRun> {
  return post(`/research/plans/${encodeURIComponent(rootNodeId)}/legal-policy/dry-run`, body);
}

export function applyLegalPolicy(
  rootNodeId: string,
  body: LegalPolicyEventInput,
  idempotencyKey: string,
): Promise<LegalPolicyMutationReceipt> {
  const path = `/research/plans/${encodeURIComponent(rootNodeId)}/legal-policy/events`;
  return apiFetch(`${API_BASE}${path}`, {
    method: "POST",
    cache: "no-store",
    headers: { "Content-Type": "application/json", "Idempotency-Key": idempotencyKey },
    body: JSON.stringify(body),
  }).then((r) => jsonOrThrow<LegalPolicyMutationReceipt>(r, `POST ${path}`));
}

export function revokeLegalPolicy(
  rootNodeId: string,
  body: LegalPolicyRevokeInput,
  idempotencyKey: string,
): Promise<LegalPolicyMutationReceipt & { revoked_event_id: string }> {
  const path = `/research/plans/${encodeURIComponent(rootNodeId)}/legal-policy/revoke`;
  return apiFetch(`${API_BASE}${path}`, {
    method: "POST",
    cache: "no-store",
    headers: { "Content-Type": "application/json", "Idempotency-Key": idempotencyKey },
    body: JSON.stringify(body),
  }).then((r) => jsonOrThrow<LegalPolicyMutationReceipt & { revoked_event_id: string }>(r, `POST ${path}`));
}

export function listLegalPolicyDispatchLeases(
  rootNodeId: string,
): Promise<{ count: number; leases: LegalPolicyDispatchLease[] }> {
  const path = `/research/plans/${encodeURIComponent(rootNodeId)}/legal-policy/dispatch-leases`;
  return apiFetch(`${API_BASE}${path}`, { cache: "no-store" })
    .then((r) => jsonOrThrow<unknown>(r, `GET ${path}`))
    .then((value) => {
      if (!value || typeof value !== "object") throw new Error("invalid dispatch lease response");
      const envelope = value as { count?: unknown; leases?: unknown };
      if (!Number.isInteger(envelope.count) || !Array.isArray(envelope.leases) ||
          envelope.count !== envelope.leases.length) throw new Error("invalid dispatch lease response");
      for (const item of envelope.leases) {
        if (!item || typeof item !== "object") throw new Error("invalid dispatch lease response");
        const lease = item as Record<string, unknown>;
        if (typeof lease.lease_id !== "string" || !lease.lease_id ||
            !(lease.holder_investigation_id === null || typeof lease.holder_investigation_id === "string") ||
            typeof lease.acquired_at !== "string" || typeof lease.diagnostic_deadline !== "string" ||
            !["active", "terminal_recoverable", "evidence_invalid"].includes(String(lease.recovery_state)) ||
            !(lease.terminal_action === null || ["investigation.completed", "investigation.failed", "investigation.chase_halted"].includes(String(lease.terminal_action))) ||
            ((lease.recovery_state === "terminal_recoverable") !== (lease.terminal_action !== null))) {
          throw new Error("invalid dispatch lease response");
        }
      }
      return value as { count: number; leases: LegalPolicyDispatchLease[] };
    });
}

export function recoverLegalPolicyDispatchLease(
  rootNodeId: string,
  leaseId: string,
  idempotencyKey: string,
): Promise<{ lease_id: string; recovered: true; idempotency_replayed: boolean }> {
  const path = `/research/plans/${encodeURIComponent(rootNodeId)}/legal-policy/dispatch-leases/${encodeURIComponent(leaseId)}/recover`;
  return apiFetch(`${API_BASE}${path}`, {
    method: "POST",
    cache: "no-store",
    headers: { "Content-Type": "application/json", "Idempotency-Key": idempotencyKey },
    body: "{}",
  }).then((r) => jsonOrThrow<unknown>(r, `POST ${path}`)).then((value) => {
    if (!value || typeof value !== "object") throw new Error("invalid dispatch recovery response");
    const receipt = value as Record<string, unknown>;
    if (receipt.lease_id !== leaseId || receipt.recovered !== true ||
        typeof receipt.idempotency_replayed !== "boolean") {
      throw new Error("invalid dispatch recovery response");
    }
    return value as { lease_id: string; recovered: true; idempotency_replayed: boolean };
  });
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

// ── Launch + session (SPR-06) ───────────────────────────────────────────

export function launchPlan(rootId: string, req: {
  expected_gather_mode: "contract_stub" | "exa_reasoning" | "authorized_multi_source";
  expected_gather_plan_fingerprint?: string | null;
  allow_contract_stub?: boolean;
  per_research_budget_usd?: number;
  aggregate_budget_usd?: number | null;
  research_tier?: "fast" | "deep" | "wrestle";
}, idempotencyKey: string): Promise<LaunchResponse> {
  return apiFetch(`${API_BASE}/research/plans/${encodeURIComponent(rootId)}/launch`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "Idempotency-Key": idempotencyKey,
    },
    body: JSON.stringify(req),
  }).then(async (r) => {
    if (r.status === 409) {
      const body = await r.text();
      try {
        const parsed = JSON.parse(body) as { detail?: { code?: unknown; session_id?: unknown } };
        if (parsed.detail?.code === "launch_outcome_unknown" &&
            typeof parsed.detail.session_id === "string" && parsed.detail.session_id) {
          throw new LaunchOutcomeUnknownError(parsed.detail.session_id);
        }
      } catch (error) {
        if (error instanceof LaunchOutcomeUnknownError) throw error;
      }
      throw new ApiError("POST cascade launch failed: HTTP 409", 409, body);
    }
    return jsonOrThrow<unknown>(r, "POST cascade launch");
  })
    .then(verifiedLaunchResponse);
}

export function getCascadeDriverReadiness(
  researchTier: "fast" | "deep" | "wrestle",
): Promise<CascadeDriverReadiness> {
  return get<CascadeDriverReadiness>(
    `/research/driver-readiness?research_tier=${encodeURIComponent(researchTier)}`,
  ).then((value) => {
    const row = value as unknown as Record<string, unknown>;
    const expected = [
      "availability_source", "candidate_rank", "model", "provider", "ready",
      "reason", "research_tier",
    ];
    if (Object.keys(row).sort().join("|") !== expected.sort().join("|") ||
        !["fast", "deep", "wrestle"].includes(String(row.research_tier)) ||
        typeof row.ready !== "boolean" ||
        !(row.provider === null || (typeof row.provider === "string" && row.provider)) ||
        !(row.model === null || (typeof row.model === "string" && row.model)) ||
        !(row.candidate_rank === null ||
          (typeof row.candidate_rank === "number" && Number.isInteger(row.candidate_rank) && row.candidate_rank > 0)) ||
        row.availability_source !== "boot_registered_providers" ||
        typeof row.reason !== "string" || !row.reason ||
        (row.ready && (row.provider === null || row.model === null || row.candidate_rank === null)) ||
        (!row.ready && (row.provider !== null || row.model !== null || row.candidate_rank !== null))) {
      throw new Error("invalid cascade driver readiness response");
    }
    return value;
  });
}

export function getLaunchAttemptStatus(
  rootId: string,
  idempotencyKey: string,
): Promise<LaunchAttemptStatus> {
  return apiFetch(`${API_BASE}/research/plans/${encodeURIComponent(rootId)}/launch-attempt`, {
    method: "GET",
    headers: { "Idempotency-Key": idempotencyKey },
  }).then(async (response) => {
    const value = await jsonOrThrow<unknown>(response, "GET cascade launch attempt");
    if (!value || typeof value !== "object") throw new Error("invalid cascade launch-attempt response");
    const row = value as Record<string, unknown>;
    const keys = Object.keys(row).sort();
    const expected = ["action", "launch_evidence_present", "plan_id", "response_integrity", "session_authority_present", "session_id", "state"].sort();
    if (keys.length !== expected.length || keys.some((key, index) => key !== expected[index]) ||
        typeof row.plan_id !== "string" || !row.plan_id ||
        typeof row.session_id !== "string" || !row.session_id ||
        (row.state !== "claimed" && row.state !== "completed") ||
        (row.response_integrity !== true && row.response_integrity !== null) ||
        typeof row.session_authority_present !== "boolean" ||
        typeof row.launch_evidence_present !== "boolean" ||
        (row.action !== "inspect_session" && row.action !== "await_operator_reconciliation")) {
      throw new Error("invalid cascade launch-attempt response");
    }
    return row as unknown as LaunchAttemptStatus;
  });
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
