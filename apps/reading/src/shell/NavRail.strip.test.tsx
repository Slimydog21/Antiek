/**
 * NavRail.strip.test.tsx — SPR-02 M4
 * (specs/antiek-keyboard-panes-agents-20261007/sprint-02-launcher.html).
 *
 * With `antiek.flag.switcher.places` OFF the bottom dock is the pre-SPR-02
 * dock (parity: full height, Home + Search keys, keycap chips, More opens the
 * products drawer). With it ON at desktop width the dock is the compact
 * five-key strip (captions kept, no chips, no Home/Search keys) and More
 * opens the Switcher narrowed to Scenes instead of the drawer.
 */
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
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

import { NavRail } from "./NavRail";
import { setFeatureFlag } from "../lib/featureFlags";
import { SHORTCUT_EVENTS } from "../workspace/shortcuts";
import { PRODUCT_ACTIVATE_EVENT } from "../components/hotkeys/bindings";

function mount() {
  return render(
    <MemoryRouter initialEntries={["/"]}>
      <NavRail orientation="bottom" />
    </MemoryRouter>,
  );
}

beforeEach(() => {
  window.localStorage.clear();
  Object.defineProperty(window, "innerWidth", { configurable: true, writable: true, value: 1280 });
});
afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe("flag off — the pre-SPR-02 dock", () => {
  beforeEach(() => setFeatureFlag("switcher.places", false));

  it("keeps Home and Search keys, keycap chips on the doors, and no strip marker", () => {
    mount();
    const dock = screen.getByLabelText("Primary navigation");
    expect(dock.getAttribute("data-rail-strip")).toBeNull();
    expect(dock.className).toContain("h-16");
    expect(screen.getByRole("button", { name: "Antiek home" })).toBeTruthy();
    // "Research" also matches /search/ — scope to the Utilities cluster.
    expect(within(within(dock).getByLabelText("Utilities")).getByRole("button", { name: /^Search/ })).toBeTruthy();
    expect(within(screen.getByTestId("navrail-workflows")).getAllByRole("button")).toHaveLength(4);
  });

  it("More opens the products drawer, not the Switcher", () => {
    const toggles = vi.fn();
    window.addEventListener(SHORTCUT_EVENTS.PALETTE_TOGGLE, toggles);
    mount();
    fireEvent.click(screen.getByRole("button", { name: /^more/i }));
    expect(toggles).not.toHaveBeenCalled();
    expect(screen.getByRole("dialog")).toBeTruthy(); // ProductsLauncher
    window.removeEventListener(SHORTCUT_EVENTS.PALETTE_TOGGLE, toggles);
  });
});

describe("flag on — the strip", () => {
  beforeEach(() => setFeatureFlag("switcher.places", true));

  it("folds to the compact five-key strip at desktop width: four doors + More, captions kept, no Home/Search keys", () => {
    mount();
    const dock = screen.getByLabelText("Primary navigation");
    expect(dock.getAttribute("data-rail-strip")).toBe("true");
    expect(dock.className).toContain("h-12");
    expect(screen.queryByRole("button", { name: "Antiek home" })).toBeNull();
    expect(within(dock).queryByLabelText("Utilities")).toBeNull(); // the Search cluster is gone
    const doors = within(screen.getByTestId("navrail-workflows")).getAllByRole("button");
    expect(doors).toHaveLength(4);
    for (const d of doors) expect(d.textContent).toMatch(/Research|Read|Write|Speak/);
  });

  it("More opens the Switcher narrowed to Scenes (detail.query) and never the drawer — by click and by the More hotkey", () => {
    const toggles = vi.fn();
    window.addEventListener(SHORTCUT_EVENTS.PALETTE_TOGGLE, toggles);
    mount();
    fireEvent.click(screen.getByRole("button", { name: /^more/i }));
    expect(toggles).toHaveBeenCalledTimes(1);
    expect((toggles.mock.calls[0][0] as CustomEvent).detail).toEqual({ query: "in:scenes" });
    expect(screen.queryByRole("dialog")).toBeNull();
    window.dispatchEvent(new CustomEvent(PRODUCT_ACTIVATE_EVENT, { detail: { productId: "more", source: "hotkey" } }));
    expect(toggles).toHaveBeenCalledTimes(2);
    expect(screen.queryByRole("dialog")).toBeNull();
    window.removeEventListener(SHORTCUT_EVENTS.PALETTE_TOGGLE, toggles);
  });
});
