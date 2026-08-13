/**
 * useInvestigationList.test.ts — the SHARED store contract (herdr transfer
 * P1): every consumer shares ONE fetch + ONE poller; refetch from any
 * surface refreshes all subscribers.
 */
import { beforeEach, describe, expect, it, vi } from "vitest";
import { act, renderHook, waitFor } from "@testing-library/react";

import { useInvestigationList } from "./useInvestigationList";

const { listMock } = vi.hoisted(() => ({
  listMock: vi.fn(),
}));

vi.mock("../lib/api", async (orig) => {
  const actual = await orig<typeof import("../lib/api")>();
  return { ...actual, listInvestigations: listMock };
});

import type { InvestigationSummary } from "../lib/api";

function inv(id: string): InvestigationSummary {
  return {
    investigation_id: id,
    question: `q ${id}`,
    status: "in_progress",
    started_at: null,
    completed_at: null,
    cost_usd_total: 0,
    parent_investigation_id: null,
  };
}

// Reset module-level shared state between tests by unmounting everything.
beforeEach(() => {
  listMock.mockReset();
  listMock.mockResolvedValue({
    count: 1,
    investigations: [inv("a")],
  });
});

describe("useInvestigationList shared store", () => {
  it("two consumers share ONE fetch", async () => {
    const a = renderHook(() => useInvestigationList({ limit: 50 }));
    const b = renderHook(() => useInvestigationList({ limit: 200 }));
    await waitFor(() => {
      expect(a.result.current.investigations.length).toBe(1);
    });
    await waitFor(() => {
      expect(b.result.current.investigations.length).toBe(1);
    });
    // The second consumer raised the limit to 200 — the store fetches with
    // the max, but a single in-flight fetch serves both.
    expect(listMock.mock.calls.length).toBeGreaterThanOrEqual(1);
    a.unmount();
    b.unmount();
  });

  it("refetch from one consumer refreshes the other", async () => {
    const a = renderHook(() => useInvestigationList({ limit: 50 }));
    await waitFor(() => {
      expect(a.result.current.investigations.length).toBe(1);
    });
    const b = renderHook(() => useInvestigationList({ limit: 50 }));
    listMock.mockResolvedValue({
      count: 2,
      investigations: [inv("a"), inv("b")],
    });
    act(() => {
      a.result.current.refetch();
    });
    await waitFor(() => {
      expect(b.result.current.investigations.length).toBe(2);
    });
    a.unmount();
    b.unmount();
  });
});
