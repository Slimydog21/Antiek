import { afterEach, describe, expect, it } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import FloatingResearchDraftCombinedDocumentPanel from "./FloatingResearchDraftCombinedDocumentPanel";

afterEach(() => {
  cleanup();
});

describe("FloatingResearchDraftCombinedDocumentPanel", () => {
  it("composes draft without writing or merging", async () => {
    render(<FloatingResearchDraftCombinedDocumentPanel />);
    fireEvent.click(screen.getByTestId("frdcd-compose"));
    await waitFor(() => {
      expect(screen.getByTestId("frdcd-written").textContent).toMatch(/false/);
      expect(screen.getByTestId("frdcd-merged").textContent).toMatch(/false/);
      expect(screen.getByTestId("frdcd-ready").textContent).toMatch(/true/);
    });
  });

  it("empty findings without highlight not ready", async () => {
    render(<FloatingResearchDraftCombinedDocumentPanel />);
    fireEvent.change(screen.getByTestId("frdcd-highlight"), {
      target: { value: "" },
    });
    fireEvent.change(screen.getByTestId("frdcd-findings"), {
      target: { value: "" },
    });
    fireEvent.click(screen.getByTestId("frdcd-compose"));
    await waitFor(() => {
      expect(screen.getByTestId("frdcd-ready").textContent).toMatch(/false/);
      expect(screen.getByTestId("frdcd-written").textContent).toMatch(/false/);
    });
  });
});
