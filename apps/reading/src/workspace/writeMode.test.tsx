/**
 * writeMode.test.tsx — cockpit chrome PR 4 (C5) acceptance.
 *
 *   Write mode in the cockpit: the writing mothership's document tree holds
 *   the full body as tab 1 with one child tab per section (1.1, 1.2, …) and
 *   WriteHome scopes its view to the active tab (body = the full outline, a
 *   section tab = that section alone — the same Outline, never a fake
 *   per-section editor). The right pane is mode-aware: the outline pane in
 *   writing mode (one tab per outline block, each a source-document drop
 *   target), the companion in research/reading. DnD assignment lands in the
 *   honest blockSources bridge (session state, never a pretend-write). The
 *   AI sidecar binding is untouched. Prefix ,/. cycles outline block tabs
 *   with the companion's muscle memory.
 */
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import { act, cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { BrowserRouter, Route, Routes } from "react-router-dom";

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
    { section_id: "s-1", deliverable_id: "d-1", parent_section_id: null, section_index: 0, title: "Intro section", prose_text: "intro prose", prose_provenance: null, block_count: 2 },
    { section_id: "s-2", deliverable_id: "d-1", parent_section_id: null, section_index: 1, title: "Body section", prose_text: "body prose", prose_provenance: null, block_count: 1 },
  ],
};

const BLOCKS: Record<string, Array<Record<string, unknown>>> = {
  "s-1": [
    { outline_block_id: "b-1", section_id: "s-1", block_kind: "insight", provenance_kind: "graph_node", node_id: "n-1", content: "alpha claim", node_label: null, block_index: 0, is_user_originated: false },
    { outline_block_id: "b-2", section_id: "s-1", block_kind: "open_question", provenance_kind: "graph_node", node_id: "n-2", content: "beta question", node_label: null, block_index: 1, is_user_originated: false },
  ],
  "s-2": [
    { outline_block_id: "b-3", section_id: "s-2", block_kind: "insight", provenance_kind: "graph_node", node_id: "n-3", content: "gamma claim", node_label: null, block_index: 0, is_user_originated: false },
  ],
};

const { apiFetchMock, getDeliverableMock, listInvestigationsMock, getSectionBlocksMock, searchRepositoryMock, listFoldersMock } =
  vi.hoisted(() => ({
    apiFetchMock: vi.fn(),
    getDeliverableMock: vi.fn(),
    listInvestigationsMock: vi.fn(),
    getSectionBlocksMock: vi.fn(),
    searchRepositoryMock: vi.fn(),
    listFoldersMock: vi.fn(),
  }));

vi.mock("../lib/api", async (orig) => ({
  ...(await orig<typeof import("../lib/api")>()),
  apiFetch: apiFetchMock,
  getDeliverable: getDeliverableMock,
  listInvestigations: listInvestigationsMock,
  listDeliverables: vi.fn(async () => ({ count: 0, deliverables: [] })),
  postTypedEvent: vi.fn(() => Promise.resolve({ event_id: "e" })),
}));

vi.mock("../modes/Write/writeApi", async (orig) => ({
  ...(await orig<typeof import("../modes/Write/writeApi")>()),
  getSectionBlocks: getSectionBlocksMock,
  searchRepository: searchRepositoryMock,
  listFolders: listFoldersMock,
}));

import { KEYMAP } from "../components/hotkeys/keymap";
import { prefixState } from "../components/hotkeys/prefixState";
import WriteHome from "../modes/Write/WriteHome";
import { PanelLayout } from "./PanelLayout";
import { SOURCE_DOCUMENT_MIME } from "./WriteOutlinePane";
import { useBlockSources } from "./blockSources";
import { useCompanion } from "./companionStore";
import { useTabTrees } from "./tabTreeStore";
import { useWorkspace } from "./WorkspaceStore";
import { WRITE_OUTLINE_PANEL_ID, useWriteOutline } from "./writeOutlineStore";
import { childTabId } from "./documentSpace";
import { installShortcuts } from "./shortcuts";
import { pinPlatform, press, unpinPlatform } from "./keymapTestKit";

const { tierRef } = vi.hoisted(() => ({ tierRef: { current: "xl" as string } }));
vi.mock("./useViewportTier", () => ({
  useViewportTier: () => tierRef.current,
}));

let uninstall: (() => void) | null = null;
const ws = () => useWorkspace.getState();
const tabs = () => useTabTrees.getState();
const outline = () => useWriteOutline.getState();
const sources = () => useBlockSources.getState();

function key(target: EventTarget, spec: string): KeyboardEvent {
  let e = new KeyboardEvent("keydown");
  act(() => {
    e = press(target, spec, "mac");
  });
  return e;
}

function mountCockpit(path: string, preset: "docked" | "omarchy-inset" = "omarchy-inset") {
  window.history.replaceState({}, "", path);
  ws().setLayoutPreset(preset);
  return render(
    <BrowserRouter>
      <PanelLayout
        mainSlot={
          <Routes>
            <Route path="/write/:deliverableId" element={<WriteHome />} />
            <Route path="/inv/:investigationId" element={<p>investigation surface</p>} />
          </Routes>
        }
      />
    </BrowserRouter>,
  );
}

beforeEach(() => {
  pinPlatform("mac");
  tierRef.current = "xl";
  apiFetchMock.mockReset().mockImplementation(() =>
    Promise.resolve({ ok: false, status: 404, json: async () => ({}), text: async () => "" }),
  );
  getDeliverableMock.mockReset().mockImplementation(async (id: string) =>
    id === "d-1" ? DETAIL : null,
  );
  listInvestigationsMock.mockReset().mockResolvedValue({ count: 0, investigations: [] });
  getSectionBlocksMock.mockReset().mockImplementation(async (sectionId: string) => BLOCKS[sectionId] ?? []);
  searchRepositoryMock.mockReset().mockResolvedValue([]);
  listFoldersMock.mockReset().mockResolvedValue({ folders: [] });
  ws().reset();
  ws().setLayoutPreset("docked");
  tabs().resetTabTrees();
  outline().reset();
  sources().reset();
  useCompanion.getState().reset();
  uninstall = installShortcuts(vi.fn() as never);
});

afterEach(() => {
  uninstall?.();
  uninstall = null;
  cleanup();
  prefixState.disarm();
  ws().reset();
  ws().setLayoutPreset("docked");
  tabs().resetTabTrees();
  outline().reset();
  sources().reset();
  useCompanion.getState().reset();
  unpinPlatform();
  document.body.innerHTML = "";
  window.history.replaceState({}, "", "/");
  window.localStorage.removeItem("antiek.workspace.layout-preset");
});

// ─── the writing document tree ───────────────────────────────────────────

describe("the writing mothership tree (C5 left)", () => {
  it("seeds the full body as tab 1 with one child tab per section", async () => {
    mountCockpit("/write/d-1");
    await screen.findAllByText("Intro section");
    const tree = tabs().trees.writing!;
    const body = Object.values(tree.nodes).find((n) => n.parent_tab_id === null);
    expect(body?.kind).toBe("document");
    expect(body?.ref).toBe("/write/d-1");
    expect(body?.hier_number).toBe("1");
    const children = body!.child_order.map((id) => tree.nodes[id]);
    expect(children.map((c) => c.hier_number)).toEqual(["1.1", "1.2"]);
    expect(children.map((c) => c.ref)).toEqual(["section:s-1", "section:s-2"]);
  });

  it("a section tab scopes the piece view to that section; the body tab shows all", async () => {
    const { container } = mountCockpit("/write/d-1");
    await screen.findAllByText("Intro section");
    const main = container.querySelector("main")!;
    expect(within(main as HTMLElement).getAllByText("Body section").length).toBeGreaterThan(0);
    const cid = childTabId("root:document:/write/d-1", "document", "section:s-2");
    act(() => {
      tabs().activateTab("writing", cid);
    });
    // Only the active section renders in the main surface — the same Outline,
    // one section. (The right outline pane keeps its own block card; that is
    // the C5 split, so the scoping is asserted on the main surface.)
    await within(main as HTMLElement).findAllByText("Body section");
    expect(within(main as HTMLElement).queryByText("Intro section")).toBeNull();
    expect(within(main as HTMLElement).getAllByText("Body section").length).toBeGreaterThan(0);
    // Back to the body tab: both sections again.
    act(() => {
      tabs().activateTab("writing", "root:document:/write/d-1");
    });
    await within(main as HTMLElement).findAllByText("Intro section");
    expect(within(main as HTMLElement).getAllByText("Body section").length).toBeGreaterThan(0);
  });
});

// ─── the mode-aware right pane ───────────────────────────────────────────

describe("the mode-aware right pane (C4/C5 contract)", () => {
  it("writing mode gets the outline pane with one tab per outline block — NOT the companion", async () => {
    mountCockpit("/write/d-1");
    await screen.findAllByText("alpha claim");
    const right = document.querySelector<HTMLElement>('[data-pane="right"]')!;
    expect(right.querySelector("[data-write-outline]")).toBeTruthy();
    expect(right.querySelector("[data-companion-pane]")).toBeNull();
    expect(right.querySelector('[data-block-tab="b-1"]')).toBeTruthy();
    expect(right.querySelector('[data-block-tab="b-2"]')).toBeTruthy();
    expect(right.querySelector('[data-block-tab="b-3"]')).toBeTruthy();
    // The first block is active with its content summary + provenance.
    expect(right.querySelector('[data-block-card="b-1"]')).toBeTruthy();
    expect(right.textContent).toContain("Intro section");
  });

  it("research mode still gets the companion right pane", async () => {
    mountCockpit("/inv/inv-1");
    await screen.findAllByText("investigation surface");
    const right = document.querySelector<HTMLElement>('[data-pane="right"]')!;
    expect(right.querySelector("[data-companion-pane]")).toBeTruthy();
    expect(right.querySelector("[data-write-outline]")).toBeNull();
  });

  it("the docked preset surfaces the outline as a right-dock panel on a piece route", async () => {
    mountCockpit("/write/d-1", "docked");
    await screen.findAllByText("Intro section");
    expect(ws().panels[WRITE_OUTLINE_PANEL_ID]).toBeTruthy();
    expect(ws().dockRightIds).toContain(WRITE_OUTLINE_PANEL_ID);
  });
});

// ─── drag-and-drop source assignment ────────────────────────────────────

describe("drag a source document onto a block tab", () => {
  function dropOn(blockId: string, payload: { document_id: string; document_title: string | null }) {
    const tab = document.querySelector<HTMLElement>(`[data-block-tab="${blockId}"]`)!;
    fireEvent.dragOver(tab, {
      dataTransfer: { types: { includes: (t: string) => t === SOURCE_DOCUMENT_MIME } },
    });
    fireEvent.drop(tab, {
      dataTransfer: {
        getData: (t: string) => (t === SOURCE_DOCUMENT_MIME ? JSON.stringify(payload) : ""),
      },
    });
  }

  it("assigns the source to the block and reflects it — with NO pretend-write to the server", async () => {
    mountCockpit("/write/d-1");
    await screen.findAllByText("alpha claim");
    dropOn("b-2", { document_id: "doc-source", document_title: "The Source Book" });
    // The assignment record landed (session-scoped bridge, write-through TODO).
    const record = sources().records["d-1"]?.["b-2"] ?? [];
    expect(record).toHaveLength(1);
    expect(record[0].document_id).toBe("doc-source");
    // The drop activated the block tab, and the card lists the source by title.
    expect(outline().activeBlockId).toBe("b-2");
    await screen.findByText("The Source Book");
    expect(document.querySelector('[data-block-tab="b-2"]')!.textContent).toContain("·1");
    // The honest bridge: no deliverable mutation was faked to the server.
    const writes = apiFetchMock.mock.calls.filter(([input]) => {
      const url = String(input);
      return url.includes("/deliverables") || url.includes("/write/");
    });
    expect(writes).toHaveLength(0);
    // Idempotent re-drop: no duplicate.
    dropOn("b-2", { document_id: "doc-source", document_title: "The Source Book" });
    expect(sources().records["d-1"]["b-2"]).toHaveLength(1);
    // Unassign is the operator's undo.
    fireEvent.click(screen.getByLabelText("Remove The Source Book from this block"));
    expect(sources().records["d-1"]["b-2"] ?? []).toHaveLength(0);
  });

  it("an empty assignment list says so honestly, with the session-state label", async () => {
    mountCockpit("/write/d-1");
    await screen.findAllByText("alpha claim");
    expect(document.querySelector("[data-no-sources]")!.textContent).toContain("None assigned yet");
    expect(document.querySelector("[data-no-sources]")!.textContent).toContain("session state");
  });
});

// ─── keys: outline block cycling + the untouched sidecar ────────────────

describe("the keys in writing mode", () => {
  it("prefix ,/. cycle the outline's block tabs (the right-pane muscle memory)", async () => {
    mountCockpit("/write/d-1");
    await screen.findAllByText("alpha claim");
    expect(outline().activeBlockId).toBe("b-1");
    key(document.body, "ctrl+b");
    key(document.body, ",");
    expect(outline().activeBlockId).toBe("b-2");
    key(document.body, "ctrl+b");
    key(document.body, ",");
    expect(outline().activeBlockId).toBe("b-3");
    key(document.body, "ctrl+b");
    key(document.body, ","); // wraps
    expect(outline().activeBlockId).toBe("b-1");
    key(document.body, "ctrl+b");
    key(document.body, ".");
    expect(outline().activeBlockId).toBe("b-3");
  });

  it("the AI sidecar binding is untouched and works on a write route", async () => {
    const row = KEYMAP.find((r) => r.id === "aisidecar");
    expect(row?.action).toBe("aisidecar.toggle");
    expect(row?.chord).toBe("mod+/");
    mountCockpit("/write/d-1");
    await screen.findAllByText("Intro section");
    expect(ws().panels["shortcuts:aisidecar"]).toBeUndefined();
    key(document.body, "mod+/");
    expect(ws().panels["shortcuts:aisidecar"]).toBeTruthy();
    expect(ws().dockRightIds).toContain("shortcuts:aisidecar");
    // The outline pane is NOT the companion — no agent tabs appeared.
    expect(useCompanion.getState().tabs).toHaveLength(0);
  });

  it("the tree keys traverse body → section children (prefix o / u)", async () => {
    mountCockpit("/write/d-1");
    await screen.findAllByText("Intro section");
    key(document.body, "ctrl+b");
    key(document.body, "o");
    expect(tabs().trees.writing!.active_tab_id).toBe(
      childTabId("root:document:/write/d-1", "document", "section:s-1"),
    );
    key(document.body, "ctrl+b");
    key(document.body, "u");
    expect(tabs().trees.writing!.active_tab_id).toBe("root:document:/write/d-1");
  });
});
