/**
 * Book free-copy preflight client (marketplace honesty).
 *
 * POST /books/free-copy/preflight
 *
 * Answers "is there a free PD/OA copy online?" before purchase intent.
 * Fail-closed: never invent freely_available=true from partial payloads.
 */

import { API_BASE, apiFetch } from "../lib/api";

export interface FreeCopyOutcome {
  source: string;
  found: boolean;
  query: string;
  timestamp: string;
  error: string | null;
}

export interface FreeCopyPreflightRequest {
  title: string;
  author?: string | null;
  sources?: string[];
}

export interface FreeCopyPreflightResult {
  freely_available: boolean;
  title: string;
  author: string | null;
  source: string | null;
  rights_basis: string | null;
  retrieved_at: string | null;
  candidate_kind: string | null;
  candidate_ref_withheld: boolean;
  outcomes: FreeCopyOutcome[];
  checked_at: string;
}

export class FreeCopyHttpError extends Error {
  readonly status: number;
  readonly body: string;

  constructor(status: number, body: string) {
    super(`book-free-copy API ${status}: ${body.slice(0, 200)}`);
    this.name = "FreeCopyHttpError";
    this.status = status;
    this.body = body;
  }
}

async function readOkBody(res: Response): Promise<unknown> {
  if (!res.ok) {
    const text = await res.text();
    throw new FreeCopyHttpError(res.status, text);
  }
  return res.json() as Promise<unknown>;
}

function parseOutcome(raw: unknown): FreeCopyOutcome {
  if (!raw || typeof raw !== "object") {
    throw new Error("free-copy outcome must be an object");
  }
  const o = raw as Record<string, unknown>;
  if (typeof o.source !== "string" || !o.source.trim()) {
    throw new Error("free-copy outcome rejected: source must be non-empty string");
  }
  if (typeof o.found !== "boolean") {
    throw new Error("free-copy outcome rejected: found must be boolean");
  }
  if (typeof o.query !== "string") {
    throw new Error("free-copy outcome rejected: query must be string");
  }
  if (typeof o.timestamp !== "string") {
    throw new Error("free-copy outcome rejected: timestamp must be string");
  }
  if (o.error !== null && typeof o.error !== "string") {
    throw new Error("free-copy outcome rejected: error must be string|null");
  }
  return {
    source: o.source,
    found: o.found,
    query: o.query,
    timestamp: o.timestamp,
    error: o.error as string | null,
  };
}

/**
 * Fail closed: freely_available must be a real boolean; true requires source.
 * Never coerce missing freely_available to false or true.
 */
export function parseFreeCopyPreflightResult(
  body: unknown,
): FreeCopyPreflightResult {
  if (!body || typeof body !== "object") {
    throw new Error("free-copy preflight response must be an object");
  }
  const o = body as Record<string, unknown>;
  if (typeof o.freely_available !== "boolean") {
    throw new Error(
      "free-copy preflight rejected: freely_available must be boolean",
    );
  }
  if (typeof o.title !== "string" || !o.title.trim()) {
    throw new Error("free-copy preflight rejected: title must be non-empty string");
  }
  if (o.author !== null && typeof o.author !== "string") {
    throw new Error("free-copy preflight rejected: author must be string|null");
  }
  if (typeof o.candidate_ref_withheld !== "boolean") {
    throw new Error(
      "free-copy preflight rejected: candidate_ref_withheld must be boolean",
    );
  }
  if (typeof o.checked_at !== "string" || !o.checked_at.trim()) {
    throw new Error(
      "free-copy preflight rejected: checked_at must be non-empty string",
    );
  }
  if (!Array.isArray(o.outcomes)) {
    throw new Error("free-copy preflight rejected: outcomes must be an array");
  }
  const outcomes = o.outcomes.map(parseOutcome);

  if (o.freely_available === true) {
    if (typeof o.source !== "string" || !o.source.trim()) {
      throw new Error(
        "free-copy preflight rejected: freely_available=true requires non-empty source",
      );
    }
    if (typeof o.rights_basis !== "string" || !o.rights_basis.trim()) {
      throw new Error(
        "free-copy preflight rejected: freely_available=true requires rights_basis",
      );
    }
  } else {
    // freely_available=false: source must not pretend a hit
    if (o.source !== null && o.source !== undefined) {
      if (typeof o.source !== "string") {
        throw new Error(
          "free-copy preflight rejected: source must be string|null when not free",
        );
      }
      if (o.source.trim()) {
        throw new Error(
          "free-copy preflight rejected: freely_available=false must not name a source hit",
        );
      }
    }
  }

  return {
    freely_available: o.freely_available,
    title: o.title.trim(),
    author: typeof o.author === "string" ? o.author : null,
    source:
      typeof o.source === "string" && o.source.trim() ? o.source.trim() : null,
    rights_basis:
      typeof o.rights_basis === "string" && o.rights_basis.trim()
        ? o.rights_basis.trim()
        : null,
    retrieved_at:
      typeof o.retrieved_at === "string" && o.retrieved_at.trim()
        ? o.retrieved_at.trim()
        : null,
    candidate_kind:
      typeof o.candidate_kind === "string" ? o.candidate_kind : null,
    candidate_ref_withheld: o.candidate_ref_withheld,
    outcomes,
    checked_at: o.checked_at.trim(),
  };
}

export async function postFreeCopyPreflight(
  req: FreeCopyPreflightRequest,
): Promise<FreeCopyPreflightResult> {
  const title = String(req.title || "").trim();
  if (!title) {
    throw new Error("title must be a non-empty string");
  }
  const payload: Record<string, unknown> = { title };
  if (req.author != null && String(req.author).trim()) {
    payload.author = String(req.author).trim();
  }
  if (req.sources != null) {
    const sources = req.sources.map((s) => String(s).trim()).filter(Boolean);
    if (sources.length === 0) {
      throw new Error("sources must be non-empty when provided");
    }
    payload.sources = sources;
  }

  const res = await apiFetch(`${API_BASE}/books/free-copy/preflight`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  const raw = await readOkBody(res);
  return parseFreeCopyPreflightResult(raw);
}

export function formatFreeCopySummary(r: FreeCopyPreflightResult): string {
  if (r.freely_available) {
    return `Free copy found via ${r.source} (${r.rights_basis})`;
  }
  const n = r.outcomes.length;
  return `No free copy found after ${n} source check${n === 1 ? "" : "s"}`;
}
