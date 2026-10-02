import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

const { inventory, recent, quote, send, usageSnapshot, balanceSnapshot, authState } = vi.hoisted(() => ({
  inventory: vi.fn(), recent: vi.fn(), quote: vi.fn(), send: vi.fn(),
  usageSnapshot: vi.fn(), balanceSnapshot: vi.fn(),
  authState: { current: { status: "authenticated", identity: { user_id: "owner-a", email: "a@example.test" } } },
}));

vi.mock("../../lib/auth", () => ({ useAuth: () => ({ state: authState.current }) }));

vi.mock("../../api/quickAsk", async (original) => {
  const actual = await original<typeof import("../../api/quickAsk")>();
  return {
    ...actual, fetchQuickAskModels: inventory, fetchQuickAskRecent: recent,
    quoteQuickAsk: quote, sendQuickAsk: send,
  };
});

vi.mock("../../api/settingsUsage", () => ({ fetchSettingsUsage: usageSnapshot, fetchSettingsBalance: balanceSnapshot }));
import type { SettingsBalanceResponse, SettingsUsageSnapshotResponse } from "../../api/settingsUsage";

import { QuickAskError } from "../../api/quickAsk";
import QuickAsk from "./QuickAsk";

const currentModel = {
  provider_id: "user-deepseek", model_id: "deepseek-flash", display_name: "My DeepSeek",
  price_snapshot: "deepseek-2026-09-27", price_source: "https://api-docs.deepseek.com/pricing",
};

const quoted = {
  quote_digest: "a".repeat(64), estimate_usd: "0.0042", reserved_cents: 1,
  price_snapshot: "deepseek-2026-09-27", price_source: "https://api-docs.deepseek.com/pricing",
  provider_id: "user-deepseek", model_id: "deepseek-flash", max_output_tokens: 1024,
  warning: "Estimate, not a provider cap. A network failure after sending may leave the charge unknown.",
};

function renderQuickAsk(onPaidRequestInFlight?: (pending: boolean) => void) {
  return render(<MemoryRouter><QuickAsk onPaidRequestInFlight={onPaidRequestInFlight} /></MemoryRouter>);
}

async function selectFlash() {
  const selector = await screen.findByRole("combobox", { name: "Quick Ask model" });
  fireEvent.click(selector.querySelector("button")!);
  fireEvent.click(await screen.findByRole("option", { name: /My DeepSeek · deepseek-flash/ }));
}

beforeEach(() => {
  window.sessionStorage.clear();
  authState.current.identity.user_id = "owner-a";
  authState.current.identity.email = "a@example.test";
  inventory.mockReset(); recent.mockReset(); quote.mockReset(); send.mockReset();
  usageSnapshot.mockReset(); balanceSnapshot.mockReset();
  usageSnapshot.mockResolvedValue({ keys: [], count: 0 });
  balanceSnapshot.mockImplementation(async (id: string) => nativeBalance(id));
  inventory.mockResolvedValue([currentModel]);
  recent.mockResolvedValue([]);
  quote.mockResolvedValue(quoted);
  send.mockResolvedValue({
    answer: "A bounded answer.", operation_id: "quick-1", provider_id: "user-deepseek",
    model_id: "deepseek-flash", estimated_cost_usd: 0.0038,
    usage_basis: "provider_reported_tokens_priced_locally", input_tokens: 120,
    output_tokens: 42, replayed: false, incomplete: false,
    reported_usage_estimate_exceeds_quote: false,
  });
});

afterEach(() => cleanup());

describe("Quick Ask one-request boundary", () => {
  it("restores a stored answer with no eligible model and makes no paid request", async () => {
    inventory.mockResolvedValue([]);
    const operationId = "9d4b35fb-a34a-4a4e-9977-9f822ce0bfd3";
    recent.mockResolvedValue([{
      operation_id: operationId, created_at: "2026-09-27T08:59:00+00:00",
      status: "answered",
      result: {
        answer: "A stored answer.", operation_id: operationId,
        provider_id: "user-deepseek", model_id: "deepseek-flash",
        estimated_cost_usd: 0.0038, usage_basis: "prior_receipt",
        input_tokens: null, output_tokens: null, replayed: true,
        incomplete: false, reported_usage_estimate_exceeds_quote: true,
      },
    }]);
    renderQuickAsk();
    expect(await screen.findByText(/No current saved model is ready/)).toBeTruthy();
    fireEvent.click(await screen.findByRole("button", { name: "View stored answer" }));
    expect(screen.getByRole("article", { name: "Stored Quick Ask answer" }).textContent).toContain("A stored answer.");
    expect(screen.getByText(/no new model request was sent/i)).toBeTruthy();
    expect(screen.getByText(/provider-reported usage priced above the quote/i)).toBeTruthy();
    expect(quote).not.toHaveBeenCalled();
    expect(send).not.toHaveBeenCalled();
  });

  it("recovers a later stored answer without clearing a pending unknown-charge marker", async () => {
    const operationId = "9d4b35fb-a34a-4a4e-9977-9f822ce0bfd3";
    window.sessionStorage.setItem("antiek.quick-ask.pending-send.session.v1:owner-a", operationId);
    recent.mockResolvedValueOnce([]).mockResolvedValueOnce([{
      operation_id: operationId, created_at: "2026-09-27T08:59:00+00:00",
      status: "answered",
      result: {
        answer: "The provider did answer.", operation_id: operationId,
        provider_id: "user-deepseek", model_id: "deepseek-flash",
        estimated_cost_usd: null, usage_basis: "charge_unknown",
        input_tokens: null, output_tokens: null, replayed: true,
        incomplete: false, reported_usage_estimate_exceeds_quote: null,
      },
    }]);
    renderQuickAsk();
    expect(await screen.findByText(/No recent request receipt is available/)).toBeTruthy();
    expect(screen.getByText(/Charge unknown\. Check your provider dashboard/)).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Refresh receipts" }));
    fireEvent.click(await screen.findByRole("button", { name: "View stored answer" }));
    expect(screen.getByRole("article", { name: "Stored Quick Ask answer" }).textContent).toContain("The provider did answer.");
    expect(screen.getByText(/Charge unknown\. Check your provider dashboard/)).toBeTruthy();
    expect(window.sessionStorage.getItem("antiek.quick-ask.pending-send.session.v1:owner-a")).toBe(operationId);
    expect(send).not.toHaveBeenCalled();
  });

  it("does not render an old owner's late receipt after the account changes", async () => {
    let releaseOld: ((value: unknown) => void) | undefined;
    recent.mockImplementationOnce(() => new Promise((resolve) => { releaseOld = resolve; }));
    recent.mockResolvedValueOnce([]);
    const view = renderQuickAsk();
    await waitFor(() => expect(recent).toHaveBeenCalledTimes(1));
    authState.current.identity.user_id = "owner-b";
    view.rerender(<MemoryRouter><QuickAsk /></MemoryRouter>);
    await waitFor(() => expect(recent).toHaveBeenCalledTimes(2));
    releaseOld?.([{
      operation_id: "9d4b35fb-a34a-4a4e-9977-9f822ce0bfd3",
      created_at: "2026-09-27T08:59:00+00:00", status: "answered",
      result: { answer: "Owner A private answer" },
    }]);
    expect(await screen.findByText(/No recent request receipt is available/)).toBeTruthy();
    expect(screen.queryByText(/Owner A private answer/)).toBeNull();
    expect(send).not.toHaveBeenCalled();
  });

  it("restores a no-blind-retry warning after navigation during an unresolved paid send", async () => {
    let rejectSend: ((reason: Error) => void) | undefined;
    send.mockImplementation(() => new Promise((_resolve, reject) => { rejectSend = reject; }));
    const first = renderQuickAsk();
    await selectFlash();
    fireEvent.change(screen.getByLabelText("Quick Ask question"), {
      target: { value: "What if the browser leaves?" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Review estimate" }));
    await screen.findByText(/Estimated request cost/);
    fireEvent.click(screen.getByRole("button", { name: "Send one request" }));
    const operationId = send.mock.calls[0][0].operation_id;
    expect(window.sessionStorage.getItem("antiek.quick-ask.pending-send.session.v1:owner-a")).toBe(operationId);
    first.unmount();
    renderQuickAsk();
    expect(screen.getByText(new RegExp(operationId))).toBeTruthy();
    expect(screen.getByText(/Check your provider dashboard before making another request/)).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Send one request" })).toBeNull();
    expect(send).toHaveBeenCalledTimes(1);
    rejectSend?.(new QuickAskError("charge_unknown"));
  });

  it("does not show another email's pending request under the shared operator sentinel", async () => {
    send.mockRejectedValue(new QuickAskError("charge_unknown"));
    authState.current.identity.user_id = "__operator__";
    const view = renderQuickAsk();
    await selectFlash();
    fireEvent.change(screen.getByLabelText("Quick Ask question"), {
      target: { value: "Owner A's question?" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Review estimate" }));
    await screen.findByText(/Estimated request cost/);
    fireEvent.click(screen.getByRole("button", { name: "Send one request" }));
    const operationId = send.mock.calls[0][0].operation_id;
    await screen.findByText(/Charge unknown\. Check your provider dashboard/);
    authState.current.identity.email = "b@example.test";
    view.rerender(<MemoryRouter><QuickAsk /></MemoryRouter>);
    expect(screen.queryByText(new RegExp(operationId))).toBeNull();
    expect(screen.queryByText(/Charge unknown\. Check your provider dashboard/)).toBeNull();
    expect(window.sessionStorage.getItem("antiek.quick-ask.pending-send.session.v1:__operator__%3Aa%40example.test")).toBe(operationId);
    expect(window.sessionStorage.getItem("antiek.quick-ask.pending-send.session.v1:__operator__%3Ab%40example.test")).toBeNull();
    expect(send).toHaveBeenCalledTimes(1);
  });

  it("reports only the paid in-flight interval to its mounted Research home", async () => {
    let resolveSend: ((value: unknown) => void) | undefined;
    send.mockImplementation(() => new Promise((resolve) => { resolveSend = resolve; }));
    const onPaidRequestInFlight = vi.fn();
    renderQuickAsk(onPaidRequestInFlight);
    await selectFlash();
    fireEvent.change(screen.getByLabelText("Quick Ask question"), {
      target: { value: "What remains uncertain?" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Review estimate" }));
    await screen.findByText(/Estimated request cost/);
    expect(onPaidRequestInFlight).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "Send one request" }));
    expect(onPaidRequestInFlight).toHaveBeenCalledWith(true);
    expect(send).toHaveBeenCalledTimes(1);
    const operationId = send.mock.calls[0][0].operation_id;
    resolveSend?.({
      answer: "A bounded answer.", operation_id: operationId,
      provider_id: "user-deepseek", model_id: "deepseek-flash",
      estimated_cost_usd: 0.0038, usage_basis: "provider_reported_tokens_priced_locally",
      input_tokens: 120, output_tokens: 42, replayed: false, incomplete: false,
      reported_usage_estimate_exceeds_quote: false,
    });
    expect((await screen.findByRole("article", { name: "Quick Ask answer" })).textContent).toContain("A bounded answer.");
    await waitFor(() => expect(onPaidRequestInFlight).toHaveBeenLastCalledWith(false));
    expect(screen.getByText(new RegExp(operationId))).toBeTruthy();
    expect(send).toHaveBeenCalledTimes(1);
  });

  it("shows a separately eligible saved variant and requires a visible quote before one send", async () => {
    renderQuickAsk();
    await selectFlash();
    fireEvent.change(screen.getByLabelText("Quick Ask question"), {
      target: { value: "What is the counterargument?" },
    });
    expect(send).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "Review estimate" }));
    expect(await screen.findByText(/Estimated request cost: \$0\.0042/)).toBeTruthy();
    expect(screen.getByText(/network failure after sending may leave the charge unknown/i)).toBeTruthy();
    expect(send).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "Send one request" }));
    expect((await screen.findByRole("article", { name: "Quick Ask answer" })).textContent).toContain("A bounded answer.");
    expect(quote).toHaveBeenCalledTimes(1);
    expect(send).toHaveBeenCalledTimes(1);
    expect(send).toHaveBeenCalledWith(expect.objectContaining({
      question: "What is the counterargument?",
      model_choice: { authority: "user_model", provider_id: "user-deepseek", model_id: "deepseek-flash" },
    }), quoted);
    expect(screen.getByText(/Antiek-estimated cost/)).toBeTruthy();
    expect(screen.getByText(/final charge is not reconciled/)).toBeTruthy();
  });

  it("shows empty server eligibility and points the owner to Settings", async () => {
    inventory.mockResolvedValue([]);
    renderQuickAsk();
    expect(await screen.findByText(/No current saved model is ready/)).toBeTruthy();
    expect(screen.getByRole("link", { name: /Connect a model in Settings/ }).getAttribute("href")).toBe("/settings");
    expect((screen.getByRole("button", { name: "Review estimate" }) as HTMLButtonElement).disabled).toBe(true);
    expect(quote).not.toHaveBeenCalled();
    expect(send).not.toHaveBeenCalled();
  });

  it("holds an ambiguous sent outcome instead of retrying", async () => {
    send.mockRejectedValue(new QuickAskError("charge_unknown"));
    renderQuickAsk();
    await selectFlash();
    fireEvent.change(screen.getByLabelText("Quick Ask question"), { target: { value: "What remains unknown?" } });
    fireEvent.click(screen.getByRole("button", { name: "Review estimate" }));
    await screen.findByText(/Estimated request cost/);
    fireEvent.click(screen.getByRole("button", { name: "Send one request" }));
    expect(await screen.findByText(/Charge unknown\. Check your provider dashboard before making another request/)).toBeTruthy();
    expect(send).toHaveBeenCalledTimes(1);
    expect(screen.queryByRole("button", { name: "Send one request" })).toBeNull();
    expect(window.sessionStorage.getItem("antiek.quick-ask.pending-send.session.v1:owner-a")).toBe(send.mock.calls[0][0].operation_id);
    fireEvent.click(screen.getByRole("button", { name: "I checked my provider · new question" }));
    expect(window.sessionStorage.getItem("antiek.quick-ask.pending-send.session.v1:owner-a")).toBeNull();
  });

  it("holds a server 503 after Send instead of making an editable second attempt", async () => {
    send.mockRejectedValue(new QuickAskError("quick_ask_unavailable"));
    renderQuickAsk();
    await selectFlash();
    fireEvent.change(screen.getByLabelText("Quick Ask question"), {
      target: { value: "Did the provider answer?" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Review estimate" }));
    await screen.findByText(/Estimated request cost/);
    fireEvent.click(screen.getByRole("button", { name: "Send one request" }));
    const operationId = send.mock.calls[0][0].operation_id;
    expect(await screen.findByText(/Charge unknown\. Check your provider dashboard/)).toBeTruthy();
    expect(screen.queryByLabelText("Quick Ask question")).toBeNull();
    expect(screen.queryByRole("button", { name: "Send one request" })).toBeNull();
    expect(window.sessionStorage.getItem("antiek.quick-ask.pending-send.session.v1:owner-a")).toBe(operationId);
    expect(send).toHaveBeenCalledTimes(1);
  });

  it("labels a length-limited answer incomplete without a follow-up request", async () => {
    send.mockResolvedValue({
      answer: "A partial answer.", operation_id: "quick-2", provider_id: "user-deepseek",
      model_id: "deepseek-flash", estimated_cost_usd: 0.004,
      usage_basis: "provider_reported_tokens_priced_locally", input_tokens: 20,
      output_tokens: 1024, replayed: false, incomplete: true,
      reported_usage_estimate_exceeds_quote: false,
    });
    renderQuickAsk();
    await selectFlash();
    fireEvent.change(screen.getByLabelText("Quick Ask question"), { target: { value: "Explain the whole argument." } });
    fireEvent.click(screen.getByRole("button", { name: "Review estimate" }));
    await screen.findByText(/Estimated request cost/);
    fireEvent.click(screen.getByRole("button", { name: "Send one request" }));
    expect(await screen.findByText(/This answer may be incomplete/)).toBeTruthy();
    expect(send).toHaveBeenCalledTimes(1);
  });

  it("discards a quote that returns after its question was edited", async () => {
    let resolveQuote: ((value: typeof quoted) => void) | undefined;
    quote.mockImplementation(() => new Promise((resolve) => { resolveQuote = resolve; }));
    renderQuickAsk();
    await selectFlash();
    const question = screen.getByLabelText("Quick Ask question");
    fireEvent.change(question, { target: { value: "Initial question?" } });
    fireEvent.click(screen.getByRole("button", { name: "Review estimate" }));
    fireEvent.change(question, { target: { value: "Changed question?" } });
    resolveQuote?.(quoted);
    await waitFor(() => expect(screen.queryByText(/Estimated request cost/)).toBeNull());
    expect(send).not.toHaveBeenCalled();
  });
});

function nativeBalance(api_key_id: string): SettingsBalanceResponse {
  return { api_key_id, catalog_id: "deepseek", kind: "balance_native",
    balance_usd: null, granted_usd: null, spend_usd: null, budget_usd: null,
    utilization: null, window_label: null, resets_at: null, note: null,
    held_cents: 300, available_cents: 500, native_available: true,
    native_balances: [
      { currency: "CNY", total: "12.3400", granted: "0", topped_up: "12.3400" },
      { currency: "USD", total: "1.25", granted: "0", topped_up: "1.25" },
    ] };
}
function localUsage(api_key_id = "user-deepseek"): SettingsUsageSnapshotResponse {
  return { keys: [{ api_key_id, used_cents: 200, limit_cents: 1000,
    remaining_cents: 800, held_cents: 300, available_cents: 500 }], count: 1 };
}
function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason: Error) => void;
  const promise = new Promise<T>((yes, no) => { resolve = yes; reject = no; });
  return { promise, resolve, reject };
}
async function openModels() {
  const selector = await screen.findByRole("combobox", { name: "Quick Ask model" });
  fireEvent.click(selector.querySelector("button")!);
}
function changeOwner(view: ReturnType<typeof render>, operator: boolean) {
  if (operator) authState.current.identity.email = "b@example.test";
  else authState.current.identity.user_id = "owner-b";
  view.rerender(<MemoryRouter><QuickAsk /></MemoryRouter>);
}

describe("Quick Ask per-key read-only snapshots", () => {
  it("keeps the inventory loading message while no saved model is known", async () => {
    const pending = deferred<typeof currentModel[]>();
    inventory.mockReturnValueOnce(pending.promise);
    renderQuickAsk();
    expect(screen.getByRole("combobox", { name: "Quick Ask model" }).textContent)
      .toContain("Checking saved models…");
    expect(balanceSnapshot).not.toHaveBeenCalled();
    expect(quote).not.toHaveBeenCalled();
    expect(send).not.toHaveBeenCalled();
    await act(async () => pending.resolve([currentModel]));
  });

  it("deduplicates variants by saved key and keeps native precision separate from held-aware local usage", async () => {
    inventory.mockResolvedValue([currentModel, { ...currentModel, model_id: "deepseek-flash-nothink" },
      { ...currentModel, provider_id: "second-deepseek", display_name: "Second key" }]);
    usageSnapshot.mockResolvedValue(localUsage()); renderQuickAsk();
    await waitFor(() => expect(balanceSnapshot).toHaveBeenCalledTimes(2));
    expect(balanceSnapshot.mock.calls.map(([key]) => key).sort()).toEqual(["second-deepseek", "user-deepseek"]);
    await openModels(); const options = screen.getAllByRole("option"); expect(options).toHaveLength(3);
    expect(within(options[0]).getByText("Provider-reported balance: CNY 12.3400 · USD 1.25")).toBeTruthy();
    expect(within(options[0]).getByText(/Antiek local USD: used \$2.00 · cap \$10.00 · remaining \$8.00 · held \$3.00 · available \$5.00/)).toBeTruthy();
    expect(within(options[1]).getByText(/available \$5.00/)).toBeTruthy();
    expect(within(options[2]).getByText("No Antiek usage recorded")).toBeTruthy();
    fireEvent.click(options[1]); expect(screen.getByRole("combobox").textContent).not.toContain("CNY");
    fireEvent.change(screen.getByLabelText("Quick Ask question"), { target: { value: "Chosen variant?" } });
    fireEvent.click(screen.getByRole("button", { name: "Review estimate" }));
    await waitFor(() => expect(quote).toHaveBeenCalledWith(expect.objectContaining({ model_choice:
      { authority: "user_model", provider_id: "user-deepseek", model_id: "deepseek-flash-nothink" } })));
    expect(send).not.toHaveBeenCalled();
  });
  it.each([
    [0.0031, "0.0031"], [-0.0001, "-0.0001"], [42.50001, "42.50001"],
    [1.037e-9, "1.037e-9"], [0, "0.00"], [42, "42.00"], [42.5, "42.50"],
  ] as const)("preserves native USD %s in mounted model options", async (amount, displayed) => {
    const kimiModel = { ...currentModel, model_id: "kimi-k2.5", display_name: "My Kimi",
      price_snapshot: "kimi-fixture", price_source: "fixture" };
    inventory.mockResolvedValue([kimiModel, { ...kimiModel, model_id: "kimi-k2.5-thinking" }]);
    usageSnapshot.mockResolvedValue(localUsage());
    balanceSnapshot.mockResolvedValue({ ...nativeBalance("user-deepseek"), catalog_id: "kimi",
      native_balances: null, balance_usd: amount, native_available: amount > 0 });
    renderQuickAsk(); await openModels();
    const text = `Provider-reported balance $${displayed}${amount <= 0 ? " · insufficient for API calls" : ""}`;
    await waitFor(() => expect(screen.getAllByText(text)).toHaveLength(2));
    expect(Number(displayed)).toBe(amount);
    expect(screen.getAllByRole("option")).toHaveLength(2);
    expect(screen.getAllByText(/held \$3.00 · available \$5.00/)).toHaveLength(2);
    expect(balanceSnapshot).toHaveBeenCalledTimes(1);
    expect(quote).not.toHaveBeenCalled(); expect(send).not.toHaveBeenCalled();
  });
  it.each([0, -1.25])("labels Kimi %s as insufficient without filtering the model", async amount => {
    inventory.mockResolvedValue([{ ...currentModel, model_id: "kimi-k2.5", display_name: "My Kimi",
      price_snapshot: "kimi-fixture", price_source: "fixture" }]);
    balanceSnapshot.mockResolvedValue({ ...nativeBalance("user-deepseek"), catalog_id: "kimi",
      native_balances: null, balance_usd: amount, native_available: false });
    renderQuickAsk(); await openModels(); expect(await screen.findByText(/insufficient for API calls/)).toBeTruthy();
    expect(screen.getAllByRole("option")).toHaveLength(1); expect(quote).not.toHaveBeenCalled(); expect(send).not.toHaveBeenCalled();
  });
  it("shows uncapped/unknown local availability despite failed native reads and rejects wrong returned key IDs", async () => {
    inventory.mockResolvedValue([currentModel, { ...currentModel, provider_id: "wrong-response" }]);
    usageSnapshot.mockResolvedValue({ keys: [{ ...localUsage().keys[0], limit_cents: null,
      remaining_cents: null, available_cents: null }], count: 1 });
    balanceSnapshot.mockImplementation(async (key: string) => {
      if (key === "user-deepseek") throw new Error("offline"); return nativeBalance("another-key");
    });
    renderQuickAsk(); await openModels();
    await waitFor(() => expect(screen.getAllByText("Provider balance unavailable")).toHaveLength(2));
    expect(screen.getByText(/cap uncapped.*held \$3.00.*available unknown/)).toBeTruthy(); expect(screen.queryByText(/CNY/)).toBeNull();
    expect(screen.getAllByRole("option")).toHaveLength(2);
  });
  it("keeps eligibility on failed usage and labels the spend-history meter without fabricating zero", async () => {
    usageSnapshot.mockRejectedValue(new Error("offline"));
    balanceSnapshot.mockResolvedValue({ ...nativeBalance("user-deepseek"), kind: "spend_history", spend_usd: 2.5,
      budget_usd: null, native_balances: null });
    renderQuickAsk(); await openModels(); expect(await screen.findByText("Antiek usage unavailable")).toBeTruthy();
    expect(screen.getByText("Antiek meter: spent $2.50, uncapped (not provider credit)")).toBeTruthy();
    expect(screen.queryByText(/used \$0.00/)).toBeNull(); fireEvent.click(screen.getByRole("option"));
    fireEvent.change(screen.getByLabelText("Quick Ask question"), { target: { value: "Still eligible?" } });
    fireEvent.click(screen.getByRole("button", { name: "Review estimate" }));
    expect(await screen.findByText(/Estimated request cost/)).toBeTruthy(); expect(send).not.toHaveBeenCalled();
  });
  it.each([false, true])("refresh preserves the quote/request and terminal marker (unknown=%s)", async unknown => {
    usageSnapshot.mockResolvedValue(localUsage()); if (unknown) send.mockRejectedValue(new QuickAskError("charge_unknown"));
    renderQuickAsk(); await selectFlash();
    fireEvent.change(screen.getByLabelText("Quick Ask question"), { target: { value: "Keep this estimate?" } });
    fireEvent.click(screen.getByRole("button", { name: "Review estimate" })); await screen.findByText(/Estimated request cost/);
    const approved = quote.mock.calls[0][0]; fireEvent.click(screen.getByRole("button", { name: "Refresh usage and balance" }));
    await waitFor(() => expect(usageSnapshot).toHaveBeenCalledTimes(2)); expect(quote).toHaveBeenCalledTimes(1); expect(send).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "Send one request" }));
    await waitFor(() => expect(usageSnapshot).toHaveBeenCalledTimes(3)); expect(send).toHaveBeenCalledTimes(1);
    expect(send).toHaveBeenCalledWith(approved, quoted);
    const marker = window.sessionStorage.getItem("antiek.quick-ask.pending-send.session.v1:owner-a");
    if (unknown) expect(marker).toBe(approved.operation_id); else expect(marker).toBeNull();
  });
  it.each([false, true])("never schedules balances from a late old inventory (operator=%s)", async operator => {
    if (operator) authState.current.identity.user_id = "__operator__";
    const old = deferred<typeof currentModel[]>(); inventory.mockReturnValueOnce(old.promise);
    inventory.mockResolvedValueOnce([{ ...currentModel, provider_id: "key-b" }]);
    const view = renderQuickAsk(); changeOwner(view, operator);
    await waitFor(() => expect(balanceSnapshot).toHaveBeenCalledWith("key-b"));
    await act(async () => old.resolve([currentModel])); expect(balanceSnapshot).not.toHaveBeenCalledWith("user-deepseek");
    expect(send).not.toHaveBeenCalled(); expect(quote).not.toHaveBeenCalled();
  });
  it.each([false, true])("discards late old usage/errors and native balances on owner transition (operator=%s)", async operator => {
    if (operator) authState.current.identity.user_id = "__operator__";
    const oldUsage = deferred<SettingsUsageSnapshotResponse>(), oldBalance = deferred<SettingsBalanceResponse>();
    usageSnapshot.mockReturnValueOnce(oldUsage.promise).mockResolvedValue(localUsage("key-b"));
    balanceSnapshot.mockReturnValueOnce(oldBalance.promise).mockImplementation(async (key: string) => ({
      ...nativeBalance(key), native_balances: [{ currency: "USD", total: "99.123", granted: "0", topped_up: "99.123" }] }));
    inventory.mockResolvedValueOnce([currentModel]).mockResolvedValue([{ ...currentModel, provider_id: "key-b" }]);
    const view = renderQuickAsk(); await waitFor(() => expect(balanceSnapshot).toHaveBeenCalledTimes(1));
    changeOwner(view, operator); await waitFor(() => expect(balanceSnapshot).toHaveBeenCalledTimes(2));
    await act(async () => { oldUsage.reject(new Error("old-owner")); oldBalance.resolve(nativeBalance("user-deepseek")); });
    await openModels(); expect(await screen.findByText("Provider-reported balance: USD 99.123")).toBeTruthy();
    expect(screen.queryByText(/CNY/)).toBeNull(); expect(screen.queryByText("Antiek usage unavailable")).toBeNull();
  });
  it("discards superseded refresh success/failure without clearing newer snapshots", async () => {
    const oldUsage = deferred<SettingsUsageSnapshotResponse>(), oldBalance = deferred<SettingsBalanceResponse>();
    usageSnapshot.mockReturnValueOnce(oldUsage.promise).mockResolvedValue(localUsage());
    balanceSnapshot.mockReturnValueOnce(oldBalance.promise).mockResolvedValue({ ...nativeBalance("user-deepseek"),
      native_balances: [{ currency: "USD", total: "99.123", granted: "0", topped_up: "99.123" }] });
    renderQuickAsk(); await waitFor(() => expect(balanceSnapshot).toHaveBeenCalledTimes(1));
    fireEvent.click(screen.getByRole("button", { name: "Refresh usage and balance" }));
    await waitFor(() => expect(balanceSnapshot).toHaveBeenCalledTimes(2));
    await act(async () => { oldUsage.reject(new Error("superseded")); oldBalance.resolve(nativeBalance("user-deepseek")); });
    await openModels(); expect(await screen.findByText("Provider-reported balance: USD 99.123")).toBeTruthy();
    expect(screen.getByText(/available \$5.00/)).toBeTruthy(); expect(screen.queryByText("Antiek usage unavailable")).toBeNull();
    expect(send).not.toHaveBeenCalled(); expect(quote).not.toHaveBeenCalled();
  });
});
