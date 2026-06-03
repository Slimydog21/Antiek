/**
 * WERNER-ICE SPR-15 — mounted PenguinMascot reel integration (ice flag on).
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

vi.mock("../werner/iceFishingFlags", () => ({
  wernerIceFishingCursor: true,
}));

import { centerLaggedTarget, LAG_MS } from "../werner";
import { PenguinMascot } from "./PenguinMascot";

const MASCOT_SIZE = 64;
const HANDOFF_EPSILON_PX = 24;
const HANDOFF_BUDGET_MS = 950;

beforeEach(() => {
  vi.useFakeTimers();
  Object.defineProperty(window, "innerWidth", { value: 1200, configurable: true });
  Object.defineProperty(window, "innerHeight", { value: 800, configurable: true });
  Object.defineProperty(window, "matchMedia", {
    writable: true,
    configurable: true,
    value: (q: string) => ({
      matches: false,
      media: q,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      addListener: vi.fn(),
      removeListener: vi.fn(),
    }),
  });
});

afterEach(() => {
  cleanup();
  vi.useRealTimers();
});

function advanceFrames(frames: number, dtMs = 16) {
  act(() => {
    for (let i = 0; i < frames; i++) {
      vi.advanceTimersByTime(dtMs);
    }
  });
}

describe("PenguinMascot ice-fishing mounted integration", () => {
  it("reel rAF pursues centered lagged hook within 950ms (not live pointer)", () => {
    render(
      <MemoryRouter>
        <PenguinMascot />
      </MemoryRouter>,
    );
    const el = screen.getByTestId("penguin-mascot") as HTMLElement;
    const startX = parseFloat(el.style.left);
    const startY = parseFloat(el.style.top);

    act(() => {
      fireEvent.pointerMove(window, { clientX: 420, clientY: 320 });
    });
    // Fill lag buffer, then let reel rAF run (LAG_MS + REEL_TAU budget).
    advanceFrames(Math.ceil((LAG_MS + HANDOFF_BUDGET_MS) / 16) + 8);

    const endX = parseFloat(el.style.left);
    const endY = parseFloat(el.style.top);
    const hook = centerLaggedTarget({ x: 420, y: 320 }, MASCOT_SIZE)!;
    const err = Math.hypot(endX - hook.x, endY - hook.y);

    expect(Math.hypot(endX - startX, endY - startY)).toBeGreaterThan(1);
    expect(err).toBeLessThanOrEqual(HANDOFF_EPSILON_PX + 16);
    expect(LAG_MS).toBe(500);
  });

  it("applies walk gait class while reel is active", () => {
    const { container } = render(
      <MemoryRouter>
        <PenguinMascot />
      </MemoryRouter>,
    );
    act(() => {
      fireEvent.pointerMove(window, { clientX: 200, clientY: 200 });
    });
    advanceFrames(30);
    expect(container.querySelector(".werner-waddle")).toBeTruthy();
  });
});