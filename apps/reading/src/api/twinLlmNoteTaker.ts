/**
 * LLM note-taker twin payload client (no model invocation).
 *
 * POST /twins/note-taker/payload
 */

import { API_BASE, apiFetch } from "../lib/api";

export interface NoteTakerRequest {
  parent_asset_id: string;
  insights?: string[];
  questions?: string[];
  source_label?: string;
  llm_filled: boolean;
  asset_text_sha256?: string | null;
  gated: boolean;
}

export interface TwinNotePayload {
  parent_asset_id: string;
  insights: string[];
  questions: string[];
  source_label: string;
  llm_filled: boolean;
  asset_text_sha256: string | null;
  notes: string[];
  authority: string;
  model_invoked: boolean;
}

export class NoteTakerHttpError extends Error {
  readonly status: number;
  readonly body: string;
  constructor(status: number, body: string) {
    super(`twin-note-taker API ${status}: ${body.slice(0, 200)}`);
    this.name = "NoteTakerHttpError";
    this.status = status;
    this.body = body;
  }
}

async function readOkBody(res: Response): Promise<unknown> {
  if (!res.ok) {
    throw new NoteTakerHttpError(res.status, await res.text());
  }
  return res.json() as Promise<unknown>;
}

export function parseTwinNotePayload(body: unknown): TwinNotePayload {
  if (!body || typeof body !== "object") {
    throw new Error("note-taker payload must be an object");
  }
  const o = body as Record<string, unknown>;
  if (typeof o.parent_asset_id !== "string" || !o.parent_asset_id.trim()) {
    throw new Error("note-taker rejected: parent_asset_id required");
  }
  if (typeof o.model_invoked !== "boolean") {
    throw new Error("note-taker rejected: model_invoked must be boolean");
  }
  if (o.model_invoked === true) {
    throw new Error(
      "note-taker rejected: model_invoked=true not accepted (adapter never calls models)",
    );
  }
  if (typeof o.llm_filled !== "boolean") {
    throw new Error("note-taker rejected: llm_filled must be boolean");
  }
  if (typeof o.authority !== "string" || o.authority.trim() !== "note_taker_payload_only") {
    throw new Error("note-taker rejected: authority must be note_taker_payload_only");
  }
  if (!Array.isArray(o.insights) || !Array.isArray(o.questions)) {
    throw new Error("note-taker rejected: insights/questions must be arrays");
  }
  const insights = o.insights.map((x) => {
    if (typeof x !== "string") throw new Error("insights must be strings");
    return x.trim();
  }).filter(Boolean);
  const questions = o.questions.map((x) => {
    if (typeof x !== "string") throw new Error("questions must be strings");
    return x.trim();
  }).filter(Boolean);
  if (insights.length === 0 && questions.length === 0) {
    throw new Error("note-taker rejected: at least one insight or question required");
  }
  if (!Array.isArray(o.notes)) {
    throw new Error("note-taker rejected: notes must be an array");
  }
  return {
    parent_asset_id: o.parent_asset_id.trim(),
    insights,
    questions,
    source_label: typeof o.source_label === "string" ? o.source_label : "llm-note-taker",
    llm_filled: o.llm_filled,
    asset_text_sha256:
      typeof o.asset_text_sha256 === "string" ? o.asset_text_sha256 : null,
    notes: o.notes.map((n) => {
      if (typeof n !== "string") throw new Error("notes must be strings");
      return n;
    }),
    authority: "note_taker_payload_only",
    model_invoked: false,
  };
}

export async function postTwinNoteTakerPayload(
  req: NoteTakerRequest,
): Promise<TwinNotePayload> {
  if (typeof req.llm_filled !== "boolean") {
    throw new Error("llm_filled must be an explicit boolean");
  }
  if (typeof req.gated !== "boolean") {
    throw new Error("gated must be an explicit boolean");
  }
  if (req.gated === true) {
    throw new Error("gated/withheld asset cannot receive note-taker twin");
  }
  const parent = String(req.parent_asset_id || "").trim();
  if (!parent) throw new Error("parent_asset_id must be non-empty");
  const insights = (req.insights || []).map((s) => String(s).trim()).filter(Boolean);
  const questions = (req.questions || []).map((s) => String(s).trim()).filter(Boolean);
  if (insights.length === 0 && questions.length === 0) {
    throw new Error("at least one insight or question required");
  }

  const payload: Record<string, unknown> = {
    parent_asset_id: parent,
    insights,
    questions,
    source_label: req.source_label ?? "llm-note-taker",
    llm_filled: req.llm_filled,
    gated: req.gated,
  };
  if (req.asset_text_sha256 != null && String(req.asset_text_sha256).trim()) {
    payload.asset_text_sha256 = String(req.asset_text_sha256).trim();
  }

  const res = await apiFetch(`${API_BASE}/twins/note-taker/payload`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return parseTwinNotePayload(await readOkBody(res));
}
