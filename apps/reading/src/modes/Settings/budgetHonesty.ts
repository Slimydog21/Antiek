/**
 * Pure honesty helpers for the Settings budget bar.
 *
 * Keeps presentation logic free of React so unit tests drive the real
 * formatters without re-implementing UI copy. Consumes the additive budget
 * honesty fields from the Settings budget API (#769).
 */

export type SpendBasis = "unknown" | "reserved_estimate";

export interface BudgetHonestyFields {
  daily_cap_usd: number | null;
  spent_usd: number | null;
  remaining_usd: number | null;
  spent_status: "known" | "unknown" | "no_cap";
  cap_env: string | null;
  notes: string[];
  reserved_estimated_usd?: number | null;
  spend_basis?: SpendBasis | null;
  enforcement_cap_usd?: number | null;
  enforcement_cap_env?: string | null;
  caps_aligned?: boolean | null;
  over_budget?: boolean | null;
}

export function resolveSpendBasis(budget: BudgetHonestyFields): SpendBasis {
  if (budget.spend_basis === "reserved_estimate") return "reserved_estimate";
  if (budget.spend_basis === "unknown") return "unknown";
  // Back-compat when API predates honesty fields: known spend is still only
  // a reserved estimate on the daemon sidecar path.
  if (budget.spent_status === "known" && budget.spent_usd != null) {
    return "reserved_estimate";
  }
  return "unknown";
}

/** Prefer reserved estimate when present; never invent a figure. */
export function resolvedReservedAmount(
  budget: BudgetHonestyFields,
): number | null {
  if (budget.spent_status !== "known") return null;
  const amount = budget.reserved_estimated_usd ?? budget.spent_usd;
  if (amount == null || Number.isNaN(amount)) return null;
  return amount;
}

/**
 * Row label for the spend figure.
 * Never "Spent today" — that implies settled provider cost. Even unknown
 * ledgers stay reserved/ledger-oriented.
 */
export function spendAmountLabel(budget: BudgetHonestyFields): string {
  return resolveSpendBasis(budget) === "reserved_estimate"
    ? "Reserved (est.)"
    : "Reserved / ledger";
}

export function formatUsd(
  amount: number | null | undefined,
  digits = 4,
): string {
  if (amount == null || Number.isNaN(amount)) return "unknown";
  return `$${amount.toFixed(digits)}`;
}

export function formatSpendAmount(budget: BudgetHonestyFields): string {
  const amount = resolvedReservedAmount(budget);
  if (amount == null) {
    return "unknown (ledger not inventing $0)";
  }
  return formatUsd(amount, 4);
}

export function formatRemaining(budget: BudgetHonestyFields): string {
  if (budget.remaining_usd == null) return "unknown";
  const base = formatUsd(budget.remaining_usd, 4);
  if (budget.remaining_usd < 0 || budget.over_budget === true) {
    return `${base} (over display cap)`;
  }
  return base;
}

export function budgetStatusText(budget: BudgetHonestyFields): string {
  if (budget.daily_cap_usd == null) return "no cap configured";
  if (budget.spent_status !== "known") return "spend unknown";
  if (
    budget.over_budget === true ||
    (budget.remaining_usd != null && budget.remaining_usd < 0)
  ) {
    return "cap exceeded";
  }
  return "within cap";
}

export function dualCapNote(budget: BudgetHonestyFields): string | null {
  if (budget.caps_aligned === false && budget.enforcement_cap_usd != null) {
    const display =
      budget.daily_cap_usd == null
        ? "unset"
        : `$${budget.daily_cap_usd.toFixed(2)}`;
    const enforce = `$${budget.enforcement_cap_usd.toFixed(2)}`;
    const enforceEnv = budget.enforcement_cap_env ?? "daemon default";
    const displayEnv = budget.cap_env ?? "display default";
    return `Display cap ${display} (${displayEnv}) · Enforcement cap ${enforce} (${enforceEnv}) — daemon halt uses enforcement; Settings bar uses display`;
  }
  return null;
}

export function spendBasisNote(budget: BudgetHonestyFields): string | null {
  if (resolveSpendBasis(budget) === "reserved_estimate") {
    return "Reserved estimate = fixed per-spawn holds, not settled provider cost";
  }
  return null;
}

export function spendPct(budget: BudgetHonestyFields): number | null {
  const reserved = resolvedReservedAmount(budget);
  if (
    budget.daily_cap_usd == null ||
    reserved == null ||
    budget.daily_cap_usd <= 0
  ) {
    return null;
  }
  // Cap the visual bar at 100; over-budget is shown via remaining + status text.
  // Uses the same resolved reserved amount as the visible figure.
  return Math.min(100, (reserved / budget.daily_cap_usd) * 100);
}
