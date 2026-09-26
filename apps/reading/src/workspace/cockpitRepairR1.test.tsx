/**
 * cockpitRepairR1.test.tsx — cockpit lane A, repair round 1.
 *
 * One describe per critic finding (REVISE of 211e9a7f7), each encoding the
 * critic's own probe with the assertion flipped to the behaviour the spec
 * asks for. Every test drives a surface that already existed at 211e9a7f7
 * (PanelLayout, the strip, the tab-tree store, the Write tree sync), so each
 * fails there for the finding's own reason:
 *
 *   P-A  a save queued before a close ran inside the hold and wrote the close;
 *   P-B  another piece's section tab never navigated to its piece;
 *   P-C  a closed-then-reopened piece got no section tabs;
 *   P-F  Esc with focus on body did not restore fullscreen;
 *   P-G  right-pane fullscreen kept the 320 px companion width.
 *
 * P-D (branches from a document) lives in branchFromDocument.test.tsx.
 */
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import { act, cleanup, fireEvent, render, renderHook, screen, waitFor } from "@testing-library/react";
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

import { prefixState } from "../components/hotkeys/prefixState";
import type { DeliverableDetailResponse } from "../lib/api";
import { PanelLayout } from "./PanelLayout";
import { useWorkspace } from "./WorkspaceStore";
import { childTabId, freshTabId, rootTabId } from "./documentSpace";
import { installShortcuts } from "./shortcuts";
import { pinPlatform, unpinPlatform } from "./keymapTestKit";
import { sectionRefOf } from "./sectionRef";
import {
  createInMemoryTabTreeAdapter,
  type TabTreeAdapter,
  type TabTreeSnapshot,
} from "./tabTree";
import { useTabTrees } from "./tabTreeStore";
import { useWriteTreeSync } from "./writeTreeSync";

const tabs = () => useTabTrees.getState();
const ws = () => useWorkspace.getState();
const nav: { current: NavigateFunction | null } = { current: null };
let uninstall: (() => void) | null = null;

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

const location = () => screen.getByTestId("location").textContent;

beforeEach(() => {
  pinPlatform("mac");
  tierRef.current = "xl";
  ws().reset();
  ws().setLayoutPreset("docked");
  tabs().resetTabTrees();
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
  unpinPlatform();
  document.body.innerHTML = "";
  window.history.replaceState({}, "", "/");
  window.localStorage.removeItem("antiek.workspace.layout-preset");
});

// ─── P-A: the §2.2 close hold never leaks through a queued save ─────────

describe("P-A — a save queued before a close never writes the held close", () => {
  /** An adapter whose saves wait for the test to release them, one by one. */
  function gatedAdapter(beforeSave?: (n: number) => Promise<void>) {
    const inner = createInMemoryTabTreeAdapter();
    const saves: TabTreeSnapshot[] = [];
    const gates: (() => void)[] = [];
    let n = 0;
    const adapter: TabTreeAdapter = {
      load: inner.load,
      allocate: inner.allocate,
      save: (p, m, s) => {
        const copy = JSON.parse(JSON.stringify(s)) as TabTreeSnapshot;
        const call = n++;
        return new Promise((resolve) =>
          gates.push(() => {
            void (async () => {
              await beforeSave?.(call);
              saves.push(copy);
              resolve(await inner.save(p, m, copy));
            })();
          }),
        );
      },
    };
    return { adapter, inner, saves, gates };
  }
  const closedIn = (s: TabTreeSnapshot, id: string) => Object.hasOwn(s.tree.history, id);
  async function releaseAll(gates: (() => void)[]) {
    for (let i = 0; i < 20 && gates.length > 0; i++) {
      await act(async () => {
        gates.shift()!();
      });
      await flush(4);
    }
  }

  it("the queued save runs inside the window without the close; the close lands when it lapses", async () => {
    const g = gatedAdapter();
    tabs().setTabTreeAdapter(g.adapter);
    await tabs().ensureMothership("reading");
    act(() => {
      tabs().spawnTab("reading", null, { tab_id: "r", kind: "reader", ref: "d1", mothership: "reading" });
    });
    await flush(2); // S1 in flight
    act(() => {
      tabs().spawnTab("reading", "r", { tab_id: "c", kind: "reader", ref: "d2", mothership: "reading" });
    }); // S2 queued behind S1
    vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout"] });
    act(() => tabs().closeActiveTab("reading", "prune"));
    expect(tabs().heldClose).not.toBeNull();
    await releaseAll(g.gates);
    expect(g.saves.some((s) => closedIn(s, "c"))).toBe(false);
    // S2 waited: the only snapshot written inside the window is S1's.
    expect(g.saves.map((s) => Object.keys(s.tree.nodes).sort())).toEqual([["r"]]);
    await act(async () => {
      vi.advanceTimersByTime(10_000);
    });
    await releaseAll(g.gates);
    expect(closedIn(await g.inner.load("default", "reading"), "c")).toBe(true);
  });

  it("a 409 inside the window rebases, keeps the close held (still undoable) and never writes it", async () => {
    let foreign: (() => Promise<void>) | null = null;
    const g = gatedAdapter(async (call) => {
      // Another device writes just before our first save lands.
      if (call === 0 && foreign) await foreign();
    });
    foreign = async () => {
      const cur = await g.inner.load("default", "reading");
      await g.inner.save("default", "reading", cur);
    };
    tabs().setTabTreeAdapter(g.adapter);
    await tabs().ensureMothership("reading");
    act(() => {
      tabs().spawnTab("reading", null, { tab_id: "r", kind: "reader", ref: "d1", mothership: "reading" });
      tabs().spawnTab("reading", "r", { tab_id: "c", kind: "reader", ref: "d2", mothership: "reading" });
    });
    await flush(2);
    vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout"] });
    act(() => tabs().closeActiveTab("reading", "prune"));
    const closeId = tabs().heldClose!.token.close_id;
    await releaseAll(g.gates);
    // Locally c is still closed, and the close is still the held one.
    expect(tabs().trees.reading!.nodes["c"]).toBeUndefined();
    expect(tabs().heldClose?.token.close_id).toBe(closeId);
    expect(g.saves.some((s) => closedIn(s, "c"))).toBe(false);
    act(() => tabs().undoClose(closeId));
    await releaseAll(g.gates);
    expect(tabs().trees.reading!.nodes["c"]).toBeTruthy();
    await act(async () => {
      vi.advanceTimersByTime(20_000);
    });
    await releaseAll(g.gates);
    expect(g.saves.some((s) => closedIn(s, "c"))).toBe(false);
  });
});

// ─── P-B: a section tab of another piece opens its piece ────────────────

describe("P-B — activating another piece's section tab navigates to that piece", () => {
  it("from /write/B, A's section 1.x lands on /write/A with the section active", async () => {
    mount("/write/B");
    await waitFor(() => expect(tabs().trees.writing?.active_tab_id ?? null).not.toBeNull());
    await flush();
    const aRoot = rootTabId({ kind: "document", ref: "/write/A" });
    act(() => {
      tabs().spawnTab("writing", null, { tab_id: aRoot, kind: "document", ref: "/write/A", mothership: "writing", activate: false });
      tabs().spawnTab("writing", aRoot, { tab_id: "secA", kind: "document", ref: sectionRefOf("sa"), mothership: "writing", activate: false });
    });
    act(() => tabs().activateTab("writing", "secA"));
    await flush();
    expect(location()).toBe("/write/A");
    // The route sync sees the section's piece on screen: the section stays active.
    expect(tabs().trees.writing!.active_tab_id).toBe("secA");
  });

  it("a section of another piece never scopes this piece's outline", async () => {
    // Imported here so the rest of the file runs where the helper is absent.
    const { sectionScopeFor } = await import("./writeTreeSync");
    const sections = [{ section_id: "b1" }, { section_id: "b2" }];
    const tabOf = (ref: string) => ({ kind: "document" as const, ref });
    expect(sectionScopeFor(tabOf(sectionRefOf("b2")), sections)).toBe("b2");
    expect(sectionScopeFor(tabOf(sectionRefOf("a1")), sections)).toBeNull();
    expect(sectionScopeFor(tabOf("/write/B"), sections)).toBeNull();
    expect(sectionScopeFor(null, sections)).toBeNull();
  });
});

// ─── P-C: a reopened piece gets its section tabs again ──────────────────

describe("P-C — a piece closed and reopened gets its section tabs under the new root", () => {
  it("the Write sync adopts the reseeded root (base~2), not the closed base id", async () => {
    await tabs().ensureMothership("writing");
    const detail = {
      deliverable_id: "A",
      title: "Piece A",
      investigation_root_id: null,
      sections: [
        { section_id: "s1", section_index: 0, title: "One" },
        { section_id: "s2", section_index: 1, title: "Two" },
      ],
    } as unknown as DeliverableDetailResponse;
    const h = renderHook(({ d }) => useWriteTreeSync(d), { initialProps: { d: detail } });
    await flush();
    const base = rootTabId({ kind: "document", ref: "/write/A" });
    expect(tabs().trees.writing!.nodes[base].child_order.length).toBe(2);
    vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout"] });
    act(() => tabs().activateTab("writing", base));
    act(() => tabs().closeActiveTab("writing", "prune"));
    await act(async () => {
      vi.advanceTimersByTime(10_000);
    });
    vi.useRealTimers();
    const fresh = freshTabId(tabs().trees.writing!, base);
    expect(fresh).toBe(`${base}~2`);
    act(() => {
      tabs().spawnTab("writing", null, { tab_id: fresh, kind: "document", ref: "/write/A", mothership: "writing" });
    });
    h.rerender({ d: { ...(detail as object) } as DeliverableDetailResponse });
    await flush();
    const after = tabs().trees.writing!;
    expect(after.nodes[fresh].child_order).toEqual([
      childTabId(fresh, "document", sectionRefOf("s1")),
      childTabId(fresh, "document", sectionRefOf("s2")),
    ]);
    expect(after.root_order).toEqual([fresh]);
  });

  it("with the piece closed and not reopened, the sync seeds a fresh root rather than failing", async () => {
    await tabs().ensureMothership("writing");
    const detail = {
      deliverable_id: "A",
      title: "Piece A",
      investigation_root_id: null,
      sections: [{ section_id: "s1", section_index: 0, title: "One" }],
    } as unknown as DeliverableDetailResponse;
    const h = renderHook(({ d }) => useWriteTreeSync(d), { initialProps: { d: detail } });
    await flush();
    const base = rootTabId({ kind: "document", ref: "/write/A" });
    vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout"] });
    act(() => tabs().activateTab("writing", base));
    act(() => tabs().closeActiveTab("writing", "prune"));
    await act(async () => {
      vi.advanceTimersByTime(10_000);
    });
    vi.useRealTimers();
    h.rerender({ d: { ...(detail as object) } as DeliverableDetailResponse });
    await flush();
    const after = tabs().trees.writing!;
    expect(after.root_order).toEqual([`${base}~2`]);
    expect(after.nodes[`${base}~2`].child_order.length).toBe(1);
  });
});

// ─── P-F / P-G: fullscreen ──────────────────────────────────────────────

describe("P-F — Esc restores fullscreen from any focus", () => {
  it.each(["omarchy-inset", "docked"] as const)("%s: Esc on body restores both panes", async (preset) => {
    ws().setLayoutPreset(preset);
    // Docked fullscreen collapses the docks, so it needs one to hide (with
    // none it is an honest no-op: F-18's 0 px sidecar trap).
    if (preset === "docked") ws().open("Notes", {}, { mode: "docked-left", id: "p:left", title: "Left" });
    mount("/read/doc-9");
    await flush();
    act(() => ws().toggleFullscreenPane());
    expect(ws().fullscreenPane).not.toBeNull();
    act(() => {
      fireEvent.keyDown(document.body, { key: "Escape", code: "Escape" });
    });
    expect(ws().fullscreenPane).toBeNull();
  });

  it("Esc a dialog or a text field claims stays theirs", async () => {
    ws().setLayoutPreset("omarchy-inset");
    mount("/read/doc-9");
    await flush();
    act(() => ws().toggleFullscreenPane());
    const dialog = document.createElement("div");
    dialog.setAttribute("role", "dialog");
    const btn = document.createElement("button");
    dialog.appendChild(btn);
    document.body.appendChild(dialog);
    act(() => {
      fireEvent.keyDown(btn, { key: "Escape", code: "Escape" });
    });
    expect(ws().fullscreenPane).not.toBeNull();
    const input = document.createElement("input");
    document.body.appendChild(input);
    act(() => {
      fireEvent.keyDown(input, { key: "Escape", code: "Escape" });
    });
    expect(ws().fullscreenPane).not.toBeNull();
    // No listener outlives fullscreen: a later Esc is not the layout's.
    act(() => {
      fireEvent.keyDown(document.body, { key: "Escape", code: "Escape" });
    });
    expect(ws().fullscreenPane).toBeNull();
  });
});

describe("P-G — right-pane fullscreen fills the cockpit", () => {
  it("the right pane drops its 320 px width and grows; the left is hidden", async () => {
    ws().setLayoutPreset("omarchy-inset");
    mount("/read/doc-9");
    await flush();
    act(() => ws().setFocusedPane("right"));
    act(() => ws().toggleFullscreenPane());
    expect(ws().fullscreenPane).toBe("right");
    const right = document.querySelector("[data-pane='right']") as HTMLElement;
    // Hidden, never unmounted (F-17): the route keeps its state.
    expect(document.querySelector("[data-pane='left']")!.closest("[hidden]")).not.toBeNull();
    expect(right.style.width).toBe("");
    expect(right.className.includes("shrink-0")).toBe(false);
    expect(right.className.includes("flex-1")).toBe(true);
    act(() => ws().toggleFullscreenPane());
    const back = document.querySelector("[data-pane='right']") as HTMLElement;
    expect(back.style.width).toBe("320px");
    expect(back.className.includes("shrink-0")).toBe(true);
  });
});
