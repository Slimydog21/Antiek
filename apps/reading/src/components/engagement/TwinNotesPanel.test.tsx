import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { TwinNotesPanel } from "./TwinNotesPanel";

const fetchTwinNotes = vi.fn();
const recordTwinNote = vi.fn();
const promoteTwinsToContext = vi.fn();

vi.mock("../../api/engagement", () => ({
  fetchTwinNotes: (...args: unknown[]) => fetchTwinNotes(...args),
  recordTwinNote: (...args: unknown[]) => recordTwinNote(...args),
  promoteTwinsToContext: (...args: unknown[]) => promoteTwinsToContext(...args),
}));

describe("TwinNotesPanel", () => {
  afterEach(() => cleanup());
  beforeEach(() => {
    fetchTwinNotes.mockReset();
    recordTwinNote.mockReset();
    promoteTwinsToContext.mockReset();
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
  });
});
