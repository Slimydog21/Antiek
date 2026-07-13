/**
 * Midnight Oil API client — create → recommended ceiling → approve.
 * Mirrors interfaces/research/api/midnight_oil_routes.py
 * Deliverable view_format is always html (never PDF).
 */

import { API_BASE, apiFetch } from "../lib/api";

export type MidnightOilExecutionRequest = {
  launch_packet: Record<string, unknown>;
  approval_receipt: Record<string, unknown>;
  runner_handoff: Record<string, unknown>;
  applied_run_receipt: Record<string, unknown>;
  role_plans: Array<Record<string, unknown>>;
};

export type MidnightOilRouteReceipt = {
  route_receipt_id: string;
  task_kind: string;
  selected: {
    provider: string;
    model: string;
    reason_code: string;
    pricing_known: boolean;
  };
  budget: {
    cap_usd: number | null;
    actual_cost_usd: number | null;
  } | null;
};

export type MidnightOilExecutionReceipt = {
  receipt_id: string;
  run_id: string;
  status: "mock_completed";
  execution_mode: "synthetic" | "live";
  persisted: boolean;
  goal_fingerprint: string;
  role_outputs: Array<{
    role: "planner" | "gatherer" | "verifier" | "synthesizer";
    status: "synthetic_complete";
    execution_mode: "synthetic_no_provider";
    route_receipt: MidnightOilRouteReceipt;
    source_receipt_ids: string[];
    output_summary: string;
  }>;
  html_information_asset: string;
  twin_note_html: string;
  actual_cost_usd: number;
  dispatch_performed: boolean;
  budget_reserved: boolean;
  provider_calls_made: boolean;
  retrieval_performed: boolean;
  graph_mutated: boolean;
  final_artifact_created: boolean;
  notes: string[];
};

export async function executeMidnightOil(
  request: MidnightOilExecutionRequest,
): Promise<MidnightOilExecutionReceipt> {
  const res = await apiFetch(`${API_BASE}/research/midnight-oil/execute`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(request),
  });
  return readJson<MidnightOilExecutionReceipt>(res);
}

export type MidnightOilAcceptancePolicy = {
  policy_version: 1;
  required_coverage: "insights_and_output_paragraphs";
  exploratory_questions: "operational_only";
  external_receipts: "local_canonical_chunk_required";
  unsupported_output: "retain_operational_only";
  legacy_rows: "legacy_unverified";
};

export type MidnightOilGraphProjectionState = "pending" | "complete" | "refused";

export type MidnightOilGraphAdmissionReason =
  | "internal_local_chunk_temporarily_missing"
  | "operational_artifact_pending"
  | "graph_lock_unavailable"
  | "policy_authority_drift"
  | "legacy_unverified"
  | "claim_coverage_missing"
  | "receipt_malformed_or_forged"
  | "external_receipt_not_admissible_v1"
  | "deterministic_row_conflict";

export type MidnightOilLaunchContract = {
  acceptance_policy?: MidnightOilAcceptancePolicy | null;
  acceptance_policy_version?: 1 | null;
  research_brief_hash?: string | null;
  approved_research_brief_hash?: string | null;
  research_brief_state?:
    | "proposed"
    | "approved"
    | "authority_drift"
    | "legacy_unverified";
  research_result_state?: "none" | "receipt_only" | "returned" | null;
  deposit_state?: "pending" | "complete" | null;
  deposit_document_id?: string | null;
  graph_node_ids?: string[];
  graph_deliverable_id?: string | null;
  graph_projection_state?: MidnightOilGraphProjectionState | null;
  graph_projection_reason?: MidnightOilGraphAdmissionReason | null;
};

function normalizeGraphNavigation<T extends MidnightOilLaunchContract>(value: T): T {
  const rawNodeIds = value.graph_node_ids as unknown;
  const graphNodeIds =
    Array.isArray(rawNodeIds) &&
    rawNodeIds.every(
      (nodeId) =>
        typeof nodeId === "string" &&
        nodeId.length > 0 &&
        nodeId === nodeId.trim(),
    )
      ? [...rawNodeIds]
      : [];
  const rawDeliverableId = value.graph_deliverable_id as unknown;
  const graphDeliverableId =
    typeof rawDeliverableId === "string" &&
    rawDeliverableId.length > 0 &&
    rawDeliverableId === rawDeliverableId.trim()
      ? rawDeliverableId
      : null;
  return {
    ...value,
    graph_node_ids: graphNodeIds,
    graph_deliverable_id: graphDeliverableId,
  };
}

export type MidnightOilAdmissionPresentation = {
  state:
    | "not_started"
    | "no_result"
    | "receipt_only"
    | "operational_pending"
    | "admitted"
    | "refused"
    | "reconciliation_required"
    | "unknown";
  reason: MidnightOilGraphAdmissionReason | "unknown" | null;
  heading: string;
  detail: string;
  verified: boolean;
};

const GRAPH_REASON_COPY: Record<MidnightOilGraphAdmissionReason, string> = {
  internal_local_chunk_temporarily_missing:
    "A cited local source is temporarily unavailable. Retry graph admission without rerunning research.",
  operational_artifact_pending:
    "The operational HTML is not ready for graph admission yet. Keep the artifact and retry admission later.",
  graph_lock_unavailable:
    "The knowledge graph is busy. Retry admission without rerunning research.",
  policy_authority_drift:
    "The approved research brief no longer matches durable authority. Reconciliation is required.",
  legacy_unverified:
    "This run predates the approved evidence policy. Its HTML remains operational, not verified knowledge.",
  claim_coverage_missing:
    "At least one returned claim lacks exact local evidence coverage. The HTML remains operational only.",
  receipt_malformed_or_forged:
    "A source receipt failed integrity checks. The HTML remains operational only.",
  external_receipt_not_admissible_v1:
    "V1 requires a locally canonical source chunk. External-only evidence remains operational only.",
  deterministic_row_conflict:
    "Durable graph data conflicts with this projection. Reconciliation is required before admission.",
};

const GRAPH_STATES = new Set<MidnightOilGraphProjectionState>([
  "pending",
  "complete",
  "refused",
]);
const GRAPH_REASONS = new Set<MidnightOilGraphAdmissionReason>(
  Object.keys(GRAPH_REASON_COPY) as MidnightOilGraphAdmissionReason[],
);
const RETRYABLE_GRAPH_REASONS = new Set<MidnightOilGraphAdmissionReason>([
  "internal_local_chunk_temporarily_missing",
  "operational_artifact_pending",
  "graph_lock_unavailable",
]);
const REFUSED_GRAPH_REASONS = new Set<MidnightOilGraphAdmissionReason>([
  "policy_authority_drift",
  "legacy_unverified",
  "claim_coverage_missing",
  "receipt_malformed_or_forged",
  "external_receipt_not_admissible_v1",
  "deterministic_row_conflict",
]);

export function isMidnightOilAcceptancePolicy(
  value: unknown,
): value is MidnightOilAcceptancePolicy {
  if (typeof value !== "object" || value === null) return false;
  const policy = value as Record<string, unknown>;
  return (
    Object.keys(policy).length === 6 &&
    policy.policy_version === 1 &&
    policy.required_coverage === "insights_and_output_paragraphs" &&
    policy.exploratory_questions === "operational_only" &&
    policy.external_receipts === "local_canonical_chunk_required" &&
    policy.unsupported_output === "retain_operational_only" &&
    policy.legacy_rows === "legacy_unverified"
  );
}

export function describeMidnightOilAdmission(job: {
  status?: unknown;
  graph_projection_state?: unknown;
  graph_projection_reason?: unknown;
  research_brief_state?: unknown;
  research_result_state?: unknown;
  deposit_state?: unknown;
  acceptance_policy?: unknown;
  acceptance_policy_version?: unknown;
  research_brief_hash?: unknown;
  approved_research_brief_hash?: unknown;
}): MidnightOilAdmissionPresentation {
  const rawState = job.graph_projection_state;
  const state = GRAPH_STATES.has(rawState as MidnightOilGraphProjectionState)
    ? (rawState as MidnightOilGraphProjectionState)
    : null;
  const rawReason = job.graph_projection_reason;
  const reason =
    rawReason == null
      ? null
      : GRAPH_REASONS.has(rawReason as MidnightOilGraphAdmissionReason)
        ? (rawReason as MidnightOilGraphAdmissionReason)
        : "unknown";
  const briefHash = job.research_brief_hash;
  const approvedBriefHash = job.approved_research_brief_hash;
  const validBriefHashes =
    typeof briefHash === "string" &&
    /^[0-9a-f]{64}$/.test(briefHash) &&
    typeof approvedBriefHash === "string" &&
    /^[0-9a-f]{64}$/.test(approvedBriefHash);
  const briefHashMismatch = validBriefHashes && briefHash !== approvedBriefHash;
  if (
    job.acceptance_policy_version !== 1 ||
    !isMidnightOilAcceptancePolicy(job.acceptance_policy)
  ) {
    return {
      state: "unknown",
      reason,
      heading: "Research acceptance policy is unknown",
      detail:
        "The server did not return the exact V1 evidence policy. Approval and verified knowledge presentation are disabled.",
      verified: false,
    };
  }
  const contradictoryGraphContract =
    (state === null && reason !== null) ||
    (state === "complete" && reason !== null) ||
    (state === "refused" &&
      (reason === null ||
        reason === "unknown" ||
        !REFUSED_GRAPH_REASONS.has(reason))) ||
    (state === "pending" &&
      reason !== null &&
      (reason === "unknown" || !RETRYABLE_GRAPH_REASONS.has(reason)));
  if (contradictoryGraphContract) {
    return {
      state: "unknown",
      reason,
      heading: "Knowledge admission state is contradictory",
      detail:
        "The graph state and reason violate the closed admission contract. Keep the HTML operational and do not expose graph navigation.",
      verified: false,
    };
  }
  if (
    job.research_brief_state === "authority_drift" ||
    job.status === "failed_reconcile" ||
    reason === "policy_authority_drift" ||
    reason === "deterministic_row_conflict" ||
    briefHashMismatch
  ) {
    return {
      state: "reconciliation_required",
      reason,
      heading: "Reconciliation required",
      detail:
        reason && reason !== "unknown"
          ? GRAPH_REASON_COPY[reason]
          : "Durable authority or graph state is inconsistent. Do not treat this output as verified knowledge.",
      verified: false,
    };
  }
  if (
    state === "complete" &&
    (job.research_brief_state !== "approved" || !validBriefHashes)
  ) {
    return {
      state: "unknown",
      reason,
      heading: "Approved research brief is unavailable",
      detail:
        "Verified knowledge requires matching canonical and approved research brief hashes. Keep the HTML operational until authority is reconciled.",
      verified: false,
    };
  }
  if (reason === "unknown") {
    return {
      state: "unknown",
      reason,
      heading: "Knowledge admission state is unknown",
      detail:
        "The server returned an admission combination this client does not recognize. Keep the HTML operational and do not treat it as verified knowledge.",
      verified: false,
    };
  }
  if (state === "complete") {
    return {
      state: "admitted",
      reason: null,
      heading: "Admitted to the knowledge graph",
      detail: "Every policy-covered claim passed exact local evidence checks.",
      verified: true,
    };
  }
  if (state === "refused") {
    return {
      state: "refused",
      reason,
      heading: "Operational HTML retained; graph admission refused",
      detail:
        reason
          ? GRAPH_REASON_COPY[reason]
          : "The refusal reason is unknown. Keep the HTML operational and do not treat it as verified knowledge.",
      verified: false,
    };
  }
  if (
    state === "pending" &&
    (job.status === "awaiting_approval" ||
      job.status === "approved" ||
      job.status === "consent_issued" ||
      job.status === "queued" ||
      job.status === "running")
  ) {
    return {
      state: "not_started",
      reason,
      heading: job.status === "running" ? "Research is running" : "Research has not finished",
      detail:
        "No terminal research result exists yet, so nothing has been evaluated for knowledge admission.",
      verified: false,
    };
  }
  if (state === "pending" && job.research_result_state === "receipt_only") {
    return {
      state: "receipt_only",
      reason,
      heading: "Operational receipts retained; no research result returned",
      detail: "Receipts are audit evidence, not a supported finding. Nothing has been admitted to the graph.",
      verified: false,
    };
  }
  if (state === "pending" && job.research_result_state === "none") {
    return {
      state: "no_result",
      reason,
      heading: "No research result returned",
      detail:
        job.deposit_state === "complete"
          ? "The honest operational HTML remains available, but it contains no verified finding."
          : "No operational HTML has been deposited and nothing has been admitted to the graph.",
      verified: false,
    };
  }
  if (state === "pending") {
    return {
      state: "operational_pending",
      reason,
      heading: "Operational output retained; graph admission pending",
      detail:
        reason
          ? GRAPH_REASON_COPY[reason]
          : "The HTML may be reopened, but its claims are not verified knowledge yet.",
      verified: false,
    };
  }
  return {
    state: "unknown",
    reason,
    heading: "Graph admission status unavailable",
    detail: "Keep the output operational and do not treat it as verified knowledge.",
    verified: false,
  };
}

export type MidnightOilJobResponse = {
  job_id: string;
  goals: string[];
  duration_minutes: number;
  model_id?: string | null;
  /** Residual (gs): curated fast|deep|wrestle for autonomous depth. */
  research_tier?: "fast" | "deep" | "wrestle" | string | null;
  /** Residual (ada): fan-out depth used in ceiling formula (default 3). */
  fanout_depth?: number | null;
  status: string;
  operation_state?: string;
  recommended_price_ceiling_usd: number;
  approved_ceiling_usd?: number | null;
  force_below_recommended?: boolean;
  asset_id?: string | null;
  graph_projection_state?: MidnightOilGraphProjectionState | null;
  graph_projection_reason?: MidnightOilGraphAdmissionReason | null;
  graph_node_ids?: string[];
  graph_deliverable_id?: string | null;
  notes?: string;
  view_format: "html";
  runnable: boolean;
  html?: string;
} & MidnightOilLaunchContract;

type SpendConsentResponse = MidnightOilLaunchContract & {
  token: string;
  operation_id: string;
  ceiling_cents: number;
  issued_at_ms: number;
  expires_at_ms: number;
};

type PendingConsent = {
  token: string;
  ceilingCents: number;
  expiresAtMs: number;
  attempted: boolean;
  job: MidnightOilJobResponse;
};

// Consent is bearer authority and intentionally lives only in page memory.
// Never persist it to localStorage, sessionStorage, URLs, logs, or UI state.
const pendingConsentByJob = new Map<string, PendingConsent>();

export class MidnightOilConsentExpiredError extends Error {
  constructor() {
    super("Midnight Oil spend consent expired; approve again");
    this.name = "MidnightOilConsentExpiredError";
  }
}

async function readJson<T>(res: Response): Promise<T> {
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`midnight-oil API ${res.status}: ${text.slice(0, 200)}`);
  }
  return (await res.json()) as T;
}

/** Residual (hy): offline-vs-live worker step readiness. */
export type MidnightOilLiveStepStatusResponse = {
  view_format: "html" | string;
  product_panel: string;
  source: string;
  offline_honest: boolean;
  live_env: boolean;
  injector_installed: boolean;
  live_env_flag: string;
  notes: string[];
  html?: string | null;
};

export async function fetchMidnightOilLiveStepStatus(): Promise<MidnightOilLiveStepStatusResponse> {
  const res = await apiFetch(`${API_BASE}/midnight-oil/live-step-status`);
  return readJson<MidnightOilLiveStepStatusResponse>(res);
}

export async function createMidnightOilJob(body: {
  goals: string[];
  duration_minutes: number;
  model_id?: string | null;
  fanout_depth?: number;
  asset_id?: string | null;
  /** Residual (gs): fast | deep | wrestle */
  research_tier?: "fast" | "deep" | "wrestle" | string | null;
}): Promise<MidnightOilJobResponse> {
  const res = await apiFetch(`${API_BASE}/midnight-oil/create`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  return normalizeGraphNavigation(await readJson<MidnightOilJobResponse>(res));
}

export async function approveMidnightOilCeiling(body: {
  job_id: string;
  ceiling_usd?: number | null;
  use_recommended?: boolean;
  force_below?: boolean;
}): Promise<MidnightOilJobResponse> {
  const job = await getMidnightOilJob(body.job_id);
  if (
    job.acceptance_policy_version !== 1 ||
    !isMidnightOilAcceptancePolicy(job.acceptance_policy)
  ) {
    throw new Error("Midnight Oil approval requires the exact v1 research acceptance policy");
  }
  let ceilingCents: number | null = null;
  if (!body.use_recommended) {
    const usd = body.ceiling_usd;
    if (typeof usd !== "number" || !Number.isFinite(usd) || usd <= 0) {
      throw new Error("custom Midnight Oil ceiling must be a positive USD amount");
    }
    const roundedUsd = Math.round(usd * 100) / 100;
    if (usd !== roundedUsd) {
      throw new Error("custom Midnight Oil ceiling supports at most two decimal places");
    }
    ceilingCents = Math.round(roundedUsd * 100);
  }
  const res = await apiFetch(
    `${API_BASE}/midnight-oil/jobs/${encodeURIComponent(body.job_id)}/spend-consent`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        ceiling_cents: ceilingCents,
        use_recommended: Boolean(body.use_recommended),
        force_below: Boolean(body.force_below),
        acceptance_policy_version: job.acceptance_policy_version,
      }),
    },
  );
  const consent = normalizeGraphNavigation(await readJson<SpendConsentResponse>(res));
  pendingConsentByJob.set(body.job_id, {
    token: consent.token,
    ceilingCents: consent.ceiling_cents,
    expiresAtMs: consent.expires_at_ms,
    attempted: false,
    job,
  });
  return {
    ...job,
    status: "approved",
    approved_ceiling_usd: consent.ceiling_cents / 100,
    runnable: true,
    acceptance_policy: consent.acceptance_policy,
    acceptance_policy_version: consent.acceptance_policy_version,
    research_brief_hash: consent.research_brief_hash,
    approved_research_brief_hash: consent.approved_research_brief_hash,
    research_brief_state: consent.research_brief_state,
    research_result_state: consent.research_result_state,
    deposit_state: consent.deposit_state,
    deposit_document_id: consent.deposit_document_id,
    graph_projection_state: consent.graph_projection_state,
    graph_projection_reason: consent.graph_projection_reason,
    graph_node_ids: consent.graph_node_ids,
    graph_deliverable_id: consent.graph_deliverable_id,
  };
}

export async function getMidnightOilJob(
  jobId: string,
): Promise<MidnightOilJobResponse> {
  const res = await apiFetch(`${API_BASE}/midnight-oil/jobs/${encodeURIComponent(jobId)}`);
  return normalizeGraphNavigation(await readJson<MidnightOilJobResponse>(res));
}

/** Deposit job results: HTML asset + twins + optional progress/usage. */
export type MidnightOilDepositResponse = MidnightOilLaunchContract & {
  job_id: string;
  asset_id: string;
  document_id: string;
  twin_count: number;
  spawn_ids: string[];
  draft_combined: boolean;
  usage_recorded: boolean;
  usage_event?: Record<string, unknown> | null;
  progress_seeded: boolean;
  progress?: {
    spawn_id?: string;
    event_count?: number;
    latest_stage?: string | null;
    is_terminal?: boolean;
    view_format?: string;
    html?: string | null;
    events?: Array<{ stage: string; message: string; sequence: number }>;
  } | null;
  job_status?: string | null;
  view_format: "html" | string;
  html?: string | null;
  product_panel?: string;
  source?: string;
  notes?: string[];
  graph_projection_state?: MidnightOilGraphProjectionState | null;
  graph_projection_reason?: MidnightOilGraphAdmissionReason | null;
};

export async function depositMidnightOilJob(body: {
  job_id: string;
  draft_combined?: boolean;
  record_progress?: boolean;
  mark_complete?: boolean;
  include_progress_html?: boolean;
}): Promise<MidnightOilDepositResponse> {
  const res = await apiFetch(`${API_BASE}/midnight-oil/deposit`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      job_id: body.job_id,
      draft_combined: body.draft_combined ?? true,
      record_progress: body.record_progress ?? true,
      mark_complete: body.mark_complete ?? true,
      include_progress_html: body.include_progress_html ?? true,
    }),
  });
  return normalizeGraphNavigation(await readJson<MidnightOilDepositResponse>(res));
}

/** Offline worker run (no live multi-provider calls). */
export type MidnightOilRunResponse = MidnightOilLaunchContract & {
  job_id: string;
  status: string;
  spent_usd: number;
  approved_ceiling_usd?: number | null;
  spawn_ids: string[];
  goals_total: number;
  steps_cap: number;
  elapsed_ms: number;
  notes?: string;
  view_format: "html" | string;
  runnable: boolean;
  offline: boolean;
  /** Residual (bs/by): true when env + injector used live steps */
  live_step?: boolean;
  live_step_env?: string;
  live_step_env_enabled?: boolean;
  product_panel?: string;
  source?: string;
  notes_list?: string[];
  html?: string | null;
  deposit?: MidnightOilDepositResponse | null;
  /** Durable queue acknowledgement; execution occurs in the worker process. */
  queued?: boolean;
  operation_id?: string;
  queue_state?: string;
  graph_projection_state?: MidnightOilGraphProjectionState | null;
  graph_projection_reason?: MidnightOilGraphAdmissionReason | null;
};

export async function runMidnightOilJob(body: {
  job_id: string;
  max_steps?: number | null;
  spent_per_goal?: number;
  auto_deposit?: boolean;
  draft_combined?: boolean;
}): Promise<MidnightOilRunResponse> {
  const consent = pendingConsentByJob.get(body.job_id);
  if (!consent) {
    throw new Error("Midnight Oil run requires fresh in-memory spend consent");
  }
  if (!consent.attempted && Date.now() >= consent.expiresAtMs) {
    pendingConsentByJob.delete(body.job_id);
    throw new MidnightOilConsentExpiredError();
  }
  // Retain the token after an ambiguous failure so the exact bearer can repair
  // claim→CAS or CAS→enqueue. It is deleted only after an authoritative reply.
  consent.attempted = true;
  const res = await apiFetch(`${API_BASE}/midnight-oil/run`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-Midnight-Oil-Spend-Consent": consent.token,
    },
    body: JSON.stringify({
      job_id: body.job_id,
      max_steps: body.max_steps ?? null,
      spent_per_goal: body.spent_per_goal ?? 0.05,
      auto_deposit: Boolean(body.auto_deposit),
      draft_combined: body.draft_combined ?? true,
      force_offline: true,
    }),
  });
  if (!res.ok && res.status >= 400 && res.status < 500) {
    // Definitive client/authority rejection is not an ambiguous network/5xx
    // outcome. Never extend bearer lifetime after the server has rejected it.
    pendingConsentByJob.delete(body.job_id);
    if (res.status === 403) {
      throw new MidnightOilConsentExpiredError();
    }
  }
  const queued = normalizeGraphNavigation(
    await readJson<
      {
        job_id: string;
        operation_id: string;
        state: string;
      } & MidnightOilLaunchContract
    >(res),
  );
  pendingConsentByJob.delete(body.job_id);
  const state = queued.state;
  const isQueued = state === "queued";
  const isPending = state === "queued" || state === "running";
  return {
    job_id: queued.job_id,
    status: state,
    spent_usd: 0,
    approved_ceiling_usd: consent.ceilingCents / 100,
    spawn_ids: [],
    goals_total: consent.job.goals.length,
    steps_cap: body.max_steps ?? 0,
    elapsed_ms: 0,
    view_format: "html",
    runnable: false,
    offline: true,
    live_step: false,
    notes: isPending
      ? `Durable operation is ${state}; the worker has not reported a terminal result yet.`
      : `Durable operation replay converged at terminal state ${state}.`,
    notes_list: [
      "Spend consent claimed once and operation durably queued.",
      "Execution and optional deposit occur in the worker process; refresh job status before claiming completion.",
    ],
    html: isPending
      ? "<p>Midnight Oil execution is pending.</p>"
      : "<p>Midnight Oil execution reached a terminal state.</p>",
    deposit: null,
    queued: isQueued,
    operation_id: queued.operation_id,
    queue_state: queued.state,
    graph_projection_state: queued.graph_projection_state,
    graph_projection_reason: queued.graph_projection_reason,
    acceptance_policy: queued.acceptance_policy,
    acceptance_policy_version: queued.acceptance_policy_version,
    research_brief_hash: queued.research_brief_hash,
    approved_research_brief_hash: queued.approved_research_brief_hash,
    research_brief_state: queued.research_brief_state,
    research_result_state: queued.research_result_state,
    deposit_state: queued.deposit_state,
    deposit_document_id: queued.deposit_document_id,
    graph_node_ids: queued.graph_node_ids,
    graph_deliverable_id: queued.graph_deliverable_id,
  };
}
