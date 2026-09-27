import { beforeEach, describe, expect, it, vi } from "vitest";

const { apiFetch } = vi.hoisted(() => ({ apiFetch: vi.fn() }));
vi.mock("../lib/api", () => ({ apiFetch }));

import { fetchQuickAskModels, QuickAskError, sendQuickAsk } from "./quickAsk";

const request = {
  question: "What remains uncertain?",
  operation_id: "9d4b35fb-a34a-4a4e-9977-9f822ce0bfd3",
  model_choice: {
    authority: "user_model" as const,
    provider_id: "owner-deepseek",
    model_id: "deepseek-v4-flash",
  },
  quote_digest: "a".repeat(64),
};

function json(value: unknown, status = 200): Response {
  return new Response(JSON.stringify(value), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

beforeEach(() => apiFetch.mockReset());

describe("Quick Ask browser wire contract", () => {
  it("uses the server's owner-scoped eligible variants without a browser model allowlist", async () => {
    apiFetch.mockResolvedValue(json({
      models: [{
        provider_id: "owner-deepseek", model_id: "deepseek-v4-flash",
        display_name: "My DeepSeek", price_snapshot: "deepseek-2026-09-27",
        price_source: "https://api-docs.deepseek.com/pricing",
      }],
      count: 1,
    }));
    expect(await fetchQuickAskModels()).toMatchObject([
      { provider_id: "owner-deepseek", model_id: "deepseek-v4-flash" },
    ]);
    expect(apiFetch).toHaveBeenCalledOnce();
    expect(apiFetch).toHaveBeenCalledWith("/research/quick-ask/models");
  });

  it("preserves an answer with unknown charge and its incomplete flag", async () => {
    apiFetch.mockResolvedValue(json({
      answer: "Partial answer", operation_id: request.operation_id,
      provider_id: "owner-deepseek", model_id: "deepseek-v4-flash",
      estimated_cost_usd: null, usage_basis: "charge_unknown",
      input_tokens: null, output_tokens: null, replayed: false,
      incomplete: true, reported_usage_estimate_exceeds_quote: null,
    }));
    const result = await sendQuickAsk(request);
    expect(result.answer).toBe("Partial answer");
    expect(result.usage_basis).toBe("charge_unknown");
    expect(result.incomplete).toBe(true);
    expect(apiFetch).toHaveBeenCalledOnce();
    expect(apiFetch.mock.calls[0][0]).toBe("/research/quick-ask");
  });

  it("marks an ambiguous sent response unknown and never retries", async () => {
    apiFetch.mockResolvedValue(json({ detail: "charge_unknown" }, 409));
    let caught: unknown;
    try { await sendQuickAsk(request); } catch (error) { caught = error; }
    expect(caught).toBeInstanceOf(QuickAskError);
    expect((caught as QuickAskError).reason).toBe("charge_unknown");
    expect(apiFetch).toHaveBeenCalledOnce();
  });

  it("does not treat a malformed paid success as a verified receipt", async () => {
    apiFetch.mockResolvedValue(json({ answer: "missing operation and usage" }));
    let caught: unknown;
    try { await sendQuickAsk(request); } catch (error) { caught = error; }
    expect(caught).toBeInstanceOf(QuickAskError);
    expect((caught as QuickAskError).reason).toBe("charge_unknown");
    expect(apiFetch).toHaveBeenCalledOnce();
  });
});
