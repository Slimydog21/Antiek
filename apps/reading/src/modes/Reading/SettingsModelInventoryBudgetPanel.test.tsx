import { afterEach, describe, expect, it } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import SettingsModelInventoryBudgetPanel from "./SettingsModelInventoryBudgetPanel";

afterEach(() => {
  cleanup();
});

describe("SettingsModelInventoryBudgetPanel", () => {
  it("composes inventory and remaining without secrets", async () => {
    render(<SettingsModelInventoryBudgetPanel />);
    fireEvent.click(screen.getByTestId("smib-compose"));
    await waitFor(() => {
      expect(screen.getByTestId("smib-inv").textContent).toMatch(/2/);
      expect(screen.getByTestId("smib-secrets").textContent).toMatch(/false/);
      expect(screen.getByTestId("smib-router").textContent).toMatch(/false/);
      expect(screen.getByTestId("smib-remaining").textContent).toMatch(/37\.5/);
    });
  });
});
