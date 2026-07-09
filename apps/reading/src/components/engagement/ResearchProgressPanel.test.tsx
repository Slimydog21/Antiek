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

  it("links to Settings for driver & budget (ij)", () => {
    render(<ResearchProgressPanel spawnId="spn_1" />);
    const link = screen.getByTestId("research-progress-settings-link");
    expect(link.getAttribute("href")).toBe("/settings");
    expect(link.textContent).toMatch(/driver & budget/i);
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
    // Residual (hk): machine-readable multi-minute progress metrics.
    const metrics = screen.getByTestId("research-progress-metrics");
    expect(metrics.getAttribute("data-spawn-id")).toBe("spn_1");
    expect(metrics.getAttribute("data-event-count")).toBe("4");
    expect(metrics.getAttribute("data-latest-stage")).toBe("cite");
    expect(metrics.getAttribute("data-is-terminal")).toBe("false");
    expect(metrics.getAttribute("data-view-format")).toBe("html");
    expect(metrics.getAttribute("data-product-panel")).toBe("research_progress");
    expect(metrics.getAttribute("data-source")).toBe(
      "engagement_spine.progress",
    );
    expect(metrics.textContent).toMatch(/Research progress/);
  });

  it("auto-loads progress on mount (cp)", async () => {
    fetchResearchProgress.mockResolvedValue({
      spawn_id: "spn_1",
      event_count: 1,
      events: [
        { spawn_id: "spn_1", stage: "plan", message: "planned", ts: 1, sequence: 1 },
      ],
      latest_stage: "plan",
      is_terminal: false,
      view_format: "html",
      product_panel: "research_progress",
      source: "engagement_spine.progress",
      notes: [],
      html: "<p>plan</p>",
    });
    render(<ResearchProgressPanel spawnId="spn_1" autoLoad />);
    await waitFor(() => {
      expect(fetchResearchProgress).toHaveBeenCalledWith("spn_1", {
        includeHtml: true,
      });
    });
    await waitFor(() => {
      expect(screen.getByTestId("research-progress-summary").textContent).toMatch(
        /plan/,
      );
    });
    expect(seedResearchProgress).not.toHaveBeenCalled();
  });

  it("polls progress while non-terminal when pollIntervalMs set (cr)", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    fetchResearchProgress
      .mockResolvedValueOnce({
        spawn_id: "spn_poll",
        event_count: 1,
        events: [
          {
            spawn_id: "spn_poll",
            stage: "plan",
            message: "p",
            ts: 1,
            sequence: 1,
          },
        ],
        latest_stage: "plan",
        is_terminal: false,
        view_format: "html",
        product_panel: "research_progress",
        source: "test",
        notes: [],
        html: "<p>plan</p>",
      })
      .mockResolvedValue({
        spawn_id: "spn_poll",
        event_count: 2,
        events: [
          {
            spawn_id: "spn_poll",
            stage: "plan",
            message: "p",
            ts: 1,
            sequence: 1,
          },
          {
            spawn_id: "spn_poll",
            stage: "gather",
            message: "g",
            ts: 2,
            sequence: 2,
          },
        ],
        latest_stage: "gather",
        is_terminal: false,
        view_format: "html",
        product_panel: "research_progress",
        source: "test",
        notes: [],
        html: "<p>gather</p>",
      });

    render(
      <ResearchProgressPanel
        spawnId="spn_poll"
        autoLoad
        pollIntervalMs={1000}
      />,
    );
    await waitFor(() => {
      expect(fetchResearchProgress).toHaveBeenCalled();
    });
    const callsAfterMount = fetchResearchProgress.mock.calls.length;
    await vi.advanceTimersByTimeAsync(1100);
    await waitFor(() => {
      expect(fetchResearchProgress.mock.calls.length).toBeGreaterThan(
        callsAfterMount,
      );
    });
    expect(
      screen.getByTestId("research-progress-panel").getAttribute("data-poll-ms"),
    ).toBe("1000");
    vi.useRealTimers();
  });

  it("auto-seeds empty pipeline when autoSeedIfEmpty (cp)", async () => {
    fetchResearchProgress.mockResolvedValue({
      spawn_id: "spn_empty",
      event_count: 0,
      events: [],
      latest_stage: null,
      is_terminal: false,
      view_format: "html",
      product_panel: "research_progress",
      source: "engagement_spine.progress",
      notes: [],
      html: "<p>empty</p>",
    });
    seedResearchProgress.mockResolvedValue({
      spawn_id: "spn_empty",
      event_count: 4,
      events: [
        { spawn_id: "spn_empty", stage: "plan", message: "p", ts: 1, sequence: 1 },
        {
          spawn_id: "spn_empty",
          stage: "gather",
          message: "g",
          ts: 2,
          sequence: 2,
        },
        {
          spawn_id: "spn_empty",
          stage: "synthesize",
          message: "s",
          ts: 3,
          sequence: 3,
        },
        { spawn_id: "spn_empty", stage: "cite", message: "c", ts: 4, sequence: 4 },
      ],
      latest_stage: "cite",
      is_terminal: false,
      view_format: "html",
      product_panel: "research_progress",
      source: "engagement_spine.progress",
      notes: [],
      html: "<p>seeded</p>",
    });
    render(
      <ResearchProgressPanel
        spawnId="spn_empty"
        autoLoad
        autoSeedIfEmpty
      />,
    );
    await waitFor(() => {
      expect(seedResearchProgress).toHaveBeenCalledWith("spn_empty", {
        includeHtml: true,
      });
    });
    await waitFor(() => {
      expect(screen.getByTestId("research-progress-summary").textContent).toMatch(
        /cite/,
      );
    });
  });
});
