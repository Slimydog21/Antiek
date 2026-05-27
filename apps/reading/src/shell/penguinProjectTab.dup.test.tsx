/**
 * penguinProjectTab.dup.test.tsx — SPR-05 M4 regression: the Research "+"
 * (now the Penguin mascot) yields EXACTLY ONE project tab, never two.
 *
 * ── THE BUG (reproduced, then pinned) ──────────────────────────────────
 * The operator reported, PRE-SPR-12, that in the Research workflow clicking
 * the "+" surfaced TWO project columns/tabs. The root cause class was a
 * non-idempotent "append a project tab" path firing twice (e.g. a rail "+"
 * button whose handler appended a fresh panel on every click instead of
 * focusing the existing one).
 *
 * REPRODUCTION RESULT: NOT reproducible on this tree. SPR-12 (a) removed the
 * old NavRail "+ project / Project tree" button and (b) replaced it with the
 * Penguin mascot, whose float path is idempotent by construction:
 *   - the project tree always uses the ONE stable id PROJECT_TREE_PANEL_ID
 *     ("shortcuts:projecttree");
 *   - WorkspaceStore.open() (WorkspaceStore.ts:118-121) returns the snapshot
 *     UNCHANGED when a panel with that id already exists — it focuses, never
 *     duplicates;
 *   - PenguinMascot.floatProjectTab() (PenguinMascot.tsx:127-137) further
 *     guards with `treeExists` → setMode(...,"floating") instead of open(),
 *     and the single-click float is deferred behind a ~250ms timer so a
 *     repeated click can't stack panels.
 * So the specific duplication is already gone. Rather than "fix" a bug we
 * cannot reproduce (which would be dishonest — rigor #1), we PIN the fixed
 * behaviour here so a future regression (a second non-idempotent project-tab
 * opener) fails this test.
 *
 * Load-bearing assertions:
 *   1. Many Penguin single-clicks (each elapsing its window) → exactly ONE
 *      ProjectTree panel (the Research "+" yields one tab).
 *   2. The same id opened via the ⌘B docked path AND then floated via the
 *      Penguin is still ONE panel (the two openers share the id; they don't
 *      stack).
 *   3. Other surfaces are unaffected: opening a DIFFERENT panel kind/id
 *      coexists with the one project tree (we never collapsed unrelated
 *      panels). The Penguin only ever touches the project-tree id.
 */
import { afterAll, afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";

import { PenguinMascot, PROJECT_TREE_PANEL_ID } from "./PenguinMascot";
import { useWorkspace } from "../workspace/WorkspaceStore";

const s = () => useWorkspace.getState();

const proto = window.HTMLElement.prototype as unknown as Record<string, unknown>;
const ORIG = {
  setPointerCapture: proto.setPointerCapture,
  releasePointerCapture: proto.releasePointerCapture,
  hasPointerCapture: proto.hasPointerCapture,
  matchMedia: (window as unknown as { matchMedia?: unknown }).matchMedia,
};

beforeEach(() => {
  s().reset();
  vi.useFakeTimers();
  proto.setPointerCapture = vi.fn();
  proto.releasePointerCapture = vi.fn();
  proto.hasPointerCapture = vi.fn(() => false);
  Object.defineProperty(window, "innerWidth", { value: 1200, configurable: true });
  Object.defineProperty(window, "innerHeight", { value: 800, configurable: true });
  // matchMedia for usePrefersReducedMotion (default: motion allowed).
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

function mountPenguin() {
  return render(
    <MemoryRouter initialEntries={["/"]}>
      <Routes>
        <Route path="*" element={<PenguinMascot />} />
        <Route path="/home" element={<div>PROJECT HOME</div>} />
      </Routes>
    </MemoryRouter>,
  );
}

function treePanelCount(): number {
  return Object.values(s().panels).filter((p) => p.kind === "ProjectTree").length;
}

describe("Research + (Penguin) yields exactly one project tab (SPR-05 M4 regression)", () => {
  it("repeated single-clicks float the project tree ONCE, never two", () => {
    mountPenguin();
    const el = screen.getByTestId("penguin-mascot");

    // Three separate single-clicks, each allowed to elapse its float window.
    for (let i = 0; i < 3; i++) {
      fireEvent.click(el);
      act(() => {
        vi.advanceTimersByTime(300);
      });
    }

    // Exactly ONE ProjectTree panel exists (the bug would have stacked them).
    expect(treePanelCount()).toBe(1);
    const panel = s().panels[PROJECT_TREE_PANEL_ID];
    expect(panel).toBeDefined();
    expect(panel.mode).toBe("floating");
    // And it appears once in the floating array, not duplicated.
    const floatingHits = s().floatingIds.filter((id) => id === PROJECT_TREE_PANEL_ID);
    expect(floatingHits.length).toBe(1);
  });

  it("the ⌘B docked opener and the Penguin float share the one id (no second tab)", () => {
    // The keyboard path opens the tree docked-left with the SAME stable id.
    s().open("ProjectTree", {}, { mode: "docked-left", id: PROJECT_TREE_PANEL_ID });
    expect(treePanelCount()).toBe(1);

    // Now the Penguin floats it — it flips the existing panel, never adds one.
    mountPenguin();
    fireEvent.click(screen.getByTestId("penguin-mascot"));
    act(() => {
      vi.advanceTimersByTime(300);
    });
    expect(treePanelCount()).toBe(1);
    expect(s().panels[PROJECT_TREE_PANEL_ID].mode).toBe("floating");
  });

  it("an unrelated panel coexists — the Penguin only touches the project-tree id (other surfaces unaffected)", () => {
    // A different surface's panel is open (e.g. a Trajectory float).
    const otherId = s().open("Trajectory", { id: "nvda" }, { mode: "floating", title: "NVDA" });
    expect(s().panels[otherId]).toBeDefined();

    mountPenguin();
    fireEvent.click(screen.getByTestId("penguin-mascot"));
    act(() => {
      vi.advanceTimersByTime(300);
    });

    // The project tree was added once; the unrelated panel is untouched.
    expect(treePanelCount()).toBe(1);
    expect(s().panels[otherId]).toBeDefined();
    expect(s().panels[otherId].kind).toBe("Trajectory");
  });
});
