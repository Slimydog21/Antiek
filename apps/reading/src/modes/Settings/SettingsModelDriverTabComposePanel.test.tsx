import { afterEach, describe, expect, it } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import SettingsModelDriverTabComposePanel from "./SettingsModelDriverTabComposePanel";

afterEach(() => {
  cleanup();
});

describe("SettingsModelDriverTabComposePanel", () => {
  it("composes without live router or secrets", async () => {
    render(<SettingsModelDriverTabComposePanel />);
    fireEvent.click(screen.getByTestId("smdt-compose"));
    await waitFor(() => {
      expect(screen.getByTestId("smdt-router").textContent).toMatch(/false/);
      expect(screen.getByTestId("smdt-secrets").textContent).toMatch(/false/);
      expect(screen.getByTestId("smdt-ready").textContent).toMatch(/true/);
    });
  });

  it("rejects secret-like pending id", async () => {
    render(<SettingsModelDriverTabComposePanel />);
    fireEvent.change(screen.getByTestId("smdt-pending"), {
      target: { value: "sk-abc123" },
    });
    fireEvent.click(screen.getByTestId("smdt-compose"));
    await waitFor(() => {
      expect(screen.getByTestId("smdt-error").textContent).toMatch(
        /secret material/,
      );
    });
  });
});
