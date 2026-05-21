// SPR-11 / M1 — Per-theme notebook API client.
//
// The actual endpoints are FastAPI Python (interfaces/research/api/);
// this is the TypeScript client the reading surface imports. Polyglot-
// seam pattern: the call shape lives in one place so the surface
// doesn't string-format URLs (same convention as
// apps/reading/api/notebooks/by-doc.ts).
//
// Endpoints (paired with services/notebooks/theme_persistence.py):
//
//   GET    /api/themes
//      → list all themes for the authenticated user (sort
//        last-edited-desc by default; ?sort=title_asc for the
//        title-sort toggle).
//
//   GET    /api/themes/by-slug/{slug}
//      → load one theme + its blocks. Used by /wrestle/themes/<slug>.
//
//   POST   /api/themes
//      → create a new theme. Body: { title, cover_snippet? }.
//
//   POST   /api/themes/{theme_id}/promote
//      → promote one or more Tier-2 blocks into this theme. Body:
//        { source_block_ids: string[] }.
//
//   POST   /api/themes/{theme_id}/prose
//      → author a new prose block inside the theme. Body:
//        { content_json: Record<string, unknown>,
//          after_sort_order?: number }.
//
//   POST   /api/themes/{theme_id}/reorder
//      → assign sort_order = 1, 2, ... to the supplied order. Body:
//        { ordered_theme_block_ids: string[] }.
//
//   DELETE /api/themes/{theme_id}/blocks/{theme_block_id}
//      → remove a theme block (source Tier-2 block untouched).
//
//   POST   /api/themes/{theme_id}/blocks/{theme_block_id}/dismiss
//      → dismiss a stale placeholder.
//
//   GET    /api/themes/by-source-block/{source_block_id}
//      → reverse lookup; used by the per-doc surface to show the
//        "in theme: <title>" indicator.
//
// Same client-degrades-on-404 convention as by-doc.ts: until the
// FastAPI route handlers land, the surface renders a friendly empty/
// banner state instead of crashing.

/** Closed mirror of services/notebooks/blocks.py::BlockType plus
 *  'prose' (Tier-3 framing). Hand-kept in sync with the Python. */
export const ThemeBlockType = {
  HIGHLIGHT_CARD: "highlight_card",
  VOICE_BLOCK: "voice_block",
  AI_QA: "ai_qa",
  CITE_LINK: "cite_link",
  CROSS_DOC_JUMP: "cross_doc_jump",
  PROSE: "prose",
} as const;
export type ThemeBlockTypeValue =
  (typeof ThemeBlockType)[keyof typeof ThemeBlockType];

/** One theme_blocks row as the API returns it. */
export interface ThemeBlock {
  theme_block_id: string;
  theme_id: string;
  source_block_id: string | null;
  source_notebook_id: string | null;
  source_document_id: string | null;
  block_type: ThemeBlockTypeValue;
  content_json: Record<string, unknown>;
  sort_order: number;
  dismissed_at: string | null;
  created_at: string;
  /** True when the source Tier-2 block was deleted (its document
   *  was removed). Renderer shows a stale placeholder with the
   *  cached content_json. */
  is_stale: boolean;
  /** Optional back-link metadata for the rendering layer.
   *  Populated by the server's JOIN; missing on stale rows. */
  source_notebook_title: string | null;
  source_document_title: string | null;
}

/** Full theme envelope. */
export interface ThemeResponse {
  theme_id: string;
  user_id: string;
  slug: string;
  title: string;
  cover_snippet: string | null;
  created_at: string;
  last_edited_at: string;
  blocks: ThemeBlock[];
}

/** Index card payload — does NOT include the full block list. */
export interface ThemeCard {
  theme_id: string;
  slug: string;
  title: string;
  cover_snippet: string | null;
  block_count: number;
  last_edited_at: string;
  created_at: string;
}

/** API base resolution mirrors apps/reading/api/notebooks/by-doc.ts. */
function apiBase(): string {
  const env = (import.meta as { env?: { VITE_ANTIEK_API_BASE?: string } }).env;
  return (env?.VITE_ANTIEK_API_BASE || "").replace(/\/+$/, "");
}

export class ThemeApiError extends Error {
  status: number;
  detail: unknown;
  constructor(message: string, status: number, detail?: unknown) {
    super(message);
    this.name = "ThemeApiError";
    this.status = status;
    this.detail = detail;
  }
}

async function _request<T>(
  path: string,
  init?: RequestInit,
): Promise<T> {
  const res = await fetch(`${apiBase()}${path}`, {
    ...init,
    headers: {
      Accept: "application/json",
      ...(init?.body ? { "Content-Type": "application/json" } : {}),
      ...(init?.headers ?? {}),
    },
    credentials: "include",
  });
  if (!res.ok) {
    const detail = await res.json().catch(() => ({}));
    throw new ThemeApiError(
      `${init?.method ?? "GET"} ${path} failed: HTTP ${res.status}`,
      res.status,
      detail,
    );
  }
  return res.json();
}

/** GET /api/themes — list cards for the index page. */
export async function listThemes(
  options?: { sort?: "last_edited_desc" | "title_asc" },
): Promise<ThemeCard[]> {
  const sort = options?.sort ?? "last_edited_desc";
  return _request<ThemeCard[]>(`/api/themes?sort=${encodeURIComponent(sort)}`);
}

/** GET /api/themes/by-slug/<slug>. */
export async function getThemeBySlug(slug: string): Promise<ThemeResponse> {
  return _request<ThemeResponse>(
    `/api/themes/by-slug/${encodeURIComponent(slug)}`,
  );
}

/** POST /api/themes — create. The server auto-allocates the slug. */
export async function createTheme(body: {
  title: string;
  cover_snippet?: string | null;
}): Promise<ThemeResponse> {
  return _request<ThemeResponse>(`/api/themes`, {
    method: "POST",
    body: JSON.stringify(body),
  });
}

/** POST /api/themes/<id>/promote — multi-select promote. */
export async function promoteBlocksToTheme(
  themeId: string,
  body: { source_block_ids: string[] },
): Promise<ThemeBlock[]> {
  return _request<ThemeBlock[]>(
    `/api/themes/${encodeURIComponent(themeId)}/promote`,
    { method: "POST", body: JSON.stringify(body) },
  );
}

/** POST /api/themes/<id>/prose — add an inline framing block. */
export async function addProseBlock(
  themeId: string,
  body: {
    content_json: Record<string, unknown>;
    after_sort_order?: number | null;
  },
): Promise<ThemeBlock> {
  return _request<ThemeBlock>(
    `/api/themes/${encodeURIComponent(themeId)}/prose`,
    { method: "POST", body: JSON.stringify(body) },
  );
}

/** POST /api/themes/<id>/reorder — drag-to-reorder. */
export async function reorderThemeBlocks(
  themeId: string,
  body: { ordered_theme_block_ids: string[] },
): Promise<ThemeResponse> {
  return _request<ThemeResponse>(
    `/api/themes/${encodeURIComponent(themeId)}/reorder`,
    { method: "POST", body: JSON.stringify(body) },
  );
}

/** DELETE /api/themes/<id>/blocks/<theme_block_id>. */
export async function removeThemeBlock(
  themeId: string,
  themeBlockId: string,
): Promise<void> {
  await _request<unknown>(
    `/api/themes/${encodeURIComponent(themeId)}/blocks/${encodeURIComponent(
      themeBlockId,
    )}`,
    { method: "DELETE" },
  );
}

/** POST /api/themes/<id>/blocks/<theme_block_id>/dismiss — for stale. */
export async function dismissStaleBlock(
  themeId: string,
  themeBlockId: string,
): Promise<void> {
  await _request<unknown>(
    `/api/themes/${encodeURIComponent(themeId)}/blocks/${encodeURIComponent(
      themeBlockId,
    )}/dismiss`,
    { method: "POST", body: JSON.stringify({}) },
  );
}

/** GET /api/themes/by-source-block/<id> — reverse lookup for the
 *  "in theme: <title>" indicator on a promoted Tier-2 block. */
export async function listThemesForSourceBlock(
  sourceBlockId: string,
): Promise<ThemeCard[]> {
  return _request<ThemeCard[]>(
    `/api/themes/by-source-block/${encodeURIComponent(sourceBlockId)}`,
  );
}
