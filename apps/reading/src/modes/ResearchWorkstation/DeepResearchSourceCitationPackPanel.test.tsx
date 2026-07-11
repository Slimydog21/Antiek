import { afterEach, describe, expect, it } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import DeepResearchSourceCitationPackPanel from "./DeepResearchSourceCitationPackPanel";

afterEach(() => {
  cleanup();
});

describe("DeepResearchSourceCitationPackPanel", () => {
  it("builds pack without remote fetch", async () => {
    render(<DeepResearchSourceCitationPackPanel />);
    fireEvent.click(screen.getByTestId("drscp-build"));
    await waitFor(() => {
      expect(screen.getByTestId("drscp-fetched").textContent).toMatch(
        /false/,
      );
      expect(screen.getByTestId("drscp-ready").textContent).toMatch(/true/);
      expect(screen.getByTestId("drscp-count").textContent).toMatch(/2/);
    });
  });

  it("empty citations not ready", async () => {
    render(<DeepResearchSourceCitationPackPanel />);
    fireEvent.change(screen.getByTestId("drscp-citations"), {
      target: { value: "" },
    });
    fireEvent.click(screen.getByTestId("drscp-build"));
    await waitFor(() => {
      expect(screen.getByTestId("drscp-ready").textContent).toMatch(/false/);
      expect(screen.getByTestId("drscp-fetched").textContent).toMatch(
        /false/,
      );
    });
  });
});
