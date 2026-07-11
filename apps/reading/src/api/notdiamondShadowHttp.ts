/**
 * HTTP client for NotDiamond shadow comparison (#835).
 *
 * POST /settings/notdiamond/shadow
 *
 * Fail-closed: authority must be "shadow". When enabled is false, ND reco
 * must be null (client rejects inventing recommendations while disabled).
 */

import { API_BASE, apiFetch } from "../lib/api";

export interface ShadowHttpRequest {
  task?: string;
  local_model_id: string;
  nd_recommended_model_id?: string | null;
  enabled?: boolean;
  extra_notes?: string[];
}

export interface ShadowHttpResult {
  enabled: boolean;
  authority: "shadow";
  task: string;
  local_model_id: string;
  nd_recommended_model_id: string | null;
  agreement: boolean | null;
  notes: string[];
}

export class NotDiamondShadowHttpError extends Error {
  readonly status: number;
  readonly body: string;
  constructor(status: number, body: string) {
    super(`notdiamond-shadow API ${status}: ${body.slice(0, 200)}`);
    this.name = "NotDiamondShadowHttpError";
    this.status = status;
    this.body = body;
  }
}

async function readOkBody(res: Response): Promise<unknown> {
  if (!res.ok) {
    const text = await res.text();
    throw new NotDiamondShadowHttpError(res.status, text);
  }
  return res.json() as Promise<unknown>;
}

export function parseShadowHttpResult(body: unknown): ShadowHttpResult {
  if (!body || typeof body !== "object") {
    throw new Error("notdiamond-shadow response must be an object");
  }
  const o = body as Record<string, unknown>;
  if (o.authority !== "shadow") {
    throw new Error(
      "notdiamond-shadow response rejected: authority must be shadow",
    );
  }
  if (typeof o.enabled !== "boolean") {
    throw new Error("notdiamond-shadow response rejected: enabled must be boolean");
  }
  if (typeof o.local_model_id !== "string" || !o.local_model_id.trim()) {
    throw new Error("notdiamond-shadow response rejected: local_model_id required");
  }
  if (typeof o.task !== "string") {
    throw new Error("notdiamond-shadow response rejected: task must be string");
  }
  if (!Array.isArray(o.notes)) {
    throw new Error("notdiamond-shadow response rejected: notes must be array");
  }
  let nd: string | null;
  if (o.nd_recommended_model_id === null || o.nd_recommended_model_id === undefined) {
    nd = null;
  } else if (typeof o.nd_recommended_model_id === "string") {
    nd = o.nd_recommended_model_id;
  } else {
    throw new Error(
      "notdiamond-shadow response rejected: nd_recommended_model_id invalid",
    );
  }
  // Fail closed: while disabled, never accept a non-null ND recommendation.
  if (o.enabled === false && nd !== null) {
    throw new Error(
      "notdiamond-shadow response rejected: ND recommendation present while enabled=false",
    );
  }
  let agreement: boolean | null;
  if (o.agreement === null || o.agreement === undefined) {
    agreement = null;
  } else if (typeof o.agreement === "boolean") {
    agreement = o.agreement;
  } else {
    throw new Error("notdiamond-shadow response rejected: agreement must be boolean|null");
  }
  return {
    enabled: o.enabled,
    authority: "shadow",
    task: o.task,
    local_model_id: o.local_model_id,
    nd_recommended_model_id: nd,
    agreement,
    notes: o.notes.map((n) => String(n)),
  };
}

export async function postNotDiamondShadow(
  req: ShadowHttpRequest,
): Promise<ShadowHttpResult> {
  const local = (req.local_model_id || "").trim();
  if (!local) {
    throw new Error("local_model_id must be non-empty");
  }
  const enabled = req.enabled === true;
  // Shadow-on means "compare local vs *injected* ND recommendation" — never live ND HTTP.
  // Fail closed: cannot enable without an explicit injected recommendation string.
  let nd: string | null =
    req.nd_recommended_model_id === undefined || req.nd_recommended_model_id === null
      ? null
      : String(req.nd_recommended_model_id).trim() || null;
  if (enabled && nd === null) {
    throw new Error(
      "enabled=true requires explicit injected nd_recommended_model_id (no live ND fetch)",
    );
  }
  if (!enabled) {
    nd = null; // never forward ND reco while kill switch off
  }
  const res = await apiFetch(`${API_BASE}/settings/notdiamond/shadow`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      task: req.task ?? "general",
      local_model_id: local,
      nd_recommended_model_id: nd,
      enabled,
      extra_notes: req.extra_notes ?? [],
    }),
  });
  const raw = await readOkBody(res);
  return parseShadowHttpResult(raw);
}
