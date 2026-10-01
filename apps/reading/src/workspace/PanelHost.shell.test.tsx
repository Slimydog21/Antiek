/**
 * PanelHost.shell.test.tsx — MS-01 F2 + F4.
 *
 * F2: on fresh storage, AppShell's hydration effect ran AFTER the route's
 * PanelHost starters had opened (React runs child effects before parent
 * effects) and replaced the whole workspace with the empty hydrated layout,
 * so a route's starter panels never docked on first visit.
 *
 * F4: PanelHost rendered its own <PanelLayout> inside the shell's
 * <PanelLayout>, so every docked panel rendered twice (two left docks in the
 * DOM, two InvestigationSidebar instances, two 30 s polls).
 *
 * Both are shell-composition defects, so this mounts the REAL AppShell with
 * the REAL PanelLayout, the REAL useWorkspaceHydration and the REAL PanelHost.
 * Only the panel renderers are stand-ins (each kind renders a labelled stub),
 * plus the chrome that has its own suites.
 */
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import { act, cleanup, render } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";

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

vi.mock("./PanelRegistry", () => ({
  PanelRegistry: new Proxy(
    {},
    {
      get: (_target, kind) =>
        function StubPanel() {
          return <div data-stub-panel={String(kind)}>{String(kind)}</div>;
        },
    },
  ),
}));
vi.mock("../scene/Scene", () => ({ Scene: () => null }));
vi.mock("../shell/MascotStation", () => ({ MascotStation: () => null }));
vi.mock("../shell/NavRail", () => ({ NavRail: () => null }));
vi.mock("../components/ad/AdBorderMount", () => ({ AdBorderMount: () => null }));
vi.mock("../components/windows/WindowsLayer", () => ({ WindowsLayer: () => null }));
vi.mock("../shell/SceneChrome", () => ({
  SceneChrome: ({ children }: { children: React.ReactNode }) => <>{children}</>,
}));
vi.mock("../components/navigation/Topbar", () => ({ Topbar: () => null }));

import { AppShell } from "../AppShell";
import { PanelHost } from "./PanelHost";
import { useWorkspace } from "./WorkspaceStore";

function StarterRoute() {
  return (
    <PanelHost
      starters={[
        { kind: "InvestigationSidebar", mode: "docked-left", title: "Investigations", id: "t:sidebar" },
        { kind: "Chat", mode: "docked-bottom", title: "Chat", id: "t:chat" },
      ]}
    >
      <p>route body</p>
    </PanelHost>
  );
}

function mountAt(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <AppShell>
        <Routes>
          <Route path="/starters" element={<StarterRoute />} />
        </Routes>
      </AppShell>
    </MemoryRouter>,
  );
}

beforeEach(() => {
  window.localStorage.clear();
  useWorkspace.getState().reset();
});

afterEach(() => {
  cleanup();
  useWorkspace.getState().reset();
  window.localStorage.clear();
});

describe("F2 — a route's starter panels survive the shell's hydration on fresh storage", () => {
  it("the docked-left and docked-bottom starters are in the workspace after mount", async () => {
    mountAt("/starters");
    await act(async () => {});
    const s = useWorkspace.getState();
    expect(s.dockLeftIds, "the docked-left starter must survive hydration").toContain("t:sidebar");
    expect(s.dockBottomIds, "the docked-bottom starter must survive hydration").toContain("t:chat");
    expect(document.querySelectorAll('[data-stub-panel="InvestigationSidebar"]').length).toBe(1);
  });
});

describe("F4 — exactly one PanelLayout owns the docks", () => {
  it("renders exactly one left dock in the DOM for a PanelHost route inside the shell", async () => {
    mountAt("/starters");
    await act(async () => {});
    expect(document.querySelectorAll('[aria-label="Left dock"]').length).toBe(1);
    expect(document.querySelectorAll('[aria-label="Right dock"]').length).toBe(1);
  });
});
