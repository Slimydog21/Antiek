import { afterEach, describe, expect, it } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import WorkstationRecursiveRecordPackPanel from "./WorkstationRecursiveRecordPackPanel";

afterEach(() => {
  cleanup();
});

describe("WorkstationRecursiveRecordPackPanel", () => {
  it("composes pack without persist or inject", async () => {
    render(<WorkstationRecursiveRecordPackPanel />);
    fireEvent.click(screen.getByTestId("wrrp-compose"));
    await waitFor(() => {
      expect(screen.getByTestId("wrrp-persisted").textContent).toMatch(
        /false/,
      );
      expect(screen.getByTestId("wrrp-injected").textContent).toMatch(
        /false/,
      );
      expect(screen.getByTestId("wrrp-ready").textContent).toMatch(/true/);
    });
  });

  it("empty items not ready", async () => {
    render(<WorkstationRecursiveRecordPackPanel />);
    fireEvent.change(screen.getByTestId("wrrp-items"), {
      target: { value: "" },
    });
    fireEvent.click(screen.getByTestId("wrrp-compose"));
    await waitFor(() => {
      expect(screen.getByTestId("wrrp-ready").textContent).toMatch(/false/);
      expect(screen.getByTestId("wrrp-persisted").textContent).toMatch(
        /false/,
      );
    });
  });
});
