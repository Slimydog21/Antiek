/**
 * WriteOutlinePane.keyboard.test.tsx — the keyboard path for source
 * assignment (the DnD keyboard alternative, WCAG 2.5.7 discipline).
 *
 * A focused outline block tab's `a` opens the in-pane source picker (the
 * same candidates the drag carries: open reader tabs + repository hits that
 * name a source document), typing filters, the arrows walk, Enter assigns
 * through the SAME callback a drop uses, and Esc — a transient overlay, one
 * Esc one handler — closes and returns focus to the tab. `x` / Delete on a
 * focused tab removes the block's most recent assignment. The plain letters
 * stand down for IME composition, modifiers, editable targets, and an armed
 * keymap prefix.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";

import type { SectionResponse } from "../lib/api";
import type { OutlineBlockView, RepositoryHit } from "../modes/Write/writeApi";
import { prefixState } from "../components/hotkeys/prefixState";
import WriteOutlinePane from "./WriteOutlinePane";
import { useBlockSources } from "./blockSources";
import { resetTabTitles, setTabTitle } from "./tabTitles";
import { useTabTrees } from "./tabTreeStore";
import type { TabTree } from "./tabTree";
import { useWriteOutline } from "./writeOutlineStore";

const { getDeliverableMock, getSectionBlocksMock, searchRepositoryMock } = vi.hoisted(() => ({
  getDeliverableMock: vi.fn(),
  getSectionBlocksMock: vi.fn(),
  searchRepositoryMock: vi.fn(),
}));

vi.mock("../lib/api", async (orig) => ({
  ...(await orig<typeof import("../lib/api")>()),
  getDeliverable: getDeliverableMock,
}));

vi.mock("../modes/Write/writeApi", async (orig) => ({
  ...(await orig<typeof import("../modes/Write/writeApi")>()),
  getSectionBlocks: getSectionBlocksMock,
  searchRepository: searchRepositoryMock,
}));

const SECTION: SectionResponse = {
  section_id: "s-1",
  deliverable_id: "d-1",
  parent_section_id: null,
  section_index: 0,
  title: "The question",
  prose_text: null,
  prose_provenance: null,
  block_count: 2,
};

const blocks: OutlineBlockView[] = [0, 1].map((index) => ({
  outline_block_id: `b-${index}`,
  section_id: SECTION.section_id,
  block_kind: "insight",
  provenance_kind: "graph_node",
  node_id: `n-${index}`,
  content: null,
  node_label: `Block ${index}`,
  block_index: index,
  is_user_originated: false,
}));

const HIT: RepositoryHit = {
  node_id: "n-hit",
  label: "a claim about finches",
  node_type: "claim",
  source_tier: 2,
  document_id: "doc-source",
  document_title: "The Source Book",
  score: 1,
};

/** A reading tree with one open reader tab — the drag origin SiblingStrip
 *  renders, seeded straight into the existing store. */
const READING_TREE: TabTree = {
  mothership: "reading",
  nodes: {
    "tab-1": {
      tab_id: "tab-1",
      parent_tab_id: null,
      hier_number: "1",
      child_order: [],
      kind: "reader",
      ref: "doc-open",
      mothership: "reading",
      public_number: 1,
      side: "left",
    },
  },
  root_order: ["tab-1"],
  active_tab_id: "tab-1",
  history: {},
  next_root_index: 2,
  next_child_index: {},
  version: 0,
};

async function mountPane() {
  const view = render(
    <MemoryRouter initialEntries={["/write/d-1"]}>
      <Routes>
        <Route path="/write/:deliverableId" element={<WriteOutlinePane />} />
      </Routes>
    </MemoryRouter>,
  );
  await waitFor(() => expect(document.querySelector('[data-block-tab="b-1"]')).not.toBeNull());
  return view;
}

function blockTab(blockId: string): HTMLElement {
  return document.querySelector<HTMLElement>(`[data-block-tab="${blockId}"]`)!;
}

function seedReaderTab() {
  act(() => {
    useTabTrees.setState((s) => ({ trees: { ...s.trees, reading: READING_TREE } }));
    setTabTitle("reader", "doc-open", "The Open Book");
  });
}

function pressOn(target: Element | Document | Window, init: KeyboardEventInit) {
  act(() => {
    fireEvent.keyDown(target, init);
  });
}

/** jsdom's KeyboardEvent ignores `isComposing` in its init dict, so a
 *  composition keypress is built by hand. */
function pressComposing(target: EventTarget, key: string) {
  const e = new KeyboardEvent("keydown", { key, bubbles: true, cancelable: true });
  Object.defineProperty(e, "isComposing", { value: true });
  act(() => {
    target.dispatchEvent(e);
  });
}

beforeEach(() => {
  getDeliverableMock.mockReset().mockResolvedValue({
    deliverable_id: "d-1",
    title: "The piece",
    deliverable_kind: "general_essay",
    status: "draft",
    investigation_root_id: "inv-1",
    sections: [SECTION],
  });
  getSectionBlocksMock.mockReset().mockResolvedValue(blocks);
  searchRepositoryMock.mockReset().mockResolvedValue([HIT]);
});

afterEach(() => {
  cleanup();
  prefixState.disarm();
  useWriteOutline.getState().reset();
  useBlockSources.getState().reset();
  useTabTrees.getState().resetTabTrees();
  resetTabTitles();
});

describe("the keyboard assignment path (a on a block tab)", () => {
  it("opens the picker with focus in its filter, and Enter assigns through the drop's write path", async () => {
    seedReaderTab();
    await mountPane();
    const tab = blockTab("b-1");
    act(() => tab.focus());
    pressOn(tab, { key: "a" });

    // The picker opened, named by its block, focus in the filter.
    const picker = document.querySelector<HTMLElement>("[data-source-picker]")!;
    expect(picker).not.toBeNull();
    expect(picker.getAttribute("aria-label")).toContain("Block 1");
    const filter = screen.getByLabelText("Filter source documents");
    expect(document.activeElement).toBe(filter);

    // Both drag origins are listed: the open reader tab and (after the
    // debounced search) the repository hit.
    expect(await screen.findByRole("option", { name: /The Open Book/ })).toBeTruthy();
    const repoOption = await screen.findByRole("option", { name: /The Source Book/ });

    // ArrowDown leaves the filter for the list, the arrows walk it, Enter
    // assigns the focused option.
    pressOn(filter, { key: "ArrowDown" });
    expect(document.activeElement).toBe(screen.getByRole("option", { name: /The Open Book/ }));
    pressOn(document.activeElement!, { key: "ArrowDown" });
    expect(document.activeElement).toBe(repoOption);
    pressOn(repoOption, { key: "Enter" });

    // The SAME assignment a drop lands: the record, the active block, the
    // card's list row, the tab's count — and focus back on the block's tab.
    const record = useBlockSources.getState().records["d-1"]?.["b-1"] ?? [];
    expect(record).toHaveLength(1);
    expect(record[0]).toMatchObject({ document_id: "doc-source", document_title: "The Source Book" });
    expect(useWriteOutline.getState().activeBlockId).toBe("b-1");
    expect(document.querySelector("[data-source-picker]")).toBeNull();
    expect(document.activeElement).toBe(tab);
    expect(document.querySelector("[data-assigned-sources]")!.textContent).toContain("The Source Book");
    expect(blockTab("b-1").textContent).toContain("·1");
  });

  it("typing filters: the repository search is asked with the text and the open tabs narrow client-side", async () => {
    seedReaderTab();
    await mountPane();
    pressOn(blockTab("b-0"), { key: "a" });
    const filter = screen.getByLabelText("Filter source documents");
    await screen.findByRole("option", { name: /The Open Book/ });
    await screen.findByRole("option", { name: /The Source Book/ });

    fireEvent.change(filter, { target: { value: "finch" } });
    // The open tab no longer matches; the search is asked with the needle
    // (debounced, like the shelf's) and its hit stays.
    await waitFor(() =>
      expect(searchRepositoryMock).toHaveBeenCalledWith(expect.objectContaining({ q: "finch" })),
    );
    await waitFor(() =>
      expect(screen.queryByRole("option", { name: /The Open Book/ })).toBeNull(),
    );
    expect(screen.getByRole("option", { name: /The Source Book/ })).toBeTruthy();

    // Enter in the filter assigns the top match without leaving it.
    pressOn(filter, { key: "Enter" });
    const record = useBlockSources.getState().records["d-1"]?.["b-0"] ?? [];
    expect(record.map((r) => r.document_id)).toEqual(["doc-source"]);
  });

  it("Esc closes the overlay and returns focus to the block tab; a hidden pane leaves Esc alone", async () => {
    const view = await mountPane();
    const tab = blockTab("b-1");
    act(() => tab.focus());
    pressOn(tab, { key: "a" });
    expect(document.querySelector("[data-source-picker]")).not.toBeNull();

    const esc = new KeyboardEvent("keydown", { key: "Escape", bubbles: true, cancelable: true });
    act(() => {
      document.dispatchEvent(esc);
    });
    expect(esc.defaultPrevented).toBe(true);
    expect(document.querySelector("[data-source-picker]")).toBeNull();
    expect(document.activeElement).toBe(tab);

    // Reopened inside a hidden pane, the overlay is not the active layer:
    // it must not eat Escape (A1c low 11).
    pressOn(tab, { key: "a" });
    expect(document.querySelector("[data-source-picker]")).not.toBeNull();
    view.container.hidden = true;
    const hiddenEsc = new KeyboardEvent("keydown", { key: "Escape", bubbles: true, cancelable: true });
    act(() => {
      document.dispatchEvent(hiddenEsc);
    });
    expect(hiddenEsc.defaultPrevented).toBe(false);
    expect(document.querySelector("[data-source-picker]")).not.toBeNull();
  });

  it("the plain letters stand down for IME composition, modifiers, and an armed prefix", async () => {
    await mountPane();
    const tab = blockTab("b-0");
    act(() => tab.focus());

    pressComposing(tab, "a");
    expect(document.querySelector("[data-source-picker]")).toBeNull();
    pressOn(tab, { key: "a", ctrlKey: true });
    pressOn(tab, { key: "a", metaKey: true });
    pressOn(tab, { key: "a", altKey: true });
    expect(document.querySelector("[data-source-picker]")).toBeNull();

    act(() => prefixState.arm());
    pressOn(tab, { key: "a" });
    expect(document.querySelector("[data-source-picker]")).toBeNull();
    act(() => prefixState.disarm());

    // And an editable target inside the pane is never robbed of the letter.
    const pane = document.querySelector<HTMLElement>("[data-write-outline]")!;
    const input = document.createElement("input");
    pane.appendChild(input);
    pressOn(input, { key: "a" });
    expect(document.querySelector("[data-source-picker]")).toBeNull();
    input.remove();

    pressOn(tab, { key: "a" });
    expect(document.querySelector("[data-source-picker]")).not.toBeNull();
  });

  it("the block tabs advertise the pane-scoped keys", async () => {
    await mountPane();
    expect(blockTab("b-0").getAttribute("aria-keyshortcuts")).toBe("A X Delete");
  });
});

describe("x / Delete on a focused block tab", () => {
  it("removes the block's most recent assignment; a bare block is a quiet no-op", async () => {
    await mountPane();
    act(() => {
      const s = useBlockSources.getState();
      s.assign("d-1", "b-0", { document_id: "doc-1", document_title: "First" });
      s.assign("d-1", "b-0", { document_id: "doc-2", document_title: "Second" });
    });
    const tab = blockTab("b-0");
    act(() => tab.focus());

    pressOn(tab, { key: "x" });
    expect(
      (useBlockSources.getState().records["d-1"]?.["b-0"] ?? []).map((r) => r.document_id),
    ).toEqual(["doc-1"]);

    pressOn(tab, { key: "Delete" });
    expect(useBlockSources.getState().records["d-1"]?.["b-0"] ?? []).toHaveLength(0);

    // Nothing to remove: no error, no state change, no picker.
    pressOn(tab, { key: "x" });
    expect(useBlockSources.getState().records["d-1"]?.["b-0"] ?? []).toHaveLength(0);
    expect(document.querySelector("[data-source-picker]")).toBeNull();

    // The guards hold for removal too.
    act(() => {
      useBlockSources.getState().assign("d-1", "b-0", { document_id: "doc-3", document_title: "Third" });
    });
    pressComposing(tab, "x");
    expect(useBlockSources.getState().records["d-1"]?.["b-0"]).toHaveLength(1);
  });
});
