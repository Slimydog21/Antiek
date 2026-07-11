import { afterEach, describe, expect, it } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import RecursiveTwinIntelligentSearchPanel from "./RecursiveTwinIntelligentSearchPanel";

afterEach(() => {
  cleanup();
});

describe("RecursiveTwinIntelligentSearchPanel", () => {
  it("searches demo corpus with remote false", async () => {
    render(
      <RecursiveTwinIntelligentSearchPanel initialQuery="scaling" />,
    );
    fireEvent.click(screen.getByTestId("rtis-run"));
    await waitFor(() => {
      expect(screen.getByTestId("rtis-remote").textContent).toMatch(/false/);
      const hitText = screen.getByTestId("rtis-hit-count").textContent || "";
      expect(hitText).toMatch(/hits=[1-9]/);
    });
  });

  it("surfaces empty query error", async () => {
    render(<RecursiveTwinIntelligentSearchPanel initialQuery="" />);
    fireEvent.click(screen.getByTestId("rtis-run"));
    await waitFor(() => {
      expect(screen.getByTestId("rtis-error").textContent).toMatch(/query/);
    });
  });

  it("zero hits for unrelated query", async () => {
    render(
      <RecursiveTwinIntelligentSearchPanel initialQuery="quantum teleportation" />,
    );
    fireEvent.click(screen.getByTestId("rtis-run"));
    await waitFor(() => {
      expect(screen.getByTestId("rtis-hit-count").textContent).toMatch(
        /hits=0/,
      );
      expect(screen.getByTestId("rtis-remote").textContent).toMatch(/false/);
    });
  });
});
