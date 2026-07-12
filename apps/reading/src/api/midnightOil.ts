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
  recommended_price_ceiling_usd: number;
  approved_ceiling_usd?: number | null;
  force_below_recommended?: boolean;
  asset_id?: string | null;
  notes?: string;
  view_format: "html";
  runnable: boolean;
  html?: string;
  spawn_ids?: string[];
  lifecycle?: MidnightOilLifecycleStatus;
};

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
  live?: boolean;
}): Promise<MidnightOilJobResponse> {
  const res = await apiFetch(`${API_BASE}/midnight-oil/create`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  return readJson<MidnightOilJobResponse>(res);
}

export type MidnightOilSpendConsentResponse = {
  token: string;
  operation_id: string;
  ceiling_cents: number;
  issued_at_ms: number;
  expires_at_ms: number;
};

export type MidnightOilEnqueueResponse = {
  job_id: string;
  operation_id: string;
  state: "queued" | string;
};

export type MidnightOilLifecycleState =
  | "consent_required"
  | "consent_issued"
  | "consent_delivery_failed"
  | "queued"
  | "leased"
  | "lease_pending"
  | "blocked_provider"
  | "reconcile_required"
  | "deposit_pending"
  | "projection_pending"
  | "archive_pending"
  | "complete"
  | "failed"
  | "budget_halted"
  | "timed_out";

export type MidnightOilLifecycleStatus = {
  schema_version: 1;
  job_id: string;
  operation_id: string | null;
  state: MidnightOilLifecycleState;
  terminal_outcome:
    | "complete"
    | "blocked_provider"
    | "failed"
    | "failed_reconcile"
    | "budget_halted"
    | "timed_out"
    | null;
  approved_ceiling_cents: number | null;
  confirmed_spent_cents: number;
  reserved_cents: number;
  unknown_outcome: boolean;
  remaining_cents: number | null;
  cost_state: "not_reserved" | "reserved" | "unknown_outcome" | "settled";
  consent_expires_at_ms: number | null;
  enqueued_at_ms: number | null;
  lease_expires_at_ms: number | null;
  completed_at_ms: number | null;
  deposit_document_id: string | null;
  deposit_href: string | null;
  graph_deliverable_id: string | null;
  graph_deep_links: string[];
  operator_action: string;
  view_format: "html";
};

export type MidnightOilConsentResetResponse = {
  schema_version: 1;
  job_id: string;
  state: "consent_required";
  operation_state: "none";
  state_version: number;
  operator_action: "issue_consent";
};

export async function issueMidnightOilSpendConsent(body: {
  job_id: string;
  ceiling_usd?: number | null;
  use_recommended?: boolean;
  force_below?: boolean;
}): Promise<MidnightOilSpendConsentResponse> {
  const scaledCeiling =
    body.ceiling_usd == null ? null : body.ceiling_usd * 100;
  const ceilingCents = scaledCeiling == null ? null : Math.round(scaledCeiling);
  if (
    ceilingCents != null &&
    (!Number.isSafeInteger(ceilingCents) ||
      ceilingCents < 1 ||
      scaledCeiling == null ||
      Math.abs(scaledCeiling - ceilingCents) > 1e-7)
  ) {
    throw new Error("Midnight Oil ceiling must be positive with at most two decimals");
  }
  const res = await apiFetch(
    `${API_BASE}/midnight-oil/jobs/${encodeURIComponent(body.job_id)}/spend-consent`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        ceiling_cents: body.use_recommended ? null : ceilingCents,
        use_recommended: Boolean(body.use_recommended),
        force_below: Boolean(body.force_below),
      }),
    },
  );
  return readJson<MidnightOilSpendConsentResponse>(res);
}

export async function enqueueMidnightOilJob(
  jobId: string,
  spendConsent: string,
): Promise<MidnightOilEnqueueResponse> {
  if (!spendConsent) throw new Error("Midnight Oil spend consent is required");
  const res = await apiFetch(`${API_BASE}/midnight-oil/run`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-Midnight-Oil-Spend-Consent": spendConsent,
    },
    body: JSON.stringify({
      job_id: jobId,
      max_steps: null,
      auto_deposit: true,
      draft_combined: true,
      force_offline: false,
    }),
  });
  return readJson<MidnightOilEnqueueResponse>(res);
}

export async function resetMidnightOilSpendConsent(
  jobId: string,
): Promise<MidnightOilConsentResetResponse> {
  const res = await apiFetch(
    `${API_BASE}/midnight-oil/jobs/${encodeURIComponent(jobId)}/spend-consent`,
    { method: "DELETE", cache: "no-store" },
  );
  return readJson<MidnightOilConsentResetResponse>(res);
}

export async function getMidnightOilLifecycle(
  jobId: string,
): Promise<MidnightOilLifecycleStatus> {
  const res = await apiFetch(
    `${API_BASE}/midnight-oil/jobs/${encodeURIComponent(jobId)}/status`,
    { cache: "no-store" },
  );
  return readJson<MidnightOilLifecycleStatus>(res);
}

/**
 * Explicit confirmation boundary. The credential remains a stack-local value,
 * is sent once as a header, and is unreachable after this function returns.
 */
export async function approveMidnightOilCeiling(body: {
  job_id: string;
  ceiling_usd?: number | null;
  use_recommended?: boolean;
  force_below?: boolean;
}): Promise<MidnightOilJobResponse> {
  const consent = await issueMidnightOilSpendConsent(body);
  await enqueueMidnightOilJob(body.job_id, consent.token);
  const [job, lifecycle] = await Promise.all([
    getMidnightOilJob(body.job_id),
    getMidnightOilLifecycle(body.job_id),
  ]);
  return {
    ...job,
    status: lifecycle.state,
    approved_ceiling_usd: consent.ceiling_cents / 100,
    runnable: false,
    lifecycle,
  };
}

export async function getMidnightOilJob(
  jobId: string,
): Promise<MidnightOilJobResponse> {
  const res = await apiFetch(`${API_BASE}/midnight-oil/jobs/${encodeURIComponent(jobId)}`);
  return readJson<MidnightOilJobResponse>(res);
}

/** Deposit job results: HTML asset + twins + optional progress/usage. */
export type MidnightOilDepositResponse = {
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
  return readJson<MidnightOilDepositResponse>(res);
}

/** Offline worker run (no live multi-provider calls). */
export type MidnightOilRunResponse = {
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
};

export async function runMidnightOilJob(body: {
  job_id: string;
  max_steps?: number | null;
  spent_per_goal?: number;
  auto_deposit?: boolean;
  draft_combined?: boolean;
}): Promise<MidnightOilRunResponse> {
  void body;
  throw new Error(
    "Synchronous Midnight Oil execution is retired; issue consent and enqueue the durable worker",
  );
}

export async function fetchMidnightOilArtifact(jobId: string): Promise<string> {
  const res = await apiFetch(
    `${API_BASE}/midnight-oil/jobs/${encodeURIComponent(jobId)}/artifact`,
    { cache: "no-store" },
  );
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`midnight-oil artifact ${res.status}: ${text.slice(0, 200)}`);
  }
  const contentType = res.headers.get("content-type") || "";
  if (!contentType.toLowerCase().startsWith("text/html")) {
    throw new Error("Midnight Oil artifact must be text/html");
  }
  return res.text();
}
