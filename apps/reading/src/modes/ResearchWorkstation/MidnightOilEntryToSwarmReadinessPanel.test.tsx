import { afterEach, describe, expect, it } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import MidnightOilEntryToSwarmReadinessPanel from "./MidnightOilEntryToSwarmReadinessPanel";

afterEach(() => {
  cleanup();
});

describe("MidnightOilEntryToSwarmReadinessPanel", () => {
  it("package ready without live execution", async () => {
    render(<MidnightOilEntryToSwarmReadinessPanel />);
    fireEvent.click(screen.getByTestId("moesr-compose"));
    await waitFor(() => {
      expect(screen.getByTestId("moesr-ready").textContent).toMatch(/true/);
      expect(screen.getByTestId("moesr-live").textContent).toMatch(/false/);
    });
  });

  it("unattended off blocks package", async () => {
    render(<MidnightOilEntryToSwarmReadinessPanel />);
    fireEvent.click(screen.getByTestId("moesr-unattended"));
    fireEvent.click(screen.getByTestId("moesr-compose"));
    await waitFor(() => {
      expect(screen.getByTestId("moesr-ready").textContent).toMatch(/false/);
      expect(screen.getByTestId("moesr-live").textContent).toMatch(/false/);
    });
  });
});
