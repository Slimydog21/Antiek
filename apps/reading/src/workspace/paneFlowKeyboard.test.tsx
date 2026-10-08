// Landing: these cases exercise the pane-flow arrangement, which is behind
// antiek.flag.pane.flow (default OFF). The flag is set before any import
// reads the keymap (vi.hoisted runs first).
vi.hoisted(() => { try { window.localStorage.setItem("antiek.flag.pane.flow", "on"); } catch { /* storage unavailable */ } });
import { act, cleanup, fireEvent, render } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ACTIONS, currentPlatform, KEYMAP, validateKeymap } from "../components/hotkeys/keymap";
import { prefixState } from "../components/hotkeys/prefixState";
import { WindowsLayer } from "../components/windows/WindowsLayer";
import { PaneFlowLayout, usePaneFlowFrame } from "./PaneFlowLayout";
import { COMPANION_PANE, CORE_PANE, paneKey } from "./paneFlowGeometry";
import type { PaneTarget } from "./panel.types";
import { installShortcuts } from "./shortcuts";
import { disablePersistence, useWorkspace } from "./WorkspaceStore";
import { useWindows } from "./windowsStore";

vi.mock("./useViewportTier", () => ({ useViewportTier: () => "xl" }));
vi.mock("./usePrefersReducedMotion", () => ({ usePrefersReducedMotion: () => true }));

function ControlledHost({ target }: { target: PaneTarget }) {
  const frame = usePaneFlowFrame(target);
  return <div ref={frame.ref} data-pane-host={frame.hostKey} hidden={frame.hidden || undefined}
    style={frame.style} tabIndex={-1}>
    <button data-control-button onKeyDown={(event) => {
      if (event.key === "ArrowLeft") event.preventDefault();
    }}>Controlled child</button>
    <textarea aria-label={`Controlled ${paneKey(target)} input`} />
  </div>;
}

function node(selector: string): HTMLElement {
  const result = document.querySelector(selector);
  if (!(result instanceof HTMLElement)) throw new Error(`Missing controlled DOM target ${selector}`);
  return result;
}

function press(target: HTMLElement, key: string, code: string, extra: KeyboardEventInit = {}): KeyboardEvent {
  const event = new KeyboardEvent("keydown", { key, code, ctrlKey: true, altKey: true,
    bubbles: true, cancelable: true, ...extra });
  act(() => { target.dispatchEvent(event); });
  return event;
}

let dispose: (() => void) | null = null;
let width = 1000;
const resize = new Set<() => void>();

beforeEach(() => {
  vi.useFakeTimers();
  disablePersistence();
  useWindows.getState().reset();
  useWorkspace.getState().reset();
  useWorkspace.getState().setLayoutPreset("omarchy-inset");
  useWorkspace.getState().setPaneArrangement("horizontal");
  prefixState.disarm();
  width = 1000; resize.clear();
  vi.spyOn(Element.prototype, "clientWidth", "get").mockImplementation(() => width);
  vi.spyOn(Element.prototype, "clientHeight", "get").mockImplementation(() => 700);
  vi.spyOn(Element.prototype, "getClientRects").mockImplementation(function (this: Element): DOMRectList {
    if (!this.isConnected || this.closest("[hidden], [inert]") || width === 0) {
      return { length: 0, item: () => null, *[Symbol.iterator]() {} } as unknown as DOMRectList;
    }
    const rect = new DOMRect(0, 0, width, 700);
    return { 0: rect, length: 1, item: (index: number) => index === 0 ? rect : null, *[Symbol.iterator]() { yield rect; } } as unknown as DOMRectList;
  });
  vi.stubGlobal("ResizeObserver", class implements ResizeObserver {
    private measure: () => void;
    constructor(callback: ResizeObserverCallback) { this.measure = () => callback([], this); }
    observe() { resize.add(this.measure); this.measure(); }
    unobserve() {}
    disconnect() { resize.delete(this.measure); }
  });
  useWindows.getState().open("u1:non-book-control", { controlled: true }, { id: "control:a" });
  useWindows.getState().open("u1:non-book-control", { controlled: true }, { id: "control:b" });
  render(<PaneFlowLayout><ControlledHost target={CORE_PANE} /><ControlledHost target={COMPANION_PANE} /><WindowsLayer /></PaneFlowLayout>);
  act(() => { vi.runOnlyPendingTimers(); });
  dispose = installShortcuts(() => {});
  act(() => { node('[data-pane-host="core"]').focus(); });
});

afterEach(() => {
  dispose?.(); dispose = null;
  cleanup();
  useWindows.getState().reset();
  useWorkspace.getState().reset();
  prefixState.disarm();
  // Landing: a spy placed on the store's state object is copied into every
  // later state by zustand's set(), and main's Vitest 4 restoreAllMocks no
  // longer clears spy call history — so a toggle counted in one case leaked
  // into the next ("refuses legacy L …" ran green alone, red in sequence).
  vi.clearAllMocks();
  vi.restoreAllMocks(); vi.unstubAllGlobals(); vi.useRealTimers();
});

describe("actual dispatcher and connected host admission", () => {
  it("has one direct L row and complete canonical action handlers without duplicate chords", () => {
    expect(KEYMAP.filter((row) => row.chord === "ctrl+alt+l").map((row) => row.action)).toEqual(["layout.togglePreset"]);
    // REWRITTEN at landing: main declares inbox.toggle unimplemented (blockedBy
    // MS-03 M7) and binds no handler for it, so "every ACTIONS key is a
    // handler" is a packet-era assumption; the handler set is every action
    // whose rows are implemented — what createActionHandlers actually binds.
    const implemented = Object.keys(ACTIONS).filter((action) =>
      !KEYMAP.some((row) => row.action === action && row.status === "unimplemented"));
    expect(validateKeymap(KEYMAP, implemented, { platforms: ["mac", "other"] })).toEqual([]);
  });
  it("moves through core, companion and actual windows, reveals them, and refuses both edges", () => {
    const core = node('[data-pane-host="core"]');
    const companion = node('[data-pane-host="companion"]');
    const a = node('[data-workspace-window="control:a"]');
    const b = node('[data-workspace-window="control:b"]');
    const order = useWorkspace.getState().paneOrder.map(paneKey);
    expect(press(core, "ArrowLeft", "ArrowLeft").defaultPrevented).toBe(false);
    expect(press(core, "ArrowRight", "ArrowRight").defaultPrevented).toBe(true);
    expect(document.activeElement).toBe(companion);
    press(companion, "ArrowRight", "ArrowRight");
    expect(document.activeElement).toBe(a);
    expect(node("[data-pane-flow-root]").scrollLeft).toBe(500);
    press(a, "ArrowRight", "ArrowRight", { repeat: true });
    expect(document.activeElement).toBe(b);
    expect(press(b, "ArrowRight", "ArrowRight").defaultPrevented).toBe(false);
    expect(useWorkspace.getState().paneOrder.map(paneKey)).toEqual(order);
  });
  it("reorders once per admitted event while retaining actual DOM focus and descriptor geometry", () => {
    const a = node('[data-workspace-window="control:a"]');
    act(() => { a.focus(); });
    const descriptor = useWindows.getState().windows["control:a"];
    press(a, "ArrowLeft", "ArrowLeft", { shiftKey: true });
    expect(useWorkspace.getState().paneOrder.map(paneKey)).toEqual(["core", "window:control:a", "companion", "window:control:b"]);
    expect(document.activeElement).toBe(a);
    expect(useWindows.getState().windows["control:a"].rect).toEqual(descriptor.rect);
    expect(useWindows.getState().windows["control:a"].payload).toBe(descriptor.payload);
    expect(node('[data-workspace-window="control:a"]')).toBe(a);
  });
  it("preserves the actual opening-order cycle without changing pane presentation order", () => {
    const a = node('[data-workspace-window="control:a"]');
    const b = node('[data-workspace-window="control:b"]');
    const order = useWorkspace.getState().paneOrder.map(paneKey);
    act(() => { a.focus(); });
    const cycleModifiers = { altKey: false, ctrlKey: currentPlatform() !== "mac", metaKey: currentPlatform() === "mac" };
    press(a, "]", "BracketRight", cycleModifiers);
    expect(document.activeElement).toBe(b);
    press(b, "]", "BracketRight", cycleModifiers);
    expect(document.activeElement).toBe(a);
    expect(useWorkspace.getState().paneOrder.map(paneKey)).toEqual(order);
    expect(useWindows.getState().cycleOrder).toEqual(["control:a", "control:b"]);
  });
  it("keeps legacy bare/Shift arrows local and global F on the actual window owner", () => {
    act(() => { useWorkspace.getState().setPaneArrangement("legacy"); });
    const a = node('[data-workspace-window="control:a"]');
    act(() => { a.focus(); });
    const rect = useWindows.getState().windows["control:a"].rect;
    press(a, "ArrowRight", "ArrowRight", { ctrlKey: false, altKey: false });
    expect(useWindows.getState().windows["control:a"].rect.x).toBe(rect.x + 24);
    press(a, "ArrowDown", "ArrowDown", { ctrlKey: false, altKey: false, shiftKey: true });
    expect(useWindows.getState().windows["control:a"].rect.height).toBe(rect.height + 24);
    press(a, "f", "KeyF");
    expect(useWindows.getState().windows["control:a"].mode).toBe("full");
    expect(useWorkspace.getState().fullscreenPane).toBeNull();
    press(a, "f", "KeyF");
    expect(useWindows.getState().windows["control:a"].mode).toBe("floating");
    expect(useWindows.getState().windows["control:a"].rect.x).toBe(rect.x + 24);
  });
  it("returns to the connected opener after closing an actually newly admitted window", () => {
    const core = node('[data-pane-host="core"]');
    act(() => { core.focus(); useWindows.getState().open("u1:non-book-control", {}, { id: "control:opened" }); });
    act(() => { vi.runOnlyPendingTimers(); });
    const opened = node('[data-workspace-window="control:opened"]');
    expect(document.activeElement).toBe(opened);
    press(opened, "Escape", "Escape", { ctrlKey: false, altKey: false });
    expect(Object.hasOwn(useWindows.getState().windows, "control:opened")).toBe(false);
    expect(document.activeElement).toBe(core);
    expect(core.isConnected).toBe(true);
  });
  it("runs an arrow prefix after its own consumption, preserving h/l aliases", () => {
    const core = node('[data-pane-host="core"]');
    press(core, "b", "KeyB", { altKey: false });
    expect(prefixState.isArmed()).toBe(true);
    press(core, "ArrowRight", "ArrowRight", { ctrlKey: false, altKey: false });
    expect(document.activeElement).toBe(node('[data-pane-host="companion"]'));
    const companion = node('[data-pane-host="companion"]');
    press(companion, "b", "KeyB", { altKey: false });
    press(companion, "h", "KeyH", { ctrlKey: false, altKey: false });
    expect(document.activeElement).toBe(core);
    expect(prefixState.isArmed()).toBe(false);
  });
  it("refuses a prefix event already claimed before the dispatcher consumed it", () => {
    const core = node('[data-pane-host="core"]');
    press(core, "b", "KeyB", { altKey: false });
    const event = new KeyboardEvent("keydown", { key: "ArrowRight", code: "ArrowRight", bubbles: true, cancelable: true });
    event.preventDefault();
    act(() => { core.dispatchEvent(event); });
    expect(document.activeElement).toBe(core);
    expect(prefixState.isArmed()).toBe(false);
  });
  it("keeps ordinary and magic arrows in text entry without layout mutation", () => {
    const input = node('textarea[aria-label="Controlled core input"]');
    act(() => { input.focus(); });
    const order = useWorkspace.getState().paneOrder;
    expect(press(input, "ArrowRight", "ArrowRight").defaultPrevented).toBe(false);
    expect(press(input, "ArrowRight", "ArrowRight", { shiftKey: true }).defaultPrevented).toBe(false);
    expect(press(input, "l", "KeyL").defaultPrevented).toBe(false);
    expect(document.activeElement).toBe(input);
    expect(useWorkspace.getState().paneOrder).toBe(order);
  });
  it("preserves plaintext-only editing and refuses focus outside the admitted work area", () => {
    const editable = document.createElement("div"); editable.setAttribute("contenteditable", "plaintext-only"); editable.tabIndex = 0;
    node('[data-pane-host="core"]').append(editable);
    act(() => { editable.focus(); });
    expect(press(editable, "f", "KeyF").defaultPrevented).toBe(false);
    expect(useWorkspace.getState().paneZoom).toBeNull();
    const chrome = document.createElement("button"); document.body.append(chrome);
    act(() => { chrome.focus(); });
    expect(press(chrome, "f", "KeyF").defaultPrevented).toBe(false);
    expect(press(chrome, "l", "KeyL").defaultPrevented).toBe(false);
    expect(useWorkspace.getState().fullscreenPane).toBeNull();
    expect(document.activeElement).toBe(chrome);
    chrome.remove();
  });
  it("respects a child's claimed direct key and rejects an inactive event target", () => {
    const button = node('[data-pane-host="core"] [data-control-button]');
    act(() => { button.focus(); });
    press(button, "ArrowLeft", "ArrowLeft");
    expect(document.activeElement).toBe(button);
    const inactive = node('[data-pane-host="companion"]');
    expect(press(inactive, "ArrowRight", "ArrowRight").defaultPrevented).toBe(false);
    expect(document.activeElement).toBe(button);
  });
  it("refuses modal/IME/AltGraph input without substituting store focus", () => {
    const core = node('[data-pane-host="core"]');
    expect(press(core, "ArrowRight", "ArrowRight", { isComposing: true }).defaultPrevented).toBe(false);
    const altGraph = new KeyboardEvent("keydown", { key: "ArrowRight", code: "ArrowRight", ctrlKey: true, altKey: true, bubbles: true, cancelable: true });
    Object.defineProperty(altGraph, "getModifierState", { value: (modifier: string) => modifier === "AltGraph" });
    act(() => { core.dispatchEvent(altGraph); });
    expect(document.activeElement).toBe(core);
    const overlay = document.createElement("div"); overlay.setAttribute("role", "dialog"); overlay.setAttribute("aria-modal", "true");
    const button = document.createElement("button"); overlay.append(button); document.body.append(overlay);
    act(() => { button.focus(); });
    expect(press(button, "f", "KeyF").defaultPrevented).toBe(false);
    expect(useWorkspace.getState().paneZoom).toBeNull();
    overlay.remove();
  });
  it("refuses active pointer capture until actual release is observed", () => {
    const core = node('[data-pane-host="core"]');
    let captured = true;
    Object.defineProperty(core, "hasPointerCapture", { configurable: true, value: (id: number) => captured && id === 7 });
    const capture = new Event("gotpointercapture", { bubbles: true });
    Object.defineProperty(capture, "pointerId", { value: 7 });
    act(() => { core.dispatchEvent(capture); });
    expect(press(core, "ArrowRight", "ArrowRight").defaultPrevented).toBe(false);
    expect(press(core, "l", "KeyL").defaultPrevented).toBe(false);
    expect(document.activeElement).toBe(core);
    captured = false;
    expect(press(core, "ArrowRight", "ArrowRight").defaultPrevented).toBe(true);
  });
  it("SPR-01 M2: ctrl+alt+ArrowDown/Up move spatially in tiled mode, do nothing in horizontal flow, never wrap", () => {
    const a = node('[data-workspace-window="control:a"]');
    const companion = node('[data-pane-host="companion"]');
    act(() => { companion.focus(); });
    // Horizontal flow: nothing above or below — the key is not consumed.
    expect(press(companion, "ArrowDown", "ArrowDown").defaultPrevented).toBe(false);
    expect(document.activeElement).toBe(companion);
    act(() => { useWorkspace.getState().setPaneArrangement("tiled"); });
    // Dwindle with four hosts: core | (companion / (a | b)) — a and b sit below the companion.
    expect(press(companion, "ArrowDown", "ArrowDown").defaultPrevented).toBe(true);
    const below = document.activeElement;
    expect([a, node('[data-workspace-window="control:b"]')]).toContain(below);
    expect(useWorkspace.getState().paneFocus).toEqual({ kind: "window", id: (below as HTMLElement).dataset.workspaceWindow });
    expect(press(below as HTMLElement, "ArrowUp", "ArrowUp").defaultPrevented).toBe(true);
    expect(document.activeElement).toBe(companion);
    // Edge: nothing above the companion — not consumed, focus stays.
    expect(press(companion, "ArrowUp", "ArrowUp").defaultPrevented).toBe(false);
    expect(document.activeElement).toBe(companion);
    // herdr aliases through the prefix: k/j.
    press(companion, "b", "KeyB", { altKey: false });
    expect(press(companion, "j", "KeyJ", { ctrlKey: false, altKey: false }).defaultPrevented).toBe(true);
    expect(document.activeElement).not.toBe(companion);
  });
  it("SPR-01 M3: ctrl+alt+j and prefix+v flip the focused pane's split in tiled mode; horizontal flow and repeats are not consumed", () => {
    const companion = node('[data-pane-host="companion"]');
    act(() => { companion.focus(); });
    expect(press(companion, "j", "KeyJ").defaultPrevented).toBe(false); // horizontal flow: nothing to flip
    act(() => { useWorkspace.getState().setPaneArrangement("tiled"); });
    const before = useWorkspace.getState().paneTiles;
    expect(before?.kind).toBe("split");
    expect(press(companion, "j", "KeyJ").defaultPrevented).toBe(true);
    const after = useWorkspace.getState().paneTiles;
    expect(after).not.toEqual(before);
    expect(JSON.stringify(after).replace(/"axis":"[xy]"/g, "")).toBe(JSON.stringify(before).replace(/"axis":"[xy]"/g, "")); // only an axis changed
    expect(document.activeElement).toBe(companion); // focus stays on the host (R5: a layout op, not a focus op)
    expect(press(companion, "j", "KeyJ", { repeat: true }).defaultPrevented).toBe(false);
    // herdr form: prefix then v flips it back.
    press(companion, "b", "KeyB", { altKey: false });
    expect(press(companion, "v", "KeyV", { ctrlKey: false, altKey: false }).defaultPrevented).toBe(true);
    expect(useWorkspace.getState().paneTiles).toEqual(before);
  });
  it("toggles layouts and zoom without remounting real windows or accepting toggle repeats", () => {
    const a = node('[data-workspace-window="control:a"]');
    act(() => { a.focus(); });
    press(a, "l", "KeyL");
    expect(useWorkspace.getState().paneArrangement).toBe("tiled");
    expect(press(a, "l", "KeyL", { repeat: true }).defaultPrevented).toBe(false);
    press(a, "l", "KeyL");
    expect(useWorkspace.getState().paneArrangement).toBe("horizontal");
    press(a, "f", "KeyF");
    expect(useWorkspace.getState().paneZoom).toEqual({ kind: "window", id: "control:a" });
    expect(node('[data-pane-host="core"]').hidden).toBe(true);
    expect(press(a, "f", "KeyF", { repeat: true }).defaultPrevented).toBe(false);
    press(a, "f", "KeyF");
    expect(useWorkspace.getState().paneZoom).toBeNull();
    expect(node('[data-workspace-window="control:a"]')).toBe(a);
  });
  it("keeps a partially visible companion's saved view through canonical F/F and still reveals subsequent navigation", () => {
    const root = node("[data-pane-flow-root]");
    const companion = node('[data-pane-host="companion"]');
    const hosts = [node('[data-pane-host="core"]'), companion,
      node('[data-workspace-window="control:a"]'), node('[data-workspace-window="control:b"]')];
    const order = useWorkspace.getState().paneOrder;
    const tiles = useWorkspace.getState().paneTiles;
    const widths = hosts.map((host) => host.style.width);
    act(() => { companion.focus(); });
    fireEvent.scroll(root, { target: { scrollLeft: 900 } });
    expect(press(companion, "f", "KeyF").defaultPrevented).toBe(true);
    expect(useWorkspace.getState().paneZoom).toEqual(COMPANION_PANE);
    expect(press(companion, "f", "KeyF").defaultPrevented).toBe(true);
    expect(useWorkspace.getState().paneZoom).toBeNull();
    expect(root.scrollLeft).toBe(900);
    expect(document.activeElement).toBe(companion);
    expect([node('[data-pane-host="core"]'), node('[data-pane-host="companion"]'),
      node('[data-workspace-window="control:a"]'), node('[data-workspace-window="control:b"]')]).toEqual(hosts);
    expect(hosts.map((host) => host.style.width)).toEqual(widths);
    expect(useWorkspace.getState().paneOrder).toEqual(order);
    expect(useWorkspace.getState().paneTiles).toEqual(tiles);
    press(companion, "ArrowRight", "ArrowRight");
    const a = node('[data-workspace-window="control:a"]');
    expect(document.activeElement).toBe(a);
    expect(press(a, "ArrowLeft", "ArrowLeft").defaultPrevented).toBe(true);
    expect(document.activeElement).toBe(companion);
    expect(root.scrollLeft).toBe(510);
  });
  it.each([[0, 700], [1000, 0], [20, 700], [1000, 20]])(
    "refuses legacy L and its configured prefix at current %i by %i bounds before any preference write",
    (currentWidth, currentHeight) => {
      act(() => { useWorkspace.getState().setPaneArrangement("legacy"); });
      const a = node('[data-workspace-window="control:a"]');
      const root = node("[data-pane-flow-root]");
      act(() => { a.focus(); });
      const preferenceKey = "antiek.workspace.desktop-pane-arrangement.v1";
      const preference = window.localStorage.getItem(preferenceKey);
      const write = vi.spyOn(Storage.prototype, "setItem");
      const toggle = vi.spyOn(useWorkspace.getState(), "togglePaneArrangement");
      const order = useWorkspace.getState().paneOrder;
      const focus = useWorkspace.getState().paneFocus;
      // Only the root collapses. The actual legacy frame keeps its connected, visible client rect.
      Object.defineProperty(root, "clientWidth", { configurable: true, get: () => currentWidth });
      Object.defineProperty(root, "clientHeight", { configurable: true, get: () => currentHeight });
      expect(a.isConnected).toBe(true);
      expect(a.getClientRects().length).toBeGreaterThan(0);
      expect(root.dataset.paneMeasurement).toBe("unmeasured");
      expect(press(a, "l", "KeyL").defaultPrevented).toBe(false);
      press(a, "b", "KeyB", { altKey: false });
      expect(prefixState.isArmed()).toBe(true);
      // The existing prefix dispatcher owns its second key even when the action refuses.
      expect(press(a, "I", "KeyI", { ctrlKey: false, altKey: false, shiftKey: true }).defaultPrevented).toBe(true);
      expect(prefixState.isArmed()).toBe(false);
      expect(toggle).not.toHaveBeenCalled();
      expect(useWorkspace.getState().paneArrangement).toBe("legacy");
      expect(useWorkspace.getState().paneOrder).toEqual(order);
      expect(useWorkspace.getState().paneFocus).toEqual(focus);
      expect(document.activeElement).toBe(a);
      expect(a.hidden).toBe(false);
      expect(window.localStorage.getItem(preferenceKey)).toBe(preference);
      expect(write.mock.calls.filter(([key]) => key === preferenceKey)).toEqual([]);
      Object.defineProperty(root, "clientWidth", { configurable: true, get: () => 1000 });
      Object.defineProperty(root, "clientHeight", { configurable: true, get: () => 700 });
      expect(press(a, "l", "KeyL").defaultPrevented).toBe(true);
      expect(toggle).toHaveBeenCalledTimes(1);
      expect(useWorkspace.getState().paneArrangement).toBe("horizontal");
      expect(document.activeElement).toBe(a);
      expect(a.hidden).toBe(false);
      expect(write.mock.calls.filter(([key]) => key === preferenceKey)).toHaveLength(1);
    },
  );
  it("restores window zoom from a nonediting child before closing the window", () => {
    const a = node('[data-workspace-window="control:a"]');
    act(() => { a.focus(); });
    press(a, "f", "KeyF");
    const close = node('[data-workspace-window="control:a"] [data-window-action="close"]');
    act(() => { close.focus(); });
    press(close, "Escape", "Escape", { ctrlKey: false, altKey: false });
    expect(useWorkspace.getState().paneZoom).toBeNull();
    expect(Object.hasOwn(useWindows.getState().windows, "control:a")).toBe(true);
    expect(node('[data-workspace-window="control:a"]')).toBe(a);
  });
  it("refuses stale/detached and zero-width hosts without a last-known geometry fallback", () => {
    const core = node('[data-pane-host="core"]');
    width = 0;
    act(() => { for (const measure of resize) measure(); });
    expect(press(core, "ArrowRight", "ArrowRight").defaultPrevented).toBe(false);
    expect(node("[data-pane-flow-root]").dataset.paneMeasurement).toBe("unmeasured");
    const a = node('[data-workspace-window="control:a"]');
    act(() => { useWindows.getState().close("control:a"); });
    expect(press(a, "f", "KeyF").defaultPrevented).toBe(false);
    expect(useWorkspace.getState().paneZoom).toBeNull();
  });
});
