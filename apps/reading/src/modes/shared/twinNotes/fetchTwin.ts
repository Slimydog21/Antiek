/**
 * Live twin client — GET /twins/:parentAssetId.
 *
 * Fail-closed to null on network/401/404/shape error so the panel can keep
 * demo/empty honesty without throwing. Live twins must be `isTwin: true` and
 * share the requested parent id (anti-recursion + authority).
 */

import { API_BASE, apiFetch } from "../../../lib/api";
import type { TwinDocument, TwinInsight, TwinQuestion } from "./twinDocument";

export type FetchTwinResult =
  | { ok: true; twin: TwinDocument; source: "live" }
  | { ok: false; reason: string; status?: number };

function asString(v: unknown): string | null {
  return typeof v === "string" && v.length > 0 ? v : null;
}

function parseInsights(raw: unknown): TwinInsight[] {
  if (!Array.isArray(raw)) return [];
  const out: TwinInsight[] = [];
  for (const item of raw) {
    if (!item || typeof item !== "object") continue;
    const rec = item as Record<string, unknown>;
    const id = asString(rec.id);
    const text = asString(rec.text);
    if (!id || !text) continue;
    out.push({
      id,
      text,
      sourceSpan: asString(rec.sourceSpan) ?? undefined,
    });
  }
  return out;
}

function parseQuestions(raw: unknown): TwinQuestion[] {
  if (!Array.isArray(raw)) return [];
  const out: TwinQuestion[] = [];
  for (const item of raw) {
    if (!item || typeof item !== "object") continue;
    const rec = item as Record<string, unknown>;
    const id = asString(rec.id);
    const text = asString(rec.text);
    if (!id || !text) continue;
    out.push({
      id,
      text,
      open: rec.open !== false,
    });
  }
  return out;
}

/**
 * Pure JSON → TwinDocument. Returns null if shape is not a trustworthy twin.
 */
export function parseTwinDocument(
  raw: unknown,
  expectedParentId: string,
): TwinDocument | null {
  if (!raw || typeof raw !== "object") return null;
  const rec = raw as Record<string, unknown>;
  const id = asString(rec.id);
  const parentAssetId = asString(rec.parentAssetId) ?? asString(rec.parent_asset_id);
  if (!id || !parentAssetId) return null;
  if (parentAssetId !== expectedParentId) return null;
  if (rec.isTwin !== true && rec.is_twin !== true) return null;

  const statusRaw = asString(rec.status) ?? "ready";
  const status = (
    ["empty", "pending", "ready", "stale", "error"] as const
  ).includes(statusRaw as TwinDocument["status"])
    ? (statusRaw as TwinDocument["status"])
    : "ready";

  return {
    id,
    parentAssetId,
    insights: parseInsights(rec.insights),
    questions: parseQuestions(rec.questions),
    sourceContentHash:
      asString(rec.sourceContentHash) ??
      asString(rec.source_content_hash) ??
      undefined,
    authority: "advisory",
    isTwin: true,
    status,
    errorReason: asString(rec.errorReason) ?? asString(rec.error_reason) ?? undefined,
  };
}

/** Build the canonical twins URL for a parent asset. */
export function twinUrlForAsset(parentAssetId: string): string {
  const base = API_BASE || "";
  return `${base}/twins/${encodeURIComponent(parentAssetId)}`;
}

/**
 * Fetch live twin for parent asset. Never throws — returns ok:false with reason.
 */
export async function fetchTwinForAsset(
  parentAssetId: string,
  opts: { fetchImpl?: typeof fetch } = {},
): Promise<FetchTwinResult> {
  if (!parentAssetId.trim()) {
    return { ok: false, reason: "empty_parent_id" };
  }
  const url = twinUrlForAsset(parentAssetId);
  try {
    // Prefer apiFetch (cookie credentials) when available; fall back for tests.
    const resp = opts.fetchImpl
      ? await opts.fetchImpl(url, { credentials: "include" })
      : await apiFetch(url);
    if (resp.status === 404) {
      return { ok: false, reason: "not_found", status: 404 };
    }
    if (resp.status === 401 || resp.status === 403) {
      return { ok: false, reason: "unauthorized", status: resp.status };
    }
    if (!resp.ok) {
      return { ok: false, reason: `http_${resp.status}`, status: resp.status };
    }
    const body: unknown = await resp.json();
    const twin = parseTwinDocument(body, parentAssetId);
    if (!twin) {
      return { ok: false, reason: "shape_rejected", status: resp.status };
    }
    return { ok: true, twin, source: "live" };
  } catch (e) {
    return {
      ok: false,
      reason: e instanceof Error ? e.message : "network_error",
    };
  }
}
