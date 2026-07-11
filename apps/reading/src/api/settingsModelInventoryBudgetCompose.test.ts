import { describe, expect, it } from "vitest";
import {
  composeSettingsModelInventoryBudget,
  formatSettingsModelInventoryBudgetSummary,
} from "./settingsModelInventoryBudgetCompose";

describe("composeSettingsModelInventoryBudget", () => {
  it("composes inventory and bar without secrets or router", () => {
    const c = composeSettingsModelInventoryBudget({
      models: [
        { model_id: "gpt-5", tier: "frontier", provider: "openai" },
        { model_id: "claude-opus", tier: "frontier", provider: "anthropic" },
      ],
      pending_add_model_ids: ["mimo-pro"],
      daily_cap_usd: 50,
      spent_usd: 12.5,
      selected_model_id: "gpt-5",
    });
    expect(c.inventory_count).toBe(2);
    expect(c.pending_add_count).toBe(1);
    expect(c.selected_in_inventory).toBe(true);
    expect(c.bar.remaining_usd).toBe(37.5);
    expect(c.secrets_stored).toBe(false);
    expect(c.live_router_authorized).toBe(false);
    expect(formatSettingsModelInventoryBudgetSummary(c)).toMatch(
      /secrets_stored=false/,
    );
  });

  it("rejects secret-like ids and unknown remaining honesty", () => {
    expect(() =>
      composeSettingsModelInventoryBudget({
        models: [{ model_id: "sk-abc123secret" }],
        daily_cap_usd: 10,
        spent_usd: 1,
      }),
    ).toThrow(/secret|model id/i);

    const unk = composeSettingsModelInventoryBudget({
      models: [{ model_id: "gpt-5" }],
      daily_cap_usd: null,
      spent_usd: null,
    });
    expect(unk.bar.remaining_usd).toBeNull();
    expect(unk.secrets_stored).toBe(false);
  });
});
