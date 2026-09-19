import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import UsagePanel from "./UsagePanel";
import {
  fetchKeyBalance,
  fetchSettingsUsage,
  setKeyLimit,
} from "../../api/settingsUsage";

const userModel = {
  id: "user-my-deepseek",
  provider_kind: "openai_compat" as const,
  model_id: "deepseek-chat",
  display_name: "My DeepSeek",
  base_url: "https://api.deepseek.com/v1",
  enabled: true,
  key_present: true,
  registered: true,
};

vi.mock("../../api/settingsModels", () => ({
  fetchUserModels: vi.fn(async () => ({
    models: [userModel],
    count: 1,
    stale_registered: [],
    source: "test",
  })),
}));

vi.mock("../../api/settingsUsage", () => ({
  fetchSettingsUsage: vi.fn(async () => ({
    keys: [
      {
        api_key_id: "user-my-deepseek",
        used_cents: 12,
        limit_cents: 500,
        remaining_cents: 488,
      },
      {
        api_key_id: "user-kimi",
        used_cents: 345,
        limit_cents: null,
        remaining_cents: null,
      },
    ],
    count: 2,
  })),
  fetchKeyBalance: vi.fn(async (apiKeyId: string) => ({
    api_key_id: apiKeyId,
    catalog_id: "deepseek",
    kind: "balance_native" as const,
    balance_usd: 4.88,
    granted_usd: 3.0,
    spend_usd: null,
    budget_usd: null,
    utilization: null,
    window_label: null,
    resets_at: null,
    note: null,
  })),
  setKeyLimit: vi.fn(
    async (apiKeyId: string, limitCents: number | null) => ({
      api_key_id: apiKeyId,
      limit_cents: limitCents,
      used_cents: 12,
      remaining_cents: limitCents === null ? null : limitCents - 12,
    }),
  ),
}));

describe("UsagePanel", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  // vitest.config.ts sets globals:false, so RTL's auto-cleanup never
  // registers — clean up explicitly, like the sibling panel tests.
  afterEach(cleanup);

  it("renders one row per key with resolved names and honest limit/remaining", async () => {
    render(<UsagePanel />);
    // Display name resolved through the user-model inventory.
    expect(await screen.findByText(/My DeepSeek · deepseek-chat/)).toBeTruthy();
    expect(screen.getByText(/user-kimi/)).toBeTruthy();
    // Usage line: cents rendered as dollars.
    expect(screen.getByText("used $0.12")).toBeTruthy();
    expect(screen.getByText("limit $5.00")).toBeTruthy();
    expect(screen.getByText("remaining $4.88")).toBeTruthy();
    // Null limit → "no cap"; null remaining → "unknown" (never $0.00).
    expect(screen.getByText("limit no cap")).toBeTruthy();
    expect(screen.getByText("remaining unknown")).toBeTruthy();
    // Live balance line per key.
    expect(await screen.findAllByTestId("balance-line")).toHaveLength(2);
    expect(screen.getAllByText(/native balance/).length).toBe(2);
    expect(screen.getAllByText("$4.88").length).toBeGreaterThanOrEqual(2);
  });

  it("keeps unknown values unknown and only shows an honest zero", async () => {
    vi.mocked(fetchSettingsUsage).mockResolvedValueOnce({
      keys: [
        {
          api_key_id: "user-zero",
          used_cents: 0,
          limit_cents: 100,
          remaining_cents: 100,
        },
        {
          api_key_id: "user-blank",
          used_cents: 7,
          limit_cents: null,
          remaining_cents: null,
        },
      ],
      count: 2,
    });
    render(<UsagePanel />);
    // used_cents is truly 0 — "$0.00" here is the ledger's honest zero.
    expect(await screen.findByText("used $0.00")).toBeTruthy();
    expect(screen.getByText("remaining $1.00")).toBeTruthy();
    // A null remaining is unknown — the UI never invents $0.00 for it.
    expect(screen.getByText("remaining unknown")).toBeTruthy();
    expect(screen.queryByText("remaining $0.00")).toBeNull();
    expect(screen.queryByText("limit $0.00")).toBeNull();
  });

  it("sets a limit from a dollar input and clears it back to no cap", async () => {
    const user = userEvent.setup();
    render(<UsagePanel />);
    const input = await screen.findByRole("textbox", {
      name: /Set limit for My DeepSeek/,
    });
    await user.type(input, "7.50");
    await user.click(screen.getByRole("button", { name: "Set" }));

    await waitFor(() =>
      expect(vi.mocked(setKeyLimit)).toHaveBeenCalledWith(
        "user-my-deepseek",
        750,
      ),
    );
    // Row reflects the server's updated ledger row (remaining 750 − 12).
    expect(await screen.findByText("limit $7.50")).toBeTruthy();
    expect(screen.getByText("remaining $7.38")).toBeTruthy();
    // Input cleared after save.
    expect((input as HTMLInputElement).value).toBe("");

    await user.click(screen.getByRole("button", { name: "Clear cap" }));
    await waitFor(() =>
      expect(vi.mocked(setKeyLimit)).toHaveBeenCalledWith(
        "user-my-deepseek",
        null,
      ),
    );
    expect(await screen.findByText("limit no cap")).toBeTruthy();
    expect(screen.getByText("remaining unknown")).toBeTruthy();
  });

  it("shows the adapter's unavailable note verbatim instead of a number", async () => {
    vi.mocked(fetchKeyBalance).mockResolvedValue({
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
      note: "adapter error: TimeoutError: balance endpoint timed out",
    });
    render(<UsagePanel />);
    const lines = await screen.findAllByTestId("balance-unavailable");
    expect(lines.some((line) =>
      line.textContent?.includes(
        "adapter error: TimeoutError: balance endpoint timed out",
      ),
    )).toBe(true);
  });

  it("renders the honest empty state when no BYOT keys exist", async () => {
    vi.mocked(fetchSettingsUsage).mockResolvedValueOnce({ keys: [], count: 0 });
    render(<UsagePanel />);
    expect(
      await screen.findByText("No BYOT keys yet — add one below."),
    ).toBeTruthy();
    expect(screen.queryByTestId("balance-line")).toBeNull();
  });
});
