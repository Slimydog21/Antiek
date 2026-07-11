import { afterEach, describe, expect, it } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import ResearchWrestleCompetitionQualityPanel from "./ResearchWrestleCompetitionQualityPanel";

afterEach(() => {
  cleanup();
});

describe("ResearchWrestleCompetitionQualityPanel", () => {
  it("session ready without live dispatch", async () => {
    render(<ResearchWrestleCompetitionQualityPanel />);
    fireEvent.click(screen.getByTestId("rwcq-compose"));
    await waitFor(() => {
      expect(screen.getByTestId("rwcq-ready").textContent).toMatch(/true/);
      expect(screen.getByTestId("rwcq-wrestle").textContent).toMatch(/true/);
      expect(screen.getByTestId("rwcq-pack").textContent).toMatch(/true/);
      expect(screen.getByTestId("rwcq-live").textContent).toMatch(/false/);
      expect(screen.getByTestId("rwcq-remote").textContent).toMatch(/false/);
      expect(screen.getByTestId("rwcq-backlog").textContent).toMatch(/false/);
    });
  });

  it("require no behind blocks session", async () => {
    render(<ResearchWrestleCompetitionQualityPanel />);
    fireEvent.click(screen.getByTestId("rwcq-no-behind"));
    fireEvent.click(screen.getByTestId("rwcq-compose"));
    await waitFor(() => {
      expect(screen.getByTestId("rwcq-ready").textContent).toMatch(/false/);
      expect(screen.getByTestId("rwcq-live").textContent).toMatch(/false/);
    });
  });
});
