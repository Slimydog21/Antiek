import { afterEach, describe, expect, it } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import WorkstationSessionInsightRecordPanel from "./WorkstationSessionInsightRecordPanel";

afterEach(() => {
  cleanup();
});

describe("WorkstationSessionInsightRecordPanel", () => {
  it("records without persisting or injecting", async () => {
    render(<WorkstationSessionInsightRecordPanel />);
    fireEvent.click(screen.getByTestId("wsir-compose"));
    await waitFor(() => {
      expect(screen.getByTestId("wsir-ready").textContent).toMatch(/true/);
      expect(screen.getByTestId("wsir-persisted").textContent).toMatch(/false/);
      expect(screen.getByTestId("wsir-injected").textContent).toMatch(/false/);
    });
  });

  it("no ack not ready", async () => {
    render(<WorkstationSessionInsightRecordPanel />);
    fireEvent.click(screen.getByTestId("wsir-ack"));
    fireEvent.click(screen.getByTestId("wsir-compose"));
    await waitFor(() => {
      expect(screen.getByTestId("wsir-ready").textContent).toMatch(/false/);
      expect(screen.getByTestId("wsir-persisted").textContent).toMatch(/false/);
    });
  });
});
