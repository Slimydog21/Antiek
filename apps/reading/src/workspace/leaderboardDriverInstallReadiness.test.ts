import { describe, expect, it } from "vitest";
import {
  leaderboardDriverInstallReadiness,
  resolveLeaderboardInstallProvider,
} from "./leaderboardDriverInstallReadiness";

describe("leaderboardDriverInstallReadiness (auu)", () => {
  it("is not install_ready without model id", () => {
    const r = leaderboardDriverInstallReadiness({
      provider_id: "offline-stub",
    });
    expect(r.install_ready).toBe(false);
    expect(r.block_reason).toBe("no_model");
    expect(r.never_auto_route).toBe(true);
    expect(r.advisory_only).toBe(true);
    expect(r.bench_is_dispatch_authority).toBe(false);
    expect(r.install_title).toMatch(/No model id/i);
  });

  it("is not install_ready without provider", () => {
    const r = leaderboardDriverInstallReadiness({
      model_id: "stub-strong",
    });
    expect(r.install_ready).toBe(false);
    expect(r.block_reason).toBe("no_provider");
    expect(r.install_title).toMatch(/Select a provider/i);
  });

  it("is install_ready with model + provider", () => {
    const r = leaderboardDriverInstallReadiness({
      model_id: "stub-strong",
      provider_id: "offline-stub",
    });
    expect(r.install_ready).toBe(true);
    expect(r.block_reason).toBe("ok");
    expect(r.summary).toMatch(/decision-tree only/i);
    expect(r.install_title).toMatch(/never auto-route/i);
    expect(r.install_is_decision_tree_only).toBe(true);
  });

  it("includes task_class in title when present", () => {
    const r = leaderboardDriverInstallReadiness({
      model_id: "glm-5.2",
      provider_id: "zai",
      task_class: "deep_research",
    });
    expect(r.install_ready).toBe(true);
    expect(r.task_class).toBe("deep_research");
    expect(r.install_title).toMatch(/best-for-deep_research/i);
    expect(r.summary).toMatch(/task=deep_research/);
  });

  it("trims whitespace", () => {
    const r = leaderboardDriverInstallReadiness({
      model_id: "  a  ",
      provider_id: "  b  ",
    });
    expect(r.model_id).toBe("a");
    expect(r.provider_id).toBe("b");
    expect(r.install_ready).toBe(true);
  });
});

describe("resolveLeaderboardInstallProvider (auu)", () => {
  it("prefers selected provider", () => {
    expect(
      resolveLeaderboardInstallProvider({
        selected_provider_id: "  zai  ",
        models: [{ provider_id: "other", ready: true }],
      }),
    ).toBe("zai");
  });

  it("falls back to first ready model provider", () => {
    expect(
      resolveLeaderboardInstallProvider({
        selected_provider_id: "",
        models: [
          { provider_id: "cold", ready: false },
          { provider_id: "hot", ready: true },
        ],
      }),
    ).toBe("hot");
  });

  it("falls back to first inventory provider when none ready", () => {
    expect(
      resolveLeaderboardInstallProvider({
        models: [{ provider_id: "only" }],
      }),
    ).toBe("only");
  });

  it("returns empty when nothing available", () => {
    expect(resolveLeaderboardInstallProvider({})).toBe("");
    expect(resolveLeaderboardInstallProvider({ models: [] })).toBe("");
  });
});
