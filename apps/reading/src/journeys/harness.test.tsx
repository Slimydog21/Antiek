/**
 * journeys/harness.test.tsx — SPR-05 M1: the harness proves itself.
 *   - POSITIVE CONTROL: a deliberately clicking journey FAILS under noClick().
 *   - the guard restores the mouse helpers afterwards;
 *   - prefix() refuses to run under a rebound prefix;
 *   - J0, the smallest real journey: mount the App at "/", press prefix+g on
 *     the body, the Switcher opens; Escape closes it. Keyboard only.
 */
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, screen, waitFor } from "@testing-library/react";

beforeAll(() => {
  if (!window.matchMedia) {
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
  }
});

// The repo's API pattern (no MSW): every request answers 404 unless a journey
// installs a route table. An authenticated session via the auth hook.
vi.mock("../lib/api", async (orig) => ({
  ...(await orig<typeof import("../lib/api")>()),
  apiFetch: vi.fn(() => Promise.resolve({ ok: false, status: 404, json: async () => ({}) })),
}));
vi.mock("../lib/auth", async (orig) => {
  const actual = await orig<typeof import("../lib/auth")>();
  return {
    ...actual,
    useAuth: () => ({
      state: { status: "authenticated", identity: { user_id: "u-journey", email: "journey@example.test", auth_method: "test" } },
      refresh: async () => {},
      logout: async () => {},
    }),
  };
});
vi.mock("../scene/Scene", () => ({ Scene: () => null }));
vi.mock("../components/ad/AdBorderMount", () => ({ AdBorderMount: () => null }));

import { JourneyClickError, keyInit, keys, locationSpy, mountApp, noClick, prefix } from "./harness";
import { setPrefix } from "../components/hotkeys/keymap";

beforeEach(() => {
  window.localStorage.clear();
  Object.defineProperty(window, "innerWidth", { configurable: true, writable: true, value: 1280 });
});
afterEach(() => {
  cleanup();
  setPrefix(null);
});

describe("the no-click guard", () => {
  it("POSITIVE CONTROL: a journey that clicks fails loudly, naming the helper", () => {
    const restore = noClick();
    const button = document.createElement("button");
    document.body.appendChild(button);
    try {
      expect(() => fireEvent.click(button)).toThrow(JourneyClickError);
      expect(() => fireEvent.click(button)).toThrow(/used the mouse \(fireEvent\.click\)/);
      expect(() => fireEvent.pointerDown(button)).toThrow(JourneyClickError);
    } finally {
      restore();
      button.remove();
    }
  });

  it("POSITIVE CONTROL: element.click(), a raw non-bubbling MouseEvent on a child, and touchstart are caught at capture and fail at restore()", () => {
    const restore = noClick();
    const parent = document.createElement("div");
    const child = document.createElement("span");
    parent.appendChild(child);
    document.body.appendChild(parent);
    let reached = 0;
    parent.addEventListener("click", () => reached++);
    child.click(); // HTMLElement.prototype.click — not a fireEvent helper
    child.dispatchEvent(new MouseEvent("mousedown", { bubbles: false }));
    child.dispatchEvent(new Event("touchstart", { bubbles: true }));
    expect(reached).toBe(0); // stopped at capture, never reached the handler
    expect(() => restore()).toThrow(JourneyClickError);
    expect(() => restore()).not.toThrow(); // second restore is idempotent
    parent.remove();
  });

  it("restore() gives the mouse back (so other test files are unaffected)", () => {
    const restore = noClick();
    restore();
    const button = document.createElement("button");
    document.body.appendChild(button);
    expect(() => fireEvent.click(button)).not.toThrow();
    button.remove();
  });
});

describe("keys()", () => {
  it("sets the physical code the dispatcher matches on", () => {
    expect(keyInit("ctrl+alt+shift+o")).toMatchObject({ key: "O", code: "KeyO", ctrlKey: true, altKey: true, shiftKey: true });
    expect(keyInit("ctrl+b")).toMatchObject({ key: "b", code: "KeyB", ctrlKey: true });
    expect(keyInit("1")).toMatchObject({ key: "1", code: "Digit1" });
    expect(keyInit("Escape")).toMatchObject({ key: "Escape", code: "Escape" });
    expect(() => keyInit("hyper+x")).toThrow(/unknown key spec/);
  });

  it("prefix() refuses to run under a rebound prefix", () => {
    // ctrl+q is usable (ctrl, not a row's key on any platform); ctrl+; is
    // refused by setPrefix because mod+; is a row off the Mac.
    expect(setPrefix("ctrl+q")).toBe(true);
    expect(() => prefix()).toThrow(/rebound prefix/);
    setPrefix(null);
    expect(() => prefix()).not.toThrow();
  });
});

describe("J0 — the smallest real journey (keyboard only)", () => {
  it("mounts the App at /, prefix+g opens the Switcher, Escape closes it", async () => {
    const restore = noClick();
    try {
      mountApp("/");
      await waitFor(() => expect(locationSpy.pathname).toBe("/"));
      // The shell's dispatcher listens on window; press from the body.
      prefix(document.body);
      keys(document.body, "g");
      const dialog = await screen.findByRole("dialog", { name: "Command palette" });
      expect(dialog).toBeTruthy();
      keys(within(dialog).getByRole("textbox"), "Escape");
      await waitFor(() => expect(screen.queryByRole("dialog", { name: "Command palette" })).toBeNull());
    } finally {
      restore();
    }
  });
});

import { within } from "@testing-library/react";
