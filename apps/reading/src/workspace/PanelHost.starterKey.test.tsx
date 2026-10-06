/**
 * PanelHost.starterKey.test.tsx — G-X1 (+ GAPS-F5 generalized).
 *
 * React keeps ONE component instance when only a path param changes
 * ("/wrestle" and "/wrestle/:documentId" are two Routes rendering the same
 * element type at the same tree position). PanelHost opens its starters on
 * mount only, so on a param change the route's starters never open: they
 * "never reopen" (GAPS §8 G-X1). MS-01's F5 fixed ResearchWorkstation alone
 * by keying its PanelHost on the investigation id; the generic fix belongs
 * HERE — a starter key derived from the route's params.
 *
 * Three consumers, no React `key` on any of them (the point of the fix):
 *   - the Wrestle shape: starters gated on the route param (/wrestle → /wrestle/:id),
 *   - the Creation shape: static starters (/create → /create/:id) that must
 *     REOPEN when the operator closed one before the route change,
 *   - the Research shape: per-id starters (/inv/a → /inv/b) without MS-01's key.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, cleanup, render } from "@testing-library/react";
import { useEffect } from "react";
import {
  MemoryRouter,
  Route,
  Routes,
  useNavigate,
  useParams,
  type NavigateFunction,
} from "react-router-dom";

import { PanelHost, type StarterPanel } from "./PanelHost";
import { useWorkspace } from "./WorkspaceStore";

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

const navRef: { current: NavigateFunction | null } = { current: null };
function CaptureNavigate() {
  const navigate = useNavigate();
  useEffect(() => {
    navRef.current = navigate;
  }, [navigate]);
  return null;
}

/** WrestleApp shape: starters exist only when the route carries a document id. */
function WrestleProbe() {
  const { documentId } = useParams<{ documentId?: string }>();
  const starters: StarterPanel[] = documentId
    ? [
        {
          kind: "Notes",
          mode: "docked-left",
          props: { documentId },
          title: "Notes · trajectory",
          id: `wrestle:notes:${documentId}`,
        },
        {
          kind: "CrossDocs",
          mode: "docked-right",
          props: { documentId },
          title: "Cross-doc",
          id: `wrestle:crossdocs:${documentId}`,
        },
      ]
    : [];
  return <PanelHost starters={starters}><p>wrestle</p></PanelHost>;
}

/** CreationStudio shape: static starters, whatever the param is. */
function CreateProbe() {
  return (
    <PanelHost
      starters={[
        {
          kind: "DeliverableSidebar",
          mode: "docked-left",
          title: "Deliverables",
          id: "create:deliverable-sidebar",
        },
        {
          kind: "BlockPalette",
          mode: "docked-right",
          title: "Block palette",
          id: "create:block-palette",
        },
      ]}
    >
      <p>create</p>
    </PanelHost>
  );
}

/** ResearchWorkstation shape WITHOUT MS-01's React key. */
function InvProbe() {
  const { investigationId } = useParams<{ investigationId?: string }>();
  const starters: StarterPanel[] = [
    {
      kind: "InvestigationSidebar",
      mode: "docked-left",
      title: "Investigations",
      id: "rw:investigation-sidebar",
    },
    ...(investigationId
      ? ([
          {
            kind: "Chat",
            mode: "docked-bottom",
            props: { parentInvestigationId: investigationId },
            title: "Chat · this investigation",
            id: `rw:chat:${investigationId}`,
          },
        ] as StarterPanel[])
      : []),
  ];
  return <PanelHost starters={starters}><p>inv</p></PanelHost>;
}

function mount(initial: string) {
  return render(
    <MemoryRouter initialEntries={[initial]}>
      <CaptureNavigate />
      <Routes>
        <Route path="/wrestle" element={<WrestleProbe />} />
        <Route path="/wrestle/:documentId" element={<WrestleProbe />} />
        <Route path="/create" element={<CreateProbe />} />
        <Route path="/create/:deliverableId" element={<CreateProbe />} />
        <Route path="/inv/:investigationId" element={<InvProbe />} />
      </Routes>
    </MemoryRouter>,
  );
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
});

describe("G-X1 — PanelHost reopens starters when the route params change", () => {
  it("/wrestle → /wrestle/doc-1 opens the document's starters (Wrestle shape)", async () => {
    mount("/wrestle");
    await act(async () => {});
    expect(useWorkspace.getState().panels["wrestle:notes:doc-1"]).toBeUndefined();

    await act(async () => {
      navRef.current!("/wrestle/doc-1");
    });

    const s = useWorkspace.getState();
    expect(s.dockLeftIds, "the notes starter must dock on /wrestle/doc-1").toContain(
      "wrestle:notes:doc-1",
    );
    expect(s.dockRightIds, "the cross-doc starter must dock on /wrestle/doc-1").toContain(
      "wrestle:crossdocs:doc-1",
    );
  });

  it("/wrestle/doc-1 → /wrestle/doc-2 swaps in the new document's starters", async () => {
    mount("/wrestle/doc-1");
    await act(async () => {});

    await act(async () => {
      navRef.current!("/wrestle/doc-2");
    });

    const s = useWorkspace.getState();
    expect(s.dockLeftIds).toContain("wrestle:notes:doc-2");
    expect(Object.keys(s.panels), "doc-1's starters must be gone").not.toContain(
      "wrestle:notes:doc-1",
    );
  });

  it("/create → /create/x reopens starters the operator closed (Creation shape)", async () => {
    mount("/create");
    await act(async () => {});
    act(() => {
      useWorkspace.getState().close("create:block-palette");
      useWorkspace.getState().close("create:deliverable-sidebar");
    });
    expect(useWorkspace.getState().panels["create:block-palette"]).toBeUndefined();

    await act(async () => {
      navRef.current!("/create/deliv-9");
    });

    const s = useWorkspace.getState();
    expect(s.dockLeftIds, "the route change must reopen the closed starter").toContain(
      "create:deliverable-sidebar",
    );
    expect(s.dockRightIds).toContain("create:block-palette");
  });

  it("/inv/a → /inv/b without a React key opens b's chat and drops a's (F5 generalized)", async () => {
    mount("/inv/a");
    await act(async () => {});
    expect(useWorkspace.getState().dockBottomIds).toContain("rw:chat:a");

    await act(async () => {
      navRef.current!("/inv/b");
    });

    const s = useWorkspace.getState();
    expect(s.dockBottomIds, "b's chat starter must open on /inv/b").toContain("rw:chat:b");
    expect(Object.keys(s.panels)).not.toContain("rw:chat:a");
    expect(s.dockLeftIds).toContain("rw:investigation-sidebar");
  });
});
