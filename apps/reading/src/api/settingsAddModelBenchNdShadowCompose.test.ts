import { describe, expect, it } from "vitest";
import {
  composeSettingsAddModelBenchNdShadow,
  formatSettingsAddModelBenchNdShadowSummary,
} from "./settingsAddModelBenchNdShadowCompose";

const models = [
  { model_id: "gpt-5.5", provider: "openai" },
  { model_id: "grok-4.5", provider: "xai" },
];

const decision_models = [
  { model_id: "gpt-5.5", projected_cost_usd_high: 0.5 },
  { model_id: "grok-4.5", projected_cost_usd_high: 0.3 },
  { model_id: "mimo-v2", projected_cost_usd_high: 0.1 },
];

function eventsDeepResearch() {
  return [
    {
      event_id: "e1",
      task: "deep_research",
      model_id: "gpt-5.5",
      outcome: "worked" as const,
      score: 0.9,
    },
    {
      event_id: "e2",
      task: "deep_research",
      model_id: "gpt-5.5",
      outcome: "worked" as const,
      score: 0.85,
    },
    {
      event_id: "e3",
      task: "deep_research",
      model_id: "mimo-v2",
      outcome: "failed" as const,
      score: 0.2,
    },
    {
      event_id: "e4",
      task: "deep_research",
      model_id: "mimo-v2",
      outcome: "failed" as const,
      score: 0.3,
    },
  ];
}

describe("composeSettingsAddModelBenchNdShadow", () => {
  it("settings pack + ND shadow ready with REJECT", () => {
    const c = composeSettingsAddModelBenchNdShadow({
      models,
      pending_add_model_ids: ["mimo-v2"],
      action: "preview",
      week_id: "2026-W28",
      focus_task: "deep_research",
      events: eventsDeepResearch(),
      decision_models,
      daily_cap_usd: 20,
      spent_usd: 5,
      projected_cost_usd_high: 0.5,
      operator_ack: true,
      nd_recommended_model_id: "gpt-5.5",
      kill_switch_on: false,
      nd_confidence: 0.7,
      existing_tasks: ["deep_research"],
    });
    expect(c.settings_pack.pack_ready).toBe(true);
    expect(c.pack_ready).toBe(true);
    expect(c.production_router_verdict).toBe("REJECT");
    expect(c.live_router_authorized).toBe(false);
    expect(c.secrets_stored).toBe(false);
    expect(c.inventory_mutated).toBe(false);
    expect(c.bench_vs_nd).toBe("agree");
    expect(c.nd_shadow.production_router_verdict).toBe("REJECT");
    expect(c.authority).toBe(
      "settings_add_model_bench_nd_shadow_compose_advisory",
    );
    expect(formatSettingsAddModelBenchNdShadowSummary(c)).toMatch(
      /production_router_verdict=REJECT/,
    );
  });

  it("kill switch hides ND shadow", () => {
    const c = composeSettingsAddModelBenchNdShadow({
      models,
      pending_add_model_ids: ["mimo-v2"],
      action: "preview",
      week_id: "2026-W28",
      focus_task: "deep_research",
      events: eventsDeepResearch(),
      decision_models,
      daily_cap_usd: 20,
      spent_usd: 5,
      operator_ack: true,
      nd_recommended_model_id: "mimo-v2",
      kill_switch_on: true,
    });
    expect(c.bench_vs_nd).toBe("nd_hidden");
    expect(c.nd_shadow.shadow_visible).toBe(false);
    expect(c.production_router_verdict).toBe("REJECT");
    expect(c.pack_ready).toBe(true);
  });

  it("bench vs nd disagree still advisory", () => {
    const c = composeSettingsAddModelBenchNdShadow({
      models,
      pending_add_model_ids: ["mimo-v2"],
      action: "preview",
      week_id: "2026-W28",
      focus_task: "deep_research",
      events: eventsDeepResearch(),
      decision_models,
      daily_cap_usd: 20,
      spent_usd: 5,
      operator_ack: true,
      nd_recommended_model_id: "mimo-v2",
      kill_switch_on: false,
    });
    expect(c.bench_vs_nd).toBe("disagree");
    expect(c.live_router_authorized).toBe(false);
    expect(c.production_router_verdict).toBe("REJECT");
    // operator selection not auto-switched to ND
    expect(c.operator_selected_model_id).not.toBe("mimo-v2");
  });

  it("operator_ack false blocks pack", () => {
    const c = composeSettingsAddModelBenchNdShadow({
      models,
      pending_add_model_ids: ["mimo-v2"],
      action: "preview",
      week_id: "2026-W28",
      focus_task: "deep_research",
      events: eventsDeepResearch(),
      decision_models,
      daily_cap_usd: 20,
      spent_usd: 1,
      operator_ack: false,
      nd_recommended_model_id: "gpt-5.5",
      kill_switch_on: false,
    });
    expect(c.pack_ready).toBe(false);
    expect(c.inventory_mutated).toBe(false);
    expect(c.production_router_verdict).toBe("REJECT");
  });
});
