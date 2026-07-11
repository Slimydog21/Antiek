import { afterEach, describe, expect, it } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import TwinSubstrateCrossAssetMergePanel from "./TwinSubstrateCrossAssetMergePanel";

afterEach(() => {
  cleanup();
});

describe("TwinSubstrateCrossAssetMergePanel", () => {
  it("composes merge_ready without executing", async () => {
    render(<TwinSubstrateCrossAssetMergePanel />);
    fireEvent.click(screen.getByTestId("tscam-compose"));
    await waitFor(() => {
      expect(screen.getByTestId("tscam-ready").textContent).toMatch(/true/);
      expect(screen.getByTestId("tscam-merged").textContent).toMatch(/false/);
      expect(screen.getByTestId("tscam-written").textContent).toMatch(/false/);
      expect(screen.getByTestId("tscam-store").textContent).toMatch(/false/);
    });
  });

  it("no ack not ready", async () => {
    render(<TwinSubstrateCrossAssetMergePanel />);
    fireEvent.click(screen.getByTestId("tscam-ack"));
    fireEvent.click(screen.getByTestId("tscam-compose"));
    await waitFor(() => {
      expect(screen.getByTestId("tscam-ready").textContent).toMatch(/false/);
      expect(screen.getByTestId("tscam-merged").textContent).toMatch(/false/);
    });
  });
});
