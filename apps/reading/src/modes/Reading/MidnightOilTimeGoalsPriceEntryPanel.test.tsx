import { afterEach, describe, expect, it } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import MidnightOilTimeGoalsPriceEntryPanel from "./MidnightOilTimeGoalsPriceEntryPanel";

afterEach(() => {
  cleanup();
});

describe("MidnightOilTimeGoalsPriceEntryPanel", () => {
  it("entry ready without authorizing execution", async () => {
    render(<MidnightOilTimeGoalsPriceEntryPanel />);
    fireEvent.click(screen.getByTestId("motgpe-compose"));
    await waitFor(() => {
      expect(screen.getByTestId("motgpe-ready").textContent).toMatch(/true/);
      expect(screen.getByTestId("motgpe-live").textContent).toMatch(/false/);
    });
  });
});
