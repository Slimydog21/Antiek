import { describe, it, expect, beforeEach, afterEach, beforeAll } from "vitest";
import { render, act } from "@testing-library/react";

import { HotkeyHud } from "./HotkeyHud";
import { SHORTCUT_EVENTS } from "../../workspace/shortcuts";
import { writeCustomHotkeys } from "../../workspace/persistence";

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

describe("HotkeyHud — SPR-08", () => {
  beforeEach(() => {
    window.localStorage.clear();
  });
  afterEach(() => {
    window.localStorage.clear();
  });

  it("renders a dialog listing built-in + product bindings when open", () => {
    const { unmount } = render(<HotkeyHud open onClose={() => {}} />);
    // The modal portals to document.body.
    const dialog = document.body.querySelector('[role="dialog"]');
    expect(dialog).toBeTruthy();
    expect(dialog!.textContent).toContain("Command palette");
    expect(dialog!.textContent).toContain("Research");
    expect(dialog!.textContent).toContain("Read");
    unmount();
  });

  it("M3 — the HUD is ⌘-ONLY: no 'Go to (chords)' group and no chip shows 'then'", () => {
    const { unmount } = render(<HotkeyHud open onClose={() => {}} />);
    const dialog = document.body.querySelector('[role="dialog"]')!;
    // The chord group heading is gone.
    expect(dialog.textContent).not.toContain("Go to (chords)");
    // No group heading mentions "chord" at all.
    const headings = Array.from(dialog.querySelectorAll(".antiek-hud__heading")).map(
      (h) => h.textContent ?? "",
    );
    expect(headings.some((h) => /chord/i.test(h))).toBe(false);
    // No KeyChip renders a "then" separator — every live spec is a combo.
    expect(dialog.querySelector(".antiek-keychip__then")).toBeNull();
    // Every rendered chip is a single glyph group (no chord sequence wrapper).
    expect(dialog.querySelector(".antiek-keychip__seq")).toBeNull();
    // It DOES surface the Products group (the ⌘+key doors).
    expect(headings).toContain("Products");
    unmount();
  });

  it("M3 — keeps a custom-bindings section + an empty-state when none are set", () => {
    const { unmount } = render(<HotkeyHud open onClose={() => {}} />);
    const dialog = document.body.querySelector('[role="dialog"]')!;
    // Empty-state copy invites the operator to assign one.
    expect(dialog.textContent).toMatch(/haven.t assigned any custom hotkeys/i);
    unmount();
  });

  it("lists custom bindings from the persisted blob", () => {
    writeCustomHotkeys({
      schemaVersion: 1,
      bindings: [
        {
          id: "c1",
          spec: "alt+j",
          route: "/inv/x",
          entityId: "x",
          entityKind: "investigation",
          label: "My pinned research",
        },
      ],
    });
    const { unmount } = render(<HotkeyHud open onClose={() => {}} />);
    const dialog = document.body.querySelector('[role="dialog"]')!;
    expect(dialog.textContent).toContain("My pinned research");
    expect(dialog.textContent).toContain("Your custom hotkeys");
    unmount();
  });

  it("toggles open via the HELP_TOGGLE window event (uncontrolled)", () => {
    const { unmount } = render(<HotkeyHud />);
    expect(document.body.querySelector('[role="dialog"]')).toBeNull();
    // The toggle runs in a window listener (outside React's event system),
    // so flush the state update with act().
    act(() => {
      window.dispatchEvent(new CustomEvent(SHORTCUT_EVENTS.HELP_TOGGLE));
    });
    expect(document.body.querySelector('[role="dialog"]')).toBeTruthy();
    act(() => {
      window.dispatchEvent(new CustomEvent(SHORTCUT_EVENTS.HELP_TOGGLE));
    });
    expect(document.body.querySelector('[role="dialog"]')).toBeNull();
    unmount();
  });
});
