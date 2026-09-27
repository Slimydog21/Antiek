/**
 * FFX SPR-04 follow-up (A-16 client contract): GET reading-state returns
 * null ("no position recorded yet") only for the backend's typed absence,
 * a 404 whose body is exactly {"detail": "reading_state_not_found"}
 * (interfaces/research/api/reading_state_routes.py:118), or a 204 so a future
 * backend switch cannot strand the bus. Any other 404 (a wrong document id,
 * a missing route) throws as before, so the caller sees a real failure.
 */
import { beforeEach, describe, expect, it, vi } from "vitest";

const { apiFetchMock } = vi.hoisted(() => ({ apiFetchMock: vi.fn() }));

vi.mock("../lib/api", async (orig) => ({
  ...(await orig<typeof import("../lib/api")>()),
  apiFetch: (input: unknown, init?: unknown) => apiFetchMock(input, init),
}));

import { ApiError } from "../lib/api";
import { getReadingState } from "./readingState";

function json(body: unknown, status: number): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

beforeEach(() => apiFetchMock.mockReset());

describe("getReadingState absence contract", () => {
  it("a 404 with detail reading_state_not_found is null", async () => {
    apiFetchMock.mockResolvedValue(json({ detail: "reading_state_not_found" }, 404));
    await expect(getReadingState("doc-1")).resolves.toBeNull();
  });

  it("a 204 is null", async () => {
    apiFetchMock.mockResolvedValue(new Response(null, { status: 204 }));
    await expect(getReadingState("doc-1")).resolves.toBeNull();
  });

  it.each([
    ["another detail", json({ detail: "Not Found" }, 404)],
    ["an empty object", json({}, 404)],
    ["a non-JSON body", new Response("<html>not found</html>", { status: 404 })],
  ])("a 404 with %s throws an ApiError with status 404", async (_name, resp) => {
    apiFetchMock.mockResolvedValue(resp);
    const err = await getReadingState("doc-1").then(
      () => null,
      (e: unknown) => e,
    );
    expect(err).toBeInstanceOf(ApiError);
    expect((err as ApiError).status).toBe(404);
  });
});
