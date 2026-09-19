/**
 * AppShell.spr06.test.tsx — SPR-06 M3 (round-3 hardening).
 *
 * The audit found M3 ("symmetric full-width region, no left gutter, the
 * `--akb-border-inset-*` edge-reservation seam") had ZERO automated coverage:
 * no test referenced AppShell, the shell frame, or the inset vars.
 *
 * AppShell statically pulls the whole panel registry (PanelLayout → a PDF
 * reader panel → pdfjs-dist's web worker), which the vitest/vite env refuses
 * to load — so a *full* render isn't unit-testable. M3 is about AppShell's own
 * LAYOUT COMPOSITION, not its children's internals, so we mock the
 * separately-tested heavy children (each has its own suite) and keep the REAL
 * NavRail. That isolates exactly what M3 asserts: the seam frame contract and
 * the nav-is-the-bottom-rail ordering. A regression — nav drifting back to a
 * leading left column, or the seam frame losing its inset padding — reddens.
 */
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";
import { cleanup, render } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

// SPR-08 — the real NavRail (kept un-mocked here) now renders on-bar KeyChips,
// which read usePrefersReducedMotion (matchMedia). jsdom lacks matchMedia;
// stub it as the hotkey/ad/penguin suites already do. No new assertion — it
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
vi.mock("./shell/PenguinMascot", () => ({ PenguinMascot: () => null }));
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

// herdr transfer P2 — seen-once release notes; stubbed like the other
// heavy children (auto-opens in tests otherwise).
vi.mock("./components/ReleaseNotesModal", () => ({
  ReleaseNotesModal: () => null,
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
  SHORTCUT_EVENTS: {
    PALETTE_TOGGLE: "antiek:palette:toggle",
    AISIDECAR_TOGGLE: "antiek:aisidecar:toggle",
    HELP_TOGGLE: "antiek:help:toggle",
  },
}));
vi.mock("./workspace/useWorkspaceHydration", () => ({
  useWorkspaceHydration: () => {},
}));

import { AppShell } from "./AppShell";
import { useWorkspace } from "./workspace/WorkspaceStore";

afterEach(() => {
  cleanup();
  useWorkspace.getState().reset();
});

function mountShell() {
  return render(
    <MemoryRouter initialEntries={["/"]}>
      <AppShell>
        <div data-testid="route-view">ROUTE</div>
      </AppShell>
    </MemoryRouter>,
  );
}

describe("AppShell SPR-06 M3 — symmetric full-width region + edge seam", () => {
  it("wraps the column in the [data-akb-shell-frame] seam that reads all four --akb-border-inset-* vars as padding (the SPR-07 contract)", () => {
    const { container } = mountShell();
    const frame = container.querySelector(
      "[data-akb-shell-frame]",
    ) as HTMLElement | null;
    expect(frame, "the shell must mount the edge-reservation frame").toBeTruthy();
    // The seam is the SINGLE source of truth for the inset: padding reads the
    // four custom props (default 0px in tokens.css; SPR-07's border sets them).
    expect(frame!.style.paddingTop).toBe("var(--akb-border-inset-top)");
    expect(frame!.style.paddingRight).toBe("var(--akb-border-inset-right)");
    expect(frame!.style.paddingBottom).toBe("var(--akb-border-inset-bottom)");
    expect(frame!.style.paddingLeft).toBe("var(--akb-border-inset-left)");
    // box-sizing:border-box so the band is painted INTO the frame's padding,
    // not pushing the column off-screen.
    expect(frame!.style.boxSizing).toBe("border-box");
  });

  it("renders the nav BELOW the working region (bottom rail, no left gutter)", () => {
    const { container } = mountShell();
    const region = container.querySelector('[data-testid="main-region"]');
    const navGroup = container.querySelector('[data-testid="navrail-workflows"]');
    expect(region, "the working region must render").toBeTruthy();
    expect(navGroup, "the real bottom NavRail must render").toBeTruthy();
    // Document order: the working region PRECEDES the nav → nav is the bottom
    // rail, not a leading left/top gutter. A left-column regression would put
    // the nav first and flip this.
    const rel = region!.compareDocumentPosition(navGroup!);
    expect(rel & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });
});
