import { describe, expect, it } from "vitest";
import { depthTierApplyReadiness } from "./depthTierApplyReadiness";

describe("depthTierApplyReadiness (avc)", () => {
  it("is not apply_ready without tier", () => {
    const r = depthTierApplyReadiness({});
    expect(r.apply_ready).toBe(false);
    expect(r.block_reason).toBe("no_tier");
    expect(r.never_auto_route).toBe(true);
    expect(r.html_first).toBe(true);
    expect(r.apply_title).toMatch(/Select a depth tier/i);
  });

  it("is apply_ready with tier alone (hints only)", () => {
    const r = depthTierApplyReadiness({ depth_tier: "wrestle" });
    expect(r.apply_ready).toBe(true);
    expect(r.will_install_driver).toBe(false);
    expect(r.summary).toMatch(/projection hints only/i);
    expect(r.apply_title).toMatch(/never auto-route/i);
  });

  it("records will_install_driver when model present", () => {
    const r = depthTierApplyReadiness({
      depth_tier: "  pro  ",
      model_id: "  glm-5.2  ",
      provider_id: "  zai  ",
    });
    expect(r.apply_ready).toBe(true);
    expect(r.depth_tier).toBe("pro");
    expect(r.will_install_driver).toBe(true);
    expect(r.summary).toMatch(/zai\/glm-5\.2/);
    expect(r.apply_title).toMatch(/install selected model/i);
  });
});
