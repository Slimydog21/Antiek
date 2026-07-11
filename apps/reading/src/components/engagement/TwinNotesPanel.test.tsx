import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import TwinNotesPanel from "./TwinNotesPanel";
import type { ListTwinsResult, TwinDocument } from "../../api/twinNotes";

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

const sample: TwinDocument = {
  twin_id: "twin-1",
  parent_asset_id: "asset-1",
  insights: ["insight A"],
  questions: ["q?"],
  source_label: "note-taker",
  created_at: 1,
  updated_at: 2,
  merged_from: [],
};

const listSample: ListTwinsResult = {
  parent_asset_id: "asset-1",
  twins: [sample],
};

describe("TwinNotesPanel", () => {
  it("records a twin via injectable recordFn", async () => {
    const recordFn = vi.fn(async () => sample);
    render(
      <TwinNotesPanel
        recordFn={recordFn}
        initialParentAssetId="asset-1"
      />,
    );
    fireEvent.change(screen.getByTestId("twin-notes-insights"), {
      target: { value: "insight A\n" },
    });
    fireEvent.change(screen.getByTestId("twin-notes-questions"), {
      target: { value: "q?\n" },
    });
    fireEvent.click(screen.getByTestId("twin-notes-record"));
    await waitFor(() => {
      expect(screen.getByTestId("twin-notes-recorded").textContent).toMatch(
        /twin-1/,
      );
    });
    expect(recordFn).toHaveBeenCalledWith({
      parent_asset_id: "asset-1",
      insights: ["insight A"],
      questions: ["q?"],
      source_label: "note-taker",
    });
  });

  it("lists twins by parent", async () => {
    const listFn = vi.fn(async () => listSample);
    render(
      <TwinNotesPanel listFn={listFn} initialParentAssetId="asset-1" />,
    );
    fireEvent.click(screen.getByTestId("twin-notes-list"));
    await waitFor(() => {
      expect(screen.getByTestId("twin-notes-list-count").textContent).toMatch(
        /1 twin/,
      );
    });
    expect(listFn).toHaveBeenCalledWith("asset-1");
  });

  it("surfaces merge errors without success banner", async () => {
    const mergeFn = vi.fn(async () => {
      throw new Error("cross_parent_merge_rejected");
    });
    render(
      <TwinNotesPanel mergeFn={mergeFn} initialParentAssetId="asset-1" />,
    );
    fireEvent.change(screen.getByTestId("twin-notes-merge-ids"), {
      target: { value: "t1, t2" },
    });
    fireEvent.click(screen.getByTestId("twin-notes-merge"));
    await waitFor(() => {
      expect(screen.getByTestId("twin-notes-error").textContent).toMatch(
        /cross_parent/,
      );
    });
    expect(screen.queryByTestId("twin-notes-merged")).toBeNull();
  });

  it("rejects injectable empty twin_id without rendering success", async () => {
    const recordFn = vi.fn(async () => ({ ...sample, twin_id: "" }));
    render(
      <TwinNotesPanel recordFn={recordFn} initialParentAssetId="asset-1" />,
    );
    fireEvent.click(screen.getByTestId("twin-notes-record"));
    await waitFor(() => {
      expect(screen.getByTestId("twin-notes-error").textContent).toMatch(
        /twin_id/,
      );
    });
    expect(screen.queryByTestId("twin-notes-recorded")).toBeNull();
  });
});
