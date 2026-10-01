/**
 * cockpitSweepV2.write.test.tsx — lane A stage B1, F-02 from Antiek Sweep
 * v2's forensic audit: "never losing an edit on a tab switch". Kept from the
 * executed probe cockpit/probes/c5-write.probe.test.tsx ("P5 an edit made
 * just before switching to a section tab, and the editor after returning",
 * with its P5 control), with the probe's setup, asserting the correct
 * behaviour: a section-tab switch neither drops the pending (debounced)
 * save nor removes the editor. A section tab SCOPES the piece's view; every
 * section stays mounted underneath, so its draft, editor and debounce live
 * through the switch.
 */
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
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
    { section_id: "s-1", deliverable_id: "d-1", parent_section_id: null, section_index: 0, title: "Intro section", prose_text: null, prose_provenance: null, block_count: 2 },
    { section_id: "s-2", deliverable_id: "d-1", parent_section_id: null, section_index: 1, title: "Body section", prose_text: null, prose_provenance: null, block_count: 1 },
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
// The probe's handle on the real TipTap editor, to type into it.
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

import { prefixState } from "../components/hotkeys/prefixState";
import WriteHome from "../modes/Write/WriteHome";
import { setSectionProseOwner } from "../modes/Write/sectionProseOwner";
import { PanelLayout } from "./PanelLayout";
import { useBlockSources } from "./blockSources";
import { useCompanion } from "./companionStore";
import { installShortcuts } from "./shortcuts";
import { tabIdOf } from "./tabTestKit";
import { useTabTrees } from "./tabTreeStore";
import { useWorkspace } from "./WorkspaceStore";
import { useWriteOutline } from "./writeOutlineStore";
import { pinPlatform, unpinPlatform } from "./keymapTestKit";

let uninstall: (() => void) | null = null;
const ws = () => useWorkspace.getState();
const tabs = () => useTabTrees.getState();
/** The piece's body tab and its section tabs, found by what they show
 *  (tab ids are opaque). Each throws until the tab is open. */
const BODY = () => tabIdOf(tabs().trees.writing!, "document", "/write/d-1");
const SEC = (s: string) => tabIdOf(tabs().trees.writing!, "document", `section:${s}`, BODY());

function mountCockpit(path: string) {
  window.history.replaceState({}, "", path);
  ws().setLayoutPreset("omarchy-inset");
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

const isVisible = (el: Element | null): boolean => el !== null && el.closest("[hidden]") === null;
/** Elements whose text is `text` that a sighted user can see in `root`. */
const visibleText = (root: HTMLElement, text: string) => within(root).queryAllByText(text).filter(isVisible);

function typeIntoEditor(text: string) {
  return act(async () => {
    (h.editorHolder.current!.editor as { commands: { insertContent: (t: string) => void } }).commands.insertContent(text);
  });
}

async function generateFirstDraft(main: HTMLElement) {
  fireEvent.click(within(main).getAllByRole("button", { name: /generate draft/i })[0]);
  await waitFor(() => expect(main.querySelector(".ProseMirror")).toBeTruthy());
}

beforeEach(() => {
  // This focused cockpit fixture mounts below AuthProvider.
  setSectionProseOwner(null);
  setSectionProseOwner("cockpit-sweep-writer");
  pinPlatform("mac");
  h.tierRef.current = "xl";
  h.apiFetchMock.mockReset().mockImplementation(() =>
    Promise.resolve({ ok: false, status: 404, json: async () => ({}), text: async () => "" }),
  );
  h.getDeliverableMock.mockReset().mockImplementation(async (id: string) => (id === "d-1" ? DETAIL : null));
  h.listInvestigationsMock.mockReset().mockResolvedValue({ count: 0, investigations: [] });
  h.getSectionBlocksMock.mockReset().mockImplementation(async (sid: string) => BLOCKS[sid] ?? []);
  h.searchRepositoryMock.mockReset().mockResolvedValue([]);
  h.listFoldersMock.mockReset().mockResolvedValue({ folders: [] });
  h.generateSectionMock.mockReset().mockResolvedValue({
    status: "generated",
    section_id: "s-1",
    prose_text: "Draft prose from the blocks.",
  });
  h.updateSectionProseMock.mockReset().mockResolvedValue({});
  h.createSectionMock.mockReset().mockResolvedValue({ section_id: "s-3" });
  h.editorHolder.current = null;
  ws().reset();
  ws().setLayoutPreset("docked");
  tabs().resetTabTrees();
  useWriteOutline.getState().reset();
  useBlockSources.getState().reset();
  useCompanion.getState().reset();
  uninstall = installShortcuts(vi.fn() as never);
});

afterEach(() => {
  act(() => { setSectionProseOwner(null); });
  uninstall?.();
  uninstall = null;
  cleanup();
  prefixState.disarm();
  ws().reset();
  ws().setLayoutPreset("docked");
  tabs().resetTabTrees();
  useWriteOutline.getState().reset();
  useBlockSources.getState().reset();
  useCompanion.getState().reset();
  unpinPlatform();
  document.body.innerHTML = "";
  window.history.replaceState({}, "", "/");
  window.localStorage.removeItem("antiek.workspace.layout-preset");
});

describe("F-02 — a section-tab switch never loses an edit", () => {
  it("P5 control: an edit in the body tab persists after the debounce", async () => {
    mountCockpit("/write/d-1");
    await screen.findAllByText("alpha claim");
    const main = document.querySelector("main")! as HTMLElement;
    await generateFirstDraft(main);
    await typeIntoEditor("Sharpened. ");
    await waitFor(() => expect(h.updateSectionProseMock).toHaveBeenCalledTimes(1), { timeout: 2000 });
    expect(h.updateSectionProseMock.mock.calls[0][0]).toBe("s-1");
    expect(h.updateSectionProseMock.mock.calls[0][1].prose_text).toContain("Sharpened.");
  });

  it("P5 an edit made just before switching to a section tab is saved, and the editor is there on return", async () => {
    mountCockpit("/write/d-1");
    await screen.findAllByText("alpha claim");
    await waitFor(() => expect(tabs().trees.writing?.nodes[SEC("s-2")]).toBeTruthy());
    const main = document.querySelector("main")! as HTMLElement;
    await generateFirstDraft(main);
    await typeIntoEditor("Sharpened. ");
    act(() => {
      tabs().activateTab("writing", SEC("s-2"));
    });
    await waitFor(() => expect(h.updateSectionProseMock).toHaveBeenCalledTimes(1), { timeout: 2000 });
    expect(h.updateSectionProseMock.mock.calls[0][0]).toBe("s-1");
    expect(h.updateSectionProseMock.mock.calls[0][1].prose_text).toContain("Sharpened.");
    // The section tab shows its section alone.
    expect(visibleText(main, "Intro section")).toEqual([]);
    expect(visibleText(main, "Body section").length).toBeGreaterThan(0);
    act(() => {
      tabs().activateTab("writing", BODY());
    });
    await waitFor(() => expect(visibleText(main, "Intro section").length).toBeGreaterThan(0));
    const editor = main.querySelector(".ProseMirror");
    expect(isVisible(editor)).toBe(true);
    expect(editor!.textContent).toContain("Sharpened.");
  });

  it("a section tab numbers its section truly and adds the next section after the last", async () => {
    mountCockpit("/write/d-1");
    await screen.findAllByText("gamma claim");
    await waitFor(() => expect(tabs().trees.writing?.nodes[SEC("s-2")]).toBeTruthy());
    act(() => {
      tabs().activateTab("writing", SEC("s-2"));
    });
    const main = document.querySelector("main")! as HTMLElement;
    await waitFor(() => expect(visibleText(main, "Intro section")).toEqual([]));
    const heading = Array.from(main.querySelectorAll("h3")).find(isVisible)!;
    expect(heading.textContent).toContain("2.");
    const input = within(main).getByPlaceholderText(/Add section #/);
    expect(input.getAttribute("placeholder")).toContain("#3");
  });
});
