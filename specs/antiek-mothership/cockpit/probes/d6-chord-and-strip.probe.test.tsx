/**
 * VERIFIER PROBES (scratch only). Possible misses in d6-doc-tabs.
 */
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import { act, cleanup, render } from "@testing-library/react";
import { BrowserRouter, matchRoutes, useLocation } from "react-router-dom";

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
import { rootRefForPath, routeForTab } from "./documentSpace";

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
  cleanup();
  prefixState.disarm();
  tabs().resetTabTrees();
  unpinPlatform();
  document.body.innerHTML = "";
  window.history.replaceState({}, "", "/");
});

describe("V7 /read/meta-reading routes", () => {
  it("seeding and round trip", async () => {
    const r1 = rootRefForPath("/read/meta-reading");
    const r2 = rootRefForPath("/read/meta-reading/asset-1");
    const route2 = routeForTab({ tab_id: "x", parent_tab_id: null, hier_number: "1", child_order: [], kind: r2!.kind, ref: r2!.ref, mothership: "reading", public_number: null });
    const routes = [
      { path: "/read/meta-reading", id: "MetaReading" },
      { path: "/read/meta-reading/:assetId", id: "MetaReadingAsset" },
      { path: "/read/:documentId", id: "BookReader" },
    ];
    const m = matchRoutes(routes, route2);
    console.log("V7", JSON.stringify({ r1, r2, route2, matched: m?.map((x) => ({ id: x.route.id, params: x.params })) }));
    expect(m?.[0].route.id).toBe("MetaReadingAsset");
  });
});

describe("V8 ctrl+alt+c from inside a text field", () => {
  it("does the chord close the active tab while typing?", async () => {
    mount("/read/doc-9");
    await settle(3);
    const m = "reading" as const;
    const root = tabs().trees[m]!.active_tab_id!;
    act(() => { tabs().spawnTab(m, root, { tab_id: "c1", kind: "reader", ref: "doc-9", mothership: m, activate: true }); });
    await settle(3);
    const input = document.createElement("textarea");
    document.body.appendChild(input);
    input.focus();
    let e: KeyboardEvent | null = null;
    act(() => { e = press(input, "ctrl+alt+c", "mac"); });
    await settle(3);
    const t = tabs().trees[m]!;
    console.log("V8", JSON.stringify({ c1Open: !!t.nodes["c1"], active: t.active_tab_id, prevented: (e as unknown as KeyboardEvent).defaultPrevented, lastUndo: !!tabs().lastUndo }));
    expect(t.nodes["c1"]).toBeTruthy();
  });
});

describe("V9 history entries per tab click", () => {
  it("one click on a strip crumb pushes one history entry", async () => {
    mount("/inv/inv-1");
    await settle(3);
    act(() => {
      const r = tabs().trees.research!.active_tab_id!;
      tabs().spawnTab("research", r, { tab_id: "c1", kind: "research", ref: "/inv/inv-2", mothership: "research", activate: false });
      tabs().toggleTreePanel();
    });
    await settle(3);
    const pushes: string[] = [];
    const orig = window.history.pushState.bind(window.history);
    const spy = vi.spyOn(window.history, "pushState").mockImplementation((s, u, url) => {
      pushes.push(String(url));
      return orig(s, u, url as string);
    });
    const btn = document.querySelector('[data-tree-row="c1"] button') as HTMLElement;
    act(() => btn.click());
    await settle(5);
    spy.mockRestore();
    const t = tabs().trees.research!;
    console.log("V9", JSON.stringify({ pushes, loc: window.location.pathname, active: t.active_tab_id, roots: t.root_order }));
    expect(pushes.length).toBe(1);
  });
});

describe("V10 phone tier", () => {
  it("is there a tab strip at tier sm?", async () => {
    tierRef.current = "sm";
    mount("/read/doc-9");
    await settle(3);
    console.log("V10", JSON.stringify({ strip: !!document.querySelector("[data-document-strip]"), treeLoaded: !!tabs().trees.reading }));
    expect(document.querySelector("[data-document-strip]")).toBeTruthy();
  });
});
