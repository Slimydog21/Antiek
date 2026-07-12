/**
 * Engagement spine API client — mirrors interfaces/research/api/engagement_routes.py
 *
 * Spawn deep-research from highlights, attach arxiv/substack refs, assemble
 * research context packs, collective multi-spawn merge, session flywheel.
 * Process-local store on the server (MVP).
 */

import { API_BASE, apiFetch } from "../lib/api";
import type {
  CollectiveResearchUnit,
  ResearchContextPack,
  SourceReference,
} from "../workspace/researchContextPack";

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
};

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
  owner_id: string;
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
  source_session_ids?: string[];
  collective_preview_sha256?: string;
  html?: string;
};

export type ConfirmedCollectiveUnit = {
  collective_unit_id: string;
  preview_sha256: string;
  state: "confirmed";
  html: string;
  view_format: "html";
  material: { source_session_ids: string[]; unit: CollectiveResponse; prompt_block: string };
  lineage?: CollectiveLineageEdge[];
  lineage_next_cursor?: string | null;
};

export type CollectiveLineageEdge = {
  edge_id: string;
  parent_collective_id: string;
  parent_preview_sha256: string;
  child_kind: "research_session" | "written_analysis";
  child_id: string;
  initial_state: string;
  current_state: string;
  created_at: string;
  research_tier?: string | null;
  model_id?: string | null;
};

export type OwnedCollectiveSummary = {
  collective_unit_id: string;
  preview_sha256: string;
  created_at?: string | null;
  state: "confirmed";
  source_session_ids: string[];
  asset_ids: string[];
  spawn_count: number;
  twin_count: number;
  ref_count: number;
  output_count: number;
  recommended_research_tier?: string | null;
  query?: string | null;
  lineage: CollectiveLineageEdge[];
  lineage_count: number;
  lineage_count_is_lower_bound?: boolean;
  lineage_next_cursor?: string | null;
  view_format: "html";
};

export type OwnedCollectivesPage = {
  owner_id: string;
  collectives: OwnedCollectiveSummary[];
  count: number;
  next_cursor: string | null;
  view_format: "html";
};

export type CollectiveWrittenAnalysis = {
  document_id: string;
  source_collective_id: string;
  source_preview_sha256: string;
  source_session_ids: string[];
  source_spawn_ids: string[];
  html: string;
  view_format: "html";
  state: "draft";
};

export type CollectiveExecutionPreparation = {
  schema_version: 1;
  execution_id: string;
  collective_unit_id: string;
  collective_preview_sha256: string;
  session_id: string;
  spawn_id: string;
  job_id: string;
  state: string;
  operation_state: string;
  recommended_ceiling_cents: number;
  context_binding_sha256: string;
  source_scope: {
    schema_version: 1;
    manifest_sha256: string;
    collective_preview_sha256: string;
    rights_policy_id: string;
    connector_capability_id: string;
    entries: Array<{
      ref_id: string;
      kind: "arxiv" | "substack";
      canonical_url: string;
      external_id: string;
      acquisition_mode: "arxiv_abstract" | "substack_bounded_excerpt";
      rights_use: "metadata_abstract_research" | "operator_authorized_excerpt";
      max_excerpt_bytes: number;
    }>;
    required_count: number;
    acquirable_count: number;
    readiness: "connector_attestation_required" | "ready" | "blocked";
    exclusions: Array<{ ref_id: string; reason_code: string }>;
  };
  receipt_id: string;
  goal_truncated: boolean;
  view_format: "html";
};

export type CollectiveExecutionStatus = {
  schema_version: 1;
  execution_id: string;
  collective_unit_id: string;
  session_id: string;
  spawn_id: string;
  job_id: string;
  state: string;
  phase: string;
  operation_state: string;
  session_status: string;
  deposit_state: string;
  deposit_document_id: string | null;
  context_ready: boolean;
  provider_calls_started: boolean;
  status_href: string;
  view_format: "html";
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

export class EngagementApiError extends Error {
  constructor(
    readonly status: number,
    message: string,
  ) {
    super(message);
    this.name = "EngagementApiError";
  }
}

async function readJson<T>(res: Response): Promise<T> {
  if (!res.ok) {
    const text = await res.text();
    throw new EngagementApiError(
      res.status,
      `engagement API ${res.status}: ${text.slice(0, 200)}`,
    );
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
  live_env_flag: string;
  use_dispatch_env_flag: string;
  notes: string[];
  html?: string | null;
};

export async function fetchTwinSeedLiveStatus(): Promise<TwinSeedLiveStatusResponse> {
  const res = await apiFetch(`${API_BASE}/engagement/twin-seed-live-status`);
  return readJson<TwinSeedLiveStatusResponse>(res);
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
  /** Residual (air): true when insights and source refs both non-empty. */
  chain_complete?: boolean;
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
  if (opts?.includeHtml) params.set("include_html", "true");
  // Residual (le): optional spawn_id scopes research_tier on list payload.
  if (opts?.spawnId?.trim()) params.set("spawn_id", opts.spawnId.trim());
  const q = params.toString() ? `?${params.toString()}` : "";
  const res = await apiFetch(
    `${API_BASE}/engagement/twins/${encodeURIComponent(assetId)}${q}`,
  );
  return readJson<TwinNotesResponse>(res);
}

export async function recordTwinNote(body: {
  asset_id: string;
  kind: "insight" | "question";
  text: string;
  source_spawn_id?: string | null;
  investigation_id?: string | null;
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
  promotion_preview_sha256?: string;
  promotion_receipt_id?: string;
  promotion_receipt_state?: "applied" | string;
  twin_context_mode?: "preview_non_mutating" | "confirmed_mutating" | string;
  graph_write?: boolean;
  owner_graph_scope?: "physically_isolated" | "operator_canonical" | string;
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

export type SessionLifecycleResponse = SessionOpenResponse & {
  html?: string;
};

export type SessionListResponse = {
  parent_asset_id: string;
  owner_id: string;
  sessions: SessionLifecycleResponse[];
  count: number;
  view_format: "html";
};

export type OwnedSessionListResponse = {
  owner_id: string;
  sessions: SessionLifecycleResponse[];
  count: number;
  next_cursor: string | null;
  view_format: "html";
};

export async function fetchEngagementSession(
  sessionId: string,
  includeHtml = true,
): Promise<SessionLifecycleResponse> {
  const params = includeHtml ? "?include_html=true" : "?include_html=false";
  const res = await apiFetch(
    `${API_BASE}/engagement/sessions/${encodeURIComponent(sessionId)}${params}`,
  );
  return readJson<SessionLifecycleResponse>(res);
}

export async function listEngagementSessions(
  parentAssetId: string,
  includeHtml = false,
): Promise<SessionListResponse> {
  const params = includeHtml ? "?include_html=true" : "?include_html=false";
  const res = await apiFetch(
    `${API_BASE}/engagement/sessions/asset/${encodeURIComponent(parentAssetId)}${params}`,
  );
  return readJson<SessionListResponse>(res);
}

export async function listOwnedEngagementSessions(options: {
  cursor?: string | null;
  limit?: number;
  includeHtml?: boolean;
} = {}): Promise<OwnedSessionListResponse> {
  const params = new URLSearchParams();
  params.set("limit", String(options.limit ?? 100));
  params.set("include_html", String(options.includeHtml ?? false));
  if (options.cursor) params.set("cursor", options.cursor);
  const res = await apiFetch(`${API_BASE}/engagement/sessions/owned?${params}`);
  return readJson<OwnedSessionListResponse>(res);
}

export async function updateEngagementSessionView(body: {
  session_id: string;
  mode: "floating" | "full";
  expected_mode?: "floating" | "full" | null;
}): Promise<SessionLifecycleResponse> {
  const res = await apiFetch(
    `${API_BASE}/engagement/sessions/${encodeURIComponent(body.session_id)}/view`,
    {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        mode: body.mode,
        expected_mode: body.expected_mode ?? null,
      }),
    },
  );
  return readJson<SessionLifecycleResponse>(res);
}

export type SessionMergeResponse = {
  mode: MergeMode;
  parent_asset_id: string;
  document_id: string;
  source_spawn_ids: string[];
  source_session_ids: string[];
  sections_merged: number;
  document_sha256: string;
  parent_revision_sha256: string;
  result_parent_sha256: string;
  draft_leaves_parent: boolean;
  view_format: "html";
  merge_receipt_id?: string;
  merge_receipt_state?: "applied";
  html?: string;
};

export async function mergeEngagementSessions(body: {
  parent_asset_id: string;
  session_ids: string[];
  mode?: MergeMode;
  confirm_parent_write?: boolean;
  expected_parent_sha256?: string | null;
  idempotency_key?: string | null;
  include_html?: boolean;
}): Promise<SessionMergeResponse> {
  const res = await apiFetch(`${API_BASE}/engagement/sessions/merge`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      parent_asset_id: body.parent_asset_id,
      session_ids: body.session_ids,
      mode: body.mode ?? "draft_combined",
      confirm_parent_write: Boolean(body.confirm_parent_write),
      expected_parent_sha256: body.expected_parent_sha256 ?? null,
      idempotency_key: body.idempotency_key ?? null,
      include_html: body.include_html ?? true,
    }),
  });
  return readJson<SessionMergeResponse>(res);
}

export async function attachSessionReferences(body: {
  session_id: string;
  references: string[];
  hydrate?: boolean;
  seed_twins?: boolean;
  include_html?: boolean;
}): Promise<{
  session_id: string;
  spawn_id: string;
  source_references: SourceReference[];
  hydrated_assets: HydrateRefResponse[];
  research_tier?: string | null;
  view_format: "html";
}> {
  const res = await apiFetch(
    `${API_BASE}/engagement/sessions/${encodeURIComponent(body.session_id)}/references`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        references: body.references,
        hydrate: body.hydrate ?? true,
        seed_twins: body.seed_twins ?? true,
        include_html: body.include_html ?? true,
      }),
    },
  );
  return readJson(res);
}

export async function fetchSessionProgress(
  sessionId: string,
  opts?: { includeHtml?: boolean },
): Promise<ResearchProgressResponse> {
  const q = opts?.includeHtml ? "?include_html=true" : "";
  const res = await apiFetch(
    `${API_BASE}/engagement/sessions/${encodeURIComponent(sessionId)}/progress${q}`,
  );
  return readJson<ResearchProgressResponse>(res);
}

export async function seedSessionProgress(
  sessionId: string,
  opts?: { includeHtml?: boolean },
): Promise<ResearchProgressResponse> {
  const q = opts?.includeHtml ? "?include_html=true" : "";
  const res = await apiFetch(
    `${API_BASE}/engagement/sessions/${encodeURIComponent(sessionId)}/progress/seed${q}`,
    { method: "POST" },
  );
  return readJson<ResearchProgressResponse>(res);
}

export async function fetchSessionEvidence(
  sessionId: string,
  includeHtml = true,
): Promise<EvidencePackResponse> {
  const res = await apiFetch(
    `${API_BASE}/engagement/sessions/${encodeURIComponent(sessionId)}/evidence?include_html=${String(includeHtml)}`,
  );
  return readJson<EvidencePackResponse>(res);
}

export async function fetchSessionTwins(
  sessionId: string,
  includeHtml = true,
): Promise<TwinNotesResponse> {
  const res = await apiFetch(
    `${API_BASE}/engagement/sessions/${encodeURIComponent(sessionId)}/twins?include_html=${String(includeHtml)}`,
  );
  return readJson<TwinNotesResponse>(res);
}

export async function recordSessionTwin(body: {
  session_id: string;
  kind: "insight" | "question";
  text: string;
  include_html?: boolean;
}): Promise<TwinNotesResponse> {
  const res = await apiFetch(
    `${API_BASE}/engagement/sessions/${encodeURIComponent(body.session_id)}/twins`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        kind: body.kind,
        text: body.text,
        include_html: body.include_html ?? true,
      }),
    },
  );
  return readJson<TwinNotesResponse>(res);
}

export async function seedSessionTwins(body: {
  session_id: string;
  title?: string;
  body_text?: string;
  include_html?: boolean;
  force_offline?: boolean;
}): Promise<
  TwinNotesResponse & {
    seeded?: boolean;
    seed_skipped?: string | null;
    live_seed?: boolean;
    seed_source?: string | null;
  }
> {
  const res = await apiFetch(
    `${API_BASE}/engagement/sessions/${encodeURIComponent(body.session_id)}/twins/seed`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        title: body.title ?? "",
        body_text: body.body_text ?? "",
        include_html: body.include_html ?? true,
        force_offline: body.force_offline ?? false,
      }),
    },
  );
  return readJson(res);
}

export async function previewSessionTwins(body: {
  session_id: string;
  query?: string | null;
  kinds?: Array<"insight" | "question"> | null;
  note_ids?: string[] | null;
  include_html?: boolean;
}): Promise<TwinPromoteContextResponse & { twin_context_mode: "preview_non_mutating" }> {
  const res = await apiFetch(
    `${API_BASE}/engagement/sessions/${encodeURIComponent(body.session_id)}/twins/promote-preview`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        query: body.query ?? null,
        kinds: body.kinds ?? null,
        note_ids: body.note_ids ?? null,
        include_html: body.include_html ?? true,
      }),
    },
  );
  return readJson(res);
}

export async function confirmSessionTwins(body: {
  session_id: string;
  expected_preview_sha256: string;
  idempotency_key: string;
  query?: string | null;
  kinds?: Array<"insight" | "question"> | null;
  note_ids?: string[] | null;
  include_html?: boolean;
}): Promise<
  TwinPromoteContextResponse & {
    twin_context_mode: "confirmed_mutating";
    graph_write: true;
    promotion_receipt_id: string;
    promotion_receipt_state: "applied";
    owner_graph_scope: "physically_isolated" | "operator_canonical";
  }
> {
  const res = await apiFetch(
    `${API_BASE}/engagement/sessions/${encodeURIComponent(body.session_id)}/twins/promote-confirm`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        expected_preview_sha256: body.expected_preview_sha256,
        idempotency_key: body.idempotency_key,
        query: body.query ?? null,
        kinds: body.kinds ?? null,
        note_ids: body.note_ids ?? null,
        include_html: body.include_html ?? true,
      }),
    },
  );
  return readJson(res);
}

export async function searchSessionContext(body: {
  session_id: string;
  query: string;
  include_html?: boolean;
  limit?: number;
}): Promise<ContextSearchResponse> {
  const res = await apiFetch(
    `${API_BASE}/engagement/sessions/${encodeURIComponent(body.session_id)}/context-search`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        query: body.query,
        include_html: body.include_html ?? true,
        limit: body.limit ?? 50,
      }),
    },
  );
  return readJson<ContextSearchResponse>(res);
}

export async function fetchSessionResearchContext(body: {
  session_id: string;
  query?: string | null;
  include_twin_preview?: boolean;
  include_prompt_block?: boolean;
  include_html?: boolean;
}): Promise<ResearchContextResponse & { twin_context_mode: string; html?: string }> {
  const res = await apiFetch(`${API_BASE}/engagement/sessions/context`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      session_id: body.session_id,
      query: body.query ?? null,
      include_twin_preview: body.include_twin_preview ?? false,
      include_prompt_block: body.include_prompt_block ?? true,
      include_html: body.include_html ?? true,
    }),
  });
  return readJson(res);
}

export async function fetchSessionsCollective(body: {
  session_ids: string[];
  query?: string | null;
  include_twin_preview?: boolean;
  allow_cross_asset?: boolean;
  include_prompt_block?: boolean;
  include_html?: boolean;
}): Promise<CollectiveResponse & { source_session_ids: string[]; twin_context_mode: string }> {
  const res = await apiFetch(`${API_BASE}/engagement/sessions/collective`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      session_ids: body.session_ids,
      query: body.query ?? null,
      include_twin_preview: body.include_twin_preview ?? false,
      allow_cross_asset: body.allow_cross_asset ?? false,
      include_prompt_block: body.include_prompt_block ?? true,
      include_html: body.include_html ?? true,
    }),
  });
  return readJson(res);
}

export async function confirmSessionsCollective(body: {
  session_ids: string[];
  expected_preview_sha256: string;
  idempotency_key: string;
  query?: string | null;
  include_twin_preview?: boolean;
  allow_cross_asset?: boolean;
}): Promise<ConfirmedCollectiveUnit> {
  const res = await apiFetch(`${API_BASE}/engagement/sessions/collective/confirm`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      ...body,
      query: body.query ?? null,
      include_twin_preview: body.include_twin_preview ?? false,
      allow_cross_asset: body.allow_cross_asset ?? false,
      include_prompt_block: true,
      include_html: true,
    }),
  });
  return readJson(res);
}

export async function launchCollectiveResearch(
  unitId: string,
  body: {
    idempotency_key: string;
    anchor_asset_id: string;
    view_mode?: "floating" | "full";
    model_id?: string | null;
    research_tier?: "fast" | "deep" | "wrestle" | null;
  },
): Promise<SessionOpenResponse> {
  const res = await apiFetch(
    `${API_BASE}/engagement/sessions/collective/${encodeURIComponent(unitId)}/launch-research`,
    { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) },
  );
  return readJson(res);
}

export async function prepareCollectiveExecution(
  unitId: string,
  body: {
    session_id: string;
    expected_preview_sha256: string;
    idempotency_key: string;
    duration_minutes: number;
    model_id?: string | null;
    research_tier?: "fast" | "deep" | "wrestle" | null;
    fanout_depth?: number;
  },
): Promise<CollectiveExecutionPreparation> {
  const res = await apiFetch(
    `${API_BASE}/engagement/sessions/collective/${encodeURIComponent(unitId)}/execution/prepare`,
    { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) },
  );
  return readJson(res);
}

export async function getCollectiveExecutionStatus(
  unitId: string,
  executionId: string,
): Promise<CollectiveExecutionStatus> {
  const res = await apiFetch(
    `${API_BASE}/engagement/sessions/collective/${encodeURIComponent(unitId)}/execution/${encodeURIComponent(executionId)}`,
    { cache: "no-store" },
  );
  return readJson(res);
}

export async function createCollectiveWrittenAnalysis(
  unitId: string,
  idempotencyKey: string,
): Promise<CollectiveWrittenAnalysis> {
  const res = await apiFetch(
    `${API_BASE}/engagement/sessions/collective/${encodeURIComponent(unitId)}/written-analysis`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ idempotency_key: idempotencyKey }),
    },
  );
  return readJson(res);
}

export async function listOwnedCollectiveUnits(options: {
  limit?: number;
  cursor?: string | null;
} = {}): Promise<OwnedCollectivesPage> {
  const query = new URLSearchParams();
  query.set("limit", String(options.limit ?? 5));
  if (options.cursor) query.set("cursor", options.cursor);
  const res = await apiFetch(
    `${API_BASE}/engagement/sessions/collective/owned?${query.toString()}`,
  );
  return readJson(res);
}

export async function getOwnedCollectiveUnit(
  unitId: string,
): Promise<ConfirmedCollectiveUnit> {
  const res = await apiFetch(
    `${API_BASE}/engagement/sessions/collective/${encodeURIComponent(unitId)}`,
  );
  return readJson(res);
}

export async function getOwnedCollectiveWrittenAnalysis(
  unitId: string,
  documentId: string,
): Promise<CollectiveWrittenAnalysis> {
  const res = await apiFetch(
    `${API_BASE}/engagement/sessions/collective/${encodeURIComponent(unitId)}/written-analysis/${encodeURIComponent(documentId)}`,
  );
  return readJson(res);
}
