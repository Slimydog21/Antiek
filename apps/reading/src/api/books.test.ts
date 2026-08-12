import { beforeEach, describe, expect, it, vi } from "vitest";

import {
  askBook,
  askBookDeep,
  BookModelOperationNotFoundError,
  cancelBookModelOperation,
  getBookModelOperation,
  getDeepBookOperation,
  getPrimeOperation,
  reconcilePrimeOperation,
  cancelPrimeOperation,
  reconcileBookModelOperation,
} from "./books";

const apiFetchMock = vi.hoisted(() => vi.fn());

vi.mock("../lib/api", async (orig) => {
  const actual = await orig<typeof import("../lib/api")>();
  return { ...actual, API_BASE: "", apiFetch: apiFetchMock };
});

const response = {
  answer_id: null,
  capture_status: "unavailable",
  answer: "answer",
  citations: [],
  grounded: true,
  context_chunk_count: 1,
};

beforeEach(() => {
  apiFetchMock.mockReset();
  apiFetchMock.mockResolvedValue({ ok: true, status: 200, json: async () => response });
});

describe("askBook model choice", () => {
  it("preserves the legacy deep-tier request when no model is chosen", async () => {
    await askBook("doc", "question");
    const body = JSON.parse(apiFetchMock.mock.calls[0][1].body as string);
    expect(body).toEqual({ question: "question", history: [], research_tier: "deep" });
  });

  it("serializes only the authority and model reference for a chosen owner model", async () => {
    await askBook("doc", "question", {
      modelChoice: {
        authority: "user_model",
        provider_id: "user-provider",
        model_id: "model-a",
      },
      operationId: "operation-a",
    });
    const body = JSON.parse(apiFetchMock.mock.calls[0][1].body as string);
    expect(body.model_choice).toEqual({
      authority: "user_model",
      provider_id: "user-provider",
      model_id: "model-a",
    });
    expect(Object.keys(body.model_choice)).toEqual(["authority", "provider_id", "model_id"]);
    expect(body.operation_id).toBe("operation-a");
  });

  it("turns a stale selected-model rejection into an actionable value-free error", async () => {
    apiFetchMock.mockResolvedValue({ ok: false, status: 409 });
    await expect(
      askBook("doc", "question", {
        modelChoice: {
          authority: "user_model",
          provider_id: "user-provider",
          model_id: "model-a",
        },
        operationId: "operation-a",
      }),
    ).rejects.toThrow("That model is no longer available. Choose another model or use Default.");
  });
});

describe("askBookDeep", () => {
  it("keeps ordinary Ask unchanged and opts into genuine deep mode explicitly", async () => {
    await askBookDeep("doc", "question", {
      history: [{ question: "q", answer: "a" }], operationId: "deep-1",
      modelChoice: { authority: "user_model", provider_id: "canonical", model_id: "c-1" },
    });
    const body = JSON.parse(apiFetchMock.mock.calls[0][1].body as string);
    expect(body).toEqual({
      question: "question",
      history: [{ question: "q", answer: "a" }],
      research_tier: "deep",
      mode: "deep",
      operation_id: "deep-1",
      model_choice: { authority: "user_model", provider_id: "canonical", model_id: "c-1" },
    });
    expect(body).not.toHaveProperty("prime");
  });

  it("sends only explicit capped Prime authority with stable operation identity", async () => {
    await askBookDeep("doc", "question", {
      operationId: "deep-2",
      modelChoice: { authority: "user_model", provider_id: "canonical", model_id: "c-1" },
      prime: {
      operationId: "prime-stable-1",
      modelChoice: { authority: "user_model", provider_id: "prime", model_id: "p-1" },
      maxCostMicroUsd: 5_000_000,
      },
    });
    const body = JSON.parse(apiFetchMock.mock.calls[0][1].body as string);
    expect(body.prime).toEqual({
      enabled: true,
      operation_id: "prime-stable-1",
      model_choice: { authority: "user_model", provider_id: "prime", model_id: "p-1" },
      max_cost_micro_usd: 5_000_000,
    });
    expect(JSON.stringify(body)).not.toMatch(/secret|prompt|authority_digest/i);
  });
});

describe("book model operation reconciliation", () => {
  it("checks, reconciles, and cancels by the same encoded operation id without a body", async () => {
    apiFetchMock.mockResolvedValue({ ok: true, json: async () => ({ state: "prepared" }) });
    await getBookModelOperation("operation / one");
    await reconcileBookModelOperation("operation / one");
    await cancelBookModelOperation("operation / one");

    expect(apiFetchMock.mock.calls.map((call) => call[0])).toEqual([
      "/books/model-operations/operation%20%2F%20one",
      "/books/model-operations/operation%20%2F%20one/reconcile",
      "/books/model-operations/operation%20%2F%20one/cancel",
    ]);
    expect(apiFetchMock.mock.calls[0][1]).toBeUndefined();
    expect(apiFetchMock.mock.calls[1][1]).toEqual({ method: "POST" });
    expect(apiFetchMock.mock.calls[2][1]).toEqual({ method: "POST" });
  });

  it("preserves operation-status 404 as typed not_found", async () => {
    apiFetchMock.mockResolvedValue({ ok: false, status: 404 });
    await expect(getBookModelOperation("missing-operation")).rejects.toBeInstanceOf(
      BookModelOperationNotFoundError,
    );
  });
});

describe("Prime operation recovery", () => {
  it("surfaces authentication loss without treating it as an abandonable missing operation", async () => {
    apiFetchMock.mockResolvedValue({ ok: false, status: 401 });
    await expect(getPrimeOperation("held")).rejects.toThrow("Sign in again");
    await expect(getDeepBookOperation("parent")).rejects.toThrow("Sign in again");
  });

  it("checks, reconciles, and cancels the same encoded paid operation", async () => {
    apiFetchMock.mockResolvedValue({ ok: true, status: 200, json: async () => ({ state: "unknown" }) });
    await getPrimeOperation("prime / one");
    await reconcilePrimeOperation("prime / one");
    await cancelPrimeOperation("prime / one");
    expect(apiFetchMock.mock.calls.map((call) => call[0])).toEqual([
      "/books/prime-operations/prime%20%2F%20one",
      "/books/prime-operations/prime%20%2F%20one/reconcile",
      "/books/prime-operations/prime%20%2F%20one/cancel",
    ]);
  });

  it("follows the real status → owner refresh → lease checkpoint → exact resume flow", async () => {
    const held = { state: "unknown", operation_id: "prime-1" };
    const checkpoint = {
      operation_id: "deep-parent-1", state: "canonical_complete", checkpoint_phase: "canonical_complete",
      lease_expires_at_ms: 100, resumable: true,
      created_at_ms: 1, updated_at_ms: 2, response: null,
    };
    apiFetchMock
      .mockResolvedValueOnce({ ok: true, status: 200, json: async () => held })
      .mockResolvedValueOnce({ ok: true, status: 200, json: async () => held })
      .mockResolvedValueOnce({ ok: true, status: 200, json: async () => checkpoint })
      .mockResolvedValueOnce({ ok: true, status: 200, json: async () => response });

    await getPrimeOperation("prime-1");
    await reconcilePrimeOperation("prime-1"); // owner refresh is status-only
    await getDeepBookOperation("deep-parent-1");
    const exact = {
      history: [{ question: "before", answer: "prior" }],
      operationId: "deep-parent-1",
      modelChoice: { authority: "user_model" as const, provider_id: "canonical", model_id: "c-1" },
      prime: {
        operationId: "prime-1",
        modelChoice: { authority: "user_model" as const, provider_id: "prime", model_id: "p-1" },
        maxCostMicroUsd: 5_000_000,
      },
    };
    await askBookDeep("doc", "question", exact);

    expect(apiFetchMock.mock.calls.map((call) => call[0])).toEqual([
      "/books/prime-operations/prime-1",
      "/books/prime-operations/prime-1/reconcile",
      "/books/deep-operations/deep-parent-1",
      "/books/doc/ask",
    ]);
    expect(JSON.parse(apiFetchMock.mock.calls[3][1].body as string).prime.operation_id).toBe("prime-1");
    // There is exactly one resume POST and it reuses the original paid identity;
    // the server journal, not a fresh provider dispatch, owns continuation.
    expect(apiFetchMock.mock.calls.filter((call) => call[0] === "/books/doc/ask")).toHaveLength(1);
  });
});
