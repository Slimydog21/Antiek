/**
 * researchDoor.zen.test.tsx — FFX-KPA SPR-03 M7: the zen home is reachable.
 *
 * /zen is a flag-gated route ("nav.zenhome"); the reachability gate
 * (tools/lint/reachability_gate.py) reds any route nothing navigates to. The
 * honest entry is the Research door: with the flag on, both the NavRail click
 * and the door hotkeys (⌘J door.research, ⌘G door.researchHome) land on /zen.
 * With the flag off every path still lands on "/" (StartResearch), exactly as
 * before — the flag-off half is the parity check.
 */
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter, useLocation } from "react-router-dom";

import { NavRail } from "./NavRail";
import { researchDoorRoute } from "./workflowTaxonomy";
import { setFeatureFlag } from "../lib/featureFlags";
import { installShortcuts, setCustomHotkeys } from "../workspace/shortcuts";
import { PRODUCT_ACTIVATE_EVENT, type ProductActivateDetail } from "../components/hotkeys/bindings";

beforeAll(() => {
  Object.defineProperty(window, "matchMedia", {
    writable: true,
    configurable: true,
    value: (query: string) => ({
      matches: false, media: query, onchange: null,
      addEventListener: () => {}, removeEventListener: () => {},
      addListener: () => {}, removeListener: () => {}, dispatchEvent: () => false,
    }),
  });
});

beforeEach(() => window.localStorage.clear());
afterEach(() => {
  cleanup();
  window.localStorage.clear();
});

function LocationProbe() {
  const { pathname } = useLocation();
  return <output data-testid="location">{pathname}</output>;
}

function clickResearchDoor(): ProductActivateDetail[] {
  render(
    <MemoryRouter initialEntries={["/library"]}>
      <LocationProbe />
      <NavRail />
    </MemoryRouter>,
  );
  const fired: ProductActivateDetail[] = [];
  const listener = (e: Event) => fired.push((e as CustomEvent<ProductActivateDetail>).detail);
  window.addEventListener(PRODUCT_ACTIVATE_EVENT, listener);
  fireEvent.click(document.querySelector('[data-product-id="research"]') as HTMLElement);
  window.removeEventListener(PRODUCT_ACTIVATE_EVENT, listener);
  return fired;
}

function pressDoor(key: string): ReturnType<typeof vi.fn> {
  const navigate = vi.fn();
  setCustomHotkeys([]);
  const uninstall = installShortcuts(navigate as never);
  window.dispatchEvent(new KeyboardEvent("keydown", { key, metaKey: true, bubbles: true, cancelable: true }));
  uninstall();
  return navigate;
}

describe("Research door → /zen behind nav.zenhome (SPR-03 M7)", () => {
  it("flag on: the resolver, a rail click, ⌘J and ⌘G all reach /zen", () => {
    setFeatureFlag("nav.zenhome", true);
    expect(researchDoorRoute()).toBe("/zen");

    const fired = clickResearchDoor();
    expect(screen.getByTestId("location").textContent).toBe("/zen");
    expect(fired.map((d) => [d.source, d.route])).toEqual([["click", "/zen"]]);

    expect(pressDoor("j")).toHaveBeenCalledWith("/zen");
    expect(pressDoor("g")).toHaveBeenCalledWith("/zen");
  });

  it("flag off: every research door path still lands on / (StartResearch)", () => {
    expect(researchDoorRoute()).toBe("/");

    const fired = clickResearchDoor();
    expect(screen.getByTestId("location").textContent).toBe("/");
    expect(fired.map((d) => [d.source, d.route])).toEqual([["click", "/"]]);

    expect(pressDoor("j")).toHaveBeenCalledWith("/");
    expect(pressDoor("g")).toHaveBeenCalledWith("/");
  });
});
