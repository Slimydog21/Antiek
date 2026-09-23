/**
 * useInvestigation.test.ts — a failed trajectory fetch is an ERROR, never a
 * definite "not_found" (audit wave4 C15).
 *
 * GET /trajectory/{id} answers an unknown id with 200 + zero events; it never
 * 404s. So the seed fetch's catch is reached only by outages (5xx, 401/403, a
 * dropped connection). Mapping those to "not_found" told the operator their
 * research does not exist. Pinned here:
 *   - 5xx / network failure → status "error" with a classified loadError and a
 *     working retry(), never "not_found";
 *   - a 200 with zero events, or an explicit 404, is still "not_found";
 *   - retry() after an outage re-fetches and recovers the real state.
 *
 * The api boundary (getTrajectory / getInvestigationStatus) and the live WS
 * hook are stubbed; the status derivation under test is the real hook.
 */
import { afterEach, describe, expect, it, vi } from "vitest";
import { act, renderHook, waitFor } from "@testing-library/react";

const { getTrajectoryMock, getInvestigationStatusMock } = vi.hoisted(() => ({
  getTrajectoryMock: vi.fn(),
  getInvestigationStatusMock: vi.fn(),
}));

vi.mock("../lib/api", async (orig) => {
  const actual = await orig<typeof import("../lib/api")>();
  return {
    ...actual,
    getTrajectory: getTrajectoryMock,
    getInvestigationStatus: getInvestigationStatusMock,
  };
});

vi.mock("./useEventStream", () => ({
  useEventStream: () => ({ events: [], status: "open", reconnects: 0 }),
}));

import { ApiError } from "../lib/api";
import { useInvestigation } from "./useInvestigation";

const START = {
  event_id: "e1",
  action_type: "investigation.start_requested",
  emitted_at: "2026-09-01T00:00:00Z",
  payload: { question: "Real Q?" },
};

afterEach(() => {
  getTrajectoryMock.mockReset();
  getInvestigationStatusMock.mockReset();
});

async function settled(id: string) {
  const hook = renderHook(() => useInvestigation(id));
  await waitFor(() => expect(hook.result.current.status).not.toBe("loading"));
  return hook;
}

describe("useInvestigation — seed fetch failure is an error, not not_found", () => {
  it.each([
    ["HTTP 503", () => new ApiError("GET /trajectory failed: HTTP 503", 503, "")],
    ["HTTP 500", () => new ApiError("GET /trajectory failed: HTTP 500", 500, "")],
    ["HTTP 401", () => new ApiError("GET /trajectory failed: HTTP 401", 401, "")],
    ["network", () => new TypeError("Failed to fetch")],
  ])("%s → status 'error' with a retry, never 'not_found'", async (_label, make) => {
    getTrajectoryMock.mockRejectedValue(make());
    getInvestigationStatusMock.mockResolvedValue(null);

    const { result } = await settled("inv-123");

    expect(result.current.status).toBe("error");
    expect(result.current.loadError).not.toBeNull();
    expect(typeof result.current.retry).toBe("function");
  });

  it("classifies a dropped connection as backend_unreachable", async () => {
    getTrajectoryMock.mockRejectedValue(new TypeError("Failed to fetch"));
    getInvestigationStatusMock.mockResolvedValue(null);
    const { result } = await settled("inv-123");
    expect(result.current.loadError?.code).toBe("backend_unreachable");
  });

  it("CONTROL: a 200 with zero events is a genuine not_found", async () => {
    getTrajectoryMock.mockResolvedValue({ investigation_id: "x", count: 0, events: [] });
    getInvestigationStatusMock.mockResolvedValue(null);
    const { result } = await settled("inv-unknown");
    expect(result.current.status).toBe("not_found");
    expect(result.current.loadError).toBeNull();
  });

  it("CONTROL: an explicit 404 is still not_found", async () => {
    getTrajectoryMock.mockRejectedValue(new ApiError("HTTP 404", 404, ""));
    getInvestigationStatusMock.mockResolvedValue(null);
    const { result } = await settled("inv-unknown");
    expect(result.current.status).toBe("not_found");
  });

  it("CONTROL: a healthy trajectory derives in_progress", async () => {
    getTrajectoryMock.mockResolvedValue({ investigation_id: "x", count: 1, events: [START] });
    getInvestigationStatusMock.mockResolvedValue(null);
    const { result } = await settled("inv-123");
    expect(result.current.status).toBe("in_progress");
    expect(result.current.question).toBe("Real Q?");
  });

  it("retry() after an outage re-fetches and recovers the real state", async () => {
    getTrajectoryMock.mockRejectedValueOnce(new ApiError("HTTP 503", 503, ""));
    getTrajectoryMock.mockResolvedValue({ investigation_id: "x", count: 1, events: [START] });
    getInvestigationStatusMock.mockResolvedValue(null);

    const { result } = await settled("inv-123");
    expect(result.current.status).toBe("error");

    act(() => result.current.retry?.());
    await waitFor(() => expect(result.current.status).toBe("in_progress"));
    expect(getTrajectoryMock).toHaveBeenCalledTimes(2);
    expect(result.current.loadError).toBeNull();
  });
});
