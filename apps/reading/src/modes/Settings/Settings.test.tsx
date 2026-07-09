import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import Settings from "./index";
import { estimatePromptCost, type BudgetResponse } from "../../api/settings";

vi.mock("../../workspace/useViewportTier", () => ({
  useViewportTier: () => "desktop",
}));

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

const mockState = vi.hoisted((): { budget: BudgetResponse } => ({
  budget: {
    daily_cap_usd: 5,
    spent_usd: 1,
    remaining_usd: 4,
    spent_status: "known" as const,
    cap_env: null,
    notes: ["test note"],
  },
}));

vi.mock("../../api/settings", () => ({
  fetchSettingsModels: vi.fn(async () => models),
  fetchSettingsBudget: vi.fn(async () => mockState.budget),
  fetchLatestAntiekBench: vi.fn(async () => ({
    available: true,
    scorecard_id: "antiek-bench-2026-W28",
    generated_at: "2026-07-09T00:00:00Z",
    week_id: "2026-W28",
    mock_run: true,
    notes: ["mock scorecard"],
    best_by_task_class: [
      {
        task_class: "research_question",
        provider: "zai",
        model: "glm-5.2",
        quality_score: 0.82,
        estimated_cost_usd: 0.014,
        actual_cost_usd: 0.013,
        cost_per_acceptable_answer: 0.00433333,
        latency_ms: 4200,
        route_receipt_ids: ["receipt-1"],
      },
    ],
  })),
  estimatePromptCost: vi.fn(async () => ({
    estimated_usd_low: 0.001,
    estimated_usd_high: 0.002,
    would_exceed_budget: false,
    pricing_known: true,
    notes: [],
    assumed_input_tokens: 500,
    assumed_output_tokens: 500,
    tier: "pro",
    provider: "zai",
    model: "glm-5.2",
    task_kind: "research_question",
    role: "synthesizer",
    route_mode: "auto_balanced",
    selected_candidate: {
      provider: "zai",
      model: "glm-5.2",
      tier: "pro",
      fallback_chain_index: 0,
      estimated_usd_low: 0.001,
      estimated_usd_high: 0.002,
      pricing_known: true,
      cache_status: "cold",
      selection_reason: "auto_balanced",
    },
    candidates: [
      {
        provider: "zai",
        model: "glm-5.2",
        tier: "pro",
        fallback_chain_index: 0,
        estimated_usd_low: 0.001,
        estimated_usd_high: 0.002,
        pricing_known: true,
        cache_status: "cold",
        selection_reason: "auto_balanced",
      },
    ],
  })),
}));

describe("Settings SPR-01", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockState.budget = {
      daily_cap_usd: 5,
      spent_usd: 1,
      remaining_usd: 4,
      spent_status: "known",
      cap_env: null,
      notes: ["test note"],
    };
  });

  afterEach(() => {
    cleanup();
  });

  it("renders registered providers and budget bar", async () => {
    render(<Settings />);
    await waitFor(() => {
      expect(screen.getByText("zai")).toBeTruthy();
    });
    expect(screen.getByText(/ready/i)).toBeTruthy();
    expect(screen.getByText("$5.00")).toBeTruthy();
    expect(screen.getByText("$1.0000")).toBeTruthy();
  });

  it("renders latest Antiek-bench best model by task class", async () => {
    render(<Settings />);
    await waitFor(() => {
      expect(screen.getByLabelText("Best model by task class")).toBeTruthy();
    });
    expect(screen.getByText("research_question")).toBeTruthy();
    expect(screen.getAllByText("zai / glm-5.2").length).toBeGreaterThan(0);
    expect(screen.getAllByText("mock scorecard").length).toBeGreaterThan(0);
  });

  it("changes task kind in the estimator request", async () => {
    const user = userEvent.setup();
    render(<Settings />);
    await waitFor(() => expect(screen.getByText("zai")).toBeTruthy());
    await user.selectOptions(screen.getByLabelText(/task kind/i), "reading_highlight");
    await user.type(
      screen.getByRole("textbox", { name: /prompt/i }),
      "Explain this excerpt.",
    );
    await user.click(screen.getByRole("button", { name: /project cost/i }));
    await waitFor(() => expect(estimatePromptCost).toHaveBeenCalled());
    expect(estimatePromptCost).toHaveBeenCalledWith(
      expect.objectContaining({
        task_kind: "reading_highlight",
        route_mode: "auto_balanced",
        prompt_chars: 21,
      }),
    );
    expect(screen.getByLabelText(/selected route: zai \/ glm-5\.2/i)).toBeTruthy();
  });

  it("manual override displays selected model without auto recommendation text", async () => {
    const user = userEvent.setup();
    render(<Settings />);
    await waitFor(() => expect(screen.getByText("zai")).toBeTruthy());
    await user.click(screen.getByRole("radio", { name: "Manual" }));
    await user.click(screen.getByRole("button", { name: /project cost/i }));
    await waitFor(() => expect(estimatePromptCost).toHaveBeenCalled());
    expect(estimatePromptCost).toHaveBeenCalledWith(
      expect.objectContaining({
        route_mode: "manual",
        manual_provider: "zai",
        manual_model: "glm-5.2",
      }),
    );
    expect(screen.getByText("Manual override")).toBeTruthy();
    expect(screen.queryByText("Recommendation")).toBeNull();
  });

  it("renders no-cap and unknown-spend budget states accessibly", async () => {
    mockState.budget = {
      daily_cap_usd: null,
      spent_usd: null,
      remaining_usd: null,
      spent_status: "no_cap",
      cap_env: null,
      notes: ["no cap"],
    };
    render(<Settings />);
    await waitFor(() =>
      expect(screen.getByText(/budget status: no cap configured/i)).toBeTruthy(),
    );
    expect(screen.getByLabelText(/budget usage: no cap configured/i)).toBeTruthy();
  });

  it("renders cap-exceeded budget state accessibly", async () => {
    mockState.budget = {
      daily_cap_usd: 5,
      spent_usd: 6,
      remaining_usd: -1,
      spent_status: "known",
      cap_env: null,
      notes: ["over"],
    };
    render(<Settings />);
    await waitFor(() =>
      expect(screen.getByText(/budget status: cap exceeded/i)).toBeTruthy(),
    );
    expect(screen.getByLabelText(/budget usage: cap exceeded/i)).toBeTruthy();
  });
});
