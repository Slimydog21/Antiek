import { describe, expect, it } from "vitest";
import {
  composeSettingsModelDriverTab,
  formatSettingsModelDriverTabSummary,
} from "./settingsModelDriverTabCompose";

const models = [
  {
    model_id: "flash-1",
    tier: "flash",
    projected_cost_usd_high: 0.5,
    projected_cost_usd_low: 0.1,
  },
  {
    model_id: "pro-1",
    tier: "pro",
    projected_cost_usd_high: 3,
    projected_cost_usd_low: 1,
  },
];

describe("composeSettingsModelDriverTab", () => {
  it("composes tab without live router or secrets", () => {
    const t = composeSettingsModelDriverTab({
      selected_model_id: "flash-1",
      models,
      daily_cap_usd: 10,
      spent_usd: 2,
      bench_bests: [
        { task: "deep_research", best_model_id: "pro-1", score: 0.9 },
      ],
      focus_task: "deep_research",
      nd_shadow: {
        recommended_model_id: "pro-1",
        kill_switch_on: false,
        confidence: 0.7,
      },
      pending_add_model_ids: ["local-llama"],
    });
    expect(t.live_router_authorized).toBe(false);
    expect(t.secrets_stored).toBe(false);
    expect(t.tab_ready).toBe(true);
    expect(t.bench_aligned).toBe(false);
    expect(t.bench_best_for_focus).toBe("pro-1");
    expect(t.nd_shadow_differs).toBe(true);
    expect(t.nd_shadow_model).toBe("pro-1");
    expect(t.pending_add_count).toBe(1);
    expect(t.decision.would_exceed).toBe(false);
    expect(t.authority).toBe("settings_model_driver_tab_compose_advisory");
    expect(formatSettingsModelDriverTabSummary(t)).toMatch(
      /live_router_authorized=false/,
    );
  });

  it("suppresses ND when kill switch on", () => {
    const t = composeSettingsModelDriverTab({
      selected_model_id: "flash-1",
      models,
      daily_cap_usd: 10,
      spent_usd: 2,
      nd_shadow: {
        recommended_model_id: "pro-1",
        kill_switch_on: true,
      },
    });
    expect(t.nd_shadow_differs).toBeNull();
    expect(t.nd_shadow_model).toBeNull();
    expect(t.live_router_authorized).toBe(false);
    expect(t.notes.some((n) => n.includes("kill_switch_on"))).toBe(true);
  });

  it("rejects secret-like pending add ids", () => {
    expect(() =>
      composeSettingsModelDriverTab({
        selected_model_id: "flash-1",
        models,
        daily_cap_usd: null,
        spent_usd: null,
        pending_add_model_ids: ["sk-abc123secret"],
      }),
    ).toThrow(/secret material/);
  });

  it("bench aligned when selected matches best", () => {
    const t = composeSettingsModelDriverTab({
      selected_model_id: "pro-1",
      models,
      daily_cap_usd: 10,
      spent_usd: 1,
      bench_bests: [
        { task: "deep_research", best_model_id: "pro-1", score: 0.95 },
      ],
      focus_task: "deep_research",
    });
    expect(t.bench_aligned).toBe(true);
    expect(t.secrets_stored).toBe(false);
    expect(t.live_router_authorized).toBe(false);
  });

  it("would_exceed null honesty when costs unknown", () => {
    const t = composeSettingsModelDriverTab({
      selected_model_id: "flash-1",
      models: [{ model_id: "flash-1", tier: "flash" }],
      daily_cap_usd: 10,
      spent_usd: 2,
    });
    expect(t.decision.would_exceed).toBeNull();
    expect(t.live_router_authorized).toBe(false);
  });
});
