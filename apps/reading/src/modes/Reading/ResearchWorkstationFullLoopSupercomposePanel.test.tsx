import { afterEach, describe, expect, it } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import ResearchWorkstationFullLoopSupercomposePanel from "./ResearchWorkstationFullLoopSupercomposePanel";

afterEach(() => {
  cleanup();
});

describe("ResearchWorkstationFullLoopSupercomposePanel", () => {
  it("composes full_loop_ready without dispatch", async () => {
    render(<ResearchWorkstationFullLoopSupercomposePanel />);
    fireEvent.click(screen.getByTestId("rwfl-compose"));
    await waitFor(() => {
      expect(screen.getByTestId("rwfl-ready").textContent).toMatch(/true/);
      expect(screen.getByTestId("rwfl-live").textContent).toMatch(/false/);
    });
  });

  it("attach off not full ready", async () => {
    render(<ResearchWorkstationFullLoopSupercomposePanel />);
    fireEvent.click(screen.getByTestId("rwfl-attach"));
    fireEvent.click(screen.getByTestId("rwfl-compose"));
    await waitFor(() => {
      expect(screen.getByTestId("rwfl-ready").textContent).toMatch(/false/);
      expect(screen.getByTestId("rwfl-live").textContent).toMatch(/false/);
    });
  });
});
