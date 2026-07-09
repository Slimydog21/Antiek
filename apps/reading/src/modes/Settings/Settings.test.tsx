import { describe, expect, it, vi, beforeEach, afterEach } from "vitest";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
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
  fetchAntiekBenchUsageSummary,
  fetchNotDiamondAdvisory,
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
    fetchAntiekBenchUsageSummary: vi.fn(async () => ({
      event_count: 2,
      by_task_class: {
        wrestle: { worked: 1, failed: 0, total: 1 },
        book_qa: { worked: 0, failed: 1, total: 1 },
      },
      view_format: "html",
      settings_panel: "antiek_bench_usage_weekly",
      source: "antiek_bench.usage_events",
      notes: [],
      html: "<p>Events recorded: 2</p>",
    })),
    fetchNotDiamondAdvisory: vi.fn(async () => ({
      advisory_allowed: true,
      advisory_verdict: "GO",
      authority_allowed: false,
      authority_rejected: true,
      authority_verdict: "REJECT",
      dispatch_owner: "hermes_primary_plus_decision_tree",
      notdiamond_is_dispatch_authority: false,
      kill_switch_env: "ANTIEK_NOTDIAMOND",
      kill_switch_enabled: false,
      default_off: true,
      view_format: "html",
      settings_panel: "notdiamond_advisory",
      source: "docs/htmlspec/notdiamond-verdict/VERDICT.md",
      verdict_date: "2026-07-09",
      notes: ["Authority REJECT under §16"],
      html: "<p>Authority REJECT — not the dispatch authority</p>",
    })),
  };
});

vi.mock("../../api/settings", () => ({
  fetchSettingsModels,
  fetchSettingsBudget,
  estimatePromptCost,
  fetchDecisionTreeSelection,
  installDecisionTreeSelection,
  clearDecisionTreeSelection,
  fetchAntiekBenchUsageSummary,
  fetchNotDiamondAdvisory,
}));

describe("Settings SPR-01 + decision-tree install", () => {
  afterEach(() => {
    cleanup();
  });

  beforeEach(() => {
    installDecisionTreeSelection.mockClear();
    clearDecisionTreeSelection.mockClear();
    fetchDecisionTreeSelection.mockClear();
    estimatePromptCost.mockClear();
    fetchSettingsModels.mockClear();
    fetchSettingsBudget.mockClear();
    fetchAntiekBenchUsageSummary.mockClear();
    fetchNotDiamondAdvisory.mockClear();
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

  it("loads Antiek-bench weekly usage summary in Settings", async () => {
    render(<Settings />);
    await waitFor(() => {
      expect(screen.getByTestId("antiek-bench-usage-panel")).toBeTruthy();
    });
    expect(fetchAntiekBenchUsageSummary).toHaveBeenCalled();
    await waitFor(() => {
      expect(screen.getByTestId("antiek-bench-usage-summary").textContent).toMatch(
        /Events/,
      );
    });
    expect(screen.getByTestId("antiek-bench-usage-panel").getAttribute("data-view-format")).toBe(
      "html",
    );
    expect(screen.getByText(/wrestle/i)).toBeTruthy();
    expect(screen.getByTestId("antiek-bench-usage-html").innerHTML).toContain("2");
  });

  it("loads NotDiamond advisory posture — authority rejected", async () => {
    render(<Settings />);
    await waitFor(() => {
      expect(screen.getByTestId("notdiamond-advisory-panel")).toBeTruthy();
    });
    expect(fetchNotDiamondAdvisory).toHaveBeenCalled();
    await waitFor(() => {
      expect(
        screen.getByTestId("notdiamond-advisory-summary").textContent,
      ).toMatch(/REJECT/i);
    });
    expect(
      screen.getByTestId("notdiamond-advisory-panel").getAttribute("data-view-format"),
    ).toBe("html");
    expect(screen.getByTestId("notdiamond-advisory-summary").textContent).toMatch(
      /false/i,
    );
    expect(screen.getByTestId("notdiamond-advisory-html").innerHTML).toMatch(
      /authority|REJECT/i,
    );
  });
});
