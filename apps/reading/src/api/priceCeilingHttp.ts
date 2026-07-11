/**
 * HTTP client for Midnight Oil price-ceiling recommend (#831).
 *
 * POST /midnight-oil/price-ceiling/recommend
 *
 * Fail-closed: authority must be "advisory". Never invents spend capacity.
 */

import { API_BASE, apiFetch } from "../lib/api";

export interface PriceCeilingHttpRequest {
  hours: number;
  goals?: string[] | number;
  usd_per_hour_low?: number;
  usd_per_hour_high?: number;
  usd_per_goal?: number;
  contingency_fraction?: number;
}

export interface PriceCeilingHttpResult {
  hours: number;
  goal_count: number;
  recommended_ceiling_usd: number;
  low_usd: number;
  high_usd: number;
  authority: "advisory";
  notes: string[];
}

export class PriceCeilingHttpError extends Error {
  readonly status: number;
  readonly body: string;
  constructor(status: number, body: string) {
    super(`price-ceiling API ${status}: ${body.slice(0, 200)}`);
    this.name = "PriceCeilingHttpError";
    this.status = status;
    this.body = body;
  }
}

async function readOkBody(res: Response): Promise<unknown> {
  if (!res.ok) {
    const text = await res.text();
    throw new PriceCeilingHttpError(res.status, text);
  }
  return res.json() as Promise<unknown>;
}

function requireFinite(name: string, v: unknown): number {
  if (typeof v !== "number" || !Number.isFinite(v)) {
    throw new Error(`price-ceiling response rejected: ${name} must be finite number`);
  }
  if (v < 0) {
    throw new Error(`price-ceiling response rejected: ${name} must be nonnegative`);
  }
  return v;
}

export function parsePriceCeilingHttpResult(body: unknown): PriceCeilingHttpResult {
  if (!body || typeof body !== "object") {
    throw new Error("price-ceiling response must be an object");
  }
  const o = body as Record<string, unknown>;
  if (o.authority !== "advisory") {
    throw new Error(
      "price-ceiling response rejected: authority must be advisory",
    );
  }
  if (!Array.isArray(o.notes)) {
    throw new Error("price-ceiling response rejected: notes must be array");
  }
  for (let i = 0; i < o.notes.length; i++) {
    if (typeof o.notes[i] !== "string") {
      throw new Error(`price-ceiling response rejected: notes[${i}] must be string`);
    }
  }
  if (typeof o.goal_count !== "number" || !Number.isInteger(o.goal_count) || o.goal_count < 0) {
    throw new Error("price-ceiling response rejected: goal_count must be nonnegative int");
  }
  return {
    hours: requireFinite("hours", o.hours),
    goal_count: o.goal_count,
    recommended_ceiling_usd: requireFinite(
      "recommended_ceiling_usd",
      o.recommended_ceiling_usd,
    ),
    low_usd: requireFinite("low_usd", o.low_usd),
    high_usd: requireFinite("high_usd", o.high_usd),
    authority: "advisory",
    notes: o.notes as string[],
  };
}

export async function postPriceCeilingRecommend(
  req: PriceCeilingHttpRequest,
): Promise<PriceCeilingHttpResult> {
  if (typeof req.hours !== "number" || !Number.isFinite(req.hours)) {
    throw new Error("hours must be a finite number");
  }
  const res = await apiFetch(`${API_BASE}/midnight-oil/price-ceiling/recommend`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      hours: req.hours,
      goals: req.goals ?? [],
      usd_per_hour_low: req.usd_per_hour_low ?? 1,
      usd_per_hour_high: req.usd_per_hour_high ?? 5,
      usd_per_goal: req.usd_per_goal ?? 0.5,
      contingency_fraction: req.contingency_fraction ?? 0.15,
    }),
  });
  const raw = await readOkBody(res);
  return parsePriceCeilingHttpResult(raw);
}
