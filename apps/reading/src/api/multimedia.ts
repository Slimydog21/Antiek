import { API_BASE, apiFetch } from "../lib/api";

export type MultimediaMode = "video" | "audio" | "hybrid";
export type MultimediaRoutePolicy = "cheapest" | "balanced" | "highest_quality";
export type MultimediaKind = "information_video" | "documentary_video" | "audio_experience";
export type MultimediaJobKind = "render" | "steering" | "hardening" | "provider_execution";
export type MultimediaJobStatus = "queued" | "running" | "succeeded" | "failed" | "canceled" | "partial";
export type MultimediaExecutionMode = "dry_run" | "live_requested" | "live";
export type MultimediaProviderReadinessStatus =
  | "no_provider_jobs"
  | "dry_run_available"
  | "dry_run_completed"
  | "manual_attach_ready"
  | "artifact_attached"
  | "artifact_rejected";

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

export interface ProviderExecutionWorkerRequest {
  dry_run?: boolean;
  job_id?: string | null;
}

export interface ProviderArtifactAttachmentRequest {
  job_id: string;
  artifact_uri: string;
  artifact_checksum: string;
  artifact_media_type: string;
}

export interface MultimediaProviderReadinessSummary {
  status: MultimediaProviderReadinessStatus;
  label: string;
  source_job_id: string | null;
  artifact_media_type: string | null;
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
  provider_readiness: MultimediaProviderReadinessSummary;
}

export interface MultimediaAssetList {
  assets: MultimediaAssetSummary[];
  count: number;
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
  hardening_report: {
    ship_status: "pass" | "blocked" | "manual_review";
    failed_gate_ids: string[];
    manual_gate_ids: string[];
  } | null;
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
  execution_mode: MultimediaExecutionMode;
  provider_family: string | null;
  artifact_uri: string | null;
  artifact_checksum: string | null;
  artifact_media_type: string | null;
  progress_percent: number;
  message: string;
  error_code: string | null;
  retryable: boolean | null;
}

export interface MultimediaJobList {
  jobs: MultimediaJobRecord[];
  count: number;
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

export async function runMultimediaProviderWorker(
  assetId: string,
  request: ProviderExecutionWorkerRequest = { dry_run: true },
): Promise<MultimediaAssetRecord> {
  const resp = await apiFetch(`${API_BASE}/multimedia/assets/${encodeURIComponent(assetId)}/run-provider-worker`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(request),
  });
  if (resp.status === 404) throw new Error("multimedia_asset_not_found");
  if (!resp.ok) throw new Error(`POST /multimedia/assets/{id}/run-provider-worker: HTTP ${resp.status}`);
  return (await resp.json()) as MultimediaAssetRecord;
}

export async function attachMultimediaProviderArtifact(
  assetId: string,
  request: ProviderArtifactAttachmentRequest,
): Promise<MultimediaAssetRecord> {
  const resp = await apiFetch(`${API_BASE}/multimedia/assets/${encodeURIComponent(assetId)}/attach-provider-artifact`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(request),
  });
  if (resp.status === 404) throw new Error("multimedia_asset_not_found");
  if (!resp.ok) throw new Error(`POST /multimedia/assets/{id}/attach-provider-artifact: HTTP ${resp.status}`);
  return (await resp.json()) as MultimediaAssetRecord;
}
