import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ResearchProgressPanel } from "./ResearchProgressPanel";

const fetchResearchProgress = vi.fn();
const seedResearchProgress = vi.fn();

vi.mock("../../api/engagement", () => ({
  fetchResearchProgress: (...args: unknown[]) => fetchResearchProgress(...args),
  seedResearchProgress: (...args: unknown[]) => seedResearchProgress(...args),
}));

describe("ResearchProgressPanel", () => {
  afterEach(() => cleanup());
  beforeEach(() => {
    fetchResearchProgress.mockReset();
    seedResearchProgress.mockReset();
  });

  it("seeds and shows plan→cite pipeline", async () => {
    seedResearchProgress.mockResolvedValue({
      spawn_id: "spn_1",
      event_count: 4,
      events: [
        { spawn_id: "spn_1", stage: "plan", message: "p", ts: 1, sequence: 1 },
        { spawn_id: "spn_1", stage: "gather", message: "g", ts: 2, sequence: 2 },
        {
          spawn_id: "spn_1",
          stage: "synthesize",
          message: "s",
          ts: 3,
          sequence: 3,
        },
        { spawn_id: "spn_1", stage: "cite", message: "c", ts: 4, sequence: 4 },
      ],
      latest_stage: "cite",
      is_terminal: false,
      view_format: "html",
      product_panel: "research_progress",
      source: "engagement_spine.progress",
      notes: [],
      html: "<p>Deep research progress</p>",
    });

    render(<ResearchProgressPanel spawnId="spn_1" />);
    fireEvent.click(screen.getByTestId("progress-seed"));
    await waitFor(() => {
      expect(screen.getByTestId("research-progress-summary").textContent).toMatch(
        /cite/,
      );
    });
    expect(seedResearchProgress).toHaveBeenCalledWith("spn_1", {
      includeHtml: true,
    });
    expect(screen.getByTestId("research-progress-events").children.length).toBe(4);
    expect(
      screen.getByTestId("research-progress-panel").getAttribute("data-view-format"),
    ).toBe("html");
  });
});
