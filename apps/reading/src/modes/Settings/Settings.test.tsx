import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import {
  estimatePromptCost,
  fetchModelDecision,
  type ModelDecisionResponse,
} from "../../api/settings";
import { WERNER_EXPERIENCE_EVENT } from "../../werner/reactionBus";
import Settings from "./index";

vi.mock("../../workspace/useViewportTier", () => ({
  useViewportTier: () => "desktop",
}));

const models = {
  models: [
    {
      provider_id: "zai",
      registered: true,
      ready: true,
      tier_bindings: ["flash", "pro"],
      primary_model: "glm-5.2",
      notes: null,
    },
    {
      provider_id: "user-custom",
      registered: true,
      ready: false,
      tier_bindings: [],
      primary_model: null,
      notes: "registered, but not bound to an active dispatch tier",
    },
  ],
  count: 2,
  providers_ready: true,
  source: "test",
};

const budget = {
  daily_cap_usd: 5,
  spent_usd: 1,
  remaining_usd: 4,
  spent_status: "known" as const,
  cap_env: null,
  reserved_estimated_usd: 1,
  spend_basis: "reserved_estimate" as const,
  enforcement_cap_usd: 5,
  enforcement_cap_env: null,
  caps_aligned: true,
  over_budget: false,
  over_budget_usd: 0,
  notes: ["test note"],
};

vi.mock("../../api/settings", () => ({
  fetchSettingsModels: vi.fn(async () => models),
  fetchSettingsBudget: vi.fn(async () => budget),
  fetchModelDecision: vi.fn(async () => ({
    authority: "advisory",
    task: "deep_research",
    recommended_tier: "pro",
    benchmark_status: "measured",
    benchmark_generated_at: "2026-07-13T00:00:00Z",
    notes: ["server-owned evidence"],
    candidates: [
      {
        rank: 1,
        tier: "pro",
        provider: "zai",
        model: "glm-5.2",
        ready: true,
        eligible: true,
        quality_score: 0.91,
        quality_basis: "measured",
        benchmark_samples: 40,
        estimated_usd_low: 0.01,
        estimated_usd_high: 0.02,
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
    expect(screen.getAllByText("registered").length).toBeGreaterThan(0);
    expect(screen.getAllByText("$5.00")).toHaveLength(2);
    expect(screen.getByText("$1.0000")).toBeTruthy();
    expect(screen.getByText("Reserved estimate today")).toBeTruthy();
    expect(screen.queryByText("Spent today")).toBeNull();
  });

  it("renders session thinking + living-TV brand chrome on Settings door", async () => {
    render(<Settings />);
    await waitFor(() => expect(screen.getByText("Operator settings")).toBeTruthy());
    expect(screen.getByTestId("settings-home-werner-brand")).toBeTruthy();
    const livingTv = screen.getByTestId(
      "settings-home-living-tv-art",
    ) as HTMLImageElement;
    expect(livingTv.getAttribute("src") ?? "").toMatch(
      /werner_living_tv_session_v1/,
    );
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

  it("emits Werner fail when projection would exceed budget", async () => {
    vi.mocked(estimatePromptCost).mockResolvedValueOnce({
      estimated_usd_low: 4,
      estimated_usd_high: 6,
      would_exceed_budget: true,
      pricing_known: true,
      notes: ["would exceed"],
      assumed_input_tokens: 500,
      assumed_output_tokens: 500,
      tier: "pro",
      provider: "zai",
      model: "glm-5.2",
    });
    const seen: string[] = [];
    const onExp = (e: Event) => {
      const d = (e as CustomEvent).detail;
      if (d?.experience) seen.push(d.experience);
    };
    window.addEventListener(WERNER_EXPERIENCE_EVENT, onExp);
    const user = userEvent.setup();
    render(<Settings />);
    await waitFor(() => expect(screen.getByText("zai")).toBeTruthy());
    const project = screen
      .getAllByRole("button")
      .find((b) => /project cost/i.test(b.textContent ?? ""));
    await user.click(project!);
    await waitFor(() => expect(seen).toContain("fail"));
    window.removeEventListener(WERNER_EXPERIENCE_EVENT, onExp);
  });

  it("compares server-owned model candidates in the decision tree tab", async () => {
    const user = userEvent.setup();
    render(<Settings />);
    await user.click(screen.getByRole("tab", { name: "Decision tree" }));
    await user.click(screen.getByRole("button", { name: "Compare models" }));
    expect(await screen.findByText(/Recommended tier:/)).toBeTruthy();
    expect(screen.getByText("pro", { selector: "strong" })).toBeTruthy();
    expect(screen.getByText("glm-5.2")).toBeTruthy();
    expect(screen.getByText("Measured evidence")).toBeTruthy();
    expect(screen.getByText("n=40")).toBeTruthy();
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
