import { afterEach, describe, expect, it } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import SourcePublicationRegistryPanel from "./SourcePublicationRegistryPanel";

afterEach(() => {
  cleanup();
});

describe("SourcePublicationRegistryPanel", () => {
  it("builds pack with fetched false", async () => {
    render(<SourcePublicationRegistryPanel />);
    fireEvent.click(screen.getByTestId("spr-run"));
    await waitFor(() => {
      expect(screen.getByTestId("spr-fetched").textContent).toMatch(/false/);
      expect(screen.getByTestId("spr-summary").textContent).toMatch(
        /arxiv|substack/,
      );
    });
  });

  it("surfaces empty selection error", async () => {
    render(<SourcePublicationRegistryPanel />);
    // uncheck defaults
    fireEvent.click(screen.getByTestId("spr-family-arxiv"));
    fireEvent.click(screen.getByTestId("spr-family-substack"));
    fireEvent.click(screen.getByTestId("spr-run"));
    await waitFor(() => {
      expect(screen.getByTestId("spr-error").textContent).toMatch(/non-empty/);
    });
  });
});
