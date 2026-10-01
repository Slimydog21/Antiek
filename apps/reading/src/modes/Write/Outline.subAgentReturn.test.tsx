import { setSectionProseOwner } from "./sectionProse";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";

import type { SectionResponse } from "../../lib/api";
import type { OutlineBlockView } from "./writeApi";

/**
 * Outline.subAgentReturn — F7: an accepted sub-agent spawn returns to its writer.
 *
 * `SubAgentProposal` PRODUCES the spawned child's id
 * (`onAccept(child.investigation_id)`). The host used to discard it
 * (`onAccept={() => setProposal(null)}`), so a writer who accepted a proposal
 * had paid for a child investigation and had no way back to it. The id is now
 * retained and rendered as a link to `/inv/<id>`, mirroring the Reading
 * companion's child-investigation row.
 *
 * The FloatMenu and SubAgentProposal components are stubbed: this test is about
 * the HOST's handling of the id the child component reports, not about either
 * component's internals (both have their own coverage).
 */

const { getSectionBlocksMock, updateSectionProseMock } = vi.hoisted(() => ({
  getSectionBlocksMock: vi.fn(),
  updateSectionProseMock: vi.fn(),
}));

vi.mock("./writeApi", async (orig) => ({
  ...(await orig<typeof import("./writeApi")>()),
  getSectionBlocks: getSectionBlocksMock,
  generateSection: vi.fn(),
  placeBlock: vi.fn(),
  moveBlock: vi.fn(),
}));

vi.mock("../../lib/api", async (orig) => ({
  ...(await orig<typeof import("../../lib/api")>()),
  createSection: vi.fn().mockResolvedValue({}),
  updateSectionProse: updateSectionProseMock,
  postTypedEvent: vi.fn().mockResolvedValue({}),
}));

vi.mock("../shared/FloatMenu/useFloatMenuSelection", () => ({
  useFloatMenuSelection: () => null,
}));

// The menu offers the rewrite intent; firing onDeepResearch is the shipped path
// that opens the proposal (Outline.tsx `onDeepResearch` → `setProposal`).
vi.mock("../shared/FloatMenu/FloatMenu", () => ({
  default: (props: { onDeepResearch?: (t: string | null) => void }) => (
    <button type="button" onClick={() => props.onDeepResearch?.("Capital intensity rises")}>
      deep research
    </button>
  ),
}));

// The proposal reports the spawned id exactly as the real component does.
vi.mock("./SubAgentProposal", () => ({
  default: (props: { onAccept: (id: string) => void }) => (
    <button type="button" data-testid="accept-proposal" onClick={() => props.onAccept("inv-child-123")}>
      accept proposal
    </button>
  ),
}));

vi.mock("@tiptap/react", async (orig) => ({
  ...(await orig<typeof import("@tiptap/react")>()),
  useEditor: () => null,
}));

import Outline from "./Outline";

function section(prose: string): SectionResponse {
  return {
    section_id: "sec-1",
    deliverable_id: "dlv-1",
    parent_section_id: null,
    section_index: 0,
    title: "Thesis",
    prose_text: prose,
    prose_provenance: {},
    block_count: 1,
  };
}

const BLOCK: OutlineBlockView = {
  outline_block_id: "oblk-1",
  section_id: "sec-1",
  block_kind: "insight",
  provenance_kind: "graph_node",
  node_id: "n1",
  content: null,
  node_label: "Capital intensity rises with scale",
  block_index: 0,
  is_user_originated: false,
};

beforeEach(() => {
  setSectionProseOwner(null);
  setSectionProseOwner("writing-test-owner");
  getSectionBlocksMock.mockReset().mockResolvedValue([BLOCK]);
  updateSectionProseMock.mockReset().mockResolvedValue({
    status: "saved",
    section_id: "sec-1",
    claim_node_id: null,
    claim_event_id: null,
  });
});
afterEach(() => {
  cleanup();
  setSectionProseOwner(null);
});

function renderOutline() {
  return render(
    <MemoryRouter>
      <Outline deliverableId="dlv-1" sections={[section("Body prose.")]} onChanged={vi.fn()} />
    </MemoryRouter>,
  );
}

describe("Outline — F7: the accepted sub-agent spawn returns", () => {
  it("retains the child id and links to it instead of discarding it", async () => {
    renderOutline();

    // No proposal, no return row: nothing has been spawned yet.
    expect(screen.queryByTestId("write-sub-agent-spawned")).toBeNull();

    await userEvent.click(screen.getByRole("button", { name: "deep research" }));
    await userEvent.click(await screen.findByTestId("accept-proposal"));

    const row = await screen.findByTestId("write-sub-agent-spawned");
    const link = row.querySelector("a");
    expect(link).toBeTruthy();
    expect(link?.getAttribute("href")).toBe("/inv/inv-child-123");
    expect(link?.textContent).toContain("open research");
  });

  it("the proposal closes on accept, so the writer sees the outcome not the form", async () => {
    renderOutline();
    await userEvent.click(screen.getByRole("button", { name: "deep research" }));
    await userEvent.click(await screen.findByTestId("accept-proposal"));
    await waitFor(() => expect(screen.queryByTestId("accept-proposal")).toBeNull());
  });

  it("the return row is dismissible", async () => {
    renderOutline();
    await userEvent.click(screen.getByRole("button", { name: "deep research" }));
    await userEvent.click(await screen.findByTestId("accept-proposal"));
    await screen.findByTestId("write-sub-agent-spawned");
    await userEvent.click(screen.getByRole("button", { name: "dismiss" }));
    expect(screen.queryByTestId("write-sub-agent-spawned")).toBeNull();
  });
});
