/**
 * documentTabs.stage2.test.tsx — cockpit lane A, stage 2 (document tabs).
 *
 * One describe block per forensic defect (FORENSIC-KIMI-DESIGN-2026-09-26,
 * numbered as there) plus DESIGN-MODEL §2a's path header, indent cap and
 * virtualised tree. Every test drives a surface that already existed on the
 * integrated-but-unfixed carrier (e1f024b22): the strip mounted by
 * PanelLayout, the tab-tree store, the keymap dispatcher, the toast
 * viewport, the companion pane. So each one fails there for the defect's
 * own reason, not for a missing import.
 *
 * Titles come through the real resolvers over a routed apiFetch mock
 * (books.ts closes over the mocked apiFetch; listInvestigations and
 * getDeliverable are mocked directly because lib/api closes over its own).
 */
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
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

const api = vi.hoisted(() => ({
  /** url suffix → JSON body (200). Anything else answers 404. */
  routes: new Map<string, unknown>(),
  investigations: [] as { investigation_id: string; question: string | null }[],
  deliverables: new Map<string, unknown>(),
}));

vi.mock("../lib/api", async (orig) => ({
  ...(await orig<typeof import("../lib/api")>()),
  apiFetch: vi.fn((url: string) => {
    for (const [suffix, body] of api.routes) {
      if (url.endsWith(suffix)) {
        return Promise.resolve({ ok: true, status: 200, json: async () => body, text: async () => "" });
      }
    }
    return Promise.resolve({ ok: false, status: 404, json: async () => ({}), text: async () => "" });
  }),
  listInvestigations: vi.fn(async () => ({
    count: api.investigations.length,
    investigations: api.investigations.map((i) => ({
      status: "completed",
      started_at: null,
      completed_at: null,
      cost_usd_total: 0,
      parent_investigation_id: null,
      ...i,
    })),
  })),
  getDeliverable: vi.fn(async (id: string) => {
    const d = api.deliverables.get(id);
    if (!d) throw new Error("HTTP 404");
    return d;
  }),
  postTypedEvent: vi.fn(() => Promise.resolve({ event_id: "e" })),
}));

import { prefixState } from "../components/hotkeys/prefixState";
import { LemonToastViewport } from "../components/lemon/LemonToast";
import CompanionPane from "./CompanionPane";
import WriteOutlinePane from "./WriteOutlinePane";
import { useCompanion } from "./companionStore";
import { PanelLayout } from "./PanelLayout";
import { openDocumentInLeftPane } from "./crossPane";
import { mothershipForPath, rootRefForPath } from "./documentSpace";
import { useWorkspace } from "./WorkspaceStore";
import { useTabTrees } from "./tabTreeStore";
import { installShortcuts } from "./shortcuts";
import { pinPlatform, press, unpinPlatform } from "./keymapTestKit";
import {
  createInMemoryTabTreeAdapter,
  type Mothership,
  type TabTreeAdapter,
  type TabTreeSnapshot,
} from "./tabTree";

const { tierRef } = vi.hoisted(() => ({ tierRef: { current: "xl" as string } }));
vi.mock("./useViewportTier", () => ({
  useViewportTier: () => tierRef.current,
}));

let uninstall: (() => void) | null = null;
const tabs = () => useTabTrees.getState();
const nav: { current: NavigateFunction | null } = { current: null };

function key(target: EventTarget, spec: string): KeyboardEvent {
  let e = new KeyboardEvent("keydown");
  act(() => {
    e = press(target, spec, "mac");
  });
  return e;
}

function LocationProbe() {
  const loc = useLocation();
  nav.current = useNavigate();
  return <span data-testid="location">{loc.pathname + loc.search}</span>;
}

function mountStrip(initialPath: string) {
  window.history.replaceState({}, "", initialPath);
  return render(
    <BrowserRouter>
      <LocationProbe />
      <PanelLayout mainSlot={<p>route content</p>} />
      <LemonToastViewport />
    </BrowserRouter>,
  );
}

async function flush(n = 4) {
  for (let i = 0; i < n; i++) await act(async () => {});
}

const M = (): Mothership => mothershipForPath(window.location.pathname);

async function mountLoaded(path: string, m: Mothership = mothershipForPath(path)) {
  mountStrip(path);
  await waitFor(() => expect(tabs().trees[m]?.active_tab_id ?? null).not.toBeNull());
  await flush();
  return tabs().trees[m]!.active_tab_id!;
}

function spawn(m: Mothership, parent: string | null, id: string, ref: string, quote?: string, activate = false) {
  act(() => {
    const r = tabs().spawnTab(m, parent, {
      tab_id: id,
      kind: "reader",
      ref,
      mothership: m,
      activate,
      ...(quote
        ? { origin: { document_id: ref, kind: "footnote" as const, anchor: { document_id: ref, quote } } }
        : {}),
    });
    if (!r.ok) throw new Error(r.error);
  });
}

/** A chain of `depth` tabs on the same surface (footnote hops), deepest active. */
function chain(m: Mothership, rootId: string, depth: number): string[] {
  const ids = [rootId];
  for (let i = 1; i < depth; i++) {
    const id = `hop-${i}`;
    spawn(m, ids[i - 1], id, "doc-9", `hop ${i}`);
    ids.push(id);
  }
  act(() => tabs().activateTab(m, ids[ids.length - 1]));
  return ids;
}

function openTreePanel() {
  key(document.body, "ctrl+b");
  key(document.body, "t");
  expect(tabs().treePanelOpen).toBe(true);
}

const rowIds = () =>
  Array.from(document.querySelectorAll("[data-tab-tree-panel] [data-tree-row]")).map((el) =>
    el.getAttribute("data-tree-row"),
  );

beforeEach(() => {
  pinPlatform("mac");
  tierRef.current = "xl";
  api.routes.clear();
  api.investigations = [];
  api.deliverables.clear();
  useWorkspace.getState().reset();
  useWorkspace.getState().setLayoutPreset("docked");
  tabs().resetTabTrees();
  uninstall = installShortcuts(vi.fn() as never);
});

afterEach(() => {
  vi.useRealTimers();
  uninstall?.();
  uninstall = null;
  cleanup();
  prefixState.disarm();
  useWorkspace.getState().reset();
  useWorkspace.getState().setLayoutPreset("docked");
  useCompanion.getState().reset();
  tabs().resetTabTrees();
  unpinPlatform();
  document.body.innerHTML = "";
  window.history.replaceState({}, "", "/");
  window.localStorage.removeItem("antiek.workspace.layout-preset");
});

// ─── defect 2: route sync adopts; a child stays a child ─────────────────

describe("defect 2 — a child tab stays a child through activation and route changes", () => {
  it("same mothership: activating a reader child adopts it, never seeds a new root", async () => {
    const rootId = await mountLoaded("/read/doc-9");
    const m = M();
    spawn(m, rootId, "child-ref", "doc-10");
    act(() => tabs().activateTab(m, "child-ref"));
    await flush(6);
    expect(screen.getByTestId("location").textContent).toBe("/read/doc-10");
    const tree = tabs().trees.reading!;
    expect(tree.active_tab_id).toBe("child-ref");
    expect(tree.nodes["child-ref"].parent_tab_id).toBe(rootId);
    expect(tree.root_order).toEqual([rootId]);
    expect(tree.nodes["root:reader:doc-10"]).toBeUndefined();
  });

  it("across motherships: a research-spawned reader child keeps the research tree", async () => {
    const rootId = await mountLoaded("/inv/inv-1");
    act(() => openDocumentInLeftPane("doc-9", { from: "companion", investigationId: "inv-1" }));
    await flush(8);
    const research = tabs().trees.research!;
    const child = Object.values(research.nodes).find((n) => n.kind === "reader" && n.ref === "doc-9")!;
    expect(child.parent_tab_id).toBe(rootId);
    expect(research.active_tab_id).toBe(child.tab_id);
    // The document is on screen at its canonical path…
    const childUrl = screen.getByTestId("location").textContent!;
    expect(childUrl.startsWith("/read/doc-9")).toBe(true);
    // …but no reading-tree root was minted for it: the child did not switch trees.
    const reading = tabs().trees.reading;
    expect(reading ? Object.values(reading.nodes).filter((n) => n.ref === "doc-9") : []).toHaveLength(0);
    expect(mothershipForPath(window.location.pathname, window.location.search)).toBe("research");

    // A route change away and back: the root is adopted, then the child again.
    act(() => nav.current!("/inv/inv-1"));
    await flush(6);
    expect(tabs().trees.research!.active_tab_id).toBe(rootId);
    act(() => nav.current!(childUrl));
    await flush(6);
    const after = tabs().trees.research!;
    expect(after.active_tab_id).toBe(child.tab_id);
    expect(after.nodes[child.tab_id].parent_tab_id).toBe(rootId);
    expect(after.root_order).toEqual([rootId]);
  });
});

// ─── defect 3: depth-first tree panel ────────────────────────────────────

describe("defect 3 — the tree panel lists rows depth-first", () => {
  it("three roots with nested children draw each child under its own parent", async () => {
    const r1 = await mountLoaded("/read/doc-9");
    const m = M();
    spawn(m, null, "r2", "doc-r2");
    spawn(m, null, "r3", "doc-r3");
    spawn(m, r1, "a", "doc-9", "a");
    spawn(m, "a", "a1", "doc-9", "a1");
    spawn(m, r1, "b", "doc-9", "b");
    spawn(m, "r2", "c", "doc-r2", "c");
    spawn(m, "r3", "d", "doc-r3", "d");
    spawn(m, "d", "d1", "doc-r3", "d1");
    openTreePanel();
    expect(rowIds()).toEqual([r1, "a", "a1", "b", "r2", "c", "r3", "d", "d1"]);
  });
});

// ─── defect 4: titles, siblings, the ↳n chip ─────────────────────────────

describe("defect 4 — labels from titles, siblings and the ↳n chip", () => {
  it("a reader tab shows its document title, never the raw id", async () => {
    api.routes.set("/books/doc-9", { document_id: "doc-9", title: "On the Origin of Species" });
    await mountLoaded("/read/doc-9");
    const strip = document.querySelector("[data-document-strip]")!;
    await waitFor(() => expect(strip.textContent).toContain("On the Origin of Species"));
    expect(strip.textContent).not.toContain("doc-9");
  });

  it("a research tab shows its question; an unknown one a readable noun, never '/inv/<id>'", async () => {
    api.investigations = [{ investigation_id: "inv-1", question: "Why did the Beagle sail?" }];
    await mountLoaded("/inv/inv-1");
    const strip = document.querySelector("[data-document-strip]")!;
    await waitFor(() => expect(strip.textContent).toContain("Why did the Beagle sail?"));
    expect(strip.textContent).not.toContain("/inv/");
    cleanup();
    tabs().resetTabTrees();
    await mountLoaded("/inv/inv-unknown");
    await flush(6);
    const strip2 = document.querySelector("[data-document-strip]")!;
    expect(strip2.textContent).not.toContain("inv-unknown");
    expect(strip2.textContent).toContain("Research");
  });

  it("section tabs show their heading (or 'Untitled section'), never 'section:<uuid>'", async () => {
    api.deliverables.set("d1", {
      deliverable_id: "d1",
      title: "Field notes",
      deliverable_kind: "essay",
      status: "draft",
      investigation_root_id: null,
      sections: [
        { section_id: "5f0c-uuid-1", deliverable_id: "d1", parent_section_id: null, section_index: 0, title: "Method", prose_text: null, prose_provenance: null, block_count: 0 },
        { section_id: "5f0c-uuid-2", deliverable_id: "d1", parent_section_id: null, section_index: 1, title: null, prose_text: null, prose_provenance: null, block_count: 0 },
      ],
    });
    const bodyId = await mountLoaded("/write/d1");
    for (const [i, sid] of ["5f0c-uuid-1", "5f0c-uuid-2"].entries()) {
      act(() => {
        tabs().spawnTab("writing", bodyId, {
          tab_id: `sec-${i}`,
          kind: "document",
          ref: `section:${sid}`,
          mothership: "writing",
          activate: false,
        });
      });
    }
    openTreePanel();
    await waitFor(() =>
      expect(document.querySelector("[data-tab-tree-panel]")!.textContent).toContain("Method"),
    );
    const panel = document.querySelector("[data-tab-tree-panel]")!.textContent!;
    expect(panel).toContain("Field notes");
    expect(panel).toContain("Untitled section");
    expect(panel).not.toContain("section:");
    expect(panel).not.toContain("5f0c-uuid");
    expect(panel).not.toContain("/write/");
  });

  it("the strip shows the active tab's siblings and a ↳n chip for its children", async () => {
    const rootId = await mountLoaded("/read/doc-9");
    const m = M();
    spawn(m, rootId, "c1", "doc-9", "first note");
    spawn(m, rootId, "c2", "doc-9", "second note");
    spawn(m, rootId, "c3", "doc-9", "third note");
    spawn(m, "c2", "c2a", "doc-9", "deeper a");
    spawn(m, "c2", "c2b", "doc-9", "deeper b");
    act(() => tabs().activateTab(m, "c2"));
    await flush();
    const strip = document.querySelector("[data-document-strip] [role='tablist']")!;
    expect(strip).toBeTruthy();
    const tabEls = Array.from(strip.querySelectorAll("[role='tab']"));
    expect(tabEls.map((t) => t.getAttribute("data-tab-id"))).toEqual(["c1", "c2", "c3"]);
    expect(tabEls[1].getAttribute("aria-selected")).toBe("true");
    const chip = document.querySelector("[data-children-chip]")!;
    expect(chip.textContent).toContain("2");
    act(() => (chip as HTMLElement).click());
    expect(["c2a", "c2b"]).toContain(tabs().trees[m]!.active_tab_id);
  });
});

// ─── defect 6: the 10 s local hold + the LemonToast undo ─────────────────

describe("defect 6 — close is held locally for 10 s behind a LemonToast undo", () => {
  function spyAdapter() {
    const inner = createInMemoryTabTreeAdapter();
    const saves: TabTreeSnapshot[] = [];
    const adapter: TabTreeAdapter = {
      load: inner.load,
      allocate: inner.allocate,
      save: async (p, m, s) => {
        saves.push(JSON.parse(JSON.stringify(s)) as TabTreeSnapshot);
        return inner.save(p, m, s);
      },
    };
    return { adapter, saves, inner };
  }
  const closedIn = (s: TabTreeSnapshot, id: string) => Object.hasOwn(s.tree.history, id);

  async function seed() {
    const spy = spyAdapter();
    tabs().setTabTreeAdapter(spy.adapter);
    const rootId = await mountLoaded("/read/doc-9");
    const m = M();
    spawn(m, rootId, "c1", "doc-9", "a note");
    spawn(m, "c1", "c1-1", "doc-9", "a deeper note");
    act(() => tabs().activateTab(m, "c1"));
    await flush(6);
    return { ...spy, m, rootId };
  }

  it("the close is not written until the window lapses; the toast offers Undo", async () => {
    const { saves, inner, m } = await seed();
    vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout"] });
    key(document.body, "ctrl+b");
    key(document.body, "shift+x");
    await flush(6);
    // Locally the subtree is gone at once…
    expect(tabs().trees[m]!.nodes["c1"]).toBeUndefined();
    // …but nothing that other devices read has seen it.
    expect(saves.some((s) => closedIn(s, "c1"))).toBe(false);
    const undo = screen.getByRole("button", { name: /undo/i });
    expect(undo.closest("[role='status']")).toBeTruthy();
    await act(async () => {
      vi.advanceTimersByTime(9_999);
    });
    await flush(6);
    expect(saves.some((s) => closedIn(s, "c1"))).toBe(false);
    await act(async () => {
      vi.advanceTimersByTime(1);
    });
    await flush(6);
    expect(closedIn(await inner.load("default", m), "c1")).toBe(true);
    // The toast's 10,000 ms lifetime ended with the window.
    expect(screen.queryByRole("button", { name: /undo/i })).toBeNull();
  });

  it("Undo inside the window restores the subtree and no device ever saw the close", async () => {
    const { saves, m } = await seed();
    vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout"] });
    key(document.body, "ctrl+b");
    key(document.body, "shift+x");
    await flush(6);
    act(() => screen.getByRole("button", { name: /undo/i }).click());
    await flush(6);
    const tree = tabs().trees[m]!;
    expect(tree.nodes["c1"]).toBeTruthy();
    expect(tree.nodes["c1"].child_order).toContain("c1-1");
    await act(async () => {
      vi.advanceTimersByTime(20_000);
    });
    await flush(6);
    expect(saves.some((s) => closedIn(s, "c1"))).toBe(false);
    // No persistent strip button carries the undo any more.
    expect(document.querySelector("[data-undo-close]")).toBeNull();
  });
});

// ─── defect 7: /read/meta-reading is not a document ──────────────────────

describe("defect 7 — the meta-reading routes never become reader tabs", () => {
  it("rootRefForPath refuses /read/meta-reading and /read/meta-reading/:assetId", () => {
    expect(rootRefForPath("/read/meta-reading")).toBeNull();
    expect(rootRefForPath("/read/meta-reading/asset-7")).toBeNull();
    expect(rootRefForPath("/read/doc-9")?.kind).toBe("reader");
  });

  it("mounting on /read/meta-reading seeds no tab", async () => {
    mountStrip("/read/meta-reading");
    await waitFor(() => expect(tabs().loaded.reading).toBe(true));
    await flush(6);
    expect(Object.keys(tabs().trees.reading!.nodes)).toHaveLength(0);
  });
});

// ─── defect 8: ARIA tabs + tree, roving focus ────────────────────────────

describe("defect 8 — the ARIA tabs and tree patterns, with roving focus", () => {
  it("the document strip is a tablist of real tab buttons wired to one tabpanel", async () => {
    const rootId = await mountLoaded("/read/doc-9");
    const m = M();
    spawn(m, null, "r2", "doc-9");
    spawn(m, null, "r3", "doc-9");
    act(() => tabs().activateTab(m, rootId));
    await flush();
    const list = document.querySelector("[data-document-strip] [role='tablist']")!;
    expect(list.getAttribute("aria-label")).toBeTruthy();
    const tabEls = Array.from(list.querySelectorAll<HTMLElement>("[role='tab']"));
    expect(tabEls).toHaveLength(3);
    for (const t of tabEls) {
      expect(t.tagName).toBe("BUTTON");
      expect(t.querySelector("button, a, input")).toBeNull();
    }
    const selected = tabEls.find((t) => t.getAttribute("aria-selected") === "true")!;
    const panelId = selected.getAttribute("aria-controls")!;
    const panel = document.getElementById(panelId)!;
    expect(panel.getAttribute("role")).toBe("tabpanel");
    expect(panel.getAttribute("aria-labelledby")).toBe(selected.id);
    // Roving tabindex: one stop, arrows move it, Home/End jump.
    expect(tabEls.filter((t) => t.tabIndex === 0)).toEqual([selected]);
    act(() => selected.focus());
    fireEvent.keyDown(selected, { key: "ArrowRight" });
    expect(document.activeElement).toBe(tabEls[1]);
    fireEvent.keyDown(tabEls[1], { key: "End" });
    expect(document.activeElement).toBe(tabEls[2]);
    fireEvent.keyDown(tabEls[2], { key: "ArrowRight" });
    expect(document.activeElement).toBe(tabEls[0]);
    fireEvent.keyDown(tabEls[0], { key: "ArrowLeft" });
    expect(document.activeElement).toBe(tabEls[2]);
  });

  it("the tree panel is an ARIA tree with levels, positions and arrow keys", async () => {
    const rootId = await mountLoaded("/read/doc-9");
    const m = M();
    spawn(m, rootId, "a", "doc-9", "a");
    spawn(m, "a", "a1", "doc-9", "a1");
    spawn(m, rootId, "b", "doc-9", "b");
    openTreePanel();
    const tree = document.querySelector("[data-tab-tree-panel] [role='tree']")!;
    expect(tree).toBeTruthy();
    const items = Array.from(tree.querySelectorAll<HTMLElement>("[role='treeitem']"));
    expect(items.map((i) => i.getAttribute("aria-level"))).toEqual(["1", "2", "3", "2"]);
    expect(items[1].getAttribute("aria-posinset")).toBe("1");
    expect(items[1].getAttribute("aria-setsize")).toBe("2");
    expect(items.filter((i) => i.tabIndex === 0)).toHaveLength(1);
    const first = items.find((i) => i.tabIndex === 0)!;
    act(() => first.focus());
    fireEvent.keyDown(first, { key: "ArrowDown" });
    const second = document.activeElement as HTMLElement;
    expect(second.getAttribute("role")).toBe("treeitem");
    expect(second).not.toBe(first);
    fireEvent.keyDown(document.activeElement!, { key: "End" });
    expect((document.activeElement as HTMLElement).getAttribute("data-tree-row")).toBe("b");
    fireEvent.keyDown(document.activeElement!, { key: "ArrowLeft" });
    expect((document.activeElement as HTMLElement).getAttribute("data-tree-row")).toBe(rootId);
    fireEvent.keyDown(document.activeElement!, { key: "Home" });
    fireEvent.keyDown(document.activeElement!, { key: "ArrowDown" });
    fireEvent.keyDown(document.activeElement!, { key: "Enter" });
    expect(tabs().trees[m]!.active_tab_id).toBe("a");
  });

  it("companion agent tabs: the tab is the button itself, never a div around two buttons", () => {
    act(() => {
      useCompanion.getState().openAgentTab({ kind: "dialogue", title: "Ask" });
    });
    render(
      <BrowserRouter>
        <CompanionPane />
      </BrowserRouter>,
    );
    const tabEls = Array.from(document.querySelectorAll<HTMLElement>("[data-companion-pane] [role='tab']"));
    expect(tabEls.length).toBeGreaterThan(0);
    for (const t of tabEls) {
      expect(t.tagName).toBe("BUTTON");
      expect(t.querySelector("button, a, input")).toBeNull();
    }
    const list = document.querySelector("[data-companion-pane] [role='tablist']")!;
    // Only tabs are owned by the tablist.
    for (const child of Array.from(list.querySelectorAll("button, summary, a"))) {
      const owned = child.getAttribute("role") === "tab" || child.getAttribute("aria-hidden") === "true";
      expect(owned).toBe(true);
    }
  });
});

// ─── defect 9: shared state primitives + the load error path ─────────────

describe("defect 9 — Loading/Empty/Error primitives and ensureMothership's error path", () => {
  it("a slow load shows the shared LoadingState; a failed load an ErrorState with retry", async () => {
    const inner = createInMemoryTabTreeAdapter();
    let fail = true;
    let release: (() => void) | null = null;
    const adapter: TabTreeAdapter = {
      ...inner,
      load: (p, m) =>
        new Promise((resolve, reject) => {
          release = () => (fail ? reject(new Error("HTTP 503")) : resolve(inner.load(p, m)));
        }),
    };
    tabs().setTabTreeAdapter(adapter);
    mountStrip("/read/doc-9");
    await waitFor(() => expect(release).not.toBeNull());
    const strip = () => document.querySelector("[data-document-strip]")!;
    await waitFor(() => expect(strip().querySelector("[role='status']")).toBeTruthy());
    expect(strip().textContent).toMatch(/Opening your tabs/);
    await act(async () => release!());
    await flush(6);
    const alert = strip().querySelector("[role='alert']")!;
    expect(alert).toBeTruthy();
    expect(alert.textContent).not.toContain("HTTP 503");
    fail = false;
    release = null;
    act(() => screen.getByRole("button", { name: "Try again" }).click());
    await waitFor(() => expect(release).not.toBeNull());
    await act(async () => release!());
    await waitFor(() => expect(tabs().trees.reading?.active_tab_id).toBe("root:reader:doc-9"));
    expect(strip().querySelector("[role='alert']")).toBeNull();
  });

  it("an empty tree panel uses the shared EmptyState", async () => {
    mountStrip("/home");
    await waitFor(() => expect(tabs().loaded.research).toBe(true));
    await flush();
    openTreePanel();
    const panel = document.querySelector("[data-tab-tree-panel]")!;
    expect(panel.querySelector(".st")).toBeTruthy();
    expect(panel.textContent).toContain("No open tabs");
  });
});

describe("defect 9 — the Write outline pane's states use the primitives", () => {
  function mountOutline(path: string) {
    window.history.replaceState({}, "", path);
    return render(
      <BrowserRouter>
        <WriteOutlinePane />
      </BrowserRouter>,
    );
  }

  it("a piece with no blocks settles on EmptyState; loading never outlives the load", async () => {
    api.deliverables.set("d-empty", {
      deliverable_id: "d-empty",
      title: "Empty",
      deliverable_kind: "essay",
      status: "draft",
      investigation_root_id: null,
      sections: [],
    });
    mountOutline("/write/d-empty");
    const pane = () => document.querySelector("[data-write-outline]")!;
    await waitFor(() => expect(pane().querySelector(".st")).toBeTruthy());
    await flush(4);
    expect(pane().textContent).toContain("No blocks yet");
    expect(pane().textContent).not.toMatch(/loading/i);
    // Nothing but tabs inside the tablist (a status line there is not a tab).
    const list = pane().querySelector("[role='tablist']");
    if (list) expect(list.querySelector(":scope > :not([role='tab'])")).toBeNull();
  });

  it("a failed load is an ErrorState with a retry that recovers", async () => {
    mountOutline("/write/d-late");
    const pane = () => document.querySelector("[data-write-outline]")!;
    await waitFor(() => expect(pane().querySelector("[role='alert']")).toBeTruthy());
    api.deliverables.set("d-late", {
      deliverable_id: "d-late",
      title: "Late",
      deliverable_kind: "essay",
      status: "draft",
      investigation_root_id: null,
      sections: [],
    });
    act(() => screen.getByRole("button", { name: "Try again" }).click());
    await waitFor(() => expect(pane().querySelector("[role='alert']")).toBeNull());
    await waitFor(() => expect(pane().textContent).toContain("No blocks yet"));
  });
});

// ─── §2a path header ─────────────────────────────────────────────────────

describe("§2a path header — compresses past four crumbs; Esc closes the expanded path", () => {
  const crumbs = () => Array.from(document.querySelectorAll("[data-tab-path] [data-crumb]"));

  it("four crumbs show in full", async () => {
    const rootId = await mountLoaded("/read/doc-9");
    chain(M(), rootId, 4);
    await flush();
    expect(crumbs()).toHaveLength(4);
    expect(document.querySelector("[data-crumb-ellipsis]")).toBeNull();
  });

  it("twelve crumbs compress in the middle; the ellipsis opens the full path; Esc closes it", async () => {
    const rootId = await mountLoaded("/read/doc-9");
    const ids = chain(M(), rootId, 12);
    await flush();
    expect(crumbs().map((c) => c.getAttribute("data-crumb"))).toEqual([rootId, ids[10], ids[11]]);
    const ellipsis = document.querySelector<HTMLElement>("[data-crumb-ellipsis]")!;
    expect(ellipsis.getAttribute("aria-expanded")).toBe("false");
    act(() => ellipsis.click());
    const full = document.querySelector("[data-tab-path-full]")!;
    expect(full.querySelectorAll("[data-crumb]")).toHaveLength(12);
    fireEvent.keyDown(full, { key: "Escape" });
    expect(document.querySelector("[data-tab-path-full]")).toBeNull();
    expect(document.activeElement).toBe(document.querySelector("[data-crumb-ellipsis]"));
    // Every crumb is a link: clicking one activates that tab.
    act(() => (crumbs()[0] as HTMLElement).click());
    expect(tabs().trees[M()]!.active_tab_id).toBe(rootId);
  });
});

// ─── §2a tree panel: 6-level indent cap + depth badge; virtualised ───────

describe("§2a tree panel — indent capped at six levels, depth badge, virtualised", () => {
  it("rows deeper than six keep the level-6 indent and carry a dN badge", async () => {
    const rootId = await mountLoaded("/read/doc-9");
    const ids = chain(M(), rootId, 9);
    openTreePanel();
    const row = (id: string) => document.querySelector<HTMLElement>(`[data-tree-row="${id}"]`)!;
    const indent = (id: string) => row(id).style.paddingLeft;
    expect(indent(ids[6])).toBe(indent(ids[5]));
    expect(indent(ids[8])).toBe(indent(ids[5]));
    expect(indent(ids[4])).not.toBe(indent(ids[5]));
    expect(row(ids[5]).querySelector("[data-depth-badge]")).toBeNull();
    expect(row(ids[6]).querySelector("[data-depth-badge]")!.textContent).toBe("d7");
    expect(row(ids[8]).querySelector("[data-depth-badge]")!.textContent).toBe("d9");
    expect(row(ids[8]).getAttribute("aria-level")).toBe("9");
  });

  it("a 1,000-tab forest renders a window of rows, every tab still reachable by keys", async () => {
    const rootId = await mountLoaded("/read/doc-9");
    const m = M();
    act(() => {
      for (let i = 0; i < 999; i++) {
        tabs().spawnTab(m, rootId, { tab_id: `n${i}`, kind: "reader", ref: "doc-9", mothership: m, activate: false });
      }
    });
    openTreePanel();
    const rendered = document.querySelectorAll("[data-tab-tree-panel] [role='treeitem']");
    expect(rendered.length).toBeGreaterThan(0);
    expect(rendered.length).toBeLessThan(120);
    expect(rendered[1].getAttribute("aria-setsize")).toBe("999");
    const first = document.querySelector<HTMLElement>("[data-tab-tree-panel] [role='treeitem'][tabindex='0']")!;
    act(() => first.focus());
    fireEvent.keyDown(first, { key: "End" });
    const last = document.activeElement as HTMLElement;
    expect(last.getAttribute("data-tree-row")).toBe("n998");
    expect(last.getAttribute("aria-posinset")).toBe("999");
  });
});
