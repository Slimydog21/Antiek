import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import NotebookCanvas from "./NotebookCanvas";
import type { NotebookResponse } from "./types";

const notebook: NotebookResponse = {
  notebook_id: "nb_1",
  title: "Research notebook",
  investigation_id: "inv_1",
  document_id: "paper_1",
  content_class: "user_owned",
  created_at: "2026-07-12T00:00:00Z",
  updated_at: "2026-07-12T00:00:00Z",
  blocks: [],
};

describe("NotebookCanvas twin citations", () => {
  it("inserts a twin note as a reference-only notebook block", async () => {
    const onAppendBlock = vi.fn().mockResolvedValue(undefined);
    render(
      <NotebookCanvas
        notebook={notebook}
        onAppendBlock={onAppendBlock}
        twinNotes={[
          {
            note_id: "twin_grounded",
            asset_id: "paper_1",
            kind: "insight",
            text: "The graph compounds through cited reuse.",
          },
        ]}
      />,
    );

    fireEvent.click(screen.getByText("+ add block"));
    fireEvent.click(screen.getByText("Twin note"));
    const picker = screen.getByTestId("notebook-twin-picker");
    expect(picker.getAttribute("data-asset-id")).toBe("paper_1");
    fireEvent.click(screen.getByTestId("notebook-twin-option-twin_grounded"));

    await waitFor(() =>
      expect(onAppendBlock).toHaveBeenCalledWith({
        block_type: "note",
        content: {
          type: "note_block",
          attrs: { note_id: "twin_grounded" },
        },
        ref_id: "twin_grounded",
      }),
    );
  });

  it("renders current twin text instead of stale stored block text", () => {
    render(
      <NotebookCanvas
        notebook={{
          ...notebook,
          blocks: [
            {
              block_id: "b_1",
              block_index: 0,
              block_type: "note",
              ref_id: "twin_live",
              content_json: { text: "stale text" },
              created_at: "2026-07-12T00:00:00Z",
            },
          ],
        }}
        onAppendBlock={vi.fn()}
        twinNotes={[
          {
            note_id: "twin_live",
            asset_id: "paper_1",
            kind: "insight",
            text: "Current substrate text",
          },
        ]}
        twinNotesLoaded
      />,
    );

    expect(screen.getByText("Current substrate text")).toBeTruthy();
    expect(screen.queryByText("stale text")).toBeNull();
  });

  it("renders an unavailable state instead of cached text for a missing twin", () => {
    render(
      <NotebookCanvas
        notebook={{
          ...notebook,
          blocks: [
            {
              block_id: "b_missing",
              block_index: 0,
              block_type: "note",
              ref_id: "twin_missing",
              content_json: { text: "cached but untrusted" },
              created_at: "2026-07-12T00:00:00Z",
            },
          ],
        }}
        onAppendBlock={vi.fn()}
        twinNotes={[]}
        twinNotesLoaded
      />,
    );

    expect(screen.getByText(/twin note unavailable: twin_missing/i)).toBeTruthy();
    expect(screen.queryByText("cached but untrusted")).toBeNull();
  });

  it("does not present cached twin text while live resolution is pending", () => {
    render(
      <NotebookCanvas
        notebook={{
          ...notebook,
          blocks: [
            {
              block_id: "b_pending",
              block_index: 0,
              block_type: "note",
              ref_id: "twin_pending",
              content_json: { text: "cached pending text" },
              created_at: "2026-07-12T00:00:00Z",
            },
          ],
        }}
        onAppendBlock={vi.fn()}
        twinNotes={[]}
        twinNotesLoaded={false}
      />,
    );

    expect(screen.getByText(/loading twin note: twin_pending/i)).toBeTruthy();
    expect(screen.queryByText("cached pending text")).toBeNull();
  });
});
