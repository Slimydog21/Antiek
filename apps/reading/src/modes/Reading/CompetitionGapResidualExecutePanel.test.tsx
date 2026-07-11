import { afterEach, describe, expect, it } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import CompetitionGapResidualExecutePanel from "./CompetitionGapResidualExecutePanel";

afterEach(() => {
  cleanup();
});

describe("CompetitionGapResidualExecutePanel", () => {
  it("packages residual without authorizing execution", async () => {
    render(<CompetitionGapResidualExecutePanel />);
    fireEvent.click(screen.getByTestId("cgre-compose"));
    await waitFor(() => {
      expect(screen.getByTestId("cgre-ready").textContent).toMatch(/true/);
      expect(screen.getByTestId("cgre-exec").textContent).toMatch(/false/);
      expect(screen.getByTestId("cgre-backlog").textContent).toMatch(/false/);
    });
  });

  it("no ack not ready", async () => {
    render(<CompetitionGapResidualExecutePanel />);
    fireEvent.click(screen.getByTestId("cgre-ack"));
    fireEvent.click(screen.getByTestId("cgre-compose"));
    await waitFor(() => {
      expect(screen.getByTestId("cgre-ready").textContent).toMatch(/false/);
      expect(screen.getByTestId("cgre-exec").textContent).toMatch(/false/);
    });
  });
});
