import { describe, it, expect, beforeEach, afterEach, beforeAll } from "vitest";
import { render, fireEvent } from "@testing-library/react";

import { AssignHotkey } from "./AssignHotkey";
import { readCustomHotkeys } from "../../workspace/persistence";

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

const PROPS = {
  entityId: "inv-9",
  route: "/inv/inv-9",
  entityKind: "investigation" as const,
  label: "Test investigation",
};

/** Find a button by its trimmed text (the modal portals to document.body, so
 *  we search the whole body to span the trigger + the dialog footer). */
function buttonByText(re: RegExp): HTMLButtonElement | undefined {
  return Array.from(
    document.body.querySelectorAll<HTMLButtonElement>("button"),
  ).find((b) => re.test(b.textContent ?? ""));
}

describe("AssignHotkey — SPR-08", () => {
  beforeEach(() => window.localStorage.clear());
  afterEach(() => window.localStorage.clear());

  it("opens a capture dialog and saves a free ⌘+key combo, persisting it", () => {
    const { unmount } = render(<AssignHotkey {...PROPS} />);
    fireEvent.click(buttonByText(/assign hotkey/i)!);
    const dialog = document.body.querySelector('[role="dialog"]');
    expect(dialog).toBeTruthy();

    // Capture a free ⌘+key combo. The SPR-08 scheme is ⌘+<key> only — the
    // dialog gates on SAFE_ASSIGNABLE.isWithinRange (which requires `mod`),
    // mirroring useCustomHotkeys.assign. ⌘. (Meta+period) is a free safe combo.
    const capture = dialog!.querySelector('[role="textbox"]') as HTMLElement;
    expect(capture).toBeTruthy();
    fireEvent.keyDown(capture, { key: ".", metaKey: true });
    expect(dialog!.textContent).toMatch(/is available/i);

    // Save.
    fireEvent.click(buttonByText(/save hotkey/i)!);
    expect(readCustomHotkeys().bindings[0]?.spec).toBe("mod+.");
    expect(readCustomHotkeys().bindings[0]?.entityId).toBe("inv-9");
    unmount();
  });

  it("rejects an Option-only (⌥) combo — the scheme is ⌘+key only (Save disabled)", () => {
    const { unmount } = render(<AssignHotkey {...PROPS} />);
    fireEvent.click(buttonByText(/assign hotkey/i)!);
    const dialog = document.body.querySelector('[role="dialog"]')!;
    const capture = dialog.querySelector('[role="textbox"]') as HTMLElement;
    // ⌥J — carries a modifier, so it clears requiresModifierReason, but it is
    // OFF-SPEC (no ⌥ namespace). The dialog must reject it with a readable
    // ⌘-only message and disable Save.
    fireEvent.keyDown(capture, { key: "j", altKey: true });
    const alert = dialog.querySelector('[role="alert"]');
    expect(alert?.textContent).toMatch(/⌘|option-only/i);
    expect(buttonByText(/save hotkey/i)?.disabled).toBe(true);
    expect(readCustomHotkeys().bindings).toHaveLength(0);
    unmount();
  });

  it("discourages a bare single key (Save disabled, modifier required)", () => {
    const { unmount } = render(<AssignHotkey {...PROPS} />);
    fireEvent.click(buttonByText(/assign hotkey/i)!);
    const dialog = document.body.querySelector('[role="dialog"]')!;
    const capture = dialog.querySelector('[role="textbox"]') as HTMLElement;
    // A bare "j" — no modifier, not a chord.
    fireEvent.keyDown(capture, { key: "j" });
    const alert = dialog.querySelector('[role="alert"]');
    expect(alert?.textContent).toMatch(/add a modifier/i);
    expect(buttonByText(/save hotkey/i)?.disabled).toBe(true);
    expect(readCustomHotkeys().bindings).toHaveLength(0);
    unmount();
  });

  it("blocks a built-in collision (Save disabled)", () => {
    const { unmount } = render(<AssignHotkey {...PROPS} />);
    fireEvent.click(buttonByText(/assign hotkey/i)!);
    const dialog = document.body.querySelector('[role="dialog"]')!;
    const capture = dialog.querySelector('[role="textbox"]') as HTMLElement;
    // mod+k = command palette built-in.
    fireEvent.keyDown(capture, { key: "k", metaKey: true });
    const alert = dialog.querySelector('[role="alert"]');
    expect(alert?.textContent).toMatch(/can't be overridden/i);
    const save = buttonByText(/save hotkey/i);
    expect(save?.disabled).toBe(true);
    expect(readCustomHotkeys().bindings).toHaveLength(0);
    unmount();
  });
});
