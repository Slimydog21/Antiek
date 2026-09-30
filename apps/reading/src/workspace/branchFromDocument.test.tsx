/**
 * branchFromDocument.test.tsx — critic P-D (repair round 1): the operator's
 * headline ask, "tabs for all the links, footnotes, documents triggered from
 * a single document, or deep researches triggered from a single document".
 *
 * At 211e9a7f7 a deep research spun from a reader (navigate('/inv/<id>')) or
 * an in-reader document link (navigate('/read/<doc>')) seeded a ROOT tab in
 * another tree. Here a navigation that carries a branch intent lands as a
 * CHILD of the tab it was triggered from, in that tab's tree.
 *
 * branchNavigation is imported inside each test, so on a tree without it
 * every test fails for that reason alone and the file still runs.
 */
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import { act, cleanup, render, screen, waitFor } from "@testing-library/react";
import { BrowserRouter, useLocation, useNavigate, type NavigateFunction } from "react-router-dom";

beforeAll(() => {
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
});

vi.mock("../lib/api", async (orig) => ({
  ...(await orig<typeof import("../lib/api")>()),
  apiFetch: vi.fn(() =>
    Promise.resolve({ ok: false, status: 404, json: async () => ({}), text: async () => "" }),
  ),
  listInvestigations: vi.fn(async () => ({ count: 0, investigations: [] })),
  getDeliverable: vi.fn(async () => {
    throw new Error("HTTP 404");
  }),
  postTypedEvent: vi.fn(() => Promise.resolve({ event_id: "e" })),
}));

const { tierRef } = vi.hoisted(() => ({ tierRef: { current: "xl" as string } }));
vi.mock("./useViewportTier", () => ({ useViewportTier: () => tierRef.current }));

import { PanelLayout } from "./PanelLayout";
import { useWorkspace } from "./WorkspaceStore";
import { adoptTabForRoute, rootTabId } from "./documentSpace";
import { emptyTabTree, spawnChild, type TabTree } from "./tabTree";
import { useTabTrees } from "./tabTreeStore";

const tabs = () => useTabTrees.getState();
const nav: { current: NavigateFunction | null } = { current: null };

async function flush(n = 6) {
  for (let i = 0; i < n; i++) await act(async () => {});
}

function LocationProbe() {
  const loc = useLocation();
  nav.current = useNavigate();
  return <span data-testid="location">{loc.pathname + loc.search}</span>;
}

function mount(path: string) {
  window.history.replaceState({}, "", path);
  return render(
    <BrowserRouter>
      <LocationProbe />
      <PanelLayout mainSlot={<p>content</p>} />
    </BrowserRouter>,
  );
}

/** A runtime path, so the file still transforms where the module is absent. */
const BRANCH_MODULE = "./branchNavigation";
async function loadBranchNavigation(): Promise<typeof import("./branchNavigation")> {
  return import(/* @vite-ignore */ BRANCH_MODULE);
}

const here = () => ({ pathname: window.location.pathname, search: window.location.search });

beforeEach(() => {
  tierRef.current = "xl";
  useWorkspace.getState().reset();
  useWorkspace.getState().setLayoutPreset("docked");
  tabs().resetTabTrees();
});

afterEach(() => {
  cleanup();
  useWorkspace.getState().reset();
  tabs().resetTabTrees();
  document.body.innerHTML = "";
  window.history.replaceState({}, "", "/");
});

function readerTree(): TabTree {
  const r = spawnChild(emptyTabTree("reading"), null, {
    tab_id: "root:reader:doc-9",
    kind: "reader",
    ref: "doc-9",
    mothership: "reading",
  });
  if (!r.ok) throw new Error(r.error.message);
  return r.tree;
}

describe("P-D — a branch from a document lands as a child of its tab", () => {
  it("adoptTabForRoute: a branch intent spawns under its parent, not a root", async () => {
    const tree = readerTree();
    const intent = {
      parentTabId: "root:reader:doc-9",
      mothership: "reading" as const,
      origin: { document_id: "doc-9", kind: "research" as const },
    };
    const a = adoptTabForRoute(tree, "/inv/new-1", intent);
    expect(a).toEqual({
      action: "branch",
      parentId: "root:reader:doc-9",
      ref: { kind: "research", ref: "/inv/new-1" },
      origin: intent.origin,
    });
    // Without the intent the same route still seeds a root (typed URL, Back).
    expect(adoptTabForRoute(tree, "/inv/new-1")).toEqual({
      action: "seed",
      ref: { kind: "research", ref: "/inv/new-1" },
    });
    // An intent whose parent is gone falls back to a root, never a dangling child.
    expect(adoptTabForRoute(tree, "/inv/new-1", { ...intent, parentTabId: "gone" }).action).toBe("seed");
  });

  it("a deep research spun from a reader is a research child of the reader tab, in the reading tree", async () => {
    const { branchNavigation } = await loadBranchNavigation();
    mount("/read/doc-9");
    await waitFor(() => expect(tabs().trees.reading?.active_tab_id ?? null).not.toBeNull());
    await flush();
    const readerRoot = tabs().trees.reading!.active_tab_id!;
    expect(readerRoot).toBe(rootTabId({ kind: "reader", ref: "doc-9" }));

    const go = branchNavigation("/inv/new-1", here(), { document_id: "doc-9", kind: "research", page_index: 3 });
    act(() => nav.current!(go.to, go.options));
    await flush();

    // The research opens at its own route, filed under the reading tree.
    expect(screen.getByTestId("location").textContent).toBe("/inv/new-1?m=reading");
    const reading = tabs().trees.reading!;
    const child = reading.nodes[reading.active_tab_id!];
    expect(child.kind).toBe("research");
    expect(child.ref).toBe("/inv/new-1");
    expect(child.parent_tab_id).toBe(readerRoot);
    expect(child.branch_origin).toEqual({
      document_id: "doc-9",
      kind: "research",
      anchor: { document_id: "doc-9", page_index: 3 },
    });
    expect(reading.nodes[readerRoot].child_order).toEqual([child.tab_id]);
    // No root was minted in the research tree.
    const research = tabs().trees.research;
    expect(research ? research.root_order : []).toEqual([]);

    // Back to the reader and the same branch again: the open child is reused.
    act(() => nav.current!("/read/doc-9"));
    await flush();
    expect(tabs().trees.reading!.active_tab_id).toBe(readerRoot);
    const again = branchNavigation("/inv/new-1", here(), { document_id: "doc-9", kind: "research" });
    act(() => nav.current!(again.to, again.options));
    await flush();
    const after = tabs().trees.reading!;
    expect(after.active_tab_id).toBe(child.tab_id);
    expect(after.nodes[readerRoot].child_order).toEqual([child.tab_id]);
  });

  it("an in-reader document link is a reader child of the reader tab", async () => {
    const { branchNavigation } = await loadBranchNavigation();
    mount("/read/doc-9");
    await waitFor(() => expect(tabs().trees.reading?.active_tab_id ?? null).not.toBeNull());
    await flush();
    const readerRoot = tabs().trees.reading!.active_tab_id!;
    const go = branchNavigation("/read/doc-10", here(), { document_id: "doc-9", kind: "reference" });
    // Same tree: no ?m= needed.
    expect(go.to).toBe("/read/doc-10");
    act(() => nav.current!(go.to, go.options));
    await flush();
    const reading = tabs().trees.reading!;
    const child = reading.nodes[reading.active_tab_id!];
    expect(child.ref).toBe("doc-10");
    expect(child.parent_tab_id).toBe(readerRoot);
    expect(reading.root_order).toEqual([readerRoot]);
  });

  it("a Write trace to a source is a reader child of the piece tab and keeps the writing tree", async () => {
    const { branchNavigation } = await loadBranchNavigation();
    mount("/write/A");
    await waitFor(() => expect(tabs().trees.writing?.active_tab_id ?? null).not.toBeNull());
    await flush();
    const piece = tabs().trees.writing!.active_tab_id!;
    const go = branchNavigation("/read/doc-3", here(), { document_id: "doc-3", kind: "citation" });
    expect(go.to).toBe("/read/doc-3?m=writing");
    act(() => nav.current!(go.to, go.options));
    await flush();
    const writing = tabs().trees.writing!;
    expect(writing.nodes[writing.active_tab_id!].parent_tab_id).toBe(piece);
    expect(tabs().trees.reading ? tabs().trees.reading!.root_order : []).toEqual([]);
  });

  it("before any tree has loaded, the navigation is a plain one (no guessed parent)", async () => {
    const { branchNavigation } = await loadBranchNavigation();
    window.history.replaceState({}, "", "/read/doc-9");
    const go = branchNavigation("/inv/new-1", here(), { document_id: "doc-9", kind: "research" });
    expect(go).toEqual({ to: "/inv/new-1" });
  });
});
