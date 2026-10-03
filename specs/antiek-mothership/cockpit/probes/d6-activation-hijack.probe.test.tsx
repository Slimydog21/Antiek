/**
 * VERIFIER PROBES (scratch only). F05 reach: which cross-mode routes bounce.
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

describe("V6 F05 reach", () => {
  it("/inv/a -> /read/doc -> /inv/b", async () => {
    mount("/inv/a");
    await settle(3);
    const r1 = await go("/read/doc");
    const r2 = await go("/inv/b");
    console.log("V6a", JSON.stringify({ r1, r2 }));
    expect(r2).toBe("/inv/b");
  });
  it("/inv/a -> /read/doc -> / (research home)", async () => {
    mount("/inv/a");
    await settle(3);
    const r1 = await go("/read/doc");
    const r2 = await go("/");
    console.log("V6b", JSON.stringify({ r1, r2 }));
    expect(r2).toBe("/");
  });
  it("/read/doc -> /write/w1 -> /read/doc2", async () => {
    mount("/read/doc");
    await settle(3);
    const r1 = await go("/write/w1");
    const r2 = await go("/read/doc2");
    console.log("V6c", JSON.stringify({ r1, r2 }));
    expect(r2).toBe("/read/doc2");
  });
  it("/read/doc -> /library (same mode) -> /read/doc2 (control)", async () => {
    mount("/read/doc");
    await settle(3);
    const r1 = await go("/library");
    const r2 = await go("/read/doc2");
    console.log("V6d", JSON.stringify({ r1, r2 }));
    expect(r2).toBe("/read/doc2");
  });
});
