/**
 * cockpitSweepV2.panes.test.tsx — lane A stage B1: the pane blockers from
 * Antiek Sweep v2's forensic audit, each case kept from the executed probe
 * it names (cockpit/probes/c2c3-fullscreen-preset and c2c3-docked-and-keys)
 * with the probe's setup, asserting the CORRECT behaviour.
 *
 *   F-17  fullscreen and the preset toggle keep both panes MOUNTED (hidden,
 *         never unmounted), so a draft typed in the route survives and ⌘K
 *         keeps working; right-pane fullscreen fills the width (H1, H2, Q6).
 *   F-18  fullscreen never blanks the cockpit or traps the next panel in a
 *         hidden dock: the toggle only hides what is on screen, a docked
 *         panel opening into a hidden side restores the layout, and a chip
 *         says fullscreen is on (H3, H4, H4b, Q1, Q2).
 *   F-19  the preset never toggles while typing (Q3).
 *   H5/Q5 Esc from <body> restores; H6 panes are named regions with a
 *         visible focus ring; H7 the inset keeps both panes at lg and md.
 *
 * "Visible" here is what a sighted user gets: an element with no `hidden`
 * ancestor. jsdom applies no Tailwind, so the `hidden` attribute is the
 * contract the layout keeps (with the matching `hidden` utility class).
 */
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import { act, cleanup, fireEvent, render } from "@testing-library/react";
import { useEffect, useState } from "react";

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
  apiFetch: vi.fn(() => Promise.resolve({ ok: false, status: 404, json: async () => ({}), text: async () => "" })),
  postTypedEvent: vi.fn(() => Promise.resolve({ event_id: "e" })),
}));

import { prefixState } from "../components/hotkeys/prefixState";
import { PanelLayout } from "./PanelLayout";
import { useWorkspace } from "./WorkspaceStore";
import { installShortcuts } from "./shortcuts";
import { pinPlatform, press, pressKey, unpinPlatform } from "./keymapTestKit";

const { tierRef } = vi.hoisted(() => ({ tierRef: { current: "xl" as string } }));
vi.mock("./useViewportTier", () => ({ useViewportTier: () => tierRef.current }));

let uninstall: (() => void) | null = null;
const ws = () => useWorkspace.getState();

function key(target: EventTarget, spec: string) {
  act(() => {
    press(target, spec, "mac");
  });
}
function keyRaw(target: EventTarget, init: KeyboardEventInit) {
  act(() => {
    pressKey(target, init);
  });
}

let mounts = 0;
let paletteToggles = 0;
/** The route: a field with a draft, counting its mounts, and a listener
 *  standing for anything the route keeps alive (the probe's ⌘K witness). */
function Stateful() {
  const [text, setText] = useState("");
  useEffect(() => {
    mounts += 1;
  }, []);
  useEffect(() => {
    const on = () => {
      paletteToggles += 1;
    };
    window.addEventListener("antiek:palette:toggle", on);
    return () => window.removeEventListener("antiek:palette:toggle", on);
  }, []);
  return <input data-testid="route-input" value={text} onChange={(e) => setText(e.target.value)} />;
}

function typeDraft(input: HTMLInputElement, value = "draft") {
  act(() => {
    input.focus();
    fireEvent.change(input, { target: { value } });
  });
  act(() => {
    input.blur();
  });
}

const tree = () => <PanelLayout mainSlot={<Stateful />} />;
const routeInput = () => document.querySelector<HTMLInputElement>('[data-testid="route-input"]');
const isVisible = (el: Element | null): boolean => el !== null && el.closest("[hidden]") === null;
const pane = (side: "left" | "right") => document.querySelector<HTMLElement>(`[data-pane="${side}"]`);
const visiblePanes = () =>
  Array.from(document.querySelectorAll<HTMLElement>("[data-pane]"))
    .filter(isVisible)
    .map((el) => el.getAttribute("data-pane"));

function openTwo() {
  ws().open("Notes", {}, { mode: "docked-left", id: "p:left", title: "Left" });
  ws().open("Notes", {}, { mode: "docked-right", id: "p:right", title: "Right" });
}

beforeEach(() => {
  pinPlatform("mac");
  tierRef.current = "xl";
  window.localStorage.removeItem("antiek.workspace.layout-preset");
  ws().reset();
  ws().setLayoutPreset("docked");
  uninstall = installShortcuts(vi.fn() as never);
  mounts = 0;
  paletteToggles = 0;
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

// ─── F-17 ───────────────────────────────────────────────────────────────

describe("F-17 — fullscreen and the preset keep both panes mounted", () => {
  it("H1 right-pane fullscreen hides the left pane without unmounting the route", () => {
    openTwo();
    ws().setLayoutPreset("omarchy-inset");
    render(tree());
    const input = routeInput()!;
    typeDraft(input);
    key(document.body, "ctrl+b");
    key(document.body, "l");
    key(document.body, "ctrl+b");
    key(document.body, "f");
    expect(ws().fullscreenPane).toBe("right");
    const right = pane("right")!;
    expect(right.style.width).toBe("");
    expect(right.className.includes("flex-1")).toBe(true);
    expect(visiblePanes()).toEqual(["right"]);
    // Hidden, not gone: the same field, its draft, and its listeners.
    expect(routeInput()).toBe(input);
    expect(isVisible(input)).toBe(false);
    key(document.body, "mod+k");
    expect(paletteToggles).toBe(1);
    key(document.body, "ctrl+b");
    key(document.body, "f");
    expect(routeInput()).toBe(input);
    expect(routeInput()!.value).toBe("draft");
    expect(isVisible(input)).toBe(true);
    expect(mounts).toBe(1);
  });

  it("left-pane fullscreen keeps the right pane's node (the companion is hidden, not remounted)", () => {
    openTwo();
    ws().setLayoutPreset("omarchy-inset");
    render(tree());
    const right = pane("right")!;
    key(document.body, "ctrl+b");
    key(document.body, "h");
    key(document.body, "ctrl+b");
    key(document.body, "f");
    expect(ws().fullscreenPane).toBe("left");
    expect(pane("right")).toBe(right);
    expect(visiblePanes()).toEqual(["left"]);
    key(document.body, "ctrl+b");
    key(document.body, "f");
    expect(pane("right")).toBe(right);
    expect(visiblePanes()).toEqual(["left", "right"]);
  });

  it("H2 the preset toggle (prefix shift+i) keeps the route mounted with its draft, both ways", () => {
    openTwo();
    render(tree());
    const input = routeInput()!;
    typeDraft(input);
    key(document.body, "ctrl+b");
    key(document.body, "shift+i");
    expect(ws().layoutPreset).toBe("omarchy-inset");
    expect(routeInput()).toBe(input);
    expect(routeInput()!.value).toBe("draft");
    key(document.body, "ctrl+b");
    key(document.body, "shift+i");
    expect(ws().layoutPreset).toBe("docked");
    expect(routeInput()).toBe(input);
    expect(routeInput()!.value).toBe("draft");
    expect(mounts).toBe(1);
  });

  it("the preset toggle keeps a docked panel's node", () => {
    openTwo();
    render(tree());
    const leftPanel = document.querySelector('[aria-label="Left dock"]')!.firstElementChild;
    expect(leftPanel).toBeTruthy();
    key(document.body, "ctrl+b");
    key(document.body, "shift+i");
    expect(document.querySelector('[aria-label="Left dock"]')!.firstElementChild).toBe(leftPanel);
  });

  it("Q6 right-pane fullscreen at xl fills the cockpit, never a 320 px column", () => {
    ws().open("Notes", {}, { mode: "docked-right", id: "p:right", title: "Right" });
    ws().setLayoutPreset("omarchy-inset");
    render(tree());
    key(document.body, "ctrl+b");
    key(document.body, "l");
    key(document.body, "ctrl+b");
    key(document.body, "f");
    const right = pane("right")!;
    expect(right.style.width).not.toBe("320px");
    expect(right.className.includes("flex-1")).toBe(true);
  });
});

// ─── F-18 ───────────────────────────────────────────────────────────────

describe("F-18 — fullscreen never blanks the cockpit or traps a dock", () => {
  it("H3/Q1 docked with no docks: prefix f has nothing to hide, and mod+/ opens a visible sidecar", () => {
    render(tree());
    key(document.body, "ctrl+b");
    key(document.body, "f");
    expect(ws().fullscreenPane).toBeNull();
    key(document.body, "mod+/");
    const rightDock = document.querySelector<HTMLElement>('[aria-label="Right dock"]')!;
    expect(ws().dockRightIds.length).toBe(1);
    expect(rightDock.style.width).toBe("320px");
  });

  it("docked fullscreen with a dock open, then mod+/: the sidecar restores the layout and shows", () => {
    ws().open("Notes", {}, { mode: "docked-left", id: "p:left", title: "Left" });
    render(tree());
    key(document.body, "ctrl+b");
    key(document.body, "f");
    expect(ws().fullscreenPane).toBe("left");
    key(document.body, "mod+/");
    expect(ws().fullscreenPane).toBeNull();
    expect(document.querySelector<HTMLElement>('[aria-label="Right dock"]')!.style.width).toBe("320px");
  });

  it("inset left fullscreen, then a right-dock panel opens: the layout restores so it shows", () => {
    ws().setLayoutPreset("omarchy-inset");
    render(tree());
    key(document.body, "ctrl+b");
    key(document.body, "f");
    expect(ws().fullscreenPane).toBe("left");
    key(document.body, "mod+/");
    expect(ws().fullscreenPane).toBeNull();
    expect(visiblePanes()).toEqual(["left", "right"]);
  });

  it("H4 a tier change to md after focusing the right pane: prefix f shows a pane, never nothing", () => {
    openTwo();
    ws().setLayoutPreset("omarchy-inset");
    const { rerender } = render(tree());
    key(document.body, "ctrl+b");
    key(document.body, "l");
    expect(ws().focusedPane).toBe("right");
    tierRef.current = "md";
    rerender(tree());
    // md shows one pane at a time (lane A B3-3): the focused one.
    expect(visiblePanes()).toEqual(["right"]);
    key(document.body, "ctrl+b");
    key(document.body, "f");
    expect(ws().fullscreenPane).toBe("right");
    expect(visiblePanes()).toEqual(["right"]);
    expect(pane("right")!.childElementCount).toBeGreaterThan(0);
    expect(routeInput()).toBeTruthy();
  });

  it("H4b after the right panel closes (xl), prefix f fullscreens the companion pane, still on screen", () => {
    openTwo();
    ws().setLayoutPreset("omarchy-inset");
    render(tree());
    key(document.body, "ctrl+b");
    key(document.body, "l");
    act(() => {
      ws().close("p:right");
    });
    key(document.body, "ctrl+b");
    key(document.body, "f");
    expect(visiblePanes()).toEqual([ws().fullscreenPane]);
    expect(pane(ws().fullscreenPane!)!.childElementCount).toBeGreaterThan(0);
    expect(routeInput()).toBeTruthy();
  });

  it("Q2 inset at lg: sidecar, focus right, then a left dock: both panes stay, and prefix f shows one", () => {
    tierRef.current = "lg";
    ws().setLayoutPreset("omarchy-inset");
    render(<PanelLayout mainSlot={<p>route</p>} />);
    key(document.body, "mod+/");
    key(document.body, "ctrl+b");
    key(document.body, "l");
    expect(ws().focusedPane).toBe("right");
    key(document.body, "ctrl+b");
    key(document.body, "b");
    expect(visiblePanes()).toEqual(["left", "right"]);
    key(document.body, "ctrl+b");
    key(document.body, "f");
    expect(visiblePanes()).toEqual([ws().fullscreenPane]);
  });

  it("a chip says fullscreen is on, and pressing it restores", () => {
    openTwo();
    ws().setLayoutPreset("omarchy-inset");
    const { getByRole, queryByRole } = render(tree());
    expect(queryByRole("button", { name: /exit fullscreen/i })).toBeNull();
    key(document.body, "ctrl+b");
    key(document.body, "f");
    const chip = getByRole("button", { name: /exit fullscreen/i });
    act(() => {
      chip.click();
    });
    expect(ws().fullscreenPane).toBeNull();
    expect(queryByRole("button", { name: /exit fullscreen/i })).toBeNull();
  });
});

// ─── F-19 ───────────────────────────────────────────────────────────────

describe("F-19 — the preset never toggles while typing (Q3)", () => {
  it("ctrl+alt+i and prefix shift+i typed in a route field leave the preset and the draft", () => {
    render(tree());
    const f = routeInput()!;
    act(() => {
      f.focus();
      fireEvent.change(f, { target: { value: "unsaved draft" } });
    });
    keyRaw(f, { key: "i", code: "KeyI", ctrlKey: true, altKey: true });
    key(f, "ctrl+alt+i");
    key(f, "ctrl+b");
    key(f, "shift+i");
    expect(ws().layoutPreset).toBe("docked");
    expect(routeInput()).toBe(f);
    expect(routeInput()!.value).toBe("unsaved draft");
    expect(mounts).toBe(1);
  });
});

// ─── H5 / Q5, H6, H7 ────────────────────────────────────────────────────

describe("H5/Q5 — Esc from <body> restores fullscreen in both presets", () => {
  it("H5 inset", () => {
    openTwo();
    ws().setLayoutPreset("omarchy-inset");
    render(tree());
    key(document.body, "ctrl+b");
    key(document.body, "f");
    expect(ws().fullscreenPane).not.toBeNull();
    keyRaw(document.body, { key: "Escape", code: "Escape" });
    expect(ws().fullscreenPane).toBeNull();
  });

  it("Q5 docked", () => {
    ws().open("Notes", {}, { mode: "docked-left", id: "p:left", title: "Left" });
    render(<PanelLayout mainSlot={<p>route</p>} />);
    key(document.body, "ctrl+b");
    key(document.body, "f");
    expect(ws().fullscreenPane).toBe("left");
    keyRaw(document.activeElement ?? document.body, { key: "Escape", code: "Escape" });
    expect(ws().fullscreenPane).toBeNull();
  });
});

describe("H6 — the panes are named regions with a visible focus ring", () => {
  it("both panes are regions by name; the focused one carries the ring", () => {
    openTwo();
    ws().setLayoutPreset("omarchy-inset");
    const { getByRole } = render(tree());
    const left = getByRole("region", { name: "Primary pane" });
    const right = getByRole("region", { name: "Agents pane" });
    expect(left.getAttribute("data-pane")).toBe("left");
    expect(right.getAttribute("data-pane")).toBe("right");
    key(document.body, "ctrl+b");
    key(document.body, "h");
    expect(document.activeElement).toBe(left);
    expect(left.className.includes("ring-focus")).toBe(true);
    expect(right.className.includes("ring-focus")).toBe(false);
    key(document.body, "ctrl+b");
    key(document.body, "l");
    expect(document.activeElement).toBe(right);
    expect(right.className.includes("ring-focus")).toBe(true);
    expect(left.className.includes("ring-focus")).toBe(false);
  });
});

describe("H7 — the inset keeps both panes at lg; md shows one at a time, both mounted", () => {
  it.each(["xl", "lg"] as const)("%s: two panes on screen", (tier) => {
    openTwo();
    ws().setLayoutPreset("omarchy-inset");
    tierRef.current = tier;
    render(tree());
    expect(visiblePanes()).toEqual(["left", "right"]);
  });

  // Superseded by lane A B3-3 (a 280 px right pane at md was cramped and,
  // on the operator's screen, out of reach): md shows the focused pane full
  // width and keeps the other mounted, one key away. The switching itself
  // is cockpitB3.render.test.tsx.
  it("md: the left pane on screen, the right mounted behind it", () => {
    openTwo();
    ws().setLayoutPreset("omarchy-inset");
    tierRef.current = "md";
    render(tree());
    expect(visiblePanes()).toEqual(["left"]);
    expect(pane("right")).toBeTruthy();
    expect(pane("right")!.childElementCount).toBeGreaterThan(0);
  });
});
