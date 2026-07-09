import { API_BASE, apiFetch } from "../lib/api";

export type MultimediaMode = "video" | "audio" | "hybrid";
export type MultimediaRoutePolicy = "cheapest" | "balanced" | "highest_quality";
export type MultimediaKind = "information_video" | "documentary_video" | "audio_experience";
export type MultimediaJobKind = "render" | "steering" | "hardening" | "provider_execution" | "export_gate";
export type MultimediaJobStatus = "queued" | "running" | "succeeded" | "failed" | "canceled" | "partial";
export type MultimediaPublicExportNextAction =
  | "attach_provider_artifacts"
  | "run_hardening"
  | "manual_publication_review"
  | "stage_export_plan"
  | "record_publish_blocker"
  | "publisher_implementation";

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

export interface MultimediaPublicExportReviewRequest {
  decision: "approved" | "rejected";
  gate_ids: string[];
  operator_acknowledged_public_distribution: boolean;
  notes?: string | null;
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
  public_export_gate?: MultimediaPublicExportGate | null;
  public_export_review?: MultimediaPublicExportReview | null;
  public_export_plan?: MultimediaPublicExportPlan | null;
}

export interface MultimediaJobList {
  jobs: MultimediaJobRecord[];
  count: number;
}

export interface MultimediaPublicExportGate {
  status: "blocked" | "manual_review" | "ready";
  public_export_enabled: boolean;
  hardening_status: string | null;
  attached_file_ids: string[];
  required_gate_ids: string[];
  reason: string;
}

export interface MultimediaPublicExportReview {
  decision: "approved" | "rejected";
  gate_ids: string[];
  attached_file_ids: string[];
  operator_acknowledged_public_distribution: boolean;
  notes: string | null;
}

export interface MultimediaPublicExportPlan {
  export_id: string;
  attached_file_ids: string[];
  review_gate_ids: string[];
  storage_backend: "pending";
  public_url: null;
  publish_enabled: boolean;
}

export interface MultimediaPublicExportStatus {
  asset_id: string;
  revision_id: string;
  gate_status: string | null;
  review_decision: string | null;
  export_id: string | null;
  publish_blocked: boolean;
  publish_denial_code: string | null;
  public_url: null;
  latest_job_status: MultimediaJobStatus | null;
  latest_error_code: string | null;
  next_required_action: MultimediaPublicExportNextAction;
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

export async function getMultimediaPublicExportStatus(assetId: string): Promise<MultimediaPublicExportStatus> {
  const resp = await apiFetch(`${API_BASE}/multimedia/assets/${encodeURIComponent(assetId)}/public-export-status`);
  if (resp.status === 404) throw new Error("multimedia_asset_not_found");
  if (!resp.ok) throw new Error(`GET /multimedia/assets/{id}/public-export-status: HTTP ${resp.status}`);
  return (await resp.json()) as MultimediaPublicExportStatus;
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

export async function evaluateMultimediaPublicExportGate(assetId: string): Promise<MultimediaAssetRecord> {
  const resp = await apiFetch(
    `${API_BASE}/multimedia/assets/${encodeURIComponent(assetId)}/evaluate-public-export-gate`,
    { method: "POST" },
  );
  if (resp.status === 404) throw new Error("multimedia_asset_not_found");
  if (!resp.ok) throw new Error(`POST /multimedia/assets/{id}/evaluate-public-export-gate: HTTP ${resp.status}`);
  return (await resp.json()) as MultimediaAssetRecord;
}

export async function recordMultimediaPublicExportReview(
  assetId: string,
  request: MultimediaPublicExportReviewRequest,
): Promise<MultimediaAssetRecord> {
  const resp = await apiFetch(`${API_BASE}/multimedia/assets/${encodeURIComponent(assetId)}/public-export-review`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(request),
  });
  if (resp.status === 404) throw new Error("multimedia_asset_not_found");
  if (!resp.ok) throw new Error(`POST /multimedia/assets/{id}/public-export-review: HTTP ${resp.status}`);
  return (await resp.json()) as MultimediaAssetRecord;
}

export async function planMultimediaPublicExport(assetId: string): Promise<MultimediaAssetRecord> {
  const resp = await apiFetch(`${API_BASE}/multimedia/assets/${encodeURIComponent(assetId)}/plan-public-export`, {
    method: "POST",
  });
  if (resp.status === 404) throw new Error("multimedia_asset_not_found");
  if (!resp.ok) throw new Error(`POST /multimedia/assets/{id}/plan-public-export: HTTP ${resp.status}`);
  return (await resp.json()) as MultimediaAssetRecord;
}
