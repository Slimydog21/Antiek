/**
 * WernerFishingLayer.test.tsx — the cursor-line pointer-idle gate (2026-07-02).
 *
 * Under the fixed station the rod tip no longer moves onto the bait (there is no
 * reel), so the viewport line must be gated explicitly: it draws from the rod
 * tip to the cursor-bait ONLY while the pointer is ACTIVE, and hides while the
 * pointer is IDLE (Werner's own-hole gag owns the fishing visual then). This
 * pins that gate so a fixed rod tip never leaves TWO lines on screen (the
 * viewport cursor-line + the gag's own-hole line) at once.
 */
import { afterAll, afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, cleanup, render } from "@testing-library/react";

vi.mock("./iceFishingFlags", () => ({ wernerIceFishingCursor: true }));

import { WernerFishingLayer } from "./WernerFishingLayer";
import { POINTER_IDLE_MS } from "./useMouseFollow";

const ORIG_matchMedia = (window as unknown as { matchMedia?: unknown }).matchMedia;

beforeEach(() => {
  vi.useFakeTimers();
  Object.defineProperty(window, "matchMedia", {
    writable: true,
    configurable: true,
    value: (q: string) => ({
      matches: false, // motion allowed
      media: q,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      addListener: vi.fn(),
      removeListener: vi.fn(),
      dispatchEvent: vi.fn(),
      onchange: null,
    }),
  });
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

/** Render a stand-in mascot button (the layer resolves the rod tip from it) plus
 *  the fishing layer. */
function mount() {
  return render(
    <>
      <button data-testid="penguin-mascot" style={{ position: "fixed", left: 100, top: 100 }} />
      <WernerFishingLayer />
    </>,
  );
}

function lineD(container: HTMLElement): string {
  return container.querySelector("svg path")?.getAttribute("d") ?? "";
}

describe("WernerFishingLayer — the cursor-line pointer-idle gate", () => {
  it("draws the line to the cursor-bait while the pointer is ACTIVE", () => {
    const { container } = mount();
    act(() => {
      window.dispatchEvent(
        new PointerEvent("pointermove", { clientX: 700, clientY: 500, bubbles: true }),
      );
      // A few rAF frames so the layer's tick runs.
      vi.advanceTimersByTime(64);
    });
    // A fresh move is active (not idle) → the line to the cursor is drawn.
    expect(lineD(container)).not.toBe("");
  });

  it("hides the line once the pointer goes IDLE (the own-hole gag owns the visual)", () => {
    const { container } = mount();
    act(() => {
      window.dispatchEvent(
        new PointerEvent("pointermove", { clientX: 700, clientY: 500, bubbles: true }),
      );
      vi.advanceTimersByTime(64);
    });
    expect(lineD(container)).not.toBe("");
    // Leave the pointer still past POINTER_IDLE_MS → the line must clear.
    act(() => {
      vi.advanceTimersByTime(POINTER_IDLE_MS + 200);
    });
    expect(lineD(container)).toBe("");
  });
});
