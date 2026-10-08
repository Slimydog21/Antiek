/**
 * paneArrangements.flow.test.tsx — SPR-01 M6 acceptance, flag ON.
 *
 * The acceptance criteria from sprint-01-leader-key-tiling.html M6, through
 * the real store and the real dispatcher (installShortcuts):
 *
 *   - jump restores order+tiles exactly (deep-equal), zoom cleared (R12)
 *   - prefix+tab / prefix+shift+tab cycle the EXISTING arrangements, empty
 *     slots skip
 *   - prefix+ctrl+tab is the last-used arrangement, returning after two hops
 *   - a preset target whose host is gone is dropped on load with an honesty
 *     event (console.warn), never substituted (S01/S09)
 *   - move-and-follow (shift+digit) carries the focused pane and lands on it
 *   - slots isolate per account project
 *   - the blob survives a reload (reset re-hydrates it); an unknown version
 *     is discarded whole
 *
 * The flag is set before any import reads the keymap (vi.hoisted runs
 * first) — the paneFlowKeyboard.test.tsx idiom.
 */
vi.hoisted(() => { try { window.localStorage.setItem("antiek.flag.pane.flow", "on"); } catch { /* storage unavailable */ } });
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { setFeatureFlag } from "../lib/featureFlags";
import { accountStorageKey, setWorkspaceOwner } from "../lib/accountWorkspaceOwner";
import { prefixState } from "../components/hotkeys/prefixState";
import { KEYMAP, validateKeymap } from "../components/hotkeys/keymap";
import type { PaneTarget } from "./panel.types";
import { readPaneArrangements, writeTabProject } from "./persistence";
import { createActionHandlers, installShortcuts } from "./shortcuts";
import { keyInit } from "./keymapTestKit";
import { disablePersistence, enablePersistence, useWorkspace } from "./WorkspaceStore";
import { useWindows } from "./windowsStore";

const WIN_A: PaneTarget = { kind: "window", id: "w-a" };
const WIN_B: PaneTarget = { kind: "window", id: "w-b" };

const ws = () => useWorkspace.getState();
const slots = (project = "default") => ws().paneSlots[project];

function press(target: EventTarget, spec: string, extra: KeyboardEventInit = {}): KeyboardEvent {
  const e = new KeyboardEvent("keydown", { ...keyInit(spec, "mac"), ...extra });
  target.dispatchEvent(e);
  return e;
}

let uninstall: (() => void) | null = null;

beforeEach(() => {
  vi.useFakeTimers();
  window.localStorage.clear();
  setFeatureFlag("pane.flow", true); // reset() re-reads the flag at call time
  disablePersistence();
  setWorkspaceOwner("arr-flow");
  useWindows.getState().reset();
  useWorkspace.getState().reset();
  prefixState.disarm();
  uninstall = installShortcuts((() => {}) as never);
});

afterEach(() => {
  uninstall?.();
  uninstall = null;
  prefixState.disarm();
  setWorkspaceOwner(null);
  vi.useRealTimers();
});

/** Two open windows on top of core + companion: order [core, companion, a, b]. */
function openTwoWindows() {
  useWindows.getState().open("u1:non-book-control", {}, { id: "w-a" });
  useWindows.getState().open("u1:non-book-control", {}, { id: "w-b" });
}

describe("M6 acceptance: jump, cycle, last-used, move", () => {
  it("jump restores order+tiles exactly (deep-equal) and clears zoom", () => {
    openTwoWindows();
    // Arrange slot 1 distinctively: window A leads, tiled.
    ws().reorderPane(WIN_A, -1);
    ws().reorderPane(WIN_A, -1);
    ws().reorderPane(WIN_A, -1);
    ws().setPaneArrangement("tiled");
    const savedOrder = ws().paneOrder;
    const savedTiles = ws().paneTiles;
    expect(savedOrder[0]).toEqual(WIN_A);

    // Land on slot 3 (empty: the current view is saved as 3), rearrange
    // there, zoom in — then jump back.
    expect(ws().jumpPaneArrangement("3")).toBe(true);
    expect(slots()?.current).toBe("3");
    ws().setPaneArrangement("horizontal");
    ws().reorderPane(WIN_A, 1);
    ws().togglePaneZoom(WIN_B);
    expect(ws().paneZoom).toEqual(WIN_B);

    expect(ws().jumpPaneArrangement("1")).toBe(true);
    expect(ws().paneOrder).toEqual(savedOrder);
    expect(ws().paneTiles).toEqual(savedTiles);
    expect(ws().paneArrangement).toBe("tiled");
    expect(ws().paneZoom).toBeNull(); // R12: an arrangement change clears zoom
  });

  it("next/previous skip empty slots; last-used returns after two hops", () => {
    openTwoWindows();
    ws().jumpPaneArrangement("4");
    ws().jumpPaneArrangement("9");
    // Existing slots: 1, 4, 9. From 9, next wraps to 1; prev goes to 4.
    expect(ws().cyclePaneArrangement(1)).toBe(true);
    expect(slots()?.current).toBe("1");
    expect(ws().cyclePaneArrangement(-1)).toBe(true);
    expect(slots()?.current).toBe("9");
    // Last-used after two hops: 9 → 1 → 9 leaves last = 1; last-used → 1 …
    // …and its own hop moves last to 9, so a second last-used returns to 9.
    expect(ws().jumpToLastPaneArrangement()).toBe(true);
    expect(slots()?.current).toBe("1");
    expect(ws().jumpToLastPaneArrangement()).toBe(true);
    expect(slots()?.current).toBe("9");
  });

  it("a preset target whose host is gone is dropped with an honesty event, never substituted", () => {
    openTwoWindows();
    ws().jumpPaneArrangement("2"); // slot 1's preset holds [core, companion, a, b]
    useWindows.getState().close("w-b"); // the host goes away while slot 1 is parked
    const warn = vi.spyOn(console, "warn").mockImplementation(() => {});
    expect(ws().jumpPaneArrangement("1")).toBe(true);
    expect(warn).toHaveBeenCalledWith(expect.stringContaining("window:w-b"));
    expect(ws().paneOrder.map((t) => t.kind === "window" ? t.id : t.kind)).toEqual(["core", "companion", "w-a"]);
  });

  it("move-and-follow carries the focused pane into the slot and lands on it", () => {
    openTwoWindows();
    ws().setPaneFocus(WIN_A);
    expect(ws().moveFocusedPaneToArrangement("5")).toBe(true);
    expect(slots()?.current).toBe("5");
    // The view is slot 5's: the moved window (focus follows), plus the
    // still-unassigned hosts. Slot 1's preset no longer holds window A.
    expect(ws().paneOrder).toContainEqual(WIN_A);
    expect(ws().paneFocus).toEqual(WIN_A);
    expect(slots()?.presets["1"]?.order).not.toContainEqual(WIN_A);
    expect(slots()?.presets["5"]?.order).toContainEqual(WIN_A);
    // And slot 1's view no longer shows it.
    ws().jumpPaneArrangement("1");
    expect(ws().paneOrder).not.toContainEqual(WIN_A);
  });

  it("slots isolate per account project", () => {
    openTwoWindows();
    ws().jumpPaneArrangement("7");
    expect(slots("default")?.presets["7"]).toBeTruthy();
    writeTabProject("proj-two");
    // A fresh project has no slots; the default project's stay put.
    expect(slots("proj-two")).toBeUndefined();
    expect(ws().jumpPaneArrangement("2")).toBe(true);
    expect(slots("proj-two")?.current).toBe("2");
    expect(slots("default")?.current).toBe("7");
    writeTabProject("default");
    expect(slots("default")?.current).toBe("7");
  });
});

describe("M6 acceptance: persistence", () => {
  it("the blob survives a reload (reset re-hydrates it), deep-equal", () => {
    enablePersistence();
    openTwoWindows();
    ws().setPaneArrangement("tiled");
    ws().jumpPaneArrangement("6");
    ws().jumpPaneArrangement("1");
    vi.advanceTimersByTime(300); // the debounced write
    const persisted = readPaneArrangements();
    expect(persisted["default"]).toBeTruthy();
    useWorkspace.getState().reset(); // the reload: state re-reads the blob
    expect(ws().paneSlots).toEqual(persisted);
    disablePersistence();
  });

  it("an unknown schemaVersion is discarded whole on read", () => {
    enablePersistence();
    ws().jumpPaneArrangement("2");
    vi.advanceTimersByTime(300);
    const key = accountStorageKey("antiek.workspace.pane-arrangements")!;
    window.localStorage.setItem(key, JSON.stringify({ schemaVersion: 99, projects: {} }));
    expect(readPaneArrangements()).toEqual({});
    disablePersistence();
  });
});

describe("the digit keys through the real dispatcher", () => {
  it("prefix+digit jumps; ctrl+alt+digit jumps; the jump lands in the store", () => {
    openTwoWindows();
    press(document.body, "ctrl+b");
    press(document.body, "2");
    expect(slots()?.current).toBe("2");
    press(document.body, "ctrl+alt+4");
    expect(slots()?.current).toBe("4");
    expect(slots()?.last).toBe("2");
  });

  it("prefix+shift+digit moves the focused pane and follows", () => {
    openTwoWindows();
    ws().setPaneFocus(WIN_B);
    press(document.body, "ctrl+b");
    press(document.body, "shift+3");
    expect(slots()?.current).toBe("3");
    expect(slots()?.presets["3"]?.order).toContainEqual(WIN_B);
    expect(ws().paneOrder).toContainEqual(WIN_B);
  });

  it("prefix+tab / prefix+shift+tab cycle existing arrangements; prefix+ctrl+tab is last-used", () => {
    openTwoWindows();
    ws().jumpPaneArrangement("5");
    ws().jumpPaneArrangement("1");
    press(document.body, "ctrl+b");
    press(document.body, "tab"); // next existing from 1 → 5
    expect(slots()?.current).toBe("5");
    press(document.body, "ctrl+b");
    press(document.body, "shift+tab"); // previous → 1
    expect(slots()?.current).toBe("1");
    press(document.body, "ctrl+b");
    press(document.body, "ctrl+tab"); // last-used → 5
    expect(slots()?.current).toBe("5");
  });

  it("a digit pressed inside a text field stays the field's (outside-text scope)", () => {
    openTwoWindows();
    const input = document.createElement("input");
    document.body.appendChild(input);
    input.focus();
    press(input, "ctrl+b");
    press(input, "3");
    expect(slots()?.current ?? "1").toBe("1"); // no slots created, no jump
    input.remove();
  });

  it("the flow keymap table passes the census guard with handlers to match", () => {
    const handlerIds = Object.keys(createActionHandlers((() => {}) as never));
    expect(validateKeymap(KEYMAP, handlerIds)).toEqual([]);
    // The digits left RESERVED_FOR_LATER: the rows own them now.
    expect(KEYMAP.filter((r) => r.prefixKey === "2").map((r) => r.action)).toContain("pane.arrangement2");
    expect(KEYMAP.filter((r) => r.chord === "ctrl+alt+2").map((r) => r.action)).toContain("pane.arrangement2");
    expect(KEYMAP.filter((r) => r.prefixKey === "shift+2").map((r) => r.action)).toContain("pane.moveToArrangement2");
  });
});
