import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";

import {
  installShortcuts,
  setCustomHotkeys,
  getCustomHotkeys,
  SHORTCUT_EVENTS,
} from "./shortcuts";
import { writeCustomHotkeys } from "./persistence";
import {
  PRODUCT_ACTIVATE_EVENT,
  emitProductActivate,
  type ProductActivateDetail,
} from "../components/hotkeys/bindings";

/** Helper: dispatch a keydown on window, optionally from a text-editing
 *  element so we can exercise the isTextEditing guard. */
function press(
  key: string,
  opts: Partial<KeyboardEventInit> & { fromInput?: boolean } = {},
) {
  const { fromInput, ...init } = opts;
  const target = fromInput ? document.createElement("input") : window;
  const event = new KeyboardEvent("keydown", {
    key,
    bubbles: true,
    cancelable: true,
    ...init,
  });
  if (fromInput) {
    document.body.appendChild(target as HTMLElement);
    (target as HTMLElement).dispatchEvent(event);
    (target as HTMLElement).remove();
  } else {
    window.dispatchEvent(event);
  }
  return event;
}

describe("shortcuts handler — SPR-08 (uniform ⌘+key, no chords)", () => {
  let navigate: ReturnType<typeof vi.fn>;
  let uninstall: () => void;

  beforeEach(() => {
    navigate = vi.fn();
    setCustomHotkeys([]);
    uninstall = installShortcuts(navigate as never);
  });

  afterEach(() => {
    uninstall();
    vi.useRealTimers();
    setCustomHotkeys([]);
  });

  // ── product ⌘+key navigates (one modifier, one keypress) ──────────────
  it("⌘E navigates to Read (/library)", () => {
    press("e", { metaKey: true });
    expect(navigate).toHaveBeenCalledWith("/library");
  });

  it("⌘J navigates to Research (/)", () => {
    press("j", { metaKey: true });
    expect(navigate).toHaveBeenCalledWith("/");
  });

  it("⌘Y navigates to Write, ⌘U to Speak, ⌘O to Home", () => {
    press("y", { metaKey: true });
    expect(navigate).toHaveBeenCalledWith("/write");
    press("u", { metaKey: true });
    expect(navigate).toHaveBeenCalledWith("/speak");
    press("o", { metaKey: true });
    expect(navigate).toHaveBeenCalledWith("/home");
  });

  it("Ctrl+E works too (mod === Cmd-on-mac / Ctrl-elsewhere)", () => {
    press("e", { ctrlKey: true });
    expect(navigate).toHaveBeenCalledWith("/library");
  });

  // ── the chord is DEAD — pressing g then a letter does NOTHING ──────────
  it("the old g-chord does nothing (g then e → no nav)", () => {
    press("g");
    press("e");
    expect(navigate).not.toHaveBeenCalled();
  });

  it("a bare 'g' alone does nothing (no pending-chord state exists)", () => {
    press("g");
    expect(navigate).not.toHaveBeenCalled();
  });

  it("the old g i / g w / g n chords are all dead", () => {
    for (const k of ["i", "w", "n", "r"]) {
      press("g");
      press(k);
    }
    expect(navigate).not.toHaveBeenCalled();
  });

  // ── isTextEditing guard (editor/PDF surfaces keep their keys) ──────────
  it("does NOT fire a product combo while typing in an input", () => {
    press("e", { metaKey: true, fromInput: true });
    expect(navigate).not.toHaveBeenCalled();
  });

  it("does NOT open the HUD with ? while typing", () => {
    const spy = vi.fn();
    window.addEventListener(SHORTCUT_EVENTS.HELP_TOGGLE, spy);
    press("?", { fromInput: true });
    expect(spy).not.toHaveBeenCalled();
    window.removeEventListener(SHORTCUT_EVENTS.HELP_TOGGLE, spy);
  });

  // ── click≡hotkey parity: hotkey === click (same activation event) ──────
  it("firing a product hotkey emits the SAME event a click emits", () => {
    const fromHotkey: ProductActivateDetail[] = [];
    const fromClick: ProductActivateDetail[] = [];
    const listener = (e: Event) => {
      const detail = (e as CustomEvent<ProductActivateDetail>).detail;
      (detail.source === "hotkey" ? fromHotkey : fromClick).push(detail);
    };
    window.addEventListener(PRODUCT_ACTIVATE_EVENT, listener);

    // Hotkey path: ⌘E → Read
    press("e", { metaKey: true });
    // Click path: a button handler calls emitProductActivate directly.
    emitProductActivate({ productId: "read", route: "/library", source: "click" });

    window.removeEventListener(PRODUCT_ACTIVATE_EVENT, listener);

    expect(fromHotkey).toHaveLength(1);
    expect(fromClick).toHaveLength(1);
    expect(fromHotkey[0].productId).toBe(fromClick[0].productId);
    expect(fromHotkey[0].route).toBe(fromClick[0].route);
  });

  it("⌘J fires Research product activation AND navigates home", () => {
    const spy = vi.fn();
    window.addEventListener(PRODUCT_ACTIVATE_EVENT, spy);
    press("j", { metaKey: true });
    expect(navigate).toHaveBeenCalledWith("/");
    expect(spy).toHaveBeenCalledTimes(1);
    window.removeEventListener(PRODUCT_ACTIVATE_EVENT, spy);
  });

  it("⌘I (More) emits a routeless activation and does NOT navigate", () => {
    // ⌘I, not ⌘M: ⌘M shadows macOS minimize-window (reserved), so More is ⌘I.
    const fired: ProductActivateDetail[] = [];
    const listener = (e: Event) =>
      fired.push((e as CustomEvent<ProductActivateDetail>).detail);
    window.addEventListener(PRODUCT_ACTIVATE_EVENT, listener);
    press("i", { metaKey: true });
    window.removeEventListener(PRODUCT_ACTIVATE_EVENT, listener);
    expect(navigate).not.toHaveBeenCalled();
    expect(fired).toHaveLength(1);
    expect(fired[0].productId).toBe("more");
    expect(fired[0].route).toBeUndefined();
  });

  // ── sub-action ⌘+key ──────────────────────────────────────────────────
  it("⌘G goes to the Research home (sub-action)", () => {
    press("g", { metaKey: true });
    expect(navigate).toHaveBeenCalledWith("/");
  });

  // ── ? toggles the HUD ────────────────────────────────────────────────
  it("? dispatches HELP_TOGGLE when not typing", () => {
    const spy = vi.fn();
    window.addEventListener(SHORTCUT_EVENTS.HELP_TOGGLE, spy);
    press("?");
    expect(spy).toHaveBeenCalledTimes(1);
    window.removeEventListener(SHORTCUT_EVENTS.HELP_TOGGLE, spy);
  });

  // ── custom binding fires + emits activation (modifier combo) ──────────
  it("a custom ⌥+key binding fires only with the modifier held, and emits activate", () => {
    setCustomHotkeys([
      { id: "x", spec: "alt+j", route: "/inv/abc", entityId: "abc" },
    ]);
    const spy = vi.fn();
    window.addEventListener(PRODUCT_ACTIVATE_EVENT, spy);

    // A bare "j" (no modifier) must NOT fire — a custom binding always carries
    // a modifier, and a bare key is never resolved.
    press("j");
    expect(navigate).not.toHaveBeenCalled();

    // ⌥J fires → navigates + emits activate with the entity id.
    press("j", { altKey: true });
    expect(navigate).toHaveBeenCalledWith("/inv/abc");
    expect(spy).toHaveBeenCalledTimes(1);
    const detail = spy.mock.calls[0][0].detail as ProductActivateDetail;
    expect(detail.entityId).toBe("abc");
    expect(detail.source).toBe("hotkey");
    window.removeEventListener(PRODUCT_ACTIVATE_EVENT, spy);
  });

  it("a custom ⌘+key (mod) binding fires after setCustomHotkeys", () => {
    // Use a free ⌘+punctuation combo (⌘.) — every free single ⌘+letter is now
    // owned by a product/sub-action/built-in, so a custom mod-combo must reach
    // for a free punctuation key (or ⌘⇧+letter). ⌘. is not reserved and not in
    // any fixed table, so a custom binding can own it.
    setCustomHotkeys([
      { id: "y", spec: "mod+.", route: "/read/doc9", entityId: "doc9" },
    ]);
    const spy = vi.fn();
    window.addEventListener(PRODUCT_ACTIVATE_EVENT, spy);
    press(".", { metaKey: true });
    expect(navigate).toHaveBeenCalledWith("/read/doc9");
    expect(spy).toHaveBeenCalledTimes(1);
    const detail = spy.mock.calls[0][0].detail as ProductActivateDetail;
    expect(detail.entityId).toBe("doc9");
    expect(detail.source).toBe("hotkey");
    window.removeEventListener(PRODUCT_ACTIVATE_EVENT, spy);
  });

  it("setCustomHotkeys normalises the stored spec", () => {
    setCustomHotkeys([
      { id: "z", spec: "Mod+.", route: "/x", entityId: "e" },
    ]);
    expect(getCustomHotkeys()[0].spec).toBe("mod+.");
  });

  // ── existing built-ins still work (no regression) ────────────────────
  it("still toggles the palette on ⌘K", () => {
    const spy = vi.fn();
    window.addEventListener(SHORTCUT_EVENTS.PALETTE_TOGGLE, spy);
    press("k", { metaKey: true });
    expect(spy).toHaveBeenCalledTimes(1);
    window.removeEventListener(SHORTCUT_EVENTS.PALETTE_TOGGLE, spy);
  });

  it("⌘K does NOT also resolve a product combo (built-in branch wins + returns)", () => {
    setCustomHotkeys([{ id: "k1", spec: "mod+k", route: "/should-not", entityId: "x" }]);
    // Even a (stale/impossible) custom mod+k can't win: the built-in branch
    // handles ⌘K and returns before resolveExtended is reached.
    press("k", { metaKey: true });
    expect(navigate).not.toHaveBeenCalledWith("/should-not");
  });
});

describe("shortcuts boot-hydration — M2 reload-persistence (the live handler reads the blob on mount)", () => {
  afterEach(() => {
    window.localStorage.clear();
    setCustomHotkeys([]);
    vi.useRealTimers();
  });

  it("a persisted custom binding fires after a fresh install WITHOUT any AssignHotkey surface mounted", () => {
    // Simulate a prior session: a custom ⌥J → /inv/persisted is in localStorage.
    setCustomHotkeys([]); // live map empty (as on a cold boot)
    writeCustomHotkeys({
      schemaVersion: 1,
      bindings: [
        {
          id: "p1",
          spec: "alt+j",
          route: "/inv/persisted",
          entityId: "persisted",
          entityKind: "investigation",
          label: "Persisted research",
        },
      ],
    });

    // Fresh install (a page reload) — the handler hydrates from the blob.
    const navigate = vi.fn();
    const uninstall = installShortcuts(navigate as never);

    // The live map now holds the persisted binding (no consumer mounted).
    expect(getCustomHotkeys().some((b) => b.spec === "alt+j")).toBe(true);

    // Pressing it navigates — identical to clicking the entity.
    const evt = new KeyboardEvent("keydown", {
      key: "j",
      altKey: true,
      bubbles: true,
      cancelable: true,
    });
    window.dispatchEvent(evt);
    expect(navigate).toHaveBeenCalledWith("/inv/persisted");

    uninstall();
  });
});
