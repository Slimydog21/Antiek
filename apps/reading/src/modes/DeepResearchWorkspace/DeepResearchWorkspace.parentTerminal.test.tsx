import { cleanup, render, renderHook, screen, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { SessionStatus } from "../../api/research";
import { MASCOT_EXPERIENCE_EVENT, notifyResearchStarted } from "../../mascot";

/**
 * Leaf DONE is not session success. GET /research/sessions/{id} carries the
 * parent-terminal contract (deep_research_complete + synthesis_tail_error) so
 * a failed synthesis tail cannot hide behind all-done leaves (audit W23).
 */

const getSession = vi.hoisted(() => vi.fn());

vi.mock("../../api/research", async (orig) => ({
  ...(await orig<typeof import("../../api/research")>()),
  getSession,
}));
vi.mock("./Canvas/Canvas", () => ({ default: () => null }));
vi.mock("../../workspace/PanelHost", () => ({
  PanelHost: ({ children }: { children: ReactNode }) => children,
}));
vi.mock("../../arcade/waitArcadeFlag", () => ({ mascotResearchWaitArcadeEnabled: false }));

import { Monitor } from ".";
import { deriveResearchReactionPhase } from "./useMascotResearchReactions";
import { useResearchSession } from "./useResearchSession";

const TAIL_ERROR = "[synthesis_tail] ValueError: synthesis tail exploded";

function body(over: Partial<SessionStatus> & Record<string, unknown>): SessionStatus {
  return {
    session_id: "session-1",
    live: true,
    researches: [
      { investigation_id: "session-1-leaf-0", sub_question: "sub one", state: "done" },
      { investigation_id: "session-1-leaf-1", sub_question: "sub two", state: "done" },
    ],
    cost: {
      per_research: { "session-1-leaf-0": 0.01, "session-1-leaf-1": 0.01 },
      session_total_usd: 0.02,
      aggregate_spent_usd: 0.02,
      aggregate_cap_usd: 10,
    },
    ...over,
  } as SessionStatus;
}

function renderMonitor(sessionId = "session-1") {
  return render(
    <MemoryRouter>
      <Monitor sessionId={sessionId} sessionGeneration={1} busy={false} />
    </MemoryRouter>,
  );
}

const experiences: string[] = [];
const listener = (event: Event) =>
  experiences.push((event as CustomEvent).detail.experience);

beforeEach(() => {
  getSession.mockReset();
  experiences.length = 0;
  window.addEventListener(MASCOT_EXPERIENCE_EVENT, listener);
});

afterEach(() => {
  cleanup();
  window.removeEventListener(MASCOT_EXPERIENCE_EVENT, listener);
});

describe("DRW monitor reads the session parent-terminal contract", () => {
  it("shows a failed synthesis tail as a failure, not 'complete', and the mascot reacts with error", async () => {
    getSession.mockResolvedValue(
      body({ deep_research_complete: false, synthesis_tail_error: TAIL_ERROR }),
    );
    notifyResearchStarted("session-1");
    experiences.length = 0;
    renderMonitor();
    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toContain(TAIL_ERROR);
    const heading = screen.getByRole("heading", { level: 2 });
    expect(heading.textContent).not.toMatch(/complete/);
    expect(heading.textContent).toMatch(/synthesis failed/);
    await waitFor(() => expect(experiences).toContain("deep_research_error"));
    expect(experiences).not.toContain("deep_research_complete");
  });

  it("shows 'complete' only when the backend reports deep_research_complete", async () => {
    getSession.mockResolvedValue(
      body({ deep_research_complete: true, synthesis_tail_error: null }),
    );
    notifyResearchStarted("session-1");
    experiences.length = 0;
    renderMonitor();
    await waitFor(() =>
      expect(screen.getByRole("heading", { level: 2 }).textContent).toMatch(/complete/),
    );
    expect(screen.queryByRole("alert")).toBeNull();
    await waitFor(() => expect(experiences).toContain("deep_research_complete"));
  });

  it("does not claim 'complete' for a recovered session whose parent outcome is unknown", async () => {
    getSession.mockResolvedValue(
      body({ live: false, all_terminal: true, deep_research_complete: null, synthesis_tail_error: null }),
    );
    renderMonitor();
    await waitFor(() =>
      expect(screen.getByRole("heading", { level: 2 }).textContent).toMatch(/2 researches/),
    );
    await waitFor(() =>
      expect(screen.getByRole("heading", { level: 2 }).textContent).toMatch(/synthesis status unknown/),
    );
    expect(screen.getByRole("heading", { level: 2 }).textContent).not.toMatch(/\bcomplete\b/);
  });

  it("does not claim 'complete' when the response omits the parent fields", async () => {
    getSession.mockResolvedValue(body({ all_terminal: true }));
    renderMonitor();
    await waitFor(() =>
      expect(screen.getByRole("heading", { level: 2 }).textContent).toMatch(/synthesis status unknown/),
    );
  });

  it("keeps polling after the leaves finish until the parent settles, then surfaces the tail failure", async () => {
    getSession
      .mockResolvedValueOnce(body({ deep_research_complete: false, synthesis_tail_error: null }))
      .mockResolvedValueOnce(body({ deep_research_complete: false, synthesis_tail_error: null }))
      .mockResolvedValue(body({ deep_research_complete: false, synthesis_tail_error: TAIL_ERROR }));
    const { result } = renderHook(() => useResearchSession("session-1", { intervalMs: 5 }));
    await waitFor(
      () =>
        expect(result.current.parent).toEqual({
          kind: "synthesis_failed",
          error: TAIL_ERROR,
        }),
      { timeout: 2000 },
    );
    expect(result.current.allTerminal).toBe(true);
    expect(getSession.mock.calls.length).toBeGreaterThanOrEqual(3);
  });

  // A skipped synthesis tail ends the parent without ever setting
  // deep_research_complete: the backend reports how the parent ended instead.
  const STOPPED_LEAVES = [
    { investigation_id: "session-1-leaf-0", sub_question: "sub one", state: "stopped" as const },
    { investigation_id: "session-1-leaf-1", sub_question: "sub two", state: "stopped" as const },
  ];
  const FAILED_LEAVES = [
    { investigation_id: "session-1-leaf-0", sub_question: "sub one", state: "failed" as const },
    { investigation_id: "session-1-leaf-1", sub_question: "sub two", state: "stopped" as const },
  ];
  const FAILED_REASON =
    "no leaf research finished: 1 of 2 failed (session-1-leaf-0); synthesis skipped";

  async function settledAfterFirstPoll(over: Record<string, unknown>) {
    getSession.mockResolvedValue(body(over));
    const { result } = renderHook(() => useResearchSession("session-1", { intervalMs: 5 }));
    await waitFor(() => expect(result.current.loading).toBe(false));
    // Several poll intervals later, nothing more was asked: the monitor settled.
    await new Promise((r) => setTimeout(r, 80));
    return result;
  }

  it("settles a skipped tail whose parent was stopped as stopped and stops polling", async () => {
    const result = await settledAfterFirstPoll({
      researches: STOPPED_LEAVES,
      deep_research_complete: false,
      synthesis_tail_error: null,
      synthesis_tail_skipped: "no_leaf_done",
      parent_terminal: { state: "stopped", reason: "stopped" },
      completion_running: false,
    });
    expect(result.current.parent).toEqual({ kind: "stopped" });
    expect(getSession).toHaveBeenCalledTimes(1);
  });

  it("settles a skipped tail whose parent failed as failed, with the reason, and stops polling", async () => {
    const result = await settledAfterFirstPoll({
      researches: FAILED_LEAVES,
      deep_research_complete: false,
      synthesis_tail_error: null,
      synthesis_tail_skipped: "no_leaf_done",
      parent_terminal: { state: "failed", reason: FAILED_REASON },
      completion_running: false,
    });
    expect(result.current.parent).toEqual({ kind: "failed", reason: FAILED_REASON });
    expect(getSession).toHaveBeenCalledTimes(1);
  });

  it("reads the parent terminal on a recovered session too", async () => {
    const result = await settledAfterFirstPoll({
      live: false,
      all_terminal: true,
      researches: STOPPED_LEAVES,
      deep_research_complete: null,
      synthesis_tail_error: null,
      parent_terminal: { state: "stopped", reason: "stopped" },
    });
    expect(result.current.parent).toEqual({ kind: "stopped" });
  });

  it("stops polling once completion ended without scheduling a tail", async () => {
    // Hard-ceiling runs and a server without the tail wired never write a
    // parent terminal; completion_running=false is the only settle signal.
    const result = await settledAfterFirstPoll({
      deep_research_complete: false,
      synthesis_tail_error: null,
      parent_terminal: null,
      completion_running: false,
    });
    expect(result.current.parent).toEqual({ kind: "not_synthesized" });
    expect(getSession).toHaveBeenCalledTimes(1);
  });

  it("settles a budget-halted parent as budget-halted, not as a stop", async () => {
    const result = await settledAfterFirstPoll({
      researches: STOPPED_LEAVES.map((r) => ({ ...r, state: "budget_halted" as const })),
      deep_research_complete: false,
      synthesis_tail_error: null,
      synthesis_tail_skipped: "no_leaf_done",
      parent_terminal: { state: "budget_halted", reason: "no leaf research finished" },
      completion_running: false,
    });
    expect(result.current.parent).toEqual({ kind: "budget_halted" });
    expect(getSession).toHaveBeenCalledTimes(1);
  });

  it("settles a parent that ended completed without DeepResearchComplete as unconfirmed", async () => {
    const result = await settledAfterFirstPoll({
      deep_research_complete: false,
      synthesis_tail_error: null,
      parent_terminal: { state: "done", reason: null },
      completion_running: false,
    });
    expect(result.current.parent).toEqual({ kind: "unconfirmed" });
    expect(getSession).toHaveBeenCalledTimes(1);
  });

  it("keeps polling while completion is still running and the parent has not ended", async () => {
    getSession
      .mockResolvedValueOnce(
        body({ deep_research_complete: false, parent_terminal: null, completion_running: true }),
      )
      .mockResolvedValue(
        body({
          deep_research_complete: false,
          parent_terminal: { state: "failed", reason: FAILED_REASON },
          completion_running: false,
        }),
      );
    const { result } = renderHook(() => useResearchSession("session-1", { intervalMs: 5 }));
    await waitFor(
      () => expect(result.current.parent).toEqual({ kind: "failed", reason: FAILED_REASON }),
      { timeout: 2000 },
    );
    expect(getSession.mock.calls.length).toBeGreaterThanOrEqual(2);
  });

  it("labels a stopped parent 'stopped' and a failed one as a failure with its reason", async () => {
    getSession.mockResolvedValue(
      body({
        researches: STOPPED_LEAVES,
        deep_research_complete: false,
        synthesis_tail_skipped: "no_leaf_done",
        parent_terminal: { state: "stopped", reason: "stopped" },
        completion_running: false,
      }),
    );
    renderMonitor();
    await waitFor(() =>
      expect(screen.getByRole("heading", { level: 2 }).textContent).toMatch(/stopped/),
    );
    expect(screen.getByRole("heading", { level: 2 }).textContent).not.toMatch(/not confirmed/);
    expect(screen.queryByRole("alert")).toBeNull();
    cleanup();

    getSession.mockResolvedValue(
      body({
        researches: FAILED_LEAVES,
        deep_research_complete: false,
        synthesis_tail_skipped: "no_leaf_done",
        parent_terminal: { state: "failed", reason: FAILED_REASON },
        completion_running: false,
      }),
    );
    renderMonitor();
    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toContain(FAILED_REASON);
    expect(screen.getByRole("heading", { level: 2 }).textContent).toMatch(/session failed/);
  });

  it("reacts with error when an all-done gather ends in a failed parent (empty evidence pack)", () => {
    expect(
      deriveResearchReactionPhase({
        sessionId: "s",
        loading: false,
        allTerminal: true,
        error: null,
        researchStates: ["done", "done"],
        parent: { kind: "failed", reason: "empty substrate-grounded evidence pack" },
      }),
    ).toBe("error");
  });

  it("derives an error reaction phase from a failed parent even when every leaf is done", () => {
    const snapshot = {
      sessionId: "s",
      loading: false,
      allTerminal: true,
      error: null,
      researchStates: ["done", "done"] as const,
    };
    expect(
      deriveResearchReactionPhase({
        ...snapshot,
        parent: { kind: "synthesis_failed", error: TAIL_ERROR },
      }),
    ).toBe("error");
    expect(deriveResearchReactionPhase({ ...snapshot, parent: { kind: "pending" } })).not.toBe(
      "complete",
    );
    expect(deriveResearchReactionPhase({ ...snapshot, parent: { kind: "unknown" } })).not.toBe(
      "complete",
    );
    expect(deriveResearchReactionPhase({ ...snapshot, parent: { kind: "complete" } })).toBe(
      "complete",
    );
  });
});
