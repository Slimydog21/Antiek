import { describe, expect, it, vi, beforeEach, afterEach } from "vitest";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { ResearchLaunchBudgetPanel } from "./ResearchLaunchBudgetPanel";

const {
  fetchSettingsBudget,
  estimatePromptCost,
  fetchDecisionTreeSelection,
} = vi.hoisted(() => ({
  fetchSettingsBudget: vi.fn(async () => ({
    daily_cap_usd: 5,
    spent_usd: 1,
    remaining_usd: 4,
    spent_status: "known" as const,
    cap_env: null,
    notes: [],
  })),
  estimatePromptCost: vi.fn(async () => ({
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
  fetchDecisionTreeSelection: vi.fn(async () => ({
    model_id: "glm-5.2",
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
}));

describe("ResearchLaunchBudgetPanel", () => {
  beforeEach(() => {
    fetchSettingsBudget.mockClear();
    estimatePromptCost.mockClear();
    fetchDecisionTreeSelection.mockClear();
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
    expect(settings.getAttribute("href")).toBe("/settings");
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
