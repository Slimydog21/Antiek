/**
 * AppShell scenery product map — Flipbook-feel edge hotspots navigate product
 * doors via pure productActionForSceneHotspot + onActivate wiring.
 */
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";

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
vi.mock("./werner/WernerIceCursorShell", () => ({
  WernerIceCursorShell: () => null,
}));
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
vi.mock("./scene/Scene", () => ({ Scene: () => null }));
vi.mock("./shell/NavRail", () => ({ NavRail: () => null }));
vi.mock("./components/hotkeys/HotkeyHud", () => ({ HotkeyHud: () => null }));
vi.mock("./components/windows/WindowsLayer", () => ({ WindowsLayer: () => null }));

import { AppShell } from "./AppShell";
import { WERNER_EXPERIENCE_EVENT } from "./werner/reactionBus";

afterEach(() => cleanup());

function LocationProbe() {
  const loc = useLocation();
  return <div data-testid="loc-path">{loc.pathname}</div>;
}

function mountAt(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <AppShell>
        <Routes>
          <Route path="*" element={<LocationProbe />} />
        </Routes>
      </AppShell>
    </MemoryRouter>,
  );
}

describe("AppShell Flipbook scenery product map", () => {
  it("mounts shell-level SceneHotspots with honest data-last-click contract", () => {
    mountAt("/");
    const layer = screen.getByTestId("scene-hotspots");
    expect(layer.getAttribute("data-hotspots-mode")).toBe("shell");
    expect(Number(layer.getAttribute("data-hotspot-count"))).toBeGreaterThan(0);
    expect(screen.getByTestId("scene-hotspot-igloo-ridge")).toBeTruthy();
    expect(screen.getByTestId("scene-hotspot-peak-left")).toBeTruthy();
  });

  it("igloo-ridge click navigates to /arcade and emits Werner highlight", () => {
    const seen: string[] = [];
    const onExp = (e: Event) => {
      const d = (e as CustomEvent).detail;
      if (d?.experience) seen.push(d.experience);
    };
    window.addEventListener(WERNER_EXPERIENCE_EVENT, onExp);
    mountAt("/");
    fireEvent.click(screen.getByTestId("scene-hotspot-igloo-ridge"));
    window.removeEventListener(WERNER_EXPERIENCE_EVENT, onExp);
    expect(screen.getByTestId("loc-path").textContent).toBe("/arcade");
    expect(
      screen.getByTestId("scene-hotspots").getAttribute("data-last-click"),
    ).toBe("igloo-ridge");
    expect(seen).toContain("highlight");
  });

  it("sky-aurora click navigates to /home", () => {
    mountAt("/");
    fireEvent.click(screen.getByTestId("scene-hotspot-sky-aurora"));
    expect(screen.getByTestId("loc-path").textContent).toBe("/home");
  });

  it("peak-right click navigates to /library", () => {
    mountAt("/");
    fireEvent.click(screen.getByTestId("scene-hotspot-peak-right"));
    expect(screen.getByTestId("loc-path").textContent).toBe("/library");
  });

  it("peak-left click stays ambient (no navigation) for shell honesty proof", () => {
    mountAt("/");
    fireEvent.click(screen.getByTestId("scene-hotspot-peak-left"));
    expect(screen.getByTestId("loc-path").textContent).toBe("/");
    expect(
      screen.getByTestId("scene-hotspots").getAttribute("data-last-click"),
    ).toBe("peak-left");
  });
});
