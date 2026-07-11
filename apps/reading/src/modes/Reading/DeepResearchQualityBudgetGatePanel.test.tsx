import { afterEach, describe, expect, it } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import DeepResearchQualityBudgetGatePanel from "./DeepResearchQualityBudgetGatePanel";

afterEach(() => {
  cleanup();
});

describe("DeepResearchQualityBudgetGatePanel", () => {
  it("gate ready without dispatch", async () => {
    render(<DeepResearchQualityBudgetGatePanel />);
    fireEvent.click(screen.getByTestId("drqbg-compose"));
    await waitFor(() => {
      expect(screen.getByTestId("drqbg-ready").textContent).toMatch(/true/);
      expect(screen.getByTestId("drqbg-live").textContent).toMatch(/false/);
    });
  });
});
