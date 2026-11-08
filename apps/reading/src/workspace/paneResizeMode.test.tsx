/**
 * paneResizeMode.test.tsx — SPR-01 M4 acceptance (R8/R9), flag ON.
 *
 * The page's acceptance criteria, verbatim:
 *   - 0.05 nudge, clamp at 0.1/0.9, Esc restores the exact previous tree
 *     (deep-equal), Enter commits;
 *   - the mode bar is absent in default mode and present with the pill text
 *     in RESIZE (DOM assertions);
 *   - entering RESIZE while a text field has focus is refused (S11) with no
 *     bar shown.
 * Plus the modal keyboard rules: the mode owns plain keys while active
 * (others are swallowed, the mode stays), modifier chords and the prefix
 * keep their own layers, a text field keeps its keys even mid-mode, the
 * entry binding again exits (herdr), and the horizontal column layout opens
 * the bar with its honest "nothing to nudge" line instead of nudging.
 *
 * The dispatcher-level keys (prefix+r entry through the armed prefix) are
 * covered in paneFlowKeyboard.test.tsx's fixture; this file drives the mode
 * and the store directly and the mode's own keyboard owner with real
 * KeyboardEvents.
 */
vi.hoisted(() => { try { window.localStorage.setItem("antiek.flag.pane.flow", "on"); } catch { /* storage unavailable */ } });
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, cleanup, render } from "@testing-library/react";

import { setFeatureFlag } from "../lib/featureFlags";
import { togglePaneResizeModeAt } from "./PaneFlowLayout";
import { COMPANION_PANE, CORE_PANE } from "./paneFlowGeometry";
import PaneModeBar from "./PaneModeBar";
import { usePaneResizeMode } from "./paneResizeMode";
import { disablePersistence, useWorkspace } from "./WorkspaceStore";
import { useWindows } from "./windowsStore";

const ws = () => useWorkspace.getState();
const mode = () => usePaneResizeMode.getState();

function key(target: EventTarget, k: string, init: KeyboardEventInit = {}): KeyboardEvent {
  const e = new KeyboardEvent("keydown", { key: k, bubbles: true, cancelable: true, ...init });
  act(() => {
    target.dispatchEvent(e);
  });
  return e;
}

beforeEach(() => {
  window.localStorage.clear();
  setFeatureFlag("pane.flow", true); // reset() re-reads the flag at call time
  disablePersistence();
  useWindows.getState().reset();
  useWorkspace.getState().reset();
  // A two-pane tiled layout: x-split 0.5 [core | companion].
  ws().setPaneArrangement("tiled");
  document.body.tabIndex = -1;
  act(() => {
    document.body.focus();
  });
});

afterEach(() => {
  usePaneResizeMode.getState().reset();
  cleanup();
  useWindows.getState().reset();
  useWorkspace.getState().reset();
  vi.useRealTimers();
});

describe("the RESIZE mode (R8 modal path)", () => {
  it("nudges the focused pane's nearest split by 0.05 and clamps at the packet's bounds", () => {
    expect(mode().enter(COMPANION_PANE)).toBe(true);
    const base = ws().paneTiles;
    expect(base?.kind).toBe("split");
    // companion is the SECOND child of the x split: growing it shrinks the ratio.
    expect(mode().nudge("x", 0.05)).toBe(true);
    let tiles = ws().paneTiles;
    expect(tiles?.kind === "split" && tiles.ratio).toBeCloseTo(0.45, 10);
    for (let i = 0; i < 30; i++) mode().nudge("x", 0.05);
    tiles = ws().paneTiles;
    expect(tiles?.kind === "split" && tiles.ratio).toBe(0.1);
    for (let i = 0; i < 30; i++) mode().nudge("x", -0.05);
    tiles = ws().paneTiles;
    expect(tiles?.kind === "split" && tiles.ratio).toBe(0.9);
  });

  it("Esc restores the exact previous tree (deep-equal); Enter commits", () => {
    const before = ws().paneTiles;
    mode().enter(COMPANION_PANE);
    mode().nudge("x", 0.05);
    mode().nudge("y", 0.05); // no y ancestor: a no-op, but the mode tracks it
    expect(ws().paneTiles).not.toEqual(before);
    expect(mode().exit(false)).toBe(true);
    expect(ws().paneTiles).toEqual(before);
    expect(mode().active).toBe(false);
    // Enter (commit) keeps the resized tree.
    mode().enter(COMPANION_PANE);
    mode().nudge("x", -0.05);
    const resized = ws().paneTiles;
    expect(mode().exit(true)).toBe(true);
    expect(ws().paneTiles).toEqual(resized);
    expect(ws().paneTiles).not.toEqual(before);
  });

  it("refuses to enter from a text field (S11) — no mode, no bar", () => {
    render(<PaneModeBar />);
    const input = document.createElement("input");
    document.body.appendChild(input);
    act(() => {
      input.focus();
    });
    const e = new KeyboardEvent("keydown", { key: "r", bubbles: true, cancelable: true });
    act(() => {
      input.dispatchEvent(e);
    });
    expect(togglePaneResizeModeAt(e)).toBe(false);
    expect(mode().active).toBe(false);
    expect(document.querySelector("[data-pane-mode-bar]")).toBeNull();
    input.remove();
  });

  it("refuses in the legacy arrangement and while zoomed", () => {
    ws().setPaneArrangement("legacy");
    expect(mode().enter(CORE_PANE)).toBe(false);
    ws().setPaneArrangement("tiled");
    ws().togglePaneZoom(CORE_PANE);
    expect(mode().enter(CORE_PANE)).toBe(false);
    ws().restorePaneZoom();
  });

  it("the horizontal column layout opens the bar with its honest notice and nudges nothing", () => {
    ws().setPaneArrangement("horizontal");
    expect(mode().enter(COMPANION_PANE)).toBe(true);
    expect(mode().columns).toBe(true);
    const tiles = ws().paneTiles;
    expect(mode().nudge("x", 0.05)).toBe(false);
    expect(ws().paneTiles).toBe(tiles);
    render(<PaneModeBar />);
    expect(document.querySelector("[data-pane-mode-bar]")!.textContent).toMatch(/Columns are measured/);
  });

  it("owns plain keys while active: h/j/k/l and arrows nudge, Enter commits, Esc restores, the rest are swallowed", () => {
    mode().enter(COMPANION_PANE);
    expect(key(document.body, "l").defaultPrevented).toBe(true);
    let tiles = ws().paneTiles;
    expect(tiles?.kind === "split" && tiles.ratio).toBeCloseTo(0.45, 10);
    key(document.body, "ArrowLeft");
    tiles = ws().paneTiles;
    expect(tiles?.kind === "split" && tiles.ratio).toBeCloseTo(0.5, 10);
    // An unrelated plain key is swallowed and the mode stays.
    expect(key(document.body, "n").defaultPrevented).toBe(true);
    expect(mode().active).toBe(true);
    // A modifier chord is NOT the mode's — it passes through unconsumed.
    expect(key(document.body, "l", { ctrlKey: true, altKey: true }).defaultPrevented).toBe(false);
    expect(mode().active).toBe(true);
    // Esc restores and exits.
    const before = ws().paneTiles;
    key(document.body, "j"); // nudge so restore has something to undo
    key(document.body, "Escape");
    expect(mode().active).toBe(false);
    expect(ws().paneTiles).not.toBe(before);
  });

  it("the entry binding again (plain r) exits committing; a text field keeps its keys mid-mode", () => {
    mode().enter(COMPANION_PANE);
    key(document.body, "l");
    const resized = ws().paneTiles;
    key(document.body, "r");
    expect(mode().active).toBe(false);
    expect(ws().paneTiles).toEqual(resized);
    // Mid-mode, a focused text field's keys are the field's (no swallow).
    mode().enter(COMPANION_PANE);
    const input = document.createElement("input");
    document.body.appendChild(input);
    act(() => {
      input.focus();
    });
    expect(key(input, "h").defaultPrevented).toBe(false);
    expect(mode().active).toBe(true);
    input.remove();
  });
});

describe("the mode bar (R9)", () => {
  it("is absent in the default mode and shows the RESIZE pill with key hints in the mode", () => {
    const view = render(<PaneModeBar />);
    expect(document.querySelector("[data-pane-mode-bar]")).toBeNull();
    mode().enter(COMPANION_PANE);
    view.rerender(<PaneModeBar />);
    const bar = document.querySelector("[data-pane-mode-bar]")!;
    expect(bar).not.toBeNull();
    expect(bar.textContent).toContain("Resize");
    expect(bar.textContent).toContain("h/l width");
    expect(bar.textContent).toContain("Esc restores");
    mode().exit(true);
    view.rerender(<PaneModeBar />);
    expect(document.querySelector("[data-pane-mode-bar]")).toBeNull();
  });
});
