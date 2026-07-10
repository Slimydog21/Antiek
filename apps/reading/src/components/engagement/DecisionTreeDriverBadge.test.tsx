import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  budgetUsagePct,
  DecisionTreeDriverBadge,
} from "./DecisionTreeDriverBadge";

const fetchDecisionTreeSelection = vi.fn();
const fetchSettingsBudget = vi.fn();
const estimatePromptCost = vi.fn();

vi.mock("../../api/settings", () => ({
  fetchDecisionTreeSelection: (...args: unknown[]) =>
    fetchDecisionTreeSelection(...args),
  fetchSettingsBudget: (...args: unknown[]) => fetchSettingsBudget(...args),
  estimatePromptCost: (...args: unknown[]) => estimatePromptCost(...args),
}));

describe("DecisionTreeDriverBadge residual cw/eq", () => {
  afterEach(() => cleanup());
  beforeEach(() => {
    fetchDecisionTreeSelection.mockReset();
    fetchSettingsBudget.mockReset();
    estimatePromptCost.mockReset();
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
    expect(dual.getAttribute("href")).toMatch(/DUAL-GATE-L1-L4/);
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
