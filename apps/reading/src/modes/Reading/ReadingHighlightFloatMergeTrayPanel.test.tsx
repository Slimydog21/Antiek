import { afterEach, describe, expect, it } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import ReadingHighlightFloatMergeTrayPanel from "./ReadingHighlightFloatMergeTrayPanel";

afterEach(() => {
  cleanup();
});

describe("ReadingHighlightFloatMergeTrayPanel", () => {
  it("spawn_only surface ready without dispatch", async () => {
    render(<ReadingHighlightFloatMergeTrayPanel />);
    fireEvent.click(screen.getByTestId("rhfmt-compose"));
    await waitFor(() => {
      expect(screen.getByTestId("rhfmt-ready").textContent).toMatch(/true/);
      expect(screen.getByTestId("rhfmt-live").textContent).toMatch(/false/);
      expect(screen.getByTestId("rhfmt-merged").textContent).toMatch(/false/);
      expect(screen.getByTestId("rhfmt-pack").textContent).toMatch(/false/);
    });
  });

  it("no ack not ready", async () => {
    render(<ReadingHighlightFloatMergeTrayPanel />);
    fireEvent.click(screen.getByTestId("rhfmt-ack"));
    fireEvent.click(screen.getByTestId("rhfmt-compose"));
    await waitFor(() => {
      expect(screen.getByTestId("rhfmt-ready").textContent).toMatch(/false/);
      expect(screen.getByTestId("rhfmt-live").textContent).toMatch(/false/);
    });
  });
});
