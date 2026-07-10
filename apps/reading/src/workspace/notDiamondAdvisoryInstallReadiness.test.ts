import { describe, expect, it } from "vitest";
import { notDiamondAdvisoryInstallReadiness } from "./notDiamondAdvisoryInstallReadiness";

describe("notDiamondAdvisoryInstallReadiness (aut)", () => {
  it("is not install_ready without suggested model", () => {
    const r = notDiamondAdvisoryInstallReadiness({});
    expect(r.install_ready).toBe(false);
    expect(r.block_reason).toBe("no_suggestion");
    expect(r.never_auto_route).toBe(true);
    expect(r.notdiamond_authority).toBe("advisory_only");
    expect(r.install_is_decision_tree_only).toBe(true);
    expect(r.never_dispatch_authority).toBe(true);
    expect(r.install_title).toMatch(/No advisory suggestion/i);
  });

  it("is install_ready with suggestion and no dispatch authority", () => {
    const r = notDiamondAdvisoryInstallReadiness({
      suggested_model_id: "stub-strong",
      suggested_provider_id: "offline-stub",
    });
    expect(r.install_ready).toBe(true);
    expect(r.block_reason).toBe("ok");
    expect(r.suggested_model_id).toBe("stub-strong");
    expect(r.has_suggested_provider).toBe(true);
    expect(r.summary).toMatch(/install ready/i);
    expect(r.summary).toMatch(/decision-tree only/i);
    expect(r.install_title).toMatch(/never dispatch authority/i);
  });

  it("refuses when notdiamond_is_dispatch_authority is true", () => {
    const r = notDiamondAdvisoryInstallReadiness({
      suggested_model_id: "evil-router",
      notdiamond_is_dispatch_authority: true,
    });
    expect(r.install_ready).toBe(false);
    expect(r.block_reason).toBe("dispatch_authority_refused");
    expect(r.notdiamond_is_dispatch_authority).toBe(true);
    expect(r.install_title).toMatch(/never be dispatch authority/i);
    expect(r.never_dispatch_authority).toBe(true);
  });

  it("is not install_ready when installable is false", () => {
    const r = notDiamondAdvisoryInstallReadiness({
      suggested_model_id: "stub-strong",
      installable: false,
    });
    expect(r.install_ready).toBe(false);
    expect(r.block_reason).toBe("not_installable");
    expect(r.installable).toBe(false);
    expect(r.install_title).toMatch(/not installable/i);
  });

  it("trims whitespace and treats null installable as installable", () => {
    const r = notDiamondAdvisoryInstallReadiness({
      suggested_model_id: "  glm-5.2  ",
      suggested_provider_id: "  zai  ",
      installable: null,
      notdiamond_is_dispatch_authority: false,
    });
    expect(r.install_ready).toBe(true);
    expect(r.suggested_model_id).toBe("glm-5.2");
    expect(r.suggested_provider_id).toBe("zai");
    expect(r.installable).toBe(true);
    expect(r.summary).toMatch(/zai\/glm-5\.2/);
  });

  it("dispatch authority refuses even when installable false (priority)", () => {
    const r = notDiamondAdvisoryInstallReadiness({
      suggested_model_id: "x",
      notdiamond_is_dispatch_authority: true,
      installable: false,
    });
    expect(r.block_reason).toBe("dispatch_authority_refused");
    expect(r.install_ready).toBe(false);
  });
});
