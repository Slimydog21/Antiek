/**
 * HotkeyHud.test.tsx — the key sheet's mount point (MS-01; was SPR-08's HUD).
 *
 * HotkeyHud toggles on the keymap's HELP_TOGGLE event (`?` or prefix+?),
 * lazy-loads the sheet, and gives focus back to whatever had it when the
 * sheet opened. The sheet's own content is KeySheet.test.tsx.
 */
import { afterEach, beforeAll, describe, expect, it } from "vitest";
import { act, cleanup, render, waitFor } from "@testing-library/react";

import { HotkeyHud } from "./HotkeyHud";
import { SHORTCUT_EVENTS } from "../../workspace/shortcuts";

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

afterEach(() => {
  cleanup();
  window.localStorage.clear();
  document.body.innerHTML = "";
});

const dialog = () => document.body.querySelector('[role="dialog"]');

describe("HotkeyHud — the lazy key sheet", () => {
  it("renders the sheet when controlled open", async () => {
    render(<HotkeyHud open onClose={() => {}} />);
    await waitFor(() => expect(dialog()).toBeTruthy());
    expect(dialog()!.textContent).toContain("Keyboard shortcuts");
    expect(dialog()!.textContent).toContain("Switcher (command palette)");
  });

  it("toggles open and shut on the HELP_TOGGLE window event (uncontrolled)", async () => {
    render(<HotkeyHud />);
    expect(dialog()).toBeNull();
    act(() => {
      window.dispatchEvent(new CustomEvent(SHORTCUT_EVENTS.HELP_TOGGLE));
    });
    await waitFor(() => expect(dialog()).toBeTruthy());
    act(() => {
      window.dispatchEvent(new CustomEvent(SHORTCUT_EVENTS.HELP_TOGGLE));
    });
    expect(dialog()).toBeNull();
  });

  it("returns focus to the element that had it when the sheet opened", async () => {
    const opener = document.createElement("button");
    opener.textContent = "where I was";
    document.body.appendChild(opener);
    opener.focus();
    render(<HotkeyHud />);
    act(() => {
      window.dispatchEvent(new CustomEvent(SHORTCUT_EVENTS.HELP_TOGGLE));
    });
    await waitFor(() => expect(dialog()).toBeTruthy());
    // The dialog took focus.
    await waitFor(() => expect(dialog()!.contains(document.activeElement)).toBe(true));
    act(() => {
      window.dispatchEvent(new CustomEvent(SHORTCUT_EVENTS.HELP_TOGGLE));
    });
    expect(document.activeElement).toBe(opener);
  });
});
