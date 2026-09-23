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
