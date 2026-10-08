/**
 * ThreadIsland.escape.test.tsx — the expanded card's Esc is its own only
 * when nothing above it claimed the key: an Esc another handler already
 * handled (defaultPrevented, e.g. the geared switch closing) and an Esc
 * pressed inside an open aria-modal dialog leave the card expanded (one
 * Esc reaches exactly one handler, workspace/escapeOverlay.ts). Repair
 * round 2026-10-07T22:40Z.
 */
import { afterEach, describe, expect, it, vi } from "vitest";
import { act, cleanup, fireEvent, render } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

import type { IslandThreadState } from "./useIslandThread";

const { useIslandThreadMock } = vi.hoisted(() => ({ useIslandThreadMock: vi.fn() }));
vi.mock("./useIslandThread", () => ({ useIslandThread: useIslandThreadMock }));

import ThreadIsland from "./ThreadIsland";

function thread(over: Partial<IslandThreadState> = {}): IslandThreadState {
  return {
    status: "unavailable", costTotal: 0, question: null, family: [], loading: false, outcomeLoading: false,
    outcome: null, sessionState: null, refetchFamily: vi.fn(), retry: null, ...over,
  };
}

function renderExpanded() {
  useIslandThreadMock.mockReturnValue(thread());
  const r = render(
    <MemoryRouter>
      <ThreadIsland anchorId="ahl-1" documentId="doc-1" investigationId="inv-1" servable passageQuote="a passage" pageIndexHint={3} />
    </MemoryRouter>,
  );
  fireEvent.click(r.container.querySelector('[data-island-status="unavailable"]') as Element);
  expect(r.container.querySelector('[data-island-state="collapsed"]')).toBeNull();
  return r;
}

function esc(target: EventTarget, preventFirst = false) {
  act(() => {
    const e = new KeyboardEvent("keydown", { key: "Escape", bubbles: true, cancelable: true });
    if (preventFirst) e.preventDefault();
    target.dispatchEvent(e);
  });
}

afterEach(() => {
  cleanup();
  useIslandThreadMock.mockReset();
  document.body.innerHTML = "";
});

describe("ThreadIsland — Esc ownership", () => {
  it("control: a plain Esc collapses the card", () => {
    const { container } = renderExpanded();
    esc(document.body);
    expect(container.querySelector('[data-island-state="collapsed"]')).not.toBeNull();
  });

  it("an Esc another handler already claimed leaves the card expanded", () => {
    const { container } = renderExpanded();
    esc(document.body, true);
    expect(container.querySelector('[data-island-state="collapsed"]')).toBeNull();
  });

  it("an Esc pressed inside an open modal is the modal's, not the card's", () => {
    const { container } = renderExpanded();
    const modal = document.createElement("div");
    modal.setAttribute("role", "dialog");
    modal.setAttribute("aria-modal", "true");
    const button = document.createElement("button");
    modal.append(button);
    document.body.append(modal);
    button.focus();
    esc(button);
    expect(container.querySelector('[data-island-state="collapsed"]')).toBeNull();
  });
});
