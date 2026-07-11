/**
 * Twin-notes CRUD client (PR #785 contract).
 *
 * Surfaces for the recursive note-taker substrate:
 * - POST   /twins
 * - GET    /twins/by-parent/{parent_asset_id}
 * - GET    /twins/{twin_id}
 * - POST   /twins/merge
 *
 * No LLM dispatch, no graph writes. Fail closed on malformed documents so
 * empty/invented twins cannot enter the reading surface as success.
 */

import { API_BASE, apiFetch } from "../lib/api";

export interface TwinDocument {
  twin_id: string;
  parent_asset_id: string;
  insights: string[];
  questions: string[];
  source_label: string;
  created_at: number;
  updated_at: number;
  merged_from: string[];
}

export interface RecordTwinRequest {
  parent_asset_id: string;
  insights?: string[];
  questions?: string[];
  source_label?: string;
  twin_id?: string | null;
}

export interface MergeTwinsRequest {
  twin_ids: string[];
  parent_asset_id?: string | null;
  source_label?: string;
}

export interface ListTwinsResult {
  parent_asset_id: string;
  twins: TwinDocument[];
}

export class TwinNotesHttpError extends Error {
  readonly status: number;
  readonly body: string;

  constructor(status: number, body: string) {
    super(`twin-notes API ${status}: ${body.slice(0, 200)}`);
    this.name = "TwinNotesHttpError";
    this.status = status;
    this.body = body;
  }
}

async function readOkBody(res: Response): Promise<unknown> {
  if (!res.ok) {
    const text = await res.text();
    throw new TwinNotesHttpError(res.status, text);
  }
  return res.json() as Promise<unknown>;
}

function parseStringList(raw: unknown, field: string): string[] {
  if (raw === undefined || raw === null) return [];
  if (!Array.isArray(raw)) {
    throw new Error(`twin document rejected: ${field} must be an array`);
  }
  const out: string[] = [];
  for (const item of raw) {
    if (typeof item !== "string") {
      throw new Error(`twin document rejected: every ${field} entry must be a string`);
    }
    // Preserve empty? Store strips empties on write; allow empty here but
    // do not coerce non-strings.
    out.push(item);
  }
  return out;
}

/**
 * Fail closed: twin_id and parent_asset_id must be non-empty strings.
 * insight/question entries must be strings (no null/object coercion).
 */
export function parseTwinDocument(body: unknown): TwinDocument {
  if (!body || typeof body !== "object") {
    throw new Error("twin document response must be an object");
  }
  const o = body as Record<string, unknown>;
  if (typeof o.twin_id !== "string" || !o.twin_id.trim()) {
    throw new Error("twin document rejected: twin_id must be non-empty string");
  }
  if (typeof o.parent_asset_id !== "string" || !o.parent_asset_id.trim()) {
    throw new Error(
      "twin document rejected: parent_asset_id must be non-empty string",
    );
  }
  const created = o.created_at;
  const updated = o.updated_at;
  if (created !== undefined && created !== null) {
    if (typeof created !== "number" || !Number.isFinite(created)) {
      throw new Error("twin document rejected: created_at must be finite number");
    }
  }
  if (updated !== undefined && updated !== null) {
    if (typeof updated !== "number" || !Number.isFinite(updated)) {
      throw new Error("twin document rejected: updated_at must be finite number");
    }
  }
  return {
    twin_id: o.twin_id.trim(),
    parent_asset_id: o.parent_asset_id.trim(),
    insights: parseStringList(o.insights, "insights"),
    questions: parseStringList(o.questions, "questions"),
    source_label: typeof o.source_label === "string" ? o.source_label : "",
    created_at: Number(created ?? 0),
    updated_at: Number(updated ?? 0),
    merged_from: parseStringList(o.merged_from, "merged_from"),
  };
}

export function parseListTwinsResult(body: unknown): ListTwinsResult {
  if (!body || typeof body !== "object") {
    throw new Error("list twins response must be an object");
  }
  const o = body as Record<string, unknown>;
  if (typeof o.parent_asset_id !== "string" || !o.parent_asset_id.trim()) {
    throw new Error(
      "list twins response rejected: parent_asset_id must be non-empty string",
    );
  }
  if (!Array.isArray(o.twins)) {
    throw new Error("list twins response rejected: twins must be an array");
  }
  return {
    parent_asset_id: o.parent_asset_id.trim(),
    twins: o.twins.map((t) => parseTwinDocument(t)),
  };
}

export async function recordTwin(req: RecordTwinRequest): Promise<TwinDocument> {
  const parent = String(req.parent_asset_id || "").trim();
  if (!parent) {
    throw new Error("parent_asset_id must be a non-empty string");
  }
  const insights = (req.insights || [])
    .map((s) => String(s).trim())
    .filter(Boolean);
  const questions = (req.questions || [])
    .map((s) => String(s).trim())
    .filter(Boolean);

  const payload: Record<string, unknown> = {
    parent_asset_id: parent,
    insights,
    questions,
    source_label: req.source_label ?? "",
  };
  if (req.twin_id != null && String(req.twin_id).trim()) {
    payload.twin_id = String(req.twin_id).trim();
  }

  const res = await apiFetch(`${API_BASE}/twins`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  const raw = await readOkBody(res);
  return parseTwinDocument(raw);
}

export async function listTwinsForParent(
  parentAssetId: string,
): Promise<ListTwinsResult> {
  const parent = String(parentAssetId || "").trim();
  if (!parent) {
    throw new Error("parent_asset_id must be a non-empty string");
  }
  const res = await apiFetch(
    `${API_BASE}/twins/by-parent/${encodeURIComponent(parent)}`,
    { method: "GET" },
  );
  const raw = await readOkBody(res);
  return parseListTwinsResult(raw);
}

export async function getTwin(
  twinId: string,
  parentAssetId?: string | null,
): Promise<TwinDocument> {
  const id = String(twinId || "").trim();
  if (!id) {
    throw new Error("twin_id must be a non-empty string");
  }
  const qs =
    parentAssetId != null && String(parentAssetId).trim()
      ? `?parent_asset_id=${encodeURIComponent(String(parentAssetId).trim())}`
      : "";
  const res = await apiFetch(`${API_BASE}/twins/${encodeURIComponent(id)}${qs}`, {
    method: "GET",
  });
  const raw = await readOkBody(res);
  return parseTwinDocument(raw);
}

export async function mergeTwins(req: MergeTwinsRequest): Promise<TwinDocument> {
  const twinIds = (req.twin_ids || [])
    .map((t) => String(t).trim())
    .filter(Boolean);
  if (twinIds.length === 0) {
    throw new Error("twin_ids must contain at least one id");
  }
  const payload: Record<string, unknown> = {
    twin_ids: twinIds,
    source_label: req.source_label ?? "merged",
  };
  if (req.parent_asset_id != null && String(req.parent_asset_id).trim()) {
    payload.parent_asset_id = String(req.parent_asset_id).trim();
  }
  const res = await apiFetch(`${API_BASE}/twins/merge`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  const raw = await readOkBody(res);
  return parseTwinDocument(raw);
}

export function formatTwinSummary(doc: TwinDocument): string {
  return (
    `${doc.twin_id} · parent=${doc.parent_asset_id} · ` +
    `insights=${doc.insights.length} questions=${doc.questions.length}` +
    (doc.source_label ? ` · ${doc.source_label}` : "")
  );
}

export function parseLines(raw: string): string[] {
  return raw
    .split(/\r?\n/)
    .map((s) => s.trim())
    .filter(Boolean);
}
