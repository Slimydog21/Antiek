/**
 * VERIFIER PROBES (scratch only, never committed). Independent variants of
 * the d6-doc-tabs audit probes, driven through real UI gestures where possible.
 */
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import { act, cleanup, render } from "@testing-library/react";
import { BrowserRouter, useLocation } from "react-router-dom";

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

function Probe() {
  const loc = useLocation();
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
async function settle(n = 10) {
  for (let i = 0; i < n; i++) {
    // eslint-disable-next-line no-await-in-loop
    await act(async () => { await new Promise((r) => setTimeout(r, 0)); });
  }
}
function key(spec: string) {
  act(() => { press(document.body, spec, "mac"); });
}
function snap(m: "reading" | "research") {
  const t = tabs().trees[m]!;
  return { loc: window.location.pathname, active: t.active_tab_id, roots: [...t.root_order] };
}

beforeEach(() => {
  pinPlatform("mac");
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

describe("V1 (F03) clicking a child row in the tree panel", () => {
  it("child pointing at another document", async () => {
    mount("/read/doc-9");
    await settle(3);
    const m = "reading" as const;
    const root = tabs().trees[m]!.active_tab_id!;
    act(() => {
      tabs().spawnTab(m, root, { tab_id: "c1", origin: { document_id: "doc-9", kind: "footnote" }, kind: "reader", ref: "doc-a", mothership: m, activate: false });
      tabs().toggleTreePanel();
    });
    const btn = document.querySelector('[data-tree-row="c1"] button') as HTMLElement;
    act(() => btn.click());
    const sync = snap(m);
    await settle(10);
    console.log("V1", JSON.stringify({ sync, settled: snap(m) }));
    expect(tabs().trees[m]!.active_tab_id).toBe("c1");
  });
  it("control: child pointing at the SAME document stays", async () => {
    mount("/read/doc-9");
    await settle(3);
    const m = "reading" as const;
    const root = tabs().trees[m]!.active_tab_id!;
    act(() => {
      tabs().spawnTab(m, root, { tab_id: "c1", kind: "reader", ref: "doc-9", mothership: m, activate: false });
      tabs().toggleTreePanel();
    });
    const btn = document.querySelector('[data-tree-row="c1"] button') as HTMLElement;
    act(() => btn.click());
    await settle(10);
    console.log("V1-control", JSON.stringify(snap(m)));
    expect(tabs().trees[m]!.active_tab_id).toBe("c1");
  });
});

describe("V2 (F04) the committed n/p + u/o tests with the event loop allowed to run", () => {
  async function seed() {
    mount("/read/doc-9");
    await settle(3);
    const m = "reading" as const;
    const rootId = tabs().trees[m]!.active_tab_id!;
    act(() => {
      tabs().spawnTab(m, rootId, { tab_id: "c1", kind: "reader", ref: "doc-a", mothership: m, activate: false });
      tabs().spawnTab(m, rootId, { tab_id: "c2", kind: "reader", ref: "doc-b", mothership: m, activate: false });
    });
    await settle(3);
    return { m, rootId };
  }
  it("n/p", async () => {
    const { m } = await seed();
    const log: unknown[] = [];
    act(() => tabs().activateTab(m, "c1"));
    log.push({ step: "activate c1 (sync)", ...snap(m) });
    await settle();
    log.push({ step: "activate c1 (settled)", ...snap(m) });
    key("ctrl+b"); key("n");
    log.push({ step: "prefix n (sync)", ...snap(m) });
    await settle();
    log.push({ step: "prefix n (settled)", ...snap(m) });
    console.log("V2-np", JSON.stringify(log));
    expect(tabs().trees[m]!.active_tab_id).toBe("c2");
  });
  it("u from a child", async () => {
    const { m, rootId } = await seed();
    act(() => tabs().activateTab(m, "c2"));
    await settle();
    const afterC2 = snap(m);
    key("ctrl+b"); key("u");
    await settle();
    console.log("V2-u", JSON.stringify({ afterC2, afterU: snap(m), rootId }));
    expect(tabs().trees[m]!.active_tab_id).toBe(rootId);
  });
});

describe("V3 (F11) saved path clears ops added in flight; a later 409 then loses them", () => {
  it("B survives", async () => {
    const base = createInMemoryTabTreeAdapter();
    let release: (() => void) | null = null;
    let call = 0;
    const adapter: TabTreeAdapter = {
      load: (p, m) => base.load(p, m),
      allocate: (p, m) => base.allocate(p, m),
      async save(p, m, s) {
        call++;
        if (call === 1) {
          // first save succeeds, but slowly (in flight while B is spawned)
          await new Promise<void>((r) => { release = r; });
          return base.save(p, m, s);
        }
        if (call === 2) {
          // another device writes first -> this save 409s
          const cur = await base.load(p, m);
          await base.save(p, m, cur);
        }
        return base.save(p, m, s);
      },
    };
    act(() => tabs().setTabTreeAdapter(adapter));
    await act(async () => { await tabs().ensureMothership("reading"); });
    act(() => { tabs().spawnTab("reading", null, { tab_id: "A", kind: "reader", ref: "doc-a", mothership: "reading" }); });
    await settle(2);
    act(() => { tabs().spawnTab("reading", "A", { tab_id: "B", kind: "reader", ref: "doc-b", mothership: "reading" }); });
    const pendingBeforeRelease = tabs().pendingOps.reading.length;
    await act(async () => { release!(); });
    await settle(10);
    const t = tabs().trees.reading!;
    const persisted = await base.load("default", "reading");
    console.log("V3", JSON.stringify({ calls: call, pendingBeforeRelease, local: Object.keys(t.nodes), persisted: Object.keys(persisted.tree.nodes) }));
    expect(Object.keys(t.nodes)).toContain("B");
  });
});

describe("V4 (F19) two concurrent ensureMothership calls with different latencies", () => {
  it("a spawn made after the first load completes survives the second load", async () => {
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
    act(() => { tabs().spawnTab("reading", null, { tab_id: "A", kind: "reader", ref: "doc-a", mothership: "reading" }); });
    const afterSpawn = Object.keys(tabs().trees.reading!.nodes);
    await p2;
    const afterP2 = Object.keys(tabs().trees.reading!.nodes);
    console.log("V4", JSON.stringify({ loads: n, afterSpawn, afterP2 }));
    expect(afterP2).toContain("A");
  });
});

describe("V5 (F20) Trail row mounts only when a child is active", () => {
  it("records strip rows before/after a same-doc child activation", async () => {
    mount("/read/doc-9");
    await settle(3);
    const m = "reading" as const;
    const root = tabs().trees[m]!.active_tab_id!;
    const before = !!document.querySelector("[data-tab-trail]");
    act(() => { tabs().spawnTab(m, root, { tab_id: "c1", kind: "reader", ref: "doc-9", mothership: m, activate: true }); });
    await settle(3);
    const after = !!document.querySelector("[data-tab-trail]");
    const strip = document.querySelector("[data-document-strip]")!;
    const main = strip.parentElement;
    console.log("V5", JSON.stringify({ trailBefore: before, trailAfter: after, stripParentTag: main?.tagName, stripNextSibling: strip.nextElementSibling?.tagName }));
    expect(before).toBe(after);
  });
});
