import { describe, expect, it } from "vitest";
import {
  composeNotDiamondShadowAdvisory,
  formatNotDiamondShadowAdvisorySummary,
} from "./notDiamondShadowAdvisoryCompose";

describe("composeNotDiamondShadowAdvisory", () => {
  it("rejects production router and never authorizes live routing", () => {
    const c = composeNotDiamondShadowAdvisory({
      selected_model_id: "gpt-5",
      nd_recommended_model_id: "claude-opus",
      kill_switch_on: false,
      confidence: 0.72,
      task: "deep_research",
      inventory_model_ids: ["gpt-5", "claude-opus", "mimo"],
    });
    expect(c.production_router_verdict).toBe("REJECT");
    expect(c.live_router_authorized).toBe(false);
    expect(c.shadow_visible).toBe(true);
    expect(c.differs_from_selected).toBe(true);
    expect(c.suggested_model_id).toBe("claude-opus");
    expect(c.authority).toBe("notdiamond_shadow_advisory_only");
    expect(formatNotDiamondShadowAdvisorySummary(c)).toMatch(/REJECT/);
  });

  it("suppresses shadow when kill switch on", () => {
    const c = composeNotDiamondShadowAdvisory({
      selected_model_id: "gpt-5",
      nd_recommended_model_id: "claude-opus",
      kill_switch_on: true,
      inventory_model_ids: ["gpt-5", "claude-opus"],
    });
    expect(c.shadow_visible).toBe(false);
    expect(c.differs_from_selected).toBeNull();
    expect(c.suggested_model_id).toBeNull();
    expect(c.live_router_authorized).toBe(false);
    expect(c.production_router_verdict).toBe("REJECT");
  });

  it("does not invent recommendation when null", () => {
    const c = composeNotDiamondShadowAdvisory({
      selected_model_id: "gpt-5",
      nd_recommended_model_id: null,
      kill_switch_on: false,
    });
    expect(c.shadow_visible).toBe(false);
    expect(c.suggested_model_id).toBeNull();
    expect(c.live_router_authorized).toBe(false);
  });

  it("fails closed when recommended not in inventory", () => {
    const c = composeNotDiamondShadowAdvisory({
      selected_model_id: "gpt-5",
      nd_recommended_model_id: "unknown-model",
      kill_switch_on: false,
      inventory_model_ids: ["gpt-5", "claude-opus"],
    });
    expect(c.shadow_visible).toBe(false);
    expect(c.suggested_model_id).toBeNull();
  });

  it("rejects secret-like ids and non-bool kill switch", () => {
    expect(() =>
      composeNotDiamondShadowAdvisory({
        selected_model_id: "gpt-5",
        nd_recommended_model_id: "sk-abc123secret",
        kill_switch_on: false,
      }),
    ).toThrow(/secret|model id/i);
    expect(() =>
      composeNotDiamondShadowAdvisory({
        selected_model_id: "gpt-5",
        nd_recommended_model_id: "x",
        // @ts-expect-error intentional
        kill_switch_on: "yes",
      }),
    ).toThrow(/kill_switch_on/);
  });

  it("agrees with selected: visible, no suggestion, still REJECT", () => {
    const c = composeNotDiamondShadowAdvisory({
      selected_model_id: "gpt-5",
      nd_recommended_model_id: "gpt-5",
      kill_switch_on: false,
    });
    expect(c.shadow_visible).toBe(true);
    expect(c.differs_from_selected).toBe(false);
    expect(c.suggested_model_id).toBeNull();
    expect(c.production_router_verdict).toBe("REJECT");
    expect(c.live_router_authorized).toBe(false);
  });
});
