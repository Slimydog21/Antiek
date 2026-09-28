import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import { createRef } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

const arcadeRender = vi.hoisted(() => vi.fn());
const motion = vi.hoisted(() => ({ reduced: false }));
const track = vi.hoisted(() => vi.fn());
const openWindowMock = vi.hoisted(() => vi.fn());
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

vi.mock("./Canvas/Canvas", () => ({
  default: ({
    investigationId,
    onCiteSource,
  }: {
    investigationId: string;
    onCiteSource?: (
      node: { source_document_id: string | null },
      anchor: { left: number; top: number; right: number; bottom: number; width: number; height: number },
    ) => void;
  }) => (
    <div data-testid="selected-organism-canvas">
      <span data-testid="selected-organism-id">{investigationId}</span>
      <button
        onClick={() =>
          onCiteSource?.(
            { source_document_id: " doc/evidence 1 " },
            { left: 10, top: 10, right: 110, bottom: 40, width: 100, height: 30 },
          )
        }
      >
        Read grounded source
      </button>
      <button
        onClick={() =>
          onCiteSource?.(
            { source_document_id: "   " },
            { left: 10, top: 10, right: 110, bottom: 40, width: 100, height: 30 },
          )
        }
      >
        Read ungrounded source
      </button>
    </div>
  ),
}));

vi.mock("../../components/windows/openWindow", async (orig) => ({
  // The real module minus the store-touching open (readerWindowId stays
  // real — the stable-id invariant is asserted through it).
  ...(await orig<typeof import("../../components/windows/openWindow")>()),
  openWindow: openWindowMock,
}));

vi.mock("../../lib/analytics", () => ({ track }));

vi.mock("../../workspace/usePrefersReducedMotion", () => ({
  usePrefersReducedMotion: () => motion.reduced,
}));

vi.mock("../../arcade/waitArcadeFlag", () => ({
  mascotResearchWaitArcadeEnabled: true,
}));

vi.mock("../../workspace/PanelHost", () => ({
  PanelHost: ({ children }: { children: ReactNode }) => children,
}));

vi.mock("./useResearchSession", () => ({
  useResearchSession: () => sessionView.current,
}));

vi.mock("./useMascotResearchReactions", () => ({
  useMascotResearchReactions: () => undefined,
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
  openWindowMock.mockClear();
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

  it("still requests the lazy host under reduced motion (reduced cartridges, not hidden)", async () => {
    motion.reduced = true;
    render(<ResearchWaitArcadeGate {...base} />);
    expect(await screen.findByTestId("lazy-wait-arcade")).toBeTruthy();
    expect(arcadeRender).toHaveBeenCalledWith(
      expect.objectContaining({ episodeId: "session:3" }),
    );
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
    expect(screen.getByText(/reconnecting.*poll dropped/)).toBeTruthy();
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

  it("opens a grounded Canvas source in one identity-stable reader window without replacing the Canvas", async () => {
    render(
      <Monitor sessionId="session-source" sessionGeneration={1} busy={false} />,
    );
    fireEvent.click(await screen.findByRole("button", { name: "view as canvas" }));

    fireEvent.click(screen.getByRole("button", { name: "Read grounded source" }));

    expect(openWindowMock).toHaveBeenCalledWith(
      "reader",
      // Reading-global SPR-02: the write-only evidenceSourceContext flag is
      // unified into the typed origin shape — the canvas's investigation is
      // the calling context.
      { documentId: " doc/evidence 1 ", origin: { from: "evidence", id: "done-1" } },
      expect.objectContaining({
        id: "win:reader:%20doc%2Fevidence%201%20",
        title: "Research source",
        replaceOldestAtLimit: true,
      }),
    );
    expect(screen.getByTestId("selected-organism-id").textContent).toBe("done-1");

    fireEvent.click(screen.getByRole("button", { name: "Read ungrounded source" }));
    expect(openWindowMock).toHaveBeenCalledTimes(1);
  });
});
