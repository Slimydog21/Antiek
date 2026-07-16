import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import type { ReactNode } from "react";
import { createRef } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

const arcadeRender = vi.hoisted(() => vi.fn());
const motion = vi.hoisted(() => ({ reduced: false }));
const track = vi.hoisted(() => vi.fn());
const sessionView = vi.hoisted(() => ({
  current: {
    researches: [
      {
        investigation_id: "done-1",
        sub_question: "Finished evidence",
        state: "done",
      },
      {
        investigation_id: "live-1",
        sub_question: "Live evidence",
        state: "running",
      },
      {
        investigation_id: "done-2",
        sub_question: "Second finished evidence",
        state: "done",
      },
      {
        investigation_id: "failed-1",
        sub_question: "Failed evidence",
        state: "failed",
      },
    ],
    cost: null,
    live: true,
    allTerminal: false,
    loading: false,
    error: null as string | null,
  },
}));

vi.mock("./ResearchWaitArcade", () => ({
  default: (props: {
    episodeId: string;
    activeResearchCount: number;
    onViewResearch?: (id: string) => void;
  }) => {
    arcadeRender(props);
    return (
      <div data-testid="lazy-wait-arcade">
        <button onClick={() => props.onViewResearch?.("done-2")}>
          Open broadcast result
        </button>
        <button onClick={() => props.onViewResearch?.("failed-1")}>
          Open broadcast details
        </button>
        <button onClick={() => props.onViewResearch?.("missing-1")}>
          Open missing broadcast
        </button>
      </div>
    );
  },
}));

vi.mock("./Canvas/Canvas", () => ({
  default: ({ investigationId }: { investigationId: string }) => (
    <div data-testid="selected-organism-canvas">{investigationId}</div>
  ),
}));

vi.mock("../../lib/analytics", () => ({ track }));

vi.mock("../../workspace/usePrefersReducedMotion", () => ({
  usePrefersReducedMotion: () => motion.reduced,
}));

vi.mock("../../arcade/waitArcadeFlag", () => ({
  wernerResearchWaitArcadeEnabled: true,
}));

vi.mock("../../workspace/PanelHost", () => ({
  PanelHost: ({ children }: { children: ReactNode }) => children,
}));

vi.mock("./useResearchSession", () => ({
  useResearchSession: () => sessionView.current,
}));

vi.mock("./useWernerResearchReactions", () => ({
  useWernerResearchReactions: () => undefined,
}));

import { Monitor, ResearchWaitArcadeGate } from ".";

const base = {
  enabled: true,
  episodeId: "session:3",
  hasAuthoritativeSnapshot: true,
  researchCount: 4,
  activeResearchCount: 2,
  allTerminal: false,
  returnFocusRef: createRef<HTMLElement>(),
};

afterEach(() => {
  cleanup();
  arcadeRender.mockClear();
  track.mockClear();
  motion.reduced = false;
  sessionView.current = {
    researches: [
      {
        investigation_id: "done-1",
        sub_question: "Finished evidence",
        state: "done",
      },
      {
        investigation_id: "live-1",
        sub_question: "Live evidence",
        state: "running",
      },
      {
        investigation_id: "done-2",
        sub_question: "Second finished evidence",
        state: "done",
      },
      {
        investigation_id: "failed-1",
        sub_question: "Failed evidence",
        state: "failed",
      },
    ],
    cost: null,
    live: true,
    allTerminal: false,
    loading: false,
    error: null,
  };
});

describe("Deep Research wait arcade gate", () => {
  it.each([
    ["disabled", { enabled: false }],
    ["connecting", { hasAuthoritativeSnapshot: false }],
    ["empty", { researchCount: 0, activeResearchCount: 0 }],
    ["terminal", { activeResearchCount: 0, allTerminal: true }],
  ])("does not request the lazy host when %s", async (_name, patch) => {
    render(<ResearchWaitArcadeGate {...base} {...patch} />);
    await Promise.resolve();
    expect(screen.queryByTestId("lazy-wait-arcade")).toBeNull();
    expect(arcadeRender).not.toHaveBeenCalled();
  });

  it("mounts for a partial session and preserves the lazy host for its terminal broadcast", async () => {
    const { rerender } = render(<ResearchWaitArcadeGate {...base} />);
    expect(await screen.findByTestId("lazy-wait-arcade")).toBeTruthy();
    expect(arcadeRender).toHaveBeenCalledWith(
      expect.objectContaining({
        episodeId: "session:3",
        activeResearchCount: 2,
      }),
    );

    rerender(
      <ResearchWaitArcadeGate {...base} activeResearchCount={0} allTerminal />,
    );
    expect(screen.getByTestId("lazy-wait-arcade")).toBeTruthy();
    expect(arcadeRender).toHaveBeenLastCalledWith(
      expect.objectContaining({ allTerminal: true, activeResearchCount: 0 }),
    );
  });

  it("does not request the lazy host under reduced motion", async () => {
    motion.reduced = true;
    render(<ResearchWaitArcadeGate {...base} />);
    await Promise.resolve();
    expect(screen.queryByTestId("lazy-wait-arcade")).toBeNull();
    expect(arcadeRender).not.toHaveBeenCalled();
  });

  it("does not retain terminal eligibility from activity hidden by reduced motion", async () => {
    motion.reduced = true;
    const view = render(<ResearchWaitArcadeGate {...base} />);
    await Promise.resolve();
    motion.reduced = false;
    view.rerender(
      <ResearchWaitArcadeGate {...base} activeResearchCount={0} allTerminal />,
    );
    await Promise.resolve();
    expect(screen.queryByTestId("lazy-wait-arcade")).toBeNull();
  });

  it("keeps cards and reconnect truth visible while the terminal broadcast host remains mounted", async () => {
    const { rerender } = render(
      <Monitor
        sessionId="session-partial"
        sessionGeneration={7}
        busy={false}
      />,
    );
    expect(await screen.findByTestId("lazy-wait-arcade")).toBeTruthy();
    expect(screen.getByText("Finished evidence")).toBeTruthy();
    expect(screen.getByText("Live evidence")).toBeTruthy();

    sessionView.current = { ...sessionView.current, error: "poll dropped" };
    rerender(
      <Monitor
        sessionId="session-partial"
        sessionGeneration={7}
        busy={false}
      />,
    );
    expect(
      screen.getByText(/reconnecting.*status details stay private/),
    ).toBeTruthy();
    expect(screen.queryByText(/poll dropped/)).toBeNull();
    expect(screen.getByTestId("lazy-wait-arcade")).toBeTruthy();

    sessionView.current = {
      ...sessionView.current,
      researches: sessionView.current.researches.map((research) => ({
        ...research,
        state: "done" as const,
      })),
      allTerminal: true,
      error: null,
    };
    rerender(
      <Monitor
        sessionId="session-partial"
        sessionGeneration={7}
        busy={false}
      />,
    );
    expect(screen.getByTestId("lazy-wait-arcade")).toBeTruthy();
    expect(screen.getByText("Finished evidence")).toBeTruthy();
    expect(screen.getByText("Live evidence")).toBeTruthy();
  });

  it("opens the exact broadcast result and restores focus to its card on Back", async () => {
    render(
      <Monitor sessionId="session-result" sessionGeneration={1} busy={false} />,
    );
    fireEvent.click(
      await screen.findByRole("button", { name: "Open broadcast result" }),
    );
    expect(screen.getByTestId("selected-organism-canvas").textContent).toBe(
      "done-2",
    );
    expect(track).toHaveBeenCalledWith("deep_research_canvas_opened", {
      investigation_id: "done-2",
      source: "werner_broadcast",
      outcome: "done",
    });

    fireEvent.click(screen.getByRole("button", { name: /back to monitor/i }));
    const card = await screen.findByRole("region", { name: "research done-2" });
    await waitFor(() => expect(document.activeElement).toBe(card));
  });

  it("opens the exact terminal-card result and restores focus to its action", async () => {
    render(
      <Monitor sessionId="session-card" sessionGeneration={1} busy={false} />,
    );
    const actions = screen.getAllByRole("button", { name: "View result" });
    fireEvent.click(actions[1]);
    expect(screen.getByTestId("selected-organism-canvas").textContent).toBe(
      "done-2",
    );

    fireEvent.click(screen.getByRole("button", { name: /back to monitor/i }));
    await waitFor(() => {
      expect(document.activeElement).toBe(
        screen.getAllByRole("button", { name: "View result" })[1],
      );
    });
  });

  it.each(["failed", "stopped", "budget_halted"] as const)(
    "keeps a %s broadcast on its state-honest terminal card",
    async (state) => {
      sessionView.current = {
        ...sessionView.current,
        researches: sessionView.current.researches.map((research) =>
          research.investigation_id === "failed-1"
            ? { ...research, state }
            : research,
        ),
      };
      render(
        <Monitor
          sessionId="session-failed"
          sessionGeneration={1}
          busy={false}
        />,
      );
      fireEvent.click(
        await screen.findByRole("button", { name: "Open broadcast details" }),
      );
      expect(screen.queryByTestId("selected-organism-canvas")).toBeNull();
      await waitFor(() => {
        expect(document.activeElement).toBe(
          screen.getByRole("region", { name: "research failed-1" }),
        );
      });
      expect(track).not.toHaveBeenCalled();
    },
  );

  it("fails closed for a stale broadcast identity", async () => {
    render(
      <Monitor sessionId="session-stale" sessionGeneration={1} busy={false} />,
    );
    fireEvent.click(
      await screen.findByRole("button", { name: "Open missing broadcast" }),
    );
    expect(screen.queryByTestId("selected-organism-canvas")).toBeNull();
    expect(screen.getByText("Second finished evidence")).toBeTruthy();
    expect(track).not.toHaveBeenCalled();
  });

  it("falls back to the monitor heading when the result origin disappeared", async () => {
    const view = render(
      <Monitor
        sessionId="session-fallback"
        sessionGeneration={1}
        busy={false}
      />,
    );
    fireEvent.click(
      (await screen.findAllByRole("button", { name: "View result" }))[1],
    );
    sessionView.current = {
      ...sessionView.current,
      researches: sessionView.current.researches.filter(
        (research) => research.investigation_id !== "done-2",
      ),
    };
    view.rerender(
      <Monitor
        sessionId="session-fallback"
        sessionGeneration={1}
        busy={false}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: /back to monitor/i }));
    const heading = await screen.findByRole("heading", { level: 2 });
    await waitFor(() => expect(document.activeElement).toBe(heading));
  });
});
