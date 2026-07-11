/**
 * Midnight Oil unattended launch gate client.
 *
 * POST /midnight-oil/unattended/launch-gate
 *
 * Advisory dispatch readiness only — never invents live_execution_authorized.
 */

import { API_BASE, apiFetch } from "../lib/api";

export interface LaunchGateRequest {
  operator_approved: boolean;
  consent_receipt_id?: string | null;
  duration_minutes: number;
  goals: string[];
  approved_ceiling_cents: number;
  recommended_ceiling_cents?: number | null;
}

export interface LaunchGateDecision {
  dispatch_ready: boolean;
  live_execution_authorized: boolean;
  zero_ceiling_dry_run: boolean;
  operator_approved: boolean;
  consent_receipt_id: string | null;
  brief: Record<string, unknown>;
  reasons: string[];
  notes: string[];
  authority: string;
}

export class LaunchGateHttpError extends Error {
  readonly status: number;
  readonly body: string;
  constructor(status: number, body: string) {
    super(`unattended-launch-gate API ${status}: ${body.slice(0, 200)}`);
    this.name = "LaunchGateHttpError";
    this.status = status;
    this.body = body;
  }
}

async function readOkBody(res: Response): Promise<unknown> {
  if (!res.ok) {
    throw new LaunchGateHttpError(res.status, await res.text());
  }
  return res.json() as Promise<unknown>;
}

export function parseLaunchGateDecision(body: unknown): LaunchGateDecision {
  if (!body || typeof body !== "object") {
    throw new Error("launch gate response must be an object");
  }
  const o = body as Record<string, unknown>;
  if (typeof o.dispatch_ready !== "boolean") {
    throw new Error("launch gate rejected: dispatch_ready must be boolean");
  }
  if (typeof o.live_execution_authorized !== "boolean") {
    throw new Error(
      "launch gate rejected: live_execution_authorized must be boolean",
    );
  }
  if (o.live_execution_authorized === true) {
    throw new Error(
      "launch gate rejected: live_execution_authorized=true not accepted",
    );
  }
  if (typeof o.zero_ceiling_dry_run !== "boolean") {
    throw new Error("launch gate rejected: zero_ceiling_dry_run must be boolean");
  }
  if (typeof o.operator_approved !== "boolean") {
    throw new Error("launch gate rejected: operator_approved must be boolean");
  }
  if (typeof o.authority !== "string" || o.authority.trim() !== "launch_gate_advisory") {
    throw new Error(
      "launch gate rejected: authority must be launch_gate_advisory",
    );
  }
  if (o.consent_receipt_id !== null && typeof o.consent_receipt_id !== "string") {
    throw new Error(
      "launch gate rejected: consent_receipt_id must be string|null",
    );
  }
  if (!o.brief || typeof o.brief !== "object") {
    throw new Error("launch gate rejected: brief must be an object");
  }
  if (!Array.isArray(o.reasons) || !Array.isArray(o.notes)) {
    throw new Error("launch gate rejected: reasons/notes must be arrays");
  }
  const brief = o.brief as Record<string, unknown>;
  const ceiling = brief.approved_ceiling_cents;
  if (typeof ceiling !== "number" || !Number.isInteger(ceiling) || ceiling < 0) {
    throw new Error(
      "launch gate rejected: brief.approved_ceiling_cents must be nonnegative integer",
    );
  }
  const receipt =
    typeof o.consent_receipt_id === "string" && o.consent_receipt_id.trim()
      ? o.consent_receipt_id.trim()
      : null;
  // Trust-boundary: re-check full dispatch_ready predicate (never trust server alone).
  if (o.dispatch_ready === true) {
    if (o.operator_approved !== true) {
      throw new Error(
        "launch gate rejected: dispatch_ready=true requires operator_approved=true",
      );
    }
    if (!(ceiling === 0 || receipt !== null)) {
      throw new Error(
        "launch gate rejected: dispatch_ready=true requires ceiling==0 or consent_receipt_id",
      );
    }
  }
  return {
    dispatch_ready: o.dispatch_ready,
    live_execution_authorized: false,
    zero_ceiling_dry_run: o.zero_ceiling_dry_run,
    operator_approved: o.operator_approved,
    consent_receipt_id: receipt,
    brief,
    reasons: o.reasons.map((r) => {
      if (typeof r !== "string") throw new Error("reasons must be strings");
      return r;
    }),
    notes: o.notes.map((n) => {
      if (typeof n !== "string") throw new Error("notes must be strings");
      return n;
    }),
    authority: "launch_gate_advisory",
  };
}

export async function postUnattendedLaunchGate(
  req: LaunchGateRequest,
): Promise<LaunchGateDecision> {
  if (typeof req.operator_approved !== "boolean") {
    throw new Error("operator_approved must be an explicit boolean");
  }
  if (
    typeof req.duration_minutes !== "number" ||
    !Number.isFinite(req.duration_minutes)
  ) {
    throw new Error("duration_minutes must be a finite number");
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
    operator_approved: req.operator_approved,
    duration_minutes: Math.trunc(req.duration_minutes),
    goals,
    approved_ceiling_cents: Math.trunc(req.approved_ceiling_cents),
  };
  if (req.consent_receipt_id != null && String(req.consent_receipt_id).trim()) {
    payload.consent_receipt_id = String(req.consent_receipt_id).trim();
  }
  if (
    req.recommended_ceiling_cents != null &&
    Number.isFinite(req.recommended_ceiling_cents)
  ) {
    payload.recommended_ceiling_cents = Math.trunc(req.recommended_ceiling_cents);
  }

  const res = await apiFetch(`${API_BASE}/midnight-oil/unattended/launch-gate`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return parseLaunchGateDecision(await readOkBody(res));
}

export function formatLaunchGateSummary(d: LaunchGateDecision): string {
  return (
    `dispatch_ready=${d.dispatch_ready} · live=${d.live_execution_authorized} · ` +
    `approved=${d.operator_approved}` +
    (d.reasons.length ? ` · blocked: ${d.reasons.join("; ")}` : "")
  );
}
