/**
 * cockpitInset.test.tsx — cockpit chrome PR 1 (C2/C3) acceptance.
 *
 *   C2  the Omarchy inset preset: two tall rounded rectangles over the scene
 *       (the gap shows the background), the SAME slot structure inside, the
 *       docked preset byte-identical by default, the choice persisted via
 *       its own global blob (the custom-hotkeys precedent).
 *   C3  the pane key rows: prefix h/l (+ ctrl+alt twins) move DOM focus
 *       between the panes with a visible ring — and in the docked preset
 *       they cycle dock areas, never a dead key; prefix f fullscreens the
 *       focused pane (Esc or repeat restores); prefix i switches the
 *       preset; none of the prefix keys arms from a text field.
 *
 * The dispatcher runs with REAL handlers here: the assertions are on the
 * store and the DOM, not on counting stubs.
 */
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import { act, cleanup, render } from "@testing-library/react";

beforeAll(() => {
  Object.defineProperty(window, "matchMedia", {
    writable: true,
    configurable: true,
    value: (query: string) => ({
      matches: false,
      media: query,
      onchange: null,
      addEventListener: () => {},
      removeEventListener: () => {},
      addListener: () => {},
      removeListener: () => {},
      dispatchEvent: () => false,
    }),
  });
});

vi.mock("../lib/api", async (orig) => ({
  ...(await orig<typeof import("../lib/api")>()),
  apiFetch: vi.fn(() => Promise.resolve({ ok: false, status: 404, json: async () => ({}) })),
  postTypedEvent: vi.fn(() => Promise.resolve({ event_id: "e" })),
}));

import { RESERVED_FOR_LATER } from "../components/hotkeys/keymap";
import { prefixState } from "../components/hotkeys/prefixState";
import { PanelLayout } from "./PanelLayout";
import { useWorkspace } from "./WorkspaceStore";
import { installShortcuts } from "./shortcuts";
import { readLayoutPreset } from "./persistence";
import { pinPlatform, press, pressKey, unpinPlatform } from "./keymapTestKit";

const { tierRef } = vi.hoisted(() => ({ tierRef: { current: "xl" as string } }));
vi.mock("./useViewportTier", () => ({
  useViewportTier: () => tierRef.current,
}));

let uninstall: (() => void) | null = null;

/** Key presses go through act(): the real handlers mutate the store, and
 *  React must flush the resulting render before the DOM assertions. */
function key(target: EventTarget, spec: string): KeyboardEvent {
  let e = new KeyboardEvent("keydown");
  act(() => {
    e = press(target, spec, "mac");
  });
  return e;
}

function keyRaw(target: EventTarget, init: KeyboardEventInit): KeyboardEvent {
  let e = new KeyboardEvent("keydown");
  act(() => {
    e = pressKey(target, init);
  });
  return e;
}

const ws = () => useWorkspace.getState();

beforeEach(() => {
  pinPlatform("mac");
  tierRef.current = "xl";
  window.localStorage.removeItem("antiek.workspace.layout-preset");
  ws().reset();
  ws().setLayoutPreset("docked");
  uninstall = installShortcuts(vi.fn() as never);
});

afterEach(() => {
  uninstall?.();
  uninstall = null;
  cleanup();
  prefixState.disarm();
  ws().reset();
  ws().setLayoutPreset("docked");
  window.localStorage.removeItem("antiek.workspace.layout-preset");
  unpinPlatform();
  document.body.innerHTML = "";
});

function openTwoDocks() {
  ws().open("Notes", {}, { mode: "docked-left", id: "p:left", title: "Left" });
  ws().open("Notes", {}, { mode: "docked-right", id: "p:right", title: "Right" });
}

function mountLayout() {
  return render(
    <div>
      <nav data-testid="rail">NavRail stands here (a sibling, as in AppShell)</nav>
      <PanelLayout mainSlot={<p>route content</p>} />
    </div>,
  );
}

describe("the docked preset is the default and its DOM is unchanged", () => {
  it("no inset frame, the docks keep their chrome, main slot intact", () => {
    openTwoDocks();
    const { container, getByText } = mountLayout();
    expect(container.querySelector("[data-layout-preset]")).toBeNull();
    expect(container.querySelector("[data-pane]")).toBeNull();
    const leftDock = container.querySelector('[aria-label="Left dock"]')!;
    const rightDock = container.querySelector('[aria-label="Right dock"]')!;
    expect(leftDock.className).toContain("border-r");
    expect(leftDock.className).toContain("bg-ice-1");
    expect(rightDock.className).toContain("border-l");
    expect(getByText("route content")).toBeTruthy();
    // No pane wrappers: the docks are direct children of the layout root.
    expect(leftDock.parentElement).toBe(container.querySelector("div.relative.h-full.w-full.flex"));
  });
});

describe("the omarchy-inset preset (C2)", () => {
  it("renders two inset panes with the gap, rounded hairline shells, and the nav OUTSIDE the frame", () => {
    openTwoDocks();
    ws().setLayoutPreset("omarchy-inset");
    const { container, getByTestId, getByText } = mountLayout();
    const frame = container.querySelector<HTMLElement>('[data-layout-preset="omarchy-inset"]')!;
    expect(frame).toBeTruthy();
    // The outer gap: padding + inter-pane gap show the scene background.
    expect(frame.style.padding).toBe("12px");
    expect(frame.style.gap).toBe("12px");
    const left = container.querySelector<HTMLElement>('[data-pane="left"]')!;
    const right = container.querySelector<HTMLElement>('[data-pane="right"]')!;
    expect(left.getAttribute("aria-label")).toBe("Primary pane");
    expect(right.getAttribute("aria-label")).toBe("Companion pane");
    // Rounded, hairline-bordered shells from tokens.
    expect(left.style.borderRadius).toBe("10px");
    expect(right.style.borderRadius).toBe("10px");
    expect(left.className).toContain("border-hairline");
    expect(right.className).toContain("border-hairline");
    // The primary material (route content) lives in the left pane.
    expect(left.contains(getByText("route content"))).toBe(true);
    // NavRail is a sibling of the layout: the frame never wraps it.
    expect(frame.contains(getByTestId("rail"))).toBe(false);
    expect(getByTestId("rail")).toBeTruthy();
  });

  it("an empty right dock still collapses: one pane, full inset width", () => {
    ws().open("Notes", {}, { mode: "docked-left", id: "p:left", title: "Left" });
    ws().setLayoutPreset("omarchy-inset");
    const { container } = mountLayout();
    expect(container.querySelector('[data-pane="left"]')).toBeTruthy();
    expect(container.querySelector('[data-pane="right"]')).toBeNull();
  });

  it("tier sm still early-returns the bare main slot (no hooks after the return)", () => {
    openTwoDocks();
    ws().setLayoutPreset("omarchy-inset");
    tierRef.current = "sm";
    const { container, getByText } = mountLayout();
    expect(container.querySelector("[data-layout-preset]")).toBeNull();
    expect(container.querySelector("[data-pane]")).toBeNull();
    expect(getByText("route content")).toBeTruthy();
  });
});

describe("the preset key (layout.togglePreset) and its persistence", () => {
  it("prefix+i switches docked ⇄ omarchy-inset and the choice survives a reload", () => {
    key(document.body, "ctrl+b");
    key(document.body, "i");
    expect(ws().layoutPreset).toBe("omarchy-inset");
    // The reload proof: a fresh read from persistence (what a new page load
    // seeds the store with) returns the operator's choice.
    expect(readLayoutPreset()).toBe("omarchy-inset");
    key(document.body, "ctrl+b");
    key(document.body, "i");
    expect(ws().layoutPreset).toBe("docked");
    expect(readLayoutPreset()).toBe("docked");
  });

  it("the chord twin ctrl+alt+i also switches, from a default focus", () => {
    key(document.body, "ctrl+alt+i");
    expect(ws().layoutPreset).toBe("omarchy-inset");
  });

  it("switching presets clears the pane states (nothing hidden on the far side)", () => {
    openTwoDocks();
    ws().setLayoutPreset("omarchy-inset");
    ws().setFocusedPane("left");
    ws().setFullscreenPane("left");
    key(document.body, "ctrl+b");
    key(document.body, "i");
    expect(ws().layoutPreset).toBe("docked");
    expect(ws().fullscreenPane).toBeNull();
    expect(ws().focusedPane).toBeNull();
  });
});

describe("the pane-focus keys (C3)", () => {
  it("prefix h/l move DOM focus between the inset panes with a visible ring", () => {
    openTwoDocks();
    ws().setLayoutPreset("omarchy-inset");
    const { container } = mountLayout();
    const left = container.querySelector<HTMLElement>('[data-pane="left"]')!;
    const right = container.querySelector<HTMLElement>('[data-pane="right"]')!;

    key(document.body, "ctrl+b");
    key(document.body, "l");
    expect(ws().focusedPane).toBe("right");
    expect(document.activeElement).toBe(right);
    expect(right.className).toContain("ring-focus");
    expect(left.className).not.toContain("ring-focus");

    key(document.body, "ctrl+b");
    key(document.body, "h");
    expect(ws().focusedPane).toBe("left");
    expect(document.activeElement).toBe(left);
    expect(left.className).toContain("ring-focus");
    expect(right.className).not.toContain("ring-focus");
  });

  it("the chord twins ctrl+alt+h/l move pane focus too", () => {
    openTwoDocks();
    ws().setLayoutPreset("omarchy-inset");
    mountLayout();
    key(document.body, "ctrl+alt+l");
    expect(ws().focusedPane).toBe("right");
    key(document.body, "ctrl+alt+h");
    expect(ws().focusedPane).toBe("left");
  });

  it("in the docked preset the same keys cycle dock areas — never a dead key", () => {
    ws().open("Notes", {}, { mode: "docked-left", id: "p:a", title: "A" });
    ws().open("Notes", {}, { mode: "docked-right", id: "p:b", title: "B" });
    ws().focus("p:a");
    key(document.body, "ctrl+b");
    key(document.body, "l");
    expect(ws().focusedPanelId).toBe("p:b");
    key(document.body, "ctrl+b");
    key(document.body, "h");
    expect(ws().focusedPanelId).toBe("p:a");
  });

  it("focus onto a collapsed pane is an honest no-op (nowhere for focus to go)", () => {
    ws().open("Notes", {}, { mode: "docked-left", id: "p:left", title: "Left" });
    ws().setLayoutPreset("omarchy-inset");
    mountLayout();
    key(document.body, "ctrl+b");
    key(document.body, "l");
    expect(ws().focusedPane).toBeNull();
  });
});

describe("the fullscreen key (pane.fullscreen)", () => {
  function mountInsetTwoPanes() {
    openTwoDocks();
    ws().setLayoutPreset("omarchy-inset");
    return mountLayout();
  }

  it("prefix f hides the companion pane; prefix f again restores it", () => {
    const { container } = mountInsetTwoPanes();
    key(document.body, "ctrl+b");
    key(document.body, "f");
    expect(ws().fullscreenPane).toBe("left");
    expect(container.querySelector('[data-pane="left"]')).toBeTruthy();
    expect(container.querySelector('[data-pane="right"]')).toBeNull();

    key(document.body, "ctrl+b");
    key(document.body, "f");
    expect(ws().fullscreenPane).toBeNull();
    expect(container.querySelector('[data-pane="right"]')).toBeTruthy();
  });

  it("Esc restores the hidden pane (element-scoped, never a global binding)", () => {
    const { container } = mountInsetTwoPanes();
    key(document.body, "ctrl+b");
    key(document.body, "f");
    expect(ws().fullscreenPane).toBe("left");
    const left = container.querySelector<HTMLElement>('[data-pane="left"]')!;
    keyRaw(left, { key: "Escape", code: "Escape" });
    expect(ws().fullscreenPane).toBeNull();
    expect(container.querySelector('[data-pane="right"]')).toBeTruthy();
  });

  it("fullscreen follows the FOCUSED pane", () => {
    const { container } = mountInsetTwoPanes();
    key(document.body, "ctrl+b");
    key(document.body, "l");
    expect(ws().focusedPane).toBe("right");
    key(document.body, "ctrl+b");
    key(document.body, "f");
    expect(ws().fullscreenPane).toBe("right");
    expect(container.querySelector('[data-pane="left"]')).toBeNull();
    expect(container.querySelector('[data-pane="right"]')).toBeTruthy();
  });

  it("in the docked preset, fullscreen collapses every dock and Esc restores", () => {
    openTwoDocks();
    const { container } = mountLayout();
    const leftDock = container.querySelector<HTMLElement>('[aria-label="Left dock"]')!;
    expect(leftDock.style.width).not.toBe("0px");
    key(document.body, "ctrl+b");
    key(document.body, "f");
    expect(ws().fullscreenPane).toBe("left");
    expect(leftDock.style.width).toBe("0px");
    keyRaw(leftDock, { key: "Escape", code: "Escape" });
    expect(ws().fullscreenPane).toBeNull();
    expect(leftDock.style.width).not.toBe("0px");
  });
});

describe("the scope guards hold for the new keys", () => {
  it("none of the prefix keys arms or fires from a text field", () => {
    const input = document.createElement("input");
    document.body.appendChild(input);
    input.focus();
    for (const k of ["h", "l", "f", "i"]) {
      key(input, "ctrl+b");
      expect(prefixState.isArmed(), `prefix must not arm in text (for ${k})`).toBe(false);
      const e = key(input, k);
      expect(e.defaultPrevented, `'${k}' must reach the field as a character`).toBe(false);
    }
    expect(ws().layoutPreset).toBe("docked");
    expect(ws().fullscreenPane).toBeNull();
    expect(ws().focusedPane).toBeNull();
  });

  it("no leftover reserved row remains for h/l/f/i or their chord twins", () => {
    for (const k of ["h", "l", "f", "i"]) {
      expect(RESERVED_FOR_LATER.prefixKeys).not.toContain(k);
    }
    for (const c of ["ctrl+alt+h", "ctrl+alt+l", "ctrl+alt+f", "ctrl+alt+i"]) {
      expect(RESERVED_FOR_LATER.chords).not.toContain(c);
    }
  });

  it("Esc while typing inside a fullscreen pane stays the field's (no restore)", () => {
    openTwoDocks();
    ws().setLayoutPreset("omarchy-inset");
    const { container } = mountLayout();
    act(() => {
      ws().setFullscreenPane("left");
    });
    const input = document.createElement("input");
    const left = container.querySelector<HTMLElement>('[data-pane="left"]')!;
    left.appendChild(input);
    input.focus();
    keyRaw(input, { key: "Escape", code: "Escape" });
    expect(ws().fullscreenPane).toBe("left");
  });
});
