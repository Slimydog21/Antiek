/**
 * AUDIT PROBES (scratch only, never committed). Each probe states the
 * behaviour the D6 slice claims and records what actually happens.
 */
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import { act, cleanup, render } from "@testing-library/react";
import { BrowserRouter, useLocation, useNavigate, type NavigateFunction } from "react-router-dom";

beforeAll(() => {
  Object.defineProperty(window, "matchMedia", {
    writable: true,
    configurable: true,
    value: (query: string) => ({
      matches: false, media: query, onchange: null,
      addEventListener: () => {}, removeEventListener: () => {},
      addListener: () => {}, removeListener: () => {}, dispatchEvent: () => false,
    }),
  });
});

vi.mock("../lib/api", async (orig) => ({
  ...(await orig<typeof import("../lib/api")>()),
  apiFetch: vi.fn(() => Promise.resolve({ ok: false, status: 404, json: async () => ({}) })),
  postTypedEvent: vi.fn(() => Promise.resolve({ event_id: "e" })),
}));

import { prefixState } from "../components/hotkeys/prefixState";
import { PanelLayout } from "./PanelLayout";
import { useWorkspace } from "./WorkspaceStore";
import { useTabTrees } from "./tabTreeStore";
import { installShortcuts } from "./shortcuts";
import { pinPlatform, press, unpinPlatform } from "./keymapTestKit";
import { createInMemoryTabTreeAdapter, type TabTreeAdapter } from "./tabTree";

const { tierRef } = vi.hoisted(() => ({ tierRef: { current: "xl" as string } }));
vi.mock("./useViewportTier", () => ({ useViewportTier: () => tierRef.current }));

const tabs = () => useTabTrees.getState();
let uninstall: (() => void) | null = null;
const navRef: { current: NavigateFunction | null } = { current: null };
const seen: string[] = [];

function Probe() {
  const loc = useLocation();
  navRef.current = useNavigate();
  seen.push(loc.pathname);
  return <span data-testid="location">{loc.pathname}</span>;
}

function mount(path: string) {
  window.history.replaceState({}, "", path);
  return render(
    <BrowserRouter>
      <Probe />
      <PanelLayout mainSlot={<p>route content</p>} />
    </BrowserRouter>,
  );
}

async function settle(n = 20) {
  for (let i = 0; i < n; i++) {
    // eslint-disable-next-line no-await-in-loop
    await act(async () => {
      await new Promise((r) => setTimeout(r, 0));
    });
  }
}

beforeEach(() => {
  pinPlatform("mac");
  seen.length = 0;
  useWorkspace.getState().reset();
  useWorkspace.getState().setLayoutPreset("docked");
  tabs().resetTabTrees();
  uninstall = installShortcuts(vi.fn() as never);
});
afterEach(() => {
  uninstall?.();
  cleanup();
  prefixState.disarm();
  tabs().resetTabTrees();
  unpinPlatform();
  document.body.innerHTML = "";
  window.history.replaceState({}, "", "/");
});

describe("PROBE-1 tree panel row order", () => {
  it("lists rows depth-first (child under its parent)", async () => {
    mount("/read/doc-9");
    await settle(3);
    const m = "reading" as const;
    const r1 = tabs().trees[m]!.active_tab_id!;
    act(() => {
      tabs().spawnTab(m, null, { tab_id: "r2", kind: "reader", ref: "doc-9", mothership: m, activate: false });
      tabs().spawnTab(m, r1, { tab_id: "c11", kind: "reader", ref: "doc-9", mothership: m, activate: false });
      tabs().spawnTab(m, "r2", { tab_id: "c21", kind: "reader", ref: "doc-9", mothership: m, activate: false });
      tabs().toggleTreePanel();
    });
    const order = Array.from(document.querySelectorAll("[data-tree-row]")).map((e) => {
      const id = e.getAttribute("data-tree-row")!;
      return `${tabs().trees[m]!.nodes[id].hier_number}`;
    });
    console.log("PROBE-1 row order:", JSON.stringify(order));
    expect(order).toEqual(["1", "1.1", "2", "2.1"]);
  });
});

describe("PROBE-2 a reference child to ANOTHER document, activated, then the event loop runs", () => {
  it("stays the active child tab and spawns no duplicate root", async () => {
    mount("/read/doc-9");
    await settle(3);
    const m = "reading" as const;
    const root = tabs().trees[m]!.active_tab_id!;
    act(() => {
      tabs().spawnTab(m, root, {
        tab_id: "ref-a",
        origin: { document_id: "doc-9", kind: "reference" },
        kind: "reader", ref: "doc-a", mothership: m, activate: true,
      });
    });
    await settle(10);
    const t = tabs().trees[m]!;
    const summary = {
      location: window.location.pathname,
      active: t.active_tab_id,
      roots: t.root_order.map((id) => `${t.nodes[id].hier_number}:${id}`),
      trail: document.querySelector("[data-tab-trail]")?.textContent ?? null,
      strip: document.querySelector("[data-document-strip]")?.textContent ?? null,
    };
    console.log("PROBE-2", JSON.stringify(summary));
    expect(t.active_tab_id).toBe("ref-a");
    expect(t.root_order).toHaveLength(1);
  });
});

describe("PROBE-3 prefix n onto a sibling that points at another document, with the event loop between keys", () => {
  it("prefix n moves to c2 and it stays active", async () => {
    mount("/read/doc-9");
    await settle(3);
    const m = "reading" as const;
    const root = tabs().trees[m]!.active_tab_id!;
    act(() => {
      tabs().spawnTab(m, root, { tab_id: "c1", kind: "reader", ref: "doc-a", mothership: m, activate: false });
      tabs().spawnTab(m, root, { tab_id: "c2", kind: "reader", ref: "doc-b", mothership: m, activate: false });
    });
    act(() => tabs().activateTab(m, "c1"));
    await settle(10);
    const afterC1 = { active: tabs().trees[m]!.active_tab_id, roots: [...tabs().trees[m]!.root_order], loc: window.location.pathname };
    act(() => { press(document.body, "ctrl+b", "mac"); });
    act(() => { press(document.body, "n", "mac"); });
    await settle(10);
    const t = tabs().trees[m]!;
    console.log("PROBE-3", JSON.stringify({ afterC1, active: t.active_tab_id, roots: t.root_order, loc: window.location.pathname }));
    expect(afterC1.active).toBe("c1");
    expect(t.active_tab_id).toBe("c2");
  });
});

describe("PROBE-4 cross-pane open from research: where does the child tab end up visible?", () => {
  it("the research child tab stays the visible active tab of the research tree", async () => {
    const { openDocumentInLeftPane } = await import("./crossPane");
    mount("/inv/inv-1");
    await settle(3);
    act(() => openDocumentInLeftPane("doc-9", { from: "companion", investigationId: "inv-1" }));
    await settle(10);
    const research = tabs().trees.research!;
    const reading = tabs().trees.reading;
    const out = {
      location: window.location.pathname,
      researchActive: research.active_tab_id,
      researchNodes: Object.values(research.nodes).map((n) => `${n.hier_number}:${n.kind}:${n.ref}`),
      readingNodes: reading ? Object.values(reading.nodes).map((n) => `${n.hier_number}:${n.kind}:${n.ref}:parent=${n.parent_tab_id}`) : null,
      strip: document.querySelector("[data-document-strip]")?.textContent ?? null,
    };
    console.log("PROBE-4", JSON.stringify(out));
    expect(window.location.pathname.startsWith("/inv/")).toBe(true);
  });
});

describe("PROBE-5 mothership switch with a stale active tab in the target tree", () => {
  it("navigating /read/doc-old -> /inv/x -> /read/doc-new lands on /read/doc-new without ping-pong", async () => {
    mount("/read/doc-old");
    await settle(3);
    await act(async () => { navRef.current!("/inv/x"); });
    await settle(5);
    const pushes: string[] = [];
    const orig = window.history.pushState.bind(window.history);
    const spy = vi.spyOn(window.history, "pushState").mockImplementation((s, u, url) => {
      pushes.push(String(url));
      if (pushes.length > 60) throw new Error("navigation storm: >60 pushState");
      return orig(s, u, url as string);
    });
    let err: unknown = null;
    try {
      await act(async () => { navRef.current!("/read/doc-new"); });
      await settle(40);
    } catch (e) {
      err = e;
    }
    spy.mockRestore();
    console.log("PROBE-5", JSON.stringify({ final: window.location.pathname, pushCount: pushes.length, first12: pushes.slice(0, 12), err: err ? String(err) : null }));
    expect(pushes.length).toBeLessThanOrEqual(1);
    expect(window.location.pathname).toBe("/read/doc-new");
  });
});

describe("PROBE-6 depth 200: path strip and tree-panel indent", () => {
  it("the path header compresses past ~4 crumbs and the indent caps at 6 levels", async () => {
    mount("/read/doc-9");
    await settle(3);
    const m = "reading" as const;
    let parent = tabs().trees[m]!.active_tab_id!;
    act(() => {
      for (let i = 0; i < 200; i++) {
        const id = `d${i}`;
        tabs().spawnTab(m, parent, { tab_id: id, kind: "reader", ref: "doc-9", mothership: m, activate: false });
        parent = id;
      }
      tabs().activateTab(m, parent);
      tabs().toggleTreePanel();
    });
    const pathButtons = document.querySelectorAll("[data-document-strip] [data-tab-id]").length;
    const deepest = document.querySelector(`[data-tree-row="d199"]`) as HTMLElement | null;
    const trailItems = document.querySelectorAll("[data-tab-trail] li").length;
    const hier = tabs().trees[m]!.nodes["d199"].hier_number;
    console.log("PROBE-6", JSON.stringify({ pathButtons, trailItems, deepestPaddingLeft: deepest?.style.paddingLeft, hierLen: hier.length }));
    expect(pathButtons).toBeLessThanOrEqual(6);
  });
});

describe("PROBE-7 Trail over a reference child that is a DIFFERENT document", () => {
  it("does the fabricated thread claim one entity for two documents?", async () => {
    mount("/read/doc-9");
    await settle(3);
    const m = "reading" as const;
    const root = tabs().trees[m]!.active_tab_id!;
    act(() => {
      tabs().spawnTab(m, root, {
        tab_id: "ref-a", origin: { document_id: "doc-9", kind: "reference" },
        kind: "reader", ref: "doc-9", mothership: m, activate: true,
      });
    });
    // Same doc (to avoid PROBE-2's navigation); now look at labels and roles.
    const trail = document.querySelector("[data-tab-trail] nav");
    console.log("PROBE-7", JSON.stringify({
      trailText: trail?.textContent,
      trailAriaLabel: trail?.getAttribute("aria-label"),
      tablist: document.querySelectorAll('[data-document-strip] [role="tablist"], [data-document-strip] [role="tab"]').length,
      treeRoles: document.querySelectorAll('[role="tree"], [role="treeitem"]').length,
      stripText: document.querySelector("[data-document-strip]")?.textContent,
      toggleAriaKeyshortcuts: document.querySelector('[aria-label="Toggle the tab tree"]')?.getAttribute("aria-keyshortcuts"),
    }));
    expect("see stdout").toBe("PROBE-7 dump");
  });
});

describe("PROBE-8 store conflict race: an op applied while a save is in flight", () => {
  it("a spawn made during an in-flight save that then 409s survives", async () => {
    const base = createInMemoryTabTreeAdapter();
    let release: (() => void) | null = null;
    let first = true;
    const adapter: TabTreeAdapter = {
      load: (p, m) => base.load(p, m),
      allocate: (p, m) => base.allocate(p, m),
      async save(p, m, snap) {
        if (first) {
          first = false;
          // another device writes first, then our in-flight save resolves as a conflict
          const cur = await base.load(p, m);
          await base.save(p, m, cur);
          await new Promise<void>((r) => { release = r; });
        }
        return base.save(p, m, snap);
      },
    };
    act(() => tabs().setTabTreeAdapter(adapter));
    await act(async () => { await tabs().ensureMothership("reading"); });
    act(() => { tabs().spawnTab("reading", null, { tab_id: "A", kind: "reader", ref: "doc-a", mothership: "reading" }); });
    await settle(2);
    // save of A is in flight; operator spawns B meanwhile
    act(() => { tabs().spawnTab("reading", "A", { tab_id: "B", kind: "reader", ref: "doc-b", mothership: "reading" }); });
    await act(async () => { release!(); });
    await settle(10);
    const t = tabs().trees.reading!;
    const persisted = await base.load("default", "reading");
    console.log("PROBE-8", JSON.stringify({ local: Object.keys(t.nodes), persisted: Object.keys(persisted.tree.nodes), pending: tabs().pendingOps.reading.length }));
    expect(Object.keys(t.nodes)).toContain("B");
    expect(Object.keys(persisted.tree.nodes)).toContain("B");
  });
});

describe("PROBE-9 close is written before the 10 s undo window lapses", () => {
  it("records when the close reaches the adapter", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    const base = createInMemoryTabTreeAdapter();
    const writes: { at: number; nodes: string[] }[] = [];
    const t0 = Date.now();
    const adapter: TabTreeAdapter = {
      load: (p, m) => base.load(p, m),
      allocate: (p, m) => base.allocate(p, m),
      async save(p, m, snap) {
        writes.push({ at: Date.now() - t0, nodes: Object.keys(snap.tree.nodes) });
        return base.save(p, m, snap);
      },
    };
    act(() => tabs().setTabTreeAdapter(adapter));
    await act(async () => { await tabs().ensureMothership("reading"); });
    act(() => { tabs().spawnTab("reading", null, { tab_id: "A", kind: "reader", ref: "doc-a", mothership: "reading" }); });
    await act(async () => { await Promise.resolve(); await Promise.resolve(); });
    act(() => tabs().closeActiveTab("reading", "prune"));
    await act(async () => { await Promise.resolve(); await Promise.resolve(); await Promise.resolve(); });
    const beforeWindow = writes.map((w) => ({ at: w.at, nodes: w.nodes }));
    await act(async () => { vi.advanceTimersByTime(11_000); });
    console.log("PROBE-9", JSON.stringify({ writes: beforeWindow, lastUndoAfter11s: tabs().lastUndo !== null }));
    vi.useRealTimers();
    expect(beforeWindow.some((w) => w.nodes.length === 0 && w.at < 10_000)).toBe(false);
  });
});

describe("PROBE-10 a non-document route shows a stale tab as current", () => {
  it("at / after /inv/x, the strip marks no tab as the current page", async () => {
    mount("/inv/x");
    await settle(3);
    await act(async () => { navRef.current!("/"); });
    await settle(5);
    const cur = document.querySelector('[data-document-strip] [aria-current="page"]');
    console.log("PROBE-10", JSON.stringify({ loc: window.location.pathname, currentText: cur?.textContent ?? null, strip: document.querySelector("[data-document-strip]")?.textContent }));
    expect(cur).toBeNull();
  });
});
