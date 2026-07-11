/**
 * Finalize authorize HTTP client (PR #818 contract).
 *
 * POST /twins/finalize/authorize
 *
 * Returns whether a provisional draft may proceed to parent mutation.
 * Never mutates parent. Fail-closed parsing: authorized must be strict bool.
 */

import { API_BASE, apiFetch } from "../lib/api";

export interface FinalizeAuthorizeRequest {
  draft_id: string;
  parent_asset_id: string;
  provisional: boolean;
  operator_accepted: boolean;
  twin_ids?: string[] | null;
  twin_parent_ids?: string[] | null;
}

export interface FinalizeAuthorizeResult {
  authorized: boolean;
  draft_id: string;
  parent_asset_id: string;
  reason: string;
  notes: string[];
}

export class FinalizeAuthorizeHttpError extends Error {
  readonly status: number;
  readonly body: string;

  constructor(status: number, body: string) {
    super(`finalize-authorize API ${status}: ${body.slice(0, 200)}`);
    this.name = "FinalizeAuthorizeHttpError";
    this.status = status;
    this.body = body;
  }
}

async function readOkBody(res: Response): Promise<unknown> {
  if (!res.ok) {
    const text = await res.text();
    throw new FinalizeAuthorizeHttpError(res.status, text);
  }
  return res.json() as Promise<unknown>;
}

/**
 * Fail closed: authorized must be boolean; never invent true.
 * If operator_accepted was false, client also refuses authorized=true
 * even if a buggy server returned it.
 */
export function parseFinalizeAuthorizeResult(
  body: unknown,
  opts?: { operator_accepted?: boolean },
): FinalizeAuthorizeResult {
  const operator_accepted = opts?.operator_accepted;
  if (!body || typeof body !== "object") {
    throw new Error("finalize-authorize response must be an object");
  }
  const o = body as Record<string, unknown>;
  if (typeof o.authorized !== "boolean") {
    throw new Error(
      "finalize-authorize response rejected: authorized must be boolean",
    );
  }
  if (typeof o.draft_id !== "string" || !o.draft_id.trim()) {
    throw new Error("finalize-authorize response rejected: draft_id required");
  }
  if (typeof o.parent_asset_id !== "string" || !o.parent_asset_id.trim()) {
    throw new Error(
      "finalize-authorize response rejected: parent_asset_id required",
    );
  }
  if (typeof o.reason !== "string") {
    throw new Error("finalize-authorize response rejected: reason must be string");
  }
  if (!Array.isArray(o.notes)) {
    throw new Error("finalize-authorize response rejected: notes must be array");
  }
  for (let i = 0; i < o.notes.length; i++) {
    if (typeof o.notes[i] !== "string") {
      throw new Error(
        `finalize-authorize response rejected: notes[${i}] must be string`,
      );
    }
  }

  let authorized = o.authorized;
  // Copy notes so fail-closed annotation never mutates the raw response body.
  const notes = [...(o.notes as string[])];
  // Continuous honesty: client never surfaces authorized=true without accept.
  if (authorized === true && operator_accepted !== true) {
    authorized = false;
    notes.push(
      "client fail-closed: operator_accepted was not true — forced authorized=false",
    );
  }

  return {
    authorized,
    draft_id: o.draft_id,
    parent_asset_id: o.parent_asset_id,
    reason: authorized ? o.reason : operator_accepted !== true && o.authorized === true
      ? "operator_accept_required"
      : o.reason,
    notes,
  };
}

export async function postFinalizeAuthorize(
  req: FinalizeAuthorizeRequest,
): Promise<FinalizeAuthorizeResult> {
  const draft_id = (req.draft_id || "").trim();
  const parent_asset_id = (req.parent_asset_id || "").trim();
  if (!draft_id) {
    throw new Error("draft_id must be non-empty");
  }
  if (!parent_asset_id) {
    throw new Error("parent_asset_id must be non-empty");
  }
  if (typeof req.provisional !== "boolean") {
    throw new Error("provisional must be boolean");
  }
  if (typeof req.operator_accepted !== "boolean") {
    throw new Error("operator_accepted must be boolean");
  }

  const res = await apiFetch(`${API_BASE}/twins/finalize/authorize`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      draft_id,
      parent_asset_id,
      provisional: req.provisional,
      operator_accepted: req.operator_accepted,
      twin_ids: req.twin_ids ?? null,
      twin_parent_ids: req.twin_parent_ids ?? null,
    }),
  });
  const raw = await readOkBody(res);
  return parseFinalizeAuthorizeResult(raw, {
    operator_accepted: req.operator_accepted,
  });
}

export function formatAuthorizeResult(r: FinalizeAuthorizeResult): string {
  if (r.authorized) {
    return "AUTHORIZED — may proceed to parent merge (not performed by this client)";
  }
  return `DENIED — ${r.reason}`;
}
