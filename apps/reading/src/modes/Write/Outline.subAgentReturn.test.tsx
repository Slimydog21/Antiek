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
 * The REAL SubAgentProposal is mounted here, not a stub. An independent critic
 * rejected an earlier revision of this file for mocking the component: with
 * `vi.mock("./SubAgentProposal")` the suite stayed 3/3 green after the real
 * component's `onAccept(child.investigation_id)` call was deleted, so it proved
 * the host keeps an id it is handed and nothing about the component handing it
 * over. The fix is to exercise the chain the defect actually lives in:
 *
 *   SubAgentProposal.accept() -> startInvestigation() -> onAccept(child id)
 *     -> Outline.spawnedChild -> <Link to={`/inv/${id}`}>
 *
 * Only the two edges that leave the process are stubbed: the repository search
 * and the spawn API. Everything between them is the shipped code.
 *
 * VERIFIED RED ON THE DEFECT: deleting `onAccept(child.investigation_id)` from
 * SubAgentProposal.tsx:77 fails every case below.
 */

const { getSectionBlocksMock, updateSectionProseMock, searchRepositoryMock, startInvestigationMock } =
  vi.hoisted(() => ({
    getSectionBlocksMock: vi.fn(),
    updateSectionProseMock: vi.fn(),
    searchRepositoryMock: vi.fn(),
    startInvestigationMock: vi.fn(),
  }));

vi.mock("./writeApi", async (orig) => ({
  ...(await orig<typeof import("./writeApi")>()),
  getSectionBlocks: getSectionBlocksMock,
  generateSection: vi.fn(),
  placeBlock: vi.fn(),
  moveBlock: vi.fn(),
  searchRepository: searchRepositoryMock,
}));

vi.mock("../../lib/api", async (orig) => ({
  ...(await orig<typeof import("../../lib/api")>()),
  createSection: vi.fn().mockResolvedValue({}),
  updateSectionProse: updateSectionProseMock,
  postTypedEvent: vi.fn().mockResolvedValue({}),
  startInvestigation: startInvestigationMock,
}));

vi.mock("../shared/FloatMenu/useFloatMenuSelection", () => ({
  useFloatMenuSelection: () => null,
}));

// Only the MENU is stubbed (jsdom cannot drive its DOM selection). Firing
// onDeepResearch is the shipped path that opens the proposal.
vi.mock("../shared/FloatMenu/FloatMenu", () => ({
  default: (props: { onDeepResearch?: (t: string | null) => void }) => (
    <button type="button" onClick={() => props.onDeepResearch?.("Capital intensity rises")}>
      deep research
    </button>
  ),
}));

vi.mock("@tiptap/react", async (orig) => ({
  ...(await orig<typeof import("@tiptap/react")>()),
  useEditor: () => null,
}));

import Outline from "./Outline";

const CHILD_ID = "inv-child-123";

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
  searchRepositoryMock.mockReset().mockResolvedValue([]);
  startInvestigationMock.mockReset().mockResolvedValue({ investigation_id: CHILD_ID });
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

/** Open the proposal, then accept it through the REAL component's button. */
async function spawnViaRealProposal() {
  await userEvent.click(screen.getByRole("button", { name: "deep research" }));
  await userEvent.click(
    await screen.findByRole("button", { name: /accept/i }),
  );
}

describe("Outline — F7: the accepted sub-agent spawn returns", () => {
  it("the real proposal reports its child id and the host links to it", async () => {
    renderOutline();
    expect(screen.queryByTestId("write-sub-agent-spawned")).toBeNull();

    await spawnViaRealProposal();

    // The real component must have gone through the shipped spawn path.
    await waitFor(() => expect(startInvestigationMock).toHaveBeenCalled());
    const req = startInvestigationMock.mock.calls.at(-1)?.[0] as { question: string };
    expect(req.question).toContain("Capital intensity rises");

    const row = await screen.findByTestId("write-sub-agent-spawned");
    const link = row.querySelector("a");
    expect(link?.getAttribute("href")).toBe(`/inv/${CHILD_ID}`);
    expect(link?.textContent).toContain("open research");
  });

  it("the proposal closes on accept, so the writer sees the outcome not the form", async () => {
    renderOutline();
    await spawnViaRealProposal();
    await waitFor(() =>
      expect(screen.queryByRole("button", { name: /accept/i })).toBeNull(),
    );
  });

  it("the return row is dismissible", async () => {
    renderOutline();
    await spawnViaRealProposal();
    await screen.findByTestId("write-sub-agent-spawned");
    await userEvent.click(screen.getByRole("button", { name: "dismiss" }));
    expect(screen.queryByTestId("write-sub-agent-spawned")).toBeNull();
  });
});
