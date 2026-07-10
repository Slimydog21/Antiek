import { describe, expect, it } from "vitest";
import { clearDecisionTreeReadiness } from "./clearDecisionTreeReadiness";

describe("clearDecisionTreeReadiness (auw)", () => {
  it("is not clear_ready when nothing installed", () => {
    const r = clearDecisionTreeReadiness({});
    expect(r.clear_ready).toBe(false);
    expect(r.block_reason).toBe("not_installed");
    expect(r.never_auto_route).toBe(true);
    expect(r.notdiamond_authority).toBe("advisory_only");
    expect(r.clear_title).toMatch(/No decision-tree driver/i);
  });

  it("is clear_ready when installed flag is true", () => {
    const r = clearDecisionTreeReadiness({
      installed: true,
      model_id: "glm-5.2",
      provider_id: "zai",
    });
    expect(r.clear_ready).toBe(true);
    expect(r.block_reason).toBe("ok");
    expect(r.summary).toMatch(/zai\/glm-5\.2/);
    expect(r.clear_title).toMatch(/never auto-route/i);
  });

  it("is clear_ready when model_id present even if installed flag false", () => {
    const r = clearDecisionTreeReadiness({
      installed: false,
      model_id: "stub-strong",
    });
    expect(r.clear_ready).toBe(true);
    expect(r.is_installed).toBe(true);
    expect(r.summary).toMatch(/stub-strong/);
  });

  it("trims whitespace", () => {
    const r = clearDecisionTreeReadiness({
      model_id: "  a  ",
      provider_id: "  b  ",
    });
    expect(r.model_id).toBe("a");
    expect(r.provider_id).toBe("b");
    expect(r.clear_ready).toBe(true);
  });
});
