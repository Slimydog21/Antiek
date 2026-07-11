import { afterEach, describe, expect, it } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import RecursiveTwinSessionPackComposePanel from "./RecursiveTwinSessionPackComposePanel";

afterEach(() => {
  cleanup();
});

describe("RecursiveTwinSessionPackComposePanel", () => {
  it("composes pack without store mutation", async () => {
    render(<RecursiveTwinSessionPackComposePanel />);
    fireEvent.click(screen.getByTestId("rtsp-compose"));
    await waitFor(() => {
      expect(screen.getByTestId("rtsp-mutated").textContent).toMatch(/false/);
      expect(screen.getByTestId("rtsp-ready").textContent).toMatch(/true/);
      expect(screen.getByTestId("rtsp-summary").textContent).toMatch(
        /twin pack/,
      );
    });
  });

  it("unbound fails pack_ready", async () => {
    render(<RecursiveTwinSessionPackComposePanel />);
    fireEvent.click(screen.getByTestId("rtsp-bound"));
    fireEvent.click(screen.getByTestId("rtsp-compose"));
    await waitFor(() => {
      expect(screen.getByTestId("rtsp-ready").textContent).toMatch(/false/);
      expect(screen.getByTestId("rtsp-mutated").textContent).toMatch(/false/);
    });
  });
});
