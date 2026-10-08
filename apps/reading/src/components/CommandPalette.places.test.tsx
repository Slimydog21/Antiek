/**
 * CommandPalette.places.test.tsx — SPR-02 M2/M3
 * (specs/antiek-keyboard-panes-agents-20261007/sprint-02-launcher.html).
 *
 * The Switcher gains PLACES sections behind `antiek.flag.switcher.places`.
 * Contract under test:
 *   - flag off: the DOM has no section chips and no section lists (parity);
 *   - flag on: Doors/Scenes/Open sections render, an Open row for a window
 *     carries the store's id, Enter on it calls windowsStore.focus(id) once
 *     and windowsStore.open never (pane-flow contract S01/S09/S10);
 *   - a bare letter in the box searches, it never filters;
 *   - `in:open` narrows to the Open section; Tab cycles sections;
 *   - keyboard-only: open → type → ↓ → Enter, no click anywhere.
 *
 * What this does NOT prove (recorded, not hidden): that DOM focus lands
 * inside the window host after focus(id). WindowsLayer is not mounted here
 * and on main the store's focus() is the host's own command; the pane-flow
 * packet (SPR-01) is where "no hidden successful consumption" becomes a DOM
 * assertion for windows.
 */
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

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

vi.mock("../lib/api", async (orig) => ({
  ...(await orig<typeof import("../lib/api")>()),
  apiFetch: vi.fn(() => Promise.resolve({ ok: false, status: 404, json: async () => ({}) })),
}));

import CommandPalette from "./CommandPalette";
import { setFeatureFlag } from "../lib/featureFlags";
import { useWindows } from "../workspace/windowsStore";
import { useWorkspace } from "../workspace/WorkspaceStore";
import { useCompanion } from "../workspace/companionStore";

function mount() {
  return render(
    <MemoryRouter initialEntries={["/"]}>
      <CommandPalette />
    </MemoryRouter>,
  );
}

function openPalette() {
  act(() => {
    window.dispatchEvent(new CustomEvent("antiek:palette:toggle"));
  });
  return screen.getByRole("dialog", { name: "Command palette" });
}

function key(el: Element, init: KeyboardEventInit) {
  fireEvent.keyDown(el, { bubbles: true, cancelable: true, ...init });
}

beforeEach(() => {
  window.localStorage.clear();
  useWindows.getState().reset();
  useWorkspace.getState().reset();
  useCompanion.getState().reset();
});

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe("flag off — parity", () => {
  it("renders no section chips and no section lists", () => {
    setFeatureFlag("switcher.places", false);
    mount();
    const dialog = openPalette();
    expect(within(dialog).queryByTestId("switcher-section-chips")).toBeNull();
    expect(within(dialog).queryByTestId("switcher-section-doors")).toBeNull();
    // The legacy "Go to Read" jump action is still a plain row.
    expect(within(dialog).getByText("Go to Read")).toBeTruthy();
  });
});

describe("flag on — places sections", () => {
  beforeEach(() => setFeatureFlag("switcher.places", true));

  it("renders Doors, Scenes and Open sections; Open rows carry the stores' ids by reference", () => {
    const a = useWindows.getState().open("reader", { documentId: "doc-a" }, { title: "Paper A", id: "win-a" });
    const b = useWindows.getState().open("notebook", {}, { title: "Notes B", id: "win-b" });
    expect([a, b]).toEqual(["win-a", "win-b"]);
    mount();
    const dialog = openPalette();
    expect(within(dialog).getByTestId("switcher-section-doors")).toBeTruthy();
    expect(within(dialog).getByTestId("switcher-section-scenes")).toBeTruthy();
    const open = within(dialog).getByTestId("switcher-section-open");
    expect(within(open).getByText("Paper A")).toBeTruthy();
    expect(within(open).getByText("Notes B")).toBeTruthy();
    // The focused window (the last opened) is marked as "here".
    const here = within(open).getAllByLabelText("current");
    expect(here).toHaveLength(1);
    // Doors are not ALSO listed as legacy "Go to" actions (no double hits).
    expect(within(dialog).queryByText("Go to Read")).toBeNull();
  });

  it("keyboard-only: in:open, ↓, Enter focuses the window through windowsStore.focus and never open()", () => {
    useWindows.getState().open("reader", {}, { title: "Paper A", id: "win-a" });
    useWindows.getState().open("notebook", {}, { title: "Notes B", id: "win-b" });
    const focus = vi.spyOn(useWindows.getState(), "focus");
    const open = vi.spyOn(useWindows.getState(), "open");
    mount();
    const dialog = openPalette();
    const input = within(dialog).getByRole("textbox");
    fireEvent.change(input, { target: { value: "in:open" } });
    // Order inside Open: current (win-b, last opened) first, then win-a.
    key(input, { key: "ArrowDown" });
    key(input, { key: "Enter" });
    expect(focus).toHaveBeenCalledTimes(1);
    expect(focus).toHaveBeenCalledWith("win-a");
    expect(open).not.toHaveBeenCalled();
    // Choosing closes the Switcher.
    expect(screen.queryByRole("dialog", { name: "Command palette" })).toBeNull();
  });

  it("a bare first letter searches; it never filters", () => {
    useWindows.getState().open("reader", {}, { title: "Paper A", id: "win-a" });
    mount();
    const dialog = openPalette();
    const input = within(dialog).getByRole("textbox") as HTMLInputElement;
    fireEvent.change(input, { target: { value: "r" } });
    expect(input.value).toBe("r");
    // "r" matches the Read/Research doors by text; Open's "Paper A" has an r too.
    expect(within(dialog).getByTestId("switcher-section-doors")).toBeTruthy();
    const chips = within(dialog).getByTestId("switcher-section-chips");
    expect(within(chips).getByRole("button", { name: "all" }).getAttribute("aria-pressed")).toBe("true");
  });

  it("in:open narrows to the Open section; the chip reflects it", () => {
    useWindows.getState().open("reader", {}, { title: "Paper A", id: "win-a" });
    mount();
    const dialog = openPalette();
    const input = within(dialog).getByRole("textbox");
    fireEvent.change(input, { target: { value: "in:open" } });
    expect(within(dialog).queryByTestId("switcher-section-doors")).toBeNull();
    expect(within(dialog).getByTestId("switcher-section-open")).toBeTruthy();
    const chips = within(dialog).getByTestId("switcher-section-chips");
    expect(within(chips).getByRole("button", { name: "open" }).getAttribute("aria-pressed")).toBe("true");
  });

  it("Tab cycles the section filter and keeps focus in the box; Shift+Tab reverses", () => {
    useWindows.getState().open("reader", {}, { title: "Paper A", id: "win-a" });
    mount();
    const dialog = openPalette();
    const input = within(dialog).getByRole("textbox") as HTMLInputElement;
    key(input, { key: "Tab" });
    expect(input.value).toBe("in:doors");
    key(input, { key: "Tab" });
    expect(input.value).toBe("in:scenes");
    key(input, { key: "Tab", shiftKey: true });
    expect(input.value).toBe("in:doors");
    key(input, { key: "Tab", shiftKey: true });
    expect(input.value).toBe("");
  });

  it("Enter on a companion tab row activates it through companionStore, by id", () => {
    const id = useCompanion.getState().openAgentTab({ kind: "dialogue", title: "Ask the project agent" });
    const activate = vi.spyOn(useCompanion.getState(), "activateAgentTab");
    mount();
    const dialog = openPalette();
    const input = within(dialog).getByRole("textbox");
    fireEvent.change(input, { target: { value: "in:open ask the project" } });
    key(input, { key: "Enter" });
    expect(activate).toHaveBeenCalledWith(id);
  });
});

describe("keyboard contract (critique F1–F4, both flag states)", () => {
  it.each([false, true])("close returns focus to the opener (flag=%s)", async (flag) => {
    setFeatureFlag("switcher.places", flag);
    const opener = document.createElement("button");
    opener.textContent = "opener";
    document.body.appendChild(opener);
    opener.focus();
    expect(document.activeElement).toBe(opener);
    mount();
    const dialog = openPalette();
    const input = within(dialog).getByRole("textbox");
    // The palette focuses its input on a 0 ms timer; the test is vacuous
    // unless focus has actually LEFT the opener before Escape (a mutant with
    // no restore passed the first version of this test for exactly that
    // reason — recorded in the PR).
    await waitFor(() => expect(document.activeElement).toBe(input));
    key(input, { key: "Escape" });
    expect(screen.queryByRole("dialog", { name: "Command palette" })).toBeNull();
    expect(document.activeElement).toBe(opener);
    opener.remove();
  });

  it("Esc clears a non-empty query first, then closes (R14)", () => {
    setFeatureFlag("switcher.places", true);
    mount();
    const dialog = openPalette();
    const input = within(dialog).getByRole("textbox") as HTMLInputElement;
    fireEvent.change(input, { target: { value: "in:open" } });
    key(input, { key: "Escape" });
    expect(input.value).toBe("");
    expect(screen.getByRole("dialog", { name: "Command palette" })).toBeTruthy();
    key(input, { key: "Escape" });
    expect(screen.queryByRole("dialog", { name: "Command palette" })).toBeNull();
  });

  it("with text in the box, j is not navigation: Enter still chooses the first (current) Open row", () => {
    setFeatureFlag("switcher.places", true);
    useWindows.getState().open("reader", {}, { title: "Paper A", id: "win-a" });
    useWindows.getState().open("notebook", {}, { title: "Notes B", id: "win-b" });
    const focus = vi.spyOn(useWindows.getState(), "focus");
    mount();
    const dialog = openPalette();
    const input = within(dialog).getByRole("textbox") as HTMLInputElement;
    fireEvent.change(input, { target: { value: "in:open" } });
    key(input, { key: "j" });
    key(input, { key: "Enter" });
    expect(focus).toHaveBeenCalledWith("win-b");
  });

  it("with an empty box, j/k move one row and PageDown/PageUp move six, bounded", () => {
    setFeatureFlag("switcher.places", true);
    mount();
    const dialog = openPalette();
    const input = within(dialog).getByRole("textbox") as HTMLInputElement;
    const highlighted = () => dialog.querySelector('li[class*="bg-ice-3"]')?.textContent ?? "";
    expect(highlighted()).toContain("Research"); // first door
    key(input, { key: "j" });
    expect(highlighted()).toContain("Read");
    key(input, { key: "k" });
    expect(highlighted()).toContain("Research");
    key(input, { key: "PageDown" });
    expect(highlighted()).toContain("Scene"); // index 6 is past the four doors
    key(input, { key: "PageUp" });
    expect(highlighted()).toContain("Research");
    key(input, { key: "k" }); // bounded at 0
    expect(highlighted()).toContain("Research");
    expect(input.value).toBe("");
  });
});
