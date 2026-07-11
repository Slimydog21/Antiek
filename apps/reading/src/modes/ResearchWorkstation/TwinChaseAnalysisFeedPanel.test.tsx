import { afterEach, describe, expect, it } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import TwinChaseAnalysisFeedPanel from "./TwinChaseAnalysisFeedPanel";

afterEach(() => {
  cleanup();
});

describe("TwinChaseAnalysisFeedPanel", () => {
  it("feed ready without twin write", async () => {
    render(<TwinChaseAnalysisFeedPanel />);
    fireEvent.click(screen.getByTestId("tcaf-compose"));
    await waitFor(() => {
      expect(screen.getByTestId("tcaf-ready").textContent).toMatch(/true/);
      expect(screen.getByTestId("tcaf-twin").textContent).toMatch(/false/);
      expect(screen.getByTestId("tcaf-record").textContent).toMatch(/false/);
      expect(screen.getByTestId("tcaf-prompts").textContent).toMatch(/false/);
      expect(screen.getByTestId("tcaf-live").textContent).toMatch(/false/);
    });
  });

  it("no ack not ready", async () => {
    render(<TwinChaseAnalysisFeedPanel />);
    fireEvent.click(screen.getByTestId("tcaf-ack"));
    fireEvent.click(screen.getByTestId("tcaf-compose"));
    await waitFor(() => {
      expect(screen.getByTestId("tcaf-ready").textContent).toMatch(/false/);
      expect(screen.getByTestId("tcaf-twin").textContent).toMatch(/false/);
    });
  });
});
