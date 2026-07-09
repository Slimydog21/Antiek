import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import Settings from "./index";

vi.mock("../../workspace/useViewportTier", () => ({
  useViewportTier: () => "desktop",
}));

const {
  installDecisionTreeSelection,
  clearDecisionTreeSelection,
  fetchDecisionTreeSelection,
  estimatePromptCost,
  fetchSettingsModels,
  fetchSettingsBudget,
} = vi.hoisted(() => {
  const models = {
    models: [
      {
        provider_id: "zai",
        ready: true,
        tier_bindings: ["flash", "pro"],
        primary_model: "glm-5.2",
        notes: null,
      },
    ],
    count: 1,
    providers_ready: true,
    source: "test",
  };
  const budget = {
    daily_cap_usd: 5,
    spent_usd: 1,
    remaining_usd: 4,
    spent_status: "known" as const,
    cap_env: null,
    notes: ["test note"],
  };
  return {
    installDecisionTreeSelection: vi.fn(async () => ({
      model_id: "glm-5.2",
      provider_id: "zai",
      installed: true,
      notes: ["installed into process-local decision-tree registry"],
      source: "test",
    })),
    clearDecisionTreeSelection: vi.fn(async () => ({
      model_id: null,
      provider_id: null,
      installed: false,
      notes: ["decision-tree selection cleared"],
      source: "test",
    })),
    fetchDecisionTreeSelection: vi.fn(async () => ({
      model_id: null,
      provider_id: null,
      installed: false,
      notes: ["no decision-tree selection installed in this process"],
      source: "test",
    })),
    estimatePromptCost: vi.fn(async () => ({
      estimated_usd_low: null,
      estimated_usd_high: null,
      would_exceed_budget: null,
      pricing_known: false,
      notes: ["tier pricing is 0.0 placeholder"],
      assumed_input_tokens: 500,
      assumed_output_tokens: 500,
      tier: "pro",
      provider: "zai",
      model: "glm-5.2",
    })),
    fetchSettingsModels: vi.fn(async () => models),
    fetchSettingsBudget: vi.fn(async () => budget),
  };
});

vi.mock("../../api/settings", () => ({
  fetchSettingsModels,
  fetchSettingsBudget,
  estimatePromptCost,
  fetchDecisionTreeSelection,
  installDecisionTreeSelection,
  clearDecisionTreeSelection,
}));

describe("Settings SPR-01 + decision-tree install", () => {
  beforeEach(() => {
    installDecisionTreeSelection.mockClear();
    clearDecisionTreeSelection.mockClear();
    fetchDecisionTreeSelection.mockClear();
    estimatePromptCost.mockClear();
    fetchSettingsModels.mockClear();
    fetchSettingsBudget.mockClear();
  });

  it("renders registered providers and budget bar", async () => {
    render(<Settings />);
    await waitFor(() => {
      expect(screen.getAllByText(/zai/).length).toBeGreaterThan(0);
    });
    expect(screen.getByText(/ready/i)).toBeTruthy();
    expect(screen.getByText("$5.00")).toBeTruthy();
    expect(screen.getByText("$1.0000")).toBeTruthy();
  });

  it("projects cost and shows honest unknown pricing", async () => {
    const user = userEvent.setup();
    render(<Settings />);
    await waitFor(() => expect(screen.getAllByText(/zai/).length).toBeGreaterThan(0));
    const buttons = screen.getAllByRole("button");
    const project = buttons.find((b) => /project cost/i.test(b.textContent ?? ""));
    expect(project).toBeTruthy();
    await user.click(project!);
    await waitFor(() => {
      expect(
        screen.getByText(/tier pricing is 0\.0 placeholder/i),
      ).toBeTruthy();
    });
    // Projection still #440 path (mocked api/settings estimatePromptCost)
    expect(estimatePromptCost).toHaveBeenCalled();
  });

  it("installs decision-tree driver via Settings panel", async () => {
    const user = userEvent.setup();
    const { container } = render(<Settings />);
    await waitFor(() => expect(screen.getAllByText(/zai/).length).toBeGreaterThan(0));
    const installBtn = container.querySelector(
      '[data-testid="decision-tree-install"]',
    ) as HTMLButtonElement | null;
    expect(installBtn).toBeTruthy();
    const modelInput = container.querySelector(
      '[data-testid="decision-tree-model"]',
    ) as HTMLInputElement;
    expect(modelInput).toBeTruthy();
    await user.clear(modelInput);
    await user.type(modelInput, "glm-5.2");
    await user.click(installBtn!);
    await waitFor(() => {
      expect(installDecisionTreeSelection).toHaveBeenCalled();
    });
    const call = installDecisionTreeSelection.mock.calls.at(-1)?.[0] as {
      model_id: string;
    };
    expect(call.model_id).toBe("glm-5.2");
    await waitFor(() => {
      const status = container.querySelector('[data-testid="decision-tree-status"]');
      expect(status?.textContent).toMatch(/zai\s*\/\s*glm-5\.2/i);
    });
  });
});
