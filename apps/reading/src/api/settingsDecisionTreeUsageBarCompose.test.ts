import { describe, expect, it } from "vitest";
import {
  composeSettingsDecisionTreeUsageBar,
  formatSettingsDecisionTreeUsageBarSummary,
} from "./settingsDecisionTreeUsageBarCompose";

const MODELS = [
  {
    model_id: "gpt-5",
    tier: "frontier",
    projected_cost_usd_high: 2,
    projected_cost_usd_low: 1,
  },
  { model_id: "composer-2.5", tier: "workhorse", projected_cost_usd_high: 0.5 },
];

describe("composeSettingsDecisionTreeUsageBar", () => {
  it("decision ready with usage percent and projection", () => {
    const c = composeSettingsDecisionTreeUsageBar({
      selected_model_id: "gpt-5",
      models: MODELS,
      daily_cap_usd: 100,
      spent_usd: 40,
      projected_cost_usd_high: 2,
      projected_cost_usd_low: 1,
      operator_ack: true,
    });
    expect(c.decision_ready).toBe(true);
    expect(c.usage_percent).toBe(40);
    expect(c.remaining_usd).toBe(60);
    expect(c.would_exceed).toBe(false);
    expect(c.live_router_authorized).toBe(false);
    expect(c.secrets_stored).toBe(false);
    expect(c.live_meter_read).toBe(false);
    expect(c.authority).toBe(
      "settings_decision_tree_usage_bar_compose_advisory",
    );
    const s = formatSettingsDecisionTreeUsageBarSummary(c);
    expect(s).toMatch(/live_router_authorized=false/);
    expect(s).toMatch(/secrets_stored=false/);
    expect(s).toMatch(/live_meter_read=false/);
  });

  it("would_exceed true when high cost exceeds remaining", () => {
    const c = composeSettingsDecisionTreeUsageBar({
      selected_model_id: "gpt-5",
      models: MODELS,
      daily_cap_usd: 10,
      spent_usd: 9,
      projected_cost_usd_high: 5,
      operator_ack: true,
    });
    expect(c.would_exceed).toBe(true);
    expect(c.usage_percent).toBe(90);
    expect(c.live_router_authorized).toBe(false);
  });

  it("usage_percent null when cap unknown", () => {
    const c = composeSettingsDecisionTreeUsageBar({
      selected_model_id: "gpt-5",
      models: MODELS,
      daily_cap_usd: null,
      spent_usd: 5,
      projected_cost_usd_high: 1,
      operator_ack: true,
    });
    expect(c.usage_percent).toBeNull();
    expect(c.would_exceed).toBeNull();
    expect(c.decision_ready).toBe(true);
  });

  it("ack false not decision_ready", () => {
    const c = composeSettingsDecisionTreeUsageBar({
      selected_model_id: "gpt-5",
      models: MODELS,
      daily_cap_usd: 100,
      spent_usd: 10,
      operator_ack: false,
    });
    expect(c.decision_ready).toBe(false);
  });

  it("rejects unknown selected model", () => {
    expect(() =>
      composeSettingsDecisionTreeUsageBar({
        selected_model_id: "nope",
        models: MODELS,
        daily_cap_usd: 10,
        spent_usd: 1,
        operator_ack: true,
      }),
    ).toThrow(/not found/);
  });
});
