import { afterEach, describe, expect, it } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import ReadingHighlightFloatTwinFeedPanel from "./ReadingHighlightFloatTwinFeedPanel";

afterEach(() => {
  cleanup();
});

describe("ReadingHighlightFloatTwinFeedPanel", () => {
  it("pack ready without dispatch or twin write", async () => {
    render(<ReadingHighlightFloatTwinFeedPanel />);
    fireEvent.click(screen.getByTestId("rhftf-compose"));
    await waitFor(() => {
      expect(screen.getByTestId("rhftf-ready").textContent).toMatch(/true/);
      expect(screen.getByTestId("rhftf-live").textContent).toMatch(/false/);
      expect(screen.getByTestId("rhftf-merge").textContent).toMatch(/false/);
      expect(screen.getByTestId("rhftf-twin-w").textContent).toMatch(/false/);
    });
  });

  it("no ack not ready", async () => {
    render(<ReadingHighlightFloatTwinFeedPanel />);
    fireEvent.click(screen.getByTestId("rhftf-ack"));
    fireEvent.click(screen.getByTestId("rhftf-compose"));
    await waitFor(() => {
      expect(screen.getByTestId("rhftf-ready").textContent).toMatch(/false/);
      expect(screen.getByTestId("rhftf-live").textContent).toMatch(/false/);
    });
  });
});
