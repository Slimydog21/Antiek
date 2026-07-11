import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import Settings from "./index";
import type { BudgetResponse } from "../../api/settings";

vi.mock("../../workspace/useViewportTier", () => ({
  useViewportTier: () => "desktop",
}));

vi.mock("@simplewebauthn/browser", () => ({
  startRegistration: vi.fn(),
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
    spent_status: "known",
    cap_env: null,
    notes: ["test note"],
    reserved_estimated_usd: 1,
    spend_basis: "reserved_estimate",
    enforcement_cap_usd: 5,
    enforcement_cap_env: null,
    caps_aligned: true,
    over_budget: false,
  },
}));

vi.mock("../../api/settings", () => ({
  fetchSettingsModels: vi.fn(async () => models),
  fetchSettingsBudget: vi.fn(async () => mockState.budget),
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
    mockState.budget = {
      daily_cap_usd: 5,
      spent_usd: 1,
      remaining_usd: 4,
      spent_status: "known",
      cap_env: null,
      notes: ["test note"],
      reserved_estimated_usd: 1,
      spend_basis: "reserved_estimate",
      enforcement_cap_usd: 5,
      enforcement_cap_env: null,
      caps_aligned: true,
      over_budget: false,
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
    // Honesty: reserved label, not "Spent today".
    expect(screen.getByText("Reserved (est.)")).toBeTruthy();
    expect(screen.queryByText("Spent today")).toBeNull();
  });

  it("projects cost and shows honest unknown pricing", async () => {
    const user = userEvent.setup();
    render(<Settings />);
    await waitFor(() => expect(screen.getByText("zai")).toBeTruthy());
    const buttons = screen.getAllByRole("button");
    const project = buttons.find((b) =>
      /project cost/i.test(b.textContent ?? ""),
    );
    expect(project).toBeTruthy();
    await user.click(project!);
    await waitFor(() => {
      expect(
        screen.getByText(/tier pricing is 0\.0 placeholder/i),
      ).toBeTruthy();
    });
  });

  it("surfaces dual display vs enforcement caps when misaligned", async () => {
    mockState.budget = {
      daily_cap_usd: 200,
      spent_usd: 4,
      remaining_usd: 196,
      spent_status: "known",
      cap_env: "ANTIEK_OPERATOR_BUDGET_USD",
      notes: [],
      reserved_estimated_usd: 4,
      spend_basis: "reserved_estimate",
      enforcement_cap_usd: 5,
      enforcement_cap_env: null,
      caps_aligned: false,
      over_budget: false,
    };
    render(<Settings />);
    await waitFor(() =>
      expect(screen.getByTestId("dual-cap-note")).toBeTruthy(),
    );
    expect(screen.getByText("Enforcement cap")).toBeTruthy();
    // Enforcement row value may share the page with other $5 figures — assert via dual-cap note.
    const dual = screen.getByTestId("dual-cap-note").textContent ?? "";
    expect(dual).toMatch(/Display cap \$200\.00/);
    expect(dual).toMatch(/Enforcement cap \$5\.00/);
    expect(screen.getByTestId("spend-basis-note").textContent).toMatch(
      /not settled provider cost/i,
    );
  });

  it("renders signed remaining when over display cap", async () => {
    mockState.budget = {
      daily_cap_usd: 2,
      spent_usd: 4,
      remaining_usd: -2,
      spent_status: "known",
      cap_env: "ANTIEK_OPERATOR_BUDGET_USD",
      notes: ["over display budget by $2.0000"],
      reserved_estimated_usd: 4,
      spend_basis: "reserved_estimate",
      enforcement_cap_usd: 5,
      enforcement_cap_env: null,
      caps_aligned: false,
      over_budget: true,
    };
    render(<Settings />);
    await waitFor(() =>
      expect(screen.getByText(/budget status: cap exceeded/i)).toBeTruthy(),
    );
    expect(screen.getByText("$-2.0000 (over display cap)")).toBeTruthy();
    expect(
      screen.getByLabelText(/budget usage: cap exceeded/i),
    ).toBeTruthy();
  });

  it("keeps unknown spend as unknown — never invents $0", async () => {
    mockState.budget = {
      daily_cap_usd: 5,
      spent_usd: null,
      remaining_usd: null,
      spent_status: "unknown",
      cap_env: null,
      notes: ["spent ledger unavailable: daemon sidecar missing"],
      spend_basis: "unknown",
      reserved_estimated_usd: null,
      enforcement_cap_usd: 5,
      caps_aligned: true,
      over_budget: null,
    };
    render(<Settings />);
    await waitFor(() =>
      expect(screen.getByText(/budget status: spend unknown/i)).toBeTruthy(),
    );
    expect(
      screen.getByText(/unknown \(ledger not inventing \$0\)/i),
    ).toBeTruthy();
    expect(screen.queryByText("$0.0000")).toBeNull();
  });
});
