import { describe, expect, it } from "vitest";
import {
  composeAntiekBenchTaskModelRecommendation,
  formatAntiekBenchTaskModelRecommendationSummary,
} from "./antiekBenchTaskModelRecommendationCompose";

const models = [
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
    {
      event_id: "e5",
      task: "twin_notes",
      model_id: "grok-4.5",
      outcome: "worked" as const,
      score: 0.8,
    },
    {
      event_id: "e6",
      task: "twin_notes",
      model_id: "grok-4.5",
      outcome: "worked" as const,
      score: 0.75,
    },
  ];
}

describe("composeAntiekBenchTaskModelRecommendation", () => {
  it("recommends best model for focus task and wires decision tree", () => {
    const c = composeAntiekBenchTaskModelRecommendation({
      week_id: "2026-W28",
      focus_task: "deep_research",
      events: eventsDeepResearch(),
      models,
      daily_cap_usd: 20,
      spent_usd: 5,
      projected_cost_usd_high: 0.5,
      operator_ack: true,
      existing_tasks: ["deep_research", "twin_notes"],
    });
    expect(c.recommendation?.recommended_model_id).toBe("gpt-5.5");
    expect(c.decision_tree.driver.decision.selected_model_id).toBe("gpt-5.5");
    expect(c.pack_ready).toBe(true);
    expect(c.live_router_authorized).toBe(false);
    expect(c.suite_rewritten).toBe(false);
    expect(c.backlog_mutated).toBe(false);
    expect(c.store_mutated).toBe(false);
    expect(c.authority).toBe(
      "antiek_bench_task_model_recommendation_compose_advisory",
    );
    expect(formatAntiekBenchTaskModelRecommendationSummary(c)).toMatch(
      /live_router_authorized=false/,
    );
  });

  it("respects explicit selected_model_id over recommendation", () => {
    const c = composeAntiekBenchTaskModelRecommendation({
      week_id: "2026-W28",
      focus_task: "deep_research",
      events: eventsDeepResearch(),
      models,
      selected_model_id: "mimo-v2",
      daily_cap_usd: 20,
      spent_usd: 5,
      operator_ack: true,
    });
    expect(c.recommendation?.recommended_model_id).toBe("gpt-5.5");
    expect(c.decision_tree.driver.decision.selected_model_id).toBe("mimo-v2");
    expect(c.live_router_authorized).toBe(false);
  });

  it("null recommendation when insufficient events", () => {
    const c = composeAntiekBenchTaskModelRecommendation({
      week_id: "2026-W28",
      focus_task: "deep_research",
      events: [
        {
          event_id: "e1",
          task: "deep_research",
          model_id: "gpt-5.5",
          outcome: "worked",
          score: 0.9,
        },
      ],
      models,
      daily_cap_usd: 10,
      spent_usd: 1,
      operator_ack: true,
      min_events_for_recommendation: 2,
    });
    expect(c.recommendation).toBeNull();
    expect(c.live_router_authorized).toBe(false);
    expect(c.suite_rewritten).toBe(false);
  });

  it("operator_ack false blocks pack_ready", () => {
    const c = composeAntiekBenchTaskModelRecommendation({
      week_id: "2026-W28",
      focus_task: "deep_research",
      events: eventsDeepResearch(),
      models,
      daily_cap_usd: 20,
      spent_usd: 5,
      operator_ack: false,
    });
    expect(c.pack_ready).toBe(false);
    expect(c.live_router_authorized).toBe(false);
  });

  it("budget projection honesty on decision tree", () => {
    const c = composeAntiekBenchTaskModelRecommendation({
      week_id: "2026-W28",
      focus_task: "deep_research",
      events: eventsDeepResearch(),
      models,
      daily_cap_usd: 1,
      spent_usd: 0.9,
      projected_cost_usd_high: 0.5,
      operator_ack: true,
    });
    expect(c.decision_tree.would_exceed).toBe(true);
    expect(c.live_router_authorized).toBe(false);
    expect(c.live_meter_read).toBe(false);
  });
});
