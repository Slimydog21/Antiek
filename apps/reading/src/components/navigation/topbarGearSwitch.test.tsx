/**
 * topbarGearSwitch.test.tsx — SPR-04 M5: the Topbar's left carries the
 * geared switch's host behind antiek.flag.nav.switcher, before the
 * route-derived breadcrumb (which stays exactly as it was). With the flag
 * off nothing mounts and the crumbs are byte-for-byte unchanged.
 */
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";
import { cleanup, render, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

import { setFeatureFlag } from "../../lib/featureFlags";

vi.mock("../../lib/auth", async (orig) => ({
  ...(await orig<typeof import("../../lib/auth")>()),
  useAuth: () => ({
    state: { status: "authenticated", identity: { user_id: "u", email: "reader@antiek.test", auth_method: "magic_link" } },
    refresh: async () => {},
    signOut: async () => {},
  }),
}));

import { Topbar } from "./Topbar";

beforeAll(() => {
  if (!window.matchMedia) {
    Object.defineProperty(window, "matchMedia", {
      writable: true,
      configurable: true,
      value: (query: string) => ({ matches: false, media: query, onchange: null, addEventListener: () => {}, removeEventListener: () => {}, addListener: () => {}, removeListener: () => {}, dispatchEvent: () => false }),
    });
  }
});

afterEach(() => {
  cleanup();
  setFeatureFlag("nav.switcher", null);
  vi.unstubAllGlobals();
});

function mount(path = "/library") {
  return render(<MemoryRouter initialEntries={[path]}><Topbar /></MemoryRouter>);
}

describe("Topbar × the geared switch (SPR-04 M5)", () => {
  it("flag off: no chip, no feeder, the breadcrumb is the first thing in the bar", () => {
    setFeatureFlag("nav.switcher", false);
    const { container } = mount();
    expect(container.querySelector("[data-gear-chip]")).toBeNull();
    expect(container.querySelector("[data-gear-host]")).toBeNull();
    const header = container.querySelector("header")!;
    expect(header.firstElementChild?.getAttribute("aria-label")).toBe("Breadcrumb");
    expect(header.textContent).toContain("Library");
  });

  it("flag on: one chip mounts in the Topbar's left, before the breadcrumb, which is unchanged", async () => {
    setFeatureFlag("nav.switcher", true);
    vi.stubGlobal("fetch", () => new Promise<Response>(() => {}));
    const { container } = mount();
    await waitFor(() => expect(container.querySelector("[data-gear-chip]")).toBeTruthy(), { timeout: 5000 });
    const header = container.querySelector("header")!;
    const chip = container.querySelector("[data-gear-chip]")!;
    const nav = header.querySelector('nav[aria-label="Breadcrumb"]')!;
    expect(chip.compareDocumentPosition(nav) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(container.querySelectorAll("[data-gear-chip]")).toHaveLength(1);
    expect(container.querySelector('[data-gear-host="topbar"]')).toBeTruthy();
    expect(nav.textContent).toContain("Library");
    expect(container.querySelector("[data-gear-switch]")).toBeNull();
  });
});
