/**
 * Twin collective pack client (PR #794 contract).
 *
 * POST /twins/collective
 *
 * Builds a plain-text pack from multiple twin notes so the operator can
 * prompt them as one cohesive deep-research unit. Cross-parent twins are
 * allowed (unlike draft-merge). This module does not dispatch models.
 */

import { API_BASE, apiFetch } from "../lib/api";

export interface CollectivePackRequest {
  twin_ids: string[];
  instruction?: string;
}

export interface CollectivePackResult {
  instruction: string;
  twin_ids: string[];
  parent_asset_ids: string[];
  pack_text: string;
  insight_count: number;
  question_count: number;
  notes: string[];
}

export class CollectivePackHttpError extends Error {
  readonly status: number;
  readonly body: string;

  constructor(status: number, body: string) {
    super(`twin-collective API ${status}: ${body.slice(0, 200)}`);
    this.name = "CollectivePackHttpError";
    this.status = status;
    this.body = body;
  }
}

async function readOkBody(res: Response): Promise<unknown> {
  if (!res.ok) {
    const text = await res.text();
    throw new CollectivePackHttpError(res.status, text);
  }
  return res.json() as Promise<unknown>;
}

/**
 * Fail closed when pack_text is missing/empty so an empty success body
 * cannot be treated as a usable collective prompt unit.
 */
export function parseCollectivePackResult(body: unknown): CollectivePackResult {
  if (!body || typeof body !== "object") {
    throw new Error("collective pack response must be an object");
  }
  const o = body as Record<string, unknown>;
  if (typeof o.pack_text !== "string" || !o.pack_text.trim()) {
    throw new Error("collective pack response rejected: pack_text must be non-empty");
  }
  if (!Array.isArray(o.twin_ids) || o.twin_ids.length === 0) {
    throw new Error("collective pack response rejected: twin_ids required");
  }
  return {
    instruction: typeof o.instruction === "string" ? o.instruction : "",
    twin_ids: o.twin_ids.map((t) => String(t)),
    parent_asset_ids: Array.isArray(o.parent_asset_ids)
      ? o.parent_asset_ids.map((p) => String(p))
      : [],
    pack_text: o.pack_text,
    insight_count: Number(o.insight_count ?? 0),
    question_count: Number(o.question_count ?? 0),
    notes: Array.isArray(o.notes) ? o.notes.map((n) => String(n)) : [],
  };
}

export async function postCollectivePack(
  req: CollectivePackRequest,
): Promise<CollectivePackResult> {
  const twinIds = (req.twin_ids || []).map((t) => String(t).trim()).filter(Boolean);
  if (twinIds.length === 0) {
    throw new Error("twin_ids must contain at least one id");
  }

  const res = await apiFetch(`${API_BASE}/twins/collective`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      twin_ids: twinIds,
      instruction: req.instruction ?? "",
    }),
  });
  const raw = await readOkBody(res);
  return parseCollectivePackResult(raw);
}

export function formatParentIds(ids: string[] | null | undefined): string {
  if (!ids || ids.length === 0) return "no parents labeled";
  return `${ids.length} parent${ids.length === 1 ? "" : "s"}: ${ids.join(", ")}`;
}

export function formatPackPreview(text: string, max = 240): string {
  const t = (text || "").trim();
  if (!t) return "(empty pack)";
  if (t.length <= max) return t;
  return t.slice(0, max) + "…";
}
