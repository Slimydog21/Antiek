/**
 * Prompt budget projection (pure TS mirror of model_decision.usage_bar).
 *
 * Operator vision: project how a proposed prompt would affect remaining
 * budget before send. Never invents $0 remaining or would_exceed=false when
 * unknown. Does not call providers or read live meters.
 */

export interface UsageBarSnapshot {
  daily_cap_usd: number | null;
  spent_usd: number | null;
  remaining_usd: number | null;
  over_budget: boolean | null;
  fraction_used: number | null;
  spend_basis: string;
  notes: string[];
}

export interface PromptProjection {
  projected_cost_usd_low: number | null;
  projected_cost_usd_high: number | null;
  remaining_before_usd: number | null;
  remaining_after_high_usd: number | null;
  would_exceed: boolean | null;
  notes: string[];
}

function finiteMoney(value: unknown, name: string): number | null {
  if (value === null || value === undefined) return null;
  if (typeof value !== "number" || !Number.isFinite(value)) {
    throw new Error(`${name} must be finite number or null`);
  }
  return value;
}

/**
 * Build honest usage bar from optional cap/spent (fail closed on non-finite).
 */
export function computeUsageBar(input: {
  daily_cap_usd: number | null;
  spent_usd: number | null;
  spend_basis?: string;
}): UsageBarSnapshot {
  const cap = finiteMoney(input.daily_cap_usd, "daily_cap_usd");
  const spent = finiteMoney(input.spent_usd, "spent_usd");
  const notes: string[] = [];
  if (cap === null) {
    notes.push("daily_cap_usd unknown — remaining and fraction_used are null");
  }
  if (spent === null) {
    notes.push("spent_usd unknown — remaining and fraction_used are null");
  }

  let remaining: number | null = null;
  let over: boolean | null = null;
  let fraction: number | null = null;

  if (cap !== null && spent !== null) {
    remaining = cap - spent;
    over = remaining < 0;
    if (cap > 0) {
      fraction = spent / cap;
    } else {
      notes.push("daily_cap_usd is zero — fraction_used null (not 0-faked)");
      fraction = null;
    }
    if (over) {
      notes.push(
        `over display budget by $${Math.abs(remaining).toFixed(4)} (remaining_usd is signed, not clamped to 0)`,
      );
    }
  }

  return {
    daily_cap_usd: cap,
    spent_usd: spent,
    remaining_usd: remaining,
    over_budget: over,
    fraction_used: fraction,
    spend_basis: input.spend_basis ?? "reserved_estimate",
    notes,
  };
}

/**
 * Project prompt cost against a usage bar. would_exceed is null when either
 * remaining or projected high is unknown (never invent false safety).
 */
export function projectPromptAgainstBar(
  bar: UsageBarSnapshot,
  input: {
    projected_cost_usd_low: number | null;
    projected_cost_usd_high: number | null;
  },
): PromptProjection {
  if (!bar || typeof bar !== "object") {
    throw new Error("usage bar must be an object");
  }
  // Re-validate money fields on bar (trust boundary).
  const remaining = finiteMoney(bar.remaining_usd, "remaining_usd");
  const low = finiteMoney(input.projected_cost_usd_low, "projected_cost_usd_low");
  const high = finiteMoney(input.projected_cost_usd_high, "projected_cost_usd_high");
  const notes = Array.isArray(bar.notes)
    ? bar.notes.map((n) => {
        if (typeof n !== "string") throw new Error("bar.notes must be strings");
        return n;
      })
    : [];

  let after: number | null = null;
  let would: boolean | null = null;

  if (high === null) {
    notes.push("projected_cost_usd_high unknown — would_exceed is null");
    would = null;
  } else if (remaining === null) {
    notes.push("remaining_usd unknown — would_exceed is null (not zero-faked)");
    would = null;
  } else {
    after = remaining - high;
    would = high > remaining;
    if (would) {
      notes.push(
        `projection high $${high.toFixed(4)} exceeds remaining $${remaining.toFixed(4)}`,
      );
    }
  }

  return {
    projected_cost_usd_low: low,
    projected_cost_usd_high: high,
    remaining_before_usd: remaining,
    remaining_after_high_usd: after,
    would_exceed: would,
    notes,
  };
}

export function formatProjectionSummary(p: PromptProjection): string {
  const w =
    p.would_exceed === null
      ? "would_exceed=null"
      : `would_exceed=${p.would_exceed}`;
  return (
    `high=${p.projected_cost_usd_high ?? "null"} · remaining=${p.remaining_before_usd ?? "null"} · ${w}`
  );
}
