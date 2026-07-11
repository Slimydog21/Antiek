import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import HighlightTwinPanel from "./HighlightTwinPanel";
import type { HighlightTwinSeed } from "../../api/twinFromHighlight";

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

const sample: HighlightTwinSeed = {
  parent_asset_id: "asset-1",
  highlight: "A key sentence.",
  insights: ["insight"],
  questions: [],
  source_label: "highlight",
  notes: [],
  llm_filled: false,
  authority: "highlight_seed_only",
};

describe("HighlightTwinPanel", () => {
  it("seeds via injectable", async () => {
    const seedFn = vi.fn(async () => sample);
    render(
      <HighlightTwinPanel
        seedFn={seedFn}
        initialParentAssetId="asset-1"
        initialHighlight="A key sentence."
        gated={false}
      />,
    );
    fireEvent.change(screen.getByTestId("highlight-twin-insights"), {
      target: { value: "insight\n" },
    });
    fireEvent.click(screen.getByTestId("highlight-twin-seed"));
    await waitFor(() => {
      expect(screen.getByTestId("highlight-twin-echo").textContent).toMatch(
        /key sentence/,
      );
    });
    expect(seedFn).toHaveBeenCalledWith({
      parent_asset_id: "asset-1",
      highlight: "A key sentence.",
      insights: ["insight"],
      questions: [],
      gated: false,
    });
  });

  it("surfaces errors", async () => {
    const seedFn = vi.fn(async () => {
      throw new Error("gated/withheld");
    });
    render(
      <HighlightTwinPanel
        seedFn={seedFn}
        initialParentAssetId="a"
        initialHighlight="x"
        gated={false}
      />,
    );
    fireEvent.click(screen.getByTestId("highlight-twin-seed"));
    await waitFor(() => {
      expect(screen.getByTestId("highlight-twin-error").textContent).toMatch(
        /gated/,
      );
    });
  });

  it("rejects llm_filled invent", async () => {
    const seedFn = vi.fn(async () => ({ ...sample, llm_filled: true }));
    render(
      <HighlightTwinPanel
        seedFn={seedFn}
        initialParentAssetId="a"
        initialHighlight="x"
        gated={false}
      />,
    );
    fireEvent.click(screen.getByTestId("highlight-twin-seed"));
    await waitFor(() => {
      expect(screen.getByTestId("highlight-twin-error").textContent).toMatch(
        /llm_filled/,
      );
    });
  });

  it("passes gated true through and does not invent ungated", async () => {
    const seedFn = vi.fn(async () => sample);
    render(
      <HighlightTwinPanel
        seedFn={seedFn}
        initialParentAssetId="a"
        initialHighlight="secret"
        gated={true}
      />,
    );
    fireEvent.click(screen.getByTestId("highlight-twin-seed"));
    await waitFor(() => {
      expect(seedFn).toHaveBeenCalledWith(
        expect.objectContaining({ gated: true }),
      );
    });
  });
});
