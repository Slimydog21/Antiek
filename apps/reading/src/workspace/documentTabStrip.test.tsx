/**
 * documentTabStrip.test.tsx — cockpit chrome PR 3 (D6) acceptance.
 *
 *   The left document tab strip over Opus's pure tabTree model: route-seeded
 *   root tabs, the active path with hier numbers, the Opus Trail as the
 *   ancestry breadcrumb (its one-entity integrity contract never bent), the
 *   tree panel with subtree focus, spawns landing as CHILD tabs (the
 *   cross-pane seam, a research open-in-reader call, a footnote-shaped
 *   reference spawn), close/prune with the undo affordance, and the D6 key
 *   rows (sibling/parent/child/close/prune/tree-toggle) — never from text
 *   fields. The model's own suites (tabTree.test.ts, tabTree.property.test.ts)
 *   run unmodified alongside.
 *
 * The dispatcher runs with REAL handlers; navigation is asserted on the
 * MemoryRouter's location.
 */
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import { act, cleanup, render, screen } from "@testing-library/react";
import { BrowserRouter, useLocation } from "react-router-dom";

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
  apiFetch: vi.fn(() => Promise.resolve({ ok: false, status: 404, json: async () => ({}) })),
  postTypedEvent: vi.fn(() => Promise.resolve({ event_id: "e" })),
}));

import { prefixState } from "../components/hotkeys/prefixState";
import { labelForTab } from "./DocumentTabStrip";
import { PanelLayout } from "./PanelLayout";
import { openDocumentInLeftPane } from "./crossPane";
import { mothershipForPath } from "./documentSpace";
import { useWorkspace } from "./WorkspaceStore";
import { useTabTrees } from "./tabTreeStore";
import { installShortcuts } from "./shortcuts";
import { pinPlatform, press, unpinPlatform } from "./keymapTestKit";

const { tierRef } = vi.hoisted(() => ({ tierRef: { current: "xl" as string } }));
vi.mock("./useViewportTier", () => ({
  useViewportTier: () => tierRef.current,
}));

let uninstall: (() => void) | null = null;
const tabs = () => useTabTrees.getState();

function key(target: EventTarget, spec: string): KeyboardEvent {
  let e = new KeyboardEvent("keydown");
  act(() => {
    e = press(target, spec, "mac");
  });
  return e;
}

/** The live route, exposed to assertions. */
function LocationProbe() {
  const loc = useLocation();
  return <span data-testid="location">{loc.pathname}</span>;
}

function mountStrip(initialPath: string) {
  // BrowserRouter (not MemoryRouter): the production location source is
  // window.location — the strip reads it through useLocation and the
  // tab-tree key handlers through mothershipForPath(window.location) —
  // and jsdom's history API tracks pushState, so tests see the real thing.
  window.history.replaceState({}, "", initialPath);
  return render(
    <BrowserRouter>
      <LocationProbe />
      <PanelLayout mainSlot={<p>route content</p>} />
    </BrowserRouter>,
  );
}

beforeEach(() => {
  pinPlatform("mac");
  tierRef.current = "xl";
  useWorkspace.getState().reset();
  useWorkspace.getState().setLayoutPreset("docked");
  tabs().resetTabTrees();
  uninstall = installShortcuts(vi.fn() as never);
});

afterEach(() => {
  uninstall?.();
  uninstall = null;
  cleanup();
  prefixState.disarm();
  useWorkspace.getState().reset();
  useWorkspace.getState().setLayoutPreset("docked");
  tabs().resetTabTrees();
  unpinPlatform();
  document.body.innerHTML = "";
  window.history.replaceState({}, "", "/");
  window.localStorage.removeItem("antiek.workspace.layout-preset");
});

const M = () => mothershipForPath(window.location.pathname);

// ─── route seeding + the active path ─────────────────────────────────────

describe("route seeding and the active path", () => {
  it("a /read/:id route seeds a root reader tab with hier number 1", async () => {
    mountStrip("/read/doc-9");
    await screen.findByText("doc-9");
    const tree = tabs().trees[M()]!;
    const root = Object.values(tree.nodes).find((n) => n.parent_tab_id === null);
    expect(root?.kind).toBe("reader");
    expect(root?.ref).toBe("doc-9");
    expect(root?.hier_number).toBe("1");
    expect(tree.active_tab_id).toBe(root?.tab_id);
  });

  it("a /inv/:id route seeds a root research tab in the research mothership", async () => {
    mountStrip("/inv/inv-1");
    await screen.findAllByText("/inv/inv-1");
    const tree = tabs().trees.research!;
    const root = Object.values(tree.nodes).find((n) => n.parent_tab_id === null);
    expect(root?.kind).toBe("research");
    expect(root?.ref).toBe("/inv/inv-1");
  });

  it("child spawns take hierarchical numbers and render on the active path", async () => {
    mountStrip("/read/doc-9");
    await screen.findByText("doc-9");
    const m = M();
    const rootId = tabs().trees[m]!.active_tab_id!;
    act(() => {
      tabs().spawnTab(m, rootId, {
        tab_id: "child-footnote",
        origin: { document_id: "doc-9", kind: "footnote", anchor: { document_id: "doc-9", quote: "the footnote text" } },
        kind: "reader",
        ref: "doc-9",
        mothership: m,
        activate: true,
      });
    });
    const tree = tabs().trees[m]!;
    expect(tree.nodes["child-footnote"].hier_number).toBe("1.1");
    expect(tree.nodes["child-footnote"].parent_tab_id).toBe(rootId);
    // The active path shows root › child with hier numbers.
    expect(screen.getByText("1.1")).toBeTruthy();
    expect(labelForTab(tree.nodes["child-footnote"])).toBe("the footnote text");
  });
});

// ─── the breadcrumb (the Opus Trail, lawfully driven) ────────────────────

describe("the ancestry breadcrumb", () => {
  it("renders the Opus Trail over the path — one canonical entity, never a fork", async () => {
    mountStrip("/read/doc-9");
    await screen.findByText("doc-9");
    const m = M();
    const rootId = tabs().trees[m]!.active_tab_id!;
    act(() => {
      tabs().spawnTab(m, rootId, {
        tab_id: "child-ref",
        origin: { document_id: "doc-9", kind: "footnote" },
        kind: "reader",
        ref: "doc-9",
        mothership: m,
        activate: true,
      });
    });
    // The Trail renders: a single-entity Thread (its fork guard must NOT trip).
    expect(document.querySelector('[data-tab-trail] [data-testid="thread-breadcrumb"]')).toBeTruthy();
    expect(document.querySelector('[data-testid="thread-breadcrumb-integrity-warning"]')).toBeNull();
    // Two hops: root (reader) and the footnote branch, current = the child.
    expect(document.querySelector('[data-testid="thread-hop-current-read"]')?.textContent).toContain("footnote");
  });
});

// ─── the tree panel + subtree focus ──────────────────────────────────────

describe("the tree panel (prefix t)", () => {
  it("toggles the full tree and focuses a subtree honestly", async () => {
    mountStrip("/read/doc-9");
    await screen.findByText("doc-9");
    const m = M();
    const rootId = tabs().trees[m]!.active_tab_id!;
    act(() => {
      tabs().spawnTab(m, rootId, { tab_id: "c1", kind: "reader", ref: "doc-9", mothership: m, activate: false });
      tabs().spawnTab(m, "c1", { tab_id: "c1-1", kind: "reader", ref: "doc-9", mothership: m, activate: false });
    });
    key(document.body, "ctrl+b");
    key(document.body, "t");
    expect(tabs().treePanelOpen).toBe(true);
    expect(document.querySelector('[data-tab-tree-panel]')).toBeTruthy();
    expect(document.querySelector('[data-tree-row="c1-1"]')).toBeTruthy();
    // Subtree focus narrows the panel to c1's subtree; "show full tree" returns.
    const focusButtons = document.querySelectorAll('[data-tree-row="c1"] [aria-label^="Focus the subtree"]');
    act(() => {
      (focusButtons[0] as HTMLElement).click();
    });
    expect(document.querySelector('[data-tab-tree-panel]')!.textContent).toContain("Subtree of 1.1");
    expect(document.querySelector('[data-tree-row="c1-1"]')).toBeTruthy();
    act(() => {
      screen.getByText("show full tree").click();
    });
    expect(document.querySelector('[data-tab-tree-panel]')!.textContent).toContain("All tabs");
    key(document.body, "ctrl+b");
    key(document.body, "t");
    expect(tabs().treePanelOpen).toBe(false);
  });

  it("the ctrl+alt+y twin also toggles the panel", async () => {
    mountStrip("/read/doc-9");
    await screen.findByText("doc-9");
    key(document.body, "ctrl+alt+y");
    expect(tabs().treePanelOpen).toBe(true);
  });
});

// ─── spawns land as child tabs ───────────────────────────────────────────

describe("spawn seams", () => {
  it("the cross-pane seam spawns a reader child tab under the active tab", async () => {
    mountStrip("/inv/inv-1");
    await screen.findAllByText("/inv/inv-1");
    const rootId = tabs().trees.research!.active_tab_id!;
    act(() => {
      openDocumentInLeftPane("doc-9", { from: "companion", investigationId: "inv-1" });
    });
    await act(async () => {});
    await act(async () => {});
    const tree = tabs().trees.research!;
    const child = Object.values(tree.nodes).find((n) => n.kind === "reader" && n.ref === "doc-9");
    expect(child).toBeTruthy();
    expect(child!.parent_tab_id).toBe(rootId);
    expect(child!.hier_number).toBe("1.1");
    expect(child!.branch_origin?.kind).toBe("reference");
    // Re-opening the same document under the same parent activates, never duplicates.
    act(() => {
      openDocumentInLeftPane("doc-9", { from: "companion", investigationId: "inv-1" });
    });
    await act(async () => {});
    await act(async () => {});
    expect(
      Object.values(tabs().trees.research!.nodes).filter((n) => n.kind === "reader" && n.ref === "doc-9"),
    ).toHaveLength(1);
  });

  it("a research open-in-reader call (the unit-4 shape) spawns a child tab too", async () => {
    // The exact call the research surfaces' "open in reader" affordance makes
    // through the same seam — proven once, used by every future caller.
    mountStrip("/inv/inv-1");
    await screen.findAllByText("/inv/inv-1");
    act(() => {
      openDocumentInLeftPane("doc-source", { from: "research", investigationId: "inv-1" });
    });
    await act(async () => {});
    await act(async () => {});
    const tree = tabs().trees.research!;
    const child = Object.values(tree.nodes).find((n) => n.kind === "reader" && n.ref === "doc-source");
    expect(child).toBeTruthy();
    expect(child!.hier_number).toBe("1.1");
  });

  it("a reader child tab activation navigates to the canonical /read route (tree → route)", async () => {
    mountStrip("/inv/inv-1");
    await screen.findAllByText("/inv/inv-1");
    act(() => {
      openDocumentInLeftPane("doc-9", { from: "companion" });
    });
    await act(async () => {});
    await act(async () => {});
    await screen.findByText("doc-9");
    // The strip's tree→route sync navigated to the document's canonical URL.
    expect(screen.getByTestId("location").textContent).toBe("/read/doc-9");
    // …and the reading mothership's tree now hosts the document as its root.
    const reading = tabs().trees.reading;
    expect(reading && Object.values(reading.nodes).some((n) => n.kind === "reader" && n.ref === "doc-9")).toBe(true);
  });
});

// ─── the key rows: parent / child / sibling / close / prune / undo ───────

describe("the tab-tree keys", () => {
  async function seedTree() {
    mountStrip("/read/doc-9");
    await screen.findByText("doc-9");
    const m = M();
    const rootId = tabs().trees[m]!.active_tab_id!;
    act(() => {
      tabs().spawnTab(m, rootId, { tab_id: "c1", kind: "reader", ref: "doc-a", mothership: m, activate: false });
      tabs().spawnTab(m, rootId, { tab_id: "c2", kind: "reader", ref: "doc-b", mothership: m, activate: false });
    });
    return { m, rootId };
  }

  it("prefix u goes to the parent; prefix o descends to the last-visited child", async () => {
    const { m } = await seedTree();
    act(() => tabs().activateTab(m, "c2"));
    key(document.body, "ctrl+b");
    key(document.body, "u");
    const tree = tabs().trees[m]!;
    expect(tree.active_tab_id).toBe(tree.nodes["c2"].parent_tab_id);
    // Descending retraces the last-visited child (c2, just visited).
    key(document.body, "ctrl+b");
    key(document.body, "o");
    expect(tabs().trees[m]!.active_tab_id).toBe("c2");
    // The chord twins work too.
    key(document.body, "ctrl+alt+u");
    key(document.body, "ctrl+alt+o");
    expect(tabs().trees[m]!.active_tab_id).toBe("c2");
  });

  it("prefix n/p cycle SIBLINGS (the corpus's canonical tab keys, retargeted from PR 2)", async () => {
    const { m } = await seedTree();
    act(() => tabs().activateTab(m, "c1"));
    key(document.body, "ctrl+b");
    key(document.body, "n");
    expect(tabs().trees[m]!.active_tab_id).toBe("c2");
    key(document.body, "ctrl+b");
    key(document.body, "n"); // wraps to c1
    expect(tabs().trees[m]!.active_tab_id).toBe("c1");
    key(document.body, "ctrl+b");
    key(document.body, "p");
    expect(tabs().trees[m]!.active_tab_id).toBe("c2");
    key(document.body, "ctrl+alt+[");
    expect(tabs().trees[m]!.active_tab_id).toBe("c1");
    key(document.body, "ctrl+alt+]");
    expect(tabs().trees[m]!.active_tab_id).toBe("c2");
  });

  it("prefix c closes with lift_children (children keep their numbers); undo restores", async () => {
    const { m } = await seedTree();
    act(() => {
      tabs().spawnTab(m, "c1", { tab_id: "c1-1", kind: "reader", ref: "doc-a1", mothership: m, activate: false });
      tabs().activateTab(m, "c1");
    });
    key(document.body, "ctrl+b");
    key(document.body, "c");
    let tree = tabs().trees[m]!;
    expect(tree.nodes["c1"]).toBeUndefined();
    // The child LIFTED into c1's place under the root, keeping its hier
    // number (addresses are never renumbered on lift).
    expect(tree.nodes["c1-1"].hier_number).toBe("1.1.1");
    expect(tree.nodes["root:reader:doc-9"].child_order).toContain("c1-1");
    expect(tabs().lastUndo).toBeTruthy();
    // The undo affordance restores the exact tree.
    const undoBtn = document.querySelector("[data-undo-close]")!;
    expect(undoBtn).toBeTruthy();
    act(() => {
      (undoBtn as HTMLElement).click();
    });
    tree = tabs().trees[m]!;
    expect(tree.nodes["c1"]).toBeTruthy();
    expect(tree.nodes["c1"].child_order).toContain("c1-1");
    expect(tabs().lastUndo).toBeNull();
  });

  it("prefix shift+x prunes the whole subtree (soft close, numbers kept in history)", async () => {
    const { m } = await seedTree();
    act(() => {
      tabs().spawnTab(m, "c1", { tab_id: "c1-1", kind: "reader", ref: "doc-a1", mothership: m, activate: false });
      tabs().activateTab(m, "c1");
    });
    key(document.body, "ctrl+b");
    key(document.body, "shift+x");
    const tree = tabs().trees[m]!;
    expect(tree.nodes["c1"]).toBeUndefined();
    expect(tree.nodes["c1-1"]).toBeUndefined();
    expect(tree.history["c1"].node.hier_number).toBe("1.1");
    expect(tree.history["c1-1"].node.hier_number).toBe("1.1.1");
    // The surface the tab pointed at is untouched (tab ≠ branch): the ref is
    // navigation state only, and the close wrote nothing but tree history.
  });

  it("the keys are honest no-ops before the tree loads, and never fire from a text field", async () => {
    // No strip mounted, no tree loaded: the keys must do nothing, silently.
    for (const k of ["u", "o", "c"]) {
      key(document.body, "ctrl+b");
      key(document.body, k);
    }
    expect(tabs().trees.reading).toBeNull();
    // From a text field the prefix never arms and the key stays the field's.
    await seedTree();
    const input = document.createElement("input");
    document.body.appendChild(input);
    input.focus();
    for (const k of ["u", "o", "c", "n", "p", "t"]) {
      key(input, "ctrl+b");
      expect(prefixState.isArmed(), `prefix must not arm in text (for ${k})`).toBe(false);
      const e = key(input, k);
      expect(e.defaultPrevented, `'${k}' must reach the field as a character`).toBe(false);
    }
  });
});

// ─── persistence through the adapter (§1.6) ─────────────────────────────

describe("the adapter path", () => {
  it("operations persist through the in-memory adapter (session-scoped, honest)", async () => {
    mountStrip("/read/doc-9");
    await screen.findByText("doc-9");
    // The save pipeline is queued; flush it and reload through the adapter.
    await act(async () => {});
    await act(async () => {});
    const snapshot = await tabs().adapter.load("default", M());
    const refs = Object.values(snapshot.tree.nodes).map((n) => n.ref);
    expect(refs).toContain("doc-9");
    expect(snapshot.tree.mothership).toBe(M());
    // §1.6 honesty: nothing in web storage carries tab state.
    for (let i = 0; i < window.localStorage.length; i++) {
      expect(window.localStorage.key(i)).not.toContain("tabtree");
      expect(window.localStorage.key(i)).not.toContain("tab-tree");
    }
  });
});
