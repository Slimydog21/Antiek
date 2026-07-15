import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { fetchModelDecision, type ModelDecisionResponse } from "../../api/settings";
import Settings from "./index";

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

const budget = {
  daily_cap_usd: 5,
  spent_usd: 1,
  remaining_usd: 4,
  spent_status: "known" as const,
  cap_env: null,
  notes: ["test note"],
};

vi.mock("../../api/settings", () => ({
  fetchSettingsModels: vi.fn(async () => models),
  fetchSettingsBudget: vi.fn(async () => budget),
  fetchModelDecision: vi.fn(async () => ({
    authority: "advisory",
    task: "deep_research",
    recommended_tier: "synthesis",
    benchmark_status: "measured",
    benchmark_generated_at: "2026-07-07T00:00:00Z",
    notes: ["server-owned evidence"],
    candidates: [
      {
        rank: 1,
        tier: "synthesis",
        provider: "zai",
        model: "glm-5.2",
        ready: true,
        operationally_eligible: true,
        quality_score: 0.91,
        quality_basis: "measured",
        benchmark_samples: 40,
        estimated_usd_low: 0.012,
        estimated_usd_high: 0.019,
        would_exceed_budget: false,
      },
      {
        rank: 2,
        tier: "pro",
        provider: "deepseek",
        model: "deepseek-v4-pro",
        ready: true,
        operationally_eligible: true,
        quality_score: 0.82,
        quality_basis: "measured",
        benchmark_samples: 35,
        estimated_usd_low: 0.008,
        estimated_usd_high: 0.013,
        would_exceed_budget: false,
      },
    ],
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
}));

describe("Settings SPR-01", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  afterEach(cleanup);

  it("renders registered providers and budget bar", async () => {
    render(<Settings />);
    await waitFor(() => {
      expect(screen.getByText("zai")).toBeTruthy();
    });
    expect(screen.getByText(/ready/i)).toBeTruthy();
    expect(screen.getByText("$5.00")).toBeTruthy();
    expect(screen.getByText("$1.0000")).toBeTruthy();
  });

  it("projects cost and shows honest unknown pricing", async () => {
    const user = userEvent.setup();
    render(<Settings />);
    await waitFor(() => expect(screen.getByText("zai")).toBeTruthy());
    const buttons = screen.getAllByRole("button");
    const project = buttons.find((b) => /project cost/i.test(b.textContent ?? ""));
    expect(project).toBeTruthy();
    await user.click(project!);
    await waitFor(() => {
      expect(
        screen.getByText(/tier pricing is 0\.0 placeholder/i),
      ).toBeTruthy();
    });
  });

  it("compares server-owned model candidates in the evidence tab", async () => {
    const user = userEvent.setup();
    render(<Settings />);
    await user.click(screen.getByRole("tab", { name: "Decision tree" }));
    await user.click(screen.getByRole("button", { name: "Compare models" }));
    expect(await screen.findByText(/Measured pick:/)).toBeTruthy();
    expect(screen.getByText("synthesis", { selector: "strong" })).toBeTruthy();
    expect(screen.getByText(/2\/2 routes measured/i)).toBeTruthy();
    expect(screen.getByText(/n=40/i)).toBeTruthy();
  });

  it("links tabs to panels and supports arrow-key navigation", async () => {
    const user = userEvent.setup();
    render(<Settings />);
    const overview = screen.getByRole("tab", { name: "Overview" });
    const decision = screen.getByRole("tab", { name: "Decision tree" });
    expect(overview.getAttribute("aria-controls")).toBe("settings-overview-panel");
    overview.focus();
    await user.keyboard("{ArrowRight}");
    expect(decision.getAttribute("aria-selected")).toBe("true");
    expect(document.activeElement).toBe(decision);
    const panel = screen.getByRole("tabpanel");
    expect(panel.getAttribute("aria-labelledby")).toBe("settings-decision-tab");
  });

  it("does not render an in-flight result after the task changes", async () => {
    let resolveDecision: ((value: ModelDecisionResponse) => void) | undefined;
    vi.mocked(fetchModelDecision).mockImplementationOnce(
      () => new Promise<ModelDecisionResponse>((resolve) => { resolveDecision = resolve; }),
    );
    const user = userEvent.setup();
    render(<Settings />);
    await user.click(screen.getByRole("tab", { name: "Decision tree" }));
    await user.click(screen.getByRole("button", { name: "Compare models" }));
    await user.selectOptions(screen.getByLabelText("Task"), "writing");
    resolveDecision?.({
      authority: "advisory",
      task: "deep_research",
      recommended_tier: "pro",
      benchmark_status: "unavailable",
      benchmark_generated_at: null,
      notes: [],
      candidates: [],
    });
    await waitFor(() => expect(screen.queryByText(/Recommended tier:/)).toBeNull());
  });
});
