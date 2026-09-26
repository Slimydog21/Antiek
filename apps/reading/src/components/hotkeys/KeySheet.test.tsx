/**
 * KeySheet.test.tsx — MS-01 milestone 5: the key sheet is the keymap.
 *
 * The load-bearing check: no binding in the table is missing from the
 * rendered sheet (on either platform), and nothing on the sheet is a key the
 * table does not have. Plus the herdr-style filter (`/`, ctrl+u), the
 * side-by-side prefix and direct forms, and the sheet as its own modal owner.
 */
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";
import { act, cleanup, fireEvent, render } from "@testing-library/react";

import KeySheet from "./KeySheet";
import { ACTIONS, KEYMAP, isActiveOn, type Platform } from "./keymap";
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

afterEach(() => {
  cleanup();
  window.localStorage.clear();
});

const sheet = () => document.body.querySelector('[role="dialog"]') as HTMLElement;

describe("no binding in the table is missing from the sheet", () => {
  for (const platform of ["mac", "other"] as Platform[]) {
    it(`${platform}: every active row renders, and only those`, () => {
      render(<KeySheet onClose={() => {}} platform={platform} />);
      const rendered = new Set(
        Array.from(sheet().querySelectorAll("[data-keymap-row]")).map((el) => el.getAttribute("data-keymap-row")),
      );
      const active = KEYMAP.filter((r) => isActiveOn(r, platform)).map((r) => r.id);
      for (const id of active) expect(rendered.has(id), `row ${id} missing from the sheet`).toBe(true);
      expect([...rendered].sort()).toEqual([...active].sort());
      for (const action of Object.keys(ACTIONS)) {
        expect(sheet().querySelector(`[data-keymap-action="${action}"]`), action).toBeTruthy();
      }
    });
  }

  it("shows the prefix form and the direct form of one action side by side", () => {
    render(<KeySheet onClose={() => {}} platform="mac" />);
    const row = sheet().querySelector('[data-keymap-action="projecttree.toggle"]')!;
    const [prefixCell, directCell] = Array.from(row.querySelectorAll("td"));
    // ⌃ B, then B (the "›" between them is aria-hidden decoration).
    expect(prefixCell.querySelector('[data-keymap-row="prefix-sidebar"]')!.textContent).toBe("⌃B›B");
    expect(directCell.querySelector('[data-keymap-row="projecttree"]')!.textContent).toBe("⌘B");
    expect(directCell.querySelector('[data-keymap-row="chord-sidebar"]')!.textContent).toBe("⌃⌥B");
  });

  it("off the Mac there is no ⌘B row, and modifiers read Ctrl / Alt", () => {
    render(<KeySheet onClose={() => {}} platform="other" />);
    expect(sheet().querySelector('[data-keymap-row="projecttree"]')).toBeNull();
    expect(sheet().querySelector('[data-keymap-row="chord-sidebar"]')!.textContent).toBe("CtrlAltB");
  });
});

describe("the filter (herdr keybind-help semantics)", () => {
  it("'/' moves focus to the filter; typing narrows the rows; ctrl+u clears", async () => {
    render(<KeySheet onClose={() => {}} platform="mac" />);
    await act(async () => {});
    const input = sheet().querySelector<HTMLInputElement>('input[aria-label="Filter shortcuts"]')!;
    const close = sheet().querySelector<HTMLButtonElement>('button[aria-label="Close"]')!;
    close.focus();
    fireEvent.keyDown(close, { key: "/" });
    expect(document.activeElement).toBe(input);

    fireEvent.change(input, { target: { value: "sidecar" } });
    const actions = Array.from(sheet().querySelectorAll("[data-keymap-action]")).map((el) =>
      el.getAttribute("data-keymap-action"),
    );
    expect(actions).toEqual(["aisidecar.toggle"]);

    fireEvent.keyDown(input, { key: "u", ctrlKey: true });
    expect(input.value).toBe("");
    expect(sheet().querySelectorAll("[data-keymap-action]").length).toBe(Object.keys(ACTIONS).length);
  });

  it("filters by key as well as by name, and says so when nothing matches", () => {
    render(<KeySheet onClose={() => {}} platform="mac" />);
    const input = sheet().querySelector<HTMLInputElement>('input[aria-label="Filter shortcuts"]')!;
    fireEvent.change(input, { target: { value: "ctrl+alt" } });
    // Every ctrl+alt chord row: the sidebar's plus the C3 pane/preset twins,
    // the D6 tab-tree twins, and the C4 companion twins (retargeted to
    // ctrl+alt+, / ctrl+alt+. when the tree took the bracket pair).
    expect(Array.from(sheet().querySelectorAll("[data-keymap-action]")).map((e) => e.getAttribute("data-keymap-action"))).toEqual([
      "projecttree.toggle",
      "pane.focusLeft",
      "pane.focusRight",
      "pane.fullscreen",
      "layout.togglePreset",
      "companion.nextTab",
      "companion.prevTab",
      "tab.nextSibling",
      "tab.prevSibling",
      "tab.parent",
      "tab.visitChild",
      "tab.close",
      "tab.treeToggle",
    ]);
    fireEvent.change(input, { target: { value: "zzz-nothing" } });
    expect(sheet().textContent).toContain("No shortcut matches");
  });
});

describe("custom hotkeys and ownership", () => {
  it("lists the operator's custom bindings, and states plainly when there are none", () => {
    const { unmount } = render(<KeySheet onClose={() => {}} platform="mac" />);
    expect(sheet().textContent).toMatch(/haven.t assigned any custom hotkeys/i);
    unmount();
    writeCustomHotkeys({
      schemaVersion: 1,
      bindings: [
        { id: "c1", spec: "alt+j", route: "/inv/x", entityId: "x", entityKind: "investigation", label: "My pinned research" },
      ],
    });
    render(<KeySheet onClose={() => {}} platform="mac" />);
    expect(sheet().textContent).toContain("My pinned research");
  });

  it("names itself the owner of the key-sheet toggle, so '?' inside it closes it", () => {
    render(<KeySheet onClose={() => {}} platform="mac" />);
    expect(sheet().querySelector('[data-keymap-owner="keysheet.toggle"]')).toBeTruthy();
  });

  it("Esc closes it (the modal's own key)", async () => {
    const onClose = vi.fn();
    render(<KeySheet onClose={onClose} platform="mac" />);
    await act(async () => {});
    fireEvent.keyDown(window, { key: "Escape" });
    expect(onClose).toHaveBeenCalledTimes(1);
  });
});
