import { describe, expect, it } from "vitest";
import { twinSeedLiveGateReadiness } from "./twinSeedLiveGateReadiness";

describe("twinSeedLiveGateReadiness (avf)", () => {
  it("is offline-honest by default", () => {
    const r = twinSeedLiveGateReadiness({});
    expect(r.live_ready).toBe(false);
    expect(r.offline_honest).toBe(true);
    expect(r.never_enables_live).toBe(true);
    expect(r.dual_gate).toBe("L3");
    expect(r.summary).toMatch(/deferred|offline-honest/i);
  });

  it("requires all four gates for live_ready", () => {
    const almost = twinSeedLiveGateReadiness({
      live_env: true,
      use_dispatch: true,
      injector_installed: true,
      offline_honest: true,
    });
    expect(almost.live_ready).toBe(false);

    const ready = twinSeedLiveGateReadiness({
      live_env: true,
      use_dispatch: true,
      injector_installed: true,
      offline_honest: false,
    });
    expect(ready.live_ready).toBe(true);
    expect(ready.offline_honest).toBe(false);
    expect(ready.summary).toMatch(/live ready/i);
  });

  it("fails when injector missing even if env on", () => {
    const r = twinSeedLiveGateReadiness({
      live_env: true,
      use_dispatch: true,
      injector_installed: false,
      offline_honest: false,
    });
    expect(r.live_ready).toBe(false);
    expect(r.summary).toMatch(/injector/i);
  });
});
