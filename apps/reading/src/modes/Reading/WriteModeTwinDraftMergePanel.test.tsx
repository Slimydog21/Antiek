import { afterEach, describe, expect, it } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import WriteModeTwinDraftMergePanel from "./WriteModeTwinDraftMergePanel";

afterEach(() => {
  cleanup();
});

describe("WriteModeTwinDraftMergePanel", () => {
  it("composes draft without writing", async () => {
    render(<WriteModeTwinDraftMergePanel />);
    fireEvent.click(screen.getByTestId("wmtdm-compose"));
    await waitFor(() => {
      expect(screen.getByTestId("wmtdm-ready").textContent).toMatch(/true/);
      expect(screen.getByTestId("wmtdm-written").textContent).toMatch(/false/);
      expect(screen.getByTestId("wmtdm-merged").textContent).toMatch(/false/);
      expect(screen.getByTestId("wmtdm-store").textContent).toMatch(/false/);
    });
  });

  it("no ack not ready", async () => {
    render(<WriteModeTwinDraftMergePanel />);
    fireEvent.click(screen.getByTestId("wmtdm-ack"));
    fireEvent.click(screen.getByTestId("wmtdm-compose"));
    await waitFor(() => {
      expect(screen.getByTestId("wmtdm-ready").textContent).toMatch(/false/);
      expect(screen.getByTestId("wmtdm-written").textContent).toMatch(/false/);
    });
  });
});
