import { describe, expect, it } from "vitest";
import { hydrateLiveGateReadiness } from "./hydrateLiveGateReadiness";

describe("hydrateLiveGateReadiness (ave)", () => {
  it("is offline-honest when both legs deferred", () => {
    const r = hydrateLiveGateReadiness({});
    expect(r.offline_honest).toBe(true);
    expect(r.any_live_ready).toBe(false);
    expect(r.arxiv.live_ready).toBe(false);
    expect(r.substack.live_ready).toBe(false);
    expect(r.never_enables_live).toBe(true);
    expect(r.html_first).toBe(true);
    expect(r.dual_gate).toBe("L1-L2");
    expect(r.summary).toMatch(/offline-honest/i);
  });

  it("requires both env and injector for arxiv L1 live_ready", () => {
    const envOnly = hydrateLiveGateReadiness({
      arxiv_env_enabled: true,
      arxiv_injector_installed: false,
    });
    expect(envOnly.arxiv.live_ready).toBe(false);
    expect(envOnly.offline_honest).toBe(true);

    const both = hydrateLiveGateReadiness({
      arxiv_env_enabled: true,
      arxiv_injector_installed: true,
    });
    expect(both.arxiv.live_ready).toBe(true);
    expect(both.any_live_ready).toBe(true);
    expect(both.offline_honest).toBe(false);
    expect(both.arxiv.dual_gate).toBe("L1");
  });

  it("tracks substack L2 independently", () => {
    const r = hydrateLiveGateReadiness({
      substack_env_enabled: true,
      substack_injector_installed: true,
      arxiv_env_enabled: false,
      arxiv_injector_installed: false,
    });
    expect(r.substack.live_ready).toBe(true);
    expect(r.arxiv.live_ready).toBe(false);
    expect(r.any_live_ready).toBe(true);
    expect(r.offline_honest).toBe(false);
    expect(r.substack.dual_gate).toBe("L2");
  });

  it("preserves env flags", () => {
    const r = hydrateLiveGateReadiness({
      arxiv_env_flag: "ANTIEK_HYDRATE_LIVE_ARXIV",
      substack_env_flag: "ANTIEK_HYDRATE_LIVE_SUBSTACK",
    });
    expect(r.arxiv.env_flag).toBe("ANTIEK_HYDRATE_LIVE_ARXIV");
    expect(r.substack.env_flag).toBe("ANTIEK_HYDRATE_LIVE_SUBSTACK");
  });
});
