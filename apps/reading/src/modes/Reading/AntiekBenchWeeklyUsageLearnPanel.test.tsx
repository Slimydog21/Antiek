import { afterEach, describe, expect, it } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import AntiekBenchWeeklyUsageLearnPanel from "./AntiekBenchWeeklyUsageLearnPanel";

afterEach(() => {
  cleanup();
});

describe("AntiekBenchWeeklyUsageLearnPanel", () => {
  it("composes learn proposals without mutating store", async () => {
    render(<AntiekBenchWeeklyUsageLearnPanel />);
    fireEvent.click(screen.getByTestId("abwul-compose"));
    await waitFor(() => {
      expect(screen.getByTestId("abwul-ready").textContent).toMatch(/true/);
      expect(screen.getByTestId("abwul-backlog").textContent).toMatch(/false/);
      expect(screen.getByTestId("abwul-store").textContent).toMatch(/false/);
    });
  });

  it("no ack not ready", async () => {
    render(<AntiekBenchWeeklyUsageLearnPanel />);
    fireEvent.click(screen.getByTestId("abwul-ack"));
    fireEvent.click(screen.getByTestId("abwul-compose"));
    await waitFor(() => {
      expect(screen.getByTestId("abwul-ready").textContent).toMatch(/false/);
      expect(screen.getByTestId("abwul-backlog").textContent).toMatch(/false/);
    });
  });
});
