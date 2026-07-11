import { afterEach, describe, expect, it } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import AntiekBenchTaskFamilyExpandPanel from "./AntiekBenchTaskFamilyExpandPanel";

afterEach(() => {
  cleanup();
});

describe("AntiekBenchTaskFamilyExpandPanel", () => {
  it("expand ready without suite rewrite", async () => {
    render(<AntiekBenchTaskFamilyExpandPanel />);
    fireEvent.click(screen.getByTestId("abtf-compose"));
    await waitFor(() => {
      expect(screen.getByTestId("abtf-ready").textContent).toMatch(/true/);
      expect(screen.getByTestId("abtf-backlog").textContent).toMatch(/false/);
      expect(screen.getByTestId("abtf-store").textContent).toMatch(/false/);
      expect(screen.getByTestId("abtf-suite").textContent).toMatch(/false/);
    });
  });

  it("no ack not ready", async () => {
    render(<AntiekBenchTaskFamilyExpandPanel />);
    fireEvent.click(screen.getByTestId("abtf-ack"));
    fireEvent.click(screen.getByTestId("abtf-compose"));
    await waitFor(() => {
      expect(screen.getByTestId("abtf-ready").textContent).toMatch(/false/);
      expect(screen.getByTestId("abtf-suite").textContent).toMatch(/false/);
    });
  });
});
