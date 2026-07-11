/**
 * Twin compose analysis client (PR #790 contract).
 *
 * POST /twins/compose
 *
 * Merges same-parent twin notes into a human-viewable HTML analysis draft.
 * Cross-parent compose is rejected by the server (409). This module does not
 * dispatch models, write the graph, or finalize into a parent asset.
 */

import { API_BASE, apiFetch } from "../lib/api";

export interface ComposeAnalysisRequest {
  twin_ids: string[];
  title?: string;
  parent_asset_id?: string | null;
}

export interface ComposeAnalysisResult {
  parent_asset_id: string;
  title: string;
  html: string;
  twin_ids: string[];
  insight_count: number;
  question_count: number;
}

export class ComposeAnalysisHttpError extends Error {
  readonly status: number;
  readonly body: string;

  constructor(status: number, body: string) {
    super(`twin-compose API ${status}: ${body.slice(0, 200)}`);
    this.name = "ComposeAnalysisHttpError";
    this.status = status;
    this.body = body;
  }
}

async function readOkBody(res: Response): Promise<unknown> {
  if (!res.ok) {
    const text = await res.text();
    throw new ComposeAnalysisHttpError(res.status, text);
  }
  return res.json() as Promise<unknown>;
}

/**
 * Fail closed when html is missing/empty so an empty success body cannot be
 * treated as a usable analysis draft (HTML-native surface requires content).
 */
export function parseComposeAnalysisResult(body: unknown): ComposeAnalysisResult {
  if (!body || typeof body !== "object") {
    throw new Error("compose analysis response must be an object");
  }
  const o = body as Record<string, unknown>;
  if (typeof o.html !== "string" || !o.html.trim()) {
    throw new Error("compose analysis response rejected: html must be non-empty");
  }
  if (!Array.isArray(o.twin_ids) || o.twin_ids.length === 0) {
    throw new Error("compose analysis response rejected: twin_ids required");
  }
  if (typeof o.parent_asset_id !== "string" || !o.parent_asset_id.trim()) {
    throw new Error(
      "compose analysis response rejected: parent_asset_id must be non-empty string",
    );
  }
  const insightRaw = o.insight_count;
  const questionRaw = o.question_count;
  if (insightRaw !== undefined && insightRaw !== null) {
    if (typeof insightRaw !== "number" || !Number.isFinite(insightRaw)) {
      throw new Error("compose analysis response rejected: insight_count must be finite number");
    }
  }
  if (questionRaw !== undefined && questionRaw !== null) {
    if (typeof questionRaw !== "number" || !Number.isFinite(questionRaw)) {
      throw new Error(
        "compose analysis response rejected: question_count must be finite number",
      );
    }
  }
  return {
    parent_asset_id: o.parent_asset_id,
    title: typeof o.title === "string" && o.title.trim() ? o.title : "Combined analysis",
    html: o.html,
    twin_ids: o.twin_ids.map((t) => String(t)),
    insight_count: Number(insightRaw ?? 0),
    question_count: Number(questionRaw ?? 0),
  };
}

export async function postComposeAnalysis(
  req: ComposeAnalysisRequest,
): Promise<ComposeAnalysisResult> {
  const twinIds = (req.twin_ids || []).map((t) => String(t).trim()).filter(Boolean);
  if (twinIds.length === 0) {
    throw new Error("twin_ids must contain at least one id");
  }

  const payload: Record<string, unknown> = {
    twin_ids: twinIds,
    title: (req.title ?? "Combined analysis").trim() || "Combined analysis",
  };
  if (req.parent_asset_id != null && String(req.parent_asset_id).trim()) {
    payload.parent_asset_id = String(req.parent_asset_id).trim();
  }

  const res = await apiFetch(`${API_BASE}/twins/compose`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  const raw = await readOkBody(res);
  return parseComposeAnalysisResult(raw);
}

export function formatComposeMeta(result: ComposeAnalysisResult): string {
  return (
    `parent=${result.parent_asset_id}; twins=${result.twin_ids.length}; ` +
    `insights=${result.insight_count}; questions=${result.question_count}`
  );
}

export function formatHtmlPreview(html: string, max = 240): string {
  const t = (html || "").trim();
  if (!t) return "(empty html)";
  if (t.length <= max) return t;
  return t.slice(0, max) + "…";
}
