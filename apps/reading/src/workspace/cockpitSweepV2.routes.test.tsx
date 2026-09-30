/**
 * cockpitSweepV2.routes.test.tsx — lane A stage B1: the route and tab-tree
 * blockers from Antiek Sweep v2's forensic audit
 * (cockpit/FORENSIC-SWEEP-V2-KIMI-COCKPIT-2026-09-26.md), each case kept
 * from the executed probe named beside it (cockpit/probes/) with the
 * probe's setup, asserting the CORRECT behaviour instead of recording the
 * defect. The probes settled with a fixed number of ticks; the strip and the
 * tree store now load lazily, so each mount waits for its tree instead.
 *
 *   F-03    a child tab for another document stays a child
 *           (d6-rerooting-and-spawn V1, with its same-document control).
 *   F-04    the tree → route direction never hijacks a navigation the
 *           user or an opener started (d6-activation-hijack V6a-d,
 *           d6-audit PROBE-5, d6-mode-flip-reload V11).
 *   D6-F06  an agent open keeps the current mode (d6-audit PROBE-4,
 *           d6-mode-flip-reload V12).
 *   D6-F11  two-device lost update (d6-audit PROBE-8/9,
 *           d6-rerooting-and-spawn V3/V4).
 *   F-19    no destructive chord fires while typing (d6-chord-and-strip V8).
 */
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import { act, cleanup, render, waitFor } from "@testing-library/react";
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
  apiFetch: vi.fn(() => Promise.resolve({ ok: false, status: 404, json: async () => ({}), text: async () => "" })),
  postTypedEvent: vi.fn(() => Promise.resolve({ event_id: "e" })),
}));

import { KEYMAP } from "../components/hotkeys/keymap";
import { prefixState } from "../components/hotkeys/prefixState";
import { PanelLayout } from "./PanelLayout";
import { openDocumentInLeftPane } from "./crossPane";
import { mothershipForPath } from "./documentSpace";
import { useWorkspace } from "./WorkspaceStore";
import { useTabTrees } from "./tabTreeStore";
import { installShortcuts } from "./shortcuts";
import { pinPlatform, press, unpinPlatform } from "./keymapTestKit";
import {
  createInMemoryTabTreeAdapter,
  emptyTabTree,
  spawnChild,
  toSnapshot,
  type Mothership,
  type TabTreeAdapter,
} from "./tabTree";

const { tierRef } = vi.hoisted(() => ({ tierRef: { current: "xl" as string } }));
vi.mock("./useViewportTier", () => ({ useViewportTier: () => tierRef.current }));

const tabs = () => useTabTrees.getState();
let uninstall: (() => void) | null = null;
const navRef: { current: NavigateFunction | null } = { current: null };

function Probe() {
  const loc = useLocation();
  navRef.current = useNavigate();
  return <span data-testid="location">{loc.pathname + loc.search}</span>;
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

async function settle(n = 10) {
  for (let i = 0; i < n; i++) {
    await act(async () => {
      await new Promise((r) => setTimeout(r, 0));
    });
  }
}

/** Mount at `path` and wait for its tree to load and seed the route's tab
 *  (the strip and the store arrive with a lazy chunk). */
async function mountLoaded(path: string): Promise<string> {
  const m = mothershipForPath(path);
  mount(path);
  await waitFor(() => expect(tabs().trees[m]?.active_tab_id ?? null).not.toBeNull());
  await settle(3);
  return tabs().trees[m]!.active_tab_id!;
}

/** Navigate the way a link or an opener does, and let every effect run. */
async function go(p: string): Promise<string> {
  await act(async () => {
    navRef.current!(p);
  });
  await settle(10);
  return window.location.pathname;
}

const here = () => window.location.pathname + window.location.search;
const modeHere = (): Mothership => mothershipForPath(window.location.pathname, window.location.search);

function key(target: EventTarget, spec: string): KeyboardEvent {
  let e = new KeyboardEvent("keydown");
  act(() => {
    e = press(target, spec, "mac");
  });
  return e;
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
  vi.useRealTimers();
  uninstall?.();
  uninstall = null;
  cleanup();
  prefixState.disarm();
  tabs().resetTabTrees();
  unpinPlatform();
  document.body.innerHTML = "";
  window.history.replaceState({}, "", "/");
});

// ─── F-03 ───────────────────────────────────────────────────────────────

describe("F-03 — a child tab for another document stays a child (probe V1)", () => {
  it("clicking a child row pointing at another document activates it, and it stays the child", async () => {
    const root = await mountLoaded("/read/doc-9");
    const m = "reading" as const;
    act(() => {
      tabs().spawnTab(m, root, {
        tab_id: "c1",
        origin: { document_id: "doc-9", kind: "footnote" },
        kind: "reader",
        ref: "doc-a",
        mothership: m,
        activate: false,
      });
      tabs().toggleTreePanel();
    });
    // The row is the treeitem (its inner buttons are focus-subtree and close).
    const btn = document.querySelector('[data-tree-row="c1"]') as HTMLElement;
    act(() => btn.click());
    await settle(10);
    const t = tabs().trees[m]!;
    expect(window.location.pathname).toBe("/read/doc-a");
    expect(t.active_tab_id).toBe("c1");
    expect(t.nodes.c1.parent_tab_id).toBe(root);
    expect(t.root_order).toEqual([root]);
  });

  it("control: a child pointing at the SAME document stays", async () => {
    const root = await mountLoaded("/read/doc-9");
    const m = "reading" as const;
    act(() => {
      tabs().spawnTab(m, root, { tab_id: "c1", kind: "reader", ref: "doc-9", mothership: m, activate: false });
      tabs().toggleTreePanel();
    });
    // The row is the treeitem (its inner buttons are focus-subtree and close).
    const btn = document.querySelector('[data-tree-row="c1"]') as HTMLElement;
    act(() => btn.click());
    await settle(10);
    expect(tabs().trees[m]!.active_tab_id).toBe("c1");
    expect(tabs().trees[m]!.root_order).toEqual([root]);
  });

  it("prefix n onto a sibling for another document moves there and stays (probe V2 / PROBE-3)", async () => {
    const root = await mountLoaded("/read/doc-9");
    const m = "reading" as const;
    act(() => {
      tabs().spawnTab(m, root, { tab_id: "c1", kind: "reader", ref: "doc-a", mothership: m, activate: false });
      tabs().spawnTab(m, root, { tab_id: "c2", kind: "reader", ref: "doc-b", mothership: m, activate: false });
    });
    act(() => tabs().activateTab(m, "c1"));
    await settle();
    expect(tabs().trees[m]!.active_tab_id).toBe("c1");
    key(document.body, "ctrl+b");
    key(document.body, "n");
    await settle();
    expect(tabs().trees[m]!.active_tab_id).toBe("c2");
    expect(window.location.pathname).toBe("/read/doc-b");
    key(document.body, "ctrl+b");
    key(document.body, "u");
    await settle();
    expect(tabs().trees[m]!.active_tab_id).toBe(root);
    expect(window.location.pathname).toBe("/read/doc-9");
    expect(tabs().trees[m]!.root_order).toEqual([root]);
  });
});

// ─── F-04 ───────────────────────────────────────────────────────────────

describe("F-04 — the tree → route direction never hijacks a navigation (probe V6)", () => {
  it("/inv/a -> /read/doc -> /inv/b lands on /inv/b", async () => {
    await mountLoaded("/inv/a");
    expect(await go("/read/doc")).toBe("/read/doc");
    expect(await go("/inv/b")).toBe("/inv/b");
  });

  it("/inv/a -> /read/doc -> / (research home) lands on /", async () => {
    await mountLoaded("/inv/a");
    expect(await go("/read/doc")).toBe("/read/doc");
    expect(await go("/")).toBe("/");
  });

  it("/read/doc -> /write/w1 -> /read/doc2 lands on /read/doc2", async () => {
    await mountLoaded("/read/doc");
    expect(await go("/write/w1")).toBe("/write/w1");
    expect(await go("/read/doc2")).toBe("/read/doc2");
  });

  it("control: /read/doc -> /library (same mode) -> /read/doc2", async () => {
    await mountLoaded("/read/doc");
    expect(await go("/library")).toBe("/library");
    expect(await go("/read/doc2")).toBe("/read/doc2");
  });

  it("/read/doc-old -> /inv/x -> /read/doc-new pushes one entry, no ping-pong (PROBE-5)", async () => {
    await mountLoaded("/read/doc-old");
    await go("/inv/x");
    const pushes: string[] = [];
    const orig = window.history.pushState.bind(window.history);
    const spy = vi.spyOn(window.history, "pushState").mockImplementation((s, u, url) => {
      pushes.push(String(url));
      if (pushes.length > 60) throw new Error("navigation storm: >60 pushState");
      return orig(s, u, url as string);
    });
    try {
      await go("/read/doc-new");
      await settle(30);
    } finally {
      spy.mockRestore();
    }
    expect(pushes).toEqual(["/read/doc-new"]);
    expect(window.location.pathname).toBe("/read/doc-new");
  });

  it("every research route stays reachable after an agent open (V11)", async () => {
    await mountLoaded("/inv/inv-1");
    act(() => openDocumentInLeftPane("doc-9", { from: "companion", investigationId: "inv-1" }));
    await settle(10);
    const attempts: string[] = [];
    for (const p of ["/inv/inv-1", "/", "/home", "/my-research", "/inv/inv-2"]) {
      attempts.push(await go(p));
    }
    expect(attempts).toEqual(["/inv/inv-1", "/", "/home", "/my-research", "/inv/inv-2"]);
  });

  it("an agent open made before the strip loads never overrides a navigation made after it (V11 unwaited)", async () => {
    // The probe's own timing: open at once, before the lazy strip is up.
    mount("/inv/inv-1");
    act(() => openDocumentInLeftPane("doc-9", { from: "companion", investigationId: "inv-1" }));
    await act(async () => {
      navRef.current!("/inv/inv-2");
    });
    await waitFor(() => expect(document.querySelector('[data-document-strip] [role="tablist"]')).toBeTruthy());
    await settle(10);
    expect(here()).toBe("/inv/inv-2");
  });

  it("an activation still navigates: a strip tab click goes to its tab's route", async () => {
    const root = await mountLoaded("/read/doc-9");
    act(() => {
      tabs().spawnTab("reading", root, { tab_id: "c1", kind: "reader", ref: "doc-a", mothership: "reading", activate: false });
    });
    await settle(3);
    // Visit the child (prefix o): the activation navigates to its route.
    key(document.body, "ctrl+b");
    key(document.body, "o");
    await settle();
    expect(window.location.pathname).toBe("/read/doc-a");
  });
});

// ─── D6-F06 ─────────────────────────────────────────────────────────────

describe("D6-F06 — an agent open keeps the current mode (PROBE-4, V12)", () => {
  it("an open from Research lands as the visible active child of the research tree", async () => {
    const root = await mountLoaded("/inv/inv-1");
    act(() => openDocumentInLeftPane("doc-9", { from: "companion", investigationId: "inv-1" }));
    await settle(10);
    const research = tabs().trees.research!;
    const active = research.nodes[research.active_tab_id!];
    // The document is on screen in the LEFT pane, and the mode is still
    // Research: the route carries ?m=research, so Reading never takes over.
    expect(modeHere()).toBe("research");
    expect(here()).toBe("/read/doc-9?m=research");
    expect(active.kind).toBe("reader");
    expect(active.ref).toBe("doc-9");
    expect(active.parent_tab_id).toBe(root);
    expect(tabs().trees.reading).toBeNull();
    const strip = document.querySelector("[data-document-strip]")!;
    expect(strip.querySelector('[aria-selected="true"]')?.getAttribute("data-tab-id")).toBe(active.tab_id);
  });

  it("an open made before the route's tab is seeded still lands as a child of that tab", async () => {
    mount("/inv/inv-1");
    act(() => openDocumentInLeftPane("doc-9", { from: "companion", investigationId: "inv-1" }));
    await waitFor(() => expect(here()).toBe("/read/doc-9?m=research"));
    await settle(5);
    const research = tabs().trees.research!;
    const active = research.nodes[research.active_tab_id!];
    expect(active.ref).toBe("doc-9");
    expect(active.parent_tab_id).toBe("root:research:/inv/inv-1");
    expect(research.root_order).toEqual(["root:research:/inv/inv-1"]);
  });

  it("a reload at /inv/inv-1 with a persisted active reader child stays at /inv/inv-1", async () => {
    const adapter = createInMemoryTabTreeAdapter();
    const t = emptyTabTree("research");
    const a = spawnChild(t, null, {
      tab_id: "root:research:/inv/inv-1",
      kind: "research",
      ref: "/inv/inv-1",
      mothership: "research",
      activate: true,
    });
    if (!a.ok) throw new Error("a");
    const b = spawnChild(a.tree, "root:research:/inv/inv-1", {
      tab_id: "kid",
      kind: "reader",
      ref: "doc-9",
      mothership: "research",
      activate: true,
      origin: { document_id: "doc-9", kind: "reference" },
    });
    if (!b.ok) throw new Error("b");
    await adapter.save("default", "research", toSnapshot(b.tree));
    act(() => tabs().setTabTreeAdapter(adapter));
    mount("/inv/inv-1");
    await waitFor(() => expect(tabs().trees.research).not.toBeNull());
    await settle(10);
    expect(here()).toBe("/inv/inv-1");
    expect(tabs().trees.research!.active_tab_id).toBe("root:research:/inv/inv-1");
    expect(tabs().trees.research!.nodes.kid).toBeTruthy();
  });
});

// ─── D6-F11 ─────────────────────────────────────────────────────────────

describe("D6-F11 — two devices never lose an update (PROBE-8/9, V3/V4)", () => {
  it("a spawn made during an in-flight save that then 409s survives, locally and persisted", async () => {
    const base = createInMemoryTabTreeAdapter();
    let release: (() => void) | null = null;
    let first = true;
    const adapter: TabTreeAdapter = {
      load: (p, m) => base.load(p, m),
      allocate: (p, m) => base.allocate(p, m),
      async save(p, m, snap) {
        if (first) {
          first = false;
          const cur = await base.load(p, m);
          await base.save(p, m, cur); // another device writes first
          await new Promise<void>((r) => {
            release = r;
          });
        }
        return base.save(p, m, snap);
      },
    };
    act(() => tabs().setTabTreeAdapter(adapter));
    await act(async () => {
      await tabs().ensureMothership("reading");
    });
    act(() => {
      tabs().spawnTab("reading", null, { tab_id: "A", kind: "reader", ref: "doc-a", mothership: "reading" });
    });
    await settle(2);
    act(() => {
      tabs().spawnTab("reading", "A", { tab_id: "B", kind: "reader", ref: "doc-b", mothership: "reading" });
    });
    await act(async () => {
      release!();
    });
    await settle(10);
    const persisted = await base.load("default", "reading");
    expect(Object.keys(tabs().trees.reading!.nodes).sort()).toEqual(["A", "B"]);
    expect(Object.keys(persisted.tree.nodes).sort()).toEqual(["A", "B"]);
    expect(tabs().pendingOps.reading).toEqual([]);
  });

  it("a save that succeeds slowly, then a later save that 409s, keeps the op made in flight (V3)", async () => {
    const base = createInMemoryTabTreeAdapter();
    let release: (() => void) | null = null;
    let call = 0;
    const adapter: TabTreeAdapter = {
      load: (p, m) => base.load(p, m),
      allocate: (p, m) => base.allocate(p, m),
      async save(p, m, s) {
        call++;
        if (call === 1) {
          await new Promise<void>((r) => {
            release = r;
          });
          return base.save(p, m, s);
        }
        if (call === 2) {
          const cur = await base.load(p, m);
          await base.save(p, m, cur);
        }
        return base.save(p, m, s);
      },
    };
    act(() => tabs().setTabTreeAdapter(adapter));
    await act(async () => {
      await tabs().ensureMothership("reading");
    });
    act(() => {
      tabs().spawnTab("reading", null, { tab_id: "A", kind: "reader", ref: "doc-a", mothership: "reading" });
    });
    await settle(2);
    act(() => {
      tabs().spawnTab("reading", "A", { tab_id: "B", kind: "reader", ref: "doc-b", mothership: "reading" });
    });
    await act(async () => {
      release!();
    });
    await settle(10);
    const persisted = await base.load("default", "reading");
    expect(Object.keys(tabs().trees.reading!.nodes)).toContain("B");
    expect(Object.keys(persisted.tree.nodes)).toContain("B");
  });

  it("a close reaches the adapter only after its 10 s undo window lapses", async () => {
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
    await act(async () => {
      await tabs().ensureMothership("reading");
    });
    act(() => {
      tabs().spawnTab("reading", null, { tab_id: "A", kind: "reader", ref: "doc-a", mothership: "reading" });
    });
    await act(async () => {
      await Promise.resolve();
      await Promise.resolve();
    });
    act(() => tabs().closeActiveTab("reading", "prune"));
    await act(async () => {
      await Promise.resolve();
      await Promise.resolve();
      await Promise.resolve();
    });
    expect(writes.some((w) => w.nodes.length === 0)).toBe(false);
    await act(async () => {
      vi.advanceTimersByTime(11_000);
    });
    await act(async () => {
      await Promise.resolve();
      await Promise.resolve();
    });
    const closeWrite = writes.find((w) => w.nodes.length === 0);
    expect(closeWrite).toBeTruthy();
    expect(closeWrite!.at).toBeGreaterThanOrEqual(10_000);
  });

  it("a spawn made after the first load completes survives the second load (V4)", async () => {
    const base = createInMemoryTabTreeAdapter();
    let n = 0;
    const adapter: TabTreeAdapter = {
      async load(p, m) {
        const delay = n++ === 0 ? 5 : 40;
        const s = await base.load(p, m);
        await new Promise((r) => setTimeout(r, delay));
        return s;
      },
      allocate: (p, m) => base.allocate(p, m),
      save: (p, m, s) => base.save(p, m, s),
    };
    act(() => tabs().setTabTreeAdapter(adapter));
    const p1 = tabs().ensureMothership("reading");
    const p2 = tabs().ensureMothership("reading");
    await p1;
    act(() => {
      tabs().spawnTab("reading", null, { tab_id: "A", kind: "reader", ref: "doc-a", mothership: "reading" });
    });
    await p2;
    expect(Object.keys(tabs().trees.reading!.nodes)).toContain("A");
  });
});

// ─── F-19 ───────────────────────────────────────────────────────────────

describe("F-19 — no destructive chord fires while typing (probe V8)", () => {
  it("close and the preset have no direct chord in the table (DESIGN-MODEL §2)", () => {
    const direct = KEYMAP.filter((r) => (r.action === "tab.close" || r.action === "layout.togglePreset") && r.chord);
    expect(direct).toEqual([]);
  });

  it("typed in a text field, ctrl+alt+c and prefix shift+x leave the active tab open", async () => {
    const root = await mountLoaded("/read/doc-9");
    const m = "reading" as const;
    act(() => {
      tabs().spawnTab(m, root, { tab_id: "c1", kind: "reader", ref: "doc-9", mothership: m, activate: true });
    });
    await settle(3);
    const input = document.createElement("textarea");
    document.body.appendChild(input);
    input.focus();
    key(input, "ctrl+alt+c");
    key(input, "ctrl+alt+x");
    key(input, "ctrl+b");
    key(input, "shift+x");
    await settle(3);
    const t = tabs().trees[m]!;
    expect(t.nodes.c1).toBeTruthy();
    expect(t.active_tab_id).toBe("c1");
    expect(tabs().heldClose).toBeNull();
  });
});
