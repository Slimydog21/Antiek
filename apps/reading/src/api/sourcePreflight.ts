/**
 * Source-policy preflight client (PR #776 contract).
 *
 * POST /research/source-policy/preflight
 *
 * Honesty: offline_probe_ok and runner_consumes_today are strict booleans —
 * never invent true. Client rejects non-boolean probe fields.
 */

import { API_BASE, apiFetch } from "../lib/api";

export type SourcePolicy = "arxiv" | "substack" | "web" | "operator_corpus";

export interface SourcePreflightEntry {
  source: string;
  status: string;
  runner_consumes_today: boolean;
  external_call_would_be_required: boolean;
  note: string;
  adapter_importable: boolean;
  offline_probe_ok: boolean;
}

export interface SourcePolicyPreflight {
  source_receipt_id: string;
  source_policy: string[];
  gather_mode: string;
  entries: SourcePreflightEntry[];
  notes: string[];
}

export interface SourcePreflightRequest {
  source_policy: SourcePolicy[];
  root_id?: string | null;
  problem?: string | null;
}

export class SourcePreflightHttpError extends Error {
  readonly status: number;
  readonly body: string;
  constructor(status: number, body: string) {
    super(`source-preflight API ${status}: ${body.slice(0, 200)}`);
    this.name = "SourcePreflightHttpError";
    this.status = status;
    this.body = body;
  }
}

async function readOkBody(res: Response): Promise<unknown> {
  if (!res.ok) {
    const text = await res.text();
    throw new SourcePreflightHttpError(res.status, text);
  }
  return res.json() as Promise<unknown>;
}

function requireBool(v: unknown, path: string): boolean {
  if (typeof v !== "boolean") {
    throw new Error(`source-preflight rejected: ${path} must be boolean`);
  }
  return v;
}

export function parseSourcePreflightEntry(
  raw: unknown,
  path = "entry",
): SourcePreflightEntry {
  if (!raw || typeof raw !== "object") {
    throw new Error(`source-preflight rejected: ${path} must be object`);
  }
  const o = raw as Record<string, unknown>;
  return {
    source: String(o.source ?? ""),
    status: String(o.status ?? ""),
    runner_consumes_today: requireBool(o.runner_consumes_today, `${path}.runner_consumes_today`),
    external_call_would_be_required: requireBool(
      o.external_call_would_be_required,
      `${path}.external_call_would_be_required`,
    ),
    note: String(o.note ?? ""),
    adapter_importable: requireBool(o.adapter_importable, `${path}.adapter_importable`),
    offline_probe_ok: requireBool(o.offline_probe_ok, `${path}.offline_probe_ok`),
  };
}

export function parseSourcePolicyPreflight(body: unknown): SourcePolicyPreflight {
  if (!body || typeof body !== "object") {
    throw new Error("source-preflight response must be an object");
  }
  const o = body as Record<string, unknown>;
  if (typeof o.source_receipt_id !== "string" || !o.source_receipt_id.trim()) {
    throw new Error("source-preflight rejected: source_receipt_id required");
  }
  if (!Array.isArray(o.source_policy) || o.source_policy.length === 0) {
    throw new Error("source-preflight rejected: source_policy required");
  }
  if (typeof o.gather_mode !== "string") {
    throw new Error("source-preflight rejected: gather_mode must be string");
  }
  if (!Array.isArray(o.entries)) {
    throw new Error("source-preflight rejected: entries must be array");
  }
  return {
    source_receipt_id: o.source_receipt_id,
    source_policy: o.source_policy.map((s) => String(s)),
    gather_mode: o.gather_mode,
    entries: o.entries.map((e, i) => parseSourcePreflightEntry(e, `entries[${i}]`)),
    notes: Array.isArray(o.notes) ? o.notes.map((n) => String(n)) : [],
  };
}

export async function postSourcePreflight(
  req: SourcePreflightRequest,
): Promise<SourcePolicyPreflight> {
  if (!req.source_policy || req.source_policy.length === 0) {
    throw new Error("source_policy must contain at least one source");
  }
  const res = await apiFetch(`${API_BASE}/research/source-policy/preflight`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      source_policy: req.source_policy,
      root_id: req.root_id ?? null,
      problem: req.problem ?? null,
    }),
  });
  const raw = await readOkBody(res);
  return parseSourcePolicyPreflight(raw);
}

export function formatProbeHonesty(entry: SourcePreflightEntry): string {
  const offline = entry.offline_probe_ok ? "offline probe ok" : "offline probe not ok";
  const consume = entry.runner_consumes_today
    ? "runner consumes today"
    : "runner does not claim consumption today";
  return `${entry.source}: ${offline}; ${consume}`;
}
