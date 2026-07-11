import { afterEach, describe, expect, it } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import SettingsDecisionTreeUsageBarPanel from "./SettingsDecisionTreeUsageBarPanel";

afterEach(() => {
  cleanup();
});

describe("SettingsDecisionTreeUsageBarPanel", () => {
  it("composes usage bar and projection honesty", async () => {
    render(<SettingsDecisionTreeUsageBarPanel />);
    fireEvent.click(screen.getByTestId("sdtub-compose"));
    await waitFor(() => {
      expect(screen.getByTestId("sdtub-ready").textContent).toMatch(/true/);
      expect(screen.getByTestId("sdtub-usage").textContent).toMatch(/40/);
      expect(screen.getByTestId("sdtub-would").textContent).toMatch(/false/);
      expect(screen.getByTestId("sdtub-router").textContent).toMatch(/false/);
      expect(screen.getByTestId("sdtub-secrets").textContent).toMatch(/false/);
      expect(screen.getByTestId("sdtub-meter").textContent).toMatch(/false/);
    });
  });

  it("no ack not decision_ready", async () => {
    render(<SettingsDecisionTreeUsageBarPanel />);
    fireEvent.click(screen.getByTestId("sdtub-ack"));
    fireEvent.click(screen.getByTestId("sdtub-compose"));
    await waitFor(() => {
      expect(screen.getByTestId("sdtub-ready").textContent).toMatch(/false/);
      expect(screen.getByTestId("sdtub-router").textContent).toMatch(/false/);
    });
  });
});
