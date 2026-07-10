import { describe, expect, it } from "vitest";
import { decisionTreeInstallReadiness } from "./decisionTreeInstallReadiness";

describe("decisionTreeInstallReadiness (aun)", () => {
  it("is not install_ready without model id", () => {
    const r = decisionTreeInstallReadiness({});
    expect(r.install_ready).toBe(false);
    expect(r.never_auto_route).toBe(true);
    expect(r.notdiamond_authority).toBe("advisory_only");
    expect(r.install_title).toMatch(/Enter a model id/i);
  });

  it("is install_ready with model id alone", () => {
    const r = decisionTreeInstallReadiness({ model_id: "glm-5.2" });
    expect(r.install_ready).toBe(true);
    expect(r.model_id).toBe("glm-5.2");
    expect(r.has_provider_id).toBe(false);
    expect(r.summary).toMatch(/install ready/i);
    expect(r.install_title).toMatch(/never auto-route/i);
  });

  it("trims whitespace and records provider when present", () => {
    const r = decisionTreeInstallReadiness({
      model_id: "  glm-5.2  ",
      provider_id: " zai ",
    });
    expect(r.install_ready).toBe(true);
    expect(r.model_id).toBe("glm-5.2");
    expect(r.provider_id).toBe("zai");
    expect(r.summary).toMatch(/zai\/glm-5\.2/);
  });
});
