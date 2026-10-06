/**
 * c5probe.test.tsx: AUDIT PROBES (scratch copy only, never committed).
 * Each test records an observed fact about the C5 slice at 0f4361e22.
 */
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { BrowserRouter, Route, Routes } from "react-router-dom";
import axe from "axe-core";

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

const DETAIL = {
  deliverable_id: "d-1", title: "The memo", deliverable_kind: "general_essay", status: "draft",
  investigation_root_id: "inv-1",
  sections: [
    { section_id: "s-1", deliverable_id: "d-1", parent_section_id: null, section_index: 0, title: "Intro section", prose_text: null, prose_provenance: null, block_count: 2 },
    { section_id: "s-2", deliverable_id: "d-1", parent_section_id: null, section_index: 1, title: "Body section", prose_text: null, prose_provenance: null, block_count: 1 },
  ],
};
const DETAIL3 = {
  ...DETAIL,
  sections: [
    ...DETAIL.sections,
    { section_id: "s-3", deliverable_id: "d-1", parent_section_id: null, section_index: 2, title: "Third section", prose_text: null, prose_provenance: null, block_count: 1 },
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
  "s-3": [
    { outline_block_id: "b-4", section_id: "s-3", block_kind: "insight", provenance_kind: "graph_node", node_id: "n-4", content: "delta claim", node_label: null, block_index: 0, is_user_originated: false },
  ],
};

const h = vi.hoisted(() => ({
  apiFetchMock: vi.fn(),
  getDeliverableMock: vi.fn(),
  listInvestigationsMock: vi.fn(),
  getSectionBlocksMock: vi.fn(),
  searchRepositoryMock: vi.fn(),
  listFoldersMock: vi.fn(),
  generateSectionMock: vi.fn(),
  updateSectionProseMock: vi.fn(),
  createSectionMock: vi.fn(),
  editorHolder: { current: null as null | { editor: unknown } },
  tierRef: { current: "xl" as string },
}));

vi.mock("../lib/api", async (orig) => ({
  ...(await orig<typeof import("../lib/api")>()),
  apiFetch: h.apiFetchMock,
  getDeliverable: h.getDeliverableMock,
  listInvestigations: h.listInvestigationsMock,
  listDeliverables: vi.fn(async () => ({ count: 0, deliverables: [] })),
  postTypedEvent: vi.fn(() => Promise.resolve({ event_id: "e" })),
  updateSectionProse: h.updateSectionProseMock,
  createSection: h.createSectionMock,
}));
vi.mock("../modes/Write/writeApi", async (orig) => ({
  ...(await orig<typeof import("../modes/Write/writeApi")>()),
  getSectionBlocks: h.getSectionBlocksMock,
  searchRepository: h.searchRepositoryMock,
  listFolders: h.listFoldersMock,
  generateSection: h.generateSectionMock,
}));
vi.mock("@tiptap/react", async (orig) => {
  const actual = await orig<typeof import("@tiptap/react")>();
  return {
    ...actual,
    useEditor: (options: unknown, deps?: unknown) => {
      const ed = (actual.useEditor as (o: unknown, d?: unknown) => unknown)(options, deps);
      if (ed) h.editorHolder.current = { editor: ed };
      return ed;
    },
  };
});
vi.mock("./useViewportTier", () => ({ useViewportTier: () => h.tierRef.current }));

import { ACTIONS, KEYMAP } from "../components/hotkeys/keymap";
import { prefixState } from "../components/hotkeys/prefixState";
import WriteHome from "../modes/Write/WriteHome";
import { PanelLayout } from "./PanelLayout";
import { useBlockSources } from "./blockSources";
import { useCompanion } from "./companionStore";
import { useTabTrees } from "./tabTreeStore";
import { useWorkspace } from "./WorkspaceStore";
import { WRITE_OUTLINE_PANEL_ID, useWriteOutline } from "./writeOutlineStore";
import { childTabId } from "./documentSpace";
import { installShortcuts } from "./shortcuts";
import { openDocumentInLeftPane } from "./crossPane";
import { pinPlatform, press, unpinPlatform } from "./keymapTestKit";

let uninstall: (() => void) | null = null;
const ws = () => useWorkspace.getState();
const tabs = () => useTabTrees.getState();
const outline = () => useWriteOutline.getState();
const BODY = "root:document:/write/d-1";
const SEC = (s: string) => childTabId(BODY, "document", `section:${s}`);

function key(target: EventTarget, spec: string) {
  act(() => { press(target, spec, "mac"); });
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
            <Route path="/read/:documentId" element={<p>reader surface</p>} />
          </Routes>
        }
      />
    </BrowserRouter>,
  );
}
function go(path: string) {
  act(() => {
    window.history.pushState({}, "", path);
    window.dispatchEvent(new PopStateEvent("popstate"));
  });
}

beforeEach(() => {
  pinPlatform("mac");
  h.tierRef.current = "xl";
  h.apiFetchMock.mockReset().mockImplementation(() =>
    Promise.resolve({ ok: false, status: 404, json: async () => ({}), text: async () => "" }));
  h.getDeliverableMock.mockReset().mockImplementation(async (id: string) => (id === "d-1" ? DETAIL : null));
  h.listInvestigationsMock.mockReset().mockResolvedValue({ count: 0, investigations: [] });
  h.getSectionBlocksMock.mockReset().mockImplementation(async (sid: string) => BLOCKS[sid] ?? []);
  h.searchRepositoryMock.mockReset().mockResolvedValue([]);
  h.listFoldersMock.mockReset().mockResolvedValue({ folders: [] });
  h.generateSectionMock.mockReset().mockResolvedValue({ status: "generated", section_id: "s-1", prose_text: "Draft prose from the blocks." });
  h.updateSectionProseMock.mockReset().mockResolvedValue({});
  h.createSectionMock.mockReset().mockResolvedValue({ section_id: "s-3" });
  h.editorHolder.current = null;
  ws().reset(); ws().setLayoutPreset("docked");
  tabs().resetTabTrees(); outline().reset(); useBlockSources.getState().reset(); useCompanion.getState().reset();
  uninstall = installShortcuts(vi.fn() as never);
});
afterEach(() => {
  uninstall?.(); uninstall = null; cleanup(); prefixState.disarm();
  ws().reset(); ws().setLayoutPreset("docked");
  tabs().resetTabTrees(); outline().reset(); useBlockSources.getState().reset(); useCompanion.getState().reset();
  unpinPlatform(); document.body.innerHTML = "";
  window.history.replaceState({}, "", "/");
  window.localStorage.removeItem("antiek.workspace.layout-preset");
});

describe("C5 audit probes", () => {
  it("P1 strip labels + bridge copy for body and section tabs", async () => {
    mountCockpit("/write/d-1");
    await screen.findAllByText("Intro section");
    await waitFor(() => expect(tabs().trees.writing?.nodes[SEC("s-2")]).toBeTruthy());
    const strip = () => document.querySelector("[data-document-strip]")!.textContent;
    console.log("P1 body-active strip text:", JSON.stringify(strip()));
    act(() => { tabs().activateTab("writing", SEC("s-2")); });
    await waitFor(() => expect(strip()).toContain("1.2"));
    console.log("P1 section-active strip text:", JSON.stringify(strip()));
    console.log("P1 bridge node:", document.querySelector("[data-tab-bridge]")?.getAttribute("title"));
  });

  it("P2 right-pane block tabs after a section with a block is added via the outline", async () => {
    mountCockpit("/write/d-1");
    await screen.findAllByText("alpha claim");
    h.getDeliverableMock.mockImplementation(async (id: string) => (id === "d-1" ? DETAIL3 : null));
    const main = document.querySelector("main")!;
    const input = within(main as HTMLElement).getByPlaceholderText(/Add section #3/);
    fireEvent.change(input, { target: { value: "Third section" } });
    fireEvent.submit(input.closest("form")!);
    await within(main as HTMLElement).findAllByText("delta claim");
    await waitFor(() => expect(tabs().trees.writing?.nodes[SEC("s-3")]).toBeTruthy());
    await new Promise((r) => setTimeout(r, 300));
    const right = document.querySelector<HTMLElement>('[data-pane="right"]')!;
    console.log("P2 left tree has 1.3:", tabs().trees.writing!.nodes[SEC("s-3")].hier_number);
    console.log("P2 right block tabs:", [...right.querySelectorAll("[data-block-tab]")].map((e) => e.getAttribute("data-block-tab")));
    console.log("P2 outline store blockIds:", outline().blockIds);
    console.log("P2 getDeliverable calls:", h.getDeliverableMock.mock.calls.length);
  });

  it("P3/P4 NewSectionForm + section number inside a section tab", async () => {
    mountCockpit("/write/d-1");
    await screen.findAllByText("gamma claim");
    await waitFor(() => expect(tabs().trees.writing?.nodes[SEC("s-2")]).toBeTruthy());
    act(() => { tabs().activateTab("writing", SEC("s-2")); });
    const main = document.querySelector("main")! as HTMLElement;
    await waitFor(() => expect(within(main).queryByText("Intro section")).toBeNull());
    const h3 = main.querySelector("h3")!;
    console.log("P4 section heading in tab 1.2:", JSON.stringify(h3.textContent));
    const input = within(main).getByPlaceholderText(/Add section #/);
    console.log("P3 placeholder:", input.getAttribute("placeholder"));
    fireEvent.change(input, { target: { value: "Inserted" } });
    fireEvent.submit(input.closest("form")!);
    await waitFor(() => expect(h.createSectionMock).toHaveBeenCalled());
    console.log("P3 createSection args:", JSON.stringify(h.createSectionMock.mock.calls[0][0]),
      "existing indices:", DETAIL.sections.map((s) => s.section_index));
  });

  it("P5 control: an edit in the body tab persists after the debounce", async () => {
    mountCockpit("/write/d-1");
    await screen.findAllByText("alpha claim");
    const main = document.querySelector("main")! as HTMLElement;
    fireEvent.click(within(main).getAllByRole("button", { name: /generate draft/i })[0]);
    await waitFor(() => expect(main.querySelector(".ProseMirror")).toBeTruthy());
    await act(async () => { (h.editorHolder.current!.editor as { commands: { insertContent: (t: string) => void } }).commands.insertContent("Sharpened. "); });
    await new Promise((r) => setTimeout(r, 1500));
    console.log("P5-control updateSectionProse calls:", h.updateSectionProseMock.mock.calls.length);
  });

  it("P5 an edit made just before switching to a section tab, and the editor after returning", async () => {
    mountCockpit("/write/d-1");
    await screen.findAllByText("alpha claim");
    await waitFor(() => expect(tabs().trees.writing?.nodes[SEC("s-2")]).toBeTruthy());
    const main = document.querySelector("main")! as HTMLElement;
    fireEvent.click(within(main).getAllByRole("button", { name: /generate draft/i })[0]);
    await waitFor(() => expect(main.querySelector(".ProseMirror")).toBeTruthy());
    await act(async () => { (h.editorHolder.current!.editor as { commands: { insertContent: (t: string) => void } }).commands.insertContent("Sharpened. "); });
    act(() => { tabs().activateTab("writing", SEC("s-2")); });
    await new Promise((r) => setTimeout(r, 1500));
    console.log("P5 updateSectionProse calls after tab switch:", h.updateSectionProseMock.mock.calls.length);
    act(() => { tabs().activateTab("writing", BODY); });
    await within(main).findAllByText("Intro section");
    await new Promise((r) => setTimeout(r, 200));
    console.log("P5 editor present after returning to body tab:", Boolean(main.querySelector(".ProseMirror")));
  });

  it("P6 prefix n/p move among section tabs and scope the view", async () => {
    mountCockpit("/write/d-1");
    await screen.findAllByText("Intro section");
    await waitFor(() => expect(tabs().trees.writing?.nodes[SEC("s-2")]).toBeTruthy());
    const main = document.querySelector("main")! as HTMLElement;
    key(document.body, "ctrl+b"); key(document.body, "o");
    key(document.body, "ctrl+b"); key(document.body, "n");
    console.log("P6 active after o,n:", tabs().trees.writing!.active_tab_id);
    await waitFor(() => expect(within(main).queryByText("Intro section")).toBeNull());
    console.log("P6 main shows Body only:", within(main).queryAllByText("Body section").length > 0);
    key(document.body, "ctrl+alt+[");
    console.log("P6 active after chord prev:", tabs().trees.writing!.active_tab_id);
  });

  it("P7 a piece with sections but zero blocks", async () => {
    h.getSectionBlocksMock.mockImplementation(async () => []);
    mountCockpit("/write/d-1");
    await screen.findAllByText("Intro section");
    await new Promise((r) => setTimeout(r, 300));
    const right = document.querySelector<HTMLElement>('[data-pane="right"]')!;
    console.log("P7 right pane text:", JSON.stringify(right.querySelector("[data-write-outline]")!.textContent));
  });

  it("P8 docked outline panel after leaving the write route", async () => {
    mountCockpit("/write/d-1", "docked");
    await screen.findAllByText("Intro section");
    expect(ws().panels[WRITE_OUTLINE_PANEL_ID]).toBeTruthy();
    go("/inv/inv-1");
    await screen.findAllByText("investigation surface");
    console.log("P8 outline panel still open on /inv:", Boolean(ws().panels[WRITE_OUTLINE_PANEL_ID]),
      "text:", JSON.stringify(document.querySelector("[data-write-outline]")?.textContent ?? null));
  });

  it("P9 reader-tab drag source reachability in writing mode", async () => {
    mountCockpit("/write/d-1");
    await screen.findAllByText("alpha claim");
    const strip = document.querySelector("[data-document-strip]")!;
    console.log("P9 draggable tabs in writing strip:", strip.querySelectorAll('[draggable="true"]').length);
    await act(async () => { openDocumentInLeftPane("doc-9", { from: "probe" }); await new Promise((r) => setTimeout(r, 50)); });
    await waitFor(() => expect(window.location.pathname).toBe("/read/doc-9"));
    const right = document.querySelector<HTMLElement>('[data-pane="right"]')!;
    console.log("P9 after open: path", window.location.pathname,
      "outline pane:", Boolean(right.querySelector("[data-write-outline]")),
      "companion:", Boolean(right.querySelector("[data-companion-pane]")));
  });

  it("P10 key sheet labels for the ,/. rows and Write-specific rows", () => {
    const rows = KEYMAP.filter((r) => r.action === "companion.nextTab" || r.action === "companion.prevTab");
    console.log("P10 rows:", rows.map((r) => `${r.id}=${r.prefixKey ?? r.chord}`).join(","),
      "labels:", ACTIONS["companion.nextTab"].label, "|", ACTIONS["companion.prevTab"].label);
    const writeish = Object.entries(ACTIONS).filter(([k, v]) => /block|section|outline|write/i.test(k + v.label));
    console.log("P10 write/block/section actions:", JSON.stringify(writeish));
  });

  it("P11 axe over the Write right pane", async () => {
    mountCockpit("/write/d-1");
    await screen.findAllByText("alpha claim");
    const right = document.querySelector<HTMLElement>("[data-write-outline]")!;
    const res = await axe.run(right, { rules: { "color-contrast": { enabled: false } } });
    console.log("P11 axe violations:", JSON.stringify(res.violations.map((v) => ({ id: v.id, impact: v.impact, n: v.nodes.length, target: v.nodes.slice(0, 2).map((n) => n.target) }))));
    const tab = right.querySelector<HTMLElement>('[data-block-tab="b-1"]')!;
    console.log("P11 tab attrs:", tab.getAttribute("aria-controls"), tab.getAttribute("tabindex"),
      "tabpanels:", right.querySelectorAll('[role="tabpanel"]').length);
  });

  it("P12 persisted prose in the body tab on a fresh load", async () => {
    const withProse = { ...DETAIL, sections: DETAIL.sections.map((sec, i) => ({ ...sec, prose_text: i === 0 ? "Persisted body prose sentence one. Sentence two." : "Second section persisted prose." })) };
    h.getDeliverableMock.mockImplementation(async (id: string) => (id === "d-1" ? withProse : null));
    mountCockpit("/write/d-1");
    await screen.findAllByText("alpha claim");
    await new Promise((r) => setTimeout(r, 300));
    const main = document.querySelector("main")! as HTMLElement;
    console.log("P12 body tab shows persisted prose:", (main.textContent ?? "").includes("Persisted body prose"),
      "editor mounted:", Boolean(main.querySelector(".ProseMirror")),
      "X-ray toggles:", within(main).queryAllByRole("button", { name: "X-ray" }).length);
  });

  it("P14 close a section tab, then any outline refresh", async () => {
    mountCockpit("/write/d-1");
    await screen.findAllByText("alpha claim");
    await waitFor(() => expect(tabs().trees.writing?.nodes[SEC("s-2")]).toBeTruthy());
    act(() => { tabs().activateTab("writing", SEC("s-1")); });
    key(document.body, "ctrl+b"); key(document.body, "c");
    console.log("P14 after close: s-1 present?", Boolean(tabs().trees.writing!.nodes[SEC("s-1")]));
    h.getDeliverableMock.mockImplementation(async (id: string) => (id === "d-1" ? DETAIL3 : null));
    act(() => { tabs().activateTab("writing", BODY); });
    const main = document.querySelector("main")! as HTMLElement;
    await within(main).findAllByText("Intro section");
    const input = within(main).getByPlaceholderText(/Add section #3/);
    fireEvent.change(input, { target: { value: "Third section" } });
    fireEvent.submit(input.closest("form")!);
    await waitFor(() => expect(tabs().trees.writing?.nodes[SEC("s-3")]).toBeTruthy());
    await new Promise((r) => setTimeout(r, 100));
    const t = tabs().trees.writing!;
    console.log("P14 body children after refresh:", JSON.stringify(t.nodes[BODY].child_order.map((id) => [t.nodes[id].ref, t.nodes[id].hier_number])));
  });
});
