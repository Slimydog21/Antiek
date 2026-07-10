import { describe, expect, it } from "vitest";
import { registerModelReadiness } from "./registerModelReadiness";

describe("registerModelReadiness (auv)", () => {
  it("is not register_ready when both empty", () => {
    const r = registerModelReadiness({});
    expect(r.register_ready).toBe(false);
    expect(r.block_reason).toBe("missing_both");
    expect(r.never_auto_route).toBe(true);
    expect(r.register_title).toMatch(/model id and provider id/i);
  });

  it("is not register_ready without model", () => {
    const r = registerModelReadiness({ provider_id: "zai" });
    expect(r.register_ready).toBe(false);
    expect(r.block_reason).toBe("no_model");
    expect(r.register_title).toMatch(/model id/i);
  });

  it("is not register_ready without provider", () => {
    const r = registerModelReadiness({ model_id: "glm-5.2" });
    expect(r.register_ready).toBe(false);
    expect(r.block_reason).toBe("no_provider");
    expect(r.register_title).toMatch(/provider id/i);
  });

  it("is register_ready with both ids (registry only)", () => {
    const r = registerModelReadiness({
      model_id: "glm-5.2",
      provider_id: "zai",
    });
    expect(r.register_ready).toBe(true);
    expect(r.block_reason).toBe("ok");
    expect(r.select_as_driver).toBe(false);
    expect(r.summary).toMatch(/registry only/i);
    expect(r.register_title).toMatch(/Register zai\/glm-5\.2/i);
  });

  it("records select_as_driver and never auto-route", () => {
    const r = registerModelReadiness({
      model_id: "  stub-strong  ",
      provider_id: "  offline-stub  ",
      select_as_driver: true,
    });
    expect(r.register_ready).toBe(true);
    expect(r.model_id).toBe("stub-strong");
    expect(r.provider_id).toBe("offline-stub");
    expect(r.select_as_driver).toBe(true);
    expect(r.summary).toMatch(/decision-tree driver/i);
    expect(r.summary).toMatch(/never auto-route/i);
    expect(r.install_is_decision_tree_only).toBe(true);
  });
});
