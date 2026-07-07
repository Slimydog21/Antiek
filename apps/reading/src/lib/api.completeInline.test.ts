import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ApiError, completeInline } from "./api";

const fetchMock = vi.fn();

beforeEach(() => {
  fetchMock.mockReset();
  vi.stubGlobal("fetch", fetchMock);
});
afterEach(() => {
  vi.unstubAllGlobals();
});

describe("completeInline", () => {
  it("POSTs to /complete with the request body and returns { text }", async () => {
    fetchMock.mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({ text: " continuation" }),
    });

    const res = await completeInline({
      prefix: "Hello",
      document_context: "doc",
      max_tokens: 64,
    });

    expect(res).toEqual({ text: " continuation" });
    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [url, init] = fetchMock.mock.calls[0];
    expect(String(url)).toContain("/complete");
    expect(init?.method).toBe("POST");
    expect(JSON.parse(init?.body as string)).toEqual({
      prefix: "Hello",
      document_context: "doc",
      max_tokens: 64,
    });
  });

  it("throws ApiError when the response is not ok", async () => {
    fetchMock.mockResolvedValue({
      ok: false,
      status: 422,
      text: async () => "validation failed",
    });

    await expect(completeInline({ prefix: "x" })).rejects.toBeInstanceOf(ApiError);
    await expect(completeInline({ prefix: "x" })).rejects.toMatchObject({
      status: 422,
    });
  });
});