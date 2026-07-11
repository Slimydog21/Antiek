import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import LlmNoteTakerPanel from "./LlmNoteTakerPanel";
import type { TwinNotePayload } from "../../api/twinLlmNoteTaker";

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

const sample: TwinNotePayload = {
  parent_asset_id: "asset-1",
  insights: ["a"],
  questions: ["q?"],
  source_label: "llm-note-taker",
  llm_filled: true,
  asset_text_sha256: null,
  notes: [],
  authority: "note_taker_payload_only",
  model_invoked: false,
};

describe("LlmNoteTakerPanel", () => {
  it("builds payload via injectable", async () => {
    const payloadFn = vi.fn(async () => sample);
    render(
      <LlmNoteTakerPanel
        payloadFn={payloadFn}
        initialParentAssetId="asset-1"
        gated={false}
      />,
    );
    fireEvent.change(screen.getByTestId("lnt-insights"), {
      target: { value: "a\n" },
    });
    fireEvent.change(screen.getByTestId("lnt-questions"), {
      target: { value: "q?\n" },
    });
    fireEvent.click(screen.getByTestId("lnt-build"));
    await waitFor(() => {
      expect(screen.getByTestId("lnt-counts").textContent).toMatch(
        /insights=1/,
      );
    });
    expect(payloadFn).toHaveBeenCalledWith({
      parent_asset_id: "asset-1",
      insights: ["a"],
      questions: ["q?"],
      llm_filled: true,
      gated: false,
    });
  });

  it("surfaces gated provenance", async () => {
    const payloadFn = vi.fn(async () => sample);
    render(
      <LlmNoteTakerPanel
        payloadFn={payloadFn}
        initialParentAssetId="a"
        gated={true}
      />,
    );
    fireEvent.change(screen.getByTestId("lnt-insights"), {
      target: { value: "x" },
    });
    fireEvent.click(screen.getByTestId("lnt-build"));
    await waitFor(() => {
      expect(payloadFn).toHaveBeenCalledWith(
        expect.objectContaining({ gated: true }),
      );
    });
  });

  it("rejects model_invoked invent", async () => {
    const payloadFn = vi.fn(async () => ({ ...sample, model_invoked: true }));
    render(
      <LlmNoteTakerPanel
        payloadFn={payloadFn}
        initialParentAssetId="a"
        gated={false}
      />,
    );
    fireEvent.change(screen.getByTestId("lnt-insights"), {
      target: { value: "x" },
    });
    fireEvent.click(screen.getByTestId("lnt-build"));
    await waitFor(() => {
      expect(screen.getByTestId("lnt-error").textContent).toMatch(
        /model_invoked/,
      );
    });
  });
});
