import { afterEach, describe, expect, it } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import MarketplacePaidPurchaseGatePanel from "./MarketplacePaidPurchaseGatePanel";

afterEach(() => {
  cleanup();
});

describe("MarketplacePaidPurchaseGatePanel", () => {
  it("paid path gate ready without charge", async () => {
    render(<MarketplacePaidPurchaseGatePanel />);
    fireEvent.click(screen.getByTestId("mppg-compose"));
    await waitFor(() => {
      expect(screen.getByTestId("mppg-gate").textContent).toMatch(/true/);
      expect(screen.getByTestId("mppg-purchase").textContent).toMatch(/true/);
      expect(screen.getByTestId("mppg-exec").textContent).toMatch(/false/);
      expect(screen.getByTestId("mppg-charge").textContent).toMatch(/false/);
      expect(screen.getByTestId("mppg-hosted").textContent).toMatch(/false/);
      expect(screen.getByTestId("mppg-pdf").textContent).toMatch(/false/);
    });
  });

  it("budget exceed blocks purchase_ready", async () => {
    render(<MarketplacePaidPurchaseGatePanel />);
    fireEvent.change(screen.getByTestId("mppg-remaining"), {
      target: { value: "1" },
    });
    fireEvent.click(screen.getByTestId("mppg-compose"));
    await waitFor(() => {
      expect(screen.getByTestId("mppg-purchase").textContent).toMatch(/false/);
      expect(screen.getByTestId("mppg-would").textContent).toMatch(/true/);
      expect(screen.getByTestId("mppg-charge").textContent).toMatch(/false/);
    });
  });
});
