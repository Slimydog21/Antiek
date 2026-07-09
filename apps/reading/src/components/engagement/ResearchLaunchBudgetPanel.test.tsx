import { describe, expect, it, vi, beforeEach, afterEach } from "vitest";
import { cleanup, render, screen, waitFor } from "@testing-library/react";

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
