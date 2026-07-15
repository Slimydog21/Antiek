import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import {
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
  notes: ["test note"],
};

vi.mock("../../api/settings", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../../api/settings")>()),
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
    expect(screen.getAllByText("registered").length).toBeGreaterThan(0);
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
    const experiences: string[] = [];
    const listener = (event: Event) => {
      experiences.push((event as CustomEvent).detail?.experience);
    };
    window.addEventListener(WERNER_EXPERIENCE_EVENT, listener);
    const user = userEvent.setup();
    render(<Settings />);
    await user.click(screen.getByRole("tab", { name: "Decision tree" }));
    await user.click(screen.getByRole("button", { name: "Compare models" }));
    expect(await screen.findByText(/Measured pick:/)).toBeTruthy();
    expect(screen.getByText("synthesis", { selector: "strong" })).toBeTruthy();
    expect(screen.getByText(/2\/2 routes measured/i)).toBeTruthy();
    expect(screen.getByText(/n=40/i)).toBeTruthy();
    expect(experiences).toEqual(["model_evidence_compared"]);
    window.removeEventListener(WERNER_EXPERIENCE_EVENT, listener);
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
    const listener = vi.fn();
    window.addEventListener(WERNER_EXPERIENCE_EVENT, listener);
    let resolveDecision: ((value: ModelDecisionResponse) => void) | undefined;
    vi.mocked(fetchModelDecision).mockImplementationOnce(
      () => new Promise<ModelDecisionResponse>((resolve) => { resolveDecision = resolve; }),
    );
    const user = userEvent.setup();
    render(<Settings />);
    await user.click(screen.getByRole("tab", { name: "Decision tree" }));
    await user.click(screen.getByRole("button", { name: "Compare models" }));
    await user.selectOptions(screen.getByLabelText("Task"), "writing");
    await act(async () => {
      resolveDecision?.({
        authority: "advisory",
        task: "deep_research",
        recommended_tier: "pro",
        benchmark_status: "unavailable",
        benchmark_generated_at: null,
        notes: [],
        candidates: [],
      });
    });
    await waitFor(() => expect(screen.queryByText(/Recommended tier:/)).toBeNull());
    expect(listener).not.toHaveBeenCalled();
    window.removeEventListener(WERNER_EXPERIENCE_EVENT, listener);
  });

  it("keeps a response silent when shared overview inputs invalidate it", async () => {
    let resolveDecision: ((value: ModelDecisionResponse) => void) | undefined;
    vi.mocked(fetchModelDecision).mockImplementationOnce(
      () => new Promise<ModelDecisionResponse>((resolve) => { resolveDecision = resolve; }),
    );
    const listener = vi.fn();
    window.addEventListener(WERNER_EXPERIENCE_EVENT, listener);
    const user = userEvent.setup();
    render(<Settings />);
    await user.click(screen.getByRole("tab", { name: "Decision tree" }));
    await user.click(screen.getByRole("button", { name: "Compare models" }));
    await user.click(screen.getByRole("tab", { name: "Overview" }));
    const input = screen.getByLabelText("Input chars");
    await user.clear(input);
    await user.type(input, "3000");
    await act(async () => {
      resolveDecision?.({
        authority: "advisory",
        task: "deep_research",
        recommended_tier: null,
        benchmark_status: "unavailable",
        benchmark_generated_at: null,
        notes: [],
        candidates: [],
      });
    });
    await waitFor(() => expect(listener).not.toHaveBeenCalled());
    window.removeEventListener(WERNER_EXPERIENCE_EVENT, listener);
  });

  it("keeps rejected and post-unmount responses silent", async () => {
    const listener = vi.fn();
    window.addEventListener(WERNER_EXPERIENCE_EVENT, listener);
    vi.mocked(fetchModelDecision).mockRejectedValueOnce(new Error("offline"));
    const user = userEvent.setup();
    const view = render(<Settings />);
    await user.click(screen.getByRole("tab", { name: "Decision tree" }));
    await user.click(screen.getByRole("button", { name: "Compare models" }));
    expect((await screen.findByRole("alert")).textContent).toContain("offline");
    expect(listener).not.toHaveBeenCalled();

    let resolveDecision: ((value: ModelDecisionResponse) => void) | undefined;
    vi.mocked(fetchModelDecision).mockImplementationOnce(
      () => new Promise<ModelDecisionResponse>((resolve) => { resolveDecision = resolve; }),
    );
    await user.click(screen.getByRole("button", { name: "Compare models" }));
    view.unmount();
    await act(async () => {
      resolveDecision?.({
        authority: "advisory",
        task: "deep_research",
        recommended_tier: null,
        benchmark_status: "unavailable",
        benchmark_generated_at: null,
        notes: [],
        candidates: [],
      });
    });
    expect(listener).not.toHaveBeenCalled();
    window.removeEventListener(WERNER_EXPERIENCE_EVENT, listener);
  });

  it.each([
    { authority: "unexpected", task: "deep_research" },
    { authority: "advisory", task: "writing" },
    { authority: "advisory", task: "deep_research", omitPayload: true },
  ])("rejects a mismatched runtime response without a reaction: %o", async (mismatch) => {
    vi.mocked(fetchModelDecision).mockResolvedValueOnce((mismatch.omitPayload ? {
      authority: mismatch.authority,
      task: mismatch.task,
    } : {
      authority: mismatch.authority,
      task: mismatch.task,
      recommended_tier: null,
      benchmark_status: "unavailable",
      benchmark_generated_at: null,
      notes: [],
      candidates: [],
    }) as unknown as ModelDecisionResponse);
    const listener = vi.fn();
    window.addEventListener(WERNER_EXPERIENCE_EVENT, listener);
    const user = userEvent.setup();
    render(<Settings />);
    await user.click(screen.getByRole("tab", { name: "Decision tree" }));
    await user.click(screen.getByRole("button", { name: "Compare models" }));
    expect((await screen.findByRole("alert")).textContent).toContain(
      "did not match",
    );
    expect(listener).not.toHaveBeenCalled();
    window.removeEventListener(WERNER_EXPERIENCE_EVENT, listener);
  });
});
