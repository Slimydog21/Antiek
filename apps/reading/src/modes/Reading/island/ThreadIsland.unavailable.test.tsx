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
  it("closes only the real diligence editor on Escape and restores its trigger", () => {
    useIslandThreadMock.mockReturnValue(thread({
      status: "complete",
      outcome: { questions: [], insights: [{
        node_id: "insight-1", kind: "insight", text: "A finding", refinement_count: 0,
        escalated: false, source_document_id: "doc-1",
      }] },
    }));
    renderIsland();
    fireEvent.click(screen.getByRole("button", { name: /Expand the island/ }));
    fireEvent.click(screen.getByRole("button", { name: "flag for diligence" }));
    const note = screen.getByRole("textbox", { name: "A note for the diligence flag (optional)" });
    expect(document.activeElement).toBe(note);
    fireEvent.keyDown(note, { key: "Escape" });
    expect(screen.queryByRole("textbox")).toBeNull();
    expect(screen.getByRole("button", { name: "Dismiss the island" })).toBeTruthy();
    expect(document.activeElement).toBe(screen.getByRole("button", { name: "flag for diligence" }));
  });

  it("closes only the real dig composer on Escape and restores its trigger", () => {
    useIslandThreadMock.mockReturnValue(thread());
    renderIsland();
    fireEvent.click(screen.getByRole("button", { name: /Expand the island/ }));
    const dig = screen.getByRole("button", { name: "Dig deeper" });
    fireEvent.click(dig);
    const question = screen.getByRole("textbox", { name: "What do you want to find out?" });
    expect(document.activeElement).toBe(question);
    fireEvent.keyDown(question, { key: "Escape" });
    expect(screen.queryByRole("textbox")).toBeNull();
    expect(screen.getByRole("button", { name: "Dismiss the island" })).toBeTruthy();
    expect(document.activeElement).toBe(dig);
  });

  it("moves focus into the card and returns it to the mark on Escape or Dismiss", () => {
    useIslandThreadMock.mockReturnValue(thread());
    renderIsland();
    fireEvent.click(screen.getByRole("button", { name: /Expand the island/ }));
    const dismiss = screen.getByRole("button", { name: "Dismiss the island" });
    expect(document.activeElement).toBe(dismiss);
    fireEvent.keyDown(dismiss, { key: "Escape" });
    expect(document.activeElement).toBe(screen.getByRole("button", { name: /Expand the island/ }));
    fireEvent.click(document.activeElement!);
    fireEvent.click(screen.getByRole("button", { name: "Dismiss the island" }));
    expect(document.activeElement).toBe(screen.getByRole("button", { name: /Expand the island/ }));
  });

  it("leaves an open card alone when a modal owns Escape and pointer input", () => {
    useIslandThreadMock.mockReturnValue(thread());
    renderIsland();
    fireEvent.click(screen.getByRole("button", { name: /Expand the island/ }));
    const modal = document.createElement("div");
    modal.setAttribute("role", "dialog");
    modal.setAttribute("aria-modal", "true");
    const input = document.createElement("input");
    modal.append(input);
    document.body.append(modal);
    try {
      input.focus();
      fireEvent.keyDown(input, { key: "Escape" });
      fireEvent.mouseDown(input);
      expect(screen.getByRole("button", { name: "Dismiss the island" })).toBeTruthy();
      expect(document.activeElement).toBe(input);
    } finally {
      modal.remove();
    }
  });

  it("does not take focus from an outside pointer target when closing", () => {
    useIslandThreadMock.mockReturnValue(thread());
    renderIsland();
    fireEvent.click(screen.getByRole("button", { name: /Expand the island/ }));
    const input = document.createElement("input");
    document.body.append(input);
    try {
      input.focus();
      fireEvent.mouseDown(input);
      expect(screen.queryByRole("button", { name: "Dismiss the island" })).toBeNull();
      expect(document.activeElement).toBe(input);
    } finally {
      input.remove();
    }
  });

  it("leaves Escape to a nested transient menu", () => {
    useIslandThreadMock.mockReturnValue(thread());
    renderIsland();
    fireEvent.click(screen.getByRole("button", { name: /Expand the island/ }));
    const card = screen.getByRole("dialog");
    const menu = document.createElement("div");
    menu.setAttribute("data-esc-overlay", "");
    menu.tabIndex = -1;
    card.append(menu);
    menu.focus();
    fireEvent.keyDown(menu, { key: "Escape" });
    expect(screen.getByRole("button", { name: "Dismiss the island" })).toBeTruthy();
    expect(document.activeElement).toBe(menu);
  });

  it("closes the focused card when another card is open", () => {
    useIslandThreadMock.mockReturnValue(thread());
    renderIsland();
    renderIsland();
    for (const glyph of screen.getAllByRole("button", { name: /Expand the island/ })) fireEvent.click(glyph);
    const buttons = screen.getAllByRole("button", { name: "Dismiss the island" });
    expect(document.activeElement).toBe(buttons[1]);
    fireEvent.keyDown(buttons[1], { key: "Escape" });
    expect(screen.getAllByRole("button", { name: "Dismiss the island" })).toEqual([buttons[0]]);
    expect(document.activeElement).toBe(screen.getByRole("button", { name: /Expand the island/ }));
  });

  it("handles its own Escape inside a floating workspace overlay", () => {
    useIslandThreadMock.mockReturnValue(thread());
    const view = renderIsland();
    view.container.setAttribute("data-esc-overlay", "");
    fireEvent.click(screen.getByRole("button", { name: /Expand the island/ }));
    fireEvent.keyDown(screen.getByRole("button", { name: "Dismiss the island" }), { key: "Escape" });
    expect(screen.queryByRole("button", { name: "Dismiss the island" })).toBeNull();
    expect(document.activeElement).toBe(screen.getByRole("button", { name: /Expand the island/ }));
  });

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
