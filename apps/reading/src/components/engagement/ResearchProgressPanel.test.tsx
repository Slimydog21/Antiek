import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ResearchProgressPanel } from "./ResearchProgressPanel";

const fetchResearchProgress = vi.fn();
const seedResearchProgress = vi.fn();
const openWindow = vi.fn(() => "win:progress:test");

vi.mock("../windows/openWindow", () => ({
  openWindow: (...args: unknown[]) => openWindow(...args),
}));

vi.mock("../../api/engagement", () => ({
  fetchResearchProgress: (...args: unknown[]) => fetchResearchProgress(...args),
  seedResearchProgress: (...args: unknown[]) => seedResearchProgress(...args),
}));

vi.mock("./DecisionTreeDriverBadge", () => ({
  DecisionTreeDriverBadge: (props: {
    researchTier?: string | null;
  }) => (
    <div
      data-testid="decision-tree-driver-badge-stub"
      data-research-tier={(props.researchTier || "").trim().toLowerCase() || ""}
    >
      driver badge
    </div>
  ),
}));

describe("ResearchProgressPanel", () => {
  afterEach(() => cleanup());
  beforeEach(() => {
    fetchResearchProgress.mockReset();
    seedResearchProgress.mockReset();
    openWindow.mockClear();
  });

  it("links to Settings for driver & budget (ij)", () => {
    render(<ResearchProgressPanel spawnId="spn_1" />);
    const link = screen.getByTestId("research-progress-settings-link");
    expect(link.getAttribute("href")).toBe("/settings#decision-tree-panel");
    expect(link.textContent).toMatch(/driver & budget/i);
  });

  it("surfaces competitive duration band for wrestle (mw)", () => {
    render(
      <ResearchProgressPanel spawnId="spn_w" researchTier="wrestle" />,
    );
    const band = screen.getByTestId("research-progress-competitive-band");
    expect(band.getAttribute("data-research-tier")).toBe("wrestle");
    expect(band.getAttribute("data-band-minutes")).toMatch(/10/);
    expect(band.getAttribute("data-poll-ms")).toBe("8000");
    expect(band.textContent).toMatch(/long-horizon/i);
    expect(band.textContent).toMatch(/offline-honest estimate/i);
    const dual = screen.getByTestId("research-progress-dual-gate-checklist-link");
    // Residual (xu/aau): multi-minute job prep → L4 MO live-step checklist section.
    expect(dual.getAttribute("href")).toMatch(/DUAL-GATE-L1-L4.*#l4-moil/);
    expect(dual.textContent).toMatch(/L4 Midnight Oil checklist/i);
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
    // Residual (rp): non-terminal still offers progress draft Write handoff.
    const draftWrite = screen.getByTestId("research-progress-open-write");
    expect(draftWrite.getAttribute("data-is-terminal")).toBe("false");
    expect(draftWrite.textContent).toMatch(/progress draft/i);
    expect(draftWrite.getAttribute("href") || "").toMatch(
      /^\/write\?twin_seed=antiek\.twin_write_seed\./,
    );
    // Residual (acp): progress.html body → has-body true (parity marketplace/MO).
    expect(draftWrite.getAttribute("data-write-seed-has-body")).toBe("true");
  });

  it("links Open Write twin_seed when progress is terminal (qw)", async () => {
    fetchResearchProgress.mockResolvedValue({
      spawn_id: "spn_done",
      event_count: 2,
      events: [
        {
          spawn_id: "spn_done",
          stage: "synthesize",
          message: "syn",
          ts: 1,
          sequence: 1,
        },
        {
          spawn_id: "spn_done",
          stage: "cite",
          message: "done",
          ts: 2,
          sequence: 2,
        },
      ],
      latest_stage: "cite",
      is_terminal: true,
      research_tier: "deep",
      view_format: "html",
      product_panel: "research_progress",
      source: "engagement_spine.progress",
      notes: [],
      html: "<p>Final synthesis</p>",
    });
    render(
      <ResearchProgressPanel
        spawnId="spn_done"
        autoLoad
        parentAssetId="book-qw"
        goal="Prove attention routing"
        researchTier="deep"
      />,
    );
    await waitFor(() => {
      expect(screen.getByTestId("research-progress-open-write")).toBeTruthy();
    });
    const write = screen.getByTestId("research-progress-open-write");
    const href = write.getAttribute("href") || "";
    expect(href).toMatch(/^\/write\?twin_seed=antiek\.twin_write_seed\./);
    expect(href).not.toMatch(/html_draft=/);
    expect(write.getAttribute("data-has-twin-seed")).toBe("1");
    expect(write.getAttribute("data-is-terminal")).toBe("true");
    expect(write.getAttribute("data-view-format")).toBe("html");
    // Residual (acp): Final synthesis HTML body → has-body true.
    expect(write.getAttribute("data-write-seed-has-body")).toBe("true");
    // Residual (aex): plan→cite progress → Write path honesty.
    expect(write.getAttribute("data-spawn-id")).toBe("spn_done");
    expect(write.getAttribute("data-progress-source")).toBe(
      "research_progress_complete",
    );
    expect(write.getAttribute("data-seamless-progress-write")).toBe("true");
    // Residual (sm): float|full progress HTML reading windows.
    fireEvent.click(screen.getByTestId("research-progress-open-float"));
    const floatCall = openWindow.mock.calls.at(-1) as [
      string,
      { source?: string; html?: string; view_format?: string },
      { mode?: string },
    ];
    expect(floatCall[0]).toBe("hosted_html_document");
    expect(floatCall[1].source).toBe("research_progress_complete");
    expect(floatCall[1].view_format).toBe("html");
    expect(floatCall[1].html).toMatch(/Final synthesis/);
    expect(floatCall[2].mode).toBe("floating");
    fireEvent.click(screen.getByTestId("research-progress-open-full"));
    const fullCall = openWindow.mock.calls.at(-1) as [
      string,
      { source?: string },
      { mode?: string },
    ];
    expect(fullCall[1].source).toBe("research_progress_complete");
    expect(fullCall[2].mode).toBe("full");
  });

  it("Open Write has-body false when progress has no HTML body (acp)", async () => {
    fetchResearchProgress.mockResolvedValue({
      spawn_id: "spn_meta",
      event_count: 1,
      events: [
        {
          spawn_id: "spn_meta",
          stage: "plan",
          message: "planned only",
          ts: 1,
          sequence: 1,
        },
      ],
      latest_stage: "plan",
      is_terminal: false,
      view_format: "html",
      product_panel: "research_progress",
      source: "engagement_spine.progress",
      notes: [],
      html: "",
    });
    render(
      <ResearchProgressPanel
        spawnId="spn_meta"
        autoLoad
        goal="Events-only seed"
      />,
    );
    await waitFor(() => {
      expect(screen.getByTestId("research-progress-open-write")).toBeTruthy();
    });
    const write = screen.getByTestId("research-progress-open-write");
    // Twin seed still lands from goal/events meta; body honesty is false without HTML.
    expect(write.getAttribute("href") || "").toMatch(
      /^\/write\?twin_seed=antiek\.twin_write_seed\./,
    );
    expect(write.getAttribute("data-write-seed-has-body")).toBe("false");
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

  it("surfaces wrestle long-horizon posture chrome (jq)", () => {
    render(
      <ResearchProgressPanel spawnId="spn_w" researchTier="wrestle" />,
    );
    const panel = screen.getByTestId("research-progress-panel");
    expect(panel.getAttribute("data-research-tier")).toBe("wrestle");
    expect(panel.getAttribute("data-research-tier-source")).toBe("prop");
    expect(screen.getByTestId("research-progress-wrestle-note").textContent).toMatch(
      /multi-minute long-horizon/i,
    );
    expect(panel.textContent).toMatch(/tier=wrestle/);
    // Residual (lr): driver badge mounts when tier is known.
    expect(
      screen
        .getByTestId("research-progress-driver-badge-mount")
        .getAttribute("data-research-tier"),
    ).toBe("wrestle");
    expect(
      screen
        .getByTestId("decision-tree-driver-badge-stub")
        .getAttribute("data-research-tier"),
    ).toBe("wrestle");
  });

  it("falls back to progress API research_tier when prop omitted (ka)", async () => {
    fetchResearchProgress.mockResolvedValue({
      spawn_id: "spn_api_tier",
      event_count: 1,
      events: [
        {
          spawn_id: "spn_api_tier",
          stage: "plan",
          message: "planned",
          ts: 1,
          sequence: 1,
        },
      ],
      latest_stage: "plan",
      is_terminal: false,
      research_tier: "wrestle",
      view_format: "html",
      product_panel: "research_progress",
      source: "engagement_spine.progress",
      notes: [],
      html: "<p>plan</p>",
    });
    render(<ResearchProgressPanel spawnId="spn_api_tier" autoLoad />);
    await waitFor(() => {
      expect(fetchResearchProgress).toHaveBeenCalled();
    });
    await waitFor(() => {
      const panel = screen.getByTestId("research-progress-panel");
      expect(panel.getAttribute("data-research-tier")).toBe("wrestle");
      expect(panel.getAttribute("data-research-tier-source")).toBe("api");
    });
    expect(screen.getByTestId("research-progress-wrestle-note").textContent).toMatch(
      /multi-minute long-horizon/i,
    );
  });
});
