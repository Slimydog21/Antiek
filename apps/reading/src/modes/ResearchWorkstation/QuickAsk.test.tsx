import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

const { inventory, recent, quote, send, authState } = vi.hoisted(() => ({
  inventory: vi.fn(), recent: vi.fn(), quote: vi.fn(), send: vi.fn(),
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
    expect(send.mock.calls[0][0]).toMatchObject({
      question: "What is the counterargument?",
      model_choice: { authority: "user_model", provider_id: "user-deepseek", model_id: "deepseek-flash" },
      quote_digest: quoted.quote_digest,
    });
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
