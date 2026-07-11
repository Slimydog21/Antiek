import { describe, expect, it } from "vitest";
import {
  composeSettingsAddModelInventory,
  formatSettingsAddModelInventorySummary,
} from "./settingsAddModelInventoryCompose";

describe("composeSettingsAddModelInventory", () => {
  it("preview pack with inventory and pending", () => {
    const c = composeSettingsAddModelInventory({
      models: [
        { model_id: "gpt-5.5", provider: "openai" },
        { model_id: "grok-4.5", provider: "xai" },
      ],
      pending_add_model_ids: ["mimo-v2"],
      action: "preview",
      daily_cap_usd: 25,
      spent_usd: 4,
      selected_model_id: "gpt-5.5",
      operator_ack: true,
    });
    expect(c.inventory.inventory_count).toBe(2);
    expect(c.inventory.pending_add_count).toBe(1);
    expect(c.proposed_new_count).toBe(1);
    expect(c.proposed_new_model_ids).toEqual(["mimo-v2"]);
    expect(c.pack_ready).toBe(true);
    expect(c.secrets_stored).toBe(false);
    expect(c.inventory_mutated).toBe(false);
    expect(c.live_router_authorized).toBe(false);
    expect(c.authority).toBe(
      "settings_add_model_inventory_compose_advisory",
    );
    expect(formatSettingsAddModelInventorySummary(c)).toMatch(
      /inventory_mutated=false/,
    );
  });

  it("propose_add ready with new ids", () => {
    const c = composeSettingsAddModelInventory({
      models: [{ model_id: "gpt-5.5" }],
      pending_add_model_ids: ["claude-opus", "mimo-v2"],
      action: "propose_add",
      daily_cap_usd: 10,
      spent_usd: 1,
      operator_ack: true,
    });
    expect(c.proposed_new_count).toBe(2);
    expect(c.pack_ready).toBe(true);
    expect(c.decision_tree).not.toBeNull();
    expect(c.inventory_mutated).toBe(false);
    expect(c.secrets_stored).toBe(false);
  });

  it("propose_add with only duplicates not ready", () => {
    const c = composeSettingsAddModelInventory({
      models: [{ model_id: "gpt-5.5" }],
      pending_add_model_ids: ["gpt-5.5"],
      action: "propose_add",
      daily_cap_usd: 10,
      spent_usd: 0,
      operator_ack: true,
    });
    expect(c.proposed_new_count).toBe(0);
    expect(c.pack_ready).toBe(false);
    expect(c.inventory_mutated).toBe(false);
  });

  it("rejects secret-like pending id", () => {
    expect(() =>
      composeSettingsAddModelInventory({
        models: [{ model_id: "gpt-5.5" }],
        pending_add_model_ids: ["sk-abc123secret"],
        action: "preview",
        daily_cap_usd: 10,
        spent_usd: 0,
        operator_ack: true,
      }),
    ).toThrow(/secret material/);
  });

  it("operator_ack false blocks pack", () => {
    const c = composeSettingsAddModelInventory({
      models: [{ model_id: "gpt-5.5" }],
      pending_add_model_ids: ["mimo-v2"],
      action: "propose_add",
      daily_cap_usd: 10,
      spent_usd: 0,
      operator_ack: false,
    });
    expect(c.pack_ready).toBe(false);
    expect(c.live_router_authorized).toBe(false);
  });
});
