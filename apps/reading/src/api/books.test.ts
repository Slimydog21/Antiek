import { beforeEach, describe, expect, it, vi } from "vitest";

import {
  askBook,
  BookModelOperationNotFoundError,
  cancelBookModelOperation,
  getBookModelOperation,
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
