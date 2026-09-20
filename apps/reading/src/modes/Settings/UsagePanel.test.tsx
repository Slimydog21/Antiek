import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import UsagePanel from "./UsagePanel";
import {
  fetchSettingsBalance,
  fetchSettingsUsage,
  setSettingsUsageLimit,
} from "../../api/settingsUsage";
import { fetchSettingsModels } from "../../api/settings";
import { fetchUserModels } from "../../api/settingsModels";

vi.mock("../../api/settingsUsage", () => ({
  fetchSettingsUsage: vi.fn(),
  setSettingsUsageLimit: vi.fn(),
  fetchSettingsBalance: vi.fn(),
}));

vi.mock("../../api/settings", () => ({
  fetchSettingsModels: vi.fn(),
}));

vi.mock("../../api/settingsModels", () => ({
  fetchUserModels: vi.fn(),
}));

const usage = {
  keys: [
    {
      api_key_id: "user-deepseek",
      used_cents: 120,
      limit_cents: 1000,
      remaining_cents: 880,
      held_cents: 40,
      available_cents: 840,
    },
    {
      api_key_id: "user-kimi",
      used_cents: 10,
      limit_cents: null,
      remaining_cents: null,
      held_cents: 0,
      available_cents: null,
    },
  ],
  count: 2,
};

const userModels = {
  models: [
    {
      id: "user-deepseek",
      provider_kind: "openai_compat" as const,
      provider_catalog_id: "deepseek",
      model_id: "deepseek-chat",
      display_name: "DeepSeek key",
      base_url: "https://api.deepseek.com",
      enabled: true,
      key_present: true,
      registered: true,
      route_eligible: true,
      pricing_status: "known" as const,
      hard_ceiling_eligible: false,
      execution_status: "blocked_idempotency_unproven" as const,
      rate_snapshot: "deepseek-v4",
    },
    {
      id: "user-kimi",
      provider_kind: "openai_compat" as const,
      provider_catalog_id: "kimi",
      model_id: "kimi-k2.5",
      display_name: "Kimi key",
      base_url: "https://api.moonshot.ai/v1",
      enabled: true,
      key_present: true,
      registered: true,
      route_eligible: true,
      pricing_status: "known" as const,
      hard_ceiling_eligible: false,
      execution_status: "blocked_idempotency_unproven" as const,
      rate_snapshot: "kimi-k2.5",
    },
  ],
  count: 2,
  stale_registered: [],
  source: "test",
};

const settingsModels = {
  models: [
    {
      provider_id: "user-deepseek",
      registered: true,
      ready: false,
      tier_bindings: ["pro"],
      primary_model: "deepseek-chat",
      model_id: "deepseek-chat",
      route_eligible: true,
      pricing_status: "known" as const,
      hard_ceiling_eligible: false,
      execution_status: "blocked_idempotency_unproven",
      rate_snapshot: "deepseek-v4",
      notes: null,
    },
    {
      provider_id: "user-kimi",
      registered: true,
      ready: false,
      tier_bindings: [],
      primary_model: "kimi-k2.5",
      model_id: "kimi-k2.5",
      route_eligible: true,
      pricing_status: "known" as const,
      hard_ceiling_eligible: false,
      execution_status: "blocked_idempotency_unproven",
      rate_snapshot: "kimi-k2.5",
      notes: null,
    },
  ],
  count: 2,
  providers_ready: false,
  source: "test",
};

describe("UsagePanel", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(fetchSettingsUsage).mockResolvedValue(usage);
    vi.mocked(fetchUserModels).mockResolvedValue(userModels);
    vi.mocked(fetchSettingsModels).mockResolvedValue(settingsModels);
    vi.mocked(fetchSettingsBalance).mockImplementation(async (id) => {
      if (id === "user-deepseek") {
        return {
          api_key_id: "user-deepseek",
          catalog_id: "deepseek",
          kind: "balance_native",
          balance_usd: 42.5,
          granted_usd: 100,
          spend_usd: 57.5,
          budget_usd: null,
          utilization: null,
          window_label: null,
          resets_at: null,
          note: null,
          held_cents: 40,
          available_cents: 840,
        };
      }
      return {
        api_key_id: "user-kimi",
        catalog_id: "kimi",
        kind: "unavailable",
        balance_usd: null,
        granted_usd: null,
        spend_usd: null,
        budget_usd: null,
        utilization: null,
        window_label: null,
        resets_at: null,
        note: "provider timeout",
        held_cents: 0,
        available_cents: null,
      };
    });
    vi.mocked(setSettingsUsageLimit).mockResolvedValue({
      api_key_id: "user-deepseek",
      used_cents: 120,
      limit_cents: 2500,
      remaining_cents: 2380,
      held_cents: 40,
      available_cents: 2340,
    });
  });

  afterEach(cleanup);

  it("renders per-key usage, model lists, and honest unavailable balance", async () => {
    render(<UsagePanel />);
    const deepseek = await screen.findByTestId("usage-row-user-deepseek");
    expect(within(deepseek).getByText("DeepSeek key")).toBeTruthy();
    expect(within(deepseek).getByText(/used \$1\.20 · cap \$10\.00 · remaining \$8\.80/)).toBeTruthy();
    expect(within(deepseek).getByText("Live balance $42.50")).toBeTruthy();
    expect(within(deepseek).getByText("deepseek-chat")).toBeTruthy();

    const kimi = await screen.findByTestId("usage-row-user-kimi");
    expect(within(kimi).getByText("Live balance unavailable")).toBeTruthy();
    expect(within(kimi).getByText("provider timeout")).toBeTruthy();
    expect(within(kimi).getByText(/remaining unknown/)).toBeTruthy();
  });

  it("saves and clears spend caps", async () => {
    const user = userEvent.setup();
    render(<UsagePanel />);
    const deepseek = await screen.findByTestId("usage-row-user-deepseek");
    const input = within(deepseek).getByLabelText("Spend cap (USD)") as HTMLInputElement;
    await user.clear(input);
    await user.type(input, "25");
    await user.click(within(deepseek).getByRole("button", { name: "Save cap" }));
    await waitFor(() =>
      expect(setSettingsUsageLimit).toHaveBeenCalledWith("user-deepseek", {
        limit_cents: 2500,
      }),
    );
    expect(await within(deepseek).findByText("Spend cap updated.")).toBeTruthy();

    vi.mocked(setSettingsUsageLimit).mockResolvedValueOnce({
      api_key_id: "user-deepseek",
      used_cents: 120,
      limit_cents: null,
      remaining_cents: null,
      held_cents: 40,
      available_cents: null,
    });
    await user.click(within(deepseek).getByRole("button", { name: "Clear cap" }));
    await waitFor(() =>
      expect(setSettingsUsageLimit).toHaveBeenLastCalledWith("user-deepseek", {
        limit_cents: null,
      }),
    );
    expect(await within(deepseek).findByText("Spend cap cleared.")).toBeTruthy();
  });

  it("shows value-free cap validation and load retry", async () => {
    vi.mocked(fetchUserModels).mockRejectedValueOnce(new Error("server echoed sk-secret"));
    const user = userEvent.setup();
    render(<UsagePanel />);
    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toContain("Can't load BYOT keys right now");
    expect(document.body.textContent).not.toContain("sk-secret");

    vi.mocked(fetchUserModels).mockResolvedValue(userModels);
    await user.click(screen.getByRole("button", { name: "Retry" }));
    expect(await screen.findByTestId("usage-row-user-deepseek")).toBeTruthy();

    const deepseek = screen.getByTestId("usage-row-user-deepseek");
    const input = within(deepseek).getByLabelText("Spend cap (USD)") as HTMLInputElement;
    await user.clear(input);
    await user.type(input, "-1");
    await user.click(within(deepseek).getByRole("button", { name: "Save cap" }));
    expect((await within(deepseek).findByRole("alert")).textContent).toContain(
      "Cap must be a non-negative dollar value.",
    );
  });
});
