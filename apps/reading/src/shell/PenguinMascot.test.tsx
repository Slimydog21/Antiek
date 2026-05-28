/**
 * PenguinMascot.test.tsx — SPR-12 M3 acceptance.
 *
 * Load-bearing claims (each ASSERTED, not eyeballed — rigor #3):
 *  - single-click FLOATS the project tab (the one "shortcuts:projecttree"
 *    workspace panel) in floating mode — but only AFTER the ~250ms
 *    click-vs-doubleclick window elapses (the float is deferred so a
 *    double-click can cancel it);
 *  - if the tree already exists docked, a single-click flips it to floating
 *    (it does not duplicate);
 *  - a REAL double-click (the browser's click + click + dblclick sequence)
 *    OPENS the project (navigates to /home) and leaves NO stray floating
 *    project-tree panel (the pending single-click float was cancelled);
 *  - a drag MOVES the mascot and an aggressive off-screen drag CLAMPS so the
 *    mascot stays reachable (never lost past the viewport edge);
 *  - a drag-then-release does NOT also float (the click is suppressed);
 *  - prefers-reduced-motion removes the wander class (the still-mascot path).
 */
import { afterAll, afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";

import { PenguinMascot, PROJECT_TREE_PANEL_ID } from "./PenguinMascot";
import { useWorkspace } from "../workspace/WorkspaceStore";

const s = () => useWorkspace.getState();

// Snapshot the globals we mutate so we can restore them after this suite —
// the worker is shared across files, so leaving prototype stubs / a fake
// matchMedia behind would risk leaking into later test files.
const proto = window.HTMLElement.prototype as unknown as Record<string, unknown>;
const ORIG = {
  setPointerCapture: proto.setPointerCapture,
  releasePointerCapture: proto.releasePointerCapture,
  hasPointerCapture: proto.hasPointerCapture,
  matchMedia: (window as unknown as { matchMedia?: unknown }).matchMedia,
};

// jsdom doesn't implement pointer capture; stub it so setPointerCapture /
// hasPointerCapture / releasePointerCapture don't throw during the drag.
beforeEach(() => {
  s().reset();
  // Fake timers so the deferred single-click float (the ~250ms
  // click-vs-doubleclick window) is driven deterministically.
  vi.useFakeTimers();
  proto.setPointerCapture = vi.fn();
  proto.releasePointerCapture = vi.fn();
  proto.hasPointerCapture = vi.fn(() => false);
  // Deterministic viewport for clamp math.
  Object.defineProperty(window, "innerWidth", { value: 1200, configurable: true });
  Object.defineProperty(window, "innerHeight", { value: 800, configurable: true });
});

afterEach(() => {
  cleanup();
  vi.useRealTimers();
});

afterAll(() => {
  proto.setPointerCapture = ORIG.setPointerCapture;
  proto.releasePointerCapture = ORIG.releasePointerCapture;
  proto.hasPointerCapture = ORIG.hasPointerCapture;
  Object.defineProperty(window, "matchMedia", {
    writable: true,
    configurable: true,
    value: ORIG.matchMedia,
  });
});

function mountReduced(reduce: boolean) {
  // Drive usePrefersReducedMotion via matchMedia.
  Object.defineProperty(window, "matchMedia", {
    writable: true,
    configurable: true,
    value: (q: string) => ({
      matches: reduce && q.includes("reduce"),
      media: q,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      addListener: vi.fn(),
      removeListener: vi.fn(),
      dispatchEvent: vi.fn(),
      onchange: null,
    }),
  });
  return render(
    <MemoryRouter initialEntries={["/"]}>
      <Routes>
        <Route path="*" element={<PenguinMascot />} />
        <Route path="/home" element={<div>PROJECT HOME</div>} />
      </Routes>
    </MemoryRouter>,
  );
}

function mount() {
  return mountReduced(false);
}

describe("PenguinMascot (SPR-12 M3)", () => {
  it("lone single-click floats the project tab AFTER the ~250ms window (one floating ProjectTree panel)", () => {
    mount();
    expect(s().panels[PROJECT_TREE_PANEL_ID]).toBeUndefined();
    fireEvent.click(screen.getByTestId("penguin-mascot"));
    // Float is DEFERRED: nothing yet (a double-click could still cancel it).
    expect(
      s().panels[PROJECT_TREE_PANEL_ID],
      "the float must be deferred, not fire synchronously on the first click",
    ).toBeUndefined();
    // Elapse the click-vs-doubleclick window → the deferred float fires.
    act(() => {
      vi.advanceTimersByTime(300);
    });
    const panel = s().panels[PROJECT_TREE_PANEL_ID];
    expect(panel).toBeDefined();
    expect(panel.kind).toBe("ProjectTree");
    expect(panel.mode).toBe("floating");
    expect(s().floatingIds).toContain(PROJECT_TREE_PANEL_ID);
  });

  it("flips an already-docked tree to floating instead of duplicating (after the window)", () => {
    // Pre-existing docked tree (e.g. opened elsewhere).
    s().open("ProjectTree", {}, { mode: "docked-left", id: PROJECT_TREE_PANEL_ID });
    expect(s().panels[PROJECT_TREE_PANEL_ID].mode).toBe("docked-left");
    mount();
    fireEvent.click(screen.getByTestId("penguin-mascot"));
    act(() => {
      vi.advanceTimersByTime(300);
    });
    expect(s().panels[PROJECT_TREE_PANEL_ID].mode).toBe("floating");
    // No duplicate panel created.
    const treePanels = Object.values(s().panels).filter(
      (p) => p.kind === "ProjectTree",
    );
    expect(treePanels.length).toBe(1);
  });

  it("REAL double-click opens the project AND leaves no stray floating panel (click+click+dblclick)", () => {
    mount();
    const el = screen.getByTestId("penguin-mascot");
    // A real browser double-click dispatches click, click, THEN dblclick.
    // The two clicks each (re)arm the deferred float; dblclick must cancel
    // the pending timer before it can fire, so we land on /home with NO
    // stray floating project-tree panel.
    fireEvent.click(el);
    fireEvent.click(el);
    fireEvent.doubleClick(el);
    expect(screen.getByText("PROJECT HOME")).toBeTruthy();
    expect(
      s().panels[PROJECT_TREE_PANEL_ID],
      "the pending single-click float must be cancelled by the double-click",
    ).toBeUndefined();
    // Even after the window fully elapses, the cancelled float must NOT
    // resurrect (the timer was cleared, not merely outrun).
    act(() => {
      vi.advanceTimersByTime(300);
    });
    expect(
      s().panels[PROJECT_TREE_PANEL_ID],
      "no stray panel may appear after the window elapses",
    ).toBeUndefined();
  });

  it("drag moves the mascot and an off-screen drag CLAMPS (stays reachable)", () => {
    mount();
    const el = screen.getByTestId("penguin-mascot") as HTMLButtonElement;
    // Drag far past the right + bottom edges.
    fireEvent.pointerDown(el, { pointerId: 1, clientX: 88, clientY: 700 });
    fireEvent.pointerMove(el, { pointerId: 1, clientX: 100000, clientY: 100000 });
    fireEvent.pointerUp(el, { pointerId: 1 });

    const left = parseFloat(el.style.left);
    const top = parseFloat(el.style.top);
    // clampRectToViewport keeps >= 80px reachable: x <= innerWidth - 80,
    // y <= innerHeight - 80. So the mascot can't be lost off-screen.
    expect(left).toBeLessThanOrEqual(1200 - 80);
    expect(top).toBeLessThanOrEqual(800 - 80);
    // And it actually moved toward the far corner (not stuck at start).
    expect(left).toBeGreaterThan(88);
    expect(top).toBeGreaterThan(700);
  });

  it("drag past the top-left also clamps (never negative off-screen)", () => {
    mount();
    const el = screen.getByTestId("penguin-mascot") as HTMLButtonElement;
    fireEvent.pointerDown(el, { pointerId: 1, clientX: 88, clientY: 700 });
    fireEvent.pointerMove(el, { pointerId: 1, clientX: -100000, clientY: -100000 });
    fireEvent.pointerUp(el, { pointerId: 1 });
    const left = parseFloat(el.style.left);
    const top = parseFloat(el.style.top);
    // y is clamped to >= 0; x is clamped to >= 80 - width (so >= 80px of the
    // mascot stays on-screen on the left edge too).
    expect(top).toBeGreaterThanOrEqual(0);
    expect(left).toBeGreaterThanOrEqual(80 - 64);
  });

  it("a drag does NOT also float the tab (click suppressed after a move)", () => {
    mount();
    const el = screen.getByTestId("penguin-mascot") as HTMLButtonElement;
    fireEvent.pointerDown(el, { pointerId: 1, clientX: 88, clientY: 700 });
    fireEvent.pointerMove(el, { pointerId: 1, clientX: 300, clientY: 400 });
    fireEvent.pointerUp(el, { pointerId: 1 });
    // A real drag fires a click on pointerup; our guard must swallow it.
    fireEvent.click(el);
    expect(s().panels[PROJECT_TREE_PANEL_ID]).toBeUndefined();
  });

  it("idle wander animates by default but is STILLED under prefers-reduced-motion", () => {
    // Default: the wander class is present (the mascot is alive).
    const { container: live } = mountReduced(false);
    expect(
      live.querySelector(".penguin-mascot-wander"),
      "the wander class should be present when motion is allowed",
    ).toBeTruthy();
    cleanup();
    // Reduced-motion: the wander class is removed (JS guard), and the CSS
    // guard (animations.css) zeroes any residual animation.
    const { container: still } = mountReduced(true);
    expect(
      still.querySelector(".penguin-mascot-wander"),
      "the wander class must be removed under prefers-reduced-motion",
    ).toBeNull();
  });
});

/**
 * SPR-06 M5 — the AUTONOMOUS waddler. The mascot walks itself around the
 * viewport on a chained timeout (not a rAF loop). Each claim asserted:
 *  - by default a roam leg fires after the settle delay, MOVES the mascot,
 *    and stays clamped on-screen (bounded);
 *  - mid-stroll the foot-bob `werner-waddle` rides the bob span, then clears
 *    when the leg ends (he walks, then rests);
 *  - under prefers-reduced-motion he NEVER roams (position is the initial
 *    seed even after a long elapse) — static, still clickable;
 *  - the roam never fights a drag (a drag in flight pauses it).
 */
describe("PenguinMascot SPR-06 — autonomous roam", () => {
  it("strolls to a new on-screen spot by itself, bounded to the viewport", () => {
    const { container } = mount();
    const el = screen.getByTestId("penguin-mascot") as HTMLButtonElement;
    const startLeft = parseFloat(el.style.left);
    const startTop = parseFloat(el.style.top);
    // Settle (1800ms) → first leg begins: position is retargeted + the foot
    // bob is on while walking.
    act(() => {
      vi.advanceTimersByTime(1900);
    });
    const movedLeft = parseFloat(el.style.left);
    const movedTop = parseFloat(el.style.top);
    expect(
      movedLeft !== startLeft || movedTop !== startTop,
      "the mascot should have walked to a new spot on its own",
    ).toBe(true);
    expect(el.style.transition).toContain("left");
    expect(container.querySelector(".werner-waddle")).toBeTruthy();
    // Bounded: clamp keeps >= 80px reachable on every side (viewport 1200x800).
    expect(movedLeft).toBeGreaterThanOrEqual(80 - 64);
    expect(movedLeft).toBeLessThanOrEqual(1200 - 80);
    expect(movedTop).toBeGreaterThanOrEqual(0);
    expect(movedTop).toBeLessThanOrEqual(800 - 80);
    // Leg ends (2600ms stroll) → bob clears + transition drops (so a drag
    // stays instant), and he rests before the next leg.
    act(() => {
      vi.advanceTimersByTime(2700);
    });
    expect(container.querySelector(".werner-waddle")).toBeNull();
    expect(el.style.transition).toBe("");
  });

  it("does NOT roam under prefers-reduced-motion (stays at the seed, still clickable)", () => {
    mountReduced(true);
    const el = screen.getByTestId("penguin-mascot") as HTMLButtonElement;
    const startLeft = parseFloat(el.style.left);
    const startTop = parseFloat(el.style.top);
    // Elapse well past several roam cycles — nothing should move.
    act(() => {
      vi.advanceTimersByTime(30000);
    });
    expect(parseFloat(el.style.left)).toBe(startLeft);
    expect(parseFloat(el.style.top)).toBe(startTop);
    // Still a clickable control (the float still fires on a lone click).
    fireEvent.click(el);
    act(() => {
      vi.advanceTimersByTime(300);
    });
    expect(s().panels[PROJECT_TREE_PANEL_ID]).toBeDefined();
  });

  it("a drag pauses the roam (no stroll transition fights the pointer)", () => {
    mount();
    const el = screen.getByTestId("penguin-mascot") as HTMLButtonElement;
    fireEvent.pointerDown(el, { pointerId: 1, clientX: 88, clientY: 700 });
    // pointerDown must have cleared any scheduled/active stroll transition.
    expect(el.style.transition).toBe("");
    fireEvent.pointerMove(el, { pointerId: 1, clientX: 300, clientY: 400 });
    // Mid-drag the transition stays empty (the drag owns the position 1:1).
    expect(el.style.transition).toBe("");
    fireEvent.pointerUp(el, { pointerId: 1 });
  });
});
