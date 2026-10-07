/**
 * journeys/harness.tsx — SPR-05 M1
 * (specs/antiek-keyboard-panes-agents-20261007/sprint-05-keyboard-journeys-flip.html).
 *
 * The operator's sentence under test is "navigable by power users via
 * keyboard". A journey is a vitest+jsdom test that drives the REAL App
 * (router-less App.tsx inside a MemoryRouter; 53 lazy scenes under Suspense)
 * with KeyboardEvents only. This module gives journeys three things:
 *
 *   mountApp(path)   — the App with a location spy, nothing mocked here.
 *                      Test files own their vi.mock calls (lib/auth for an
 *                      authenticated session, lib/api for the apiFetch
 *                      route-table stub — the repo's pattern; no MSW).
 *   keys(target, …)  — real KeyboardEvents with `code` set, because the
 *                      keymap dispatcher matches ctrl+alt chords on the
 *                      PHYSICAL key (keymap.ts D2). `prefix(target)` presses
 *                      the configured prefix and REFUSES to run under a
 *                      rebound one, so a journey cannot pass by accident.
 *   noClick()        — a guard that makes every mouse helper throw. A journey
 *                      that needs a click fails loudly, naming the step. The
 *                      guard has a positive control (harness.test.tsx): a
 *                      deliberately clicking journey must fail.
 */
import { fireEvent, render, type RenderResult } from "@testing-library/react";
import { MemoryRouter, useLocation } from "react-router-dom";

import App from "../App";
import { DEFAULT_PREFIX, readPrefix } from "../components/hotkeys/keymap";

/** The last pathname the router rendered; read it after `waitFor`. */
export const locationSpy = { pathname: "", search: "" };

function LocationSpy() {
  const loc = useLocation();
  locationSpy.pathname = loc.pathname;
  locationSpy.search = loc.search;
  return null;
}

export function mountApp(initialPath = "/"): RenderResult {
  locationSpy.pathname = "";
  locationSpy.search = "";
  return render(
    <MemoryRouter initialEntries={[initialPath]}>
      <LocationSpy />
      <App />
    </MemoryRouter>,
  );
}

/* ------------------------------------------------------------------ */
/* Keys                                                                */
/* ------------------------------------------------------------------ */

const NAMED: Record<string, { key: string; code: string }> = {
  enter: { key: "Enter", code: "Enter" },
  escape: { key: "Escape", code: "Escape" },
  esc: { key: "Escape", code: "Escape" },
  tab: { key: "Tab", code: "Tab" },
  space: { key: " ", code: "Space" },
  backspace: { key: "Backspace", code: "Backspace" },
  up: { key: "ArrowUp", code: "ArrowUp" },
  down: { key: "ArrowDown", code: "ArrowDown" },
  left: { key: "ArrowLeft", code: "ArrowLeft" },
  right: { key: "ArrowRight", code: "ArrowRight" },
  "?": { key: "?", code: "Slash" },
  "/": { key: "/", code: "Slash" },
  "[": { key: "[", code: "BracketLeft" },
  "]": { key: "]", code: "BracketRight" },
  "-": { key: "-", code: "Minus" },
  "=": { key: "=", code: "Equal" },
  ";": { key: ";", code: "Semicolon" },
};

/** "ctrl+b", "shift+o", "g", "Enter", "ArrowDown" → a KeyboardEventInit with
 *  the physical `code` the dispatcher matches on. */
export function keyInit(spec: string): KeyboardEventInit {
  const parts = spec.toLowerCase().split("+");
  const base = parts.pop()!;
  const mods = new Set(parts);
  for (const m of mods) {
    if (!["ctrl", "alt", "shift", "meta", "mod"].includes(m)) {
      throw new Error(`journey harness: unknown key spec "${spec}" (modifier "${m}")`);
    }
  }
  const named = NAMED[base];
  let key: string;
  let code: string;
  if (named) {
    ({ key, code } = named);
  } else if (/^[a-z]$/.test(base)) {
    key = mods.has("shift") ? base.toUpperCase() : base;
    code = `Key${base.toUpperCase()}`;
  } else if (/^[0-9]$/.test(base)) {
    key = base;
    code = `Digit${base}`;
  } else {
    throw new Error(`journey harness: unknown key spec "${spec}"`);
  }
  return {
    key,
    code,
    ctrlKey: mods.has("ctrl"),
    altKey: mods.has("alt"),
    shiftKey: mods.has("shift"),
    metaKey: mods.has("meta") || mods.has("mod"),
    bubbles: true,
    cancelable: true,
  };
}

/** Press each spec on `target` (keydown + keyup), in order. */
export function keys(target: Element | Window, ...specs: string[]): void {
  for (const spec of specs) {
    const init = keyInit(spec);
    fireEvent.keyDown(target, init);
    fireEvent.keyUp(target, init);
  }
}

/** Type printable text into a focused input/textarea via change events. */
export function type(target: HTMLInputElement | HTMLTextAreaElement, text: string): void {
  fireEvent.change(target, { target: { value: text } });
}

/** Press the configured herdr-style prefix. Refuses a rebound prefix so a
 *  journey never passes against a key the operator does not have. */
export function prefix(target: Element | Window = window): void {
  const configured = readPrefix();
  if (configured !== DEFAULT_PREFIX) {
    throw new Error(`journey refuses to run under a rebound prefix (${configured} ≠ ${DEFAULT_PREFIX})`);
  }
  keys(target, configured);
}

/* ------------------------------------------------------------------ */
/* The no-click guard                                                  */
/* ------------------------------------------------------------------ */

export class JourneyClickError extends Error {
  constructor(helper: string) {
    super(`journey used the mouse (${helper}) — the operator's sentence is "navigable via keyboard"; name the step and its owner`);
    this.name = "JourneyClickError";
  }
}

const MOUSE_HELPERS = ["click", "dblClick", "mouseDown", "mouseUp", "pointerDown", "pointerUp", "contextMenu", "touchStart"] as const;
const MOUSE_EVENTS = ["click", "dblclick", "mousedown", "mouseup", "pointerdown", "pointerup", "contextmenu", "touchstart"] as const;

/**
 * Make the mouse impossible until `restore()`:
 *   1. every `fireEvent` mouse helper throws synchronously (names the helper);
 *   2. a CAPTURE-phase listener on `window` for every mouse event records a
 *      violation and stops it — capture runs for non-bubbling events and for
 *      events dispatched on a child, so `el.dispatchEvent(new MouseEvent(…))`
 *      and `HTMLElement.prototype.click()` cannot slip past;
 *   3. `restore()` THROWS if any violation was recorded, so a journey that
 *      clicked through a path the patches do not cover still fails.
 */
export function noClick(): () => void {
  const saved = new Map<string, unknown>();
  const fe = fireEvent as unknown as Record<string, unknown>;
  for (const name of MOUSE_HELPERS) {
    saved.set(name, fe[name]);
    fe[name] = () => {
      throw new JourneyClickError(`fireEvent.${name}`);
    };
  }
  const violations: string[] = [];
  const onMouse = (e: Event) => {
    const target = e.target instanceof Element ? e.target.tagName.toLowerCase() : "window";
    violations.push(`${e.type} on <${target}>`);
    e.stopImmediatePropagation();
    e.preventDefault();
  };
  for (const type of MOUSE_EVENTS) window.addEventListener(type, onMouse, true);
  return () => {
    for (const [name, fn] of saved) fe[name] = fn;
    for (const type of MOUSE_EVENTS) window.removeEventListener(type, onMouse, true);
    const seen = violations.splice(0); // report once; a second restore() is a no-op
    if (seen.length) throw new JourneyClickError(seen.join(", "));
  };
}
