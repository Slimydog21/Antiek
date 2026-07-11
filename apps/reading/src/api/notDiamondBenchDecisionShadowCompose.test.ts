import { describe, expect, it } from "vitest";
import {
  composeNotDiamondBenchDecisionShadow,
  formatNotDiamondBenchDecisionShadowSummary,
} from "./notDiamondBenchDecisionShadowCompose";

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
      score: 0.88,
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
      score: 0.25,
    },
  ];
}

describe("composeNotDiamondBenchDecisionShadow", () => {
  it("bench + ND agree with kill switch off", () => {
    const c = composeNotDiamondBenchDecisionShadow({
      week_id: "2026-W28",
      focus_task: "deep_research",
      events: eventsDeepResearch(),
      models,
      daily_cap_usd: 20,
      spent_usd: 4,
      projected_cost_usd_high: 0.5,
      nd_recommended_model_id: "gpt-5.5",
      kill_switch_on: false,
      nd_confidence: 0.8,
      operator_ack: true,
    });
    expect(c.bench_rec.recommendation?.recommended_model_id).toBe("gpt-5.5");
    expect(c.nd_shadow.shadow_visible).toBe(true);
    expect(c.bench_vs_nd).toBe("agree");
    expect(c.production_router_verdict).toBe("REJECT");
    expect(c.live_router_authorized).toBe(false);
    expect(c.pack_ready).toBe(true);
    expect(c.authority).toBe(
      "notdiamond_bench_decision_shadow_compose_advisory",
    );
    expect(formatNotDiamondBenchDecisionShadowSummary(c)).toMatch(
      /production_router_verdict=REJECT/,
    );
  });

  it("kill switch hides ND", () => {
    const c = composeNotDiamondBenchDecisionShadow({
      week_id: "2026-W28",
      focus_task: "deep_research",
      events: eventsDeepResearch(),
      models,
      daily_cap_usd: 20,
      spent_usd: 4,
      nd_recommended_model_id: "mimo-v2",
      kill_switch_on: true,
      operator_ack: true,
    });
    expect(c.nd_shadow.shadow_visible).toBe(false);
    expect(c.bench_vs_nd).toBe("nd_hidden");
    expect(c.production_router_verdict).toBe("REJECT");
    expect(c.live_router_authorized).toBe(false);
  });

  it("bench vs ND disagree still advisory", () => {
    const c = composeNotDiamondBenchDecisionShadow({
      week_id: "2026-W28",
      focus_task: "deep_research",
      events: eventsDeepResearch(),
      models,
      daily_cap_usd: 20,
      spent_usd: 4,
      nd_recommended_model_id: "mimo-v2",
      kill_switch_on: false,
      operator_ack: true,
    });
    expect(c.bench_vs_nd).toBe("disagree");
    expect(c.nd_shadow.suggested_model_id).toBe("mimo-v2");
    // operator selection not auto-switched to ND
    expect(c.operator_selected_model_id).toBe("gpt-5.5");
    expect(c.live_router_authorized).toBe(false);
    expect(c.production_router_verdict).toBe("REJECT");
  });

  it("operator explicit selection preserved", () => {
    const c = composeNotDiamondBenchDecisionShadow({
      week_id: "2026-W28",
      focus_task: "deep_research",
      events: eventsDeepResearch(),
      models,
      selected_model_id: "grok-4.5",
      daily_cap_usd: 20,
      spent_usd: 4,
      nd_recommended_model_id: "gpt-5.5",
      kill_switch_on: false,
      operator_ack: true,
    });
    expect(c.operator_selected_model_id).toBe("grok-4.5");
    expect(c.live_router_authorized).toBe(false);
  });

  it("ack false blocks pack_ready", () => {
    const c = composeNotDiamondBenchDecisionShadow({
      week_id: "2026-W28",
      focus_task: "deep_research",
      events: eventsDeepResearch(),
      models,
      daily_cap_usd: 20,
      spent_usd: 4,
      nd_recommended_model_id: "gpt-5.5",
      kill_switch_on: false,
      operator_ack: false,
    });
    expect(c.pack_ready).toBe(false);
    expect(c.production_router_verdict).toBe("REJECT");
  });
});
