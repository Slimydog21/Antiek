import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

const { inventory, quote, send } = vi.hoisted(() => ({
  inventory: vi.fn(), quote: vi.fn(), send: vi.fn(),
}));

vi.mock("../../api/quickAsk", async (original) => {
  const actual = await original<typeof import("../../api/quickAsk")>();
  return { ...actual, fetchQuickAskModels: inventory, quoteQuickAsk: quote, sendQuickAsk: send };
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

function renderQuickAsk() {
  render(<MemoryRouter><QuickAsk /></MemoryRouter>);
}

async function selectFlash() {
  const selector = await screen.findByRole("combobox", { name: "Quick Ask model" });
  fireEvent.click(selector.querySelector("button")!);
  fireEvent.click(await screen.findByRole("option", { name: /My DeepSeek · deepseek-flash/ }));
}

beforeEach(() => {
  inventory.mockReset(); quote.mockReset(); send.mockReset();
  inventory.mockResolvedValue([currentModel]);
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
