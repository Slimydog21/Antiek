/**
 * A1c low 11 negative controls for the outline block overflow menu.
 *
 * A menu mounted in a hidden pane is not the active layer: it must leave
 * Escape for that layer. A visible menu remains transient and closes on
 * Escape, returning focus to its trigger.
 */
import { afterEach, describe, expect, it, vi } from "vitest";
import { act, cleanup, fireEvent, render, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";

import type { SectionResponse } from "../lib/api";
import type { OutlineBlockView } from "../modes/Write/writeApi";
import WriteOutlinePane from "./WriteOutlinePane";
import { useBlockSources } from "./blockSources";
import { useWriteOutline } from "./writeOutlineStore";

const { getDeliverableMock, getSectionBlocksMock } = vi.hoisted(() => ({
  getDeliverableMock: vi.fn(),
  getSectionBlocksMock: vi.fn(),
}));

vi.mock("../lib/api", async (orig) => ({
  ...(await orig<typeof import("../lib/api")>()),
  getDeliverable: getDeliverableMock,
}));

vi.mock("../modes/Write/writeApi", async (orig) => ({
  ...(await orig<typeof import("../modes/Write/writeApi")>()),
  getSectionBlocks: getSectionBlocksMock,
}));

vi.mock("./stripOverflow", async (orig) => ({
  ...(await orig<typeof import("./stripOverflow")>()),
  useStripOverflow: () => ({ start: true, end: false, hiddenBefore: 1, hiddenAfter: 0 }),
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

async function mountPane() {
  const view = render(
    <MemoryRouter initialEntries={["/write/d-1"]}>
      <Routes>
        <Route path="/write/:deliverableId" element={<WriteOutlinePane />} />
      </Routes>
    </MemoryRouter>,
  );
  await waitFor(() => expect(document.querySelector("[data-block-overflow]")).not.toBeNull());
  return view;
}

afterEach(() => {
  cleanup();
  useWriteOutline.getState().reset();
  useBlockSources.getState().reset();
});

describe("A1c low 11: outline block overflow Escape layering", () => {
  it("a hidden pane leaves Escape for the active layer", async () => {
    getDeliverableMock.mockResolvedValue({
      deliverable_id: "d-1",
      title: "The piece",
      deliverable_kind: "general_essay",
      status: "draft",
      investigation_root_id: "inv-1",
      sections: [SECTION],
    });
    getSectionBlocksMock.mockResolvedValue(blocks);
    const view = await mountPane();
    const trigger = document.querySelector<HTMLButtonElement>("[data-block-overflow]")!;
    act(() => {
      fireEvent.click(trigger);
    });
    expect(document.querySelector("[role='menu']")).not.toBeNull();

    view.container.hidden = true;
    const event = new KeyboardEvent("keydown", { key: "Escape", bubbles: true, cancelable: true });
    act(() => {
      document.dispatchEvent(event);
    });
    expect(event.defaultPrevented).toBe(false);
    expect(document.querySelector("[role='menu']")).not.toBeNull();
  });

  it("a visible menu closes and returns focus to its trigger", async () => {
    getDeliverableMock.mockResolvedValue({
      deliverable_id: "d-1",
      title: "The piece",
      deliverable_kind: "general_essay",
      status: "draft",
      investigation_root_id: "inv-1",
      sections: [SECTION],
    });
    getSectionBlocksMock.mockResolvedValue(blocks);
    await mountPane();
    const trigger = document.querySelector<HTMLButtonElement>("[data-block-overflow]")!;
    act(() => {
      fireEvent.click(trigger);
    });
    expect(document.querySelector("[role='menu']")).not.toBeNull();

    act(() => {
      document.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true, cancelable: true }));
    });
    expect(document.querySelector("[role='menu']")).toBeNull();
    expect(document.activeElement).toBe(trigger);
  });
});
