/**
 * WrestleApp.starterKey.test.tsx — G-X1 on the named surface.
 *
 * `/wrestle` and `/wrestle/:documentId` render WrestleApp at the same tree
 * position, so React keeps ONE instance across the param change. Two things
 * used to keep the document's starters shut there: PanelHost opened starters
 * on mount only (fixed by the starter key in PanelHost.tsx), and WrestleApp
 * kept the document id in state initialised once from the param. This mounts
 * the real route component and proves the starters follow the route.
 */
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import { act, cleanup, render } from "@testing-library/react";
import { useEffect } from "react";
import {
  MemoryRouter,
  Route,
  Routes,
  useNavigate,
  type NavigateFunction,
} from "react-router-dom";

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
vi.mock("../../api/books", () => ({
  getBook: vi.fn(() => Promise.resolve({ title: "stub book" })),
}));
vi.mock("../../hooks/useEventStream", () => ({
  useEventStream: () => ({ events: [], status: "idle", reconnects: 0 }),
}));
vi.mock("../../lib/api", async (orig) => ({
  ...(await orig<typeof import("../../lib/api")>()),
  postTypedEvent: vi.fn(() => Promise.resolve({ ok: true })),
}));
vi.mock("../../components/PdfViewer", () => ({
  default: () => <div data-stub-panel="PdfViewer" />,
}));

import { useWorkspace } from "../../workspace/WorkspaceStore";
import WrestleApp from "./index";

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
      <CaptureNavigate />
      <Routes>
        <Route path="/wrestle" element={<WrestleApp />} />
        <Route path="/wrestle/:documentId" element={<WrestleApp />} />
      </Routes>
    </MemoryRouter>,
  );
}

beforeEach(() => {
  window.localStorage.clear();
  window.sessionStorage.clear();
  useWorkspace.getState().reset();
  navRef.current = null;
});

afterEach(() => {
  cleanup();
  useWorkspace.getState().reset();
  window.localStorage.clear();
  window.sessionStorage.clear();
});

describe("G-X1 — WrestleApp starters follow /wrestle/:documentId across the route change", () => {
  it("/wrestle → /wrestle/doc-1 docks the document's Notes and CrossDocs", async () => {
    mountAt("/wrestle");
    await act(async () => {});
    expect(useWorkspace.getState().panels["wrestle:notes:inv"]).toBeUndefined();

    await act(async () => {
      navRef.current!("/wrestle/doc-1");
    });

    // The starter ids embed the tab-stable investigation id, not the document,
    // so assert on the dock presence (and the props via the panel descriptor).
    const s = useWorkspace.getState();
    const notes = Object.values(s.panels).find((p) => p.kind === "Notes");
    const cross = Object.values(s.panels).find((p) => p.kind === "CrossDocs");
    expect(notes, "the notes starter must dock on /wrestle/doc-1").toBeTruthy();
    expect(cross, "the cross-doc starter must dock on /wrestle/doc-1").toBeTruthy();
    expect(notes?.mode).toBe("docked-left");
    expect(cross?.mode).toBe("docked-right");
  });

  it("/wrestle/doc-1 → /wrestle/doc-2 reopens the starters against the new document", async () => {
    mountAt("/wrestle/doc-1");
    await act(async () => {});
    const before = Object.values(useWorkspace.getState().panels).find((p) => p.kind === "Notes");
    expect(before?.props?.documentId).toBe("doc-1");

    await act(async () => {
      navRef.current!("/wrestle/doc-2");
    });

    const after = Object.values(useWorkspace.getState().panels).find((p) => p.kind === "Notes");
    expect(after, "the notes starter must reopen on /wrestle/doc-2").toBeTruthy();
    expect(after?.props?.documentId, "the reopened starter must carry the new document").toBe(
      "doc-2",
    );
  });
});
