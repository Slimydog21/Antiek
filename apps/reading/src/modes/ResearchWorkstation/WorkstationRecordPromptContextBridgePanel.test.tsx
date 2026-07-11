import { afterEach, describe, expect, it } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import WorkstationRecordPromptContextBridgePanel from "./WorkstationRecordPromptContextBridgePanel";

afterEach(() => {
  cleanup();
});

describe("WorkstationRecordPromptContextBridgePanel", () => {
  it("bridges without injecting", async () => {
    render(<WorkstationRecordPromptContextBridgePanel />);
    fireEvent.click(screen.getByTestId("wrpcb-bridge"));
    await waitFor(() => {
      expect(screen.getByTestId("wrpcb-injected").textContent).toMatch(
        /false/,
      );
      expect(screen.getByTestId("wrpcb-persisted").textContent).toMatch(
        /false/,
      );
      expect(screen.getByTestId("wrpcb-ready").textContent).toMatch(/true/);
      expect(screen.getByTestId("wrpcb-proposed").textContent).toMatch(
        /scaling holds/,
      );
    });
  });

  it("blank user prompt fails closed", async () => {
    render(<WorkstationRecordPromptContextBridgePanel />);
    fireEvent.change(screen.getByTestId("wrpcb-prompt"), {
      target: { value: "   " },
    });
    fireEvent.click(screen.getByTestId("wrpcb-bridge"));
    await waitFor(() => {
      expect(screen.getByTestId("wrpcb-error").textContent).toMatch(
        /user_prompt/,
      );
    });
  });
});
