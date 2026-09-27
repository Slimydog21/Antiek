/**
 * companions.test.ts — the companion client against lane B's pinned wire
 * shape (GET never writes; POST /refresh rebuilds). The validator accepts each
 * state, maps a pre-hotfix payload (no `state`) to built, and the refresh
 * failure exposes only `hasLastBuild` — never a status or server code to render.
 */
import { beforeEach, describe, expect, it, vi } from "vitest";

const apiFetchMock = vi.hoisted(() => vi.fn());
vi.mock("../lib/api", async () => {
  const actual = await vi.importActual<typeof import("../lib/api")>("../lib/api");
  return { ...actual, API_BASE: "", apiFetch: apiFetchMock };
});

import { ApiError } from "../lib/api";
import {
  CompanionRebuildFailedError,
  getDocumentCompanion,
  isCompanionNotFound,
  refreshDocumentCompanion,
} from "./companions";

function legacyPayload() {
  return {
    document_id: "doc-1",
    exists: true,
    title: "A Servable Book",
    servable: true,
    rebuilt_at: "2026-09-25T12:00:00Z",
    claims: [{ evidence_id: "ev-1", kind: "insight", node_ref: "node:n-1", text: "a finding" }],
    anchors: [],
    processes: [],
  };
}

function json(body: unknown, status = 200): Response {
  return new Response(typeof body === "string" ? body : JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

describe("getDocumentCompanion — the state union", () => {
  beforeEach(() => apiFetchMock.mockReset());

  it("reads the structured payload with a GET (no method override)", async () => {
    apiFetchMock.mockResolvedValue(json({ ...legacyPayload(), state: "built" }));
    await getDocumentCompanion("doc 1");
    const [url, init] = apiFetchMock.mock.calls[0] as [string, RequestInit | undefined];
    expect(url).toBe("/documents/doc%201/companion?format=json");
    expect(init?.method ?? "GET").toBe("GET");
  });

  it("built: today's payload plus state built", async () => {
    apiFetchMock.mockResolvedValue(json({ ...legacyPayload(), state: "built" }));
    const res = await getDocumentCompanion("doc-1");
    expect(res.state).toBe("built");
    if (res.state !== "built") throw new Error("unreachable");
    expect(res.claims[0].text).toBe("a finding");
    expect(res.rebuilt_at).toBe("2026-09-25T12:00:00Z");
  });

  it("a legacy payload with NO state (pre-hotfix server) is treated as built", async () => {
    apiFetchMock.mockResolvedValue(json(legacyPayload()));
    const res = await getDocumentCompanion("doc-1");
    expect(res.state).toBe("built");
    if (res.state !== "built") throw new Error("unreachable");
    expect(res.claims).toHaveLength(1);
  });

  it("not_built: the bare state", async () => {
    apiFetchMock.mockResolvedValue(json({ document_id: "doc-1", state: "not_built" }));
    const res = await getDocumentCompanion("doc-1");
    expect(res).toEqual({ document_id: "doc-1", state: "not_built" });
  });

  it.each(["taken_down", "not_servable"])("withheld (%s): the reason, no content", async (reason) => {
    apiFetchMock.mockResolvedValue(json({ document_id: "doc-1", state: "withheld", reason }));
    const res = await getDocumentCompanion("doc-1");
    expect(res).toEqual({ document_id: "doc-1", state: "withheld", reason });
  });

  it("a malformed legacy payload is rejected, never rendered", async () => {
    apiFetchMock.mockResolvedValue(json({ document_id: "doc-1", claims: "nope" }));
    await expect(getDocumentCompanion("doc-1")).rejects.toBeInstanceOf(ApiError);
  });

  it("a built payload missing its rebuilt_at stamp is rejected", async () => {
    const { rebuilt_at: _omit, ...rest } = legacyPayload();
    apiFetchMock.mockResolvedValue(json({ ...rest, state: "built" }));
    await expect(getDocumentCompanion("doc-1")).rejects.toBeInstanceOf(ApiError);
  });

  it("an unknown state is rejected", async () => {
    apiFetchMock.mockResolvedValue(json({ document_id: "doc-1", state: "half_built" }));
    await expect(getDocumentCompanion("doc-1")).rejects.toBeInstanceOf(ApiError);
  });

  it("a 404 (foreign or missing) is recognisable without reading its status at the call site", async () => {
    apiFetchMock.mockResolvedValue(json({ detail: "book_not_found" }, 404));
    const err = await getDocumentCompanion("doc-1").catch((e: unknown) => e);
    expect(isCompanionNotFound(err)).toBe(true);
    expect(isCompanionNotFound(new ApiError("x", 500, ""))).toBe(false);
    expect(isCompanionNotFound(new Error("network"))).toBe(false);
  });
});

describe("refreshDocumentCompanion — the explicit rebuild", () => {
  beforeEach(() => apiFetchMock.mockReset());

  it("POSTs /documents/{id}/companion/refresh with the session helper and returns the built payload", async () => {
    apiFetchMock.mockResolvedValue(json({ ...legacyPayload(), state: "built" }));
    const res = await refreshDocumentCompanion("doc-1");
    const [url, init] = apiFetchMock.mock.calls[0] as [string, RequestInit | undefined];
    expect(url.split("?")[0]).toBe("/documents/doc-1/companion/refresh");
    expect(init?.method).toBe("POST");
    expect(res.state).toBe("built");
  });

  it.each([
    [true, true],
    [false, false],
  ])("503 has_last_build=%s → a typed error exposing hasLastBuild=%s", async (flag, expected) => {
    apiFetchMock.mockResolvedValue(
      json(
        { detail: "companion_rebuild_failed", error_type: "DuckDBLockTimeout", has_last_build: flag },
        503,
      ),
    );
    const err = await refreshDocumentCompanion("doc-1").catch((e: unknown) => e);
    expect(err).toBeInstanceOf(CompanionRebuildFailedError);
    expect((err as CompanionRebuildFailedError).hasLastBuild).toBe(expected);
  });

  it("503 with an unparsable body defaults hasLastBuild to false", async () => {
    apiFetchMock.mockResolvedValue(json("<html>bad gateway</html>", 503));
    const err = await refreshDocumentCompanion("doc-1").catch((e: unknown) => e);
    expect(err).toBeInstanceOf(CompanionRebuildFailedError);
    expect((err as CompanionRebuildFailedError).hasLastBuild).toBe(false);
  });

  it("the typed error carries no server code or error_type in its message", async () => {
    apiFetchMock.mockResolvedValue(
      json(
        { detail: "companion_rebuild_failed", error_type: "DuckDBLockTimeout", has_last_build: true },
        503,
      ),
    );
    const err = (await refreshDocumentCompanion("doc-1").catch((e: unknown) => e)) as Error;
    expect(err.message).not.toContain("DuckDBLockTimeout");
    expect(err.message).not.toContain("companion_rebuild_failed");
  });

  it("a 404 on refresh is the same not-found as GET", async () => {
    apiFetchMock.mockResolvedValue(json({ detail: "book_not_found" }, 404));
    const err = await refreshDocumentCompanion("doc-1").catch((e: unknown) => e);
    expect(isCompanionNotFound(err)).toBe(true);
    expect(err).not.toBeInstanceOf(CompanionRebuildFailedError);
  });
});
