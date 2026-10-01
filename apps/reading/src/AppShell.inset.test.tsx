/**
 * AppShell.inset.test.tsx — cockpit repair round 2 (critic H3).
 *
 * DECISIONS C2 (operator-confirmed 2026-09-26): the Omarchy inset is a
 * layout preset inside PanelLayout that keeps the LEFT toolbar visible. The
 * shell mounted NavRail with its SPR-06 default (a 64 px bottom bar) in every
 * preset, so the inset had no left toolbar at any width. The inset now takes
 * the vertical rail at every tier the inset draws (xl, lg, and md, the
 * Omarchy half screen: R3-M4); the docked preset and the phone tier (sm)
 * keep the bottom dock (SPR-06, the phone design). Heavy children are stubbed exactly as AppShell.spr06.test does.
 */
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";
import { cleanup, render } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

// SPR-08 — the real NavRail (kept un-mocked here) now renders on-bar KeyChips,
// which read usePrefersReducedMotion (matchMedia). jsdom lacks matchMedia;
// stub it as the hotkey/ad/mascot suites already do. No new assertion — it
// only lets the real rail render its real children.
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

// Heavy / separately-tested children → lightweight honest stand-ins. The PDF
// worker import lives behind PanelLayout; mocking it keeps the env happy while
// preserving the prop contract (PanelLayout renders its mainSlot).
vi.mock("./shell/MascotStation", () => ({ MascotStation: () => null }));
// SPR-07 — the always-on ad border mounts here too; it has its own suite
// (components/ad/*.test.*) and pulls usePrefersReducedMotion (matchMedia,
// which jsdom lacks), so stub it to null exactly as the other heavy children.
vi.mock("./components/ad/AdBorderMount", () => ({ AdBorderMount: () => null }));
vi.mock("./shell/SceneChrome", () => ({
  SceneChrome: ({ children }: { children: React.ReactNode }) => <>{children}</>,
}));
vi.mock("./components/navigation/Topbar", () => ({
  Topbar: () => <div data-testid="topbar-stub" />,
}));
vi.mock("./components/lemon/LemonToast", () => ({
  LemonToastViewport: () => null,
  // herdr transfer P0-4 — AppShell registers the toast navigator; the mock
  // contract must keep the registration callable (a no-op is fine here).
  setToastNavigator: () => {},
}));
vi.mock("./workspace/PanelLayout", () => ({
  PanelLayout: ({ mainSlot }: { mainSlot: React.ReactNode }) => (
    <div data-testid="main-region">{mainSlot}</div>
  ),
}));
// SPR-08 — AppShell now mounts <HotkeyHud/>, which imports SHORTCUT_EVENTS
// from this module; the mock must still export it (a real const, not the
// keydown handler) so the HUD's HELP_TOGGLE listener resolves. The keydown
// installer is the only thing stubbed.
vi.mock("./workspace/shortcuts", () => ({
  useWorkspaceShortcuts: () => {},
  // SceneChrome's "Ask" verb + CommandPalette import the real toggle; stub
  // it so the mock module still satisfies their imports.
  toggleAISidecar: () => {},
  SHORTCUT_EVENTS: {
    PALETTE_TOGGLE: "antiek:palette:toggle",
    AISIDECAR_TOGGLE: "antiek:aisidecar:toggle",
    HELP_TOGGLE: "antiek:help:toggle",
  },
}));
vi.mock("./workspace/useWorkspaceHydration", () => ({
  useWorkspaceHydration: () => {},
}));


const { tierRef } = vi.hoisted(() => ({ tierRef: { current: "xl" as string } }));
vi.mock("./workspace/useViewportTier", () => ({ useViewportTier: () => tierRef.current }));

import { AppShell } from "./AppShell";
import { useWorkspace } from "./workspace/WorkspaceStore";

afterEach(() => {
  cleanup();
  tierRef.current = "xl";
  useWorkspace.getState().reset();
  useWorkspace.getState().setLayoutPreset("docked");
  window.localStorage.removeItem("antiek.workspace.layout-preset");
});

function mountShell() {
  return render(
    <MemoryRouter initialEntries={["/read/origin-of-species"]}>
      <AppShell>
        <div data-testid="route-view">ROUTE</div>
      </AppShell>
    </MemoryRouter>,
  );
}

const rail = (c: HTMLElement) => c.querySelector<HTMLElement>("aside[aria-label='Primary navigation']")!;
/** Does `a` come before `b` in document order? */
const before = (a: Node, b: Node) => (a.compareDocumentPosition(b) & Node.DOCUMENT_POSITION_FOLLOWING) !== 0;

describe("C2 — the inset keeps a LEFT toolbar", () => {
  // md is an Omarchy half screen (960 px on a 1920 display): the inset is on
  // there too, so the left toolbar is too (C2 has no tier exemption; R3-M4).
  it.each(["xl", "lg", "md"])("omarchy-inset at tier %s: the primary navigation is a vertical rail to the left of the panes", (tier) => {
    tierRef.current = tier;
    useWorkspace.getState().setLayoutPreset("omarchy-inset");
    const { container, getByTestId, queryByRole } = mountShell();
    const nav = rail(container);
    expect(nav).toBeTruthy();
    // Orientation and flow come from NavRail's `orientation` prop, stamped as
    // data-* (one source of truth). A1c low 14: assert the behavior, not the
    // Tailwind class list — a class-string assertion cannot fail when someone
    // restyles the rail, only when someone edits the class names.
    expect(nav.dataset.orientation).toBe("left");
    expect(nav.dataset.railFlow).toBe("inline");
    // To the LEFT of the working region, in the same row.
    const region = getByTestId("main-region");
    expect(before(nav, region)).toBe(true);
    const row = nav.parentElement!;
    expect(row.contains(region)).toBe(true);
    // The row holds rail + region side by side (a column would stack them).
    expect(before(nav, region) && before(nav, row.lastChild!)).toBe(true);
    // The mascot keeps its reserved station in the rail.
    expect(nav.querySelector("[data-mascot-station]")).toBeTruthy();
    // Never the phone overlay drawn over the left pane (the R3 render probe at
    // 900 px caught exactly that) — the flow stamp is the contract.
    expect(nav.dataset.railFlow).not.toBe("overlay");
    expect(queryByRole("button", { name: "Close navigation" })).toBeNull();
  });

  it("the docked preset keeps the SPR-06 bottom dock after the working region", () => {
    useWorkspace.getState().setLayoutPreset("docked");
    const { container, getByTestId } = mountShell();
    const nav = rail(container);
    expect(nav.dataset.orientation).toBe("bottom");
    expect(nav.dataset.railFlow).toBe("inline");
    expect(before(getByTestId("main-region"), nav)).toBe(true);
  });

  it("the phone tier (sm) keeps the bottom dock even in the inset", () => {
    tierRef.current = "sm";
    useWorkspace.getState().setLayoutPreset("omarchy-inset");
    const { container, getByTestId } = mountShell();
    const nav = rail(container);
    expect(nav.dataset.orientation).toBe("bottom");
    expect(nav.dataset.railFlow).toBe("inline");
    expect(before(getByTestId("main-region"), nav)).toBe(true);
  });
});
