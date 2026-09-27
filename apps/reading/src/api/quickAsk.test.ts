import { beforeEach, describe, expect, it, vi } from "vitest";

const { apiFetch } = vi.hoisted(() => ({ apiFetch: vi.fn() }));
vi.mock("../lib/api", () => ({ apiFetch }));

import { fetchQuickAskModels, fetchQuickAskRecent, QuickAskError, sendQuickAsk } from "./quickAsk";

const request = {
  question: "What remains uncertain?",
  operation_id: "9d4b35fb-a34a-4a4e-9977-9f822ce0bfd3",
  model_choice: {
    authority: "user_model" as const,
    provider_id: "owner-deepseek",
    model_id: "deepseek-flash",
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
  it("reads an owner receipt without a model send and preserves unknown-charge truth", async () => {
    apiFetch.mockResolvedValue(json({ operations: [
      {
        operation_id: request.operation_id, created_at: "2026-09-27T08:59:00+00:00",
        status: "answered",
        result: {
          answer: "Stored answer", operation_id: request.operation_id,
          provider_id: "owner-deepseek", model_id: "deepseek-flash",
          estimated_cost_usd: null, usage_basis: "charge_unknown",
          input_tokens: null, output_tokens: null, replayed: true,
          incomplete: true, reported_usage_estimate_exceeds_quote: null,
        },
      },
      {
        operation_id: "45670f5f-4d04-4d6c-84f3-68d9c56dcb25",
        created_at: "2026-09-27T08:58:00+00:00",
        status: "charge_unknown", result: null,
      },
    ] }));
    const recent = await fetchQuickAskRecent();
    expect(recent[0]).toMatchObject({
      status: "answered", result: { answer: "Stored answer", usage_basis: "charge_unknown", incomplete: true },
    });
    expect(recent[1]).toMatchObject({ status: "charge_unknown", result: null });
    expect(apiFetch).toHaveBeenCalledOnce();
    expect(apiFetch).toHaveBeenCalledWith("/research/quick-ask/recent", { cache: "no-store" });
  });

  it("rejects a misbound stored answer rather than showing it under another operation", async () => {
    apiFetch.mockResolvedValue(json({ operations: [{
      operation_id: request.operation_id, created_at: "2026-09-27T08:59:00+00:00",
      status: "answered",
      result: {
        answer: "Wrong row", operation_id: "45670f5f-4d04-4d6c-84f3-68d9c56dcb25",
        provider_id: "owner-deepseek", model_id: "deepseek-flash",
        estimated_cost_usd: 0.0038, usage_basis: "prior_receipt",
        input_tokens: null, output_tokens: null, replayed: true,
        incomplete: false, reported_usage_estimate_exceeds_quote: false,
      },
    }] }));
    await expect(fetchQuickAskRecent()).rejects.toMatchObject({ reason: "quick_ask_unavailable" });
    expect(apiFetch).toHaveBeenCalledOnce();
  });

  it("rejects duplicate operation IDs instead of rendering ambiguous history rows", async () => {
    const item = {
      operation_id: request.operation_id, created_at: "2026-09-27T08:59:00+00:00",
      status: "charge_unknown", result: null,
    };
    apiFetch.mockResolvedValue(json({ operations: [item, item] }));
    await expect(fetchQuickAskRecent()).rejects.toMatchObject({ reason: "quick_ask_unavailable" });
    expect(apiFetch).toHaveBeenCalledOnce();
  });

  it("uses the server's owner-scoped eligible variants without a browser model allowlist", async () => {
    apiFetch.mockResolvedValue(json({
      models: [{
        provider_id: "owner-deepseek", model_id: "deepseek-flash",
        display_name: "My DeepSeek", price_snapshot: "deepseek-2026-09-27",
        price_source: "https://api-docs.deepseek.com/pricing",
      }],
      count: 1,
    }));
    expect(await fetchQuickAskModels()).toMatchObject([
      { provider_id: "owner-deepseek", model_id: "deepseek-flash" },
    ]);
    expect(apiFetch).toHaveBeenCalledOnce();
    expect(apiFetch).toHaveBeenCalledWith("/research/quick-ask/models");
  });

  it("preserves an answer with unknown charge and its incomplete flag", async () => {
    apiFetch.mockResolvedValue(json({
      answer: "Partial answer", operation_id: request.operation_id,
      provider_id: "owner-deepseek", model_id: "deepseek-flash",
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

  it("rejects a paid answer attributed to another operation without resending", async () => {
    apiFetch.mockResolvedValue(json({
      answer: "Wrong operation", operation_id: "45670f5f-4d04-4d6c-84f3-68d9c56dcb25",
      provider_id: "owner-deepseek", model_id: "deepseek-flash",
      estimated_cost_usd: 0.0004,
      usage_basis: "provider_reported_tokens_priced_locally",
      input_tokens: 12, output_tokens: 25, replayed: false, incomplete: false,
      reported_usage_estimate_exceeds_quote: false,
    }));
    let caught: unknown;
    try { await sendQuickAsk(request); } catch (error) { caught = error; }
    expect(caught).toBeInstanceOf(QuickAskError);
    expect((caught as QuickAskError).reason).toBe("charge_unknown");
    expect(apiFetch).toHaveBeenCalledOnce();
  });
});
