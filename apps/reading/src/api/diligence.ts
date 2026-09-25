/**
 * diligence.ts — the diligence-queue client (autonomous-diligence SPR-01).
 *
 * POST /diligence/flags (idempotent — 201 created, 200 the existing row),
 * GET /diligence/queue (the owner's flags, newest first), POST dismiss.
 * Refs only: a flag carries the object's stable ref, an optional short
 * note, and source ids — never the object's text beyond its ref.
 */
import { API_BASE, ApiError, apiFetch } from "../lib/api";

export type DiligenceKind = "concept" | "open_question" | "insight";
export type DiligenceStatus = "queued" | "spawned" | "dismissed" | "done";

export interface DiligenceFlag {
  flag_id: string;
  kind: DiligenceKind;
  object_ref: string;
  note: string | null;
  source_investigation_id: string | null;
  source_document_id: string | null;
  status: DiligenceStatus;
  spawned_investigation_id: string | null;
  created_at: string;
  updated_at: string;
}

export interface CreateFlagBody {
  kind: DiligenceKind;
  object_ref: string;
  note?: string | null;
  source_investigation_id?: string | null;
  source_document_id?: string | null;
}

async function throwIfNotOk(resp: Response, what: string): Promise<void> {
  if (!resp.ok) {
    throw new ApiError(
      `${what} failed: HTTP ${resp.status}`,
      resp.status,
      await resp.text(),
    );
  }
}

/** Flag an object for diligence. `created` is false when the server
 *  returned the EXISTING row (idempotent re-flag). */
export async function createFlag(
  body: CreateFlagBody,
): Promise<{ flag: DiligenceFlag; created: boolean }> {
  const resp = await apiFetch(`${API_BASE}/diligence/flags`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  await throwIfNotOk(resp, "POST /diligence/flags");
  return { flag: (await resp.json()) as DiligenceFlag, created: resp.status === 201 };
}

export async function getQueue(): Promise<{ flags: DiligenceFlag[]; count: number }> {
  const resp = await apiFetch(`${API_BASE}/diligence/queue`);
  await throwIfNotOk(resp, "GET /diligence/queue");
  const raw = (await resp.json()) as { flags?: unknown; count?: unknown };
  // Boundary validation: a malformed body is an honest error state, never
  // a crash rendering a non-row.
  if (!Array.isArray(raw.flags)) {
    throw new ApiError("GET /diligence/queue: malformed response body", 0, JSON.stringify(raw));
  }
  return { flags: raw.flags as DiligenceFlag[], count: raw.flags.length };
}

export async function dismissFlag(flagId: string): Promise<DiligenceFlag> {
  const resp = await apiFetch(
    `${API_BASE}/diligence/flags/${encodeURIComponent(flagId)}/dismiss`,
    { method: "POST" },
  );
  await throwIfNotOk(resp, "POST /diligence/flags/{id}/dismiss");
  return (await resp.json()) as DiligenceFlag;
}

/** The queue-changed signal: fired after a successful flag/dismiss so any
 *  mounted rail refetches (same-tab convergence; the server is the truth). */
export const DILIGENCE_CHANGED_EVENT = "antiek:diligence-changed";

export function notifyDiligenceChanged(): void {
  window.dispatchEvent(new Event(DILIGENCE_CHANGED_EVENT));
}
