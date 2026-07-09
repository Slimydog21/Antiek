import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { CollectiveResearchPanel } from "./CollectiveResearchPanel";

const fetchCollectiveResearch = vi.fn();

vi.mock("../../api/engagement", () => ({
  fetchCollectiveResearch: (...args: unknown[]) => fetchCollectiveResearch(...args),
}));

describe("CollectiveResearchPanel", () => {
  afterEach(() => cleanup());
  beforeEach(() => fetchCollectiveResearch.mockReset());

  it("merges selected spawns into collective prompt", async () => {
    fetchCollectiveResearch.mockResolvedValue({
      collective_id: "col_abc",
      spawn_ids: ["spn_1", "spn_2"],
      asset_ids: ["a", "b"],
      investigation_ids: [],
      twin_units: [],
      source_references: [],
      view_format: "html",
      spawn_count: 2,
      twin_count: 0,
      ref_count: 0,
      prompt_block: "# Collective deep-research unit `col_abc`\n",
    });

    render(
      <CollectiveResearchPanel availableSpawnIds={["spn_1", "spn_2", "spn_3"]} />,
    );

    const boxes = screen.getAllByRole("checkbox");
    fireEvent.click(boxes[0]);
    fireEvent.click(boxes[1]);
    fireEvent.click(screen.getByRole("button", { name: /merge 2 spawn/i }));

    await waitFor(() => {
      expect(screen.getByTestId("collective-prompt-block").textContent).toContain(
        "col_abc",
      );
    });
    expect(fetchCollectiveResearch).toHaveBeenCalledWith({
      spawn_ids: ["spn_1", "spn_2"],
    });
  });
});
