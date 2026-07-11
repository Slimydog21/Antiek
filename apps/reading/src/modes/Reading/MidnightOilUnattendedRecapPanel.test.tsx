import { afterEach, describe, expect, it } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import MidnightOilUnattendedRecapPanel from "./MidnightOilUnattendedRecapPanel";

afterEach(() => {
  cleanup();
});

describe("MidnightOilUnattendedRecapPanel", () => {
  it("composes recap without re-authorizing execution", async () => {
    render(<MidnightOilUnattendedRecapPanel />);
    fireEvent.click(screen.getByTestId("mour-compose"));
    await waitFor(() => {
      expect(screen.getByTestId("mour-ready").textContent).toMatch(/true/);
      expect(screen.getByTestId("mour-live").textContent).toMatch(/false/);
      expect(screen.getByTestId("mour-ceiling-flag").textContent).toMatch(
        /true/,
      );
    });
  });

  it("no ack not ready", async () => {
    render(<MidnightOilUnattendedRecapPanel />);
    fireEvent.click(screen.getByTestId("mour-ack"));
    fireEvent.click(screen.getByTestId("mour-compose"));
    await waitFor(() => {
      expect(screen.getByTestId("mour-ready").textContent).toMatch(/false/);
      expect(screen.getByTestId("mour-live").textContent).toMatch(/false/);
    });
  });
});
