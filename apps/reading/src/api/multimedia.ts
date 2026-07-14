import { API_BASE, apiFetch } from "../lib/api";

export type MultimediaMode = "video" | "audio" | "hybrid";
export type MultimediaRoutePolicy = "cheapest" | "balanced" | "highest_quality";
export type MultimediaDepth = "overview" | "intermediate" | "deep";
export type MultimediaKind = "information_video" | "documentary_video" | "audio_experience";
export type MultimediaJobKind = "render" | "steering" | "hardening" | "provider_execution";
export type MultimediaJobStatus = "queued" | "running" | "succeeded" | "failed" | "canceled" | "partial";

export interface CreateMultimediaDraftRequest {
  topic: string;
  target_minutes: number;
  mode: MultimediaMode;
  route_policy: MultimediaRoutePolicy;
  source_scope?: string | null;
  sources?: string[];
  must_cover?: string[];
  avoid?: string[];
  audience?: string;
  style?: string | null;
  depth?: MultimediaDepth;
  selected_arc_ids?: string[];
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
  production_ready?: boolean;
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

export interface MultimediaEvidenceCandidate {
  chunk_id: string;
  document_id: string;
  document_title: string;
  section_path: string | null;
  excerpt: string;
  text_sha256: string;
  similarity: number;
}

export interface MultimediaEvidenceSearchResult {
  asset_id: string;
  revision_id: string;
  query: string;
  candidates: MultimediaEvidenceCandidate[];
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
    parent_asset_id?: string | null;
    parent_revision_id?: string | null;
    steering_event_id?: string | null;
    manifest: unknown;
  };
  plan: unknown;
  mode: MultimediaMode;
  derived_from_revision_id?: string | null;
  style: string | null;
  hardening_report: MultimediaHardeningReport | null;
  latest_steering_intent: unknown | null;
  jobs: MultimediaJobRecord[];
  knowledge_link?: MultimediaKnowledgeLink | null;
  knowledge_finalization_revision_id?: string | null;
  production_link?: MultimediaProductionLink | null;
  audio_production_link?: MultimediaAudioProductionLink | null;
}

export interface MultimediaSteeringRequest {
  expected_parent_revision_id: string;
  prompt: string;
  raw_voice_transcript?: string | null;
  corrected_voice_transcript?: string | null;
}

export interface MultimediaSteeringOperation {
  operation_id: string;
  kind: string;
  target_kind: string;
  target_id: string;
  value: string | null;
  reason: string;
}

export interface MultimediaSteeringIntent {
  steering_event_id: string;
  prompt: string;
  status: "ready" | "needs_clarification";
  operations: MultimediaSteeringOperation[];
  clarifications: string[];
  transcript: {
    transcript_id: string;
    raw_text: string;
    corrected_text: string | null;
    confidence: number | null;
  } | null;
}

export interface MultimediaSteeringPreviewClarification {
  status: "needs_clarification";
  asset_id: string;
  parent_revision_id: string;
  intent: MultimediaSteeringIntent;
}

export interface MultimediaSteeringPreviewReady {
  status: "ready";
  asset_id: string;
  parent_revision_id: string;
  proposed_revision_id: string;
  route_policy: MultimediaRoutePolicy;
  intent: MultimediaSteeringIntent;
  operations: MultimediaSteeringOperation[];
  affected_segment_ids: string[];
  segment_reuse: Array<{
    segment_id: string;
    reused: boolean;
    reason: string;
    file_ids: string[];
    file_sha256s: string[];
  }>;
  changes: Array<{
    operation_id: string;
    target_id: string;
    changed_segment_ids: string[];
    estimated_cost_delta_usd: number;
    explanation: string;
  }>;
  estimated_cost_delta_usd: number;
  preview_token: string;
  expires_at_epoch_seconds: number;
}

export type MultimediaSteeringPreview =
  | MultimediaSteeringPreviewClarification
  | MultimediaSteeringPreviewReady;

export interface MultimediaProductionLink {
  schema_version: "antiek.multimedia-production-link.v1";
  owner_identity_digest: string;
  asset_id: string;
  revision_id: string;
  receipt_sha256: string;
  video_sha256: string;
  audio_sha256: string;
  duration_seconds: number;
  width_px: number;
  height_px: number;
  chapter_ids: string[];
}

export interface MultimediaAudioProductionLink {
  schema_version: "antiek.multimedia-audio-production-link.v1";
  owner_identity_digest: string;
  asset_id: string;
  revision_id: string;
  receipt_sha256: string;
  audio_sha256: string;
  audio_size_bytes: number;
  duration_seconds: number;
  chapter_ids: string[];
  retention_marker_count: number;
  learned_claim_count: number;
  source_count: number;
}

export interface MultimediaSourceCitationWire {
  chunk_id: string;
  document_id: string;
  locator: string | null;
  quote_sha256: string | null;
}

export interface MultimediaEvidenceSpanWire {
  chunk_id: string;
  document_id: string;
  authority_kind: "canonical_graph" | "operator_excerpt";
  chunk_sha256: string;
  start_utf8_byte: number;
  end_utf8_byte: number;
  span_sha256: string;
  exact_text: string;
}

export interface MultimediaEvidenceDerivationWire {
  method: "verbatim_span";
  recipe_version: "antiek.evidence-narration.v1";
  spans: MultimediaEvidenceSpanWire[];
  output_sha256: string;
}

export interface MultimediaScriptLineWire {
  line_id: string;
  sequence: number;
  text: string;
  kind: "factual" | "transition" | "narration" | "opinion" | "instruction";
  citations: MultimediaSourceCitationWire[];
  evidence_derivation?: MultimediaEvidenceDerivationWire | null;
  unsourced_reason: string | null;
}

export interface MultimediaPlanWire {
  grounding_contract?: "citation_presence_v1" | "exact_extract_v2" | "audible_transform_v1";
  request: {
    topic: string;
    target_minutes: number;
    mode: MultimediaMode;
    route_policy: MultimediaRoutePolicy;
    depth?: MultimediaDepth;
    source_scope?: string | null;
    selected_arc_ids?: string[];
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
  receipt_sha256: string;
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

export interface MultimediaLocalCapability {
  available: boolean;
  reason: "ready" | "unavailable";
  route_policy: "cheapest";
  cost_usd: 0;
}

export type MultimediaLocalStatus =
  | "preparing"
  | "preparation_unknown"
  | "review_required"
  | "ready_to_produce"
  | "production_unknown"
  | "registered";

export interface MultimediaLocalPreparedSet {
  set_id: string;
  asset_id: string;
  revision_id: string;
  status: MultimediaLocalStatus;
  recoverable: boolean;
  cost_usd: 0;
  playback_ready: boolean;
  chapters: Array<{
    chapter_id: string;
    title: string;
    narration_ready: boolean;
    card_id: string | null;
    card_ready: boolean;
    attested: boolean;
    source_count: number;
  }>;
}

export type MultimediaLocalAudibleStatus =
  | "preparing"
  | "preparation_unknown"
  | "ready_to_produce"
  | "production_unknown"
  | "registered";

export interface MultimediaLocalAudiblePreparedSet {
  set_id: string;
  asset_id: string;
  revision_id: string;
  status: MultimediaLocalAudibleStatus;
  recoverable: boolean;
  cost_usd: 0;
  playback_ready: boolean;
  total_duration_seconds: number;
  chapters: Array<{
    chapter_id: string;
    title: string;
    span_count: number;
    ready_span_count: number;
    duration_seconds: number;
    source_count: number;
    remember_ready: boolean;
    recap_ready: boolean;
    learned_claim_count: number;
  }>;
}

export interface MultimediaLocalAudiblePlayback {
  asset_id: string;
  revision_id: string;
  receipt_sha256: string;
  audio_sha256: string;
  audio_size_bytes: number;
  duration_seconds: number;
  chapter_ids: string[];
  chapters: Array<{
    chapter_id: string;
    title: string;
    sequence: number;
    start_offset_seconds: number;
    end_offset_seconds: number;
  }>;
  retention_marker_count: number;
  learned_claim_count: number;
  source_count: number;
  learned_claims: Array<{
    chapter_id: string;
    claim_text: string;
    source_count: number;
    follow_up_prompt: string;
  }>;
  audio_url: string;
}

export type MultimediaPaidAudioPlayback = MultimediaLocalAudiblePlayback;

function hasValidAudioTimeline(result: MultimediaLocalAudiblePlayback): boolean {
  if (!Array.isArray(result.chapters) || result.chapters.length !== result.chapter_ids.length) return false;
  let expectedStart = 0;
  const ids = new Set<string>();
  const sequences = new Set<number>();
  for (let index = 0; index < result.chapters.length; index += 1) {
    const chapter = result.chapters[index];
    if (
      !chapter || typeof chapter.chapter_id !== "string" || !chapter.chapter_id ||
      typeof chapter.title !== "string" || !chapter.title.trim() ||
      !Number.isSafeInteger(chapter.sequence) || chapter.sequence !== index ||
      ids.has(chapter.chapter_id) || sequences.has(chapter.sequence) ||
      chapter.chapter_id !== result.chapter_ids[index] ||
      !Number.isFinite(chapter.start_offset_seconds) || !Number.isFinite(chapter.end_offset_seconds) ||
      chapter.start_offset_seconds < 0 || chapter.end_offset_seconds <= chapter.start_offset_seconds ||
      Math.abs(chapter.start_offset_seconds - expectedStart) > 0.001
    ) return false;
    ids.add(chapter.chapter_id);
    sequences.add(chapter.sequence);
    expectedStart = chapter.end_offset_seconds;
  }
  return Math.abs(expectedStart - result.duration_seconds) <= 0.001;
}

export interface MultimediaNarrationAuthorization {
  chapter_id: string;
  child_revision_id: string;
  request_body_digest: string;
  authorization: {
    version: number;
    authorization_id: string;
    request_id: string;
    operator_id: string;
    asset_id: string;
    revision_id: string;
    provider: string;
    route_policy: string;
    model: string;
    endpoint_capability: string;
    catalog_version: string;
    catalog_digest: string;
    quote_id: string;
    quote_expires_at: string;
    recovery_authority_id: string;
    recovery_verification_key_digest: string;
    approved_ceiling_microdollars: number;
    request_body_digest: string;
    issued_at: string;
    expires_at: string;
    signature: string;
  };
}

export interface MultimediaReviewedVisualSet {
  set_id: string;
  asset_id: string;
  revision_id: string;
  chapter_ids: string[];
  scene_ids: string[];
  candidate_ids: string[];
  selection_digest: string;
  created_at: string;
}

export interface MultimediaVisualAuthorization {
  chapter_id: string;
  scene_id: string;
  width: number;
  height: number;
  seed: number;
  request_body_digest: string;
  quote: {
    quote_id: string;
    model: string;
    ceiling_microdollars: number;
    expires_at: string;
  };
  authorization: MultimediaNarrationAuthorization["authorization"];
}

export interface MultimediaVisualGeneration {
  execution_id: string;
  authorization_id: string;
  provider_job_id: string | null;
  status: string;
  candidate_count: number;
}

export interface MultimediaVisualCandidate {
  candidate_id: string;
  artifact_receipt_id: string;
  media_type: string;
  byte_count: number;
}

export interface MultimediaVisualCandidateSet {
  execution_id: string;
  candidates: MultimediaVisualCandidate[];
}

export interface MultimediaVisualAttestation {
  artifact_receipt_id: string;
  reviewer_id: string;
  attested_at: string;
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

export async function searchMultimediaEvidence(
  assetId: string,
  revisionId: string,
  limit = 12,
): Promise<MultimediaEvidenceSearchResult> {
  const resp = await apiFetch(`${API_BASE}/multimedia/assets/${encodeURIComponent(assetId)}/evidence-search`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ expected_revision_id: revisionId, limit }),
  });
  if (resp.status === 409) throw new Error("multimedia_evidence_conflict");
  if (resp.status === 503) throw new Error("multimedia_evidence_runtime_unavailable");
  if (!resp.ok) throw new Error(`POST multimedia evidence-search: HTTP ${resp.status}`);
  const result = (await resp.json()) as MultimediaEvidenceSearchResult;
  if (
    result.asset_id !== assetId ||
    result.revision_id !== revisionId ||
    typeof result.query !== "string" ||
    !result.query ||
    !Array.isArray(result.candidates) ||
    result.candidates.length > 20 ||
    result.candidates.some((candidate) => !validEvidenceCandidate(candidate)) ||
    new Set(result.candidates.map((candidate) => candidate.chunk_id)).size !== result.candidates.length
  ) {
    throw new Error("multimedia_evidence_identity_conflict");
  }
  return result;
}

export async function createGroundedMultimediaDraft(
  assetId: string,
  revisionId: string,
  candidates: MultimediaEvidenceCandidate[],
): Promise<MultimediaAssetRecord> {
  const resp = await apiFetch(`${API_BASE}/multimedia/assets/${encodeURIComponent(assetId)}/grounded-drafts`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      expected_parent_revision_id: revisionId,
      selections: candidates.map(({ chunk_id, text_sha256 }) => ({ chunk_id, text_sha256 })),
    }),
  });
  if (resp.status === 409) throw new Error("multimedia_evidence_conflict");
  if (resp.status === 503) throw new Error("multimedia_evidence_runtime_unavailable");
  if (!resp.ok) throw new Error(`POST multimedia grounded-drafts: HTTP ${resp.status}`);
  const result = (await resp.json()) as MultimediaAssetRecord;
  if (
    result.asset.parent_asset_id !== assetId ||
    result.derived_from_revision_id !== revisionId ||
    result.asset.asset_id === assetId
  ) {
    throw new Error("multimedia_evidence_identity_conflict");
  }
  return result;
}

function validEvidenceCandidate(candidate: MultimediaEvidenceCandidate): boolean {
  return Boolean(
    candidate &&
    typeof candidate.chunk_id === "string" && candidate.chunk_id &&
    typeof candidate.document_id === "string" && candidate.document_id &&
    typeof candidate.document_title === "string" && candidate.document_title &&
    (candidate.section_path === null || typeof candidate.section_path === "string") &&
    typeof candidate.excerpt === "string" && candidate.excerpt &&
    typeof candidate.text_sha256 === "string" && /^[0-9a-f]{64}$/.test(candidate.text_sha256) &&
    typeof candidate.similarity === "number" && Number.isFinite(candidate.similarity) &&
    candidate.similarity >= -1 && candidate.similarity <= 1
  );
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

export async function registerMultimediaProduction(
  assetId: string,
  expectedRevisionId: string,
): Promise<MultimediaAssetRecord> {
  const resp = await apiFetch(
    `${API_BASE}/multimedia/assets/${encodeURIComponent(assetId)}/production-registration`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ expected_revision_id: expectedRevisionId }),
    },
  );
  if (resp.status === 404) throw new Error("multimedia_production_unavailable");
  if (resp.status === 409) throw new Error("multimedia_production_conflict");
  if (resp.status === 503) throw new Error("multimedia_playback_runtime_unavailable");
  if (!resp.ok) throw new Error(`POST /multimedia/assets/{id}/production-registration: HTTP ${resp.status}`);
  const record = (await resp.json()) as MultimediaAssetRecord;
  if (
    record.asset.asset_id !== assetId ||
    record.asset.revision_id !== expectedRevisionId ||
    record.production_link?.asset_id !== assetId ||
    record.production_link.revision_id !== expectedRevisionId
  ) {
    throw new Error("multimedia_production_identity_conflict");
  }
  return record;
}

export async function getMultimediaLocalCapability(): Promise<MultimediaLocalCapability> {
  const resp = await apiFetch(`${API_BASE}/multimedia/local/capability`);
  if (!resp.ok) throw new Error(`GET /multimedia/local/capability: HTTP ${resp.status}`);
  const result = (await resp.json()) as MultimediaLocalCapability;
  if (
    typeof result.available !== "boolean" ||
    result.reason !== (result.available ? "ready" : "unavailable") ||
    result.route_policy !== "cheapest" ||
    result.cost_usd !== 0
  ) {
    throw new Error("multimedia_local_capability_conflict");
  }
  return result;
}

export async function prepareMultimediaLocal(
  assetId: string,
  revisionId: string,
): Promise<MultimediaLocalPreparedSet> {
  return localCommand(assetId, revisionId, "/prepare", undefined);
}

export async function inspectMultimediaLocal(
  assetId: string,
  revisionId: string,
  setId: string,
): Promise<MultimediaLocalPreparedSet> {
  const resp = await apiFetch(
    `${API_BASE}/multimedia/assets/${encodeURIComponent(assetId)}/local/${encodeURIComponent(revisionId)}/${encodeURIComponent(setId)}`,
  );
  return localResponse(resp, assetId, revisionId, setId, "GET local prepared set");
}

export async function attestMultimediaLocalCard(
  assetId: string,
  revisionId: string,
  setId: string,
  cardId: string,
): Promise<MultimediaLocalPreparedSet> {
  return localCommand(
    assetId,
    revisionId,
    `/cards/${encodeURIComponent(cardId)}/attest`,
    setId,
  );
}

export async function produceMultimediaLocal(
  assetId: string,
  revisionId: string,
  setId: string,
): Promise<MultimediaLocalPreparedSet> {
  return localCommand(assetId, revisionId, "/produce", setId);
}

export async function recoverMultimediaLocal(
  assetId: string,
  revisionId: string,
  setId: string,
): Promise<MultimediaLocalPreparedSet> {
  return localCommand(assetId, revisionId, "/recover", setId);
}

export function multimediaLocalCardPreviewUrl(
  assetId: string,
  revisionId: string,
  setId: string,
  cardId: string,
): string {
  return `${API_BASE}/multimedia/assets/${encodeURIComponent(assetId)}/local/${encodeURIComponent(revisionId)}/${encodeURIComponent(setId)}/cards/${encodeURIComponent(cardId)}/content`;
}

async function localCommand(
  assetId: string,
  revisionId: string,
  suffix: string,
  setId: string | undefined,
): Promise<MultimediaLocalPreparedSet> {
  const resp = await apiFetch(
    `${API_BASE}/multimedia/assets/${encodeURIComponent(assetId)}/local${suffix}`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        expected_revision_id: revisionId,
        ...(setId === undefined ? {} : { set_id: setId }),
      }),
    },
  );
  return localResponse(resp, assetId, revisionId, setId, `POST local${suffix}`);
}

async function localResponse(
  resp: Response,
  assetId: string,
  revisionId: string,
  setId: string | undefined,
  operation: string,
): Promise<MultimediaLocalPreparedSet> {
  if (resp.status === 404) throw new Error("multimedia_local_unavailable");
  if (resp.status === 409) throw new Error("multimedia_local_conflict");
  if (resp.status === 503) throw new Error("multimedia_local_runtime_unavailable");
  if (!resp.ok) throw new Error(`${operation}: HTTP ${resp.status}`);
  const result = (await resp.json()) as MultimediaLocalPreparedSet;
  const statuses: MultimediaLocalStatus[] = [
    "preparing", "preparation_unknown", "review_required",
    "ready_to_produce", "production_unknown", "registered",
  ];
  const chapterIds = result.chapters?.map((chapter) => chapter.chapter_id) ?? [];
  const cardIds = result.chapters?.flatMap((chapter) => chapter.card_id ? [chapter.card_id] : []) ?? [];
  const allAttested = result.chapters?.length > 0 && result.chapters.every((chapter) => chapter.attested);
  const recoverable = ["preparing", "preparation_unknown", "production_unknown"].includes(result.status);
  if (
    result.asset_id !== assetId ||
    result.revision_id !== revisionId ||
    (setId !== undefined && result.set_id !== setId) ||
    !/^mmlocalset_[0-9a-f]{64}$/.test(result.set_id) ||
    !statuses.includes(result.status) ||
    result.cost_usd !== 0 ||
    result.recoverable !== recoverable ||
    result.playback_ready !== (result.status === "registered") ||
    !Array.isArray(result.chapters) ||
    new Set(chapterIds).size !== chapterIds.length ||
    new Set(cardIds).size !== cardIds.length ||
    result.chapters.some(
      (chapter) =>
        !chapter.chapter_id || !chapter.title ||
        typeof chapter.narration_ready !== "boolean" ||
        typeof chapter.card_ready !== "boolean" ||
        typeof chapter.attested !== "boolean" ||
        !Number.isSafeInteger(chapter.source_count) || chapter.source_count < 0,
    ) ||
    (["ready_to_produce", "registered"].includes(result.status) && !allAttested)
  ) {
    throw new Error("multimedia_local_identity_conflict");
  }
  return result;
}

export async function getMultimediaLocalAudibleCapability(): Promise<MultimediaLocalCapability> {
  const resp = await apiFetch(`${API_BASE}/multimedia/local-audible/capability`);
  if (!resp.ok) throw new Error(`GET /multimedia/local-audible/capability: HTTP ${resp.status}`);
  const result = (await resp.json()) as MultimediaLocalCapability;
  if (
    typeof result.available !== "boolean" ||
    result.reason !== (result.available ? "ready" : "unavailable") ||
    result.route_policy !== "cheapest" ||
    result.cost_usd !== 0
  ) {
    throw new Error("multimedia_local_audible_capability_conflict");
  }
  return result;
}

export async function prepareMultimediaLocalAudible(
  assetId: string,
  revisionId: string,
): Promise<MultimediaLocalAudiblePreparedSet> {
  return localAudibleCommand(assetId, revisionId, "/prepare");
}

export async function inspectMultimediaLocalAudible(
  assetId: string,
  revisionId: string,
  setId: string,
): Promise<MultimediaLocalAudiblePreparedSet> {
  const resp = await apiFetch(
    `${API_BASE}/multimedia/assets/${encodeURIComponent(assetId)}/local-audible/${encodeURIComponent(revisionId)}/${encodeURIComponent(setId)}`,
  );
  return localAudibleResponse(resp, assetId, revisionId, setId, "GET local audible set");
}

export async function produceMultimediaLocalAudible(
  assetId: string,
  revisionId: string,
  setId: string,
): Promise<MultimediaLocalAudiblePreparedSet> {
  return localAudibleCommand(assetId, revisionId, "/produce", setId);
}

export async function recoverMultimediaLocalAudible(
  assetId: string,
  revisionId: string,
  setId: string,
): Promise<MultimediaLocalAudiblePreparedSet> {
  return localAudibleCommand(assetId, revisionId, "/recover", setId);
}

export async function getMultimediaLocalAudiblePlayback(
  assetId: string,
  revisionId: string,
): Promise<MultimediaLocalAudiblePlayback> {
  const params = new URLSearchParams({ revision_id: revisionId });
  const resp = await apiFetch(
    `${API_BASE}/multimedia/assets/${encodeURIComponent(assetId)}/local-audible/playback?${params}`,
  );
  if (resp.status === 404) throw new Error("multimedia_local_audible_playback_unavailable");
  if (resp.status === 409) throw new Error("multimedia_local_audible_playback_conflict");
  if (resp.status === 503) throw new Error("multimedia_local_audible_runtime_unavailable");
  if (!resp.ok) throw new Error(`GET local audible playback: HTTP ${resp.status}`);
  const result = (await resp.json()) as MultimediaLocalAudiblePlayback;
  const expectedPath = `/multimedia/assets/${encodeURIComponent(assetId)}/local-audible/playback/${encodeURIComponent(revisionId)}/audio`;
  if (
    result.asset_id !== assetId ||
    result.revision_id !== revisionId ||
    result.audio_url !== expectedPath ||
    !Number.isFinite(result.duration_seconds) || result.duration_seconds <= 0 ||
    !Number.isSafeInteger(result.audio_size_bytes) || result.audio_size_bytes <= 0 ||
    !Array.isArray(result.chapter_ids) || result.chapter_ids.length < 1 ||
    new Set(result.chapter_ids).size !== result.chapter_ids.length ||
    !hasValidAudioTimeline(result) ||
    !Number.isSafeInteger(result.retention_marker_count) || result.retention_marker_count < 1 ||
    !Number.isSafeInteger(result.learned_claim_count) || result.learned_claim_count < 1 ||
    !Number.isSafeInteger(result.source_count) || result.source_count < 1 ||
    !Array.isArray(result.learned_claims) ||
    result.learned_claims.length !== result.learned_claim_count ||
    result.learned_claims.some((claim) =>
      !result.chapter_ids.includes(claim.chapter_id) || !claim.claim_text ||
      !Number.isSafeInteger(claim.source_count) || claim.source_count < 1 ||
      !claim.follow_up_prompt
    )
  ) {
    throw new Error("multimedia_local_audible_playback_identity_conflict");
  }
  return { ...result, audio_url: `${API_BASE}${result.audio_url}` };
}

export async function getMultimediaPaidAudioPlayback(
  assetId: string,
  revisionId: string,
): Promise<MultimediaPaidAudioPlayback> {
  const params = new URLSearchParams({ revision_id: revisionId });
  const resp = await apiFetch(
    `${API_BASE}/multimedia/assets/${encodeURIComponent(assetId)}/audio-playback?${params}`,
  );
  if (resp.status === 404) throw new Error("multimedia_paid_audio_playback_unavailable");
  if (resp.status === 409) throw new Error("multimedia_paid_audio_playback_conflict");
  if (resp.status === 503) throw new Error("multimedia_paid_audio_playback_runtime_unavailable");
  if (!resp.ok) throw new Error(`GET paid audio playback: HTTP ${resp.status}`);
  const result = (await resp.json()) as MultimediaPaidAudioPlayback;
  const expectedPath = `/multimedia/assets/${encodeURIComponent(assetId)}/audio-playback/${encodeURIComponent(revisionId)}/audio`;
  if (
    result.asset_id !== assetId || result.revision_id !== revisionId ||
    result.audio_url !== expectedPath || !Number.isFinite(result.duration_seconds) ||
    result.duration_seconds <= 0 || !Number.isSafeInteger(result.audio_size_bytes) ||
    result.audio_size_bytes <= 0 || !Array.isArray(result.chapter_ids) ||
    result.chapter_ids.length < 1 || new Set(result.chapter_ids).size !== result.chapter_ids.length ||
    !hasValidAudioTimeline(result) ||
    !Number.isSafeInteger(result.retention_marker_count) || result.retention_marker_count < 1 ||
    !Number.isSafeInteger(result.learned_claim_count) || result.learned_claim_count < 1 ||
    !Number.isSafeInteger(result.source_count) || result.source_count < 1 ||
    !Array.isArray(result.learned_claims) || result.learned_claims.length !== result.learned_claim_count ||
    result.learned_claims.some((claim) =>
      !result.chapter_ids.includes(claim.chapter_id) || !claim.claim_text ||
      !Number.isSafeInteger(claim.source_count) || claim.source_count < 1 || !claim.follow_up_prompt
    )
  ) throw new Error("multimedia_paid_audio_playback_identity_conflict");
  return { ...result, audio_url: `${API_BASE}${result.audio_url}` };
}

async function localAudibleCommand(
  assetId: string,
  revisionId: string,
  suffix: string,
  setId?: string,
): Promise<MultimediaLocalAudiblePreparedSet> {
  const resp = await apiFetch(
    `${API_BASE}/multimedia/assets/${encodeURIComponent(assetId)}/local-audible${suffix}`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        expected_revision_id: revisionId,
        ...(setId === undefined ? {} : { set_id: setId }),
      }),
    },
  );
  return localAudibleResponse(resp, assetId, revisionId, setId, `POST local audible${suffix}`);
}

async function localAudibleResponse(
  resp: Response,
  assetId: string,
  revisionId: string,
  setId: string | undefined,
  operation: string,
): Promise<MultimediaLocalAudiblePreparedSet> {
  if (resp.status === 404) throw new Error("multimedia_local_audible_unavailable");
  if (resp.status === 409) throw new Error("multimedia_local_audible_conflict");
  if (resp.status === 503) throw new Error("multimedia_local_audible_runtime_unavailable");
  if (!resp.ok) throw new Error(`${operation}: HTTP ${resp.status}`);
  const result = (await resp.json()) as MultimediaLocalAudiblePreparedSet;
  const statuses: MultimediaLocalAudibleStatus[] = [
    "preparing", "preparation_unknown", "ready_to_produce", "production_unknown", "registered",
  ];
  const recoverable = ["preparing", "preparation_unknown", "production_unknown"].includes(result.status);
  const chapterIds = result.chapters?.map((chapter) => chapter.chapter_id) ?? [];
  const allReady = result.chapters?.length > 0 && result.chapters.every(
    (chapter) => chapter.ready_span_count === chapter.span_count && chapter.remember_ready && chapter.recap_ready,
  );
  if (
    result.asset_id !== assetId || result.revision_id !== revisionId ||
    (setId !== undefined && result.set_id !== setId) ||
    !/^mmlocalaudibleset_[0-9a-f]{64}$/.test(result.set_id) ||
    !statuses.includes(result.status) || result.cost_usd !== 0 ||
    result.recoverable !== recoverable ||
    result.playback_ready !== (result.status === "registered") ||
    !Number.isFinite(result.total_duration_seconds) || result.total_duration_seconds < 0 ||
    !Array.isArray(result.chapters) || result.chapters.length < 1 ||
    new Set(chapterIds).size !== chapterIds.length ||
    result.chapters.some((chapter) =>
      !chapter.chapter_id || !chapter.title ||
      !Number.isSafeInteger(chapter.span_count) || chapter.span_count < 1 ||
      !Number.isSafeInteger(chapter.ready_span_count) || chapter.ready_span_count < 0 ||
      chapter.ready_span_count > chapter.span_count ||
      !Number.isFinite(chapter.duration_seconds) || chapter.duration_seconds < 0 ||
      !Number.isSafeInteger(chapter.source_count) || chapter.source_count < 0 ||
      typeof chapter.remember_ready !== "boolean" || typeof chapter.recap_ready !== "boolean" ||
      !Number.isSafeInteger(chapter.learned_claim_count) || chapter.learned_claim_count < 0
    ) ||
    (["ready_to_produce", "registered"].includes(result.status) && !allReady)
  ) {
    throw new Error("multimedia_local_audible_identity_conflict");
  }
  return result;
}

export async function authorizeMultimediaNarration(
  assetId: string,
  request: {
    request_id: string;
    expected_revision_id: string;
    chapter_id: string;
    approved_ceiling_microdollars: number;
    operator_acknowledged_spend: true;
  },
): Promise<MultimediaNarrationAuthorization> {
  const resp = await apiFetch(
    `${API_BASE}/multimedia/assets/${encodeURIComponent(assetId)}/narration-authorizations`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(request),
    },
  );
  if (resp.status === 404) throw new Error("multimedia_narration_authorization_unavailable");
  if (resp.status === 409) throw new Error("multimedia_narration_authorization_conflict");
  if (resp.status === 503) throw new Error("multimedia_narration_authorization_runtime_unavailable");
  if (!resp.ok) throw new Error(`POST /multimedia/assets/{id}/narration-authorizations: HTTP ${resp.status}`);
  const result = (await resp.json()) as MultimediaNarrationAuthorization;
  if (
    result.chapter_id !== request.chapter_id ||
    result.authorization.asset_id !== assetId ||
    result.authorization.revision_id !== result.child_revision_id ||
    result.authorization.request_body_digest !== result.request_body_digest ||
    result.authorization.request_id !== request.request_id ||
    result.authorization.approved_ceiling_microdollars !== request.approved_ceiling_microdollars ||
    result.authorization.version !== 2 ||
    result.authorization.endpoint_capability !== "text-to-speech"
  ) {
    throw new Error("multimedia_narration_authorization_identity_conflict");
  }
  return result;
}

export async function getMultimediaReviewedVisualSet(
  assetId: string,
  revisionId: string,
): Promise<MultimediaReviewedVisualSet> {
  const params = new URLSearchParams({ revision_id: revisionId });
  const resp = await apiFetch(
    `${API_BASE}/multimedia/assets/${encodeURIComponent(assetId)}/reviewed-visuals?${params}`,
  );
  if (resp.status === 404) throw new Error("multimedia_reviewed_visuals_unavailable");
  if (resp.status === 503) throw new Error("multimedia_reviewed_visuals_runtime_unavailable");
  if (!resp.ok) throw new Error(`GET /multimedia/assets/{id}/reviewed-visuals: HTTP ${resp.status}`);
  const result = (await resp.json()) as MultimediaReviewedVisualSet;
  if (
    result.asset_id !== assetId ||
    result.revision_id !== revisionId ||
    result.chapter_ids.length !== result.scene_ids.length ||
    result.chapter_ids.length !== result.candidate_ids.length
  ) {
    throw new Error("multimedia_reviewed_visuals_identity_conflict");
  }
  return result;
}

export async function authorizeMultimediaVisual(
  assetId: string,
  request: {
    request_id: string;
    expected_revision_id: string;
    chapter_id: string;
    approved_ceiling_microdollars: number;
    operator_acknowledged_spend: true;
  },
): Promise<MultimediaVisualAuthorization> {
  const resp = await apiFetch(
    `${API_BASE}/multimedia/assets/${encodeURIComponent(assetId)}/visual-authorizations`,
    { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(request) },
  );
  if (resp.status === 404) throw new Error("multimedia_visual_authorization_unavailable");
  if (resp.status === 409) throw new Error("multimedia_visual_authorization_conflict");
  if (resp.status === 503) throw new Error("multimedia_visual_authorization_runtime_unavailable");
  if (!resp.ok) throw new Error(`POST /multimedia/assets/{id}/visual-authorizations: HTTP ${resp.status}`);
  const result = (await resp.json()) as MultimediaVisualAuthorization;
  if (
    result.chapter_id !== request.chapter_id ||
    result.authorization.asset_id !== assetId ||
    result.authorization.revision_id !== request.expected_revision_id ||
    result.authorization.request_id !== request.request_id ||
    result.authorization.authorization_id.length < 1 ||
    result.authorization.version !== 2 ||
    result.authorization.request_body_digest !== result.request_body_digest ||
    result.quote.quote_id !== result.authorization.quote_id ||
    result.quote.ceiling_microdollars !== request.approved_ceiling_microdollars ||
    result.authorization.endpoint_capability !== "text-to-image"
  ) {
    throw new Error("multimedia_visual_authorization_identity_conflict");
  }
  return result;
}

export async function submitMultimediaVisualGeneration(
  assetId: string,
  requestId: string,
  revisionId: string,
  expectedAuthorizationId: string,
): Promise<MultimediaVisualGeneration> {
  return visualGenerationCommand(assetId, "", {
    request_id: requestId,
    expected_revision_id: revisionId,
  }, expectedAuthorizationId);
}

export async function pollMultimediaVisualGeneration(
  assetId: string,
  executionId: string,
  revisionId: string,
  expectedAuthorizationId: string,
): Promise<MultimediaVisualGeneration> {
  return visualGenerationCommand(
    assetId,
    `/${encodeURIComponent(executionId)}/poll`,
    { expected_revision_id: revisionId },
    expectedAuthorizationId,
    executionId,
  );
}

async function visualGenerationCommand(
  assetId: string,
  suffix: string,
  body: Record<string, string>,
  expectedAuthorizationId: string,
  expectedExecutionId?: string,
): Promise<MultimediaVisualGeneration> {
  const resp = await apiFetch(
    `${API_BASE}/multimedia/assets/${encodeURIComponent(assetId)}/visual-generations${suffix}`,
    { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) },
  );
  if (resp.status === 404) throw new Error("multimedia_visual_generation_unavailable");
  if (resp.status === 409) throw new Error("multimedia_visual_generation_conflict");
  if (resp.status === 503) throw new Error("multimedia_visual_generation_runtime_unavailable");
  if (!resp.ok) throw new Error(`POST /multimedia/assets/{id}/visual-generations: HTTP ${resp.status}`);
  const result = (await resp.json()) as MultimediaVisualGeneration;
  if (
    result.authorization_id !== expectedAuthorizationId ||
    !result.execution_id ||
    (expectedExecutionId !== undefined && result.execution_id !== expectedExecutionId)
  ) {
    throw new Error("multimedia_visual_generation_identity_conflict");
  }
  return result;
}

export async function materializeMultimediaVisualCandidates(
  assetId: string,
  executionId: string,
  authorityRequestId: string,
  revisionId: string,
): Promise<MultimediaVisualCandidateSet> {
  const resp = await apiFetch(
    `${API_BASE}/multimedia/assets/${encodeURIComponent(assetId)}/visual-generations/${encodeURIComponent(executionId)}/materialize`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ authority_request_id: authorityRequestId, expected_revision_id: revisionId }),
    },
  );
  if (resp.status === 409) throw new Error("multimedia_visual_materialization_conflict");
  if (resp.status === 503) throw new Error("multimedia_visual_materialization_runtime_unavailable");
  if (!resp.ok) throw new Error(`POST /multimedia/assets/{id}/visual-generations/{id}/materialize: HTTP ${resp.status}`);
  const result = (await resp.json()) as MultimediaVisualCandidateSet;
  const candidateIds = result.candidates.map((candidate) => candidate.candidate_id);
  if (
    result.execution_id !== executionId ||
    !result.candidates.length ||
    new Set(candidateIds).size !== candidateIds.length ||
    result.candidates.some(
      (candidate) =>
        !candidate.candidate_id ||
        !candidate.artifact_receipt_id ||
        !["image/png", "image/jpeg"].includes(candidate.media_type) ||
        !Number.isSafeInteger(candidate.byte_count) ||
        candidate.byte_count < 1,
    )
  ) {
    throw new Error("multimedia_visual_materialization_identity_conflict");
  }
  return result;
}

export async function previewMultimediaVisualCandidate(
  assetId: string,
  revisionId: string,
  candidateId: string,
): Promise<Blob> {
  const params = new URLSearchParams({ revision_id: revisionId });
  const resp = await apiFetch(
    `${API_BASE}/multimedia/assets/${encodeURIComponent(assetId)}/visual-candidates/${encodeURIComponent(candidateId)}/content?${params}`,
  );
  if (resp.status === 404) throw new Error("multimedia_visual_candidate_unavailable");
  if (resp.status === 503) throw new Error("multimedia_visual_review_runtime_unavailable");
  if (!resp.ok) throw new Error(`GET /multimedia/assets/{id}/visual-candidates/{id}/content: HTTP ${resp.status}`);
  const type = resp.headers.get("Content-Type")?.split(";", 1)[0];
  if (type !== "image/png" && type !== "image/jpeg") {
    throw new Error("multimedia_visual_candidate_media_conflict");
  }
  return resp.blob();
}

export async function attestMultimediaVisualCandidate(
  assetId: string,
  revisionId: string,
  candidateId: string,
): Promise<MultimediaVisualAttestation> {
  const resp = await apiFetch(
    `${API_BASE}/multimedia/assets/${encodeURIComponent(assetId)}/visual-candidates/${encodeURIComponent(candidateId)}/attestation`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        expected_revision_id: revisionId,
        operator_acknowledged_generated_provenance: true,
      }),
    },
  );
  if (resp.status === 409) throw new Error("multimedia_visual_attestation_conflict");
  if (resp.status === 503) throw new Error("multimedia_visual_review_runtime_unavailable");
  if (!resp.ok) throw new Error(`POST /multimedia/assets/{id}/visual-candidates/{id}/attestation: HTTP ${resp.status}`);
  const result = (await resp.json()) as MultimediaVisualAttestation;
  if (!result.artifact_receipt_id || !result.reviewer_id || !result.attested_at) {
    throw new Error("multimedia_visual_attestation_identity_conflict");
  }
  return result;
}

export async function registerMultimediaReviewedVisuals(
  assetId: string,
  revisionId: string,
  requestId: string,
  bindings: Array<{ chapter_id: string; candidate_id: string }>,
): Promise<MultimediaReviewedVisualSet> {
  const resp = await apiFetch(
    `${API_BASE}/multimedia/assets/${encodeURIComponent(assetId)}/reviewed-visuals`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ request_id: requestId, expected_revision_id: revisionId, bindings }),
    },
  );
  if (resp.status === 404) throw new Error("multimedia_reviewed_visuals_unavailable");
  if (resp.status === 409) throw new Error("multimedia_reviewed_visuals_conflict");
  if (resp.status === 503) throw new Error("multimedia_reviewed_visuals_runtime_unavailable");
  if (!resp.ok) throw new Error(`POST /multimedia/assets/{id}/reviewed-visuals: HTTP ${resp.status}`);
  const result = (await resp.json()) as MultimediaReviewedVisualSet;
  if (
    result.asset_id !== assetId ||
    result.revision_id !== revisionId ||
    result.chapter_ids.length !== bindings.length ||
    result.scene_ids.length !== bindings.length ||
    !result.selection_digest ||
    result.candidate_ids.some((candidateId, index) => candidateId !== bindings[index]?.candidate_id) ||
    result.chapter_ids.some((chapterId, index) => chapterId !== bindings[index]?.chapter_id)
  ) {
    throw new Error("multimedia_reviewed_visuals_identity_conflict");
  }
  return result;
}

export async function produceAuthorizedMultimedia(
  assetId: string,
  expectedRevisionId: string,
  chapterAuthorities: Array<{
    chapter_id: string;
    authorization: MultimediaNarrationAuthorization["authorization"];
  }>,
): Promise<MultimediaAssetRecord> {
  const resp = await apiFetch(
    `${API_BASE}/multimedia/assets/${encodeURIComponent(assetId)}/production`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        expected_revision_id: expectedRevisionId,
        chapter_authorities: chapterAuthorities,
      }),
    },
  );
  if (resp.status === 404) throw new Error("multimedia_production_worker_unavailable");
  if (resp.status === 409) throw new Error("multimedia_production_worker_conflict");
  if (resp.status === 503) throw new Error("multimedia_production_worker_runtime_unavailable");
  if (!resp.ok) throw new Error(`POST /multimedia/assets/{id}/production: HTTP ${resp.status}`);
  const record = (await resp.json()) as MultimediaAssetRecord;
  if (!record.production_link) {
    throw new Error("multimedia_production_worker_missing_link");
  }
  if (
    record.asset.asset_id !== assetId ||
    record.asset.revision_id !== expectedRevisionId ||
    record.production_link.asset_id !== assetId ||
    record.production_link.revision_id !== expectedRevisionId
  ) {
    throw new Error("multimedia_production_worker_identity_conflict");
  }
  return record;
}

export async function produceAuthorizedAudio(
  assetId: string,
  expectedRevisionId: string,
  chapterAuthorities: Array<{
    chapter_id: string;
    authorization: MultimediaNarrationAuthorization["authorization"];
  }>,
): Promise<MultimediaAssetRecord> {
  const resp = await apiFetch(
    `${API_BASE}/multimedia/assets/${encodeURIComponent(assetId)}/audio-production`,
    { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({
      expected_revision_id: expectedRevisionId, chapter_authorities: chapterAuthorities,
    }) },
  );
  if (resp.status === 404) throw new Error("multimedia_audio_production_worker_unavailable");
  if (resp.status === 409) throw new Error("multimedia_audio_production_worker_conflict");
  if (resp.status === 503) throw new Error("multimedia_audio_production_worker_runtime_unavailable");
  if (!resp.ok) throw new Error(`POST /multimedia/assets/{id}/audio-production: HTTP ${resp.status}`);
  const record = (await resp.json()) as MultimediaAssetRecord;
  if (!record.audio_production_link || record.asset.asset_id !== assetId ||
      record.asset.revision_id !== expectedRevisionId ||
      record.audio_production_link.asset_id !== assetId ||
      record.audio_production_link.revision_id !== expectedRevisionId) {
    throw new Error("multimedia_audio_production_worker_identity_conflict");
  }
  return record;
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

export async function previewMultimediaSteering(
  assetId: string,
  request: MultimediaSteeringRequest,
): Promise<MultimediaSteeringPreview> {
  const resp = await apiFetch(`${API_BASE}/multimedia/assets/${encodeURIComponent(assetId)}/steering-preview`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(request),
  });
  if (resp.status === 404) throw new Error("multimedia_asset_not_found");
  if (resp.status === 409) throw new Error(await multimediaSteeringConflict(resp));
  if (!resp.ok) throw new Error(`POST /multimedia/assets/{id}/steering-preview: HTTP ${resp.status}`);
  return (await resp.json()) as MultimediaSteeringPreview;
}

export async function steerMultimediaAsset(
  assetId: string,
  request: MultimediaSteeringRequest & { preview_token: string },
): Promise<MultimediaAssetRecord> {
  const resp = await apiFetch(`${API_BASE}/multimedia/assets/${encodeURIComponent(assetId)}/steer`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(request),
  });
  if (resp.status === 404) throw new Error("multimedia_asset_not_found");
  if (resp.status === 409) throw new Error(await multimediaSteeringConflict(resp));
  if (!resp.ok) throw new Error(`POST /multimedia/assets/{id}/steer: HTTP ${resp.status}`);
  return (await resp.json()) as MultimediaAssetRecord;
}

async function multimediaSteeringConflict(resp: Response): Promise<string> {
  try {
    const body = (await resp.json()) as { detail?: unknown };
    return typeof body.detail === "string" ? body.detail : "multimedia_steering_conflict";
  } catch {
    return "multimedia_steering_conflict";
  }
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
