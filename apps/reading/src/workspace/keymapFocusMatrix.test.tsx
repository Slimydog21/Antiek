/**
 * keymapFocusMatrix.test.tsx — MS-01 milestone 4: the focus-scope matrix.
 *
 * The contexts were enumerated before the dispatcher was written (rigor #3).
 * For each one this asserts what a PREFIX (ctrl+b then a key), a CHORD
 * (ctrl+alt+b), a legacy ⌘ combo (⌘J, and ⌘K which fires "anywhere") and a
 * PLAIN key do, against the real component that owns the context:
 *
 *   context               prefix        chord    ⌘J       ⌘K        plain key
 *   text input            not armed     fires    ignored  fires     typed ("?")
 *   contenteditable       not armed     fires    ignored  fires     typed ("?")
 *     (the Write editor)  (an element that handled a key first keeps it)
 *   FloatMenu             arms; Esc     fires    fires    fires     Esc → FloatMenu
 *                         cancels the                               (when unarmed)
 *                         prefix only
 *   WorkspaceWindow       arms; the     fires    fires    fires     ←/→ move the window
 *     (owns ←/→)          next key is
 *                         the keymap's
 *   open LemonModal       not armed     ignored  ignored  ignored   Esc → the modal
 *   the palette (modal)   not armed     ignored  ignored  CLOSES    "?" typed
 *   arXiv iframe          nothing reaches the window: nothing fires
 */
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import { act, cleanup, render } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

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
  apiFetch: vi.fn(() => Promise.resolve({ ok: false, status: 404, json: async () => ({}) })),
  postTypedEvent: vi.fn(() => Promise.resolve({ event_id: "e" })),
}));
vi.mock("../hooks/useVoiceCapture", () => ({
  useVoiceCapture: () => ({
    phase: "idle",
    error: null,
    recorderState: "idle",
    result: null,
    start: async () => {},
    stopAndCapture: async () => null,
    reset: () => {},
  }),
}));

import CommandPalette from "../components/CommandPalette";
import { LemonModal } from "../components/lemon/LemonModal";
import { WorkspaceWindow } from "../components/windows/WorkspaceWindow";
import { prefixState } from "../components/hotkeys/prefixState";
import FloatMenu from "../modes/shared/FloatMenu/FloatMenu";
import { WriteEditor } from "../modes/Write/Editor/Editor";
import { useWindows } from "./windowsStore";
import { installShortcuts } from "./shortcuts";
import { countingHandlers, pinPlatform, press, pressKey, unpinPlatform } from "./keymapTestKit";

let uninstall: (() => void) | null = null;
let counts: ReturnType<typeof countingHandlers>;

beforeEach(() => {
  pinPlatform("mac");
  counts = countingHandlers();
  uninstall = installShortcuts(vi.fn() as never, { handlers: counts.handlers });
});

afterEach(() => {
  uninstall?.();
  uninstall = null;
  cleanup();
  prefixState.disarm();
  useWindows.getState().reset();
  unpinPlatform();
  document.body.innerHTML = "";
});

/** Press ctrl+b then `next` at `target`; report whether it armed and what ran. */
function prefixThen(target: EventTarget, next: string) {
  press(target, "ctrl+b", "mac");
  const armed = prefixState.isArmed();
  const e = press(target, next, "mac");
  return { armed, e };
}

describe("text input", () => {
  it("prefix does not arm; the chord and ⌘K fire; ⌘J and '?' stay with the field", () => {
    const input = document.createElement("input");
    document.body.appendChild(input);
    input.focus();
    const { armed } = prefixThen(input, "g");
    expect(armed).toBe(false);
    expect(counts.total()).toBe(0);

    press(input, "ctrl+alt+b", "mac");
    expect(counts.calls["projecttree.toggle"]).toBe(1);
    press(input, "mod+k", "mac");
    expect(counts.calls["palette.toggle"]).toBe(1);
    const j = press(input, "mod+j", "mac");
    expect(counts.calls["door.research"]).toBe(0);
    expect(j.defaultPrevented).toBe(false);
    const q = press(input, "?", "mac");
    expect(counts.calls["keysheet.toggle"]).toBe(0);
    expect(q.defaultPrevented, "'?' must reach the field as a character").toBe(false);
  });

  it("on a Mac, ctrl+k in a field stays the field's (delete to end of line); ⌘K still opens", () => {
    const input = document.createElement("input");
    document.body.appendChild(input);
    input.focus();
    const ctrlK = pressKey(input, { key: "k", code: "KeyK", ctrlKey: true });
    expect(counts.calls["palette.toggle"]).toBe(0);
    expect(ctrlK.defaultPrevented).toBe(false);
    press(input, "mod+k", "mac");
    expect(counts.calls["palette.toggle"]).toBe(1);
  });
});

describe("text surfaces keep keys that type characters (carrier critic r1)", () => {
  /** Reinstall the dispatcher for `platform`; it reads the platform once. */
  function reinstallFor(platform: "mac" | "other") {
    uninstall?.();
    pinPlatform(platform);
    uninstall = installShortcuts(vi.fn() as never, { handlers: counts.handlers });
  }
  function focusedInput() {
    const input = document.createElement("input");
    document.body.appendChild(input);
    input.focus();
    return input;
  }

  it("off the Mac, an AltGr-composed ctrl+alt+b ('{' on Hungarian and Czech) stays with the field", () => {
    reinstallFor("other");
    const input = focusedInput();
    // Windows left ctrl+alt acts as AltGr and may not report AltGraph.
    const e = pressKey(input, { key: "{", code: "KeyB", ctrlKey: true, altKey: true });
    expect(counts.calls["projecttree.toggle"]).toBe(0);
    expect(e.defaultPrevented, "'{' must reach the field").toBe(false);
  });

  it("off the Mac, a dead key on ctrl+alt stays with the field", () => {
    reinstallFor("other");
    const input = focusedInput();
    const e = pressKey(input, { key: "Dead", code: "KeyB", ctrlKey: true, altKey: true });
    expect(counts.calls["projecttree.toggle"]).toBe(0);
    expect(e.defaultPrevented).toBe(false);
  });

  it("off the Mac, ctrl+alt+b that types nothing (a US layout) fires in the field", () => {
    reinstallFor("other");
    const input = focusedInput();
    const e = pressKey(input, { key: "b", code: "KeyB", ctrlKey: true, altKey: true });
    expect(counts.calls["projecttree.toggle"]).toBe(1);
    expect(e.defaultPrevented).toBe(true);
  });

  it("outside text the physical key rules: the same '{' press fires, since nothing can be typed", () => {
    reinstallFor("other");
    (document.activeElement as HTMLElement | null)?.blur();
    const e = pressKey(document.body, { key: "{", code: "KeyB", ctrlKey: true, altKey: true });
    expect(counts.calls["projecttree.toggle"]).toBe(1);
    expect(e.defaultPrevented).toBe(true);
  });

  it("on the Mac, ctrl+option+b fires in the field: Control-modified keys insert no text", () => {
    reinstallFor("mac");
    const input = focusedInput();
    // keyInit gives the Option glyph "∫"; with Control held Cocoa types nothing.
    const e = press(input, "ctrl+alt+b", "mac");
    expect(e.key).toBe("∫");
    expect(counts.calls["projecttree.toggle"]).toBe(1);
  });

  it("a reported AltGraph press never matches, in or out of text", () => {
    reinstallFor("other");
    const e = new KeyboardEvent("keydown", {
      bubbles: true, cancelable: true, key: "{", code: "KeyB", ctrlKey: true, altKey: true,
    });
    Object.defineProperty(e, "getModifierState", { value: (m: string) => m === "AltGraph" });
    document.body.dispatchEvent(e);
    expect(counts.calls["projecttree.toggle"]).toBe(0);
  });
});

describe("contenteditable: the Write editor", () => {
  it("prefix does not arm; the chord and ⌘K fire; ⌘J, ⌘B and '?' stay with the editor", async () => {
    const { container } = render(
      <WriteEditor deliverableId="d-1" sectionId="s-1" initialContent="<p>Words.</p>" />,
    );
    await act(async () => {});
    const editor = container.querySelector<HTMLElement>('[contenteditable="true"]')!;
    expect(editor).toBeTruthy();
    editor.focus();

    const { armed } = prefixThen(editor, "g");
    expect(armed).toBe(false);
    expect(counts.total()).toBe(0);

    press(editor, "ctrl+alt+b", "mac");
    expect(counts.calls["projecttree.toggle"]).toBe(1);
    press(editor, "mod+k", "mac");
    expect(counts.calls["palette.toggle"]).toBe(1);
    press(editor, "mod+j", "mac");
    press(editor, "mod+b", "mac");
    press(editor, "?", "mac");
    expect(counts.calls["door.research"]).toBe(0);
    expect(counts.calls["projecttree.toggle"]).toBe(1);
    expect(counts.calls["keysheet.toggle"]).toBe(0);
  });

  it("a key an element handled first (defaultPrevented) is left alone", () => {
    const div = document.createElement("div");
    div.setAttribute("contenteditable", "true");
    // Stands in for the editor's own keymap (ProseMirror prevents what it
    // handles, e.g. Mod-Alt-1 for a heading on Linux).
    div.addEventListener("keydown", (e) => e.preventDefault());
    document.body.appendChild(div);
    div.focus();
    press(div, "ctrl+alt+b", "mac");
    press(div, "mod+k", "mac");
    expect(counts.total()).toBe(0);
  });
});

describe("FloatMenu (a live reader selection)", () => {
  const selection = {
    text: "the selected passage",
    rect: { top: 200, left: 200, width: 120, height: 18 },
    provenance: {},
  };

  function mountFloatMenu() {
    const removeAllRanges = vi.fn();
    vi.spyOn(window, "getSelection").mockReturnValue({ removeAllRanges } as unknown as Selection);
    render(<FloatMenu selection={selection} investigationId="inv-1" onDeepResearch={() => {}} />);
    return removeAllRanges;
  }

  it("Esc (unarmed) is the FloatMenu's: it collapses the selection", () => {
    const removeAllRanges = mountFloatMenu();
    pressKey(document.body, { key: "Escape", code: "Escape" });
    expect(removeAllRanges).toHaveBeenCalledTimes(1);
  });

  it("while the prefix is armed, Esc cancels the prefix only; the selection stays", () => {
    const removeAllRanges = mountFloatMenu();
    press(document.body, "ctrl+b", "mac");
    expect(prefixState.isArmed()).toBe(true);
    pressKey(document.body, { key: "Escape", code: "Escape" });
    expect(prefixState.isArmed()).toBe(false);
    expect(removeAllRanges).not.toHaveBeenCalled();
  });

  it("the prefix, the chord and the ⌘ keys all work beside it", () => {
    mountFloatMenu();
    prefixThen(document.body, "g");
    expect(counts.calls["palette.toggle"]).toBe(1);
    press(document.body, "ctrl+alt+b", "mac");
    press(document.body, "mod+j", "mac");
    press(document.body, "?", "mac");
    expect(counts.calls["projecttree.toggle"]).toBe(1);
    expect(counts.calls["door.research"]).toBe(1);
    expect(counts.calls["keysheet.toggle"]).toBe(1);
  });
});

describe("a focused WorkspaceWindow (it owns ←/→)", () => {
  function mountWindow() {
    Object.defineProperty(window, "innerWidth", { value: 1440, configurable: true });
    Object.defineProperty(window, "innerHeight", { value: 900, configurable: true });
    const id = useWindows.getState().open("library", {}, { title: "Library" });
    const { container } = render(
      <WorkspaceWindow id={id}>
        <p>hosted page</p>
      </WorkspaceWindow>,
    );
    const root = container.querySelector<HTMLElement>(`[data-workspace-window='${id}']`)!;
    root.focus();
    return { id, root };
  }

  it("←/→ reach the window (it moves); the dispatcher claims neither", () => {
    const { id, root } = mountWindow();
    const x0 = useWindows.getState().windows[id].rect.x;
    const e = pressKey(root, { key: "ArrowRight", code: "ArrowRight" });
    expect(useWindows.getState().windows[id].rect.x).toBeGreaterThan(x0);
    expect(e.defaultPrevented).toBe(true); // prevented by the window itself
    expect(counts.total()).toBe(0);
  });

  it("the prefix arms from the window, and the armed prefix owns the next key (→ does not move it)", () => {
    const { id, root } = mountWindow();
    const x0 = useWindows.getState().windows[id].rect.x;
    press(root, "ctrl+b", "mac");
    expect(prefixState.isArmed()).toBe(true);
    pressKey(root, { key: "ArrowRight", code: "ArrowRight" });
    expect(useWindows.getState().windows[id].rect.x).toBe(x0);
    expect(prefixState.isArmed()).toBe(false);
  });

  it("the chord and ⌘K fire from the window; Esc is the window's (it closes)", () => {
    const { id, root } = mountWindow();
    press(root, "ctrl+alt+b", "mac");
    press(root, "mod+k", "mac");
    expect(counts.calls["projecttree.toggle"]).toBe(1);
    expect(counts.calls["palette.toggle"]).toBe(1);
    pressKey(root, { key: "Escape", code: "Escape" });
    expect(useWindows.getState().windows[id]).toBeUndefined();
  });
});

describe("an open modal (LemonModal)", () => {
  it("owns the keyboard: no prefix, no chord, no ⌘ key, no '?'; Esc closes it", async () => {
    const onClose = vi.fn();
    render(
      <LemonModal open onClose={onClose} title="Confirm">
        <button type="button">OK</button>
      </LemonModal>,
    );
    await act(async () => {});
    const focused = document.activeElement as HTMLElement;
    expect(focused.closest('[aria-modal="true"]')).toBeTruthy();

    const { armed } = prefixThen(focused, "g");
    expect(armed).toBe(false);
    press(focused, "ctrl+alt+b", "mac");
    press(focused, "mod+j", "mac");
    press(focused, "mod+k", "mac");
    press(focused, "?", "mac");
    expect(counts.total()).toBe(0);
    pressKey(focused, { key: "Escape", code: "Escape" });
    expect(onClose).toHaveBeenCalledTimes(1);
  });
});

describe("the palette (a modal that owns its toggle)", () => {
  it("⌘K from inside the palette closes it; '?' is typed into its input", async () => {
    uninstall?.();
    uninstall = installShortcuts(vi.fn() as never); // real handlers: the real toggle event
    render(
      <MemoryRouter>
        <CommandPalette />
      </MemoryRouter>,
    );
    act(() => {
      window.dispatchEvent(new Event("antiek:palette:toggle"));
    });
    const input = document.querySelector<HTMLInputElement>('[aria-label="Command palette"] input')!;
    expect(input).toBeTruthy();
    const q = press(input, "?", "mac");
    expect(q.defaultPrevented).toBe(false);
    expect(document.querySelector('[aria-label="Command palette"]')).toBeTruthy();
    act(() => {
      press(input, "mod+k", "mac");
    });
    expect(document.querySelector('[aria-label="Command palette"]')).toBeNull();
  });
});

describe("the arXiv iframe", () => {
  it("a key pressed inside the frame never reaches the window, so nothing fires", () => {
    // arxiv.org is cross-origin: the page never sees keys typed inside it. A
    // same-origin srcdoc frame is the strongest jsdom stand-in (its document
    // is a separate event target tree).
    const frame = document.createElement("iframe");
    frame.title = "arXiv paper (best-effort embed)";
    document.body.appendChild(frame);
    const inner = frame.contentDocument!;
    const KE = (frame.contentWindow as unknown as { KeyboardEvent: typeof KeyboardEvent }).KeyboardEvent;
    for (const init of [
      { key: "b", code: "KeyB", ctrlKey: true },
      { key: "∫", code: "KeyB", ctrlKey: true, altKey: true },
      { key: "k", code: "KeyK", metaKey: true },
      { key: "?", code: "Slash", shiftKey: true },
    ]) {
      inner.body.dispatchEvent(new KE("keydown", { bubbles: true, cancelable: true, ...init }));
    }
    expect(prefixState.isArmed()).toBe(false);
    expect(counts.total()).toBe(0);
  });
});
