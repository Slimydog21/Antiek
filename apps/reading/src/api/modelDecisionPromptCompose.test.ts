import { describe, expect, it } from "vitest";
import {
  composeModelDecisionWithProjection,
  formatComposeSummary,
} from "./modelDecisionPromptCompose";

const models = [
  {
    model_id: "flash-1",
    tier: "flash",
    projected_cost_usd_low: 0.1,
    projected_cost_usd_high: 0.5,
  },
  {
    model_id: "pro-1",
    tier: "pro",
    projected_cost_usd_low: 1,
    projected_cost_usd_high: 3,
  },
];

describe("composeModelDecisionWithProjection", () => {
  it("projects exceed when high > remaining", () => {
    const r = composeModelDecisionWithProjection({
      selected_model_id: "pro-1",
      models,
      daily_cap_usd: 10,
      spent_usd: 8,
    });
    expect(r.would_exceed).toBe(true);
    expect(r.selected_tier).toBe("pro");
    expect(r.authority).toBe("model_decision_prompt_compose_advisory");
  });

  it("would_exceed null when remaining unknown", () => {
    const r = composeModelDecisionWithProjection({
      selected_model_id: "flash-1",
      models,
      daily_cap_usd: null,
      spent_usd: null,
    });
    expect(r.would_exceed).toBeNull();
    expect(r.bar.remaining_usd).toBeNull();
  });

  it("would_exceed null when high unknown", () => {
    const r = composeModelDecisionWithProjection({
      selected_model_id: "flash-1",
      models: [{ model_id: "flash-1", tier: "flash" }],
      daily_cap_usd: 10,
      spent_usd: 1,
    });
    expect(r.would_exceed).toBeNull();
  });

  it("rejects unknown selected model", () => {
    expect(() =>
      composeModelDecisionWithProjection({
        selected_model_id: "missing",
        models,
        daily_cap_usd: 10,
        spent_usd: 1,
      }),
    ).toThrow(/not found/);
  });

  it("rejects empty models", () => {
    expect(() =>
      composeModelDecisionWithProjection({
        selected_model_id: "x",
        models: [],
        daily_cap_usd: 1,
        spent_usd: 0,
      }),
    ).toThrow(/models/);
  });

  it("input cost override beats model option", () => {
    const r = composeModelDecisionWithProjection({
      selected_model_id: "flash-1",
      models,
      daily_cap_usd: 10,
      spent_usd: 9,
      projected_cost_usd_high: 0.5,
      projected_cost_usd_low: 0.1,
    });
    // remaining 1, high 0.5 → false
    expect(r.would_exceed).toBe(false);
  });
});

describe("formatComposeSummary", () => {
  it("summarizes", () => {
    const r = composeModelDecisionWithProjection({
      selected_model_id: "flash-1",
      models,
      daily_cap_usd: 10,
      spent_usd: 1,
    });
    expect(formatComposeSummary(r)).toMatch(/flash-1/);
    expect(formatComposeSummary(r)).toMatch(/would_exceed/);
  });
});
