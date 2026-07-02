/**
 * PenguinMascot.station.test.tsx — the fixed-station behaviours that need the
 * WERNER-ICE flag ON and a mounted rAF (2026-07-02 rework).
 *
 * This REPLACES the deleted PenguinMascot.iceFishing.integration.test.tsx,
 * whose central pin was "a bare pointermove MOVES the penguin" (the reel). That
 * behaviour is exactly what the operator removed, so its inverse is now the
 * load-bearing regression guard:
 *
 *   (1) THE PENGUIN DOES NOT FOLLOW THE CURSOR — a pointermove (anywhere, any
 *       distance) leaves Werner's position untouched. This is the whole ask.
 *   (2) THE CURSOR IS THE BAIT — when the pointer goes idle Werner runs his own
 *       -hole never-catch gag (`werner-fishing`); the moment the pointer moves
 *       again the gag stands down (the line to the cursor-bait takes over).
 *
 * Flag mocked ON (the production default) so the ice-fishing experience is live.
 */
import { afterAll, afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, cleanup, render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";

vi.mock("../werner/iceFishingFlags", () => ({
  wernerIceFishingCursor: true,
}));

import { PenguinMascot } from "./PenguinMascot";
import { useWorkspace } from "../workspace/WorkspaceStore";

const s = () => useWorkspace.getState();

const ORIG_matchMedia = (window as unknown as { matchMedia?: unknown }).matchMedia;

beforeEach(() => {
  s().reset();
  vi.useFakeTimers();
  // Motion allowed (reduce = false) so the station gag + rAF are live.
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
      dispatchEvent: vi.fn(),
      onchange: null,
    }),
  });
  Object.defineProperty(window, "innerWidth", { value: 1200, configurable: true });
  Object.defineProperty(window, "innerHeight", { value: 800, configurable: true });
});

afterEach(() => {
  cleanup();
  vi.useRealTimers();
});

afterAll(() => {
  Object.defineProperty(window, "matchMedia", {
    writable: true,
    configurable: true,
    value: ORIG_matchMedia,
  });
});

function mount() {
  return render(
    <MemoryRouter initialEntries={["/"]}>
      <Routes>
        <Route path="*" element={<PenguinMascot />} />
      </Routes>
    </MemoryRouter>,
  );
}

/** Advance a batch of animation frames (~16ms each) under fake timers, driving
 *  both the mascot's gag rAF and useMouseFollow's sampling. */
function advanceFrames(totalMs: number) {
  act(() => {
    vi.advanceTimersByTime(totalMs);
  });
}

describe("PenguinMascot — the fixed station (flag on)", () => {
  it("does NOT follow the cursor — a pointermove leaves Werner's position untouched", () => {
    mount();
    const el = screen.getByTestId("penguin-mascot") as HTMLButtonElement;
    const startLeft = parseFloat(el.style.left);
    const startTop = parseFloat(el.style.top);

    // Fire pointer moves all over the viewport, then let many frames run.
    act(() => {
      window.dispatchEvent(
        new PointerEvent("pointermove", { clientX: 900, clientY: 120, bubbles: true }),
      );
    });
    advanceFrames(1200);
    act(() => {
      window.dispatchEvent(
        new PointerEvent("pointermove", { clientX: 40, clientY: 700, bubbles: true }),
      );
    });
    advanceFrames(1200);

    // The reel is gone: the mascot never chases the pointer. Fixed station.
    expect(parseFloat(el.style.left)).toBe(startLeft);
    expect(parseFloat(el.style.top)).toBe(startTop);
  });

  it("runs the own-hole gag when the pointer is idle, and drops it when the pointer moves", () => {
    const { container } = mount();
    const bob = container.querySelector('[data-testid="penguin-mascot"] > span');
    expect(bob).toBeTruthy();

    // Make one move, then leave the pointer still well past POINTER_IDLE_MS
    // (2000ms) → the gag takes over (own-hole never-catch, cursor at rest).
    act(() => {
      window.dispatchEvent(
        new PointerEvent("pointermove", { clientX: 400, clientY: 300, bubbles: true }),
      );
    });
    advanceFrames(2600);
    expect(
      container.querySelector(".werner-fishing"),
      "pointer idle → the own-hole fishing gag owns Werner",
    ).toBeTruthy();

    // Move again → the gag stands down within a frame. (That the cursor-line
    // then TAKES OVER is a WernerFishingLayer concern, covered directly in
    // WernerFishingLayer.test.tsx — this suite only owns the mascot's gag gate.)
    act(() => {
      window.dispatchEvent(
        new PointerEvent("pointermove", { clientX: 405, clientY: 305, bubbles: true }),
      );
    });
    advanceFrames(64);
    expect(
      container.querySelector(".werner-fishing"),
      "pointer active → the own-hole gag stands down",
    ).toBeNull();
  });

  it("does not wander off on its own even with the flag on (fixed station)", () => {
    mount();
    const el = screen.getByTestId("penguin-mascot") as HTMLButtonElement;
    const startLeft = parseFloat(el.style.left);
    const startTop = parseFloat(el.style.top);
    advanceFrames(30000);
    expect(parseFloat(el.style.left)).toBe(startLeft);
    expect(parseFloat(el.style.top)).toBe(startTop);
  });
});
