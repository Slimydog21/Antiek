/**
 * useIslandThread.test.ts — the hook composition proofs (island SPR-01).
 *
 * The REAL useIslandThread composes the REAL useInvestigationTree against
 * mocked sibling hooks + transports (useInvestigation, useInvestigationList,
 * getSession, getDistillation). The proofs are the spec's own:
 *   live (advancing cost) · complete (insights) · complete_empty (no
 *   insights — not an error) · failed / stopped / budget_halted (their
 *   honest terminals) · not_found → gone (never fabricated).
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, renderHook, waitFor } from "@testing-library/react";

import type { InvestigationState } from "../../../hooks/useInvestigation";
import type { InvestigationSummary } from "../../../lib/api";
import type { SessionStatus } from "../../../api/research";
import type { DistillationResponse } from "../../../lib/api";

const {
  useInvestigationMock,
  useInvestigationListMock,
  getSessionMock,
  getDistillationMock,
} = vi.hoisted(() => ({
  useInvestigationMock: vi.fn(),
  useInvestigationListMock: vi.fn(),
  getSessionMock: vi.fn(),
  getDistillationMock: vi.fn(),
}));

vi.mock("../../../hooks/useInvestigation", () => ({
  useInvestigation: useInvestigationMock,
}));
vi.mock("../../../hooks/useInvestigationList", () => ({
  useInvestigationList: useInvestigationListMock,
}));
vi.mock("../../../api/research", async (orig) => ({
  ...(await orig<typeof import("../../../api/research")>()),
  getSession: getSessionMock,
}));
vi.mock("../../../lib/api", async (orig) => ({
  ...(await orig<typeof import("../../../lib/api")>()),
  getDistillation: getDistillationMock,
}));

import { useIslandThread } from "./useIslandThread";

function projection(over: Partial<InvestigationState> = {}): InvestigationState {
  return {
    id: "inv-1",
    status: "in_progress",
    question: "the question",
    events: [],
    terminalPayload: null,
    costTotal: 0.1,
    completedAt: null,
    streamStatus: "open",
    reconnects: 0,
    sourcePolicy: [],
    ...over,
  };
}

function summary(over: Partial<InvestigationSummary> = {}): InvestigationSummary {
  return {
    investigation_id: "inv-1",
    question: "the question",
    status: "in_progress",
    started_at: "2026-09-24T10:00:00Z",
    completed_at: null,
    cost_usd_total: 0.1,
    parent_investigation_id: null,
    ...over,
  };
}

function session(state: SessionStatus["researches"][number]["state"]): SessionStatus {
  return {
    session_id: "inv-1",
    live: state === "running",
    researches: [
      { investigation_id: "inv-1", sub_question: "q", state },
    ],
  } as SessionStatus;
}

function distillation(count: number): DistillationResponse {
  return {
    investigation_id: "inv-1",
    insights: Array.from({ length: count }, (_, i) => ({
      node_id: `n-${i}`,
      kind: "insight",
      text: `finding ${i}`,
      refinement_count: 0,
      escalated: false,
    })),
    questions: [],
  } as DistillationResponse;
}

beforeEach(() => {
  window.localStorage.removeItem("antiek:investigation_tree");
  useInvestigationMock.mockReset();
  useInvestigationListMock.mockReset().mockReturnValue({
    investigations: [],
    loading: false,
    error: null,
    refetch: vi.fn(),
  });
  getSessionMock.mockReset().mockRejectedValue(new Error("no session for this thread"));
  getDistillationMock.mockReset();
});

afterEach(() => {
  cleanup();
  window.localStorage.removeItem("antiek:investigation_tree");
});

describe("useIslandThread", () => {
  it("a live thread reads live with advancing cost (the projection drives)", async () => {
    useInvestigationMock.mockReturnValue(projection({ costTotal: 0.1 }));
    const { result, rerender } = renderHook(() => useIslandThread("inv-1"));
    await waitFor(() => expect(result.current.status).toBe("live"));
    expect(result.current.costTotal).toBe(0.1);
    // Cost advances as the projection recomputes (dispatch.call events land).
    useInvestigationMock.mockReturnValue(projection({ costTotal: 0.4 }));
    rerender();
    await waitFor(() => expect(result.current.costTotal).toBe(0.4));
    expect(result.current.status).toBe("live");
    expect(result.current.loading).toBe(false);
  });

  it("completed-with-insights is complete", async () => {
    useInvestigationMock.mockReturnValue(projection({ status: "completed" }));
    getDistillationMock.mockResolvedValue(distillation(2));
    const { result } = renderHook(() => useIslandThread("inv-1"));
    await waitFor(() => expect(result.current.status).toBe("complete"));
    expect(result.current.outcomeLoading).toBe(false);
    expect(getDistillationMock).toHaveBeenCalledWith("inv-1");
  });

  it("completed-empty is complete_empty — an honest terminal, not an error", async () => {
    useInvestigationMock.mockReturnValue(projection({ status: "completed" }));
    getDistillationMock.mockResolvedValue(distillation(0));
    const { result } = renderHook(() => useIslandThread("inv-1"));
    await waitFor(() => expect(result.current.status).toBe("complete_empty"));
    expect(result.current.outcomeLoading).toBe(false);
  });

  it("a failed thread reads failed", async () => {
    useInvestigationMock.mockReturnValue(projection({ status: "failed" }));
    getDistillationMock.mockResolvedValue(distillation(0));
    const { result } = renderHook(() => useIslandThread("inv-1"));
    await waitFor(() => expect(result.current.status).toBe("failed"));
  });

  it("a stopped thread (summary vocabulary) reads stopped, never spins forever", async () => {
    useInvestigationMock.mockReturnValue(projection({ status: "in_progress" }));
    useInvestigationListMock.mockReturnValue({
      investigations: [summary({ status: "stopped" })],
      loading: false,
      error: null,
      refetch: vi.fn(),
    });
    const { result } = renderHook(() => useIslandThread("inv-1"));
    await waitFor(() => expect(result.current.status).toBe("stopped"));
  });

  it("a budget-halted session refines to budget_halted", async () => {
    useInvestigationMock.mockReturnValue(projection({ status: "in_progress" }));
    getSessionMock.mockResolvedValue(session("budget_halted"));
    const { result } = renderHook(() => useIslandThread("inv-1"));
    await waitFor(() => expect(result.current.status).toBe("budget_halted"));
    expect(result.current.sessionState).toBe("budget_halted");
  });

  it("an unresolvable session is an honest no-refinement (projection decides)", async () => {
    useInvestigationMock.mockReturnValue(projection({ status: "in_progress" }));
    getSessionMock.mockRejectedValue(new Error("404"));
    const { result } = renderHook(() => useIslandThread("inv-1"));
    await waitFor(() => expect(result.current.status).toBe("live"));
    expect(result.current.sessionState).toBeNull();
  });

  it("a missing trajectory is gone — never fabricated", async () => {
    useInvestigationMock.mockReturnValue(projection({ status: "not_found", events: [] }));
    const { result } = renderHook(() => useIslandThread("inv-1"));
    await waitFor(() => expect(result.current.status).toBe("gone"));
    expect(getDistillationMock).not.toHaveBeenCalled();
  });

  it("the family is the island's root-and-chases subtree from the real tree", async () => {
    useInvestigationMock.mockReturnValue(projection({ status: "in_progress" }));
    useInvestigationListMock.mockReturnValue({
      investigations: [
        summary({ investigation_id: "root", question: "root q" }),
        summary({ investigation_id: "chase-1", parent_investigation_id: "root" }),
        summary({ investigation_id: "chase-2", parent_investigation_id: "root" }),
        summary({ investigation_id: "grand-1", parent_investigation_id: "chase-2" }),
        summary({ investigation_id: "other" }),
      ],
      loading: false,
      error: null,
      refetch: vi.fn(),
    });
    const { result } = renderHook(() => useIslandThread("chase-1"));
    await waitFor(() =>
      expect(result.current.family.map((n) => n.investigationId)).toEqual([
        "root",
        "chase-1",
        "chase-2",
        "grand-1",
      ]),
    );
    expect(result.current.family.map((n) => n.depth)).toEqual([0, 1, 1, 2]);
    expect(result.current.family[0].status).toBe("in_progress");
  });

  it("a null investigation projects nothing and never fetches", () => {
    useInvestigationMock.mockReturnValue(
      projection({ status: "loading", costTotal: 0 }),
    );
    const { result } = renderHook(() => useIslandThread(null));
    expect(result.current.family).toEqual([]);
    expect(getSessionMock).not.toHaveBeenCalled();
    expect(getDistillationMock).not.toHaveBeenCalled();
  });
});
