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

  it("opens a capture dialog and saves a free modifier-combo, persisting it", () => {
    const { unmount } = render(<AssignHotkey {...PROPS} />);
    fireEvent.click(buttonByText(/assign hotkey/i)!);
    const dialog = document.body.querySelector('[role="dialog"]');
    expect(dialog).toBeTruthy();

    // Capture a free modifier-combo (a custom binding must carry a modifier —
    // a bare single key would hijack the app-wide handler; see
    // requiresModifierReason in bindings.ts).
    const capture = dialog!.querySelector('[role="textbox"]') as HTMLElement;
    expect(capture).toBeTruthy();
    fireEvent.keyDown(capture, { key: "j", altKey: true });
    expect(dialog!.textContent).toMatch(/is available/i);

    // Save.
    fireEvent.click(buttonByText(/save hotkey/i)!);
    expect(readCustomHotkeys().bindings[0]?.spec).toBe("alt+j");
    expect(readCustomHotkeys().bindings[0]?.entityId).toBe("inv-9");
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
