/**
 * VERIFIER PROBES (scratch only). After an agent opens a document from
 * Research, can the operator navigate back into any Research-mode route?
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
import { pinPlatform, unpinPlatform } from "./keymapTestKit";
import { openDocumentInLeftPane } from "./crossPane";
import { createInMemoryTabTreeAdapter, emptyTabTree, spawnChild, setActive, toSnapshot } from "./tabTree";

const { tierRef } = vi.hoisted(() => ({ tierRef: { current: "xl" as string } }));
vi.mock("./useViewportTier", () => ({ useViewportTier: () => tierRef.current }));

const tabs = () => useTabTrees.getState();
let uninstall: (() => void) | null = null;
const navRef: { current: NavigateFunction | null } = { current: null };

function Probe() {
  const loc = useLocation();
  navRef.current = useNavigate();
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
async function go(p: string) {
  await act(async () => { navRef.current!(p); });
  await settle(10);
  return window.location.pathname;
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

describe("V11 trapped out of Research after an agent open", () => {
  it("each attempt to reach a research-mode route", async () => {
    mount("/inv/inv-1");
    await settle(3);
    act(() => openDocumentInLeftPane("doc-9", { from: "companion", investigationId: "inv-1" }));
    await settle(10);
    const afterOpen = window.location.pathname;
    const attempts: Record<string, string> = {};
    for (const p of ["/inv/inv-1", "/inv/inv-1", "/", "/home", "/my-research", "/inv/inv-2"]) {
      // eslint-disable-next-line no-await-in-loop
      attempts[`${Object.keys(attempts).length}:${p}`] = await go(p);
    }
    console.log("V11", JSON.stringify({ afterOpen, attempts, researchActive: tabs().trees.research!.active_tab_id }));
    expect(Object.values(attempts).some((v) => !v.startsWith("/read/"))).toBe(true);
  });
});

describe("V12 persisted tree loads after mount (lane B adapter shape)", () => {
  it("reload at /inv/inv-1 with a persisted active reader child", async () => {
    const adapter = createInMemoryTabTreeAdapter();
    let t = emptyTabTree("research");
    const a = spawnChild(t, null, { tab_id: "root:research:/inv/inv-1", kind: "research", ref: "/inv/inv-1", mothership: "research", activate: true });
    if (!a.ok) throw new Error("a");
    const b = spawnChild(a.tree, "root:research:/inv/inv-1", { tab_id: "kid", kind: "reader", ref: "doc-9", mothership: "research", activate: true, origin: { document_id: "doc-9", kind: "reference" } });
    if (!b.ok) throw new Error("b");
    const saved = await adapter.save("default", "research", toSnapshot(b.tree));
    act(() => tabs().setTabTreeAdapter(adapter));
    mount("/inv/inv-1");
    await settle(10);
    console.log("V12", JSON.stringify({ saved: saved.status, loc: window.location.pathname, active: tabs().trees.research?.active_tab_id }));
    expect(window.location.pathname).toBe("/inv/inv-1");
  });
});
