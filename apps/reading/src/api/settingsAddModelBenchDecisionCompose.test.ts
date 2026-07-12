import { describe, expect, it } from "vitest";
import {
  composeSettingsAddModelBenchDecision,
  formatSettingsAddModelBenchDecisionSummary,
} from "./settingsAddModelBenchDecisionCompose";

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

describe("composeSettingsAddModelBenchDecision", () => {
  it("add-model + bench decision ready with usage bar", () => {
    const c = composeSettingsAddModelBenchDecision({
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
      existing_tasks: ["deep_research"],
    });
    expect(c.add_model.pack_ready).toBe(true);
    expect(c.bench_rec.pack_ready).toBe(true);
    expect(c.pack_ready).toBe(true);
    expect(c.bench_rec.recommendation?.recommended_model_id).toBe("gpt-5.5");
    expect(c.bench_rec.decision_tree.would_exceed).toBe(false);
    expect(c.secrets_stored).toBe(false);
    expect(c.inventory_mutated).toBe(false);
    expect(c.live_router_authorized).toBe(false);
    expect(c.suite_rewritten).toBe(false);
    expect(c.authority).toBe(
      "settings_add_model_bench_decision_compose_advisory",
    );
    expect(formatSettingsAddModelBenchDecisionSummary(c)).toMatch(
      /live_router_authorized=false/,
    );
  });

  it("would_exceed projection on decision tree", () => {
    const c = composeSettingsAddModelBenchDecision({
      models,
      pending_add_model_ids: ["mimo-v2"],
      action: "preview",
      week_id: "2026-W28",
      focus_task: "deep_research",
      events: eventsDeepResearch(),
      decision_models,
      daily_cap_usd: 1,
      spent_usd: 0.9,
      projected_cost_usd_high: 0.5,
      operator_ack: true,
    });
    expect(c.bench_rec.decision_tree.would_exceed).toBe(true);
    expect(c.live_router_authorized).toBe(false);
    // pack may still be ready — projection is advisory
    expect(c.secrets_stored).toBe(false);
  });

  it("operator_ack false blocks", () => {
    const c = composeSettingsAddModelBenchDecision({
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
    });
    expect(c.pack_ready).toBe(false);
    expect(c.inventory_mutated).toBe(false);
  });

  it("propose_add with bench recommend", () => {
    const c = composeSettingsAddModelBenchDecision({
      models: [{ model_id: "gpt-5.5" }],
      pending_add_model_ids: ["mimo-v2"],
      action: "propose_add",
      week_id: "2026-W28",
      focus_task: "deep_research",
      events: eventsDeepResearch(),
      decision_models,
      daily_cap_usd: 15,
      spent_usd: 2,
      projected_cost_usd_high: 0.3,
      operator_ack: true,
    });
    expect(c.add_model.proposed_new_count).toBe(1);
    expect(c.add_model.pack_ready).toBe(true);
    expect(c.bench_rec.pack_ready).toBe(true);
    expect(c.pack_ready).toBe(true);
    expect(c.inventory_mutated).toBe(false);
  });
});
