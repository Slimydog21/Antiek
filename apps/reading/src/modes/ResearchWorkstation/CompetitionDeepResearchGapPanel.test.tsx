import { afterEach, describe, expect, it } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import CompetitionDeepResearchGapPanel from "./CompetitionDeepResearchGapPanel";

afterEach(() => {
  cleanup();
});

describe("CompetitionDeepResearchGapPanel", () => {
  it("builds empty matrix with backlog false", async () => {
    render(<CompetitionDeepResearchGapPanel />);
    fireEvent.click(screen.getByTestId("cdrg-run"));
    await waitFor(() => {
      expect(screen.getByTestId("cdrg-backlog").textContent).toMatch(/false/);
      expect(screen.getByTestId("cdrg-behind").textContent).toMatch(
        /behind_count=0/,
      );
    });
  });

  it("adds row and counts behind", async () => {
    render(<CompetitionDeepResearchGapPanel />);
    fireEvent.change(screen.getByTestId("cdrg-competitor"), {
      target: { value: "Elicit" },
    });
    fireEvent.change(screen.getByTestId("cdrg-summary-input"), {
      target: { value: "Paper-grounded claims" },
    });
    fireEvent.change(screen.getByTestId("cdrg-status"), {
      target: { value: "behind" },
    });
    fireEvent.change(screen.getByTestId("cdrg-residual"), {
      target: { value: "Wire citation spans" },
    });
    fireEvent.click(screen.getByTestId("cdrg-add"));
    fireEvent.click(screen.getByTestId("cdrg-run"));
    await waitFor(() => {
      expect(screen.getByTestId("cdrg-behind").textContent).toMatch(
        /behind_count=1/,
      );
      expect(screen.getByTestId("cdrg-backlog").textContent).toMatch(/false/);
    });
  });
});
