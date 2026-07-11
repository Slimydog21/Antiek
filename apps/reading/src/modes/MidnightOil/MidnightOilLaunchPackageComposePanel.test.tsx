import { afterEach, describe, expect, it } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import MidnightOilLaunchPackageComposePanel from "./MidnightOilLaunchPackageComposePanel";

afterEach(() => {
  cleanup();
});

describe("MidnightOilLaunchPackageComposePanel", () => {
  it("composes package without live execution", async () => {
    render(<MidnightOilLaunchPackageComposePanel />);
    fireEvent.click(screen.getByTestId("molp-approved"));
    fireEvent.click(screen.getByTestId("molp-ack"));
    fireEvent.click(screen.getByTestId("molp-consent"));
    fireEvent.click(screen.getByTestId("molp-compose"));
    await waitFor(() => {
      expect(screen.getByTestId("molp-exec").textContent).toMatch(/false/);
      expect(screen.getByTestId("molp-ready").textContent).toMatch(/true/);
      expect(screen.getByTestId("molp-summary").textContent).toMatch(
        /MO package/,
      );
    });
  });

  it("without ack package not ready", async () => {
    render(<MidnightOilLaunchPackageComposePanel />);
    fireEvent.click(screen.getByTestId("molp-approved"));
    fireEvent.click(screen.getByTestId("molp-consent"));
    fireEvent.click(screen.getByTestId("molp-compose"));
    await waitFor(() => {
      expect(screen.getByTestId("molp-ready").textContent).toMatch(/false/);
      expect(screen.getByTestId("molp-exec").textContent).toMatch(/false/);
    });
  });

  it("blank rate shows null recommended", async () => {
    render(<MidnightOilLaunchPackageComposePanel />);
    fireEvent.change(screen.getByTestId("molp-rate"), {
      target: { value: "" },
    });
    fireEvent.click(screen.getByTestId("molp-compose"));
    await waitFor(() => {
      expect(screen.getByTestId("molp-recommended").textContent).toMatch(
        /null/,
      );
      expect(screen.getByTestId("molp-exec").textContent).toMatch(/false/);
    });
  });
});
