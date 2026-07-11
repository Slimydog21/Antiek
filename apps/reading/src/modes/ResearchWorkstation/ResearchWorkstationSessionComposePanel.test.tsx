import { afterEach, describe, expect, it } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import ResearchWorkstationSessionComposePanel from "./ResearchWorkstationSessionComposePanel";

afterEach(() => {
  cleanup();
});

describe("ResearchWorkstationSessionComposePanel", () => {
  it("composes ready session without live dispatch", async () => {
    render(<ResearchWorkstationSessionComposePanel />);
    fireEvent.click(screen.getByTestId("rwsc-compose"));
    await waitFor(() => {
      expect(screen.getByTestId("rwsc-dispatch").textContent).toMatch(/false/);
      expect(screen.getByTestId("rwsc-ready").textContent).toMatch(/true/);
      expect(screen.getByTestId("rwsc-summary").textContent).toMatch(/session/);
    });
  });

  it("unknown quality fails closed", async () => {
    render(<ResearchWorkstationSessionComposePanel />);
    fireEvent.change(screen.getByTestId("rwsc-quality"), {
      target: { value: "null" },
    });
    fireEvent.click(screen.getByTestId("rwsc-compose"));
    await waitFor(() => {
      expect(screen.getByTestId("rwsc-ready").textContent).toMatch(/false/);
      expect(screen.getByTestId("rwsc-dispatch").textContent).toMatch(/false/);
    });
  });
});
