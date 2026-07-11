import { afterEach, describe, expect, it } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import RecursiveTwinBindPanel from "./RecursiveTwinBindPanel";

afterEach(() => {
  cleanup();
});

describe("RecursiveTwinBindPanel", () => {
  it("evaluates operator bind with twin_created false", async () => {
    render(
      <RecursiveTwinBindPanel gated={false} initialParentAssetId="asset-1" />,
    );
    fireEvent.click(screen.getByTestId("rtb-run"));
    await waitFor(() => {
      expect(screen.getByTestId("rtb-bind-allowed").textContent).toMatch(
        /true/,
      );
      expect(screen.getByTestId("rtb-twin-created").textContent).toMatch(
        /false/,
      );
    });
  });

  it("blocks gated assets", async () => {
    render(
      <RecursiveTwinBindPanel gated={true} initialParentAssetId="asset-1" />,
    );
    fireEvent.click(screen.getByTestId("rtb-run"));
    await waitFor(() => {
      expect(screen.getByTestId("rtb-bind-allowed").textContent).toMatch(
        /false/,
      );
    });
  });

  it("surfaces llm_note_taker provenance errors", async () => {
    render(
      <RecursiveTwinBindPanel gated={false} initialParentAssetId="asset-1" />,
    );
    fireEvent.change(screen.getByTestId("rtb-source"), {
      target: { value: "llm_note_taker" },
    });
    fireEvent.click(screen.getByTestId("rtb-llm-filled"));
    fireEvent.click(screen.getByTestId("rtb-run"));
    await waitFor(() => {
      expect(screen.getByTestId("rtb-error").textContent).toMatch(/non-empty/);
    });
  });

  it("accepts operator insights lines", async () => {
    render(
      <RecursiveTwinBindPanel gated={false} initialParentAssetId="asset-1" />,
    );
    fireEvent.change(screen.getByTestId("rtb-insights"), {
      target: { value: "insight one\ninsight two" },
    });
    fireEvent.click(screen.getByTestId("rtb-run"));
    await waitFor(() => {
      expect(screen.getByTestId("rtb-summary").textContent).toMatch(
        /insights=2/,
      );
    });
  });
});
