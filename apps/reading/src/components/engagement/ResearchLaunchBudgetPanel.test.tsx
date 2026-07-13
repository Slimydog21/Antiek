import { describe, expect, it, vi, beforeEach, afterEach } from "vitest";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { ResearchLaunchBudgetPanel } from "./ResearchLaunchBudgetPanel";

const {
  fetchSettingsBudget,
  estimatePromptCost,
  fetchDecisionTreeSelection,
  fetchAntiekBenchLeaderboard,
  installDecisionTreeSelection,
} = vi.hoisted(() => ({
  fetchSettingsBudget: vi.fn<(options?: unknown) => unknown>(async () => ({
    daily_cap_usd: 5,
    spent_usd: 1,
    remaining_usd: 4,
    spent_status: "known" as const,
    cap_env: null,
    notes: [],
  })),
  estimatePromptCost: vi.fn<(options?: unknown) => unknown>(async () => ({
    estimated_usd_low: 0.08,
    estimated_usd_high: 0.12,
    would_exceed_budget: false,
    pricing_known: true,
    notes: [],
    assumed_input_tokens: 50,
    assumed_output_tokens: 2500,
    tier: "pro",
    provider: "zai",
    model: "glm-5.2",
  })),
  fetchDecisionTreeSelection: vi.fn<(options?: unknown) => unknown>(async () => ({
    model_id: "glm-5.2",
    provider_id: "zai",
    installed: true,
    notes: [],
    source: "test",
  })),
  fetchAntiekBenchLeaderboard: vi.fn<(options?: unknown) => unknown>(async () => ({
    week_id: "2026-W28",
    models: [
      {
        model_id: "glm-5.2",
        mean_score: 0.9,
        by_task_class: { synthesize: 0.95, distill: 0.8, wrestle: 0.7 },
      },
      {
        model_id: "strong-model",
        mean_score: 0.92,
        by_task_class: { synthesize: 0.88, distill: 0.99, wrestle: 0.96 },
      },
    ],
    task_classes: ["distill", "synthesize", "wrestle"],
    run_count: 2,
    suite_versions: ["suite-competitive-dogfood-v14"],
    recommended_model_id: "strong-model",
    recommended_mean_score: 0.92,
    view_format: "html",
    settings_panel: "antiek_bench_weekly",
    source: "test",
    notes: [],
  })),
  installDecisionTreeSelection: vi.fn<(options?: unknown) => unknown>(async () => ({
    model_id: "strong-model",
    provider_id: "zai",
    installed: true,
    notes: [],
    source: "test",
  })),
}));

vi.mock("../../api/settings", () => ({
  fetchSettingsBudget,
  estimatePromptCost,
  fetchDecisionTreeSelection,
  fetchAntiekBenchLeaderboard,
  installDecisionTreeSelection,
}));

describe("ResearchLaunchBudgetPanel", () => {
  beforeEach(() => {
    fetchSettingsBudget.mockClear();
    estimatePromptCost.mockClear();
    fetchDecisionTreeSelection.mockClear();
    fetchAntiekBenchLeaderboard.mockClear();
    installDecisionTreeSelection.mockClear();
    vi.useFakeTimers({ shouldAdvanceTime: true });
  });

  afterEach(() => {
    cleanup();
    vi.useRealTimers();
  });

  it("shows budget bar and decision-tree driver", async () => {
    render(
      <ResearchLaunchBudgetPanel
        promptText="What is attention?"
        researchTier="deep"
        debounceMs={0}
      />,
    );
    await waitFor(() => {
      expect(screen.getByTestId("research-launch-budget-panel")).toBeTruthy();
    });
    expect(fetchSettingsBudget).toHaveBeenCalled();
    expect(fetchDecisionTreeSelection).toHaveBeenCalled();
    await waitFor(() => {
      expect(
        screen.getByTestId("research-launch-decision-tree").textContent,
      ).toMatch(/zai\s*\/\s*glm-5\.2/);
    });
    expect(screen.getByTestId("research-launch-budget-bar").textContent).toMatch(
      /\$1\.00/,
    );
    expect(screen.getByTestId("research-launch-budget-bar-fill")).toBeTruthy();
    // Residual (fr): Settings deep-link for cap + decision-tree.
    const settings = screen.getByTestId("research-launch-budget-settings-link");
    const dual = screen.getByTestId(
      "research-launch-budget-dual-gate-checklist-link",
    );
    // Residual (aaz): deep-link L7 ND advisory-only section (parity driver badge).
    expect(dual.getAttribute("href")).toBe("/settings#notdiamond-advisory");
    expect(dual.textContent).toMatch(/L7 ND advisory/i);
    // Residual (ym): launch budget dual-gate honesty stamps (parity DecisionTree yl).
    expect(dual.getAttribute("data-offline-default")).toBe("true");
    expect(dual.getAttribute("data-l7-notdiamond")).toBe("advisory_only");
    // Residual (sc): deep-link to decision-tree panel (driver + budget foresight).
    expect(settings.getAttribute("href")).toBe("/settings#decision-tree-panel");
    expect(settings.textContent).toMatch(/driver/i);
    // Residual (ajm): budget-before-fire chokepoint → competitive DR honesty map.
    expect(
      screen
        .getByTestId("research-launch-budget-competitive-scorecard-link")
        .getAttribute("href"),
    ).toBe("/settings#settings-competitive-dr-scorecard");
    expect(
      screen
        .getByTestId("research-launch-budget-competitive-scorecard-link")
        .textContent,
    ).toMatch(/competitive DR scorecard/i);
    expect(
      screen
        .getByTestId("research-launch-budget-competitive-dr-future-agent-link")
        .getAttribute("href") || "",
    ).toBe("/settings#settings-competitive-dr-scorecard");
    // Residual (akp): launch foresight → full Settings prompt-cost projection panel.
    expect(
      screen
        .getByTestId("research-launch-budget-prompt-cost-projection-link")
        .getAttribute("href"),
    ).toBe("/settings#prompt-cost-projection");
    expect(
      screen.getByTestId("research-launch-budget-prompt-cost-projection-link")
        .textContent,
    ).toMatch(/prompt-cost projection/i);
    // Residual (afb): deep→synthesize best-by-task advisory (never auto-route).
    await waitFor(() => {
      expect(fetchAntiekBenchLeaderboard).toHaveBeenCalled();
    });
    await waitFor(() => {
      expect(screen.getByTestId("research-launch-bench-best-by-task")).toBeTruthy();
    });
    const bench = screen.getByTestId("research-launch-bench-best-by-task");
    expect(bench.getAttribute("data-task-class")).toBe("synthesize");
    expect(bench.getAttribute("data-best-model")).toBe("glm-5.2");
    expect(bench.getAttribute("data-advisory-only")).toBe("true");
    expect(bench.getAttribute("data-matches-installed")).toBe("true");
    expect(screen.getByTestId("research-launch-bench-task-class").textContent).toBe(
      "synthesize",
    );
    expect(screen.getByTestId("research-launch-bench-best-model").textContent).toBe(
      "glm-5.2",
    );
    expect(
      screen.getByTestId("research-launch-bench-leaderboard-link").getAttribute("href"),
    ).toBe("/settings#antiek-bench-leaderboard");
    expect(
      screen.getByTestId("research-launch-budget-panel").getAttribute("data-bench-task-class"),
    ).toBe("synthesize");
  });

  it("maps wrestle tier to bench best-by-task wrestle model (afb)", async () => {
    render(
      <ResearchLaunchBudgetPanel
        promptText="Wrestle with citations"
        researchTier="wrestle"
        debounceMs={0}
      />,
    );
    await waitFor(() => {
      expect(screen.getByTestId("research-launch-bench-best-by-task")).toBeTruthy();
    });
    const bench = screen.getByTestId("research-launch-bench-best-by-task");
    expect(bench.getAttribute("data-task-class")).toBe("wrestle");
    // strong-model has higher wrestle score (0.96 > 0.7).
    expect(bench.getAttribute("data-best-model")).toBe("strong-model");
    expect(bench.getAttribute("data-matches-installed")).toBe("false");
    expect(bench.getAttribute("data-install-available")).toBe("true");
    expect(bench.textContent).toMatch(/differs from installed/i);
    // Residual (aff): explicit install on launch budget (parity badge afe).
    const installBtn = screen.getByTestId("research-launch-install-best-for-task");
    expect(installBtn.getAttribute("data-install-model-id")).toBe("strong-model");
    expect(installBtn.getAttribute("data-install-task-class")).toBe("wrestle");
    await userEvent.setup().click(installBtn);
    await waitFor(() => {
      expect(installDecisionTreeSelection).toHaveBeenCalledWith({
        model_id: "strong-model",
        provider_id: "zai",
      });
    });
    await waitFor(() => {
      expect(
        screen.getByTestId("research-launch-install-best-status").textContent,
      ).toMatch(/Installed strong-model for wrestle/i);
    });
  });

  it("projects prompt cost for deep→pro tier", async () => {
    render(
      <ResearchLaunchBudgetPanel
        promptText="Trace the evolution of transformers across my corpus."
        researchTier="deep"
        debounceMs={0}
      />,
    );
    await waitFor(() => {
      expect(estimatePromptCost).toHaveBeenCalled();
    });
    const call = estimatePromptCost.mock.calls.at(-1)?.[0] as {
      tier?: string;
      input_chars?: number;
      expected_output_tokens?: number;
      model?: string | null;
    };
    expect(call.tier).toBe("pro");
    // Residual (hp): machine-readable projection metrics for budget-before-fire.
    await waitFor(() => {
      expect(
        screen.getByTestId("research-launch-projection-metrics"),
      ).toBeTruthy();
    });
    const metrics = screen.getByTestId("research-launch-projection-metrics");
    expect(metrics.getAttribute("data-dispatch-tier")).toBe("pro");
    expect(metrics.getAttribute("data-research-tier")).toBe("deep");
    expect(Number(metrics.getAttribute("data-prompt-chars"))).toBeGreaterThan(
      3,
    );
    expect(metrics.getAttribute("data-view-format")).toBe("html");
    expect(metrics.textContent).toMatch(/Projection metrics/);
    // Residual (atg): competitive duration band on launch projection (parity atf).
    expect(metrics.getAttribute("data-long-horizon")).toBe("false");
    expect(metrics.getAttribute("data-long-horizon-label")).toMatch(/deep/i);
    expect(metrics.getAttribute("data-long-horizon-band")).toMatch(/3–10|3-10/);
    expect(metrics.textContent).toMatch(/deep synthesize band/i);
    expect(call.expected_output_tokens).toBe(2500);
    expect(call.input_chars).toBeGreaterThan(3);
    expect(call.model).toBe("glm-5.2");
    await waitFor(() => {
      expect(
        screen.getByTestId("research-launch-would-exceed").getAttribute(
          "data-would-exceed",
        ),
      ).toBe("false");
    });
    expect(screen.getByTestId("research-launch-projection").textContent).toMatch(
      /\$0\.08/,
    );
  });

  it("maps fast research tier to flash projection", async () => {
    render(
      <ResearchLaunchBudgetPanel
        promptText="Quick check on citations"
        researchTier="fast"
        debounceMs={0}
      />,
    );
    await waitFor(() => {
      expect(estimatePromptCost).toHaveBeenCalled();
    });
    const call = estimatePromptCost.mock.calls.at(-1)?.[0] as {
      tier?: string;
      expected_output_tokens?: number;
    };
    expect(call.tier).toBe("flash");
    expect(call.expected_output_tokens).toBe(800);
    expect(
      screen
        .getByTestId("research-launch-budget-panel")
        .getAttribute("data-dispatch-tier"),
    ).toBe("flash");
  });

  it("maps wrestle research tier to wrestle projection (gm)", async () => {
    render(
      <ResearchLaunchBudgetPanel
        promptText="Wrestle with a multi-hop research question carefully"
        researchTier="wrestle"
        debounceMs={0}
      />,
    );
    await waitFor(() => {
      expect(estimatePromptCost).toHaveBeenCalled();
    });
    const call = estimatePromptCost.mock.calls.at(-1)?.[0] as {
      tier?: string;
      expected_output_tokens?: number;
    };
    expect(call.tier).toBe("wrestle");
    expect(call.expected_output_tokens).toBe(4000);
    expect(
      screen
        .getByTestId("research-launch-budget-panel")
        .getAttribute("data-dispatch-tier"),
    ).toBe("wrestle");
    expect(
      screen
        .getByTestId("research-launch-budget-panel")
        .getAttribute("data-research-tier"),
    ).toBe("wrestle");
  });

  it("tier picker switches projection to wrestle (gm)", async () => {
    const onTier = vi.fn();
    render(
      <ResearchLaunchBudgetPanel
        promptText="Depth tier picker should re-project cost"
        researchTier="deep"
        allowTierPick
        onResearchTierChange={onTier}
        debounceMs={0}
      />,
    );
    await waitFor(() => {
      expect(screen.getByTestId("research-launch-tier-picker")).toBeTruthy();
    });
    expect(
      screen
        .getByTestId("research-launch-budget-panel")
        .getAttribute("data-allow-tier-pick"),
    ).toBe("true");
    expect(
      screen.getByTestId("research-launch-tier-deep").getAttribute("data-selected"),
    ).toBe("true");
    estimatePromptCost.mockClear();
    await userEvent.click(screen.getByTestId("research-launch-tier-wrestle"));
    expect(onTier).toHaveBeenCalledWith("wrestle");
    await waitFor(() => {
      expect(estimatePromptCost).toHaveBeenCalled();
    });
    const call = estimatePromptCost.mock.calls.at(-1)?.[0] as {
      tier?: string;
      expected_output_tokens?: number;
    };
    expect(call.tier).toBe("wrestle");
    expect(call.expected_output_tokens).toBe(4000);
    expect(
      screen
        .getByTestId("research-launch-tier-wrestle")
        .getAttribute("data-selected"),
    ).toBe("true");
  });

  it("flags would_exceed_budget when API says true", async () => {
    estimatePromptCost.mockResolvedValueOnce({
      estimated_usd_low: 3,
      estimated_usd_high: 5,
      would_exceed_budget: true,
      pricing_known: true,
      notes: [],
      assumed_input_tokens: 100,
      assumed_output_tokens: 2500,
      tier: "pro",
      provider: null,
      model: null,
    });
    render(
      <ResearchLaunchBudgetPanel
        promptText="Very expensive deep research question with lots of text here"
        researchTier="deep"
        debounceMs={0}
      />,
    );
    await waitFor(() => {
      expect(
        screen.getByTestId("research-launch-would-exceed").getAttribute(
          "data-would-exceed",
        ),
      ).toBe("true");
    });
    expect(screen.getByTestId("research-launch-would-exceed").textContent).toMatch(
      /exceed/i,
    );
  });

  it("surfaces remaining-after-prompt projection (wa)", async () => {
    // remaining_usd=4, high=0.12 → remaining after ≈ 3.88
    render(
      <ResearchLaunchBudgetPanel
        promptText="Project remaining daily budget after this research launch prompt"
        researchTier="deep"
        debounceMs={0}
      />,
    );
    await waitFor(() => {
      expect(screen.getByTestId("research-launch-remaining-after")).toBeTruthy();
    });
    const after = screen.getByTestId("research-launch-remaining-after");
    expect(after.getAttribute("data-remaining-after-usd")).toBe("3.88");
    expect(after.textContent).toMatch(/Remaining after prompt/i);
    expect(after.textContent).toMatch(/\$3\.88/);
    expect(
      screen
        .getByTestId("research-launch-projection-metrics")
        .getAttribute("data-remaining-after-usd"),
    ).toBe("3.88");
  });

  it("flags over remaining when high band exceeds remaining (wa)", async () => {
    estimatePromptCost.mockResolvedValueOnce({
      estimated_usd_low: 3,
      estimated_usd_high: 5,
      would_exceed_budget: true,
      pricing_known: true,
      notes: [],
      assumed_input_tokens: 100,
      assumed_output_tokens: 2500,
      tier: "pro",
      provider: null,
      model: null,
    });
    render(
      <ResearchLaunchBudgetPanel
        promptText="Over-budget high band research prompt that burns past remaining"
        researchTier="deep"
        debounceMs={0}
      />,
    );
    await waitFor(() => {
      expect(screen.getByTestId("research-launch-remaining-after")).toBeTruthy();
    });
    const after = screen.getByTestId("research-launch-remaining-after");
    // remaining 4 − high 5 = −1
    expect(after.getAttribute("data-remaining-after-usd")).toBe("-1");
    // Residual (aeb): machine-readable goes-negative foresight.
    expect(after.getAttribute("data-goes-negative")).toBe("true");
    expect(
      screen
        .getByTestId("research-launch-projection-metrics")
        .getAttribute("data-goes-negative"),
    ).toBe("true");
    expect(after.textContent).toMatch(/over remaining high-band/i);
    expect(after.textContent).toMatch(/soft foresight/i);
  });

  it("notifies parent via onProjectionChange (de)", async () => {
    const onProjectionChange = vi.fn();
    estimatePromptCost.mockResolvedValueOnce({
      estimated_usd_low: 3,
      estimated_usd_high: 5,
      would_exceed_budget: true,
      pricing_known: true,
      notes: [],
      assumed_input_tokens: 100,
      assumed_output_tokens: 2500,
      tier: "pro",
      provider: null,
      model: null,
    });
    render(
      <ResearchLaunchBudgetPanel
        promptText="Expensive collective deep research prompt for projection callback"
        researchTier="deep"
        debounceMs={0}
        onProjectionChange={onProjectionChange}
      />,
    );
    await waitFor(() => {
      expect(onProjectionChange).toHaveBeenCalled();
    });
    await waitFor(() => {
      const last = onProjectionChange.mock.calls.at(-1)?.[0] as {
        wouldExceedBudget: boolean | null;
        pricingKnown: boolean;
        modelId: string | null;
      };
      expect(last.wouldExceedBudget).toBe(true);
      expect(last.pricingKnown).toBe(true);
      expect(last.modelId).toBe("glm-5.2");
    });
  });

  it("surfaces intensity factor chrome for wrestle tier (jw)", () => {
    render(
      <ResearchLaunchBudgetPanel
        promptText="Wrestle intensity projection chrome"
        researchTier="wrestle"
        allowTierPick
        debounceMs={0}
      />,
    );
    const intensity = screen.getByTestId("research-launch-tier-intensity");
    expect(intensity.getAttribute("data-research-tier")).toBe("wrestle");
    expect(intensity.getAttribute("data-intensity-multiplier")).toBe("2");
    expect(intensity.getAttribute("data-expected-output-tokens")).toBe("4000");
    expect(intensity.textContent).toMatch(/2\.0× \(wrestle\)/);
    expect(intensity.textContent).toMatch(/4000 out tokens/);
  });

  it("does not project when prompt shorter than 3 chars", async () => {
    render(
      <ResearchLaunchBudgetPanel
        promptText="hi"
        researchTier="deep"
        debounceMs={0}
      />,
    );
    await waitFor(() => {
      expect(fetchSettingsBudget).toHaveBeenCalled();
    });
    // Give debounce a tick
    await vi.advanceTimersByTimeAsync(50);
    expect(estimatePromptCost).not.toHaveBeenCalled();
    expect(screen.getByTestId("research-launch-projection").textContent).toMatch(
      /≥3 chars/,
    );
  });
});
