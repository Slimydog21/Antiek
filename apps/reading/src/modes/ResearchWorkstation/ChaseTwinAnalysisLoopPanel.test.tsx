import { afterEach, describe, expect, it } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import ChaseTwinAnalysisLoopPanel from "./ChaseTwinAnalysisLoopPanel";

afterEach(() => {
  cleanup();
});

describe("ChaseTwinAnalysisLoopPanel", () => {
  it("loop ready without writes or dispatch", async () => {
    render(<ChaseTwinAnalysisLoopPanel />);
    fireEvent.click(screen.getByTestId("ctal-compose"));
    await waitFor(() => {
      expect(screen.getByTestId("ctal-ready").textContent).toMatch(/true/);
      expect(screen.getByTestId("ctal-live").textContent).toMatch(/false/);
      expect(screen.getByTestId("ctal-twin").textContent).toMatch(/false/);
      expect(screen.getByTestId("ctal-analysis").textContent).toMatch(/false/);
    });
  });

  it("no ack not ready", async () => {
    render(<ChaseTwinAnalysisLoopPanel />);
    fireEvent.click(screen.getByTestId("ctal-ack"));
    fireEvent.click(screen.getByTestId("ctal-compose"));
    await waitFor(() => {
      expect(screen.getByTestId("ctal-ready").textContent).toMatch(/false/);
      expect(screen.getByTestId("ctal-live").textContent).toMatch(/false/);
    });
  });
});
