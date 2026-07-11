import { afterEach, describe, expect, it } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import MidnightOilUnattendedPackagePanel from "./MidnightOilUnattendedPackagePanel";

afterEach(() => {
  cleanup();
});

describe("MidnightOilUnattendedPackagePanel", () => {
  it("package ready without live execution", async () => {
    render(<MidnightOilUnattendedPackagePanel />);
    fireEvent.click(screen.getByTestId("mouap-compose"));
    await waitFor(() => {
      expect(screen.getByTestId("mouap-ready").textContent).toMatch(/true/);
      expect(screen.getByTestId("mouap-live").textContent).toMatch(/false/);
    });
  });

  it("unattended off blocks package", async () => {
    render(<MidnightOilUnattendedPackagePanel />);
    fireEvent.click(screen.getByTestId("mouap-unattended"));
    fireEvent.click(screen.getByTestId("mouap-compose"));
    await waitFor(() => {
      expect(screen.getByTestId("mouap-ready").textContent).toMatch(/false/);
      expect(screen.getByTestId("mouap-live").textContent).toMatch(/false/);
    });
  });
});
