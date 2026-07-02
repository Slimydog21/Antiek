import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const { emitBrainstormBlocksMock } = vi.hoisted(() => ({
  emitBrainstormBlocksMock: vi.fn(),
}));

vi.mock("../writeApi", async (orig) => ({
  ...(await orig<typeof import("../writeApi")>()),
  emitBrainstormBlocks: emitBrainstormBlocksMock,
}));

import { IdeaDump } from "./IdeaDump";

beforeEach(() => {
  emitBrainstormBlocksMock.mockReset().mockResolvedValue({
    block_ids: [" oblk-1 ", "", 42, "oblk-1"],
    insight_count: "1",
    question_count: -1,
    data_count: Number.NaN,
    skipped_duplicates: "2",
    flagged_unverified: [" asserted datum ", "", 99, "asserted datum"],
  });
});

afterEach(cleanup);

describe("IdeaDump", () => {
  it("sanitizes brainstorm emit results before rendering the summary", async () => {
    const onEmitted = vi.fn();
    render(<IdeaDump sectionId="sec-1" deliverableId="dlv-1" onEmitted={onEmitted} />);

    await userEvent.type(screen.getAllByPlaceholderText("one per line")[0], "The moat is data");
    await userEvent.click(screen.getByRole("button", { name: /emit lego blocks/i }));

    await waitFor(() => expect(onEmitted).toHaveBeenCalled());
    expect(emitBrainstormBlocksMock).toHaveBeenCalledWith({
      section_id: "sec-1",
      deliverable_id: "dlv-1",
      insights: ["The moat is data"],
      questions: [],
      data_points: [],
    });
    expect(screen.getByText(/Placed 1 block\(s\): 1 insight, 0 question, 0 data/)).toBeTruthy();
    expect(screen.getByText(/1 flagged unverified/)).toBeTruthy();
    expect(screen.getByText(/2 duplicate\(s\) skipped/)).toBeTruthy();
  });

  it("keeps malformed empty results from crashing the idea dump", async () => {
    emitBrainstormBlocksMock.mockResolvedValue({
      block_ids: null,
      insight_count: null,
      question_count: null,
      data_count: null,
      skipped_duplicates: null,
      flagged_unverified: null,
    });
    render(<IdeaDump sectionId="sec-1" />);

    await userEvent.type(screen.getAllByPlaceholderText("one per line")[1], "What changed?");
    await userEvent.click(screen.getByRole("button", { name: /emit lego blocks/i }));

    expect(await screen.findByText(/Placed 0 block\(s\): 0 insight, 0 question, 0 data/)).toBeTruthy();
  });
});
