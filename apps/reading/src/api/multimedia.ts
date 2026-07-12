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
  knowledge_finalized?: boolean;
  twin_document_id?: string | null;
}

export interface MultimediaKnowledgeLink {
  schema_version: "antiek.multimedia-knowledge-link.v1";
  asset_id: string;
  revision_id: string;
  source_document_id: string;
  source_event_id: string;
  graph_node_id: string;
  twin_document_id: string;
  source_html_sha256: string;
  twin_html_sha256: string;
  insight_node_ids: string[];
  question_node_ids: string[];
}

export type MultimediaDistillationStateName =
  | "not_started"
  | "in_progress"
  | "completed"
  | "integrity_conflict";

export interface MultimediaKnowledgeFinalizationStatus {
  asset_id: string;
  revision_id: string;
  asset_status: string;
  distillation: {
    state: MultimediaDistillationStateName;
    recovery_eligible: boolean;
    recovery_stale_seconds: number;
    claim_started_at: string | null;
  };
  knowledge_link: MultimediaKnowledgeLink | null;
}

export interface MultimediaKnowledgeFinalizationResponse {
  asset: MultimediaAssetRecord;
  knowledge_link: MultimediaKnowledgeLink;
}

export interface MultimediaTwinDocument {
  asset_id: string;
  revision_id: string;
  source_document_id: string;
  twin_document_id: string;
  title: string;
  html: string;
  html_sha256: string;
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
  knowledge_link?: MultimediaKnowledgeLink | null;
  knowledge_finalization_revision_id?: string | null;
}

export interface MultimediaSourceCitationWire {
  chunk_id: string;
  document_id: string;
  locator: string | null;
  quote_sha256: string | null;
}

export interface MultimediaScriptLineWire {
  line_id: string;
  sequence: number;
  text: string;
  kind: "factual" | "transition" | "narration" | "opinion" | "instruction";
  citations: MultimediaSourceCitationWire[];
  unsourced_reason: string | null;
}

export interface MultimediaPlanWire {
  request: {
    topic: string;
    target_minutes: number;
    mode: MultimediaMode;
    route_policy: MultimediaRoutePolicy;
  };
  suggestions: Array<{
    arc_id: string;
    title: string;
    teaches: string;
    evidence: MultimediaSourceCitationWire[];
    tradeoff: string;
  }>;
  chosen_arc_ids: string[];
  chapters: Array<{
    chapter_id: string;
    title: string;
    minutes: number;
    purpose: string;
    arc_id: string;
    source_chunk_ids: string[];
    cuts: string[];
  }>;
  script_lines: MultimediaScriptLineWire[];
  scenes: Array<{
    scene_id: string;
    chapter_id: string;
    visual_intent: string;
    information_purpose: string;
    narration_line_ids: string[];
    source_chunk_ids: string[];
  }>;
  omissions: string[];
  unsourced_line_ids: string[];
  duration_tolerance_minutes: number;
}

export interface MultimediaPlayback {
  asset_id: string;
  revision_id: string;
  duration_seconds: number;
  video_sha256: string;
  audio_sha256: string;
  video_size_bytes: number;
  audio_size_bytes: number;
  width_px: number;
  height_px: number;
  chapter_ids: string[];
  video_url: string;
  audio_url: string;
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

export async function getMultimediaPlayback(
  assetId: string,
  revisionId: string,
): Promise<MultimediaPlayback> {
  const asset = encodeURIComponent(assetId);
  const revision = encodeURIComponent(revisionId);
  const resp = await apiFetch(
    `${API_BASE}/multimedia/assets/${asset}/playback?revision_id=${revision}`,
  );
  if (resp.status === 404) throw new Error("multimedia_playback_unavailable");
  if (resp.status === 409) throw new Error("multimedia_playback_stale_revision");
  if (resp.status === 503) throw new Error("multimedia_playback_runtime_unavailable");
  if (!resp.ok) throw new Error(`GET /multimedia/assets/{id}/playback: HTTP ${resp.status}`);
  const playback = (await resp.json()) as MultimediaPlayback;
  const expectedPath = `/multimedia/assets/${asset}/playback/${revision}`;
  if (
    playback.asset_id !== assetId ||
    playback.revision_id !== revisionId ||
    playback.video_url !== `${expectedPath}/video` ||
    playback.audio_url !== `${expectedPath}/audio`
  ) {
    throw new Error("multimedia_playback_identity_conflict");
  }
  return {
    ...playback,
    video_url: `${API_BASE}${playback.video_url}`,
    audio_url: `${API_BASE}${playback.audio_url}`,
  };
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

function knowledgeError(operation: string, status: number): Error {
  if (status === 404) return new Error("multimedia_knowledge_unavailable");
  if (status === 409) return new Error("multimedia_knowledge_conflict");
  if (status === 503) return new Error("multimedia_knowledge_runtime_unavailable");
  return new Error(`${operation}: HTTP ${status}`);
}

export async function getMultimediaKnowledgeFinalization(
  assetId: string,
): Promise<MultimediaKnowledgeFinalizationStatus> {
  const resp = await apiFetch(
    `${API_BASE}/multimedia/assets/${encodeURIComponent(assetId)}/knowledge-finalization`,
  );
  if (!resp.ok) throw knowledgeError("GET /multimedia/assets/{id}/knowledge-finalization", resp.status);
  return (await resp.json()) as MultimediaKnowledgeFinalizationStatus;
}

export async function getMultimediaKnowledgeTwin(
  assetId: string,
): Promise<MultimediaTwinDocument> {
  const resp = await apiFetch(
    `${API_BASE}/multimedia/assets/${encodeURIComponent(assetId)}/knowledge-twin`,
  );
  if (resp.status === 404) throw new Error("multimedia_twin_unavailable");
  if (resp.status === 409) throw new Error("multimedia_twin_integrity_conflict");
  if (resp.status === 503) throw new Error("multimedia_knowledge_runtime_unavailable");
  if (!resp.ok) throw new Error(`GET /multimedia/assets/{id}/knowledge-twin: HTTP ${resp.status}`);
  return (await resp.json()) as MultimediaTwinDocument;
}

export async function finalizeMultimediaKnowledge(
  assetId: string,
  expectedRevisionId: string,
): Promise<MultimediaKnowledgeFinalizationResponse> {
  const resp = await apiFetch(
    `${API_BASE}/multimedia/assets/${encodeURIComponent(assetId)}/finalize-knowledge`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        expected_revision_id: expectedRevisionId,
        operator_acknowledged_model_use: true,
      }),
    },
  );
  if (!resp.ok) throw knowledgeError("POST /multimedia/assets/{id}/finalize-knowledge", resp.status);
  return (await resp.json()) as MultimediaKnowledgeFinalizationResponse;
}

export async function recoverMultimediaKnowledgeFinalization(
  assetId: string,
  expectedRevisionId: string,
): Promise<MultimediaKnowledgeFinalizationResponse> {
  const resp = await apiFetch(
    `${API_BASE}/multimedia/assets/${encodeURIComponent(assetId)}/recover-knowledge-finalization`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        expected_revision_id: expectedRevisionId,
        operator_acknowledged_model_use: true,
        operator_acknowledged_duplicate_model_risk: true,
      }),
    },
  );
  if (!resp.ok) throw knowledgeError("POST /multimedia/assets/{id}/recover-knowledge-finalization", resp.status);
  return (await resp.json()) as MultimediaKnowledgeFinalizationResponse;
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
