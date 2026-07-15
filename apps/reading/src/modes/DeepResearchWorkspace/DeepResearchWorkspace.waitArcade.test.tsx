import { cleanup, render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import { createRef } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

const arcadeRender = vi.hoisted(() => vi.fn());
const motion = vi.hoisted(() => ({ reduced: false }));
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
    ],
    cost: null,
    live: true,
    allTerminal: false,
    loading: false,
    error: null as string | null,
  },
}));

vi.mock("./ResearchWaitArcade", () => ({
  default: (props: { episodeId: string; activeResearchCount: number }) => {
    arcadeRender(props);
    return <div data-testid="lazy-wait-arcade" />;
  },
}));

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

  it("mounts for a partial session and removes in the terminal render", async () => {
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
    expect(screen.queryByTestId("lazy-wait-arcade")).toBeNull();
  });

  it("does not request the lazy host under reduced motion", async () => {
    motion.reduced = true;
    render(<ResearchWaitArcadeGate {...base} />);
    await Promise.resolve();
    expect(screen.queryByTestId("lazy-wait-arcade")).toBeNull();
    expect(arcadeRender).not.toHaveBeenCalled();
  });

  it("keeps partial cards and reconnect truth visible, then removes the host in the terminal render", async () => {
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
    expect(screen.getByText(/reconnecting.*status details stay private/)).toBeTruthy();
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
    expect(screen.queryByTestId("lazy-wait-arcade")).toBeNull();
    expect(screen.getByText("Finished evidence")).toBeTruthy();
    expect(screen.getByText("Live evidence")).toBeTruthy();
  });
});
