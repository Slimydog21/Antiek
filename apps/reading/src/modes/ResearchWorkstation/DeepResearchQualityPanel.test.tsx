import { afterEach, describe, expect, it } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import DeepResearchQualityPanel from "./DeepResearchQualityPanel";

afterEach(() => {
  cleanup();
});

describe("DeepResearchQualityPanel", () => {
  it("evaluates with overall and persisted false", async () => {
    render(<DeepResearchQualityPanel initialResearchId="dr-1" />);
    fireEvent.change(screen.getByTestId("drq-score-citation_density"), {
      target: { value: "0.8" },
    });
    fireEvent.change(screen.getByTestId("drq-score-intellectual_honesty"), {
      target: { value: "0.9" },
    });
    fireEvent.click(screen.getByTestId("drq-run"));
    await waitFor(() => {
      expect(screen.getByTestId("drq-persisted").textContent).toMatch(/false/);
      expect(screen.getByTestId("drq-overall").textContent).not.toMatch(
        /overall=null/,
      );
    });
  });

  it("overall null when all blank", async () => {
    render(<DeepResearchQualityPanel initialResearchId="dr-2" />);
    fireEvent.click(screen.getByTestId("drq-run"));
    await waitFor(() => {
      expect(screen.getByTestId("drq-overall").textContent).toMatch(/null/);
      expect(screen.getByTestId("drq-persisted").textContent).toMatch(/false/);
    });
  });

  it("surfaces validation errors", async () => {
    render(<DeepResearchQualityPanel initialResearchId="" />);
    fireEvent.click(screen.getByTestId("drq-run"));
    await waitFor(() => {
      expect(screen.getByTestId("drq-error").textContent).toMatch(
        /research_id/,
      );
    });
  });
});
