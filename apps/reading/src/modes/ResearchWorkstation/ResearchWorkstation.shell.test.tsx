/**
 * ResearchWorkstation.shell.test.tsx — MS-01 F2, F3 and F5 on the real
 * Research route.
 *
 * F2: fresh storage + /inv/abc must dock the investigation sidebar and this
 *     investigation's chat (the route's two starters).
 * F3: AppShell read `useParams()` outside the inner <Routes>, so it saw
 *     {"*": "inv/abc"} and never the investigation id. Every investigation
 *     wrote the shared key `antiek.workspace.route./inv/:id`, and the palette's
 *     "Reset workspace layout (this investigation)" cleared a key that was
 *     never written.
 * F5: "/" and "/inv/:investigationId" render the same ResearchWorkstation
 *     element type at the same tree position, so React kept ONE instance
 *     across /inv/a → /inv/b and the starters (opened once, on mount) never
 *     opened b's chat.
 *
 * Mounted as App.tsx composes it: the real AppShell (real PanelLayout, real
 * useWorkspaceHydration, real keymap), the real CommandPalette, and the real
 * ResearchWorkstation on its two real routes. Panel renderers are labelled
 * stubs; the investigation fetch and the idle composer are stubbed at their
 * module boundary.
 */
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import { act, cleanup, fireEvent, render } from "@testing-library/react";
import { useEffect } from "react";
import { MemoryRouter, Route, Routes, useNavigate, type NavigateFunction } from "react-router-dom";

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

vi.mock("../../workspace/PanelRegistry", () => ({
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
vi.mock("../../hooks/useInvestigation", () => ({
  useInvestigation: () => ({ status: "loading", events: [], sourcePolicy: [] }),
}));
vi.mock("./StartResearch", () => ({ default: () => <p>composer</p> }));
vi.mock("../../lib/api", async (orig) => ({
  ...(await orig<typeof import("../../lib/api")>()),
  apiFetch: vi.fn(() => Promise.resolve({ ok: false, status: 404, json: async () => ({}) })),
}));
vi.mock("../../scene/Scene", () => ({ Scene: () => null }));
vi.mock("../../shell/MascotStation", () => ({ MascotStation: () => null }));
vi.mock("../../shell/NavRail", () => ({ NavRail: () => null }));
vi.mock("../../components/ad/AdBorderMount", () => ({ AdBorderMount: () => null }));
vi.mock("../../components/windows/WindowsLayer", () => ({ WindowsLayer: () => null }));
vi.mock("../../shell/SceneChrome", () => ({
  SceneChrome: ({ children }: { children: React.ReactNode }) => <>{children}</>,
}));
vi.mock("../../components/navigation/Topbar", () => ({ Topbar: () => null }));

import { AppShell } from "../../AppShell";
import CommandPalette from "../../components/CommandPalette";
import { useWorkspace } from "../../workspace/WorkspaceStore";
import ResearchWorkstation from "./index";

const navRef: { current: NavigateFunction | null } = { current: null };
function CaptureNavigate() {
  const navigate = useNavigate();
  useEffect(() => {
    navRef.current = navigate;
  }, [navigate]);
  return null;
}

function mountAt(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <AppShell>
        <CommandPalette />
        <CaptureNavigate />
        <Routes>
          <Route path="/" element={<ResearchWorkstation />} />
          <Route path="/inv/:investigationId" element={<ResearchWorkstation />} />
        </Routes>
      </AppShell>
    </MemoryRouter>,
  );
}

const wait = (ms: number) => new Promise((r) => setTimeout(r, ms));

function lsKeys(): string[] {
  const out: string[] = [];
  for (let i = 0; i < window.localStorage.length; i++) {
    const k = window.localStorage.key(i);
    if (k) out.push(k);
  }
  return out;
}

beforeEach(() => {
  window.localStorage.clear();
  useWorkspace.getState().reset();
  navRef.current = null;
});

afterEach(() => {
  cleanup();
  useWorkspace.getState().reset();
  window.localStorage.clear();
  window.history.replaceState(null, "", "/");
});

describe("F2 — fresh storage + /inv/abc docks the sidebar and this investigation's chat", () => {
  it("both starters are docked, once each", async () => {
    mountAt("/inv/abc");
    await act(async () => {});
    const s = useWorkspace.getState();
    expect(s.dockLeftIds).toContain("rw:investigation-sidebar");
    expect(s.dockBottomIds).toContain("rw:chat:abc");
    expect(document.querySelectorAll('[data-stub-panel="InvestigationSidebar"]').length).toBe(1);
    expect(document.querySelectorAll('[data-stub-panel="Chat"]').length).toBe(1);
  });
});

describe("F3 — the per-investigation layout key is written and reset", () => {
  it("writes antiek.workspace.inv.<id>, and 'Reset workspace layout (this investigation)' clears it", async () => {
    // The palette's reset reads window.location (BrowserRouter in the app),
    // so the document URL must match the router's location here.
    window.history.replaceState(null, "", "/inv/abc");
    mountAt("/inv/abc");
    await act(async () => {});
    // The operator changes the layout on this investigation.
    act(() => {
      useWorkspace.getState().open("Notes", {}, { mode: "floating", id: "t:notes", title: "Notes" });
    });
    await act(async () => {
      await wait(300); // the persistence write is debounced at 250 ms
    });
    const keys = lsKeys();
    expect(keys, `the layout must be saved under this investigation's key (keys: ${keys.join(", ")})`).toContain(
      "antiek.workspace.inv.abc",
    );
    expect(keys, "no investigation may write the shared route key").not.toContain(
      "antiek.workspace.route./inv/:id",
    );

    // Run the palette command the way the operator does.
    act(() => {
      window.dispatchEvent(new Event("antiek:palette:toggle"));
    });
    const input = document.querySelector<HTMLInputElement>(
      '[aria-label="Command palette"] input',
    )!;
    fireEvent.change(input, { target: { value: "Reset workspace layout (this investigation)" } });
    // Enter runs the first ranked row (the palette's activeIdx resets to 0).
    const first = document.querySelector('[aria-label="Command palette"] ul li');
    expect(first?.textContent ?? "").toContain("this investigation");
    act(() => {
      fireEvent.keyDown(input, { key: "Enter" });
    });
    expect(lsKeys()).not.toContain("antiek.workspace.inv.abc");
  });
});

describe("F5 — /inv/a → /inv/b opens b's chat starter", () => {
  it("navigating between investigations opens the new investigation's chat and drops the old one", async () => {
    mountAt("/inv/a");
    await act(async () => {});
    expect(useWorkspace.getState().dockBottomIds).toContain("rw:chat:a");

    await act(async () => {
      navRef.current!("/inv/b");
    });

    const s = useWorkspace.getState();
    expect(s.dockBottomIds, "b's chat starter must open on /inv/b").toContain("rw:chat:b");
    expect(Object.keys(s.panels)).not.toContain("rw:chat:a");
    expect(s.dockLeftIds).toContain("rw:investigation-sidebar");
    expect(document.querySelectorAll('[data-stub-panel="InvestigationSidebar"]').length).toBe(1);
  });
});

describe("a saved layout survives the route change (critic r1 #2)", () => {
  it("the sidebar moved right at 555 px on /inv/abc is still there after / → /inv/abc", async () => {
    mountAt("/inv/abc");
    await act(async () => {});
    act(() => {
      useWorkspace.getState().setMode("rw:investigation-sidebar", "docked-right");
      useWorkspace.getState().setSize("rw:investigation-sidebar", { width: 555 });
    });
    await act(async () => {
      await wait(300); // persisted under antiek.workspace.inv.abc
    });
    await act(async () => {
      navRef.current!("/");
    });
    await act(async () => {
      navRef.current!("/inv/abc");
    });
    // The outgoing host's cleanup must not close what hydration restored.
    const p = useWorkspace.getState().panels["rw:investigation-sidebar"];
    expect(p?.mode).toBe("docked-right");
    expect(p?.size.width).toBe(555);
    expect(useWorkspace.getState().dockBottomIds).toContain("rw:chat:abc");
  });
});

