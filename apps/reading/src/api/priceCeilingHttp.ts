/**
 * HTTP client for Midnight Oil price-ceiling recommend (#831).
 *
 * POST /midnight-oil/price-ceiling/recommend
 *
 * Fail-closed: authority must be "advisory". Never invents rate defaults
 * or serializes non-finite money as null.
 */

import { API_BASE, apiFetch } from "../lib/api";

export interface PriceCeilingHttpRequest {
  hours: number;
  goals?: string[] | number;
  /** Required unit rates — caller must supply; client does not invent. */
  usd_per_hour_low: number;
  usd_per_hour_high: number;
  usd_per_goal: number;
  contingency_fraction: number;
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

function requireFiniteNonneg(name: string, v: unknown): number {
  if (typeof v !== "number" || !Number.isFinite(v)) {
    throw new Error(`${name} must be a finite number`);
  }
  if (v < 0) {
    throw new Error(`${name} must be nonnegative`);
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
    hours: requireFiniteNonneg("hours", o.hours),
    goal_count: o.goal_count,
    recommended_ceiling_usd: requireFiniteNonneg(
      "recommended_ceiling_usd",
      o.recommended_ceiling_usd,
    ),
    low_usd: requireFiniteNonneg("low_usd", o.low_usd),
    high_usd: requireFiniteNonneg("high_usd", o.high_usd),
    authority: "advisory",
    notes: o.notes as string[],
  };
}

export async function postPriceCeilingRecommend(
  req: PriceCeilingHttpRequest,
): Promise<PriceCeilingHttpResult> {
  const hours = requireFiniteNonneg("hours", req.hours);
  if (hours <= 0) {
    throw new Error("hours must be > 0");
  }
  const usd_per_hour_low = requireFiniteNonneg(
    "usd_per_hour_low",
    req.usd_per_hour_low,
  );
  const usd_per_hour_high = requireFiniteNonneg(
    "usd_per_hour_high",
    req.usd_per_hour_high,
  );
  const usd_per_goal = requireFiniteNonneg("usd_per_goal", req.usd_per_goal);
  const contingency_fraction = requireFiniteNonneg(
    "contingency_fraction",
    req.contingency_fraction,
  );
  if (usd_per_hour_high < usd_per_hour_low) {
    throw new Error("usd_per_hour_high must be >= usd_per_hour_low");
  }

  const res = await apiFetch(`${API_BASE}/midnight-oil/price-ceiling/recommend`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      hours,
      goals: req.goals ?? [],
      usd_per_hour_low,
      usd_per_hour_high,
      usd_per_goal,
      contingency_fraction,
    }),
  });
  const raw = await readOkBody(res);
  return parsePriceCeilingHttpResult(raw);
}
