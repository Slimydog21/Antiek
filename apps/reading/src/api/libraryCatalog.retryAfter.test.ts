import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { fetchLibraryCatalog, LibraryCatalogHttpError } from "./libraryCatalog";
import type { apiFetch } from "../lib/api";

const { request } = vi.hoisted(() => ({ request: vi.fn<typeof apiFetch>() }));
vi.mock("../lib/api", async (original) => ({
  ...await original<typeof import("../lib/api")>(),
  apiFetch: request,
}));

beforeEach(() => request.mockReset());
afterEach(() => vi.restoreAllMocks());

function failure(hint: string | null, status = 503) {
  return new Response("Ignored failure payload", {
    status,
    headers: hint === null ? undefined : { "Retry-After": hint },
  });
}

// Failure-only protocol controls; no successful catalogue or book fixture.
describe("Library Retry-After failure metadata", () => {
  it.each([
    { hint: "1", delayMs: 1000 }, { hint: "2", delayMs: 2000 },
    { hint: "30", delayMs: 30000 }, { hint: " \t2\t ", delayMs: 2000 },
  ])("retains the admitted hint $hint as a bounded wait", async ({ hint, delayMs }) => {
    request.mockResolvedValue(failure(hint));
    await expect(fetchLibraryCatalog()).rejects.toMatchObject({
      status: 503, retryAfter: { kind: "delay", delayMs },
    });
    expect(request).toHaveBeenCalledTimes(1);
  });

  it("keeps absence distinct from a malformed present hint", async () => {
    request.mockResolvedValue(failure(null));
    await expect(fetchLibraryCatalog()).rejects.toMatchObject({
      status: 503, retryAfter: { kind: "absent" },
    });
    expect(new LibraryCatalogHttpError(503)).toMatchObject({
      retryAfter: { kind: "absent" },
    });
  });

  it.each([
    "", "0", "01", "+2", "-2", "2.0", "2e0", "2 seconds", "2, 3",
    "31", "999999", "Wed, 21 Oct 2015 07:28:00 GMT", "\u00a02", "2".repeat(65),
  ])("refuses present unsupported hint %j", async (hint) => {
    request.mockResolvedValue(failure(hint));
    await expect(fetchLibraryCatalog()).rejects.toMatchObject({
      status: 503, retryAfter: { kind: "invalid" },
    });
  });

  it("retains status without reading an error response body", async () => {
    const response = failure("2", 403);
    const readJson = vi.spyOn(response, "json");
    const readText = vi.spyOn(response, "text");
    request.mockResolvedValue(response);
    await expect(fetchLibraryCatalog()).rejects.toMatchObject({
      status: 403, retryAfter: { kind: "delay", delayMs: 2000 },
    });
    expect(readJson).not.toHaveBeenCalled();
    expect(readText).not.toHaveBeenCalled();
    expect(response.bodyUsed).toBe(false);
  });
});
