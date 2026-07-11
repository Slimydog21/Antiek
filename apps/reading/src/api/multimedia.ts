import { API_BASE, apiFetch } from "../lib/api";

export type MultimediaMode = "video" | "audio" | "hybrid";
export type MultimediaRoutePolicy = "cheapest" | "balanced" | "highest_quality";
export type MultimediaKind = "information_video" | "documentary_video" | "audio_experience";
export type MultimediaJobKind = "render" | "steering" | "hardening" | "provider_execution";
export type MultimediaJobStatus = "queued" | "running" | "succeeded" | "failed" | "canceled" | "partial";

export interface CreateMultimediaDraftRequest {
  topic: string;
  target_minutes: number;
  mode: MultimediaMode;
  route_policy: MultimediaRoutePolicy;
  sources?: string[];
  must_cover?: string[];
  avoid?: string[];
  audience?: string;
  style?: string | null;
}

export interface LiveProviderExecutionRequest {
  max_budget_usd: number;
  route_policy: MultimediaRoutePolicy;
  operator_acknowledged_spend: boolean;
  provider_families?: string[];
  dry_run_revision_id?: string | null;
}

export interface MultimediaAssetSummary {
  asset_id: string;
  revision_id: string;
  title: string;
  kind: MultimediaKind;
  status: string;
  requested_duration_minutes: number;
  route_policy: MultimediaRoutePolicy;
  estimated_cost_usd: number;
  hardening_status: string | null;
  latest_job_status: MultimediaJobStatus | null;
  latest_job_kind: MultimediaJobKind | null;
}

export interface MultimediaAssetList {
  assets: MultimediaAssetSummary[];
  count: number;
}

export interface GateResult {
  gate_id: string;
  status: "pass" | "fail" | "manual";
  findings: unknown[];
}

export interface MultimediaHardeningReport {
  asset_id: string;
  revision_id: string;
  ship_status: "pass" | "blocked" | "manual_review";
  gates: GateResult[];
  residual_risks: string[];
}

export interface MultimediaAssetRecord {
  asset: {
    asset_id: string;
    revision_id: string;
    status: string;
    kind: MultimediaKind;
    title: string;
    route_policy: MultimediaRoutePolicy;
    requested_duration_minutes: number;
    parent_revision_id?: string | null;
    steering_event_id?: string | null;
    manifest: unknown;
  };
  plan: unknown;
  mode: MultimediaMode;
  style: string | null;
  hardening_report: MultimediaHardeningReport | null;
  latest_steering_intent: unknown | null;
  jobs: MultimediaJobRecord[];
}

export interface MultimediaJobRecord {
  job_id: string;
  asset_id: string;
  revision_id: string;
  sequence: number;
  kind: MultimediaJobKind;
  status: MultimediaJobStatus;
  progress_percent: number;
  message: string;
  error_code: string | null;
  retryable: boolean | null;
}

export interface MultimediaJobList {
  jobs: MultimediaJobRecord[];
  count: number;
}

export type TtsReconciliationAction = "quarantine_send" | "recover_unknown" | "release_seal";

export interface ChapterTtsReconciliation {
  execution_id: string;
  asset_id: string;
  revision_id: string;
  attempt_status: string;
  provider_status: string;
  next_action: string;
  action_eligible: boolean;
  send_age_seconds: number | null;
  seal_age_seconds: number | null;
  seal_lease_id: string | null;
  charged_cents: number;
  full_ceiling_charged: boolean;
  raw_audio_present: boolean;
  raw_audio_hash_valid: boolean;
  requires_signed_operator_authority: boolean;
  requires_external_provider_evidence: boolean;
  parent_resume_eligible: boolean;
  safe_error_code: string | null;
}

export interface NarrationRunReconciliationChild {
  chapter_id: string;
  execution_id: string;
  state: string;
  next_action: string;
  action_eligible: boolean;
  reconciliation: ChapterTtsReconciliation | null;
}

export interface NarrationRunReconciliation {
  run_id: string;
  asset_id: string;
  revision_id: string;
  run_status: string;
  blocked_chapter_count: number;
  parent_resume_eligible: boolean;
  children: NarrationRunReconciliationChild[];
}

export interface AssetReconciliationExecutionLink {
  execution_id: string;
  revision_id: string;
  provider: string;
  status: string;
  reconciliation_available: boolean;
}

export interface AssetReconciliationRunLink {
  run_id: string;
  revision_id: string;
  status: string;
}

export interface AssetReconciliationLinks {
  asset_id: string;
  revision_id: string;
  executions: AssetReconciliationExecutionLink[];
  narration_runs: AssetReconciliationRunLink[];
}

// The API serializes `gates` only; failed_gate_ids/manual_gate_ids are plain
// @property in hardening.py and are dropped by pydantic v2. Derive client-side.
export function failedGateIds(report: MultimediaHardeningReport): string[] {
  return (report.gates ?? []).filter((gate) => gate.status === "fail").map((gate) => gate.gate_id);
}

export function manualGateIds(report: MultimediaHardeningReport): string[] {
  return (report.gates ?? []).filter((gate) => gate.status === "manual").map((gate) => gate.gate_id);
}

export async function createMultimediaDraft(
  request: CreateMultimediaDraftRequest,
): Promise<MultimediaAssetRecord> {
  const resp = await apiFetch(`${API_BASE}/multimedia/assets`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(request),
  });
  if (!resp.ok) throw new Error(`POST /multimedia/assets: HTTP ${resp.status}`);
  return (await resp.json()) as MultimediaAssetRecord;
}

export async function listMultimediaAssets(): Promise<MultimediaAssetList> {
  const resp = await apiFetch(`${API_BASE}/multimedia/assets`);
  if (!resp.ok) throw new Error(`GET /multimedia/assets: HTTP ${resp.status}`);
  return (await resp.json()) as MultimediaAssetList;
}

export async function getMultimediaAsset(assetId: string): Promise<MultimediaAssetRecord> {
  const resp = await apiFetch(`${API_BASE}/multimedia/assets/${encodeURIComponent(assetId)}`);
  if (resp.status === 404) throw new Error("multimedia_asset_not_found");
  if (!resp.ok) throw new Error(`GET /multimedia/assets/{id}: HTTP ${resp.status}`);
  return (await resp.json()) as MultimediaAssetRecord;
}

export async function listMultimediaJobs(assetId: string): Promise<MultimediaJobList> {
  const resp = await apiFetch(`${API_BASE}/multimedia/assets/${encodeURIComponent(assetId)}/jobs`);
  if (resp.status === 404) throw new Error("multimedia_asset_not_found");
  if (!resp.ok) throw new Error(`GET /multimedia/assets/{id}/jobs: HTTP ${resp.status}`);
  return (await resp.json()) as MultimediaJobList;
}

export async function approveMultimediaDryRun(assetId: string): Promise<MultimediaAssetRecord> {
  const resp = await apiFetch(`${API_BASE}/multimedia/assets/${encodeURIComponent(assetId)}/approve-dry-run`, {
    method: "POST",
  });
  if (!resp.ok) throw new Error(`POST /multimedia/assets/{id}/approve-dry-run: HTTP ${resp.status}`);
  return (await resp.json()) as MultimediaAssetRecord;
}

export async function steerMultimediaAsset(
  assetId: string,
  request: { prompt: string; raw_voice_transcript?: string | null; corrected_voice_transcript?: string | null },
): Promise<MultimediaAssetRecord> {
  const resp = await apiFetch(`${API_BASE}/multimedia/assets/${encodeURIComponent(assetId)}/steer`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(request),
  });
  if (resp.status === 409) throw new Error("multimedia_steering_needs_clarification");
  if (!resp.ok) throw new Error(`POST /multimedia/assets/{id}/steer: HTTP ${resp.status}`);
  return (await resp.json()) as MultimediaAssetRecord;
}

export async function runMultimediaHardening(assetId: string): Promise<MultimediaAssetRecord> {
  const resp = await apiFetch(`${API_BASE}/multimedia/assets/${encodeURIComponent(assetId)}/hardening`, {
    method: "POST",
  });
  if (!resp.ok) throw new Error(`POST /multimedia/assets/{id}/hardening: HTTP ${resp.status}`);
  return (await resp.json()) as MultimediaAssetRecord;
}

export async function prepareMultimediaLiveExecution(
  assetId: string,
  request: LiveProviderExecutionRequest,
): Promise<MultimediaAssetRecord> {
  const resp = await apiFetch(`${API_BASE}/multimedia/assets/${encodeURIComponent(assetId)}/prepare-live-execution`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(request),
  });
  if (resp.status === 404) throw new Error("multimedia_asset_not_found");
  if (!resp.ok) throw new Error(`POST /multimedia/assets/{id}/prepare-live-execution: HTTP ${resp.status}`);
  return (await resp.json()) as MultimediaAssetRecord;
}

export async function getChapterTtsReconciliation(
  executionId: string,
): Promise<ChapterTtsReconciliation> {
  const resp = await apiFetch(
    `${API_BASE}/multimedia/executions/${encodeURIComponent(executionId)}/tts-reconciliation`,
  );
  if (resp.status === 404) throw new Error("multimedia_execution_unavailable");
  if (resp.status === 503) throw new Error("multimedia_reconciliation_runtime_unavailable");
  if (!resp.ok) throw new Error(`GET /multimedia/executions/{id}/tts-reconciliation: HTTP ${resp.status}`);
  return (await resp.json()) as ChapterTtsReconciliation;
}

export async function getAssetReconciliationLinks(
  assetId: string,
): Promise<AssetReconciliationLinks> {
  const resp = await apiFetch(
    `${API_BASE}/multimedia/assets/${encodeURIComponent(assetId)}/reconciliation-links`,
  );
  if (resp.status === 404) throw new Error("multimedia_asset_reconciliation_unavailable");
  if (resp.status === 503) throw new Error("multimedia_reconciliation_runtime_unavailable");
  if (!resp.ok) throw new Error(`GET /multimedia/assets/{id}/reconciliation-links: HTTP ${resp.status}`);
  return (await resp.json()) as AssetReconciliationLinks;
}

export async function executeChapterTtsReconciliation(
  executionId: string,
  action: TtsReconciliationAction,
): Promise<ChapterTtsReconciliation> {
  const resp = await apiFetch(
    `${API_BASE}/multimedia/executions/${encodeURIComponent(executionId)}/tts-reconciliation/actions/${action}`,
    { method: "POST" },
  );
  if (resp.status === 404) throw new Error("multimedia_execution_unavailable");
  if (resp.status === 409) throw new Error("multimedia_reconciliation_action_conflict");
  if (resp.status === 503) throw new Error("multimedia_reconciliation_runtime_unavailable");
  if (!resp.ok) throw new Error(`POST /multimedia/executions/{id}/tts-reconciliation/actions/{action}: HTTP ${resp.status}`);
  return (await resp.json()) as ChapterTtsReconciliation;
}

export async function getNarrationRunReconciliation(
  runId: string,
): Promise<NarrationRunReconciliation> {
  const resp = await apiFetch(
    `${API_BASE}/multimedia/narration-runs/${encodeURIComponent(runId)}/reconciliation`,
  );
  if (resp.status === 404) throw new Error("multimedia_narration_run_unavailable");
  if (resp.status === 503) throw new Error("multimedia_reconciliation_runtime_unavailable");
  if (!resp.ok) throw new Error(`GET /multimedia/narration-runs/{id}/reconciliation: HTTP ${resp.status}`);
  return (await resp.json()) as NarrationRunReconciliation;
}
