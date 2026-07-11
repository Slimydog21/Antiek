/**
 * Midnight Oil unattended brief client.
 *
 * POST /midnight-oil/unattended/brief
 *
 * Validates operator time+goals+ceiling. Never invents live execution auth.
 */

import { API_BASE, apiFetch } from "../lib/api";

export interface UnattendedBriefRequest {
  duration_minutes: number;
  goals: string[];
  approved_ceiling_cents: number;
  recommended_ceiling_cents?: number | null;
}

export interface UnattendedBriefResult {
  duration_minutes: number;
  goals: string[];
  approved_ceiling_cents: number;
  recommended_ceiling_cents: number | null;
  notes: string[];
  live_execution_authorized: boolean;
  authority: string;
}

export class UnattendedBriefHttpError extends Error {
  readonly status: number;
  readonly body: string;

  constructor(status: number, body: string) {
    super(`unattended-brief API ${status}: ${body.slice(0, 200)}`);
    this.name = "UnattendedBriefHttpError";
    this.status = status;
    this.body = body;
  }
}

async function readOkBody(res: Response): Promise<unknown> {
  if (!res.ok) {
    const text = await res.text();
    throw new UnattendedBriefHttpError(res.status, text);
  }
  return res.json() as Promise<unknown>;
}

export function parseUnattendedBriefResult(body: unknown): UnattendedBriefResult {
  if (!body || typeof body !== "object") {
    throw new Error("unattended brief response must be an object");
  }
  const o = body as Record<string, unknown>;
  if (typeof o.duration_minutes !== "number" || !Number.isFinite(o.duration_minutes)) {
    throw new Error("unattended brief rejected: duration_minutes must be finite number");
  }
  if (!Array.isArray(o.goals) || o.goals.length === 0) {
    throw new Error("unattended brief rejected: goals required");
  }
  const goals: string[] = [];
  for (const g of o.goals) {
    if (typeof g !== "string" || !g.trim()) {
      throw new Error("unattended brief rejected: every goal must be non-empty string");
    }
    goals.push(g.trim());
  }
  if (
    typeof o.approved_ceiling_cents !== "number" ||
    !Number.isFinite(o.approved_ceiling_cents)
  ) {
    throw new Error(
      "unattended brief rejected: approved_ceiling_cents must be finite number",
    );
  }
  if (typeof o.live_execution_authorized !== "boolean") {
    throw new Error(
      "unattended brief rejected: live_execution_authorized must be boolean",
    );
  }
  // Fail closed: never accept a forged live authorization as success path
  // for this client — live spend requires separate consent residual.
  if (o.live_execution_authorized === true) {
    throw new Error(
      "unattended brief rejected: live_execution_authorized=true is not accepted by this client",
    );
  }
  if (typeof o.authority !== "string" || !o.authority.trim()) {
    throw new Error("unattended brief rejected: authority must be non-empty string");
  }
  if (!Array.isArray(o.notes)) {
    throw new Error("unattended brief rejected: notes must be an array");
  }
  const notes = o.notes.map((n) => {
    if (typeof n !== "string") {
      throw new Error("unattended brief rejected: every note must be a string");
    }
    return n;
  });
  let recommended: number | null = null;
  if (o.recommended_ceiling_cents !== null && o.recommended_ceiling_cents !== undefined) {
    if (
      typeof o.recommended_ceiling_cents !== "number" ||
      !Number.isFinite(o.recommended_ceiling_cents)
    ) {
      throw new Error(
        "unattended brief rejected: recommended_ceiling_cents must be finite number|null",
      );
    }
    recommended = o.recommended_ceiling_cents;
  }
  return {
    duration_minutes: o.duration_minutes,
    goals,
    approved_ceiling_cents: o.approved_ceiling_cents,
    recommended_ceiling_cents: recommended,
    notes,
    live_execution_authorized: false,
    authority: o.authority.trim(),
  };
}

export async function postUnattendedBrief(
  req: UnattendedBriefRequest,
): Promise<UnattendedBriefResult> {
  if (
    typeof req.duration_minutes !== "number" ||
    !Number.isFinite(req.duration_minutes) ||
    req.duration_minutes <= 0
  ) {
    throw new Error("duration_minutes must be a positive finite number");
  }
  const goals = (req.goals || []).map((g) => String(g).trim()).filter(Boolean);
  if (goals.length === 0) {
    throw new Error("goals must contain at least one goal");
  }
  if (
    typeof req.approved_ceiling_cents !== "number" ||
    !Number.isFinite(req.approved_ceiling_cents)
  ) {
    throw new Error("approved_ceiling_cents must be a finite number");
  }

  const payload: Record<string, unknown> = {
    duration_minutes: Math.trunc(req.duration_minutes),
    goals,
    approved_ceiling_cents: Math.trunc(req.approved_ceiling_cents),
  };
  if (
    req.recommended_ceiling_cents != null &&
    Number.isFinite(req.recommended_ceiling_cents)
  ) {
    payload.recommended_ceiling_cents = Math.trunc(req.recommended_ceiling_cents);
  }

  const res = await apiFetch(`${API_BASE}/midnight-oil/unattended/brief`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  const raw = await readOkBody(res);
  return parseUnattendedBriefResult(raw);
}

export function formatUnattendedSummary(r: UnattendedBriefResult): string {
  return (
    `${r.duration_minutes} min · ${r.goals.length} goal(s) · ` +
    `ceiling ${r.approved_ceiling_cents}¢ · live=${r.live_execution_authorized}`
  );
}
