import { describe, expect, it } from "vitest";
import { moilLiveStepGateReadiness } from "./moilLiveStepGateReadiness";

describe("moilLiveStepGateReadiness (avg)", () => {
  it("is offline-honest by default", () => {
    const r = moilLiveStepGateReadiness({});
    expect(r.live_ready).toBe(false);
    expect(r.offline_honest).toBe(true);
    expect(r.never_enables_live).toBe(true);
    expect(r.dual_gate).toBe("L4");
  });

  it("requires env + injector + offline_honest=false", () => {
    expect(
      moilLiveStepGateReadiness({
        live_env: true,
        injector_installed: true,
        offline_honest: true,
      }).live_ready,
    ).toBe(false);

    const r = moilLiveStepGateReadiness({
      live_env: true,
      injector_installed: true,
      offline_honest: false,
    });
    expect(r.live_ready).toBe(true);
    expect(r.offline_honest).toBe(false);
    expect(r.summary).toMatch(/live-step ready/i);
  });
});
