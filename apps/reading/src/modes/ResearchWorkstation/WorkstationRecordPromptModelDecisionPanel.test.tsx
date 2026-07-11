import { afterEach, describe, expect, it } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import WorkstationRecordPromptModelDecisionPanel from "./WorkstationRecordPromptModelDecisionPanel";

afterEach(() => {
  cleanup();
});

describe("WorkstationRecordPromptModelDecisionPanel", () => {
  it("pack ready without inject or live router", async () => {
    render(<WorkstationRecordPromptModelDecisionPanel />);
    fireEvent.click(screen.getByTestId("wrpmd-compose"));
    await waitFor(() => {
      expect(screen.getByTestId("wrpmd-ready").textContent).toMatch(/true/);
      expect(screen.getByTestId("wrpmd-usage").textContent).toMatch(/40/);
      expect(screen.getByTestId("wrpmd-would").textContent).toMatch(/false/);
      expect(screen.getByTestId("wrpmd-inject").textContent).toMatch(/false/);
      expect(screen.getByTestId("wrpmd-router").textContent).toMatch(/false/);
    });
  });

  it("no ack not ready", async () => {
    render(<WorkstationRecordPromptModelDecisionPanel />);
    fireEvent.click(screen.getByTestId("wrpmd-ack"));
    fireEvent.click(screen.getByTestId("wrpmd-compose"));
    await waitFor(() => {
      expect(screen.getByTestId("wrpmd-ready").textContent).toMatch(/false/);
      expect(screen.getByTestId("wrpmd-inject").textContent).toMatch(/false/);
    });
  });
});
