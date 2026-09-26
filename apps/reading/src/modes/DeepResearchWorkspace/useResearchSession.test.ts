/**
 * FFX SPR-04 M3 (A-14): a 404 stops the poll loop; a transient failure keeps
 * polling with backoff and carries a humanised title, never the raw line.
 * Fake timers throughout: the request counts below are read from the mock,
 * not inferred from a loop that "seemed to stop".
 */
import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ApiError } from "../../lib/api";

const { getSessionMock } = vi.hoisted(() => ({ getSessionMock: vi.fn() }));

vi.mock("../../api/research", async (orig) => ({
  ...(await orig<typeof import("../../api/research")>()),
  getSession: getSessionMock,
}));

import { useResearchSession } from "./useResearchSession";

const INTERVAL = 1000;

/** Let the pending getSession promise settle and React flush its update. */
async function settle() {
  await act(async () => {
    await Promise.resolve();
    await Promise.resolve();
  });
}

async function advance(ms: number) {
  await act(async () => {
    await vi.advanceTimersByTimeAsync(ms);
  });
}

beforeEach(() => {
  vi.useFakeTimers();
  getSessionMock.mockReset();
});

afterEach(() => {
  vi.useRealTimers();
});

describe("useResearchSession — failure handling (A-14)", () => {
  it("a 404 makes exactly one request, then stops and marks the session missing", async () => {
    getSessionMock.mockRejectedValue(
      new ApiError("GET /research/sessions/does-not-exist failed: HTTP 404", 404, '{"detail":"not found"}'),
    );
    const { result } = renderHook(() => useResearchSession("does-not-exist", { intervalMs: INTERVAL }));
    await settle();
    await advance(60_000);

    expect(getSessionMock).toHaveBeenCalledTimes(1);
    expect(result.current.missing).toBe(true);
    expect(result.current.loading).toBe(false);
    expect(result.current.error ?? "").not.toMatch(/HTTP|404|GET/);
  });

  it("a 503 keeps polling with backoff and carries the humanised title", async () => {
    getSessionMock.mockRejectedValue(
      new ApiError("GET /research/sessions/s failed: HTTP 503", 503, "upstream down"),
    );
    const { result } = renderHook(() => useResearchSession("s", { intervalMs: INTERVAL }));
    await settle();
    expect(getSessionMock).toHaveBeenCalledTimes(1);
    expect(result.current.error).toBe("Couldn't reach this research session.");
    expect(result.current.missing).toBe(false);

    // Backoff: 1s, then 2s, then 4s after consecutive failures.
    await advance(INTERVAL - 1);
    expect(getSessionMock).toHaveBeenCalledTimes(1);
    await advance(1);
    expect(getSessionMock).toHaveBeenCalledTimes(2);
    await advance(2 * INTERVAL - 1);
    expect(getSessionMock).toHaveBeenCalledTimes(2);
    await advance(1);
    expect(getSessionMock).toHaveBeenCalledTimes(3);
    await advance(4 * INTERVAL);
    expect(getSessionMock).toHaveBeenCalledTimes(4);
    expect(result.current.error).toBe("Couldn't reach this research session.");
  });

  it("recovers to the normal interval after a transient failure clears", async () => {
    getSessionMock
      .mockRejectedValueOnce(new ApiError("x", 503, ""))
      .mockResolvedValue({
        session_id: "s",
        live: true,
        researches: [{ investigation_id: "inv-0", sub_question: "Q", state: "running" }],
        cost: null,
      });
    const { result } = renderHook(() => useResearchSession("s", { intervalMs: INTERVAL }));
    await settle();
    await advance(INTERVAL);
    expect(getSessionMock).toHaveBeenCalledTimes(2);
    expect(result.current.error).toBeNull();
    expect(result.current.researches).toHaveLength(1);
    await advance(INTERVAL);
    expect(getSessionMock).toHaveBeenCalledTimes(3);
  });
});
