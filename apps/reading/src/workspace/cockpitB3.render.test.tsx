/**
 * cockpitB3.render.test.tsx — lane A stage B3: the remaining render defects.
 *
 *   1  the agent tab strip at the pane width: one horizontally scrolling
 *      tablist with edge fades and an overflow menu (searchable past eight),
 *      "+ new agent" outside the scroller, no sideways scroll of the pane;
 *   2  writing: a preset round trip leaves exactly one outline;
 *   3  tier md: (superseded in R3-M4 by DESIGN-MODEL "Pane behaviour,
 *      ratified from A1b") both panes on screen, the right one 280 px;
 *   4  compressed hierarchical numbers stay unique along a path;
 *   5  the empty strip is as tall as a strip with tabs;
 *   7  the right pane is named for what it holds (Outline / Agents pane);
 *   8  the left strip's overflow cue: edge fades and a hidden-count chip;
 *  10  the strip carries its surface background (the docked preset).
 *
 * jsdom lays nothing out, so geometry is stubbed where a behaviour reads it
 * (scroll sizes and tab rects) and the rest is the DOM contract the layout
 * keeps: `hidden` for off-screen panes, the classes that make a row scroll.
 * The real-browser numbers live in the stage's render probe.
 */
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { useEffect, useState } from "react";
import { BrowserRouter, MemoryRouter, Route, Routes } from "react-router-dom";

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

const DETAIL = {
  deliverable_id: "d-1",
  title: "The memo",
  deliverable_kind: "general_essay",
  status: "draft",
  investigation_root_id: "inv-1",
  sections: [
    { section_id: "s-1", deliverable_id: "d-1", parent_section_id: null, section_index: 0, title: "Intro section", prose_text: "intro prose", prose_provenance: null, block_count: 1 },
  ],
};
const BLOCKS: Record<string, Array<Record<string, unknown>>> = {
  "s-1": [
    { outline_block_id: "b-1", section_id: "s-1", block_kind: "insight", provenance_kind: "graph_node", node_id: "n-1", content: "alpha claim", node_label: null, block_index: 0, is_user_originated: false },
  ],
};

const { getDeliverableMock, getSectionBlocksMock } = vi.hoisted(() => ({
  getDeliverableMock: vi.fn(),
  getSectionBlocksMock: vi.fn(),
}));

vi.mock("../lib/api", async (orig) => ({
  ...(await orig<typeof import("../lib/api")>()),
  apiFetch: vi.fn(() => Promise.resolve({ ok: false, status: 404, json: async () => ({}), text: async () => "" })),
  getDeliverable: getDeliverableMock,
  listInvestigations: vi.fn(async () => ({ count: 0, investigations: [] })),
  listDeliverables: vi.fn(async () => ({ count: 0, deliverables: [] })),
  postTypedEvent: vi.fn(() => Promise.resolve({ event_id: "e" })),
}));

vi.mock("../modes/Write/writeApi", async (orig) => ({
  ...(await orig<typeof import("../modes/Write/writeApi")>()),
  getSectionBlocks: getSectionBlocksMock,
  searchRepository: vi.fn(async () => []),
  listFolders: vi.fn(async () => ({ folders: [] })),
}));

import { prefixState } from "../components/hotkeys/prefixState";
import WriteHome from "../modes/Write/WriteHome";
import CompanionPane from "./CompanionPane";
import { PanelLayout } from "./PanelLayout";
import { useCompanion } from "./companionStore";
import { openDocumentInLeftPane } from "./crossPane";
import { StoryStrip, depthFixture, emptyFixture, siblingsFixture } from "./documentTabStories";
import { installShortcuts } from "./shortcuts";
import { compactHier } from "./tabStripParts";
import { useTabTrees } from "./tabTreeStore";
import { useWorkspace } from "./WorkspaceStore";
import { useWriteOutline } from "./writeOutlineStore";
import { pinPlatform, press, unpinPlatform } from "./keymapTestKit";

const { tierRef } = vi.hoisted(() => ({ tierRef: { current: "xl" as string } }));
vi.mock("./useViewportTier", () => ({ useViewportTier: () => tierRef.current }));

let uninstall: (() => void) | null = null;
const ws = () => useWorkspace.getState();
const comp = () => useCompanion.getState();

function key(target: EventTarget, spec: string) {
  act(() => {
    press(target, spec, "mac");
  });
}

const isVisible = (el: Element | null): boolean => el !== null && el.closest("[hidden]") === null;
const pane = (side: "left" | "right") => document.querySelector<HTMLElement>(`[data-pane="${side}"]`);
const visiblePanes = () =>
  Array.from(document.querySelectorAll<HTMLElement>("[data-pane]"))
    .filter(isVisible)
    .map((el) => el.getAttribute("data-pane"));

/**
 * Lay a horizontal strip out by hand: the scroller is `clientWidth` wide at
 * x = 0 and scrolled by `scrollLeft`; its tabs are `tabWidth` apart.
 */
function layOut(scroller: HTMLElement, opts: { clientWidth: number; tabWidth: number; scrollLeft: number }) {
  const tabs = Array.from(scroller.querySelectorAll<HTMLElement>("[role='tab']"));
  const scrollWidth = tabs.length * opts.tabWidth;
  Object.defineProperty(scroller, "clientWidth", { configurable: true, value: opts.clientWidth });
  Object.defineProperty(scroller, "scrollWidth", { configurable: true, value: scrollWidth });
  Object.defineProperty(scroller, "scrollLeft", { configurable: true, writable: true, value: opts.scrollLeft });
  scroller.getBoundingClientRect = () => new DOMRect(0, 0, opts.clientWidth, 28);
  tabs.forEach((tab, i) => {
    tab.getBoundingClientRect = () => {
      const left = i * opts.tabWidth - (scroller.scrollLeft as number);
      return new DOMRect(left, 0, opts.tabWidth - 4, 28);
    };
  });
  act(() => {
    fireEvent.scroll(scroller);
  });
}

const fades = (root: ParentNode = document) =>
  Array.from(root.querySelectorAll("[data-edge-fade]"))
    .filter(isVisible)
    .map((f) => f.getAttribute("data-edge-fade"))
    .sort();

function openAgents(n: number) {
  act(() => {
    for (let i = 0; i < n; i++) {
      comp().openAgentTab({ kind: "research-thread", investigationId: `inv-${i}`, title: `agent ${i}` });
    }
  });
}

beforeEach(() => {
  pinPlatform("mac");
  tierRef.current = "xl";
  window.localStorage.removeItem("antiek.workspace.layout-preset");
  getDeliverableMock.mockReset().mockImplementation(async (id: string) => (id === "d-1" ? DETAIL : null));
  getSectionBlocksMock.mockReset().mockImplementation(async (sectionId: string) => BLOCKS[sectionId] ?? []);
  ws().reset();
  ws().setLayoutPreset("docked");
  comp().reset();
  useTabTrees.getState().resetTabTrees();
  useWriteOutline.getState().reset();
  uninstall = installShortcuts(vi.fn() as never);
});

afterEach(() => {
  uninstall?.();
  uninstall = null;
  cleanup();
  prefixState.disarm();
  ws().reset();
  ws().setLayoutPreset("docked");
  comp().reset();
  useTabTrees.getState().resetTabTrees();
  useWriteOutline.getState().reset();
  unpinPlatform();
  document.body.innerHTML = "";
  window.history.replaceState({}, "", "/");
  window.localStorage.removeItem("antiek.workspace.layout-preset");
});

// ─── 1 the agent tab strip ──────────────────────────────────────────────

describe("B3-1 the agent tab strip at the pane width", () => {
  function mountPane() {
    return render(
      <MemoryRouter>
        <CompanionPane />
      </MemoryRouter>,
    );
  }
  const tablist = () => screen.getByRole("tablist", { name: "Agents" });

  it("every agent is a tab in ONE horizontally scrolling tablist; + new agent sits outside it", () => {
    openAgents(12);
    mountPane();
    expect(document.querySelectorAll("[data-agent-tab]")).toHaveLength(12);
    const list = tablist();
    expect(list.className).toMatch(/\boverflow-x-auto\b/);
    expect(list.className).toMatch(/\bmin-w-0\b/);
    const add = screen.getByRole("button", { name: "New agent" });
    // Never scrolled away with the tabs, never squeezed by them.
    expect(list.contains(add)).toBe(false);
    expect(add.closest("[data-agent-strip-row]")).toBeTruthy();
    expect(add.parentElement!.className).toMatch(/\bshrink-0\b/);
  });

  it("the pane's content never scrolls sideways: the strip row clips, the surface scrolls only down", () => {
    openAgents(3);
    mountPane();
    const section = document.querySelector<HTMLElement>("[data-companion-pane]")!;
    expect(section.className).toMatch(/\boverflow-hidden\b/);
    const row = document.querySelector<HTMLElement>("[data-agent-strip-row]")!;
    expect(row.className).toMatch(/\bmin-w-0\b/);
    const surface = document.getElementById("companion-agent-panel")!;
    expect(surface.className).toMatch(/\boverflow-x-hidden\b/);
    expect(surface.className).toMatch(/\boverflow-y-auto\b/);
  });

  it("edge fades show on the side(s) the tabs continue", () => {
    openAgents(12);
    mountPane();
    const list = tablist();
    layOut(list, { clientWidth: 300, tabWidth: 100, scrollLeft: 0 });
    expect(fades()).toEqual(["end"]);
    layOut(list, { clientWidth: 300, tabWidth: 100, scrollLeft: 450 });
    expect(fades()).toEqual(["end", "start"]);
    layOut(list, { clientWidth: 300, tabWidth: 100, scrollLeft: 900 });
    expect(fades()).toEqual(["start"]);
    layOut(list, { clientWidth: 1300, tabWidth: 100, scrollLeft: 0 });
    expect(fades()).toEqual([]);
  });

  it("an overflow menu lists every agent and searches past eight; picking one activates it", () => {
    openAgents(12);
    mountPane();
    layOut(tablist(), { clientWidth: 300, tabWidth: 100, scrollLeft: 0 });
    const trigger = document.querySelector<HTMLElement>("[data-agent-overflow]")!;
    expect(trigger).toBeTruthy();
    fireEvent.click(trigger);
    const menu = screen.getByRole("menu", { name: "All agents" });
    expect(menu.querySelectorAll("[role='menuitem']")).toHaveLength(12);
    const search = screen.getByRole("searchbox", { name: "Find an agent" });
    fireEvent.change(search, { target: { value: "agent 1" } });
    const items = Array.from(menu.querySelectorAll("[role='menuitem']")).map((b) => b.textContent);
    expect(items.every((t) => /agent 1/.test(t ?? ""))).toBe(true);
    expect(items).toHaveLength(3); // agent 1, agent 10, agent 11
    fireEvent.click(screen.getByRole("menuitem", { name: /agent 10/ }));
    expect(comp().activeTabId).toBe("agent:thread:inv-10");
  });

  it("eight agents or fewer: the menu lists them with no search box", () => {
    openAgents(6);
    mountPane();
    layOut(tablist(), { clientWidth: 300, tabWidth: 100, scrollLeft: 0 });
    fireEvent.click(document.querySelector<HTMLElement>("[data-agent-overflow]")!);
    expect(screen.getByRole("menu", { name: "All agents" }).querySelectorAll("[role='menuitem']")).toHaveLength(6);
    expect(screen.queryByRole("searchbox")).toBeNull();
  });

  it("arrow keys rove across every agent, not a visible five", () => {
    openAgents(7);
    mountPane();
    act(() => comp().activateAgentTab("agent:thread:inv-5"));
    const active = document.querySelector<HTMLElement>("[role='tab'][aria-selected='true']")!;
    act(() => active.focus());
    fireEvent.keyDown(active, { key: "ArrowRight" });
    expect(comp().activeTabId).toBe("agent:thread:inv-6");
  });
});

// ─── 2 writing: one outline ─────────────────────────────────────────────

describe("B3-2 writing: a preset round trip leaves exactly one outline", () => {
  function mountWrite(preset: "docked" | "omarchy-inset") {
    window.history.replaceState({}, "", "/write/d-1");
    ws().setLayoutPreset(preset);
    return render(
      <BrowserRouter>
        <PanelLayout
          mainSlot={
            <Routes>
              <Route path="/write/:deliverableId" element={<WriteHome />} />
            </Routes>
          }
        />
      </BrowserRouter>,
    );
  }
  // A1c low 14 regression guard: the detector was already global; this keeps
  // it from narrowing to one pane later.
  const outlines = () =>
    document.querySelectorAll("[data-write-outline]").length;
  async function togglePreset() {
    key(document.body, "ctrl+b");
    key(document.body, "shift+i");
    await act(async () => {
      await new Promise((r) => setTimeout(r, 0));
    });
  }

  it.each(["docked", "omarchy-inset"] as const)("starting %s: one outline, after one toggle and after two", async (start) => {
    mountWrite(start);
    await waitFor(() => expect(outlines()).toBe(1));
    await togglePreset();
    expect(ws().layoutPreset).not.toBe(start);
    await waitFor(() => expect(outlines()).toBe(1));
    // And it stays one (no late second mount).
    await act(async () => {
      await new Promise((r) => setTimeout(r, 20));
    });
    expect(outlines()).toBe(1);
    await togglePreset();
    expect(ws().layoutPreset).toBe(start);
    await waitFor(() => expect(outlines()).toBe(1));
    await act(async () => {
      await new Promise((r) => setTimeout(r, 20));
    });
    expect(outlines()).toBe(1);
  });

  it("the duplicate detector does not silently ignore an outline in either pane", async () => {
    mountWrite("docked");
    await waitFor(() => expect(outlines()).toBe(1));
    const first = document.querySelector<HTMLElement>("[data-write-outline]")!;
    const duplicate = first.cloneNode(true) as HTMLElement;
    duplicate.dataset.a1cDuplicateControl = "left-or-right";
    first.parentElement!.append(duplicate);
    expect(outlines()).toBe(2);
  });
});

// ─── 3 tier md: both panes, the right one 280 px (R3-M4) ────────────────
//
// Stage B3-3 showed ONE pane at a time at md. The binding DESIGN-MODEL line
// ("Pane behaviour, ratified from A1b (2026-09-27)") says: "At lg and md,
// the inset layout keeps both panes. At md, the right pane narrows to
// 280 px; at lg, it keeps its token width." These encode that line.

let mounts = 0;
function Stateful() {
  const [text, setText] = useState("");
  useEffect(() => {
    mounts += 1;
  }, []);
  return <input data-testid="route-input" value={text} onChange={(e) => setText(e.target.value)} />;
}

describe("R3-M4 tier md: the inset keeps both panes, the right narrowed to 280 px", () => {
  function mountAt(tier: string) {
    tierRef.current = tier;
    ws().setLayoutPreset("omarchy-inset");
    mounts = 0;
    return render(<PanelLayout mainSlot={<Stateful />} />);
  }

  it("md: both panes on screen, the right one 280 px wide, the left flexing", () => {
    mountAt("md");
    expect(visiblePanes()).toEqual(["left", "right"]);
    expect(pane("right")!.style.width).toBe("280px");
    expect(pane("left")!.className).toMatch(/(^|\s)flex-1(\s|$)/);
    // No one-pane machinery is left behind.
    expect(document.querySelector("[data-pane-switcher]")).toBeNull();
    expect(document.querySelector("[data-pane-offstage]")).toBeNull();
  });

  it("md: the left dock stays 0 px", () => {
    mountAt("md");
    expect(document.querySelector<HTMLElement>("aside[aria-label='Left dock']")!.style.width).toBe("0px");
  });

  it.each(["lg", "xl"])("%s: the right pane keeps its token width (320 px)", (tier) => {
    mountAt(tier);
    expect(visiblePanes()).toEqual(["left", "right"]);
    expect(pane("right")!.style.width).toBe("320px");
  });

  it("md: prefix l / prefix h move focus between the two visible panes; nothing hides or remounts", () => {
    mountAt("md");
    const input = document.querySelector<HTMLInputElement>('[data-testid="route-input"]')!;
    act(() => {
      input.focus();
      fireEvent.change(input, { target: { value: "draft" } });
      input.blur();
    });
    key(document.body, "ctrl+b");
    key(document.body, "l");
    expect(document.activeElement).toBe(pane("right"));
    expect(visiblePanes()).toEqual(["left", "right"]);
    key(document.body, "ctrl+b");
    key(document.body, "h");
    expect(document.activeElement).toBe(pane("left"));
    expect(document.querySelector<HTMLInputElement>('[data-testid="route-input"]')!.value).toBe("draft");
    expect(mounts).toBe(1);
  });

  it("md: fullscreen still shows the focused pane alone and restores both", () => {
    mountAt("md");
    key(document.body, "ctrl+b");
    key(document.body, "l");
    key(document.body, "ctrl+b");
    key(document.body, "f");
    expect(visiblePanes()).toEqual(["right"]);
    // Right-pane fullscreen takes the cockpit, not its 280 px column.
    expect(pane("right")!.style.width).toBe("");
    act(() => ws().setFullscreenPane(null));
    expect(visiblePanes()).toEqual(["left", "right"]);
    expect(pane("right")!.style.width).toBe("280px");
  });

  it("md: an agent opening a document on the left spawns the tab with the left pane already on screen", async () => {
    mountAt("md");
    key(document.body, "ctrl+b");
    key(document.body, "l");
    act(() => {
      openDocumentInLeftPane("doc-9", { from: "companion" });
    });
    await act(async () => {});
    await act(async () => {});
    const tree = useTabTrees.getState().trees.research;
    expect(tree && Object.values(tree.nodes).some((n) => n.ref === "doc-9")).toBe(true);
    expect(visiblePanes()).toEqual(["left", "right"]);
  });
});

// ─── 4 compressed numbers ───────────────────────────────────────────────

describe("B3-4 compressed hierarchical numbers stay unique along a path", () => {
  function pathOf(segs: number[]): string[] {
    return segs.map((_, i) => segs.slice(0, i + 1).join("."));
  }
  function assertUnique(path: string[]) {
    const shown = path.map(compactHier);
    expect(new Set(shown).size, shown.join(" | ")).toBe(path.length);
  }

  it("a depth-12 path of first children (1, 1.1, 1.1.1, …) never repeats a compressed number", () => {
    assertUnique(pathOf(Array(12).fill(1)));
  });

  it("depth-12 paths of mixed numbers stay unique too", () => {
    assertUnique(pathOf([1, 3, 1, 2, 1, 1, 2, 1, 1, 2, 1, 1]));
    assertUnique(pathOf([2, 1, 1, 1, 12, 1, 1, 1, 1, 12, 1, 1]));
    let seed = 7;
    for (let n = 0; n < 50; n++) {
      const segs = Array.from({ length: 12 }, () => {
        seed = (seed * 1103515245 + 12345) % 2147483648;
        return 1 + (seed % 3);
      });
      assertUnique(pathOf(segs));
    }
  });

  it("short numbers stay whole; a compressed one keeps the first segment and the last two", () => {
    expect(compactHier("1")).toBe("1");
    expect(compactHier("1.3.2")).toBe("1.3.2");
    expect(compactHier("1.4.3.2")).toBe("1.4.3.2");
    const c = compactHier("1.1.1.1.4.2");
    expect(c.startsWith("1…")).toBe(true);
    expect(c).toContain("4.2");
  });

  it("the depth-12 story shows no repeated number in its path header", () => {
    render(<StoryStrip fixture={depthFixture(12)} />);
    // The number a sighted reader sees on each crumb (the compressed form
    // when there is one; the full number is the accessible text).
    fireEvent.click(document.querySelector<HTMLElement>("[data-crumb-ellipsis]")!);
    const shown = Array.from(document.querySelectorAll<HTMLElement>("[data-tab-path-full] [data-crumb] .font-mono")).map(
      (el) => (el.querySelector("[aria-hidden='true']") ?? el).textContent,
    );
    expect(shown).toHaveLength(12);
    expect(new Set(shown).size, shown.join(" | ")).toBe(shown.length);
  });
});

// ─── 5 equal strip heights ──────────────────────────────────────────────

describe("B3-5 the empty strip is as tall as a strip with tabs", () => {
  const row = () => document.querySelector<HTMLElement>("[data-document-strip] [data-strip-row]");

  it("the tab row has one fixed height whether it holds tabs or 'No open tabs'", () => {
    render(<StoryStrip fixture={emptyFixture()} />);
    expect(screen.getByText("No open tabs")).toBeTruthy();
    const empty = row()!;
    expect(empty).toBeTruthy();
    const emptyHeight = empty.className.split(/\s+/).filter((c) => /^(h-|box-)/.test(c)).sort();
    cleanup();
    render(<StoryStrip fixture={depthFixture(1)} />);
    const full = row()!;
    const fullHeight = full.className.split(/\s+/).filter((c) => /^(h-|box-)/.test(c)).sort();
    expect(emptyHeight).toContain("h-7");
    expect(emptyHeight).toContain("box-content");
    expect(fullHeight).toEqual(emptyHeight);
  });
});

// ─── 7 the right pane's name ────────────────────────────────────────────

describe("B3-7 the right pane is named for what it holds", () => {
  function mountAt(path: string) {
    ws().setLayoutPreset("omarchy-inset");
    return render(
      <MemoryRouter initialEntries={[path]}>
        <PanelLayout mainSlot={<p>route</p>} />
      </MemoryRouter>,
    );
  }

  it("writing: 'Outline pane'", () => {
    mountAt("/write/d-1");
    expect(pane("right")!.getAttribute("aria-label")).toBe("Outline pane");
    expect(screen.queryByRole("region", { name: "Companion pane" })).toBeNull();
  });

  it.each(["/inv/x", "/read/book", "/"])("research/reading (%s): 'Agents pane'", (path) => {
    mountAt(path);
    expect(pane("right")!.getAttribute("aria-label")).toBe("Agents pane");
  });

  it("without a router the pane holds the companion: 'Agents pane'", () => {
    ws().setLayoutPreset("omarchy-inset");
    render(<PanelLayout mainSlot={<p>route</p>} />);
    expect(pane("right")!.getAttribute("aria-label")).toBe("Agents pane");
  });
});

// ─── 8 the left strip's overflow cue ────────────────────────────────────

describe("B3-8 the left strip shows what scrolled out of view", () => {
  const strip = () => document.querySelector<HTMLElement>("[data-sibling-strip]")!;

  it("edge fades on the sides that continue, and a chip counting the tabs out of view", () => {
    // The operator's 174-tab workspace (the active tab is the 88th sibling).
    render(<StoryStrip fixture={siblingsFixture(174)} />);
    const s = strip();
    expect(s.querySelectorAll("[role='tab']")).toHaveLength(174);
    const root = document.querySelector("[data-document-strip]")!;
    layOut(s, { clientWidth: 600, tabWidth: 100, scrollLeft: 0 });
    expect(fades(root)).toEqual(["end"]);
    // Six tabs fit in 600 px; 168 are out of view.
    const chip = document.querySelector<HTMLElement>("[data-hidden-tabs-chip]")!;
    expect(chip).toBeTruthy();
    expect(chip.textContent).toBe("+168");
    layOut(s, { clientWidth: 600, tabWidth: 100, scrollLeft: 700 });
    expect(fades(root)).toEqual(["end", "start"]);
    expect(document.querySelector("[data-hidden-tabs-chip]")!.textContent).toBe("+168");
    layOut(s, { clientWidth: 17400, tabWidth: 100, scrollLeft: 0 });
    expect(fades(root)).toEqual([]);
    expect(document.querySelector("[data-hidden-tabs-chip]")).toBeNull();
  });

  it("the chip opens the tree panel, where every tab is", () => {
    render(<StoryStrip fixture={siblingsFixture(174)} />);
    layOut(strip(), { clientWidth: 600, tabWidth: 100, scrollLeft: 0 });
    const chip = document.querySelector<HTMLElement>("[data-hidden-tabs-chip]")!;
    expect(chip.getAttribute("aria-label")).toMatch(/168 tabs out of view/);
    fireEvent.click(chip);
    expect(document.querySelector("[data-tab-tree-panel]")).toBeTruthy();
  });
});

// ─── 10 the strip's surface ─────────────────────────────────────────────

describe("B3-10 the document strip carries its surface background", () => {
  const surface = (el: Element | null) => {
    expect(el).toBeTruthy();
    expect(el!.className).toMatch(/\bbg-ice-1\b/);
    expect(el!.className).toMatch(/\bdark:bg-charcoal-1\b/);
  };

  it.each([
    ["with tabs", { fixture: depthFixture(4) }],
    ["empty", { fixture: emptyFixture() }],
    ["loading", { fixture: depthFixture(1), status: "loading" as const }],
    ["error", { fixture: depthFixture(1), status: "error" as const }],
  ])("%s", (_name, args) => {
    render(<StoryStrip {...args} />);
    surface(document.querySelector("[data-document-strip]"));
  });

  it("the docked preset's strip fallback too (drawn while the strip's chunk loads)", () => {
    ws().setLayoutPreset("docked");
    render(
      <MemoryRouter initialEntries={["/read/book"]}>
        <PanelLayout mainSlot={<p>route</p>} />
      </MemoryRouter>,
    );
    surface(document.querySelector("[data-document-strip]"));
  });
});

// ─── the stories ────────────────────────────────────────────────────────

describe("B3 stories mount and show what they claim", () => {
  it("CompanionPane: three agents, twelve agents (fades and the menu), at 320 px and md width", async () => {
    const stories = await import("./CompanionPane.stories");
    const names = Object.keys(stories).filter((k) => k !== "default") as (keyof typeof stories)[];
    expect(names.length).toBeGreaterThanOrEqual(5);
    for (const name of names) {
      const story = stories[name] as { args?: { agents: number; width: number } };
      const args = { ...stories.default.args, ...story.args } as { agents: number; width: number };
      const Pane = stories.default.component;
      render(<Pane {...args} />);
      expect(document.querySelectorAll("[data-agent-tab]"), String(name)).toHaveLength(args.agents);
      expect(screen.getByRole("button", { name: "New agent" })).toBeTruthy();
      cleanup();
    }
  });

  it("DocumentTabStrip: the narrow-pane and empty-strip stories", async () => {
    const stories = await import("./DocumentTabStrip.stories");
    render(<StoryStrip {...(stories.NarrowPaneSiblingsDay.args as Parameters<typeof StoryStrip>[0])} />);
    expect(document.querySelectorAll("[data-sibling-strip] [role='tab']")).toHaveLength(174);
    cleanup();
    render(<StoryStrip {...(stories.EmptyStripNight.args as Parameters<typeof StoryStrip>[0])} />);
    expect(screen.getByText("No open tabs")).toBeTruthy();
    expect(document.querySelector("[data-strip-row]")!.className).toMatch(/\bh-7\b/);
  });
});
