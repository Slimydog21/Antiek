import { afterEach, describe, expect, it } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import ReadingResearchHtmlParityComposePanel from "./ReadingResearchHtmlParityComposePanel";

afterEach(() => {
  cleanup();
});

describe("ReadingResearchHtmlParityComposePanel", () => {
  it("composes parity without pdf primary", async () => {
    render(<ReadingResearchHtmlParityComposePanel />);
    fireEvent.click(screen.getByTestId("rrhp-compose"));
    await waitFor(() => {
      expect(screen.getByTestId("rrhp-pdf").textContent).toMatch(/false/);
      expect(screen.getByTestId("rrhp-parity").textContent).toMatch(/true/);
      expect(screen.getByTestId("rrhp-summary").textContent).toMatch(
        /html parity/,
      );
    });
  });

  it("blank shas are not parity-ready", async () => {
    render(<ReadingResearchHtmlParityComposePanel />);
    fireEvent.change(screen.getByTestId("rrhp-read-sha"), {
      target: { value: "" },
    });
    fireEvent.change(screen.getByTestId("rrhp-research-sha"), {
      target: { value: "" },
    });
    fireEvent.click(screen.getByTestId("rrhp-compose"));
    await waitFor(() => {
      expect(screen.getByTestId("rrhp-parity").textContent).toMatch(/false/);
      expect(screen.getByTestId("rrhp-pdf").textContent).toMatch(/false/);
    });
  });
});
