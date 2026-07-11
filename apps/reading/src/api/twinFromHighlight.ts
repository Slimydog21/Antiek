/**
 * Highlight → twin seed client (no LLM).
 *
 * POST /twins/from-highlight/seed
 */

import { API_BASE, apiFetch } from "../lib/api";

export interface HighlightTwinRequest {
  parent_asset_id: string;
  highlight: string;
  insights?: string[];
  questions?: string[];
  source_label?: string;
  /** Required explicit gate provenance — never omit (fail closed). */
  gated: boolean;
}

export interface HighlightTwinSeed {
  parent_asset_id: string;
  highlight: string;
  insights: string[];
  questions: string[];
  source_label: string;
  notes: string[];
  llm_filled: boolean;
  authority: string;
}

export class HighlightTwinHttpError extends Error {
  readonly status: number;
  readonly body: string;
  constructor(status: number, body: string) {
    super(`twin-from-highlight API ${status}: ${body.slice(0, 200)}`);
    this.name = "HighlightTwinHttpError";
    this.status = status;
    this.body = body;
  }
}

async function readOkBody(res: Response): Promise<unknown> {
  if (!res.ok) {
    throw new HighlightTwinHttpError(res.status, await res.text());
  }
  return res.json() as Promise<unknown>;
}

export function parseHighlightTwinSeed(body: unknown): HighlightTwinSeed {
  if (!body || typeof body !== "object") {
    throw new Error("highlight twin seed must be an object");
  }
  const o = body as Record<string, unknown>;
  if (typeof o.parent_asset_id !== "string" || !o.parent_asset_id.trim()) {
    throw new Error("highlight twin seed rejected: parent_asset_id required");
  }
  if (typeof o.highlight !== "string" || !o.highlight.trim()) {
    throw new Error("highlight twin seed rejected: highlight required");
  }
  if (typeof o.llm_filled !== "boolean") {
    throw new Error("highlight twin seed rejected: llm_filled must be boolean");
  }
  if (o.llm_filled === true) {
    throw new Error(
      "highlight twin seed rejected: llm_filled=true not accepted (seed is operator-only)",
    );
  }
  if (typeof o.authority !== "string" || o.authority.trim() !== "highlight_seed_only") {
    throw new Error(
      "highlight twin seed rejected: authority must be highlight_seed_only",
    );
  }
  if (!Array.isArray(o.insights) || !Array.isArray(o.questions)) {
    throw new Error("highlight twin seed rejected: insights/questions must be arrays");
  }
  if (!Array.isArray(o.notes)) {
    throw new Error("highlight twin seed rejected: notes must be an array");
  }
  return {
    parent_asset_id: o.parent_asset_id.trim(),
    highlight: o.highlight,
    insights: o.insights.map((x) => {
      if (typeof x !== "string") throw new Error("insights must be strings");
      return x;
    }),
    questions: o.questions.map((x) => {
      if (typeof x !== "string") throw new Error("questions must be strings");
      return x;
    }),
    source_label: typeof o.source_label === "string" ? o.source_label : "highlight",
    notes: o.notes.map((n) => {
      if (typeof n !== "string") throw new Error("notes must be strings");
      return n;
    }),
    llm_filled: false,
    authority: "highlight_seed_only",
  };
}

export async function postHighlightTwinSeed(
  req: HighlightTwinRequest,
): Promise<HighlightTwinSeed> {
  const parent = String(req.parent_asset_id || "").trim();
  const highlight = String(req.highlight || "").trim();
  if (!parent) throw new Error("parent_asset_id must be non-empty");
  if (!highlight) throw new Error("highlight must be non-empty");
  // Fail closed: gated must be an explicit boolean from the caller/provenance
  // layer. Missing/undefined is rejected (never invent ungated).
  if (typeof req.gated !== "boolean") {
    throw new Error(
      "gated must be an explicit boolean from highlight provenance (fail closed)",
    );
  }
  if (req.gated === true) {
    throw new Error("gated/withheld highlight body cannot seed a twin");
  }

  const res = await apiFetch(`${API_BASE}/twins/from-highlight/seed`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      parent_asset_id: parent,
      highlight,
      insights: req.insights ?? [],
      questions: req.questions ?? [],
      source_label: req.source_label ?? "highlight",
      gated: req.gated,
    }),
  });
  return parseHighlightTwinSeed(await readOkBody(res));
}
