import { describe, expect, it } from "vitest";
import {
  budgetStatusText,
  dualCapNote,
  formatRemaining,
  formatSpendAmount,
  resolveSpendBasis,
  spendAmountLabel,
  spendBasisNote,
  spendPct,
  type BudgetHonestyFields,
} from "./budgetHonesty";

function base(over: Partial<BudgetHonestyFields> = {}): BudgetHonestyFields {
  return {
    daily_cap_usd: 200,
    spent_usd: 4,
    remaining_usd: 196,
    spent_status: "known",
    cap_env: "ANTIEK_OPERATOR_BUDGET_USD",
    notes: [],
    reserved_estimated_usd: 4,
    spend_basis: "reserved_estimate",
    enforcement_cap_usd: 5,
    enforcement_cap_env: null,
    caps_aligned: false,
    over_budget: false,
    ...over,
  };
}

describe("budgetHonesty helpers", () => {
  it("labels reserved estimate, never settled spend", () => {
    const b = base();
    expect(resolveSpendBasis(b)).toBe("reserved_estimate");
    expect(spendAmountLabel(b)).toBe("Reserved (est.)");
    expect(formatSpendAmount(b)).toBe("$4.0000");
    expect(spendBasisNote(b)).toMatch(/not settled provider cost/i);
  });

  it("surfaces dual display vs enforcement caps when misaligned", () => {
    const note = dualCapNote(base());
    expect(note).toBeTruthy();
    expect(note!).toContain("$200.00");
    expect(note!).toContain("$5.00");
    expect(note!).toMatch(/enforcement/i);
    expect(dualCapNote(base({ caps_aligned: true }))).toBeNull();
  });

  it("formats signed remaining and over-budget status", () => {
    const over = base({
      daily_cap_usd: 2,
      remaining_usd: -2,
      over_budget: true,
      spent_usd: 4,
      reserved_estimated_usd: 4,
    });
    expect(formatRemaining(over)).toBe("$-2.0000 (over display cap)");
    expect(budgetStatusText(over)).toBe("cap exceeded");
    expect(spendPct(over)).toBe(100);
  });

  it("keeps unknown spend as unknown — never invents $0", () => {
    const unknown = base({
      spent_usd: null,
      remaining_usd: null,
      spent_status: "unknown",
      spend_basis: "unknown",
      reserved_estimated_usd: null,
    });
    expect(formatSpendAmount(unknown)).toMatch(/unknown/i);
    // Must not present a numeric $0.0000 spend figure as known.
    expect(formatSpendAmount(unknown)).not.toMatch(/^\$0(\.0+)?$/);
    expect(formatSpendAmount(unknown)).not.toBe("$0.0000");
    expect(budgetStatusText(unknown)).toBe("spend unknown");
    expect(spendPct(unknown)).toBeNull();
  });

  it("back-compat: known spend without spend_basis still treated as reserved", () => {
    const legacy: BudgetHonestyFields = {
      daily_cap_usd: 5,
      spent_usd: 1.25,
      remaining_usd: 3.75,
      spent_status: "known",
      cap_env: null,
      notes: [],
    };
    expect(resolveSpendBasis(legacy)).toBe("reserved_estimate");
    expect(spendAmountLabel(legacy)).toBe("Reserved (est.)");
  });
});
