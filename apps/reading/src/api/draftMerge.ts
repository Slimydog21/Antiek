/**
 * Draft-merge client (PR #800 contract).
 *
 * POST /twins/draft-merge
 *
 * Builds a *provisional* combined HTML draft from parent HTML + selected
 * same-parent twins. Never claims final parent merge. Cross-parent → 409.
 */

import { API_BASE, apiFetch } from "../lib/api";

export interface DraftMergeRequest {
  parent_asset_id: string;
  parent_html?: string;
  twin_ids: string[];
  title?: string;
}

export interface DraftMergeResult {
  draft_id: string;
  parent_asset_id: string;
  provisional: boolean;
  html: string;
  twin_ids: string[];
  insight_count: number;
  question_count: number;
  created_at: number;
  notes: string[];
}

export class DraftMergeHttpError extends Error {
  readonly status: number;
  readonly code: string | null;
  readonly body: string;

  constructor(status: number, body: string, code: string | null = null) {
    super(`draft-merge API ${status}: ${body.slice(0, 200)}`);
    this.name = "DraftMergeHttpError";
    this.status = status;
    this.code = code;
    this.body = body;
  }
}

function parseErrorCode(body: string): string | null {
  try {
    const parsed = JSON.parse(body) as {
      detail?: { code?: string } | string;
    };
    if (parsed.detail && typeof parsed.detail === "object" && parsed.detail.code) {
      return String(parsed.detail.code);
    }
  } catch {
    /* not JSON */
  }
  return null;
}

async function readOkBody(res: Response): Promise<unknown> {
  if (!res.ok) {
    const text = await res.text();
    throw new DraftMergeHttpError(res.status, text, parseErrorCode(text));
  }
  return res.json() as Promise<unknown>;
}

/**
 * Fail closed when the server returns a 200 that is not a provisional draft.
 * Draft-merge must never surface a non-provisional body as success.
 */
export function parseDraftMergeResult(body: unknown): DraftMergeResult {
  if (!body || typeof body !== "object") {
    throw new Error("draft-merge response must be an object");
  }
  const o = body as Record<string, unknown>;
  if (o.provisional !== true) {
    throw new Error(
      "draft-merge response rejected: provisional must be true (not final merge)",
    );
  }
  if (typeof o.draft_id !== "string" || !o.draft_id.trim()) {
    throw new Error("draft-merge response missing draft_id");
  }
  if (typeof o.parent_asset_id !== "string" || !o.parent_asset_id.trim()) {
    throw new Error("draft-merge response missing parent_asset_id");
  }
  if (typeof o.html !== "string") {
    throw new Error("draft-merge response missing html string");
  }
  if (!Array.isArray(o.twin_ids)) {
    throw new Error("draft-merge response missing twin_ids array");
  }
  return {
    draft_id: o.draft_id,
    parent_asset_id: o.parent_asset_id,
    provisional: true,
    html: o.html,
    twin_ids: o.twin_ids.map((t) => String(t)),
    insight_count: Number(o.insight_count ?? 0),
    question_count: Number(o.question_count ?? 0),
    created_at: Number(o.created_at ?? 0),
    notes: Array.isArray(o.notes) ? o.notes.map((n) => String(n)) : [],
  };
}

export async function postDraftMerge(
  req: DraftMergeRequest,
): Promise<DraftMergeResult> {
  const parent = (req.parent_asset_id || "").trim();
  if (!parent) {
    throw new Error("parent_asset_id must be non-empty");
  }
  const twinIds = (req.twin_ids || []).map((t) => String(t).trim()).filter(Boolean);
  if (twinIds.length === 0) {
    throw new Error("twin_ids must contain at least one id");
  }

  const res = await apiFetch(`${API_BASE}/twins/draft-merge`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      parent_asset_id: parent,
      parent_html: req.parent_html ?? "",
      twin_ids: twinIds,
      title: req.title ?? "Draft merge",
    }),
  });
  const raw = await readOkBody(res);
  return parseDraftMergeResult(raw);
}

/** Pure display helpers — unit-tested without network. */

export function formatProvisional(value: boolean | null | undefined): string {
  if (value === true) return "PROVISIONAL — not merged into parent";
  if (value === false) return "not provisional (unexpected for draft-merge)";
  return "unknown provisional flag";
}

export function formatTwinCount(ids: string[] | null | undefined): string {
  if (!ids || ids.length === 0) return "0 twins";
  return `${ids.length} twin${ids.length === 1 ? "" : "s"}`;
}

export function isCrossParentRejection(err: unknown): boolean {
  if (!(err instanceof DraftMergeHttpError)) return false;
  if (err.status === 409) return true;
  return err.code === "cross_parent_draft_merge_rejected";
}
