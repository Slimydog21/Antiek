import { describe, expect, it } from "vitest";
import {
  inventoryToDecisionModels,
  preferReadyModels,
} from "./modelDecisionInventory";

describe("inventoryToDecisionModels", () => {
  it("returns empty for null/empty inventory", () => {
    expect(inventoryToDecisionModels(null)).toEqual([]);
    expect(inventoryToDecisionModels([])).toEqual([]);
  });

  it("maps ready rows with tier inference", () => {
    const models = inventoryToDecisionModels([
      {
        provider_id: "anthropic",
        ready: true,
        primary_model: "claude-opus",
        tier_bindings: ["reasoning", "smart"],
      },
      {
        provider_id: "openai",
        ready: true,
        primary_model: "gpt-mini",
        tier_bindings: ["flash"],
        usd_per_1k_tokens: 0.002,
      },
    ]);
    expect(models).toHaveLength(2);
    expect(models[0]).toMatchObject({
      model_id: "claude-opus",
      provider: "anthropic",
      tier: "reasoning",
      enabled: true,
    });
    expect(models[1]).toMatchObject({
      model_id: "gpt-mini",
      tier: "flash",
      usd_per_1k_tokens: 0.002,
      enabled: true,
    });
  });

  it("marks not-ready as disabled and skips empty primary_model", () => {
    const models = inventoryToDecisionModels([
      {
        provider_id: "x",
        ready: false,
        primary_model: "stale",
        tier_bindings: ["balanced"],
      },
      {
        provider_id: "y",
        ready: true,
        primary_model: "  ",
      },
    ]);
    expect(models).toHaveLength(1);
    expect(models[0].enabled).toBe(false);
    expect(models[0].model_id).toBe("stale");
  });
});

describe("preferReadyModels", () => {
  it("filters to ready when any exist", () => {
    const out = preferReadyModels([
      { model_id: "a", enabled: false },
      { model_id: "b", enabled: true },
    ]);
    expect(out.map((m) => m.model_id)).toEqual(["b"]);
  });

  it("keeps all when none ready", () => {
    const out = preferReadyModels([
      { model_id: "a", enabled: false },
      { model_id: "b", enabled: false },
    ]);
    expect(out).toHaveLength(2);
  });
});
