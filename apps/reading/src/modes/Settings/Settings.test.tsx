import { describe, expect, it, vi, beforeEach, afterEach } from "vitest";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
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

  it("shows a decision-tree recommendation without mutating providers", async () => {
    render(<Settings />);
    await waitFor(() => expect(screen.getByText("zai")).toBeTruthy());

    expect(screen.getByText("Decision tree")).toBeTruthy();
    expect(screen.getByText("Recommended depth")).toBeTruthy();
    expect(screen.getByText("Deep")).toBeTruthy();
    expect(screen.getByText(/does not mutate provider registration/i)).toBeTruthy();
  });

  it("recommends Fast when cheapest is selected", async () => {
    const user = userEvent.setup();
    render(<Settings />);
    await waitFor(() => expect(screen.getByText("zai")).toBeTruthy());

    await user.click(screen.getByRole("button", { name: "Cheapest" }));
    await waitFor(() => {
      expect(screen.getByText("Fast")).toBeTruthy();
    });
    expect(screen.getByText(/minimise latency and spend/i)).toBeTruthy();
  });
});
