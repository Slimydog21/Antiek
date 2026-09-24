/**
 * Test helpers for the keymap dispatcher: build the keydown a real keyboard
 * sends for a table spec, and pin the platform. Test-only (imported by
 * *.test.tsx files, never by the app).
 */
import { ACTIONS, parseCombo, type ActionId, type Platform } from "../components/hotkeys/keymap";
import type { KeyHandler } from "./shortcuts";

const PUNCT_CODES: Record<string, string> = {
  "[": "BracketLeft",
  "]": "BracketRight",
  "/": "Slash",
  ";": "Semicolon",
  ",": "Comma",
  ".": "Period",
  "'": "Quote",
  "-": "Minus",
  "=": "Equal",
};

/** What macOS composes option+<key> into (a sample; enough to prove a chord
 *  matches the physical key, not the character). */
const MAC_OPTION_GLYPHS: Record<string, string> = { b: "∫", g: "©", 1: "¡", k: "˚" };

/** The KeyboardEventInit a keyboard produces for `spec` on `platform`. */
export function keyInit(spec: string, platform: Platform): KeyboardEventInit {
  const c = parseCombo(spec);
  const init: KeyboardEventInit = {
    bubbles: true,
    cancelable: true,
    ctrlKey: c.ctrl || (c.mod && platform === "other"),
    metaKey: c.meta || (c.mod && platform === "mac"),
    altKey: c.alt,
    shiftKey: c.shift,
  };
  if (c.key === "?") return { ...init, key: "?", code: "Slash", shiftKey: true };
  if (/^[a-z]$/.test(c.key)) {
    init.code = `Key${c.key.toUpperCase()}`;
    init.key = c.shift ? c.key.toUpperCase() : c.key;
  } else if (/^[0-9]$/.test(c.key)) {
    init.code = `Digit${c.key}`;
    init.key = c.key;
  } else if (PUNCT_CODES[c.key]) {
    init.code = PUNCT_CODES[c.key];
    init.key = c.key;
  } else {
    init.key = c.key.charAt(0).toUpperCase() + c.key.slice(1);
  }
  // On a Mac, option composes a character; the chord must still match.
  if (c.alt && platform === "mac") init.key = MAC_OPTION_GLYPHS[c.key] ?? init.key;
  return init;
}

export function press(
  target: EventTarget,
  spec: string,
  platform: Platform,
  extra: KeyboardEventInit = {},
): KeyboardEvent {
  const e = new KeyboardEvent("keydown", { ...keyInit(spec, platform), ...extra });
  target.dispatchEvent(e);
  return e;
}

export function pressKey(target: EventTarget, init: KeyboardEventInit): KeyboardEvent {
  const e = new KeyboardEvent("keydown", { bubbles: true, cancelable: true, ...init });
  target.dispatchEvent(e);
  return e;
}

/** Pin navigator.platform (jsdom reports "", which reads as not-a-Mac). */
export function pinPlatform(platform: Platform): void {
  Object.defineProperty(navigator, "platform", {
    configurable: true,
    get: () => (platform === "mac" ? "MacIntel" : "Linux x86_64"),
  });
}

export function unpinPlatform(): void {
  // Drop the own-property override; the prototype getter answers again.
  delete (navigator as unknown as Record<string, unknown>).platform;
}

/** Handlers that only count, one per action, for dispatch-only assertions. */
export function countingHandlers(): {
  handlers: Record<ActionId, KeyHandler>;
  calls: Record<string, number>;
  total: () => number;
} {
  const calls: Record<string, number> = {};
  const handlers = {} as Record<ActionId, KeyHandler>;
  for (const id of Object.keys(ACTIONS) as ActionId[]) {
    calls[id] = 0;
    handlers[id] = () => {
      calls[id] += 1;
    };
  }
  return { handlers, calls, total: () => Object.values(calls).reduce((a, b) => a + b, 0) };
}
