import { afterEach, describe, expect, it } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import CompetitionDrQualitySourcePackPanel from "./CompetitionDrQualitySourcePackPanel";

afterEach(() => {
  cleanup();
});

describe("CompetitionDrQualitySourcePackPanel", () => {
  it("pack ready without live dispatch", async () => {
    render(<CompetitionDrQualitySourcePackPanel />);
    fireEvent.click(screen.getByTestId("cdqsp-compose"));
    await waitFor(() => {
      expect(screen.getByTestId("cdqsp-ready").textContent).toMatch(/true/);
      expect(screen.getByTestId("cdqsp-live").textContent).toMatch(/false/);
      expect(screen.getByTestId("cdqsp-remote").textContent).toMatch(/false/);
      expect(screen.getByTestId("cdqsp-backlog").textContent).toMatch(/false/);
    });
  });

  it("require no behind blocks pack", async () => {
    render(<CompetitionDrQualitySourcePackPanel />);
    fireEvent.click(screen.getByTestId("cdqsp-no-behind"));
    fireEvent.click(screen.getByTestId("cdqsp-compose"));
    await waitFor(() => {
      expect(screen.getByTestId("cdqsp-ready").textContent).toMatch(/false/);
      expect(screen.getByTestId("cdqsp-live").textContent).toMatch(/false/);
    });
  });
});
