/**
 * cockpitRepairR1.lows.test.tsx — the critic's LOW findings on 211e9a7f7
 * that were cheap to close, each encoding the critic's code-read probe:
 *
 *   - the strip's lazy fallback was null (the strip popped in 28 px late)
 *     and the right pane hand-rolled its loading line (defect-9 class);
 *   - prefix t opened the tree panel without moving focus into it, and an
 *     outside click never closed it;
 *   - "Close only this" (lift_children) had no affordance anywhere;
 *   - Backspace on a focused agent tab closed it at once, with no undo;
 *   - a title that failed once was never asked for again.
 *
 * The first two tests must stay first: they read the lazy fallbacks, which
 * show only until each lazy module has loaded once in this file.
 */
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { BrowserRouter, MemoryRouter } from "react-router-dom";

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

import { prefixState } from "../components/hotkeys/prefixState";
import { LemonToastViewport } from "../components/lemon/LemonToast";
import { PanelLayout } from "./PanelLayout";
import { useWorkspace } from "./WorkspaceStore";
import { useCompanion } from "./companionStore";
import { installShortcuts } from "./shortcuts";
import { pinPlatform, press, unpinPlatform } from "./keymapTestKit";
import { requestTabTitle, setTitleResolvers, titleKey, useTabTitles } from "./tabTitles";
import { useTabTrees } from "./tabTreeStore";

const tabs = () => useTabTrees.getState();
const ws = () => useWorkspace.getState();
let uninstall: (() => void) | null = null;

async function flush(n = 6) {
  for (let i = 0; i < n; i++) await act(async () => {});
}

function key(target: EventTarget, spec: string) {
  act(() => {
    press(target, spec, "mac");
  });
}

/** Toasts outlive a test's render (the toast list is module state), so the
 *  newest Undo is this test's. */
const lastUndo = () => screen.getAllByRole("button", { name: /undo/i }).at(-1)!;

function mountCockpit(path: string) {
  window.history.replaceState({}, "", path);
  return render(
    <BrowserRouter>
      <PanelLayout mainSlot={<p>content</p>} />
      <LemonToastViewport />
    </BrowserRouter>,
  );
}

beforeEach(() => {
  pinPlatform("mac");
  tierRef.current = "xl";
  ws().reset();
  ws().setLayoutPreset("docked");
  tabs().resetTabTrees();
  useCompanion.getState().reset();
  uninstall = installShortcuts(vi.fn() as never);
});

afterEach(() => {
  vi.useRealTimers();
  uninstall?.();
  uninstall = null;
  cleanup();
  prefixState.disarm();
  ws().reset();
  ws().setLayoutPreset("docked");
  tabs().resetTabTrees();
  useCompanion.getState().reset();
  unpinPlatform();
  document.body.innerHTML = "";
  window.history.replaceState({}, "", "/");
  window.localStorage.removeItem("antiek.workspace.layout-preset");
});

describe("lazy surfaces load behind the shared LoadingState", () => {
  it("the strip's lazy fallback is its own skeleton, never null (no pop-in)", () => {
    mountCockpit("/read/doc-9");
    // Synchronously after the first render the lazy strip cannot have loaded.
    const strip = document.querySelector("[data-document-strip]");
    expect(strip).toBeTruthy();
    expect(strip!.querySelector("[data-skeleton='strip']")).toBeTruthy();
    expect(strip!.querySelector("[role='status']")?.textContent).toContain("Opening your tabs");
  });

  it("the right pane's lazy fallback is the shared LoadingState", () => {
    ws().setLayoutPreset("omarchy-inset");
    mountCockpit("/read/doc-9");
    const right = document.querySelector("[data-pane='right']")!;
    const status = right.querySelector("[role='status']");
    expect(status).toBeTruthy();
    expect(status!.querySelector("[data-skeleton]")).toBeTruthy();
  });
});

describe("the tree panel takes focus and closes on an outside click", () => {
  it("prefix t moves focus onto the active row; a pointerdown outside closes it", async () => {
    mountCockpit("/read/doc-9");
    await waitFor(() => expect(tabs().trees.reading?.active_tab_id ?? null).not.toBeNull());
    await flush();
    const active = tabs().trees.reading!.active_tab_id!;
    key(document.body, "ctrl+b");
    key(document.body, "t");
    await flush();
    expect(tabs().treePanelOpen).toBe(true);
    expect(document.activeElement?.getAttribute("data-tree-row")).toBe(active);
    act(() => {
      fireEvent.pointerDown(document.body);
    });
    expect(tabs().treePanelOpen).toBe(false);
  });
});

describe("Close only this — the second close outcome (§2a)", () => {
  async function seeded() {
    mountCockpit("/read/doc-9");
    await waitFor(() => expect(tabs().trees.reading?.active_tab_id ?? null).not.toBeNull());
    await flush();
    const root = tabs().trees.reading!.active_tab_id!;
    act(() => {
      tabs().spawnTab("reading", root, { tab_id: "mid", kind: "reader", ref: "doc-10", mothership: "reading", activate: false });
      tabs().spawnTab("reading", "mid", { tab_id: "leaf", kind: "reader", ref: "doc-11", mothership: "reading", activate: false });
    });
    key(document.body, "ctrl+b");
    key(document.body, "t");
    await flush();
    const row = document.querySelector("[data-tree-row='mid']") as HTMLElement;
    act(() => row.focus());
    return { root, row };
  }

  it("Shift+Delete on a row closes only that tab; its children lift to its parent, with Undo", async () => {
    const { root, row } = await seeded();
    act(() => {
      fireEvent.keyDown(row, { key: "Delete", shiftKey: true });
    });
    await flush();
    const tree = tabs().trees.reading!;
    expect(tree.nodes["mid"]).toBeUndefined();
    expect(tree.nodes["leaf"].parent_tab_id).toBe(root);
    expect(lastUndo()).toBeTruthy();
  });

  it("Delete on a row prunes it with everything under it (the default), with Undo", async () => {
    const { row } = await seeded();
    act(() => {
      fireEvent.keyDown(row, { key: "Delete" });
    });
    await flush();
    const tree = tabs().trees.reading!;
    expect(tree.nodes["mid"]).toBeUndefined();
    expect(tree.nodes["leaf"]).toBeUndefined();
    act(() => lastUndo().click());
    await flush();
    expect(tabs().trees.reading!.nodes["leaf"]).toBeTruthy();
  });
});

describe("agent tabs close deliberately", () => {
  async function companionWithTwo() {
    const CompanionPane = (await import("./CompanionPane")).default;
    act(() => {
      useCompanion.getState().openAgentTab({ kind: "dialogue", title: "First" });
      useCompanion.getState().openAgentTab({ kind: "research-thread", investigationId: "inv-2", title: "Second" });
    });
    render(
      <MemoryRouter>
        <CompanionPane />
        <LemonToastViewport />
      </MemoryRouter>,
    );
    await flush();
    return useCompanion.getState().tabs.map((t) => t.id);
  }

  it("Backspace on a focused agent tab does nothing", async () => {
    const [, second] = await companionWithTwo();
    const tab = document.getElementById(`agent-tab-${second}`) ?? screen.getAllByRole("tab").at(-1)!;
    act(() => {
      fireEvent.keyDown(tab, { key: "Backspace" });
    });
    expect(useCompanion.getState().tabs.map((t) => t.id)).toContain(second);
  });

  it("Delete closes it behind an Undo that puts it back in place; the tab names its key", async () => {
    const ids = await companionWithTwo();
    const tab = screen.getAllByRole("tab").at(-1)!;
    expect(tab.getAttribute("aria-keyshortcuts")).toBe("Delete");
    act(() => {
      fireEvent.keyDown(tab, { key: "Delete" });
    });
    await flush();
    expect(useCompanion.getState().tabs.map((t) => t.id)).toEqual([ids[0]]);
    act(() => lastUndo().click());
    await flush();
    expect(useCompanion.getState().tabs.map((t) => t.id)).toEqual(ids);
    expect(useCompanion.getState().activeTabId).toBe(ids[1]);
  });
});

describe("tab titles recover from a failed lookup", () => {
  it("a failed title is asked for again once the retry interval has passed", async () => {
    let calls = 0;
    let fail = true;
    setTitleResolvers({
      reader: async () => {
        calls++;
        if (fail) throw new Error("offline");
        return "On the Origin of Species";
      },
    });
    const tab = { kind: "reader" as const, ref: "doc-9" };
    requestTabTitle(tab);
    await flush();
    expect(useTabTitles.getState().entries[titleKey("reader", "doc-9")]).toMatchObject({ state: "failed" });
    // Straight away: no hammering.
    requestTabTitle(tab);
    await flush();
    expect(calls).toBe(1);
    // Later: asked again, and it lands.
    fail = false;
    const now = Date.now();
    const spy = vi.spyOn(Date, "now").mockReturnValue(now + 60_000);
    requestTabTitle(tab);
    await flush();
    spy.mockRestore();
    expect(calls).toBe(2);
    expect(useTabTitles.getState().entries[titleKey("reader", "doc-9")]).toEqual({
      state: "known",
      title: "On the Origin of Species",
    });
  });
});
