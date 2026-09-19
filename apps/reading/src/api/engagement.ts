/**
 * Engagement spine API client — mirrors interfaces/research/api/engagement_routes.py
 *
 * Spawn deep-research from highlights, attach arxiv/substack refs, assemble
 * research context packs, collective multi-spawn merge, session flywheel.
 * Process-local store on the server (MVP).
 */

import { API_BASE, apiFetch } from "../lib/api";
import type {
  CitationEvidence,
  CollectiveResearchUnit,
  ResearchContextPack,
  SourceReference,
} from "../workspace/researchContextPack";
import type { ResearchArtifactClaimChallengeReceipt } from "../lib/api";

export type SpawnFromHighlightRequest = {
  asset_id: string;
  selection_text: string;
  region_id?: string | null;
  page?: number | null;
  goal_hint?: string | null;
  model_id?: string | null;
  references?: string[];
  force_new?: boolean;
  /** Residual (ji): closed research tier for reserved spawn. */
  research_tier?: "fast" | "deep" | "wrestle" | null;
  citation_provenance?: CitationProvenanceRequest;
};

export type CitationProvenanceRequest = {
  source_kind: "synthesis_claim";
  source_asset_id: string;
  claim_id: string;
  chunk_ids: string[];
};

export type CitationProvenanceReceipt = CitationProvenanceRequest & { document_id: string };

export type SpawnResponse = {
  spawn_id: string;
  investigation_id: string;
  parent_asset_id: string;
  goal: string;
  status: string;
  model_id?: string | null;
  region_id?: string | null;
  source_references: SourceReference[];
  research_tier?: "fast" | "deep" | "wrestle" | string | null;
  view_format: "html";
  citation_provenance?: CitationProvenanceReceipt | null;
  claim_challenge?: ResearchArtifactClaimChallengeReceipt | null;
};

export type SessionOpenRequest = SpawnFromHighlightRequest & {
  view_mode?: "floating" | "full";
};

export type SessionOpenResponse = {
  session_id: string;
  spawn_id: string;
  investigation_id: string;
  parent_asset_id: string;
  selection_text: string;
  status: string;
  view_mode: string;
  model_id?: string | null;
  goal?: string;
  research_tier?: "fast" | "deep" | "wrestle" | string | null;
  view_format: "html";
  citation_provenance?: CitationProvenanceReceipt | null;
  /**
   * Residual (nw/asu): Antiek-bench usage event recorded on open
   * (floating_deep_research | twin_chase | highlight_dr_launch) for recursive suite rewrite.
   */
  usage_event?: {
    task_class: string;
    outcome: string;
    prompt_hint?: string;
    source?: string;
    model_id?: string | null;
  } | null;
  usage_event_error?: string | null;
};

export type ResearchContextResponse = ResearchContextPack & {
  twin_count: number;
  ref_count: number;
  prompt_block: string;
};

export type CollectiveResponse = CollectiveResearchUnit & {
  manifest_id?: string;
  workspace_resume_ref?: { manifest_id: string };
  spawn_count: number;
  twin_count: number;
  ref_count: number;
  prompt_block: string;
  research_tiers?: string[];
  recommended_research_tier?: "fast" | "deep" | "wrestle" | string;
  /** Residual (oi/oj): Antiek-bench usage from multi-spawn cohesive unit. */
  usage_event?: {
    task_class?: string;
    outcome?: string;
    source?: string;
    prompt_hint?: string;
    model_id?: string | null;
  } | null;
  usage_event_error?: string | null;
};

export type SessionFlywheelResponse = {
  session_id: string;
  spawn_id: string;
  status: string;
  context: ResearchContextPack & { twin_count?: number; ref_count?: number };
  view_format: "html";
  prompt_block: string;
  /** Residual (jt): closed research tier from reserved session. */
  research_tier?: "fast" | "deep" | "wrestle" | string | null;
  /** Best-effort Antiek-bench usage event from flywheel complete. */
  usage_event?: {
    task_class?: string;
    outcome?: string;
    source?: string;
    model_id?: string | null;
    [key: string]: unknown;
  } | null;
};

async function readJson<T>(res: Response): Promise<T> {
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`engagement API ${res.status}: ${text.slice(0, 200)}`);
  }
  return (await res.json()) as T;
}

export async function spawnFromHighlight(
  body: SpawnFromHighlightRequest,
): Promise<SpawnResponse> {
  const res = await apiFetch(`${API_BASE}/engagement/spawn-from-highlight`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  return readJson<SpawnResponse>(res);
}

export async function attachSourceRefs(
  spawn_id: string,
  references: string[],
): Promise<{
  spawn_id: string;
  source_references: SourceReference[];
  /** Residual (ko): reserved spawn research_tier after attach. */
  research_tier?: "fast" | "deep" | "wrestle" | string | null;
  view_format: "html";
}> {
  const res = await apiFetch(`${API_BASE}/engagement/attach-refs`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ spawn_id, references }),
  });
  return readJson(res);
}

export async function fetchResearchContext(body: {
  asset_id: string;
  spawn_id?: string | null;
  query?: string | null;
  include_twin_promote?: boolean;
}): Promise<ResearchContextResponse> {
  const res = await apiFetch(`${API_BASE}/engagement/research-context`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  return readJson<ResearchContextResponse>(res);
}

export async function fetchCollectiveResearch(body: {
  spawn_ids: string[];
  query?: string | null;
  include_twin_promote?: boolean;
}): Promise<CollectiveResponse> {
  const res = await apiFetch(`${API_BASE}/engagement/collective`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  return readJson<CollectiveResponse>(res);
}

export type CollectiveManifestReference = { schema_version: 1; manifest_id: string; collective_id: string; ordered_spawn_ids: string[]; membership_sha256: string; availability: "ready" | "unavailable"; view_format: "html" };

export async function createCollectiveManifest(spawn_ids: string[]): Promise<CollectiveManifestReference> {
  return readJson(await apiFetch(`${API_BASE}/engagement/collective-manifests`, { method: "POST", cache: "no-store", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ schema_version: 1, spawn_ids }) }));
}

export async function fetchCollectiveManifestReference(manifestId: string, signal?: AbortSignal): Promise<CollectiveManifestReference> {
  return readJson(await apiFetch(`${API_BASE}/account/collective-manifest-refs/${encodeURIComponent(manifestId)}`, { signal, cache: "no-store" }));
}

export async function projectCollectiveManifest(manifestId: string, signal?: AbortSignal): Promise<CollectiveResponse & { manifest_id: string }> {
  return readJson(await apiFetch(`${API_BASE}/engagement/collective/${encodeURIComponent(manifestId)}/project`, { method: "POST", signal, cache: "no-store" }));
}

export async function fetchCollectiveCouncilReference(planId: string, signal?: AbortSignal): Promise<unknown> {
  return readJson(await apiFetch(`${API_BASE}/account/collective-council-refs/${encodeURIComponent(planId)}`, { signal, cache: "no-store" }));
}

export type CouncilMemberPlan = {
  spawn_id: string;
  investigation_id: string;
  parent_asset_id: string;
  role: string;
  model_id: string;
  projected_max_cents: number;
  evidence_sha256: string;
  source_ref_ids: string[];
  twin_note_ids: string[];
};

export type CouncilPlanResponse = {
  plan_id: string;
  collective_id: string;
  shared_prompt: string;
  members: CouncilMemberPlan[];
  synthesizer_model_id: string;
  synthesizer_projected_max_cents: number;
  approved_ceiling_cents: number;
  input_sha256: string;
  state: "preflight" | "approved" | "running" | "complete" | "failed" | "unknown";
  approval_receipt_id?: string | null;
};

export type CouncilCallReceipt = {
  role: string;
  model_id: string;
  projected_max_cents: number;
  state: "complete" | "not_dispatched" | "unknown" | "reconciled_without_output";
  actual_cents?: number | null;
  provider_receipt_id?: string | null;
  output_text?: string | null;
  hold_id?: string | null;
  error_type?: string | null;
};

export type CouncilResultResponse = {
  result_id: string;
  plan_id: string;
  state: "complete" | "failed" | "unknown";
  member_receipts: CouncilCallReceipt[];
  synthesizer_receipt?: CouncilCallReceipt | null;
  spent_cents: number;
  held_cents: number;
  html?: string | null;
  result_sha256?: string;
};

export async function preflightCollectiveCouncil(body: {
  collective_id: string;
  shared_prompt: string;
  members: Array<{
    spawn_id: string;
    role: string;
    model_id: string;
    projected_max_cents: number;
  }>;
  synthesizer_model_id: string;
  synthesizer_projected_max_cents: number;
  approved_ceiling_cents: number;
}): Promise<CouncilPlanResponse> {
  const res = await apiFetch(`${API_BASE}/engagement/council/preflight`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  return readJson<CouncilPlanResponse>(res);
}

export async function approveCollectiveCouncil(
  plan: CouncilPlanResponse,
): Promise<CouncilPlanResponse> {
  const res = await apiFetch(
    `${API_BASE}/engagement/council/${encodeURIComponent(plan.plan_id)}/approve`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        expected_input_sha256: plan.input_sha256,
        approved_ceiling_cents: plan.approved_ceiling_cents,
      }),
    },
  );
  return readJson<CouncilPlanResponse>(res);
}

export async function runCollectiveCouncil(
  planId: string,
  maxWorkers = 4,
): Promise<CouncilResultResponse> {
  const res = await apiFetch(
    `${API_BASE}/engagement/council/${encodeURIComponent(planId)}/run`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ max_workers: maxWorkers }),
    },
  );
  return readJson<CouncilResultResponse>(res);
}

export async function fetchCollectiveCouncilResult(
  resultId: string,
): Promise<CouncilResultResponse> {
  const res = await apiFetch(
    `${API_BASE}/engagement/council/results/${encodeURIComponent(resultId)}`,
  );
  return readJson<CouncilResultResponse>(res);
}

export async function convergeCollectiveCouncil(body: {
  plan_id: string;
  result_id: string;
  expected_result_sha256: string;
  mode: "offline_collective" | "draft_combined" | "into_parent";
  parent_asset_id?: string | null;
  promotion_note_ids?: string[];
}): Promise<Record<string, unknown>> {
  const res = await apiFetch(
    `${API_BASE}/engagement/council/${encodeURIComponent(body.plan_id)}/converge`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        result_id: body.result_id,
        expected_result_sha256: body.expected_result_sha256,
        mode: body.mode,
        parent_asset_id: body.parent_asset_id ?? null,
        promotion_note_ids: body.promotion_note_ids ?? [],
      }),
    },
  );
  return readJson<Record<string, unknown>>(res);
}

/** Merge completed spawns into parent or draft-combined (default draft). */
export type MergeMode = "into_parent" | "draft_combined";

export type MergeProductResponse = {
  mode: MergeMode | string;
  parent_asset_id: string;
  document_id: string;
  source_spawn_ids: string[];
  sections_merged: number;
  draft_leaves_parent: boolean;
  parent_document_id: string;
  /** Residual (kn): per-spawn closed research tiers from merge sources. */
  research_tiers?: string[];
  /** Residual (kn): depth-max recommended tier for follow-on research. */
  recommended_research_tier?: "fast" | "deep" | "wrestle" | string;
  view_format: "html" | string;
  product_panel: string;
  source: string;
  notes: string[];
  html?: string | null;
  citation_evidence?: CitationEvidence[];
  /** Immutable review token for an exact draft_combined document model. */
  draft_sha256?: string | null;
  /** Legacy merge is preview authority until the explicit canonical commit. */
  canonical_committed?: boolean;
  /** Residual (oi/oj): Antiek-bench usage from document merge path. */
  usage_event?: {
    task_class?: string;
    outcome?: string;
    source?: string;
    prompt_hint?: string;
    model_id?: string | null;
  } | null;
  usage_event_error?: string | null;
};

export async function mergeSpawnOutputs(body: {
  parent_asset_id: string;
  spawn_ids: string[];
  mode?: MergeMode;
  parent_title?: string | null;
  parent_body?: string | null;
  include_html?: boolean;
}): Promise<MergeProductResponse> {
  const res = await apiFetch(`${API_BASE}/engagement/merge`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      parent_asset_id: body.parent_asset_id,
      spawn_ids: body.spawn_ids,
      mode: body.mode ?? "draft_combined",
      parent_title: body.parent_title ?? null,
      parent_body: body.parent_body ?? null,
      include_html: body.include_html ?? true,
    }),
  });
  return readJson<MergeProductResponse>(res);
}

export type CanonicalMergeCommitResponse = {
  deliverable_id: string;
  draft_document_id: string;
  old_revision: string | null;
  new_revision: string;
  section_id: string;
  node_ids: string[];
  paragraph_count: number;
  draft_sha256: string;
  twin_note_count: number;
  view_format: "html" | string;
  html: string;
};

export async function commitReviewedMergeDraft(body: {
  draft_document_id: string;
  reviewed_draft_sha256: string;
  target_deliverable_id: string;
  expected_revision?: string | null;
  create_combined: boolean;
}): Promise<CanonicalMergeCommitResponse> {
  const res = await apiFetch(`${API_BASE}/engagement/merge/commit`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      draft_document_id: body.draft_document_id,
      reviewed_draft_sha256: body.reviewed_draft_sha256,
      target_deliverable_id: body.target_deliverable_id,
      expected_revision: body.expected_revision ?? null,
      create_combined: body.create_combined,
    }),
  });
  return readJson<CanonicalMergeCommitResponse>(res);
}

export type CanonicalMergeHtmlResponse = {
  deliverable_id: string;
  section_id: string;
  revision: string;
  draft_sha256: string;
  twin_note_count: number;
  view_format: "html" | string;
  html: string;
};

export async function getCanonicalMergeHtml(
  deliverableId: string,
): Promise<CanonicalMergeHtmlResponse> {
  const res = await apiFetch(
    `${API_BASE}/engagement/merge/canonical/html?deliverable_id=${encodeURIComponent(deliverableId)}`,
  );
  return readJson<CanonicalMergeHtmlResponse>(res);
}

/** Residual (hq): offline-vs-live hydrate injector readiness (Settings). */
export type HydrateLiveStatusResponse = {
  view_format: "html" | string;
  product_panel: string;
  source: string;
  offline_honest: boolean;
  any_live_injector: boolean;
  arxiv: {
    env_flag: string;
    env_enabled: boolean;
    injector_installed: boolean;
  };
  substack: {
    env_flag: string;
    env_enabled: boolean;
    injector_installed: boolean;
  };
  generic_fetch_publication_installed: boolean;
  notes: string[];
  html?: string | null;
};

export async function fetchHydrateLiveStatus(): Promise<HydrateLiveStatusResponse> {
  const res = await apiFetch(`${API_BASE}/engagement/hydrate-live-status`);
  return readJson<HydrateLiveStatusResponse>(res);
}

/** Residual (hs): offline-vs-live twin seed note_taker readiness (Settings). */
export type TwinSeedLiveStatusResponse = {
  view_format: "html" | string;
  product_panel: string;
  source: string;
  offline_honest: boolean;
  live_env: boolean;
  use_dispatch: boolean;
  injector_installed: boolean;
  cost_projection_ready?: boolean;
  projected_max_cents?: number | null;
  live_env_flag: string;
  use_dispatch_env_flag: string;
  notes: string[];
  html?: string | null;
};

export async function fetchTwinSeedLiveStatus(): Promise<TwinSeedLiveStatusResponse> {
  const res = await apiFetch(`${API_BASE}/engagement/twin-seed-live-status`);
  return readJson<TwinSeedLiveStatusResponse>(res);
}

export type CollectiveCouncilStatusResponse = {
  view_format: "html" | string;
  product_panel: string;
  substrate_available: boolean;
  executor_installed: boolean;
  ledger_installed: boolean;
  live_ready: boolean;
  offline_convergence_available: boolean;
  operator_gated: boolean;
  notes: string[];
};

export async function fetchCollectiveCouncilStatus(): Promise<CollectiveCouncilStatusResponse> {
  const res = await apiFetch(`${API_BASE}/engagement/council/status`, { cache: "no-store" });
  return readJson<CollectiveCouncilStatusResponse>(res);
}

/** Hydrate arxiv/substack/url into HTML-first engagement asset. */
export type HydrateRefResponse = {
  asset_id: string;
  ref: SourceReference;
  title: string;
  body_text: string;
  fetched: boolean;
  /**
   * Residual (gz/hc): true when identity-only offline path (no live body).
   * Prefer this over inventing abstracts; false when injector landed body.
   */
  offline_honest?: boolean;
  view_format: "html" | string;
  html?: string | null;
  notes: string[];
  product_panel: string;
  source: string;
};

export async function hydratePublicationRef(body: {
  reference: string;
  include_html?: boolean;
  attach_spawn_id?: string | null;
}): Promise<HydrateRefResponse> {
  const res = await apiFetch(`${API_BASE}/engagement/hydrate-ref`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      reference: body.reference,
      include_html: body.include_html ?? true,
      attach_spawn_id: body.attach_spawn_id ?? null,
    }),
  });
  return readJson<HydrateRefResponse>(res);
}

/** Residual (air): multi-hop citation chain stage item with stable anchor. */
export type CitationChainHopItem = {
  hop: "insight" | "question" | "source" | string;
  index: number;
  text: string;
  anchor: string;
  kind?: string;
  raw?: string;
  canonical_url?: string;
};

/** Residual (air): ordered hop stage (insights | questions | sources). */
export type CitationChainHop = {
  hop: "insights" | "questions" | "sources" | string;
  label: string;
  count: number;
  items: CitationChainHopItem[];
};

/** Evidence pack: twin insights/questions + spawn source refs (HTML-first). */
export type EvidencePackResponse = {
  asset_id: string;
  spawn_id?: string | null;
  insight_count: number;
  question_count: number;
  ref_count: number;
  insights: string[];
  questions: string[];
  source_references: SourceReference[];
  /**
   * Residual (air): ordered multi-hop stages for claim→source navigation.
   * Never invents supported_by edges — sequential stages with anchors only.
   */
  citation_chain?: CitationChainHop[];
  /** True only when every insight explicitly links to an attached source ref. */
  chain_complete?: boolean;
  grounded_insight_count?: number;
  ungrounded_insight_count?: number;
  grounding_links?: Array<{
    note_id: string;
    insight_index: number;
    source_ref_ids: string[];
  }>;
  /**
   * Residual (apz/aqa): substrate hop pipeline completeness summary
   * (present/missing/coverage_ratio · never invent empty hops).
   */
  citation_hop_pipeline?: {
    stages?: string[];
    present?: string[];
    missing?: string[];
    present_count?: number;
    total?: number;
    coverage_ratio?: number;
    chain_complete?: boolean;
    insight_count?: number;
    question_count?: number;
    ref_count?: number;
  } | null;
  /**
   * Residual (aqg/aqi): substrate world-class readiness (hops known ·
   * multi-stage unknown on evidence · never invent stage coverage).
   */
  world_class_readiness?: {
    multi_stage_ready?: boolean;
    citation_hops_ready?: boolean | null;
    stage_coverage_ratio?: number;
    hop_coverage_ratio?: number | null;
    world_class_bar?: string;
    notes?: string[];
  } | null;
  /**
   * Residual (kc/kd): reserved spawn research_tier when spawn_id set
   * (null when pack has no spawn identity).
   */
  research_tier?: "fast" | "deep" | "wrestle" | string | null;
  view_format: "html" | string;
  product_panel: string;
  source: string;
  notes: string[];
  html?: string | null;
};

export async function fetchEvidencePack(body: {
  asset_id: string;
  spawn_id?: string | null;
  include_html?: boolean;
}): Promise<EvidencePackResponse> {
  const res = await apiFetch(`${API_BASE}/engagement/evidence-pack`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      asset_id: body.asset_id,
      spawn_id: body.spawn_id ?? null,
      include_html: body.include_html ?? true,
    }),
  });
  return readJson<EvidencePackResponse>(res);
}

/** Research progress plan→gather→synthesize→cite telemetry. */
export type ResearchProgressResponse = {
  spawn_id: string;
  event_count: number;
  events: Array<{
    spawn_id: string;
    stage: string;
    message: string;
    ts: number;
    sequence: number;
  }>;
  latest_stage: string | null;
  is_terminal: boolean;
  /**
   * Residual (aqc/aqd): substrate multi-stage pipeline completeness summary
   * (plan→terminal · never invent stages).
   */
  stage_pipeline?: {
    stages?: string[];
    completed?: string[];
    current?: string | null;
    completed_count?: number;
    total?: number;
    coverage_ratio?: number;
    is_terminal?: boolean;
  } | null;
  /**
   * Residual (aqf/aqh): substrate world-class readiness (multi-stage known ·
   * hops unknown on progress · never invent hop coverage).
   */
  world_class_readiness?: {
    multi_stage_ready?: boolean;
    citation_hops_ready?: boolean | null;
    stage_coverage_ratio?: number;
    hop_coverage_ratio?: number | null;
    world_class_bar?: string;
    notes?: string[];
  } | null;
  /** Residual (jz/ka): spawn reserved research_tier when present. */
  research_tier?: "fast" | "deep" | "wrestle" | string | null;
  view_format: "html" | string;
  product_panel: string;
  source: string;
  notes: string[];
  html?: string | null;
};

export async function fetchResearchProgress(
  spawnId: string,
  opts?: { includeHtml?: boolean },
): Promise<ResearchProgressResponse> {
  const q = opts?.includeHtml ? "?include_html=true" : "";
  const res = await apiFetch(
    `${API_BASE}/engagement/progress/${encodeURIComponent(spawnId)}${q}`,
  );
  return readJson<ResearchProgressResponse>(res);
}

export async function seedResearchProgress(
  spawnId: string,
  opts?: { includeHtml?: boolean },
): Promise<ResearchProgressResponse> {
  const res = await apiFetch(`${API_BASE}/engagement/progress/seed`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      spawn_id: spawnId,
      include_html: opts?.includeHtml ?? true,
    }),
  });
  return readJson<ResearchProgressResponse>(res);
}

/** Twin notes — recursive note-taker substrate per asset. */
export type TwinNotesResponse = {
  asset_id: string;
  note_count: number;
  insight_count: number;
  question_count: number;
  notes: Array<{
    note_id: string;
    asset_id: string;
    kind: "insight" | "question" | string;
    text: string;
    source_spawn_id?: string | null;
    investigation_id?: string | null;
    source_ref_ids?: string[];
    origin?: string | null;
    source_revision_sha256?: string | null;
    seed_batch_id?: string | null;
    seed_receipt?: {
      provider?: string;
      model?: string;
      actual_cents?: number;
      prompt_version?: string;
      canonical_content_hash?: string;
      dispatch_event_id?: string;
    } | null;
  }>;
  /** Residual (la/lb): reserved spawn research_tier when seed/list scoped. */
  research_tier?: "fast" | "deep" | "wrestle" | string | null;
  source_spawn_id?: string | null;
  view_format: "html" | string;
  product_panel: string;
  source: string;
  messages?: string[];
  html?: string | null;
};

export async function fetchTwinNotes(
  assetId: string,
  opts?: { includeHtml?: boolean; spawnId?: string | null },
): Promise<TwinNotesResponse> {
  const params = new URLSearchParams();
  params.set("asset_id", assetId);
  if (opts?.includeHtml) params.set("include_html", "true");
  // Residual (le): optional spawn_id scopes research_tier on list payload.
  if (opts?.spawnId?.trim()) params.set("spawn_id", opts.spawnId.trim());
  const res = await apiFetch(`${API_BASE}/engagement/twins?${params.toString()}`);
  return readJson<TwinNotesResponse>(res);
}

export async function recordTwinNote(body: {
  asset_id: string;
  kind: "insight" | "question";
  text: string;
  source_spawn_id?: string | null;
  investigation_id?: string | null;
  source_ref_ids?: string[];
  include_html?: boolean;
}): Promise<TwinNotesResponse> {
  const res = await apiFetch(`${API_BASE}/engagement/twins`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      asset_id: body.asset_id,
      kind: body.kind,
      text: body.text,
      source_spawn_id: body.source_spawn_id ?? null,
      investigation_id: body.investigation_id ?? null,
      source_ref_ids: body.source_ref_ids ?? [],
      include_html: body.include_html ?? true,
    }),
  });
  return readJson<TwinNotesResponse>(res);
}

/** Residual (ch): seed insight + question twins for an asset (offline default). */
export async function seedTwinNotes(body: {
  asset_id: string;
  title?: string;
  body_text?: string;
  source_spawn_id?: string | null;
  include_html?: boolean;
  force_offline?: boolean;
  /** Residual (qy): twin write seed source → Antiek-bench by_source. */
  usage_source?: string | null;
  research_tier?: string | null;
  /**
   * Residual (adq): body honesty for recursive suite rewrite feed.
   * When set with usage_source, prevents title-only seeds from being
   * mis-inferred as has_body=true solely because title fills body_text.
   */
  has_body?: boolean | null;
}): Promise<
  TwinNotesResponse & {
    seeded?: boolean;
    live_seed?: boolean;
    seed_skipped?: string | null;
    /** Residual (hh): offline seed path id vs live note_taker. */
    seed_source?: string | null;
    force_offline?: boolean;
    usage_event?: Record<string, unknown> | null;
    usage_event_error?: string | null;
    usage_has_body?: boolean | null;
}
> {
  const res = await apiFetch(`${API_BASE}/engagement/twins/seed`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      asset_id: body.asset_id,
      title: body.title ?? "",
      body_text: body.body_text ?? "",
      source_spawn_id: body.source_spawn_id ?? null,
      include_html: body.include_html ?? true,
      force_offline: Boolean(body.force_offline),
      usage_source: body.usage_source ?? null,
      research_tier: body.research_tier ?? null,
      // Residual (adq): pass explicit body honesty when known.
      has_body: body.has_body === undefined ? null : body.has_body,
    }),
  });
  return readJson(res);
}

export async function seedLiveTwinNotes(body: {
  asset_id: string;
  approval_nonce: string;
  approved_ceiling_cents: number;
  allowed_routes: string[];
}): Promise<{
  state: "live_committed" | "skipped" | "rejected" | string;
  live_seed: boolean;
  seeded: boolean;
  promotion_performed: boolean;
  view_format: "html" | string;
  receipt: Record<string, unknown>;
  twins?: TwinNotesResponse;
}> {
  const res = await apiFetch(`${API_BASE}/engagement/twins/seed-live`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  return readJson(res);
}

/** Promote twins into depth-graph context units for research prompts. */
export type TwinPromoteContextResponse = {
  asset_id: string;
  promoted_count: number;
  context_unit_count: number;
  promoted: Array<{
    twin_note_id: string;
    graph_node_id: string;
    kind: string;
    text: string;
    unit_id?: string;
  }>;
  context_units: Array<{
    unit_id: string;
    twin_note_id: string;
    kind: string;
    text: string;
    graph_node_id?: string;
  }>;
  query?: string | null;
  /** Reserved spawn depth posture, when promotion is scoped to a spawn. */
  research_tier?: "fast" | "deep" | "wrestle" | string | null;
  /** Residual (mq): kinds filter echoed from promote request. */
  kinds?: Array<"insight" | "question"> | string[] | null;
  /** Residual (mx/my): multi-select note_ids echoed for audit honesty. */
  note_ids?: string[] | null;
  /**
   * Residual (ajo/ajn): content-addressed depth-graph honesty on promote payload.
   */
  graph_node_ids?: string[];
  unique_graph_node_count?: number;
  unique_unit_id_count?: number;
  content_addressed_alignment?: boolean;
  view_format: "html" | string;
  product_panel: string;
  source: string;
  notes: string[];
  html?: string | null;
};

export async function promoteTwinsToContext(body: {
  asset_id: string;
  query?: string | null;
  investigation_id?: string | null;
  include_html?: boolean;
  /** Residual (mq): selective promote — insight and/or question. */
  kinds?: Array<"insight" | "question"> | null;
  /** Residual (mx): multi-select by twin note_id. */
  note_ids?: string[] | null;
}): Promise<TwinPromoteContextResponse> {
  const res = await apiFetch(`${API_BASE}/engagement/twins/promote-context`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      asset_id: body.asset_id,
      query: body.query ?? null,
      investigation_id: body.investigation_id ?? null,
      include_html: body.include_html ?? true,
      kinds: body.kinds ?? null,
      note_ids: body.note_ids ?? null,
    }),
  });
  return readJson<TwinPromoteContextResponse>(res);
}

/** Search twin notes + source refs for research context. */
export type ContextSearchResponse = {
  query: string;
  asset_id?: string | null;
  spawn_id?: string | null;
  hit_count: number;
  hits: Array<{
    kind: string;
    id: string;
    asset_id?: string | null;
    text: string;
    source: string;
  }>;
  /** Residual (kg): spawn research_tier when search scoped to a spawn. */
  research_tier?: "fast" | "deep" | "wrestle" | string | null;
  view_format: "html" | string;
  product_panel: string;
  source: string;
  notes: string[];
  html?: string | null;
};

export async function searchEngagementContext(body: {
  query: string;
  asset_id?: string | null;
  spawn_id?: string | null;
  include_html?: boolean;
  limit?: number;
}): Promise<ContextSearchResponse> {
  const res = await apiFetch(`${API_BASE}/engagement/context-search`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      query: body.query,
      asset_id: body.asset_id ?? null,
      spawn_id: body.spawn_id ?? null,
      include_html: body.include_html ?? true,
      limit: body.limit ?? 50,
    }),
  });
  return readJson<ContextSearchResponse>(res);
}

export async function openEngagementSession(
  body: SessionOpenRequest,
): Promise<SessionOpenResponse> {
  const res = await apiFetch(`${API_BASE}/engagement/sessions/open`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  return readJson<SessionOpenResponse>(res);
}

export async function completeSessionFlywheel(body: {
  session_id: string;
  output_text: string;
  insights?: string[];
  questions?: string[];
  query?: string | null;
  record_twins?: boolean;
  include_twin_promote?: boolean;
}): Promise<SessionFlywheelResponse> {
  const res = await apiFetch(`${API_BASE}/engagement/sessions/complete-flywheel`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  return readJson<SessionFlywheelResponse>(res);
}
