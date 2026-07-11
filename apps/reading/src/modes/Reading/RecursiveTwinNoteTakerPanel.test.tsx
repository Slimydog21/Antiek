import { afterEach, describe, expect, it } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import RecursiveTwinNoteTakerPanel from "./RecursiveTwinNoteTakerPanel";

afterEach(() => {
  cleanup();
});

describe("RecursiveTwinNoteTakerPanel", () => {
  it("proposes twin without writing or dispatch", async () => {
    render(<RecursiveTwinNoteTakerPanel />);
    fireEvent.click(screen.getByTestId("rtnt-compose"));
    await waitFor(() => {
      expect(screen.getByTestId("rtnt-ready").textContent).toMatch(/true/);
      expect(screen.getByTestId("rtnt-written").textContent).toMatch(/false/);
      expect(screen.getByTestId("rtnt-prompts").textContent).toMatch(/false/);
      expect(screen.getByTestId("rtnt-live").textContent).toMatch(/false/);
    });
  });

  it("no ack not ready", async () => {
    render(<RecursiveTwinNoteTakerPanel />);
    fireEvent.click(screen.getByTestId("rtnt-ack"));
    fireEvent.click(screen.getByTestId("rtnt-compose"));
    await waitFor(() => {
      expect(screen.getByTestId("rtnt-ready").textContent).toMatch(/false/);
      expect(screen.getByTestId("rtnt-written").textContent).toMatch(/false/);
    });
  });
});
