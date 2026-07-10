import { describe, expect, it } from "vitest";
import { twinChaseSelectionReadiness } from "./twinChaseSelectionReadiness";

describe("twinChaseSelectionReadiness (auq)", () => {
  it("is not chase_ready without selection", () => {
    const r = twinChaseSelectionReadiness({});
    expect(r.chase_ready).toBe(false);
    expect(r.has_selection).toBe(false);
    expect(r.html_first).toBe(true);
  });

  it("is chase_ready with selection and clear budget", () => {
    const r = twinChaseSelectionReadiness({ selected_count: 3 });
    expect(r.chase_ready).toBe(true);
    expect(r.selected_count).toBe(3);
    expect(r.budget_blocks).toBe(false);
    expect(r.chase_title).toMatch(/never PDF/i);
  });

  it("soft-blocks when budget would exceed without force", () => {
    const blocked = twinChaseSelectionReadiness({
      selected_count: 2,
      budget_would_exceed: true,
      force_over_budget: false,
    });
    expect(blocked.chase_ready).toBe(false);
    expect(blocked.budget_blocks).toBe(true);
    const forced = twinChaseSelectionReadiness({
      selected_count: 2,
      budget_would_exceed: true,
      force_over_budget: true,
    });
    expect(forced.chase_ready).toBe(true);
    expect(forced.summary).toMatch(/force/i);
  });
});
