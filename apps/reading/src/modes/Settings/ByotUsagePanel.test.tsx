import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, waitFor } from "@testing-library/react";

import { fetchKeyBalance, fetchKeyUsage } from "../../api/settingsModels";
import ByotUsagePanel from "./ByotUsagePanel";

vi.mock("../../api/settingsModels", () => ({
  fetchKeyUsage: vi.fn(),
  fetchKeyBalance: vi.fn(),
}));

const usage = {
  keys: [
    { api_key_id: "user-deepseek", used_cents: 1234, limit_cents: 5000, remaining_cents: 3766 },
    { api_key_id: "user-mimo", used_cents: 0, limit_cents: null, remaining_cents: null },
  ],
  count: 2,
};

describe("ByotUsagePanel", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(fetchKeyUsage).mockResolvedValue(usage);
    vi.mocked(fetchKeyBalance).mockImplementation(async (id) => {
      if (id === "user-deepseek") {
        return {
          api_key_id: id, catalog_id: "deepseek", kind: "balance_native",
          balance_usd: 8.75, granted_usd: null, spend_usd: null,
          budget_usd: null, utilization: null, window_label: null,
          resets_at: null, note: "provider reported",
        };
      }
      return {
        api_key_id: id, catalog_id: "mimo", kind: "meter_only",
        balance_usd: null, granted_usd: null, spend_usd: null,
        budget_usd: null, utilization: null, window_label: null,
        resets_at: null, note: "no provider endpoint",
      };
    });
  });

  afterEach(cleanup);

  it("renders exact ledger cents separately from provider balance", async () => {
    render(<ByotUsagePanel />);
    await waitFor(() => expect(screen.getByText("$8.75 provider balance")).toBeTruthy());
    expect(screen.getByText("$12.34")).toBeTruthy();
    expect(screen.getByText("$50.00")).toBeTruthy();
    expect(screen.getByText("$37.66")).toBeTruthy();
    expect(screen.getByText("local meter only")).toBeTruthy();
  });

  it("shows nullable limits as unset and remaining as unknown, never invented zero", async () => {
    render(<ByotUsagePanel />);
    await waitFor(() => expect(screen.getByText("user-mimo")).toBeTruthy());
    expect(screen.getByText("unset")).toBeTruthy();
    expect(screen.getByText("unknown")).toBeTruthy();
  });

  it("contains a failed balance request to its row", async () => {
    vi.mocked(fetchKeyBalance).mockImplementation(async (id) => {
      if (id === "user-deepseek") throw new Error("provider timeout");
      return {
        api_key_id: id, catalog_id: "mimo", kind: "meter_only",
        balance_usd: null, granted_usd: null, spend_usd: null,
        budget_usd: null, utilization: null, window_label: null,
        resets_at: null, note: null,
      };
    });
    render(<ByotUsagePanel />);
    await waitFor(() => expect(screen.getByText("unavailable")).toBeTruthy());
    expect(screen.getByText("local meter only")).toBeTruthy();
    expect(screen.getByText("$12.34")).toBeTruthy();
  });

  it("reports a ledger failure without rendering key material", async () => {
    vi.mocked(fetchKeyUsage).mockRejectedValue(new Error("session expired"));
    render(<ByotUsagePanel />);
    await waitFor(() => expect(screen.getByRole("alert").textContent).toContain("session expired"));
    expect(document.body.textContent).not.toContain("sk-");
  });
});
