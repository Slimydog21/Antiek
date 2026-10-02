/**
 * cockpitRepairR2.test.tsx — cockpit lane A, repair round 2 (the critic's
 * REVISE of 85c091be1). One describe per finding, each encoding the critic's
 * probe with the assertion set to what the spec asks for:
 *
 *   H1  an agent opens a document as a LEFT tab in the current mode: from
 *       /read/<doc>, "+ new agent" → a research born from a book gives
 *       "Open source document →", which spawns a left child reader tab in
 *       the reading tree; "Open research →" keeps ?m=reading (inMode takes
 *       the mode from the path when no ?m is pinned).
 *   H5  §2.2 rev 7: every node carries `side`; an agent-opened node has
 *       origin kind "agent" and `opened_by {thread_id, agent_kind}`; an
 *       "agent" origin without opened_by is refused (tab_origin_invalid).
 *   M1  the writing right pane's block strip speaks the strips' overflow
 *       language (edge fades, an out-of-view count that lists every block)
 *       and the ARIA tabs pattern (roving tabIndex, arrows, aria-controls).
 *   M2  one Esc reaches exactly one handler with a focused floating panel
 *       in a fullscreen pane.
 *
 * H2 (saved prose editable) is in modes/Write/Outline.test.tsx, H3 (the
 * left toolbar in the inset) in AppShell.inset.test.tsx, H4 (the Thought
 * partner bookmark inside the reader) in modes/Reading/Reading.test.tsx.
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

import type { InvestigationSummary } from "../lib/api";

/** Fixtures name the wire field each case relies on (R3-H3; the R2 fixture
 *  hand-set a `read-<doc>` parent no real path produces, so it proved
 *  nothing about production):
 *   inv-beagle   THREAD-CONTRACT §1.2 ThreadSummary `document_id` (lane B's
 *                W1 wire, NOT shipped yet: until it is, GET /investigations
 *                omits it and a research spun from a book has parent null,
 *                so production does not reach this case).
 *   inv-meta     a `read-meta-<asset>` parent, a `read-` id that names no
 *                document: never a guessed source.
 *   inv-free     neither: no source link. */
const SUMMARIES: InvestigationSummary[] = [
  {
    investigation_id: "inv-beagle",
    question: "What did the Beagle's finches show?",
    status: "completed",
    started_at: "2026-09-20T10:00:00Z",
    completed_at: "2026-09-20T11:00:00Z",
    cost_usd_total: 0.5,
    parent_investigation_id: null,
    document_id: "voyage-of-the-beagle",
  },
  {
    investigation_id: "inv-meta",
    question: "A research under a meta-reading",
    status: "completed",
    started_at: "2026-09-18T10:00:00Z",
    completed_at: "2026-09-18T11:00:00Z",
    cost_usd_total: 0.1,
    parent_investigation_id: "read-meta-mr-abc123",
  },
  {
    investigation_id: "inv-free",
    question: "A question from nowhere",
    status: "completed",
    started_at: "2026-09-19T10:00:00Z",
    completed_at: "2026-09-19T11:00:00Z",
    cost_usd_total: 0.1,
    parent_investigation_id: null,
  },
];

const DETAIL = {
  deliverable_id: "d-1",
  title: "The memo",
  deliverable_kind: "general_essay",
  status: "draft",
  investigation_root_id: "inv-1",
  sections: [
    { section_id: "s-1", deliverable_id: "d-1", parent_section_id: null, section_index: 0, title: "Intro", prose_text: null, prose_provenance: null, block_count: 12 },
  ],
};
const BLOCKS = Array.from({ length: 12 }, (_, i) => ({
  outline_block_id: `b-${i}`,
  section_id: "s-1",
  block_kind: "insight",
  provenance_kind: "graph_node",
  node_id: `n-${i}`,
  content: `claim number ${i}`,
  node_label: null,
  block_index: i,
  is_user_originated: false,
}));

vi.mock("../lib/api", async (orig) => ({
  ...(await orig<typeof import("../lib/api")>()),
  apiFetch: vi.fn(() => Promise.resolve({ ok: false, status: 404, json: async () => ({}), text: async () => "" })),
  listInvestigations: vi.fn(async () => ({ count: SUMMARIES.length, investigations: SUMMARIES })),
  getDeliverable: vi.fn(async (id: string) => (id === "d-1" ? DETAIL : null)),
  postTypedEvent: vi.fn(() => Promise.resolve({ event_id: "e" })),
}));

vi.mock("../modes/Write/writeApi", async (orig) => ({
  ...(await orig<typeof import("../modes/Write/writeApi")>()),
  getSectionBlocks: vi.fn(async (sectionId: string) => (sectionId === "s-1" ? BLOCKS : [])),
}));

const { tierRef } = vi.hoisted(() => ({ tierRef: { current: "xl" as string } }));
vi.mock("./useViewportTier", () => ({ useViewportTier: () => tierRef.current }));

import { prefixState } from "../components/hotkeys/prefixState";
import { PanelLayout } from "./PanelLayout";
import WriteOutlinePane from "./WriteOutlinePane";
import { useCompanion } from "./companionStore";
import { mothershipForPath } from "./documentSpace";
import { inMode } from "./mothershipForPath";
import { installShortcuts } from "./shortcuts";
import { pinPlatform, unpinPlatform } from "./keymapTestKit";
import { emptyTabTree, fromSnapshot, spawnChild, toSnapshot } from "./tabTree";
import { useTabTrees } from "./tabTreeStore";
import { useWorkspace } from "./WorkspaceStore";
import { useWriteOutline } from "./writeOutlineStore";

const tabs = () => useTabTrees.getState();
const ws = () => useWorkspace.getState();
const comp = () => useCompanion.getState();
let uninstall: (() => void) | null = null;

async function settle(n = 8) {
  for (let i = 0; i < n; i++) {
    await act(async () => {
      await new Promise((r) => setTimeout(r, 0));
    });
  }
}

beforeEach(() => {
  pinPlatform("mac");
  tierRef.current = "xl";
  window.localStorage.removeItem("antiek.workspace.layout-preset");
  ws().reset();
  ws().setLayoutPreset("docked");
  comp().reset();
  tabs().resetTabTrees();
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
  tabs().resetTabTrees();
  unpinPlatform();
  document.body.innerHTML = "";
  window.history.replaceState({}, "", "/");
  window.localStorage.removeItem("antiek.workspace.layout-preset");
});

// ─── H1: an agent opens a document as a LEFT tab, in the current mode ───

describe("H1 — from a reader, an agent opens its source as a left tab in reading", () => {
  async function mountReaderInset() {
    window.history.replaceState({}, "", "/read/origin-of-species");
    ws().setLayoutPreset("omarchy-inset");
    render(
      <BrowserRouter>
        <PanelLayout mainSlot={<p>the reader</p>} />
      </BrowserRouter>,
    );
    // The strip that seeds the tree is a lazy chunk: the file's first mount
    // pays its cold transform, past waitFor's 1 s default on a loaded machine.
    await waitFor(() => expect(tabs().trees.reading?.active_tab_id ?? null).not.toBeNull(), { timeout: 8000 });
    await settle(3);
    return tabs().trees.reading!.active_tab_id!;
  }

  async function pickResearch(question: string) {
    fireEvent.click(await screen.findByRole("button", { name: "New agent" }));
    fireEvent.click(await screen.findByRole("menuitem", { name: question }));
  }

  it("+ new agent → a research whose summary carries document_id (lane B W1) offers its source, which opens as a left child tab in the reading tree", async () => {
    const readerTab = await mountReaderInset();
    await pickResearch("What did the Beagle's finches show?");
    const open = await screen.findByText("Open source document →");
    fireEvent.click(open);
    await waitFor(() => {
      const tree = tabs().trees.reading!;
      expect(Object.values(tree.nodes).some((n) => n.kind === "reader" && n.ref === "voyage-of-the-beagle")).toBe(true);
    });
    const tree = tabs().trees.reading!;
    const node = Object.values(tree.nodes).find((n) => n.kind === "reader" && n.ref === "voyage-of-the-beagle")!;
    // A child of the tab the operator was reading, on the LEFT, in reading.
    expect(node.parent_tab_id).toBe(readerTab);
    expect(node.side).toBe("left");
    expect(node.mothership).toBe("reading");
    // §2.2 rev 7 (S1): an agent-opened node says who opened it.
    expect(node.branch_origin?.kind).toBe("agent");
    expect(node.opened_by).toEqual({ thread_id: "inv-beagle", agent_kind: "research" });
    // The research tree was never touched: the mode did not switch.
    expect(tabs().trees.research ? Object.keys(tabs().trees.research!.nodes) : []).toHaveLength(0);
  });

  it("a research with no known source document offers no source link (never a guessed one)", async () => {
    await mountReaderInset();
    await pickResearch("A question from nowhere");
    await screen.findByText("Open research →");
    expect(screen.queryByText("Open source document →")).toBeNull();
  });

  it("a read- parent that names no document (a meta-reading) offers no source link", async () => {
    await mountReaderInset();
    await pickResearch("A research under a meta-reading");
    await screen.findByText("Open research →");
    expect(screen.queryByText("Open source document →")).toBeNull();
  });

  it("'Open research' from a reader keeps the reading mode (/inv/<id>?m=reading)", async () => {
    await mountReaderInset();
    await pickResearch("What did the Beagle's finches show?");
    const link = (await screen.findByText("Open research →")).closest("a")!;
    expect(link.getAttribute("href")).toBe("/inv/inv-beagle?m=reading");
    expect(mothershipForPath("/inv/inv-beagle", "?m=reading")).toBe("reading");
  });

  it("inMode takes the page's mode from its path when no ?m is pinned", () => {
    expect(inMode("/inv/x", "", "/read/origin-of-species")).toBe("/inv/x?m=reading");
    expect(inMode("/inv/x", "", "/write/d-1")).toBe("/inv/x?m=writing");
    // Same mode by path: untouched.
    expect(inMode("/inv/x", "", "/")).toBe("/inv/x");
    expect(inMode("/read/doc-2", "", "/library")).toBe("/read/doc-2");
    // A pinned ?m still wins over the path.
    expect(inMode("/inv/x", "?m=writing", "/read/doc")).toBe("/inv/x?m=writing");
  });
});

// ─── H5: side + opened_by on every node (§2.2 rev 7) ────────────────────

describe("H5 — §2.2 rev 7 node fields: side and opened_by", () => {
  it("every node carries a side; a child inherits it; an agent-opened child is always left", () => {
    let t = emptyTabTree("reading");
    const a = spawnChild(t, null, { tab_id: "root:reader:a", kind: "reader", ref: "a", mothership: "reading" });
    if (!a.ok) throw new Error(a.error.message);
    t = a.tree;
    expect(t.nodes["root:reader:a"].side).toBe("left");
    const b = spawnChild(t, "root:reader:a", {
      tab_id: "child:a:reader:b",
      kind: "reader",
      ref: "b",
      mothership: "reading",
      origin: { document_id: "b", kind: "agent" },
      opened_by: { thread_id: "inv-1", agent_kind: "research" },
    });
    if (!b.ok) throw new Error(b.error.message);
    expect(b.tree.nodes["child:a:reader:b"].side).toBe("left");
    expect(b.tree.nodes["child:a:reader:b"].opened_by).toEqual({ thread_id: "inv-1", agent_kind: "research" });
  });

  it("an agent origin without opened_by is refused: tab_origin_invalid, never a silent tab", () => {
    const t = emptyTabTree("reading");
    const r = spawnChild(t, null, {
      tab_id: "root:reader:x",
      kind: "reader",
      ref: "x",
      mothership: "reading",
      origin: { document_id: "x", kind: "agent" },
    });
    expect(r.ok).toBe(false);
    if (!r.ok) expect(r.error.code).toBe("tab_origin_invalid");
  });

  it("the snapshot carries side, the agent origin and opened_by through a round trip", () => {
    let t = emptyTabTree("reading");
    const r = spawnChild(t, null, {
      tab_id: "root:reader:y",
      kind: "reader",
      ref: "y",
      mothership: "reading",
      origin: { document_id: "y", kind: "agent" },
      opened_by: { thread_id: "inv-9", agent_kind: "research" },
    });
    if (!r.ok) throw new Error(r.error.message);
    t = r.tree;
    const snap = toSnapshot(t);
    const wire = snap.tree.nodes["root:reader:y"];
    expect(wire.side).toBe("left");
    expect(wire.branch_origin?.kind).toBe("agent");
    expect(wire.opened_by).toEqual({ thread_id: "inv-9", agent_kind: "research" });
    const back = fromSnapshot(JSON.parse(JSON.stringify(snap)));
    expect(back.ok).toBe(true);
    if (back.ok) expect(back.tree.nodes["root:reader:y"].opened_by?.thread_id).toBe("inv-9");
  });

  it("a server agent node without opened_by is refused on load; a legacy node without side reads as left", () => {
    const t = spawnChild(emptyTabTree("reading"), null, { tab_id: "root:reader:z", kind: "reader", ref: "z", mothership: "reading" });
    if (!t.ok) throw new Error(t.error.message);
    const snap = JSON.parse(JSON.stringify(toSnapshot(t.tree)));
    delete snap.tree.nodes["root:reader:z"].side;
    const legacy = fromSnapshot(snap);
    expect(legacy.ok).toBe(true);
    if (legacy.ok) expect(legacy.tree.nodes["root:reader:z"].side).toBe("left");
    snap.tree.nodes["root:reader:z"].branch_origin = { document_id: "z", kind: "agent" };
    const bad = fromSnapshot(snap);
    expect(bad.ok).toBe(false);
  });
});

// ─── M1: the block strip's overflow language and the ARIA tabs pattern ──

describe("M1 — the writing right pane's block strip", () => {
  function layOut(scroller: HTMLElement, clientWidth: number, tabWidth: number, scrollLeft = 0) {
    const all = Array.from(scroller.querySelectorAll<HTMLElement>("[role='tab']"));
    Object.defineProperty(scroller, "clientWidth", { configurable: true, value: clientWidth });
    Object.defineProperty(scroller, "scrollWidth", { configurable: true, value: all.length * tabWidth });
    Object.defineProperty(scroller, "scrollLeft", { configurable: true, writable: true, value: scrollLeft });
    scroller.getBoundingClientRect = () => new DOMRect(0, 0, clientWidth, 28);
    all.forEach((tab, i) => {
      tab.getBoundingClientRect = () => new DOMRect(i * tabWidth - (scroller.scrollLeft as number), 0, tabWidth - 4, 28);
    });
    act(() => {
      fireEvent.scroll(scroller);
    });
  }

  async function mountOutline() {
    render(
      <MemoryRouter initialEntries={["/write/d-1"]}>
        <div style={{ width: 318 }}>
          <WriteOutlinePane />
        </div>
      </MemoryRouter>,
    );
    const list = await screen.findByRole("tablist", { name: "Outline blocks" });
    await waitFor(() => expect(list.querySelectorAll("[role='tab']")).toHaveLength(12));
    return list;
  }

  it("12 blocks in 318 px: an end fade and a count of the blocks out of view that lists them all", async () => {
    const list = await mountOutline();
    layOut(list, 318, 106);
    const pane = document.querySelector("[data-write-outline]")!;
    expect(Array.from(pane.querySelectorAll("[data-edge-fade]")).map((f) => f.getAttribute("data-edge-fade"))).toEqual(["end"]);
    const more = pane.querySelector<HTMLElement>("[data-block-overflow]");
    expect(more).toBeTruthy();
    expect(more!.textContent).toContain("9");
    fireEvent.click(more!);
    const items = screen.getAllByRole("menuitem");
    expect(items).toHaveLength(12);
    fireEvent.click(items[10]);
    expect(useWriteOutline.getState().activeBlockId).toBe("b-10");
  });

  it("roving tabIndex, arrow / Home / End keys and aria-controls (the ARIA tabs pattern)", async () => {
    const list = await mountOutline();
    act(() => useWriteOutline.getState().setActiveBlock("b-0"));
    const all = () => Array.from(list.querySelectorAll<HTMLElement>("[role='tab']"));
    expect(all().filter((t) => t.tabIndex === 0)).toHaveLength(1);
    expect(all()[0].tabIndex).toBe(0);
    const panelId = all()[0].getAttribute("aria-controls");
    expect(panelId).toBeTruthy();
    expect(document.getElementById(panelId!)?.getAttribute("role")).toBe("tabpanel");
    all()[0].focus();
    fireEvent.keyDown(all()[0], { key: "ArrowRight" });
    expect(useWriteOutline.getState().activeBlockId).toBe("b-1");
    expect(document.activeElement).toBe(all()[1]);
    fireEvent.keyDown(all()[1], { key: "End" });
    expect(useWriteOutline.getState().activeBlockId).toBe("b-11");
    expect(document.activeElement).toBe(all()[11]);
    fireEvent.keyDown(all()[11], { key: "ArrowRight" });
    expect(useWriteOutline.getState().activeBlockId).toBe("b-0");
    fireEvent.keyDown(all()[0], { key: "Home" });
    expect(useWriteOutline.getState().activeBlockId).toBe("b-0");
    fireEvent.keyDown(all()[0], { key: "ArrowLeft" });
    expect(useWriteOutline.getState().activeBlockId).toBe("b-11");
  });

  // R3 (critic low): with no active block, ArrowRight skipped the first
  // block (index -1 clamped to 0, then +1).
  it("with no active block, ArrowRight selects the first block and ArrowLeft the last", async () => {
    const list = await mountOutline();
    act(() => useWriteOutline.getState().setActiveBlock(null));
    const all = () => Array.from(list.querySelectorAll<HTMLElement>("[role='tab']"));
    fireEvent.keyDown(list, { key: "ArrowRight" });
    expect(useWriteOutline.getState().activeBlockId).toBe("b-0");
    act(() => useWriteOutline.getState().setActiveBlock(null));
    fireEvent.keyDown(list, { key: "ArrowLeft" });
    expect(useWriteOutline.getState().activeBlockId).toBe("b-11");
    expect(document.activeElement).toBe(all()[11]);
  });

  // R3 (critic low): the ⋯ menu is role=menu, so it takes the ARIA menu keys.
  it("the ⋯ menu moves focus with ArrowDown / ArrowUp (wrapping), Home and End", async () => {
    const list = await mountOutline();
    layOut(list, 318, 106);
    fireEvent.click(document.querySelector<HTMLElement>("[data-block-overflow]")!);
    const menu = screen.getByRole("menu", { name: "All blocks" });
    const items = screen.getAllByRole("menuitem");
    await waitFor(() => expect(document.activeElement).toBe(items[0]));
    fireEvent.keyDown(items[0], { key: "ArrowDown" });
    expect(document.activeElement).toBe(items[1]);
    fireEvent.keyDown(items[1], { key: "ArrowUp" });
    expect(document.activeElement).toBe(items[0]);
    fireEvent.keyDown(items[0], { key: "ArrowUp" });
    expect(document.activeElement).toBe(items[11]);
    fireEvent.keyDown(items[11], { key: "Home" });
    expect(document.activeElement).toBe(items[0]);
    fireEvent.keyDown(items[0], { key: "End" });
    expect(document.activeElement).toBe(items[11]);
    expect(menu.contains(document.activeElement)).toBe(true);
  });
});

// ─── M2: one Esc, one handler, with a focused floating panel ────────────

describe("M2 — one Esc reaches exactly one handler with a floating panel in fullscreen", () => {
  it("the first Esc closes the focused floating panel only; the next restores the panes", async () => {
    ws().setLayoutPreset("omarchy-inset");
    render(
      <MemoryRouter>
        <PanelLayout mainSlot={<p>content</p>} />
      </MemoryRouter>,
    );
    let id = "";
    act(() => {
      id = ws().open("Notes", {}, { mode: "floating", title: "Notes" });
    });
    expect(ws().focusedPanelId).toBe(id);
    act(() => ws().setFullscreenPane("left"));
    const panelTitle = screen.getByRole("group", { name: "Notes — panel controls" });
    act(() => panelTitle.focus());
    act(() => {
      panelTitle.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true, cancelable: true }));
    });
    const panelClosed = !ws().panels[id];
    const restored = ws().fullscreenPane === null;
    expect([panelClosed, restored]).toEqual([true, false]);
    act(() => {
      document.body.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true, cancelable: true }));
    });
    expect(ws().fullscreenPane).toBeNull();
  });

  it("a focused floating panel in the pane fullscreen hides is not the Esc's: the panes restore and the panel stays", async () => {
    ws().setLayoutPreset("omarchy-inset");
    render(
      <MemoryRouter>
        <PanelLayout mainSlot={<p>content</p>} />
      </MemoryRouter>,
    );
    let id = "";
    act(() => {
      id = ws().open("Notes", {}, { mode: "floating", title: "Notes" });
    });
    act(() => ws().setFullscreenPane("right"));
    act(() => {
      document.body.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true, cancelable: true }));
    });
    expect(ws().fullscreenPane).toBeNull();
    expect(ws().panels[id]).toBeTruthy();
  });
});
