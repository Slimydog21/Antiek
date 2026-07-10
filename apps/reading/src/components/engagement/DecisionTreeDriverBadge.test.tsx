import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  budgetUsagePct,
  DecisionTreeDriverBadge,
} from "./DecisionTreeDriverBadge";

const fetchDecisionTreeSelection = vi.fn();
const fetchSettingsBudget = vi.fn();
const estimatePromptCost = vi.fn();
const fetchAntiekBenchLeaderboard = vi.fn();
const installDecisionTreeSelection = vi.fn();

vi.mock("../../api/settings", () => ({
  fetchDecisionTreeSelection: (...args: unknown[]) =>
    fetchDecisionTreeSelection(...args),
  fetchSettingsBudget: (...args: unknown[]) => fetchSettingsBudget(...args),
  estimatePromptCost: (...args: unknown[]) => estimatePromptCost(...args),
  fetchAntiekBenchLeaderboard: (...args: unknown[]) =>
    fetchAntiekBenchLeaderboard(...args),
  installDecisionTreeSelection: (...args: unknown[]) =>
    installDecisionTreeSelection(...args),
}));

describe("DecisionTreeDriverBadge residual cw/eq", () => {
  afterEach(() => cleanup());
  beforeEach(() => {
    fetchDecisionTreeSelection.mockReset();
    fetchSettingsBudget.mockReset();
    estimatePromptCost.mockReset();
    fetchAntiekBenchLeaderboard.mockReset();
    installDecisionTreeSelection.mockReset();
    fetchSettingsBudget.mockResolvedValue({
      daily_cap_usd: 10,
      spent_usd: 2.5,
      remaining_usd: 7.5,
      spent_status: "known",
      cap_env: "ANTIEK_DAILY_BUDGET_USD",
      notes: [],
    });
    estimatePromptCost.mockResolvedValue({
      estimated_usd_low: 0.05,
      estimated_usd_high: 0.2,
      would_exceed_budget: false,
      pricing_known: true,
      notes: [],
      assumed_input_tokens: 50,
      assumed_output_tokens: 2500,
      tier: "deep",
      provider: "zai",
      model: "glm-5.2",
    });
    fetchAntiekBenchLeaderboard.mockResolvedValue({
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
      suite_versions: [],
      recommended_model_id: "strong-model",
      recommended_mean_score: 0.92,
      view_format: "html",
      settings_panel: "antiek_bench_weekly",
      source: "test",
      notes: [],
    });
  });

  it("shows installed driver", async () => {
    fetchDecisionTreeSelection.mockResolvedValue({
      model_id: "glm-5.2",
      provider_id: "zai",
      installed: true,
      notes: [],
      source: "test",
    });
    render(<DecisionTreeDriverBadge />);
    await waitFor(() => {
      expect(screen.getByTestId("decision-tree-driver-active").textContent).toMatch(
        /zai\s*\/\s*glm-5\.2/,
      );
    });
  });

  it("surfaces researchTier chrome when provided (ku)", async () => {
    fetchDecisionTreeSelection.mockResolvedValue({
      model_id: "glm-5.2",
      provider_id: "zai",
      installed: true,
      notes: [],
      source: "test",
    });
    render(<DecisionTreeDriverBadge researchTier="wrestle" />);
    await waitFor(() => {
      expect(screen.getByTestId("decision-tree-driver-active")).toBeTruthy();
    });
    expect(
      screen
        .getByTestId("decision-tree-driver-badge")
        .getAttribute("data-research-tier"),
    ).toBe("wrestle");
    expect(
      screen
        .getByTestId("decision-tree-driver-metrics")
        .getAttribute("data-research-tier"),
    ).toBe("wrestle");
    expect(screen.getByTestId("decision-tree-research-tier").textContent).toMatch(
      /wrestle/i,
    );
    expect(screen.getByTestId("decision-tree-research-tier").textContent).toMatch(
      /long-horizon/i,
    );
    // Residual (afc): wrestle → best-by-task advisory (strong-model).
    await waitFor(() => {
      expect(screen.getByTestId("decision-tree-bench-best-by-task")).toBeTruthy();
    });
    const bench = screen.getByTestId("decision-tree-bench-best-by-task");
    expect(bench.getAttribute("data-task-class")).toBe("wrestle");
    expect(bench.getAttribute("data-best-model")).toBe("strong-model");
    expect(bench.getAttribute("data-advisory-only")).toBe("true");
    expect(bench.getAttribute("data-matches-installed")).toBe("false");
    expect(screen.getByTestId("decision-tree-bench-best-model").textContent).toBe(
      "strong-model",
    );
    expect(
      screen
        .getByTestId("decision-tree-driver-metrics")
        .getAttribute("data-bench-task-class"),
    ).toBe("wrestle");
    expect(
      screen.getByTestId("decision-tree-bench-leaderboard-link").getAttribute("href"),
    ).toBe("/settings#antiek-bench-leaderboard");
    // Residual (afe): explicit install when best differs from installed.
    expect(bench.getAttribute("data-install-available")).toBe("true");
    const installBtn = screen.getByTestId("decision-tree-install-best-for-task");
    expect(installBtn.getAttribute("data-install-model-id")).toBe("strong-model");
    expect(installBtn.getAttribute("data-install-task-class")).toBe("wrestle");
    expect(installBtn.getAttribute("data-advisory-only")).toBe("true");
    installDecisionTreeSelection.mockResolvedValue({
      model_id: "strong-model",
      provider_id: "zai",
      installed: true,
      notes: [],
      source: "test",
    });
    fireEvent.click(installBtn);
    await waitFor(() => {
      expect(installDecisionTreeSelection).toHaveBeenCalledWith({
        model_id: "strong-model",
        provider_id: "zai",
      });
    });
    await waitFor(() => {
      expect(
        screen.getByTestId("decision-tree-install-best-status").textContent,
      ).toMatch(/Installed strong-model for wrestle/i);
    });
  });

  it("shows none when not installed", async () => {
    fetchDecisionTreeSelection.mockResolvedValue({
      model_id: null,
      provider_id: null,
      installed: false,
      notes: [],
      source: "test",
    });
    render(<DecisionTreeDriverBadge />);
    await waitFor(() => {
      expect(screen.getByTestId("decision-tree-driver-none").textContent).toMatch(
        /none/,
      );
    });
  });

  it("links dual-gate L1–L4 checklist (oa)", async () => {
    render(<DecisionTreeDriverBadge />);
    await waitFor(() => {
      expect(
        screen.getByTestId("decision-tree-dual-gate-checklist-link"),
      ).toBeTruthy();
    });
    const dual = screen.getByTestId("decision-tree-dual-gate-checklist-link");
    // Residual (aaz): deep-link L7 ND advisory-only section (never router).
    expect(dual.getAttribute("href")).toMatch(/DUAL-GATE-L1-L4.*#l7-notdiamond/);
    expect(dual.textContent).toMatch(/L7 ND advisory/i);
    // Residual (yl): shared chokepoint dual-gate honesty stamps.
    expect(dual.getAttribute("data-offline-default")).toBe("true");
    expect(dual.getAttribute("data-l7-notdiamond")).toBe("advisory_only");
  });

  it("links to Settings for driver install and budget (fj)", async () => {
    fetchDecisionTreeSelection.mockResolvedValue({
      model_id: null,
      provider_id: null,
      installed: false,
      notes: [],
      source: "test",
    });
    render(<DecisionTreeDriverBadge />);
    await waitFor(() => {
      expect(screen.getByTestId("decision-tree-settings-link")).toBeTruthy();
    });
    const link = screen.getByTestId("decision-tree-settings-link");
    expect(link.getAttribute("href")).toBe("/settings#decision-tree-panel");
    expect(link.textContent).toMatch(/Settings/);
  });

  it("deep-links to NotDiamond advisory Settings section (rm)", async () => {
    fetchDecisionTreeSelection.mockResolvedValue({
      model_id: "claude-opus-4-8",
      provider_id: "anthropic",
      installed: true,
      notes: [],
      source: "test",
    });
    render(<DecisionTreeDriverBadge />);
    await waitFor(() => {
      expect(
        screen.getByTestId("decision-tree-notdiamond-advisory-link"),
      ).toBeTruthy();
    });
    const nd = screen.getByTestId("decision-tree-notdiamond-advisory-link");
    expect(nd.getAttribute("href")).toBe("/settings#notdiamond-advisory");
    expect(nd.getAttribute("data-notdiamond-authority")).toBe("advisory_only");
    expect(nd.textContent).toMatch(/ND advisory/i);
  });

  it("shows compact budget usage bar next to driver (eq)", async () => {
    fetchDecisionTreeSelection.mockResolvedValue({
      model_id: "claude-opus-4-8",
      provider_id: "anthropic",
      installed: true,
      notes: [],
      source: "test",
    });
    render(<DecisionTreeDriverBadge />);
    await waitFor(() => {
      expect(screen.getByTestId("decision-tree-budget-usage")).toBeTruthy();
    });
    expect(
      screen.getByTestId("decision-tree-budget-usage").getAttribute(
        "data-spent-status",
      ),
    ).toBe("known");
    expect(screen.getByTestId("decision-tree-budget-spent").textContent).toMatch(
      /\$2\.50/,
    );
    expect(screen.getByTestId("decision-tree-budget-cap").textContent).toMatch(
      /\$10\.00/,
    );
    expect(
      screen.getByTestId("decision-tree-budget-remaining").textContent,
    ).toMatch(/\$7\.50/);
    expect(screen.getByTestId("decision-tree-budget-bar-fill")).toBeTruthy();
    const track = screen.getByTestId("decision-tree-budget-bar-track");
    expect(track.getAttribute("aria-valuenow")).toBe("25");
    // Residual (hv): machine-readable driver + budget metrics.
    const metrics = screen.getByTestId("decision-tree-driver-metrics");
    expect(metrics.getAttribute("data-installed")).toBe("true");
    expect(metrics.getAttribute("data-model-id")).toBe("claude-opus-4-8");
    expect(metrics.getAttribute("data-provider-id")).toBe("anthropic");
    expect(metrics.getAttribute("data-spent-status")).toBe("known");
    expect(metrics.getAttribute("data-spent-usd")).toBe("2.5");
    expect(metrics.getAttribute("data-cap-usd")).toBe("10");
    expect(metrics.getAttribute("data-remaining-usd")).toBe("7.5");
    expect(metrics.getAttribute("data-usage-pct")).toBe("25");
    expect(metrics.getAttribute("data-view-format")).toBe("html");
    expect(metrics.textContent).toMatch(/Driver metrics/);
  });

  it("budgetUsagePct is honest for unknown/no_cap", () => {
    expect(
      budgetUsagePct({
        daily_cap_usd: 10,
        spent_usd: null,
        remaining_usd: null,
        spent_status: "unknown",
        cap_env: null,
        notes: [],
      }),
    ).toBeNull();
    expect(
      budgetUsagePct({
        daily_cap_usd: 10,
        spent_usd: 5,
        remaining_usd: 5,
        spent_status: "known",
        cap_env: null,
        notes: [],
      }),
    ).toBe(50);
  });

  it("refresh re-fetches driver and budget (fd)", async () => {
    fetchDecisionTreeSelection
      .mockResolvedValueOnce({
        model_id: "glm-5.2",
        provider_id: "zai",
        installed: true,
        notes: [],
        source: "test",
      })
      .mockResolvedValueOnce({
        model_id: "claude-opus-4-8",
        provider_id: "anthropic",
        installed: true,
        notes: [],
        source: "test",
      });
    fetchSettingsBudget
      .mockResolvedValueOnce({
        daily_cap_usd: 10,
        spent_usd: 2.5,
        remaining_usd: 7.5,
        spent_status: "known",
        cap_env: null,
        notes: [],
      })
      .mockResolvedValueOnce({
        daily_cap_usd: 10,
        spent_usd: 4,
        remaining_usd: 6,
        spent_status: "known",
        cap_env: null,
        notes: [],
      });
    render(<DecisionTreeDriverBadge />);
    await waitFor(() => {
      expect(screen.getByTestId("decision-tree-driver-active").textContent).toMatch(
        /glm-5\.2/,
      );
    });
    expect(
      screen.getByTestId("decision-tree-driver-badge").getAttribute(
        "data-refresh-tick",
      ),
    ).toBe("0");
    fireEvent.click(screen.getByTestId("decision-tree-driver-refresh"));
    await waitFor(() => {
      expect(screen.getByTestId("decision-tree-driver-active").textContent).toMatch(
        /claude-opus-4-8/,
      );
    });
    expect(
      screen.getByTestId("decision-tree-driver-badge").getAttribute(
        "data-refresh-tick",
      ),
    ).toBe("1");
    expect(screen.getByTestId("decision-tree-budget-spent").textContent).toMatch(
      /\$4\.00/,
    );
    expect(fetchDecisionTreeSelection).toHaveBeenCalledTimes(2);
    expect(fetchSettingsBudget).toHaveBeenCalledTimes(2);
  });

  it("projects prompt cost impact when promptText is provided (pg)", async () => {
    fetchDecisionTreeSelection.mockResolvedValue({
      model_id: "glm-5.2",
      provider_id: "zai",
      installed: true,
      notes: [],
      source: "test",
    });
    render(
      <DecisionTreeDriverBadge
        researchTier="deep"
        promptText="What is the recursive note-taker twin substrate?"
      />,
    );
    await waitFor(() => {
      expect(estimatePromptCost).toHaveBeenCalled();
    });
    await waitFor(() => {
      expect(screen.getByTestId("decision-tree-prompt-projection")).toBeTruthy();
    });
    const strip = screen.getByTestId("decision-tree-prompt-projection");
    expect(Number(strip.getAttribute("data-prompt-chars") || 0)).toBeGreaterThan(
      0,
    );
    expect(strip.getAttribute("data-pricing-known")).toBe("true");
    expect(strip.getAttribute("data-would-exceed")).toBe("false");
    expect(strip.textContent).toMatch(/Prompt projection/i);
    expect(strip.textContent).toMatch(/within remaining budget/i);
    expect(
      screen.getByTestId("decision-tree-prompt-remaining-after").textContent,
    ).toMatch(/Remaining after prompt/i);
    // Residual (aeb): within budget → goes-negative false.
    expect(
      screen
        .getByTestId("decision-tree-prompt-remaining-after")
        .getAttribute("data-goes-negative"),
    ).toBe("false");
    expect(
      screen
        .getByTestId("decision-tree-prompt-projection")
        .getAttribute("data-goes-negative"),
    ).toBe("false");
  });

  it("stamps data-goes-negative when high band burns past remaining (aeb)", async () => {
    fetchDecisionTreeSelection.mockResolvedValue({
      model_id: "glm-5.2",
      provider_id: "zai",
      installed: true,
      notes: [],
      source: "test",
    });
    fetchSettingsBudget.mockResolvedValue({
      daily_cap_usd: 10,
      spent_usd: 8,
      remaining_usd: 2,
      spent_status: "known",
      cap_env: "ANTIEK_DAILY_BUDGET_USD",
      notes: [],
    });
    estimatePromptCost.mockResolvedValue({
      estimated_usd_low: 3,
      estimated_usd_high: 5,
      would_exceed_budget: true,
      pricing_known: true,
      notes: [],
      assumed_input_tokens: 100,
      assumed_output_tokens: 2500,
      tier: "deep",
      provider: "zai",
      model: "glm-5.2",
    });
    render(
      <DecisionTreeDriverBadge
        researchTier="deep"
        promptText="Large prompt that will burn past remaining daily budget high band"
      />,
    );
    await waitFor(() => {
      expect(
        screen.getByTestId("decision-tree-prompt-remaining-after"),
      ).toBeTruthy();
    });
    const after = screen.getByTestId("decision-tree-prompt-remaining-after");
    // remaining 2 − high 5 = −3
    expect(after.getAttribute("data-remaining-after-usd")).toBe("-3");
    expect(after.getAttribute("data-goes-negative")).toBe("true");
    expect(
      screen
        .getByTestId("decision-tree-prompt-projection")
        .getAttribute("data-goes-negative"),
    ).toBe("true");
    expect(after.textContent).toMatch(/over remaining high-band/i);
    expect(after.textContent).toMatch(/soft foresight/i);
  });

  it("omits prompt projection when promptText is empty (pg)", async () => {
    fetchDecisionTreeSelection.mockResolvedValue({
      model_id: "glm-5.2",
      provider_id: "zai",
      installed: true,
      notes: [],
      source: "test",
    });
    render(<DecisionTreeDriverBadge promptText="" />);
    await waitFor(() => {
      expect(screen.getByTestId("decision-tree-driver-active")).toBeTruthy();
    });
    expect(screen.queryByTestId("decision-tree-prompt-projection")).toBeNull();
    expect(estimatePromptCost).not.toHaveBeenCalled();
  });
});
