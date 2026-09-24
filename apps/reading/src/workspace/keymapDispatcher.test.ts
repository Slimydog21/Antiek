/**
 * keymapDispatcher.test.ts — MS-01 milestone 4: the one dispatcher.
 *
 *  1. Every legacy binding still works: one test per legacy-SPR-08 row, with
 *     the REAL handlers, asserting the real effect (navigation, the palette
 *     and help events, the workspace store).
 *  2. The prefix engine: ctrl+b arms, the next key runs its row and disarms,
 *     Esc cancels, there is no timeout, a lone Shift is part of prefix+?, and
 *     the armed prefix owns the next key alone.
 *  3. Chords match the physical key (e.code), never the composed character.
 *  4. Fuzz: every row of the table, pressed from every focus context, reaches
 *     at most one handler, and from the page body exactly its own.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { KEYMAP, isActiveOn, readPrefix, type KeymapRow, type Platform } from "../components/hotkeys/keymap";
import { prefixState } from "../components/hotkeys/prefixState";
import { PRODUCT_ACTIVATE_EVENT, type ProductActivateDetail } from "../components/hotkeys/bindings";
import { SHORTCUT_EVENTS, installShortcuts, setCustomHotkeys } from "./shortcuts";
import { useWorkspace } from "./WorkspaceStore";
import { countingHandlers, pinPlatform, press, pressKey, unpinPlatform } from "./keymapTestKit";

let uninstall: (() => void) | null = null;

afterEach(() => {
  uninstall?.();
  uninstall = null;
  unpinPlatform();
  prefixState.disarm();
  setCustomHotkeys([]);
  useWorkspace.getState().reset();
  document.body.innerHTML = "";
  vi.useRealTimers();
});

function listen(name: string) {
  const spy = vi.fn();
  window.addEventListener(name, spy);
  return { spy, off: () => window.removeEventListener(name, spy) };
}

// ─────────────────────────────────────────────────────────────────────
// 1. every legacy binding still works (real handlers, real effects)
// ─────────────────────────────────────────────────────────────────────

type Probe = (platform: Platform) => void;

function legacyProbe(row: KeymapRow): Probe {
  return (platform) => {
    const navigate = vi.fn();
    uninstall = installShortcuts(navigate as never);
    const activations: ProductActivateDetail[] = [];
    const onActivate = (e: Event) => activations.push((e as CustomEvent<ProductActivateDetail>).detail);
    window.addEventListener(PRODUCT_ACTIVATE_EVENT, onActivate);
    const palette = listen(SHORTCUT_EVENTS.PALETTE_TOGGLE);
    const help = listen(SHORTCUT_EVENTS.HELP_TOGGLE);
    const ws = useWorkspace.getState;
    if (row.action === "panel.focusPrev" || row.action === "panel.focusNext") {
      ws().open("Notes", {}, { mode: "docked-left", id: "p:a" });
      ws().open("Notes", {}, { mode: "docked-right", id: "p:b" });
      ws().focus("p:a");
    }
    if (row.action === "panel.closeFloating") {
      ws().open("Notes", {}, { mode: "floating", id: "p:float" });
      ws().focus("p:float");
    }

    const e = press(document.body, row.chord!, platform);

    window.removeEventListener(PRODUCT_ACTIVATE_EVENT, onActivate);
    palette.off();
    help.off();
    expect(e.defaultPrevented, `${row.chord} is handled, so its browser default is prevented`).toBe(true);
    switch (row.action) {
      case "palette.toggle":
        expect(palette.spy).toHaveBeenCalledTimes(1);
        break;
      case "keysheet.toggle":
        expect(help.spy).toHaveBeenCalledTimes(1);
        break;
      case "projecttree.toggle":
        expect(ws().dockLeftIds).toContain("shortcuts:projecttree");
        break;
      case "aisidecar.toggle":
        expect(ws().dockRightIds).toContain("shortcuts:aisidecar");
        break;
      case "panel.focusPrev":
        expect(ws().focusedPanelId).toBe("p:b");
        break;
      case "panel.focusNext":
        expect(ws().focusedPanelId).toBe("p:b");
        break;
      case "panel.closeFloating":
        expect(ws().panels["p:float"]).toBeUndefined();
        break;
      default: {
        // A product door: navigates (when it has a route) and emits the
        // activation a click emits.
        expect(activations).toHaveLength(1);
        expect(activations[0].source).toBe("hotkey");
        const route = activations[0].route;
        if (route) expect(navigate).toHaveBeenCalledWith(route);
        else expect(navigate).not.toHaveBeenCalled();
      }
    }
  };
}

const legacyRows = KEYMAP.filter((r) => r.origin === "legacy-SPR-08" && r.chord);

describe("every legacy binding still works (one test per binding, real handlers)", () => {
  for (const platform of ["mac", "other"] as const) {
    const rows = legacyRows.filter((r) => isActiveOn(r, platform));
    it.each(rows.map((r) => [r.chord!, r.action, r] as const))(
      `${platform}: %s → %s`,
      (_chord, _action, row) => {
        pinPlatform(platform);
        legacyProbe(row)(platform);
      },
    );
  }

  it("⌘W with no floating panel focused is left to the browser (not prevented)", () => {
    uninstall = installShortcuts(vi.fn() as never);
    const e = press(document.body, "mod+w", "other");
    expect(e.defaultPrevented).toBe(false);
  });

  it("off the Mac, ⌘B (Win+B) is not bound; ctrl+b is the prefix", () => {
    pinPlatform("other");
    uninstall = installShortcuts(vi.fn() as never);
    press(document.body, "meta+b", "other");
    expect(useWorkspace.getState().panels["shortcuts:projecttree"]).toBeUndefined();
    press(document.body, "ctrl+b", "other");
    expect(prefixState.isArmed()).toBe(true);
  });
});

// ─────────────────────────────────────────────────────────────────────
// 2. the prefix engine
// ─────────────────────────────────────────────────────────────────────

describe("the prefix engine (herdr semantics)", () => {
  beforeEach(() => pinPlatform("mac"));

  it("defaults to ctrl+b", () => {
    expect(readPrefix()).toBe("ctrl+b");
  });

  it("ctrl+b arms; the next key runs its prefix row and disarms", () => {
    const { handlers, calls } = countingHandlers();
    uninstall = installShortcuts(vi.fn() as never, { handlers });
    const arm = press(document.body, "ctrl+b", "mac");
    expect(arm.defaultPrevented).toBe(true);
    expect(prefixState.isArmed()).toBe(true);
    press(document.body, "g", "mac");
    expect(calls["palette.toggle"]).toBe(1);
    expect(prefixState.isArmed()).toBe(false);
  });

  it("stays armed with no timeout (a minute later the next key still goes to the keymap)", () => {
    vi.useFakeTimers();
    const { handlers, calls } = countingHandlers();
    uninstall = installShortcuts(vi.fn() as never, { handlers });
    press(document.body, "ctrl+b", "mac");
    vi.advanceTimersByTime(60_000);
    expect(prefixState.isArmed()).toBe(true);
    press(document.body, "b", "mac");
    expect(calls["projecttree.toggle"]).toBe(1);
  });

  it("Esc disarms and runs nothing", () => {
    const { handlers, total } = countingHandlers();
    uninstall = installShortcuts(vi.fn() as never, { handlers });
    press(document.body, "ctrl+b", "mac");
    const esc = pressKey(document.body, { key: "Escape", code: "Escape" });
    expect(esc.defaultPrevented).toBe(true);
    expect(prefixState.isArmed()).toBe(false);
    expect(total()).toBe(0);
  });

  it("prefix+? : the Shift keydown does not disarm; '?' opens the key sheet", () => {
    const { handlers, calls } = countingHandlers();
    uninstall = installShortcuts(vi.fn() as never, { handlers });
    press(document.body, "ctrl+b", "mac");
    pressKey(document.body, { key: "Shift", code: "ShiftLeft", shiftKey: true });
    expect(prefixState.isArmed()).toBe(true);
    press(document.body, "?", "mac");
    expect(calls["keysheet.toggle"]).toBe(1);
  });

  it("an unbound next key is swallowed and disarms (nothing else sees it)", () => {
    const { handlers, total } = countingHandlers();
    uninstall = installShortcuts(vi.fn() as never, { handlers });
    const other = vi.fn();
    window.addEventListener("keydown", other);
    press(document.body, "ctrl+b", "mac");
    const k = press(document.body, "q", "mac");
    window.removeEventListener("keydown", other);
    expect(k.defaultPrevented).toBe(true);
    expect(other).not.toHaveBeenCalled();
    expect(total()).toBe(0);
    expect(prefixState.isArmed()).toBe(false);
  });

  it("a key reserved for a later sprint (prefix+1) is swallowed, not passed on", () => {
    const { handlers, total } = countingHandlers();
    uninstall = installShortcuts(vi.fn() as never, { handlers });
    press(document.body, "ctrl+b", "mac");
    const k = press(document.body, "1", "mac");
    expect(k.defaultPrevented).toBe(true);
    expect(total()).toBe(0);
  });

  it("pressing the prefix again cancels it; a held (repeating) prefix does not toggle", () => {
    uninstall = installShortcuts(vi.fn() as never);
    press(document.body, "ctrl+b", "mac");
    press(document.body, "ctrl+b", "mac", { repeat: true });
    expect(prefixState.isArmed()).toBe(false);
    press(document.body, "ctrl+b", "mac", { repeat: true });
    expect(prefixState.isArmed()).toBe(false);
  });

  it("if focus moves into a text field or a dialog while armed, the key is the field's (critic r1 #1)", () => {
    const { handlers, total } = countingHandlers();
    uninstall = installShortcuts(vi.fn() as never, { handlers });
    press(document.body, "ctrl+b", "mac");
    expect(prefixState.isArmed()).toBe(true);
    const input = document.createElement("input");
    document.body.appendChild(input);
    input.focus();
    const g = press(input, "g", "mac");
    expect(g.defaultPrevented, "the typed 'g' must reach the field").toBe(false);
    expect(total()).toBe(0);
    expect(prefixState.isArmed()).toBe(false);

    press(document.body, "ctrl+b", "mac");
    const dialog = document.createElement("div");
    dialog.setAttribute("aria-modal", "true");
    const button = document.createElement("button");
    dialog.appendChild(button);
    document.body.appendChild(dialog);
    button.focus();
    const esc = pressKey(button, { key: "Escape", code: "Escape" });
    expect(esc.defaultPrevented, "the dialog's Esc is the dialog's").toBe(false);
    expect(prefixState.isArmed()).toBe(false);
  });

  it("leaving the window (focus into an iframe or another app) disarms", () => {
    uninstall = installShortcuts(vi.fn() as never);
    press(document.body, "ctrl+b", "mac");
    window.dispatchEvent(new Event("blur"));
    expect(prefixState.isArmed()).toBe(false);
  });

  it("a configured prefix replaces ctrl+b", () => {
    window.localStorage.setItem("antiek.keymap.prefix", "ctrl+a");
    try {
      const { handlers, calls } = countingHandlers();
      uninstall = installShortcuts(vi.fn() as never, { handlers });
      press(document.body, "ctrl+b", "mac");
      expect(prefixState.isArmed()).toBe(false);
      press(document.body, "ctrl+a", "mac");
      expect(prefixState.isArmed()).toBe(true);
      press(document.body, "g", "mac");
      expect(calls["palette.toggle"]).toBe(1);
    } finally {
      window.localStorage.removeItem("antiek.keymap.prefix");
    }
  });
});

// ─────────────────────────────────────────────────────────────────────
// 3. chords match the physical key
// ─────────────────────────────────────────────────────────────────────

describe("ctrl+alt chords match KeyboardEvent.code", () => {
  it("ctrl+alt+b fires on a Mac although option composed e.key into '∫'", () => {
    pinPlatform("mac");
    const { handlers, calls } = countingHandlers();
    uninstall = installShortcuts(vi.fn() as never, { handlers });
    const e = pressKey(document.body, { key: "∫", code: "KeyB", ctrlKey: true, altKey: true });
    expect(calls["projecttree.toggle"]).toBe(1);
    expect(e.defaultPrevented).toBe(true);
  });

  it("plain alt+b (option+b) never fires: macOS types '∫' with it", () => {
    const { handlers, total } = countingHandlers();
    uninstall = installShortcuts(vi.fn() as never, { handlers });
    const e = pressKey(document.body, { key: "∫", code: "KeyB", altKey: true });
    expect(total()).toBe(0);
    expect(e.defaultPrevented).toBe(false);
  });

  it("an AltGr press (ctrl+alt reported as AltGraph) is a character, not a chord", () => {
    const { handlers, total } = countingHandlers();
    uninstall = installShortcuts(vi.fn() as never, { handlers });
    const e = new KeyboardEvent("keydown", {
      key: "{",
      code: "KeyB",
      ctrlKey: true,
      altKey: true,
      bubbles: true,
      cancelable: true,
      modifierAltGraph: true,
    } as KeyboardEventInit);
    document.body.dispatchEvent(e);
    expect(total()).toBe(0);
  });
});

// ─────────────────────────────────────────────────────────────────────
// 4. fuzz: every row, every context, at most one handler
// ─────────────────────────────────────────────────────────────────────

type Ctx = "body" | "input" | "contenteditable" | "modal" | "palette-modal";

function mountContext(ctx: Ctx): HTMLElement {
  if (ctx === "body") return document.body;
  if (ctx === "input") {
    const input = document.createElement("input");
    document.body.appendChild(input);
    input.focus();
    return input;
  }
  if (ctx === "contenteditable") {
    const div = document.createElement("div");
    div.setAttribute("contenteditable", "true");
    document.body.appendChild(div);
    div.focus();
    return div;
  }
  const dialog = document.createElement("div");
  dialog.setAttribute("role", "dialog");
  dialog.setAttribute("aria-modal", "true");
  if (ctx === "palette-modal") dialog.setAttribute("data-keymap-owner", "palette.toggle");
  const button = document.createElement("button");
  dialog.appendChild(button);
  document.body.appendChild(dialog);
  button.focus();
  return button;
}

/** What the scope rules say a row does from each context. */
function expectedFires(row: KeymapRow, ctx: Ctx): boolean {
  if (row.prefixKey) return ctx === "body";
  if (ctx === "body") return true;
  if (ctx === "input" || ctx === "contenteditable") return row.scope === "anywhere";
  if (ctx === "palette-modal") return row.action === "palette.toggle";
  return false;
}

describe("fuzz: no key reaches two handlers, and every row reaches its own", () => {
  const contexts: Ctx[] = ["body", "input", "contenteditable", "modal", "palette-modal"];
  for (const platform of ["mac", "other"] as const) {
    const rows = KEYMAP.filter((r) => isActiveOn(r, platform));
    for (const ctx of contexts) {
      it(`${platform} · ${ctx}: ${rows.length} rows`, () => {
        pinPlatform(platform);
        const { handlers, calls, total } = countingHandlers();
        uninstall = installShortcuts(vi.fn() as never, { handlers });
        // A late window listener stands in for any other keydown owner.
        const late = vi.fn();
        window.addEventListener("keydown", late);
        try {
          for (const row of rows) {
            for (const k of Object.keys(calls)) calls[k] = 0;
            late.mockClear();
            prefixState.disarm();
            document.body.innerHTML = "";
            const target = mountContext(ctx);
            let last: KeyboardEvent;
            if (row.prefixKey) {
              press(target, readPrefix(), platform);
              last = press(target, row.prefixKey, platform);
            } else {
              last = press(target, row.chord!, platform);
            }
            const fires = expectedFires(row, ctx);
            const label = `${row.id} (${row.prefixKey ? `prefix+${row.prefixKey}` : row.chord}) from ${ctx}`;
            expect(total(), `${label}: handler count`).toBe(fires ? 1 : 0);
            if (fires) {
              expect(calls[row.action], `${label}: ran its own action`).toBe(1);
              expect(late, `${label}: reached a second owner`).not.toHaveBeenCalled();
              expect(last.defaultPrevented, `${label}: default prevented`).toBe(true);
            }
            expect(prefixState.isArmed(), `${label}: left the prefix armed`).toBe(false);
          }
        } finally {
          window.removeEventListener("keydown", late);
        }
      });
    }
  }
});
