import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { TwinNotesPanel } from "./TwinNotesPanel";

const fetchTwinNotes = vi.fn();
const recordTwinNote = vi.fn();
const promoteTwinsToContext = vi.fn();
const seedTwinNotes = vi.fn();

vi.mock("../../api/engagement", () => ({
  fetchTwinNotes: (...args: unknown[]) => fetchTwinNotes(...args),
  recordTwinNote: (...args: unknown[]) => recordTwinNote(...args),
  promoteTwinsToContext: (...args: unknown[]) => promoteTwinsToContext(...args),
  seedTwinNotes: (...args: unknown[]) => seedTwinNotes(...args),
}));

describe("TwinNotesPanel", () => {
  afterEach(() => cleanup());
  beforeEach(() => {
    fetchTwinNotes.mockReset();
    recordTwinNote.mockReset();
    promoteTwinsToContext.mockReset();
    seedTwinNotes.mockReset();
  });

  it("auto-loads twins on mount when autoLoad (cq)", async () => {
    fetchTwinNotes.mockResolvedValue({
      asset_id: "paper",
      note_count: 2,
      insight_count: 1,
      question_count: 1,
      notes: [
        {
          note_id: "twin_1",
          asset_id: "paper",
          kind: "insight",
          text: "Seeded insight",
        },
      ],
      view_format: "html",
      product_panel: "twin_notes",
      source: "engagement_spine.twin",
      messages: [],
      html: "<p>twins</p>",
    });
    render(<TwinNotesPanel assetId="paper" autoLoad />);
    await waitFor(() => {
      expect(fetchTwinNotes).toHaveBeenCalledWith("paper", { includeHtml: true });
    });
    await waitFor(() => {
      expect(screen.getByTestId("twin-notes-summary").textContent).toMatch(
        /insights=1/,
      );
    });
    // Residual (fk): machine-readable twin metrics.
    const metrics = screen.getByTestId("twin-notes-metrics");
    expect(metrics.getAttribute("data-insight-count")).toBe("1");
    expect(metrics.getAttribute("data-question-count")).toBe("1");
    expect(metrics.getAttribute("data-note-count")).toBe("2");
    expect(metrics.getAttribute("data-view-format")).toBe("html");
    expect(seedTwinNotes).not.toHaveBeenCalled();
  });

  it("offline seeds when empty and autoSeedIfEmpty (dd)", async () => {
    fetchTwinNotes.mockResolvedValue({
      asset_id: "paper",
      note_count: 0,
      insight_count: 0,
      question_count: 0,
      notes: [],
      view_format: "html",
      product_panel: "twin_notes",
      source: "engagement_spine.twin",
      messages: [],
      html: "",
    });
    seedTwinNotes.mockResolvedValue({
      asset_id: "paper",
      note_count: 2,
      insight_count: 1,
      question_count: 1,
      notes: [
        {
          note_id: "twin_seed_1",
          asset_id: "paper",
          kind: "insight",
          text: "Offline seed insight",
        },
      ],
      view_format: "html",
      product_panel: "twin_notes",
      source: "engagement_spine.twin",
      messages: [],
      html: "<p>seeded</p>",
      seeded: true,
      force_offline: true,
      live_seed: false,
      seed_source: "engagement_spine.twin.seed_twins_for_asset",
    });

    render(
      <TwinNotesPanel
        assetId="paper"
        autoLoad
        autoSeedIfEmpty
        seedTitle="Attention paper"
        seedBodyText="Transformers are all you need."
      />,
    );

    await waitFor(() => {
      expect(seedTwinNotes).toHaveBeenCalledWith(
        expect.objectContaining({
          asset_id: "paper",
          force_offline: true,
          title: "Attention paper",
        }),
      );
    });
    await waitFor(() => {
      const status = screen.getByTestId("twin-seed-status");
      // Residual (hh): offline-honest copy + machine-readable attrs.
      expect(status.textContent).toMatch(/offline-honest identity stubs/);
      expect(status.getAttribute("data-offline-honest")).toBe("true");
      expect(status.getAttribute("data-live-seed")).toBe("false");
      expect(status.getAttribute("data-seeded")).toBe("true");
      expect(status.getAttribute("data-force-offline")).toBe("true");
      expect(status.getAttribute("data-seed-source")).toBe(
        "engagement_spine.twin.seed_twins_for_asset",
      );
    });
    await waitFor(() => {
      expect(screen.getByTestId("twin-notes-summary").textContent).toMatch(
        /notes=2/,
      );
    });
  });

  it("surfaces live seed honesty when API reports live_seed (hh)", async () => {
    fetchTwinNotes.mockResolvedValue({
      asset_id: "paper",
      note_count: 0,
      insight_count: 0,
      question_count: 0,
      notes: [],
      view_format: "html",
      product_panel: "twin_notes",
      source: "engagement_spine.twin",
      messages: [],
      html: "",
    });
    seedTwinNotes.mockResolvedValue({
      asset_id: "paper",
      note_count: 2,
      insight_count: 1,
      question_count: 1,
      notes: [
        {
          note_id: "twin_live_1",
          asset_id: "paper",
          kind: "insight",
          text: "Live note_taker insight",
        },
      ],
      view_format: "html",
      product_panel: "twin_notes",
      source: "engagement_spine.twin",
      messages: [],
      html: "<p>live</p>",
      seeded: true,
      live_seed: true,
      seed_source: "engagement_spine.twin.seed_twins_for_asset.live",
    });

    render(
      <TwinNotesPanel assetId="paper" autoLoad autoSeedIfEmpty />,
    );

    await waitFor(() => {
      const status = screen.getByTestId("twin-seed-status");
      expect(status.textContent).toMatch(/live note_taker injector landed/);
      expect(status.getAttribute("data-offline-honest")).toBe("false");
      expect(status.getAttribute("data-live-seed")).toBe("true");
      expect(status.getAttribute("data-seed-source")).toMatch(/\.live$/);
    });
  });

  it("auto-promotes twins to context after load when autoPromoteAfterLoad (ea)", async () => {
    fetchTwinNotes.mockResolvedValue({
      asset_id: "paper",
      note_count: 1,
      insight_count: 1,
      question_count: 0,
      notes: [
        {
          note_id: "twin_1",
          asset_id: "paper",
          kind: "insight",
          text: "Attention is routing.",
        },
      ],
      view_format: "html",
      product_panel: "twin_notes",
      source: "engagement_spine.twin",
      messages: [],
      html: "<p>twins</p>",
    });
    promoteTwinsToContext.mockResolvedValue({
      asset_id: "paper",
      promoted_count: 1,
      context_unit_count: 1,
      promoted: [
        {
          twin_note_id: "twin_1",
          graph_node_id: "n1",
          kind: "insight",
          text: "Attention is routing.",
        },
      ],
      context_units: [],
      view_format: "html",
      product_panel: "twin_promote_context",
      source: "engagement_spine.twin_promote",
      notes: [],
      html: "<p>promoted</p>",
    });

    const onPromoted = vi.fn();
    render(
      <TwinNotesPanel
        assetId="paper"
        autoLoad
        autoPromoteAfterLoad
        onPromoted={onPromoted}
      />,
    );

    await waitFor(() => {
      expect(promoteTwinsToContext).toHaveBeenCalledWith(
        expect.objectContaining({ asset_id: "paper", include_html: true }),
      );
    });
    await waitFor(() => {
      expect(screen.getByTestId("twin-promote-status").textContent).toMatch(
        /auto-promoted 1/,
      );
    });
    // Residual (ec): parent notified so context can remount.
    await waitFor(() => {
      expect(onPromoted).toHaveBeenCalled();
    });
    expect(onPromoted.mock.calls[0][0].promoted_count).toBe(1);
  });

  it("records insight and shows twin HTML", async () => {
    recordTwinNote.mockResolvedValue({
      asset_id: "paper",
      note_count: 1,
      insight_count: 1,
      question_count: 0,
      notes: [
        {
          note_id: "twin_1",
          asset_id: "paper",
          kind: "insight",
          text: "Attention is routing.",
        },
      ],
      view_format: "html",
      product_panel: "twin_notes",
      source: "engagement_spine.twin",
      messages: [],
      html: "<p>Insight: Attention is routing.</p>",
    });

    render(<TwinNotesPanel assetId="paper" spawnId="spn_1" />);
    fireEvent.change(screen.getByTestId("twin-text"), {
      target: { value: "Attention is routing." },
    });
    fireEvent.click(screen.getByTestId("twin-record"));
    await waitFor(() => {
      expect(screen.getByTestId("twin-notes-summary").textContent).toMatch(
        /insights=1/,
      );
    });
    expect(recordTwinNote).toHaveBeenCalledWith({
      asset_id: "paper",
      kind: "insight",
      text: "Attention is routing.",
      source_spawn_id: "spn_1",
      include_html: true,
    });
    expect(screen.getByTestId("twin-notes-html").innerHTML).toMatch(
      /Attention is routing/,
    );
    expect(
      screen.getByTestId("twin-notes-panel").getAttribute("data-view-format"),
    ).toBe("html");
  });

  it("promotes twins into context units", async () => {
    promoteTwinsToContext.mockResolvedValue({
      asset_id: "paper",
      promoted_count: 1,
      context_unit_count: 1,
      promoted: [
        {
          twin_note_id: "twin_1",
          graph_node_id: "insight_abc",
          kind: "insight",
          text: "Attention is routing.",
        },
      ],
      context_units: [
        {
          unit_id: "insight_abc",
          twin_note_id: "twin_1",
          kind: "insight",
          text: "Attention is routing.",
        },
      ],
      view_format: "html",
      product_panel: "twin_promote_context",
      source: "engagement_spine.twin_promote",
      notes: ["Twins promoted into content-addressed context units"],
      html: "<p>[insight] Attention is routing.</p>",
    });

    render(<TwinNotesPanel assetId="paper" />);
    fireEvent.click(screen.getByTestId("twin-promote-context"));
    await waitFor(() => {
      expect(screen.getByTestId("twin-promote-result").textContent).toMatch(
        /promoted=1/,
      );
    });
    expect(promoteTwinsToContext).toHaveBeenCalledWith({
      asset_id: "paper",
      include_html: true,
    });
    expect(screen.getByTestId("twin-promote-html").innerHTML).toMatch(
      /Attention is routing/,
    );
    // Residual (hi): machine-readable promote→context metrics.
    const metrics = screen.getByTestId("twin-promote-metrics");
    expect(metrics.getAttribute("data-promoted-count")).toBe("1");
    expect(metrics.getAttribute("data-context-unit-count")).toBe("1");
    expect(metrics.getAttribute("data-view-format")).toBe("html");
    expect(metrics.getAttribute("data-product-panel")).toBe(
      "twin_promote_context",
    );
    expect(metrics.getAttribute("data-source")).toBe(
      "engagement_spine.twin_promote",
    );
    expect(metrics.textContent).toMatch(/Twin promote → context/);
  });
});
