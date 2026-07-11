import { afterEach, describe, expect, it } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import FloatingResearchViewModeComposePanel from "./FloatingResearchViewModeComposePanel";

afterEach(() => {
  cleanup();
});

describe("FloatingResearchViewModeComposePanel", () => {
  it("fullscreen then float keeps honesty flags false", async () => {
    render(<FloatingResearchViewModeComposePanel />);
    fireEvent.click(screen.getByTestId("frvmc-fullscreen"));
    await waitFor(() => {
      expect(screen.getByTestId("frvmc-view-mode").textContent).toMatch(
        /fullscreen/,
      );
      expect(screen.getByTestId("frvmc-live").textContent).toMatch(/false/);
      expect(screen.getByTestId("frvmc-merged").textContent).toMatch(/false/);
    });
    fireEvent.click(screen.getByTestId("frvmc-float"));
    await waitFor(() => {
      expect(screen.getByTestId("frvmc-view-mode").textContent).toMatch(
        /floating/,
      );
      expect(screen.getByTestId("frvmc-live").textContent).toMatch(/false/);
    });
  });

  it("draft merge intent without execution", async () => {
    render(<FloatingResearchViewModeComposePanel />);
    fireEvent.click(screen.getByTestId("frvmc-draft"));
    await waitFor(() => {
      expect(screen.getByTestId("frvmc-intent").textContent).toMatch(
        /draft_merge/,
      );
      expect(screen.getByTestId("frvmc-merged").textContent).toMatch(/false/);
      expect(screen.getByTestId("frvmc-live").textContent).toMatch(/false/);
    });
  });

  it("full merge fails without completed; succeeds with ack", async () => {
    render(<FloatingResearchViewModeComposePanel />);
    fireEvent.click(screen.getByTestId("frvmc-full"));
    await waitFor(() => {
      expect(screen.getByTestId("frvmc-error").textContent).toMatch(
        /completed|operator_ack/,
      );
    });
    fireEvent.click(screen.getByTestId("frvmc-completed"));
    fireEvent.click(screen.getByTestId("frvmc-ack"));
    fireEvent.click(screen.getByTestId("frvmc-full"));
    await waitFor(() => {
      expect(screen.getByTestId("frvmc-intent").textContent).toMatch(
        /full_merge/,
      );
      expect(screen.getByTestId("frvmc-merged").textContent).toMatch(/false/);
      expect(screen.getByTestId("frvmc-live").textContent).toMatch(/false/);
    });
  });
});
