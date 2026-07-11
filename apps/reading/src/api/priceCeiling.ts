/**
 * Pure TS Midnight Oil price-ceiling recommender (mirrors #825).
 * Offline advisory only — never spends or reserves.
 */

export interface PriceCeilingRequest {
  hours: number;
  goals: string[] | number;
  usd_per_hour_low?: number;
  usd_per_hour_high?: number;
  usd_per_goal?: number;
  contingency_fraction?: number;
}

export interface PriceCeilingRecommendation {
  hours: number;
  goal_count: number;
  recommended_ceiling_usd: number;
  low_usd: number;
  high_usd: number;
  authority: "advisory";
  notes: string[];
}

export class PriceCeilingError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "PriceCeilingError";
  }
}

function requireFiniteNonneg(name: string, val: number): number {
  if (typeof val !== "number" || !Number.isFinite(val)) {
    throw new PriceCeilingError(`${name} must be finite`);
  }
  if (val < 0) {
    throw new PriceCeilingError(`${name} must be nonnegative`);
  }
  return val;
}

export function recommendPriceCeiling(
  req: PriceCeilingRequest,
): PriceCeilingRecommendation {
  const hours = req.hours;
  if (typeof hours !== "number" || !Number.isFinite(hours)) {
    throw new PriceCeilingError("hours must be a finite number");
  }
  if (hours <= 0) {
    throw new PriceCeilingError("hours must be > 0");
  }

  let goal_count: number;
  if (typeof req.goals === "number") {
    if (!Number.isInteger(req.goals) || req.goals < 0) {
      throw new PriceCeilingError("goal_count must be a nonnegative int");
    }
    goal_count = req.goals;
  } else {
    goal_count = req.goals.filter((g) => String(g).trim()).length;
  }

  const low_rate = requireFiniteNonneg(
    "usd_per_hour_low",
    req.usd_per_hour_low ?? 1,
  );
  const high_rate = requireFiniteNonneg(
    "usd_per_hour_high",
    req.usd_per_hour_high ?? 5,
  );
  const per_goal = requireFiniteNonneg("usd_per_goal", req.usd_per_goal ?? 0.5);
  const contingency_fraction = requireFiniteNonneg(
    "contingency_fraction",
    req.contingency_fraction ?? 0.15,
  );
  if (high_rate < low_rate) {
    throw new PriceCeilingError("usd_per_hour_high must be >= usd_per_hour_low");
  }

  const goal_cost = goal_count * per_goal;
  const low = hours * low_rate + goal_cost;
  const high = hours * high_rate + goal_cost;
  const mid = (low + high) / 2;
  const contingency = mid * contingency_fraction;
  const recommended = mid + contingency;

  for (const [name, val] of [
    ["low_usd", low],
    ["high_usd", high],
    ["recommended_ceiling_usd", recommended],
  ] as const) {
    if (!Number.isFinite(val)) {
      throw new PriceCeilingError(
        `${name} overflowed to non-finite; reduce hours or unit rates`,
      );
    }
  }

  return {
    hours,
    goal_count,
    recommended_ceiling_usd: recommended,
    low_usd: low,
    high_usd: high,
    authority: "advisory",
    notes: [
      "authority=advisory — operator must approve ceiling before unattended spend",
      "no live provider rates; unit rates are injected assumptions",
      "does not reserve, debit, or call BudgetLedger",
    ],
  };
}

export function formatCeilingUsd(value: number): string {
  if (!Number.isFinite(value)) return "unknown (non-finite)";
  return `$${value.toFixed(4)}`;
}
