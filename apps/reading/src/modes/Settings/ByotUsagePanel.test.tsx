import { cleanup, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { fetchUserModels } from "../../api/settingsModels";
import { fetchKeyBalance, fetchUsageSnapshot, setKeyLimit } from "../../api/byotUsage";
import ByotUsagePanel from "./ByotUsagePanel";

vi.mock("../../api/settingsModels", () => ({ fetchUserModels: vi.fn() }));
vi.mock("../../api/byotUsage", () => ({
  fetchKeyBalance: vi.fn(),
  fetchUsageSnapshot: vi.fn(),
  setKeyLimit: vi.fn(),
}));

const models = [{
  id: "user-model-1",
  provider_kind: "openai_compat" as const,
  provider_catalog_id: "deepseek",
  model_id: "deepseek-chat",
  display_name: "My DeepSeek",
  base_url: "https://api.deepseek.test",
  enabled: true,
  key_present: true,
  registered: true,
}];
const usage = { api_key_id: "user-model-1", used_cents: 125, limit_cents: 500, remaining_cents: 375 };
const balance = {
  api_key_id: "user-model-1",
  catalog_id: "deepseek",
  kind: "balance_native" as const,
  balance_usd: 23.5,
  granted_usd: 30,
  spend_usd: null,
  budget_usd: null,
  utilization: null,
  window_label: null,
  resets_at: null,
  note: null,
};

describe("ByotUsagePanel", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(fetchUserModels).mockResolvedValue({ models, count: 1, stale_registered: [], source: "test" });
    vi.mocked(fetchUsageSnapshot).mockResolvedValue({ keys: [usage], count: 1 });
    vi.mocked(fetchKeyBalance).mockResolvedValue(balance);
    vi.mocked(setKeyLimit).mockResolvedValue(usage);
  });
  afterEach(cleanup);

  it("separates Antiek-measured spend from provider balance", async () => {
    render(<ByotUsagePanel />);
    const row = (await screen.findByText("My DeepSeek")).closest("li")!;
    expect(within(row).getByText("$1.25")).toBeTruthy();
    expect(within(row).getByText("Antiek measured")).toBeTruthy();
    expect(within(row).getByText("$23.50 available")).toBeTruthy();
    expect(within(row).getByText("Provider balance")).toBeTruthy();
    expect(within(row).getByRole("meter").getAttribute("value")).toBe("0.25");
  });

  it("shows a newly stored key even before its first ledger row", async () => {
    vi.mocked(fetchUsageSnapshot).mockResolvedValueOnce({ keys: [], count: 0 });
    render(<ByotUsagePanel />);
    const row = (await screen.findByText("My DeepSeek")).closest("li")!;
    expect(within(row).getByText("Not measured yet")).toBeTruthy();
    expect(within(row).getByText("No ledger observation")).toBeTruthy();
    expect(within(row).getByText("No limit")).toBeTruthy();
  });

  it("saves a precise dollar limit as integer cents", async () => {
    const user = userEvent.setup();
    render(<ByotUsagePanel />);
    const row = (await screen.findByText("My DeepSeek")).closest("li")!;
    await user.click(within(row).getByRole("button", { name: "Change limit" }));
    const input = within(row).getByLabelText("Spending limit (USD)");
    await user.clear(input);
    await user.type(input, "12.34");
    await user.click(within(row).getByRole("button", { name: "Save limit" }));
    await waitFor(() => expect(setKeyLimit).toHaveBeenCalledWith("user-model-1", 1234));
  });

  it("converts binary-float edge values such as 0.29 exactly", async () => {
    const user = userEvent.setup();
    render(<ByotUsagePanel />);
    const row = (await screen.findByText("My DeepSeek")).closest("li")!;
    await user.click(within(row).getByRole("button", { name: "Change limit" }));
    const input = within(row).getByLabelText("Spending limit (USD)");
    await user.clear(input);
    await user.type(input, "0.29");
    await user.click(within(row).getByRole("button", { name: "Save limit" }));
    await waitFor(() => expect(setKeyLimit).toHaveBeenCalledWith("user-model-1", 29));
  });

  it("rejects fractional cents without calling the API", async () => {
    const user = userEvent.setup();
    render(<ByotUsagePanel />);
    const row = (await screen.findByText("My DeepSeek")).closest("li")!;
    await user.click(within(row).getByRole("button", { name: "Change limit" }));
    const input = within(row).getByLabelText("Spending limit (USD)");
    await user.clear(input);
    await user.type(input, "1.005");
    await user.click(within(row).getByRole("button", { name: "Save limit" }));
    expect((await within(row).findByRole("alert")).textContent).toContain("no more than two decimals");
    expect(setKeyLimit).not.toHaveBeenCalled();
  });

  it.each(["1e3", " 1.00", "1.00 ", "", "999999999999999999999999"])(
    "rejects non-canonical or unsafe dollar input %j",
    async (value) => {
      const user = userEvent.setup();
      render(<ByotUsagePanel />);
      const row = (await screen.findByText("My DeepSeek")).closest("li")!;
      await user.click(within(row).getByRole("button", { name: "Change limit" }));
      const input = within(row).getByLabelText("Spending limit (USD)");
      await user.clear(input);
      if (value) await user.type(input, value);
      await user.click(within(row).getByRole("button", { name: "Save limit" }));
      if (value === "") {
        expect((input as HTMLInputElement).validity.valueMissing).toBe(true);
      } else {
        expect(await within(row).findByRole("alert")).toBeTruthy();
      }
      expect(setKeyLimit).not.toHaveBeenCalled();
    },
  );

  it.each([
    ["spend_history", { ...balance, kind: "spend_history", balance_usd: null, granted_usd: null, spend_usd: 1.25, budget_usd: 5 }, "$1.25 measured spend", "Antiek meter"],
    ["quota_pct", { ...balance, kind: "quota_pct", balance_usd: null, granted_usd: null, utilization: 0.4, window_label: "Monthly quota" }, "40% quota used", "Provider quota"],
    ["meter_only", { ...balance, kind: "meter_only", balance_usd: null, granted_usd: null, spend_usd: 2.5, window_label: "This month" }, "$2.50 measured spend", "Antiek meter"],
  ] as const)("renders %s with its actual authority", async (_kind, snapshot, headline, authority) => {
    vi.mocked(fetchKeyBalance).mockResolvedValueOnce({ ...snapshot, resets_at: null, note: null });
    render(<ByotUsagePanel />);
    const row = (await screen.findByText("My DeepSeek")).closest("li")!;
    expect(within(row).getByText(headline)).toBeTruthy();
    expect(within(row).getByText(authority)).toBeTruthy();
  });

  it("does not let an older refresh overwrite a newly saved limit", async () => {
    const user = userEvent.setup();
    let release!: (value: { keys: typeof usage[]; count: number }) => void;
    const stale = new Promise<{ keys: typeof usage[]; count: number }>((resolve) => { release = resolve; });
    render(<ByotUsagePanel />);
    const row = (await screen.findByText("My DeepSeek")).closest("li")!;
    vi.mocked(fetchUsageSnapshot).mockReturnValueOnce(stale);
    await user.click(screen.getByRole("button", { name: "Refresh balances" }));
    await user.click(within(row).getByRole("button", { name: "Change limit" }));
    const input = within(row).getByLabelText("Spending limit (USD)");
    await user.clear(input);
    await user.type(input, "12.34");
    vi.mocked(setKeyLimit).mockResolvedValueOnce({ ...usage, limit_cents: 1234, remaining_cents: 1109 });
    await user.click(within(row).getByRole("button", { name: "Save limit" }));
    await waitFor(() => expect(within(row).getByText("$11.09")).toBeTruthy());
    release({ keys: [{ ...usage, limit_cents: 500, remaining_cents: 375 }], count: 1 });
    await new Promise((resolve) => setTimeout(resolve, 0));
    expect(within(row).getByText("$11.09")).toBeTruthy();
  });

  it("globally locks limit editors while a save is in flight", async () => {
    const user = userEvent.setup();
    const second = { ...models[0], id: "user-model-2", display_name: "My Kimi", provider_catalog_id: "kimi" };
    vi.mocked(fetchUserModels).mockResolvedValueOnce({ models: [models[0], second], count: 2, stale_registered: [], source: "test" });
    vi.mocked(fetchUsageSnapshot).mockResolvedValueOnce({ keys: [usage, { ...usage, api_key_id: second.id }], count: 2 });
    vi.mocked(fetchKeyBalance)
      .mockResolvedValueOnce(balance)
      .mockResolvedValueOnce({ ...balance, api_key_id: second.id, catalog_id: "kimi" });
    let release!: (value: typeof usage) => void;
    vi.mocked(setKeyLimit).mockReturnValueOnce(new Promise((resolve) => { release = resolve; }));
    render(<ByotUsagePanel />);
    const firstRow = (await screen.findByText("My DeepSeek")).closest("li")!;
    const secondRow = screen.getByText("My Kimi").closest("li")!;
    await user.click(within(firstRow).getByRole("button", { name: "Change limit" }));
    await user.clear(within(firstRow).getByLabelText("Spending limit (USD)"));
    await user.type(within(firstRow).getByLabelText("Spending limit (USD)"), "12.34");
    await user.click(within(firstRow).getByRole("button", { name: "Save limit" }));
    expect((within(secondRow).getByRole("button", { name: "Change limit" }) as HTMLButtonElement).disabled).toBe(true);
    expect((within(firstRow).getByRole("button", { name: "Saving…" }) as HTMLButtonElement).disabled).toBe(true);
    release({ ...usage, limit_cents: 1234, remaining_cents: 1109 });
    await waitFor(() => expect((within(secondRow).getByRole("button", { name: "Change limit" }) as HTMLButtonElement).disabled).toBe(false));
  });

  it("rejects balance data bound to a different provider catalog", async () => {
    vi.mocked(fetchKeyBalance).mockResolvedValueOnce({ ...balance, catalog_id: "kimi" });
    render(<ByotUsagePanel />);
    const row = (await screen.findByText("My DeepSeek")).closest("li")!;
    expect(within(row).getByText("Balance unavailable")).toBeTruthy();
    expect(within(row).getByText("No usable provider report")).toBeTruthy();
  });

  it("returns focus to the limit trigger after cancel", async () => {
    const user = userEvent.setup();
    render(<ByotUsagePanel />);
    const row = (await screen.findByText("My DeepSeek")).closest("li")!;
    const trigger = within(row).getByRole("button", { name: "Change limit" });
    await user.click(trigger);
    await user.click(within(row).getByRole("button", { name: "Cancel" }));
    await waitFor(() => expect(document.activeElement).toBe(within(row).getByRole("button", { name: "Change limit" })));
  });

  it("states unavailable honestly and retains the rest of the row", async () => {
    vi.mocked(fetchKeyBalance).mockRejectedValueOnce(new Error("balance API 503"));
    render(<ByotUsagePanel />);
    const row = (await screen.findByText("My DeepSeek")).closest("li")!;
    expect(within(row).getByText("Balance unavailable")).toBeTruthy();
    expect(within(row).getByText("No usable provider report")).toBeTruthy();
    expect(within(row).getByText("$1.25")).toBeTruthy();
  });

  it("uses 44px controls for mobile limit actions", async () => {
    const user = userEvent.setup();
    render(<ByotUsagePanel />);
    const row = (await screen.findByText("My DeepSeek")).closest("li")!;
    await user.click(within(row).getByRole("button", { name: "Change limit" }));
    expect(within(row).getByRole("button", { name: "Save limit" }).className).toContain("h-11");
    expect(within(row).getByLabelText("Spending limit (USD)").closest("label")?.className).toContain("h-11");
  });
});
