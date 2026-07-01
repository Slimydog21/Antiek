/**
 * AppShell.hotkeys.test.tsx — SPR-08 sharpen (BLOCKING 1).
 *
 * The verifier-critic found the hotkey feature did not work in the app because
 * nothing was mounted: <HotkeyHud /> existed but was never rendered, so `?`
 * opened nothing. This proves the HUD is mounted ONCE in AppShell and that it
 * self-subscribes to the HELP_TOGGLE event (the `?` key fires it in
 * shortcuts.ts) — open on toggle, closed again on the next toggle.
 *
 * Same isolation strategy as AppShell.spr06.test.tsx: the heavy / separately-
 * tested children are stubbed (they pull a PDF worker / matchMedia the unit
 * env can't load); we keep the REAL HotkeyHud, which is what this test
 * asserts. We keep the REAL shortcuts module so SHORTCUT_EVENTS.HELP_TOGGLE
 * matches the event the HUD listens for, and stub only the keydown installer.
 */
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, act } from "@testing-library/react";
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

vi.mock("./shell/PenguinMascot", () => ({ PenguinMascot: () => null }));
vi.mock("./components/ad/AdBorderMount", () => ({ AdBorderMount: () => null }));
vi.mock("./shell/SceneChrome", () => ({
  SceneChrome: ({ children }: { children: React.ReactNode }) => <>{children}</>,
}));
vi.mock("./components/navigation/Topbar", () => ({
  Topbar: () => <div data-testid="topbar-stub" />,
}));
vi.mock("./components/lemon/LemonToast", () => ({
  LemonToastViewport: () => null,
}));
vi.mock("./workspace/PanelLayout", () => ({
  PanelLayout: ({ mainSlot }: { mainSlot: React.ReactNode }) => (
    <div data-testid="main-region">{mainSlot}</div>
  ),
}));
vi.mock("./workspace/useWorkspaceHydration", () => ({
  useWorkspaceHydration: () => {},
}));

import { AppShell } from "./AppShell";
import { useWorkspace } from "./workspace/WorkspaceStore";
import { SHORTCUT_EVENTS } from "./workspace/shortcuts";
import { installLocalStorageMock } from "./test/localStorage";
import { OPERATOR_ROUTES } from "./shell/operatorRoutes";

let restoreLocalStorage: (() => void) | null = null;

beforeEach(() => {
  restoreLocalStorage = installLocalStorageMock();
});

afterEach(() => {
  cleanup();
  useWorkspace.getState().reset();
  window.localStorage.clear();
  restoreLocalStorage?.();
  restoreLocalStorage = null;
});

function mountShell(initialEntry = "/") {
  return render(
    <MemoryRouter initialEntries={[initialEntry]}>
      <AppShell>
        <div data-testid="route-view">ROUTE</div>
      </AppShell>
    </MemoryRouter>,
  );
}

describe("AppShell SPR-08 — the HotkeyHud is mounted + HELP_TOGGLE-driven", () => {
  it("does not show the HUD at rest, but the HELP_TOGGLE event opens it (mounted once, self-subscribed)", () => {
    mountShell();
    // At rest the HUD renders nothing (LemonModal is a portal to body).
    expect(document.body.querySelector('[role="dialog"]')).toBeNull();

    // The `?` key fires HELP_TOGGLE in shortcuts.ts; the mounted HUD listens.
    act(() => {
      window.dispatchEvent(new CustomEvent(SHORTCUT_EVENTS.HELP_TOGGLE));
    });
    const dialog = document.body.querySelector('[role="dialog"]');
    expect(
      dialog,
      "the `?` HUD must be mounted in AppShell and open on toggle",
    ).toBeTruthy();
    expect(dialog!.textContent).toContain("Keyboard shortcuts");

    // Toggling again closes it.
    act(() => {
      window.dispatchEvent(new CustomEvent(SHORTCUT_EVENTS.HELP_TOGGLE));
    });
    expect(document.body.querySelector('[role="dialog"]')).toBeNull();
  });

  it("mounts EXACTLY ONE HUD (a single toggle yields a single dialog, not N)", () => {
    mountShell();
    act(() => {
      window.dispatchEvent(new CustomEvent(SHORTCUT_EVENTS.HELP_TOGGLE));
    });
    expect(document.body.querySelectorAll('[role="dialog"]')).toHaveLength(1);
  });

  it("opens and closes the AISidecar panel through the global shell shortcut", () => {
    mountShell();

    act(() => {
      window.dispatchEvent(
        new KeyboardEvent("keydown", {
          key: "/",
          metaKey: true,
          bubbles: true,
        }),
      );
    });

    const opened = useWorkspace.getState().panels["shortcuts:aisidecar"];
    expect(opened?.kind).toBe("AISidecar");
    expect(opened?.mode).toBe("docked-right");
    expect(useWorkspace.getState().dockRightIds).toContain("shortcuts:aisidecar");

    act(() => {
      window.dispatchEvent(
        new KeyboardEvent("keydown", {
          key: "/",
          metaKey: true,
          bubbles: true,
        }),
      );
    });

    expect(useWorkspace.getState().panels["shortcuts:aisidecar"]).toBeUndefined();
    expect(useWorkspace.getState().dockRightIds).not.toContain("shortcuts:aisidecar");
  });

  it.each(OPERATOR_ROUTES.filter((route) => route.path !== "/trust"))(
    "opens the AISidecar from authenticated operator route $path",
    (route) => {
      mountShell(route.path);

      act(() => {
        window.dispatchEvent(
          new KeyboardEvent("keydown", {
            key: "/",
            metaKey: true,
            bubbles: true,
          }),
        );
      });

      const opened = useWorkspace.getState().panels["shortcuts:aisidecar"];
      expect(opened?.kind, `${route.path} must open AISidecar`).toBe("AISidecar");
      expect(opened?.mode, `${route.path} must dock AISidecar right`).toBe(
        "docked-right",
      );
      expect(useWorkspace.getState().dockRightIds).toContain(
        "shortcuts:aisidecar",
      );
    },
  );
});
