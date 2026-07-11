/**
 * Deep-research source pack client.
 *
 * POST /research/source-pack/build
 *
 * Advisory pack only — never invents live fetch authorization.
 */

import { API_BASE, apiFetch } from "../lib/api";

export interface SourcePackEntry {
  source: string;
  pack_status: "included" | "excluded" | "unavailable";
  readiness_status: string;
  adapter_importable: boolean;
  offline_probe_ok: boolean;
  runner_consumes_today: boolean;
  note: string;
}

export interface SourcePackResult {
  selected: string[];
  entries: SourcePackEntry[];
  pack_text: string;
  included_count: number;
  notes: string[];
  authority: string;
  live_fetch_authorized: boolean;
}

export interface SourcePackRequest {
  selected: string[];
  readiness_by_source?: Record<string, Record<string, unknown>> | null;
}

export class SourcePackHttpError extends Error {
  readonly status: number;
  readonly body: string;
  constructor(status: number, body: string) {
    super(`source-pack API ${status}: ${body.slice(0, 200)}`);
    this.name = "SourcePackHttpError";
    this.status = status;
    this.body = body;
  }
}

async function readOkBody(res: Response): Promise<unknown> {
  if (!res.ok) {
    throw new SourcePackHttpError(res.status, await res.text());
  }
  return res.json() as Promise<unknown>;
}

function parseEntry(raw: unknown): SourcePackEntry {
  if (!raw || typeof raw !== "object") {
    throw new Error("source pack entry must be an object");
  }
  const o = raw as Record<string, unknown>;
  if (typeof o.source !== "string" || !o.source.trim()) {
    throw new Error("source pack entry rejected: source required");
  }
  if (
    o.pack_status !== "included" &&
    o.pack_status !== "excluded" &&
    o.pack_status !== "unavailable"
  ) {
    throw new Error("source pack entry rejected: pack_status invalid");
  }
  for (const f of [
    "adapter_importable",
    "offline_probe_ok",
    "runner_consumes_today",
  ] as const) {
    if (typeof o[f] !== "boolean") {
      throw new Error(`source pack entry rejected: ${f} must be boolean`);
    }
  }
  if (typeof o.readiness_status !== "string") {
    throw new Error("source pack entry rejected: readiness_status must be string");
  }
  if (typeof o.note !== "string") {
    throw new Error("source pack entry rejected: note must be string");
  }
  return {
    source: o.source,
    pack_status: o.pack_status,
    readiness_status: o.readiness_status,
    adapter_importable: o.adapter_importable as boolean,
    offline_probe_ok: o.offline_probe_ok as boolean,
    runner_consumes_today: o.runner_consumes_today as boolean,
    note: o.note,
  };
}

export function parseSourcePackResult(body: unknown): SourcePackResult {
  if (!body || typeof body !== "object") {
    throw new Error("source pack response must be an object");
  }
  const o = body as Record<string, unknown>;
  if (typeof o.live_fetch_authorized !== "boolean") {
    throw new Error("source pack rejected: live_fetch_authorized must be boolean");
  }
  if (o.live_fetch_authorized === true) {
    throw new Error(
      "source pack rejected: live_fetch_authorized=true not accepted by this client",
    );
  }
  if (typeof o.authority !== "string" || o.authority.trim() !== "advisory_preflight") {
    throw new Error("source pack rejected: authority must be advisory_preflight");
  }
  if (typeof o.pack_text !== "string" || !o.pack_text.trim()) {
    throw new Error("source pack rejected: pack_text must be non-empty");
  }
  if (!Array.isArray(o.selected) || o.selected.length === 0) {
    throw new Error("source pack rejected: selected required");
  }
  if (typeof o.included_count !== "number" || !Number.isFinite(o.included_count)) {
    throw new Error("source pack rejected: included_count must be finite number");
  }
  if (!Array.isArray(o.entries)) {
    throw new Error("source pack rejected: entries must be an array");
  }
  if (!Array.isArray(o.notes)) {
    throw new Error("source pack rejected: notes must be an array");
  }
  return {
    selected: o.selected.map((s) => String(s)),
    entries: o.entries.map(parseEntry),
    pack_text: o.pack_text,
    included_count: o.included_count,
    notes: o.notes.map((n) => {
      if (typeof n !== "string") throw new Error("notes must be strings");
      return n;
    }),
    authority: "advisory_preflight",
    live_fetch_authorized: false,
  };
}

export async function postSourcePack(
  req: SourcePackRequest,
): Promise<SourcePackResult> {
  const selected = (req.selected || [])
    .map((s) => String(s).trim().toLowerCase())
    .filter(Boolean);
  if (selected.length === 0) {
    throw new Error("selected must contain at least one source");
  }
  const payload: Record<string, unknown> = { selected };
  if (req.readiness_by_source != null) {
    payload.readiness_by_source = req.readiness_by_source;
  }
  const res = await apiFetch(`${API_BASE}/research/source-pack/build`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return parseSourcePackResult(await readOkBody(res));
}

export function formatSourcePackSummary(r: SourcePackResult): string {
  return (
    `included=${r.included_count}/${r.selected.length} · ` +
    `live_fetch=${r.live_fetch_authorized} · ${r.authority}`
  );
}
