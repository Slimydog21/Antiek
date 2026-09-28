/**
 * ThreadIsland.unavailable.test.tsx — an island whose thread could not be
 * read says so and offers the retry. It never pulses as if the thread ran,
 * never reads "record not found", and never shows an outcome section it
 * cannot know.
 */
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

import type { IslandThreadState } from "./useIslandThread";

const { useIslandThreadMock } = vi.hoisted(() => ({ useIslandThreadMock: vi.fn() }));
vi.mock("./useIslandThread", () => ({ useIslandThread: useIslandThreadMock }));

import ThreadIsland from "./ThreadIsland";

function thread(over: Partial<IslandThreadState> = {}): IslandThreadState {
  return {
    status: "unavailable",
    costTotal: 0,
    question: null,
    family: [],
    loading: false,
    outcomeLoading: false,
    outcome: null,
    sessionState: null,
    refetchFamily: vi.fn(),
    retry: null,
    ...over,
  };
}

function renderIsland() {
  return render(
    <MemoryRouter>
      <ThreadIsland
        anchorId="ahl-1"
        documentId="doc-1"
        investigationId="inv-1"
        servable
        passageQuote="a passage"
        pageIndexHint={3}
      />
    </MemoryRouter>,
  );
}

afterEach(() => {
  cleanup();
  useIslandThreadMock.mockReset();
});

describe("ThreadIsland — unavailable", () => {
  it("the collapsed glyph names the unknown state and does not pulse", () => {
    useIslandThreadMock.mockReturnValue(thread());
    const { container } = renderIsland();
    const button = container.querySelector('[data-island-status="unavailable"]');
    expect(button).not.toBeNull();
    expect(button?.getAttribute("aria-label")).toMatch(/status unavailable/);
    expect(container.querySelector("[data-island-glyph]")?.className).not.toMatch(/animate-pulse/);
  });

  it("the expanded card says the status could not be read and retries on request", () => {
    const retry = vi.fn();
    useIslandThreadMock.mockReturnValue(thread({ retry }));
    const { container } = renderIsland();
    fireEvent.click(container.querySelector('[data-island-status="unavailable"]') as Element);
    expect(screen.getByText(/couldn't load its status/)).toBeTruthy();
    expect(container.querySelector("[data-island-unavailable]")).not.toBeNull();
    expect(container.querySelector("[data-island-outcome]")).toBeNull();
    expect(container.querySelector("[data-island-gone]")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(retry).toHaveBeenCalledTimes(1);
  });

  it("with no retry available the card still explains, without a dead button", () => {
    useIslandThreadMock.mockReturnValue(thread({ retry: null }));
    const { container } = renderIsland();
    fireEvent.click(container.querySelector('[data-island-status="unavailable"]') as Element);
    expect(container.querySelector("[data-island-unavailable]")).not.toBeNull();
    expect(screen.queryByRole("button", { name: "Try again" })).toBeNull();
  });
});
