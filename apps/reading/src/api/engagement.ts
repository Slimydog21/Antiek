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
  view_format: "html";
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
};

export type SessionFlywheelResponse = {
  session_id: string;
  spawn_id: string;
  status: string;
  context: ResearchContextPack & { twin_count?: number; ref_count?: number };
  view_format: "html";
  prompt_block: string;
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
): Promise<{ spawn_id: string; source_references: SourceReference[]; view_format: "html" }> {
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
  view_format: "html" | string;
  product_panel: string;
  source: string;
  notes: string[];
  html?: string | null;
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

/** Hydrate arxiv/substack/url into HTML-first engagement asset. */
export type HydrateRefResponse = {
  asset_id: string;
  ref: SourceReference;
  title: string;
  body_text: string;
  fetched: boolean;
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
  view_format: "html" | string;
  product_panel: string;
  source: string;
  messages?: string[];
  html?: string | null;
};

export async function fetchTwinNotes(
  assetId: string,
  opts?: { includeHtml?: boolean },
): Promise<TwinNotesResponse> {
  const q = opts?.includeHtml ? "?include_html=true" : "";
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
