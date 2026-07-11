import { afterEach, describe, expect, it } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import ResearchWrestleSessionSupercomposePanel from "./ResearchWrestleSessionSupercomposePanel";

afterEach(() => {
  cleanup();
});

describe("ResearchWrestleSessionSupercomposePanel", () => {
  it("composes wrestle_ready without authorizing dispatch", async () => {
    render(<ResearchWrestleSessionSupercomposePanel />);
    fireEvent.click(screen.getByTestId("rwss-compose"));
    await waitFor(() => {
      expect(screen.getByTestId("rwss-ready").textContent).toMatch(/true/);
      expect(screen.getByTestId("rwss-live").textContent).toMatch(/false/);
    });
  });

  it("zero sources not ready", async () => {
    render(<ResearchWrestleSessionSupercomposePanel />);
    fireEvent.change(screen.getByTestId("rwss-sources"), {
      target: { value: "0" },
    });
    fireEvent.click(screen.getByTestId("rwss-compose"));
    await waitFor(() => {
      expect(screen.getByTestId("rwss-ready").textContent).toMatch(/false/);
      expect(screen.getByTestId("rwss-live").textContent).toMatch(/false/);
    });
  });
});
