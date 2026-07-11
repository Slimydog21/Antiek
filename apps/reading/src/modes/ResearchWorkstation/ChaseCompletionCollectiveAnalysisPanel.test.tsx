import { afterEach, describe, expect, it } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import ChaseCompletionCollectiveAnalysisPanel from "./ChaseCompletionCollectiveAnalysisPanel";

afterEach(() => {
  cleanup();
});

describe("ChaseCompletionCollectiveAnalysisPanel", () => {
  it("draft analysis ready without write", async () => {
    render(<ChaseCompletionCollectiveAnalysisPanel />);
    fireEvent.click(screen.getByTestId("ccca-compose"));
    await waitFor(() => {
      expect(screen.getByTestId("ccca-ready").textContent).toMatch(/true/);
      expect(screen.getByTestId("ccca-written").textContent).toMatch(/false/);
      expect(screen.getByTestId("ccca-live").textContent).toMatch(/false/);
      expect(screen.getByTestId("ccca-pack").textContent).toMatch(/false/);
    });
  });

  it("full analysis without ack shows error", async () => {
    render(<ChaseCompletionCollectiveAnalysisPanel />);
    fireEvent.change(screen.getByTestId("ccca-kind"), {
      target: { value: "full_analysis" },
    });
    fireEvent.click(screen.getByTestId("ccca-ack"));
    fireEvent.click(screen.getByTestId("ccca-compose"));
    await waitFor(() => {
      expect(screen.getByTestId("ccca-error").textContent).toMatch(
        /operator_ack/i,
      );
    });
  });
});
