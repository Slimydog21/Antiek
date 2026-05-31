import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";

import {
  installShortcuts,
  setCustomHotkeys,
  getCustomHotkeys,
  SHORTCUT_EVENTS,
} from "./shortcuts";
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

describe("shortcuts handler — SPR-08", () => {
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

  // ── chord timing ─────────────────────────────────────────────────────
  it("resolves a g-chord when the 2nd key arrives within the window", () => {
    vi.useFakeTimers();
    press("g");
    vi.advanceTimersByTime(200); // within 800ms
    press("e"); // g e → Read
    expect(navigate).toHaveBeenCalledWith("/library");
  });

  it("expires the chord after the 800ms window", () => {
    vi.useFakeTimers();
    press("g");
    vi.advanceTimersByTime(801); // past the window → pending cleared
    press("e");
    // After expiry "e" alone is not a binding → no nav.
    expect(navigate).not.toHaveBeenCalled();
  });

  // ── isTextEditing guard ──────────────────────────────────────────────
  it("does NOT fire while typing in an input", () => {
    press("g", { fromInput: true });
    press("e", { fromInput: true });
    expect(navigate).not.toHaveBeenCalled();
  });

  it("does NOT open the HUD with ? while typing", () => {
    const spy = vi.fn();
    window.addEventListener(SHORTCUT_EVENTS.HELP_TOGGLE, spy);
    press("?", { fromInput: true });
    expect(spy).not.toHaveBeenCalled();
    window.removeEventListener(SHORTCUT_EVENTS.HELP_TOGGLE, spy);
  });

  // ── shared activation event (SPR-10 contract): hotkey === click ───────
  it("firing a product hotkey emits the SAME event a click emits", () => {
    const fromHotkey: ProductActivateDetail[] = [];
    const fromClick: ProductActivateDetail[] = [];
    const listener = (e: Event) => {
      const detail = (e as CustomEvent<ProductActivateDetail>).detail;
      (detail.source === "hotkey" ? fromHotkey : fromClick).push(detail);
    };
    window.addEventListener(PRODUCT_ACTIVATE_EVENT, listener);

    // Hotkey path: g e → Read
    press("g");
    press("e");

    // Click path: a button handler would call emitProductActivate directly.
    emitProductActivate({ productId: "read", route: "/library", source: "click" });

    window.removeEventListener(PRODUCT_ACTIVATE_EVENT, listener);

    expect(fromHotkey).toHaveLength(1);
    expect(fromClick).toHaveLength(1);
    // Same productId + route — only `source` differs (which SPR-10 may use
    // to choreograph, but the EVENT + target are identical).
    expect(fromHotkey[0].productId).toBe(fromClick[0].productId);
    expect(fromHotkey[0].route).toBe(fromClick[0].route);
  });

  it("g r fires Research product activation AND navigates home", () => {
    const spy = vi.fn();
    window.addEventListener(PRODUCT_ACTIVATE_EVENT, spy);
    press("g");
    press("r");
    expect(navigate).toHaveBeenCalledWith("/");
    expect(spy).toHaveBeenCalledTimes(1);
    window.removeEventListener(PRODUCT_ACTIVATE_EVENT, spy);
  });

  // ── ? toggles the HUD ────────────────────────────────────────────────
  it("? dispatches HELP_TOGGLE when not typing", () => {
    const spy = vi.fn();
    window.addEventListener(SHORTCUT_EVENTS.HELP_TOGGLE, spy);
    press("?");
    expect(spy).toHaveBeenCalledTimes(1);
    window.removeEventListener(SHORTCUT_EVENTS.HELP_TOGGLE, spy);
  });

  // ── custom binding fires + emits activation ──────────────────────────
  it("a single-key custom binding navigates to its entity and emits activate", () => {
    setCustomHotkeys([
      { id: "x", spec: "j", route: "/inv/abc", entityId: "abc" },
    ]);
    const spy = vi.fn();
    window.addEventListener(PRODUCT_ACTIVATE_EVENT, spy);
    press("j");
    expect(navigate).toHaveBeenCalledWith("/inv/abc");
    expect(spy).toHaveBeenCalledTimes(1);
    const detail = spy.mock.calls[0][0].detail as ProductActivateDetail;
    expect(detail.entityId).toBe("abc");
    expect(detail.source).toBe("hotkey");
    window.removeEventListener(PRODUCT_ACTIVATE_EVENT, spy);
  });

  it("a g-chord custom binding fires after setCustomHotkeys", () => {
    setCustomHotkeys([
      { id: "y", spec: "g 1", route: "/read/doc9", entityId: "doc9" },
    ]);
    press("g");
    press("1");
    expect(navigate).toHaveBeenCalledWith("/read/doc9");
  });

  it("setCustomHotkeys normalises the stored spec", () => {
    setCustomHotkeys([
      { id: "z", spec: "G 2", route: "/x", entityId: "e" },
    ]);
    expect(getCustomHotkeys()[0].spec).toBe("g 2");
  });

  // ── existing built-ins still work (no regression) ────────────────────
  it("still toggles the palette on mod+k", () => {
    const spy = vi.fn();
    window.addEventListener(SHORTCUT_EVENTS.PALETTE_TOGGLE, spy);
    press("k", { metaKey: true });
    expect(spy).toHaveBeenCalledTimes(1);
    window.removeEventListener(SHORTCUT_EVENTS.PALETTE_TOGGLE, spy);
  });

  it("still navigates g i to /my-research (built-in untouched)", () => {
    press("g");
    press("i");
    expect(navigate).toHaveBeenCalledWith("/my-research");
  });
});
