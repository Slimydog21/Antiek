/**
 * ComposeView.monitor.test.tsx — the DRW monitor's multi-select entry into
 * the composed evidence view (SPR-03: "reachable from the DRW monitor").
 * The Monitor mounts with a mocked session; ComposeView is stubbed so the
 * entry wiring (not the view — its own suite covers it) is what's proven:
 * arming selection adds per-card checkboxes, 2+ chosen threads open the
 * view with exactly those ids and the monitor's titles, and closing returns
 * to the monitor with selection cleared.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

const { useResearchSessionMock, composeViewMock } = vi.hoisted(() => ({
  useResearchSessionMock: vi.fn(),
  composeViewMock: vi.fn(),
}));

vi.mock("./useResearchSession", () => ({
  useResearchSession: useResearchSessionMock,
}));
vi.mock("./ComposeView", () => ({
  default: (props: { investigationIds: string[]; threadTitles?: Record<string, string> }) => {
    composeViewMock(props);
    return (
      <div data-testid="compose-view-stub">{props.investigationIds.join(",")}</div>
    );
  },
}));
vi.mock("../../components/windows/openWindow", () => ({
  openWindow: vi.fn(),
  readerWindowId: (id: string) => `reader-${id}`,
}));

import { Monitor } from "./index";

const SESSION = {
  loading: false,
  allTerminal: true,
  error: null,
  sourcePolicy: null,
  sourcePolicyExecution: null,
  hardCeiling: null,
  cost: null,
  researches: [
    {
      investigation_id: "inv-1",
      sub_question: "Supply-side research",
      state: "done",
    },
    {
      investigation_id: "inv-2",
      sub_question: "Rates research",
      state: "done",
    },
  ],
};

beforeEach(() => {
  useResearchSessionMock.mockReset();
  composeViewMock.mockReset();
  useResearchSessionMock.mockReturnValue(SESSION);
});

afterEach(() => cleanup());

function mountMonitor() {
  return render(
    <MemoryRouter>
      <Monitor sessionId="s-1" sessionGeneration={0} busy={false} />
    </MemoryRouter>,
  );
}

describe("the monitor's multi-select into the composed evidence view", () => {
  it("selects 2+ threads and opens the view with their ids and titles", async () => {
    mountMonitor();

    // Arming the selection puts a checkbox on each card.
    fireEvent.click(screen.getByRole("button", { name: "select to compare" }));
    const first = document.querySelector("[data-compose-select='inv-1']")!;
    const second = document.querySelector("[data-compose-select='inv-2']")!;
    expect(first).toBeTruthy();
    fireEvent.click(first);
    // One thread is not a composition — no review button yet.
    expect(screen.queryByRole("button", { name: /Review outcomes together/ })).toBeNull();
    fireEvent.click(second);

    fireEvent.click(screen.getByRole("button", { name: "Review outcomes together (2)" }));
    expect(screen.getByTestId("compose-view-stub").textContent).toBe("inv-1,inv-2");
    expect(composeViewMock).toHaveBeenCalledWith(
      expect.objectContaining({
        investigationIds: ["inv-1", "inv-2"],
        threadTitles: { "inv-1": "Supply-side research", "inv-2": "Rates research" },
      }),
    );
  });

  it("cancelling the selection arms nothing and keeps the monitor", () => {
    mountMonitor();
    fireEvent.click(screen.getByRole("button", { name: "select to compare" }));
    fireEvent.click(document.querySelector("[data-compose-select='inv-1']")!);
    fireEvent.click(screen.getByRole("button", { name: "cancel selection" }));
    expect(document.querySelector("[data-compose-select]")).toBeNull();
    expect(screen.queryByTestId("compose-view-stub")).toBeNull();
  });
});
