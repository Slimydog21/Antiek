import { API_BASE, ApiError, apiFetch } from "../lib/api";

export type SessionOpenRequest = {
  asset_id: string;
  selection_text: string;
  region_id?: string | null;
  page?: number | null;
  goal_hint?: string | null;
  model_id?: string | null;
  force_new?: boolean;
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
  region_id?: string | null;
  goal?: string;
  view_format: "html";
};

export type TwinNote = {
  note_id: string;
  asset_id: string;
  kind: "insight" | "question";
  text: string;
  source_spawn_id?: string | null;
  investigation_id?: string | null;
};

export type TwinNotesResponse = {
  asset_id: string;
  note_count: number;
  insight_count: number;
  question_count: number;
  notes: TwinNote[];
  view_format: "html";
  html?: string | null;
};

export type MergeMode = "into_parent" | "draft_combined";

export type MergeProductResponse = {
  mode: MergeMode;
  parent_asset_id: string;
  document_id: string;
  source_spawn_ids: string[];
  sections_merged: number;
  draft_leaves_parent: boolean;
  parent_document_id: string;
  view_format: "html";
  product_panel: string;
  source: string;
  notes: string[];
  html?: string | null;
};

async function readJson<T>(response: Response): Promise<T> {
  if (!response.ok) {
    const detail = await response.text();
    throw new ApiError(
      `engagement API ${response.status}: ${detail.slice(0, 200)}`,
      response.status,
      detail,
    );
  }
  return (await response.json()) as T;
}

export async function openEngagementSession(
  body: SessionOpenRequest,
): Promise<SessionOpenResponse> {
  const response = await apiFetch(`${API_BASE}/engagement/sessions/open`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  return readJson<SessionOpenResponse>(response);
}

export async function fetchTwinNotes(
  assetId: string,
  options: { includeHtml?: boolean } = {},
): Promise<TwinNotesResponse> {
  const params = new URLSearchParams({
    include_html: String(options.includeHtml ?? true),
  });
  const response = await apiFetch(
    `${API_BASE}/engagement/twins/${encodeURIComponent(assetId)}?${params}`,
  );
  return readJson<TwinNotesResponse>(response);
}

export async function recordTwinNote(body: {
  asset_id: string;
  kind: "insight" | "question";
  text: string;
  source_spawn_id?: string | null;
  investigation_id?: string | null;
  include_html?: boolean;
}): Promise<TwinNotesResponse> {
  const response = await apiFetch(`${API_BASE}/engagement/twins`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  return readJson<TwinNotesResponse>(response);
}

export async function mergeSpawnOutputs(body: {
  parent_asset_id: string;
  spawn_ids: string[];
  mode?: MergeMode;
  parent_title?: string | null;
  parent_body?: string | null;
  include_html?: boolean;
}): Promise<MergeProductResponse> {
  const response = await apiFetch(`${API_BASE}/engagement/merge`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      ...body,
      mode: body.mode ?? "draft_combined",
      include_html: body.include_html ?? true,
    }),
  });
  return readJson<MergeProductResponse>(response);
}
