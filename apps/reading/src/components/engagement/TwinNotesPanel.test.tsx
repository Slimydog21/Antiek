import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { TwinNotesPanel } from "./TwinNotesPanel";

const fetchTwinNotes = vi.fn();
const recordTwinNote = vi.fn();

vi.mock("../../api/engagement", () => ({
  fetchTwinNotes: (...args: unknown[]) => fetchTwinNotes(...args),
  recordTwinNote: (...args: unknown[]) => recordTwinNote(...args),
}));

describe("TwinNotesPanel", () => {
  afterEach(() => cleanup());
  beforeEach(() => {
    fetchTwinNotes.mockReset();
    recordTwinNote.mockReset();
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
});
