import { afterEach, describe, expect, it } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import CollectiveDeepResearchMergePanel from "./CollectiveDeepResearchMergePanel";

afterEach(() => {
  cleanup();
});

describe("CollectiveDeepResearchMergePanel", () => {
  it("draft intent never writes", async () => {
    render(<CollectiveDeepResearchMergePanel />);
    fireEvent.click(screen.getByTestId("cdrm-draft"));
    await waitFor(() => {
      expect(screen.getByTestId("cdrm-written").textContent).toMatch(/false/);
      expect(screen.getByTestId("cdrm-summary").textContent).toMatch(
        /draft_analysis/,
      );
    });
  });

  it("full without ack fails closed", async () => {
    render(<CollectiveDeepResearchMergePanel />);
    fireEvent.click(screen.getByTestId("cdrm-full"));
    await waitFor(() => {
      expect(screen.getByTestId("cdrm-error").textContent).toMatch(
        /operator_ack/,
      );
    });
  });

  it("full with ack succeeds without writing", async () => {
    render(<CollectiveDeepResearchMergePanel />);
    fireEvent.click(screen.getByTestId("cdrm-ack"));
    fireEvent.click(screen.getByTestId("cdrm-full"));
    await waitFor(() => {
      expect(screen.getByTestId("cdrm-written").textContent).toMatch(/false/);
      expect(screen.getByTestId("cdrm-summary").textContent).toMatch(
        /full_analysis/,
      );
    });
  });
});
