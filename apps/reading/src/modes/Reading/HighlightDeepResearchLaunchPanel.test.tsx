import { afterEach, describe, expect, it } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import HighlightDeepResearchLaunchPanel from "./HighlightDeepResearchLaunchPanel";

afterEach(() => {
  cleanup();
});

describe("HighlightDeepResearchLaunchPanel", () => {
  it("composes launch_ready without dispatch", async () => {
    render(<HighlightDeepResearchLaunchPanel />);
    fireEvent.click(screen.getByTestId("hdrl-compose"));
    await waitFor(() => {
      expect(screen.getByTestId("hdrl-ready").textContent).toMatch(/true/);
      expect(screen.getByTestId("hdrl-live").textContent).toMatch(/false/);
      expect(screen.getByTestId("hdrl-merged").textContent).toMatch(/false/);
    });
  });

  it("no ack not ready", async () => {
    render(<HighlightDeepResearchLaunchPanel />);
    fireEvent.click(screen.getByTestId("hdrl-ack"));
    fireEvent.click(screen.getByTestId("hdrl-compose"));
    await waitFor(() => {
      expect(screen.getByTestId("hdrl-ready").textContent).toMatch(/false/);
      expect(screen.getByTestId("hdrl-live").textContent).toMatch(/false/);
    });
  });
});
